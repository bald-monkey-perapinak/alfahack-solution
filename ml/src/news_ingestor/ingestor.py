"""Модуль 9: Приём новостей (bronze/silver).

Принимает сырые новости, извлекает текст, нормализует, дедуплицирует
(MinHash LSH) и выводит в JSON.

Вход: список сырых новостей (JSON).
Выход: JSON с очищенными и дедуплицированными новостями.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Стоп-слова для шинглов (служебные)
STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а",
    "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же",
    "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от",
    "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже",
    "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него",
    "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
    "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо",
    "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без",
    "будто", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда",
    "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним",
    "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас",
    "были", "куда", "зачем", "всех", "никогда", "можно", "при", "наконец",
    "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через",
    "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три",
    "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда",
    "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда",
    "конечно", "всю", "между",
}

# Параметры MinHash LSH
LSH_BANDS = 16          # число полос
LSH_ROWS = 8            # строк в полосе (всего 16*8 = 128 хешей)
LSH_THRESHOLD = 0.8     # порог схожести для кандидатов (приблизительный)

# Паттерны чисел для нормализации
_NUMBER_PATTERNS = [
    # "1,5 млн" -> "1500000"
    (re.compile(r"(\d+)[.,](\d+)\s*(млн|млрд|тыс|трлн)"), lambda m: _expand_number(m)),
    # "1,5" -> "1.5" (десятичная запятая)
    (re.compile(r"(?<=\d),(?=\d)"), lambda m: "."),
    # "1 500 000" -> "1500000" (пробелы-разделители)
    (re.compile(r"(?<=\d)\s+(?=\d{3})"), lambda m: ""),
]


def _expand_number(match: re.Match) -> str:
    """Разворачивает '1,5 млн' в '1500000'."""
    num = float(match.group(1) + "." + match.group(2))
    unit = match.group(3)
    mult = {"тыс": 1_000, "млн": 1_000_000, "млрд": 1_000_000_000, "трлн": 1_000_000_000_000}
    return str(int(num * mult[unit]))


@dataclass
class NewsArticle:
    """Очищенная новость (silver)."""

    news_id: str
    title: str
    text: str
    source: str
    published_at: str
    url: str = ""
    is_duplicate: bool = False
    duplicate_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NewsIngestor:
    """Принимает и очищает новости."""

    def __init__(
        self,
        shingle_size: int = 5,
        jaccard_threshold: float = 0.8,
        num_perm: int = 128,
        bands: int = LSH_BANDS,
        rows: int = LSH_ROWS,
    ):
        self.shingle_size = shingle_size
        self.jaccard_threshold = jaccard_threshold
        self.num_perm = num_perm
        self.bands = bands
        self.rows = rows

    def _normalize_text(self, text: str) -> str:
        """Нормализует текст: убирает лишние пробелы, нормализует кавычки."""
        text = re.sub(r"\s+", " ", text).strip()
        text = text.replace("«", "\"").replace("»", "\"")
        text = text.replace("—", "-").replace("–", "-")
        return text

    def _normalize_numbers(self, text: str) -> str:
        """Нормализует числа: '1,5 млн' -> '1500000', '1,5' -> '1.5'."""
        for pattern, repl in _NUMBER_PATTERNS:
            text = pattern.sub(repl, text)
        return text

    def _extract_text(self, raw: dict) -> str:
        """Извлекает текст из сырой новости."""
        # Поддерживаем разные форматы
        if raw.get("text"):
            return self._normalize_text(raw["text"])
        if raw.get("content"):
            return self._normalize_text(raw["content"])
        if raw.get("body"):
            return self._normalize_text(raw["body"])
        return ""

    def _shingles(self, text: str) -> set[str]:
        """Строит шинглы (n-граммы токенов) из текста."""
        tokens = [
            t.lower() for t in re.findall(r"\w+", text)
            if t.lower() not in STOPWORDS
        ]
        shingles = set()
        for i in range(len(tokens) - self.shingle_size + 1):
            shingle = " ".join(tokens[i:i + self.shingle_size])
            shingles.add(shingle)
        return shingles

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        """Считает коэффициент Жаккара."""
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _minhash(self, shingles: set[str]) -> list[int]:
        """Считает MinHash-подпись (num_perm хешей)."""
        signature = []
        for i in range(self.num_perm):
            min_hash = float("inf")
            for shingle in shingles:
                h = int(hashlib.md5(f"{i}:{shingle}".encode()).hexdigest()[:8], 16)
                if h < min_hash:
                    min_hash = h
            signature.append(min_hash if min_hash != float("inf") else 0)
        return signature

    def _lsh_bands(self, signature: list[int]) -> list[tuple[int, tuple[int, ...]]]:
        """Разбивает MinHash-подпись на полосы (для LSH-индекса).

        Возвращает список (номер_полосы, кортеж_хешей_полосы).
        """
        bands = []
        for b in range(self.bands):
            start = b * self.rows
            end = start + self.rows
            band = tuple(signature[start:end])
            bands.append((b, band))
        return bands

    def _is_duplicate(self, a: NewsArticle, b: NewsArticle) -> bool:
        """Проверяет, является ли a дубликатом b (по Жаккару шинглов)."""
        shingles_a = self._shingles(a.title + " " + a.text)
        shingles_b = self._shingles(b.title + " " + b.text)
        return self._jaccard(shingles_a, shingles_b) >= self.jaccard_threshold

    def _deduplicate_lsh(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        """Дедупликация через MinHash LSH (O(n) вместо O(n^2)).

        Строит LSH-индекс: для каждой полосы подписи — бакет кандидатов.
        Кандидаты, попавшие в один бакет, проверяются точным Жаккаром.
        """
        # Строим подписи
        signatures = []
        for article in articles:
            shingles = self._shingles(article.title + " " + article.text)
            signatures.append(self._minhash(shingles))

        # LSH-индекс: (band, band_hash) -> [индексы статей]
        index: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
        for idx, sig in enumerate(signatures):
            for band in self._lsh_bands(sig):
                index[band].append(idx)

        # Для каждой статьи ищем кандидатов и проверяем точным Жаккаром
        result = []
        for i, article in enumerate(articles):
            is_dup = False
            candidates = set()
            for band in self._lsh_bands(signatures[i]):
                for cand in index[band]:
                    if cand < i:
                        candidates.add(cand)
            # Проверяем кандидатов точным Жаккаром (только те, что раньше)
            for j in sorted(candidates):
                if self._is_duplicate(article, articles[j]):
                    article.is_duplicate = True
                    article.duplicate_of = articles[j].news_id
                    is_dup = True
                    break
            result.append(article)
        return result

    def ingest(self, raw_news: list[dict]) -> list[NewsArticle]:
        """Принимает сырые новости, очищает и дедуплицирует."""
        articles = []
        for raw in raw_news:
            text = self._extract_text(raw)
            if not text:
                continue
            article = NewsArticle(
                news_id=raw.get("news_id", f"news_{len(articles)}"),
                title=self._normalize_text(raw.get("title", "")),
                text=text,
                source=raw.get("source", ""),
                published_at=raw.get("published_at", ""),
                url=raw.get("url", ""),
            )
            articles.append(article)

        # Дедупликация через MinHash LSH (O(n) вместо O(n^2))
        return self._deduplicate_lsh(articles)

    def save_json(self, articles: list[NewsArticle], out_path: str | Path) -> Path:
        """Сохраняет новости в JSON."""
        out = Path(out_path)
        data = {
            "module": "news_ingestor",
            "version": "1.0",
            "count": len(articles),
            "unique": sum(1 for a in articles if not a.is_duplicate),
            "duplicates": sum(1 for a in articles if a.is_duplicate),
            "articles": [a.to_dict() for a in articles],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def ingest_news(
    raw_json: str | Path,
    out_path: str | Path,
) -> list[NewsArticle]:
    """Удобная функция: читает сырые новости, очищает, сохраняет."""
    data = json.loads(Path(raw_json).read_text(encoding="utf-8"))
    raw_news = data if isinstance(data, list) else data.get("news", [])
    ingestor = NewsIngestor()
    articles = ingestor.ingest(raw_news)
    ingestor.save_json(articles, out_path)
    return articles


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Использование: python ingestor.py <raw_json> <out_path>")
        sys.exit(1)
    ingest_news(sys.argv[1], sys.argv[2])
    print("Новости обработаны.")