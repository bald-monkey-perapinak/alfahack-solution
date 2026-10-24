"""Тесты для модуля кластеризации событий (event_clusterer.clusterer)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from event_clusterer.clusterer import (  # noqa: E402
    EventClusterer,
    EventCluster,
    cluster_events,
    KEY_ENTITY_TYPES,
)


@pytest.fixture
def clusterer() -> EventClusterer:
    return EventClusterer()


@pytest.fixture
def sample_news(tmp_path: Path) -> Path:
    """Создаёт JSON с новостями и сущностями."""
    news = {
        "news": [
            {
                "news_id": "n1",
                "title": "ЦБ сохранил ставку",
                "published_at": "2026-09-11",
                "entities": [
                    {"text": "Банк России", "type": "организация"},
                    {"text": "ЦБ", "type": "организация"},
                    {"text": "ключевая ставка", "type": "финансовый показатель"},
                ],
            },
            {
                "news_id": "n2",
                "title": "ЦБ сохранил ставку, риторика жёстче",
                "published_at": "2026-09-11",
                "entities": [
                    {"text": "Банк России", "type": "организация"},
                    {"text": "ЦБ", "type": "организация"},
                ],
            },
            {
                "news_id": "n3",
                "title": "Инфляция замедлилась",
                "published_at": "2026-09-12",
                "entities": [
                    {"text": "инфляция", "type": "финансовый показатель"},
                    {"text": "Россия", "type": "место"},
                ],
            },
        ]
    }
    path = tmp_path / "news.json"
    path.write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")
    return path


def test_key_entity_types():
    """Ключевые типы сущностей."""
    assert "организация" in KEY_ENTITY_TYPES
    assert "персона" in KEY_ENTITY_TYPES
    assert "место" in KEY_ENTITY_TYPES


def test_parse_date(clusterer: EventClusterer):
    """Парсинг даты."""
    assert clusterer._parse_date("2026-09-11") == (2026, 9, 11)
    assert clusterer._parse_date("2026-09-11T12:00:00") == (2026, 9, 11)
    assert clusterer._parse_date("") == (0, 0, 0)


def test_date_diff(clusterer: EventClusterer):
    """Разница между датами."""
    assert clusterer._date_diff_days("2026-09-11", "2026-09-11") == 0
    assert clusterer._date_diff_days("2026-09-11", "2026-09-14") == 3
    assert clusterer._date_diff_days("2026-09-11", "2026-09-20") == 9


def test_entity_overlap(clusterer: EventClusterer):
    """Пересечение ключевых сущностей."""
    a = {"entities": [{"text": "Банк России", "type": "организация"}, {"text": "ЦБ", "type": "организация"}]}
    b = {"entities": [{"text": "Банк России", "type": "организация"}, {"text": "ЦБ", "type": "организация"}]}
    assert clusterer._entity_overlap(a, b) == 1.0


def test_entity_overlap_no_key(clusterer: EventClusterer):
    """Без ключевых сущностей overlap = 0."""
    a = {"entities": [{"text": "инфляция", "type": "финансовый показатель"}]}
    b = {"entities": [{"text": "инфляция", "type": "финансовый показатель"}]}
    assert clusterer._entity_overlap(a, b) == 0.0


def test_should_merge(clusterer: EventClusterer):
    """Новости с общими организациями в одном окне — сливаются."""
    a = {
        "published_at": "2026-09-11",
        "entities": [{"text": "Банк России", "type": "организация"}, {"text": "ЦБ", "type": "организация"}],
    }
    b = {
        "published_at": "2026-09-11",
        "entities": [{"text": "Банк России", "type": "организация"}, {"text": "ЦБ", "type": "организация"}],
    }
    assert clusterer._should_merge(a, b) is True


def test_should_not_merge_different(clusterer: EventClusterer):
    """Новости без общих сущностей — не сливаются."""
    a = {
        "published_at": "2026-09-11",
        "entities": [{"text": "Банк России", "type": "организация"}],
    }
    b = {
        "published_at": "2026-09-11",
        "entities": [{"text": "Россия", "type": "место"}],
    }
    assert clusterer._should_merge(a, b) is False


def test_cluster(clusterer: EventClusterer, sample_news: Path):
    """Кластеризация группирует новости об одном событии."""
    data = json.loads(sample_news.read_text(encoding="utf-8"))
    clusters = clusterer.cluster(data["news"])
    assert len(clusters) == 2
    # n1 и n2 в одном кластере
    evt1 = next(c for c in clusters if "n1" in c.news_ids)
    assert "n2" in evt1.news_ids
    # n3 отдельно
    evt2 = next(c for c in clusters if "n3" in c.news_ids)
    assert "n1" not in evt2.news_ids


def test_cluster_entities(clusterer: EventClusterer, sample_news: Path):
    """Кластер содержит общие сущности."""
    data = json.loads(sample_news.read_text(encoding="utf-8"))
    clusters = clusterer.cluster(data["news"])
    evt1 = next(c for c in clusters if "n1" in c.news_ids)
    assert "организация" in evt1.entities
    assert "Банк России" in evt1.entities["организация"]


def test_save_json(clusterer: EventClusterer, tmp_path: Path):
    """Проверяет сохранение в JSON."""
    clusters = [EventCluster(event_id="evt_1", title="x", news_ids=["n1"])]
    json_path = tmp_path / "events.json"
    clusterer.save_json(clusters, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "event_clusterer"
    assert data["count"] == 1


def test_cluster_events_function(sample_news: Path, tmp_path: Path):
    """Проверяет функцию cluster_events."""
    out_path = tmp_path / "events.json"
    clusters = cluster_events(sample_news, out_path)
    assert len(clusters) == 2
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["count"] == 2