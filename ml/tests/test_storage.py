"""Тесты для адаптеров хранилищ (storage.graph_store, storage.vector_store)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from storage.graph_store import GraphStore  # noqa: E402
from storage.vector_store import VectorStore  # noqa: E402


@pytest.fixture
def graph_store(tmp_path: Path) -> GraphStore:
    return GraphStore(json_path=tmp_path / "graph.json")


@pytest.fixture
def vector_store(tmp_path: Path) -> VectorStore:
    return VectorStore(json_path=tmp_path / "vectors.json")


def test_graph_store_neo4j_unavailable(graph_store: GraphStore):
    """Neo4j недоступен (нет сервера) — fallback на JSON."""
    assert graph_store._check_neo4j() is False


def test_graph_store_save_factor_graph(graph_store: GraphStore):
    """Сохранение графа факторов в JSON."""
    factor_graph = {
        "key_rate": {"lending": {"sign": -1.0, "strength": 0.8}},
        "inflation": {"consumption": {"sign": -1.0, "strength": 0.6}},
    }
    ok = graph_store.save_factor_graph(factor_graph)
    assert ok is True
    # Проверяем, что JSON записан
    assert graph_store.json_path.exists()
    data = json.loads(graph_store.json_path.read_text(encoding="utf-8"))
    assert "factor_graph" in data
    assert "key_rate" in data["factor_graph"]


def test_graph_store_get_factor_graph(graph_store: GraphStore):
    """Чтение графа факторов из JSON."""
    factor_graph = {
        "key_rate": {"lending": {"sign": -1.0, "strength": 0.8}},
    }
    graph_store.save_factor_graph(factor_graph)
    loaded = graph_store.get_factor_graph()
    assert "key_rate" in loaded
    assert "lending" in loaded["key_rate"]


def test_graph_store_save_company(graph_store: GraphStore):
    """Сохранение компании в JSON."""
    company = {"company_id": "U_1", "observed": {"revenue": 1000000, "region": "Москва"}}
    ok = graph_store.save_company(company)
    assert ok is True
    data = json.loads(graph_store.json_path.read_text(encoding="utf-8"))
    assert "company" in data


def test_graph_store_save_event(graph_store: GraphStore):
    """Сохранение события в JSON."""
    event = {"event_id": "evt_1", "event_type": "rate_decision", "title": "Ставка"}
    ok = graph_store.save_event(event)
    assert ok is True
    data = json.loads(graph_store.json_path.read_text(encoding="utf-8"))
    assert "event" in data


def test_graph_store_no_json_path():
    """Без json_path сохранение возвращает False."""
    store = GraphStore()  # нет json_path
    assert store.save_factor_graph({"a": {}}) is False


def test_vector_store_qdrant_unavailable(vector_store: VectorStore):
    """Qdrant недоступен (нет сервера) — fallback на JSON."""
    assert vector_store._check_qdrant() is False


def test_vector_store_upsert(vector_store: VectorStore):
    """Сохранение точек в JSON."""
    points = [
        {"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"text": "новость 1"}},
        {"id": 2, "vector": [0.0, 1.0, 0.0], "payload": {"text": "новость 2"}},
    ]
    ok = vector_store.upsert(points)
    assert ok is True
    assert vector_store.json_path.exists()
    data = json.loads(vector_store.json_path.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_vector_store_search(vector_store: VectorStore):
    """Поиск ближайших точек."""
    points = [
        {"id": 1, "vector": [1.0, 0.0, 0.0], "payload": {"text": "новость 1"}},
        {"id": 2, "vector": [0.0, 1.0, 0.0], "payload": {"text": "новость 2"}},
    ]
    vector_store.upsert(points)
    results = vector_store.search([1.0, 0.0, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == 1
    assert results[0]["score"] > 0.9


def test_vector_store_search_empty(vector_store: VectorStore):
    """Поиск в пустом хранилище."""
    results = vector_store.search([1.0, 0.0, 0.0], top_k=1)
    assert results == []


def test_vector_store_cosine(vector_store: VectorStore):
    """Косинусная близость."""
    assert vector_store._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert vector_store._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert vector_store._cosine([1.0, 0.0], [0.0, 0.0]) == 0.0