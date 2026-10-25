"""Тесты для модуля NER (ner.ner)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from ner.ner import (  # noqa: E402
    NERExtractor,
    Entity,
    ENTITY_TYPES,
    extract_entities,
)


@pytest.fixture
def extractor() -> NERExtractor:
    return NERExtractor()


def test_entity_types_nonempty():
    """Должны быть типы сущностей."""
    assert len(ENTITY_TYPES) > 0


def test_fallback_extract_organization(extractor: NERExtractor):
    """Fallback извлекает организацию."""
    entities = extractor._fallback_extract("Банк России сохранил ставку")
    orgs = [e for e in entities if e.type == "организация"]
    assert any("Банк России" in e.text for e in orgs)


def test_fallback_extract_person(extractor: NERExtractor):
    """Fallback извлекает персону."""
    entities = extractor._fallback_extract("Эльвира Набиуллина заявила")
    persons = [e for e in entities if e.type == "персона"]
    assert len(persons) > 0


def test_fallback_extract_place(extractor: NERExtractor):
    """Fallback извлекает место."""
    entities = extractor._fallback_extract("Китай и Турция — партнёры")
    places = [e for e in entities if e.type == "место"]
    assert any(e.text == "Китай" for e in places)
    assert any(e.text == "Турция" for e in places)


def test_fallback_extract_indicator(extractor: NERExtractor):
    """Fallback извлекает финансовый показатель."""
    entities = extractor._fallback_extract("Инфляция остаётся высокой")
    indicators = [e for e in entities if e.type == "финансовый показатель"]
    assert any("инфляция" in e.text.lower() for e in indicators)


def test_extract_returns_entities(extractor: NERExtractor):
    """extract возвращает список Entity."""
    entities = extractor.extract("Банк России сохранил ставку")
    assert isinstance(entities, list)
    for e in entities:
        assert isinstance(e, Entity)
        assert e.text != ""
        assert e.type != ""


def test_extract_from_json(extractor: NERExtractor):
    """extract_from_json возвращает структуру с entities."""
    news = {"news_id": "n1", "text": "ЦБ сохранил ставку, Китай — партнёр"}
    result = extractor.extract_from_json(news)
    assert result["news_id"] == "n1"
    assert len(result["entities"]) > 0


def test_save_json(extractor: NERExtractor, tmp_path: Path):
    """Проверяет сохранение в JSON."""
    result = {"news_id": "n1", "text": "x", "entities": []}
    json_path = tmp_path / "ner.json"
    extractor.save_json(result, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["news_id"] == "n1"


def test_extract_entities_function(tmp_path: Path):
    """Проверяет функцию extract_entities."""
    news = {"news_id": "n1", "text": "Банк России сохранил ставку"}
    news_json = tmp_path / "news.json"
    news_json.write_text(json.dumps(news, ensure_ascii=False), encoding="utf-8")
    out_path = tmp_path / "ner.json"
    result = extract_entities(news_json, out_path)
    assert result["news_id"] == "n1"
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["entities"]) > 0