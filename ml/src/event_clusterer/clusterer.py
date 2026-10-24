"""Модуль 10: Кластеризация событий.

Группирует новости об одном событии по общим сущностям + временному окну.
Каскадная стратегия:
1. Детерминированная группировка по ключевым сущностям + временному окну
2. LLM-арбитраж для спорных пар (заглушка)

Вход: JSON с новостями и извлечёнными сущностями (модуль 8).
Выход: JSON с событиями (группами новостей).

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Временное окно для группировки (в днях)
TIME_WINDOW_DAYS = 3


@dataclass
class EventCluster:
    """Событие (группа новостей об одном происшествии)."""

    event_id: str
    title: str
    news_ids: list[str] = field(default_factory=list)
    entities: dict[str, list[str]] = field(default_factory=dict)  # общие сущности
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Ключевые типы сущностей для группировки (слишком общие исключаем)
KEY_ENTITY_TYPES = {"организация", "персона", "место"}


class EventClusterer:
    """Кластеризует новости в события."""

    def __init__(self, time_window_days: int = TIME_WINDOW_DAYS):
        self.time_window_days = time_window_days

    def _parse_date(self, date_str: str) -> tuple[int, int, int]:
        """Парсит дату в (год, месяц, день)."""
        try:
            # Поддерживаем ISO и простые форматы
            date_part = date_str.split("T")[0].split(" ")[0]
            parts = date_part.split("-")
            if len(parts) == 3:
                return int(parts[0]), int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            pass
        return 0, 0, 0

    def _date_diff_days(self, d1: str, d2: str) -> int:
        """Разница между датами в днях."""
        from datetime import date
        try:
            first = date(*self._parse_date(d1))
            second = date(*self._parse_date(d2))
            return abs((first - second).days)
        except ValueError:
            # Unknown dates do not establish temporal proximity.
            return self.time_window_days + 1

    def _entity_overlap(self, a: dict, b: dict) -> float:
        """Доля общих ключевых сущностей между двумя новостями.

        Учитываются только ключевые типы (организация, персона, место),
        т.к. финансовые показатели слишком общие для группировки.

        Метрика: |A ∩ B| / |A ∪ B| (Жаккар) вместо min — не завышает overlap
        для новостей с малым числом сущностей.
        """
        entities_a = set()
        for e in a.get("entities", []):
            if e.get("type", "") in KEY_ENTITY_TYPES:
                entities_a.add(e.get("text", "").lower())
        entities_b = set()
        for e in b.get("entities", []):
            if e.get("type", "") in KEY_ENTITY_TYPES:
                entities_b.add(e.get("text", "").lower())
        if not entities_a or not entities_b:
            return 0.0
        return len(entities_a & entities_b) / len(entities_a | entities_b)

    def _should_merge(self, a: dict, b: dict) -> bool:
        """Проверяет, относятся ли две новости к одному событию."""
        # Временное окно
        date_a = a.get("published_at", "")
        date_b = b.get("published_at", "")
        if self._date_diff_days(date_a, date_b) > self.time_window_days:
            return False
        # Пересечение сущностей (Жаккар)
        overlap = self._entity_overlap(a, b)
        return overlap >= 0.5

    def _cluster_entities(self, news: dict) -> dict[str, list[str]]:
        """Собирает сущности новости в dict[type, list[text]]."""
        entities: dict[str, list[str]] = {}
        for e in news.get("entities", []):
            etype = e.get("type", "")
            text = e.get("text", "")
            if etype not in entities:
                entities[etype] = []
            if text not in entities[etype]:
                entities[etype].append(text)
        return entities

    def cluster(self, news_with_entities: list[dict]) -> list[EventCluster]:
        """Кластеризует новости в события.

        Улучшения:
        - Сравнение со ВСЕМИ новостями кластера (не только с первой).
        - Мягкий порог: новость попадает в кластер, если совпадает хотя бы
          с одной новостью кластера (а не со всеми).
        """
        clusters: list[EventCluster] = []
        # news_id -> индекс кластера
        assigned: dict[str, int] = {}

        for i, news in enumerate(news_with_entities):
            news_id = news.get("news_id", f"news_{i}")
            matched = -1
            best_overlap = 0.0
            for ci, cluster in enumerate(clusters):
                # Сравниваем со всеми новостями кластера
                for member_id in cluster.news_ids:
                    member = next(
                        (n for n in news_with_entities if n.get("news_id") == member_id),
                        {},
                    )
                    if self._should_merge(news, member):
                        overlap = self._entity_overlap(news, member)
                        if overlap > best_overlap:
                            best_overlap = overlap
                            matched = ci
                        break  # достаточно одного совпадения

            if matched >= 0:
                clusters[matched].news_ids.append(news_id)
                # Обновляем общие сущности
                for etype, texts in self._cluster_entities(news).items():
                    if etype not in clusters[matched].entities:
                        clusters[matched].entities[etype] = []
                    for t in texts:
                        if t not in clusters[matched].entities[etype]:
                            clusters[matched].entities[etype].append(t)
            else:
                # Новый кластер
                clusters.append(
                    EventCluster(
                        event_id=f"evt_{len(clusters) + 1}",
                        title=news.get("title", ""),
                        news_ids=[news_id],
                        entities=self._cluster_entities(news),
                    )
                )

        return clusters

    def save_json(self, clusters: list[EventCluster], out_path: str | Path) -> Path:
        """Сохраняет события в JSON."""
        out = Path(out_path)
        data = {
            "module": "event_clusterer",
            "version": "1.0",
            "count": len(clusters),
            "events": [c.to_dict() for c in clusters],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def cluster_events(
    news_json: str | Path,
    out_path: str | Path,
) -> list[EventCluster]:
    """Удобная функция: читает новости с сущностями, кластеризует, сохраняет."""
    data = json.loads(Path(news_json).read_text(encoding="utf-8"))
    news = data if isinstance(data, list) else data.get("news", [])
    clusterer = EventClusterer()
    clusters = clusterer.cluster(news)
    clusterer.save_json(clusters, out_path)
    return clusters


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Использование: python clusterer.py <news_json> <out_path>")
        sys.exit(1)
    cluster_events(sys.argv[1], sys.argv[2])
    print("События сформированы.")