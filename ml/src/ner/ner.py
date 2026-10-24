"""Модуль 8: NER (извлечение сущностей из новостей).

Извлекает сущности из текста новости с помощью GLiNER (zero-shot NER
с кастомными типами). Типы сущностей: организации, персоны, места,
валюты, показатели, правовые акты, отрасли.

Вход: текст новости (JSON).
Выход: JSON с извлечёнными сущностями.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Типы сущностей для извлечения (кастомные, под банковскую доменную модель)
ENTITY_TYPES = [
    "организация",        # компания, банк, орган власти
    "персона",            # человек, руководитель
    "место",              # страна, регион, город
    "валюта",             # рубль, доллар, юань
    "финансовый показатель",  # инфляция, ВВП, ставка
    "правовой акт",       # закон, постановление, санкционный пакет
    "отрасль",            # отрасль экономики
    "сырьё",              # нефть, золото, металлы
    "число",              # сумма, процент, количество
    "дата",               # дата события
]

# Регулярные выражения для извлечения чисел, дат, валют
_NUMBER_RE = re.compile(r"\d[\d\s]*[.,]?\d*\s*(?:%|млн|млрд|тыс|трлн|млн руб|млрд руб)?")
_DATE_RE = re.compile(
    r"\b(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])[./-](?:19|20)\d{2}\b"
    r"|\b(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}\b"
)
_CURRENCY_RE = re.compile(
    r"\b(?:руб(?:ль|лей|ля)?|доллар(?:ов|а)?|юан(?:ь|я|ей)?|евро|фунт(?:ов)?|тенге|рупий?)\b",
    re.IGNORECASE,
)

# Словари известных сущностей (расширенные)
KNOWN_ORGANIZATIONS = [
    "Банк России", "ЦБ", "ЦБ РФ", "Альфа-Банк", "Минфин", "ФНС", "ФТС",
    "Минэкономразвития", "Минпромторг", "Минсельхоз", "Росстат", "Мосбиржа",
    "Сбербанк", "ВТБ", "Газпромбанк", "Совкомбанк", "Т-Банк", "Тинькофф",
    "ЕЦБ", "ФРС", "МВФ", "Всемирный банк", "ОПЕК", "ЕС",
]
KNOWN_PERSONS = [
    "Эльвира Набиуллина", "Набиуллина", "Владимир Путин", "Путин",
    "Михаил Мишустин", "Мишустин", "Антон Силуанов", "Силуанов",
    "Максим Орешкин", "Орешкин", "Герман Греф", "Греф",
]
KNOWN_PLACES = [
    "Китай", "Турция", "Россия", "Москва", "Санкт-Петербург", "ОАЭ",
    "Индия", "США", "Европа", "Евросоюз", "Казахстан", "Беларусь",
    "Гонконг", "Сингапур", "Дубай", "Пекин", "Вашингтон",
]
KNOWN_CURRENCIES = [
    "рубль", "доллар", "юань", "евро", "фунт", "тенге", "рупия",
]
KNOWN_INDICATORS = [
    "инфляция", "ВВП", "ключевая ставка", "ставка", "курс", "индекс",
    "промпроизводство", "безработица", "экспорт", "импорт", "дефицит",
    "профицит", "ликвидность", "рентабельность", "оборот", "выручка",
    "прибыль", "убыток", "капитализация", "инвестиции",
]
KNOWN_LEGAL = [
    "закон", "постановление", "санкционный пакет", "указ", "решение",
    "директива", "регламент", "поправки", "законопроект",
]
KNOWN_INDUSTRIES = [
    "нефтегазовый", "металлургия", "сельское хозяйство", "АПК", "строительство",
    "розничная торговля", "ритейл", "логистика", "машиностроение", "химия",
    "фармацевтика", "IT", "телеком", "энергетика", "транспорт",
]
KNOWN_COMMODITIES = [
    "нефть", "золото", "металлы", "газ", "уголь", "пшеница", "зерно",
    "медь", "алюминий", "никель", "сталь", "железная руда", "удобрения",
]

# Нормализация сущностей: синонимы -> каноническая форма
ENTITY_ALIASES = {
    "ЦБ": "Банк России",
    "ЦБ РФ": "Банк России",
    "Тинькофф": "Т-Банк",
    "США": "Соединённые Штаты",
    "ЕС": "Евросоюз",
    "Евросоюз": "ЕС",
    "АПК": "сельское хозяйство",
    "ритейл": "розничная торговля",
    "ставка": "ключевая ставка",
    "курс": "валютный курс",
}


@dataclass
class Entity:
    """Извлечённая сущность."""

    text: str
    type: str
    start: int
    end: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NERExtractor:
    """Извлекает сущности из текста с помощью GLiNER (или fallback).

    Если GLiNER/torch недоступны (например, DLL-проблема на Windows),
    используется детерминированный fallback на основе словарей и regex.
    """

    def __init__(self, model_name: str = "urchade/gliner_multi-v2.1"):
        self.model_name = model_name
        self._model = None
        self._gliner_available = None

    def _check_gliner(self) -> bool:
        """Проверяет доступность GLiNER.

        Проверяет torch в отдельном subprocess, т.к. сломанный torch вызывает
        краш процесса (access violation), который не перехватывается try/except
        и убивает основной процесс. Subprocess изолирует краш.
        """
        import os
        if os.getenv("NER_ALLOW_MODEL_DOWNLOAD", "false").lower() != "true":
            return False
        if self._gliner_available is None:
            import subprocess
            import sys
            try:
                # Проверяем torch в отдельном процессе
                result = subprocess.run(
                    [sys.executable, "-c", "import torch; import gliner"],
                    capture_output=True,
                    timeout=30,
                )
                self._gliner_available = result.returncode == 0
            except Exception:
                self._gliner_available = False
        return self._gliner_available

    def _load_model(self):
        """Лениво загружает модель GLiNER."""
        if self._model is None:
            from gliner import GLiNER
            self._model = GLiNER.from_pretrained(self.model_name)
        return self._model

    def _normalize_entity(self, text: str, etype: str) -> str:
        """Нормализует сущность: синоним -> каноническая форма."""
        return ENTITY_ALIASES.get(text, text)

    def _add_entity(
        self, entities: list[Entity], text: str, etype: str,
        start: int, end: int, confidence: float = 0.8,
    ) -> None:
        """Добавляет сущность с нормализацией и дедупликацией по позиции."""
        norm = self._normalize_entity(text, etype)
        # Дедупликация по (start, end) — не добавляем дубли
        for e in entities:
            if e.start == start and e.end == end:
                return
        entities.append(
            Entity(text=norm, type=etype, start=start, end=end, confidence=confidence)
        )

    def _extract_regex(self, text: str, entities: list[Entity]) -> None:
        """Извлекает числа, даты и валюты через regex."""
        # Числа (суммы, проценты)
        for m in _NUMBER_RE.finditer(text):
            token = m.group(0).strip()
            if token and token[0].isdigit():
                self._add_entity(
                    entities, token, "число", m.start(), m.end(), confidence=0.9
                )
        # Даты
        for m in _DATE_RE.finditer(text):
            self._add_entity(
                entities, m.group(0), "дата", m.start(), m.end(), confidence=0.95
            )
        # Валюты
        for m in _CURRENCY_RE.finditer(text):
            self._add_entity(
                entities, m.group(0), "валюта", m.start(), m.end(), confidence=0.85
            )

    def _extract_from_dicts(self, text: str, entities: list[Entity]) -> None:
        """Извлекает сущности из словарей (организации, персоны, места и т.д.)."""
        known = {
            "организация": KNOWN_ORGANIZATIONS,
            "персона": KNOWN_PERSONS,
            "место": KNOWN_PLACES,
            "валюта": KNOWN_CURRENCIES,
            "финансовый показатель": KNOWN_INDICATORS,
            "правовой акт": KNOWN_LEGAL,
            "отрасль": KNOWN_INDUSTRIES,
            "сырьё": KNOWN_COMMODITIES,
        }
        text_lower = text.lower()
        for etype, terms in known.items():
            for term in terms:
                term_lower = term.lower()
                start = 0
                while True:
                    idx = text_lower.find(term_lower, start)
                    if idx == -1:
                        break
                    self._add_entity(
                        entities, text[idx:idx + len(term)], etype,
                        idx, idx + len(term), confidence=0.8,
                    )
                    start = idx + len(term)

    def _fallback_extract(self, text: str) -> list[Entity]:
        """Детерминированный fallback: словари + regex.

        Используется, когда GLiNER недоступен. Извлекает известные
        организации, персоны, места, валюты, показатели, а также
        числа, даты и валюты через regex.
        """
        entities = []
        self._extract_from_dicts(text, entities)
        self._extract_regex(text, entities)
        # Сортируем по позиции
        entities.sort(key=lambda e: e.start)
        return entities

    def extract(self, text: str, entity_types: list[str] | None = None) -> list[Entity]:
        """Извлекает сущности из текста."""
        types = entity_types or ENTITY_TYPES
        if self._check_gliner():
            try:
                model = self._load_model()
                predictions = model.predict_entities(text, types)
                entities = []
                for pred in predictions:
                    entities.append(
                        Entity(
                            text=pred["text"],
                            type=pred["label"],
                            start=pred.get("start", 0),
                            end=pred.get("end", 0),
                            confidence=pred.get("score", 0.0),
                        )
                    )
                return entities
            except Exception:
                # GLiNER не сработал — fallback
                return self._fallback_extract(text)
        else:
            return self._fallback_extract(text)

    def extract_from_json(
        self, news: dict, text_field: str = "text"
    ) -> dict:
        """Извлекает сущности из JSON новости."""
        text = news.get(text_field, "")
        entities = self.extract(text)
        return {
            "news_id": news.get("news_id", ""),
            "text": text,
            "entities": [e.to_dict() for e in entities],
        }

    def save_json(self, result: dict, out_path: str | Path) -> Path:
        """Сохраняет результат в JSON."""
        out = Path(out_path)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def extract_entities(
    news_json: str | Path,
    out_path: str | Path,
    model_name: str = "urchade/gliner_multi-v2.1",
) -> dict:
    """Удобная функция: читает новость (JSON), извлекает сущности, сохраняет."""
    news = json.loads(Path(news_json).read_text(encoding="utf-8"))
    extractor = NERExtractor(model_name)
    result = extractor.extract_from_json(news)
    extractor.save_json(result, out_path)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(
            "Использование: python ner.py <news_json> <out_path> [model_name]"
        )
        sys.exit(1)
    model = sys.argv[3] if len(sys.argv) > 3 else "urchade/gliner_multi-v2.1"
    extract_entities(sys.argv[1], sys.argv[2], model)
    print("Сущности извлечены.")