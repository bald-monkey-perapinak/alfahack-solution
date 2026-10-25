"""Тесты для модуля приёма новостей (news_ingestor.ingestor)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from news_ingestor.ingestor import (  # noqa: E402
    NewsIngestor,
    NewsArticle,
    ingest_news,
)


@pytest.fixture
def ingestor() -> NewsIngestor:
    return NewsIngestor()


@pytest.fixture
def sample_raw(tmp_path: Path) -> Path:
    """Создаёт JSON с сырыми новостями (включая дубликат)."""
    raw = [
        {
            "news_id": "n1",
            "title": "ЦБ сохранил ставку на уровне 14%",
            "text": "Банк России сохранил ключевую ставку на уровне 14% годовых.",
            "source": "rbc",
            "published_at": "2026-09-11",
        },
        {
            "news_id": "n2",
            "title": "ЦБ сохранил ставку на уровне 14%",
            "text": "Банк России сохранил ключевую ставку на уровне 14% годовых.",
            "source": "interfax",
            "published_at": "2026-09-11",
        },
        {
            "news_id": "n3",
            "title": "Инфляция замедлилась",
            "text": "Инфляция в России замедлилась до 8%.",
            "source": "kommersant",
            "published_at": "2026-09-12",
        },
    ]
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def test_normalize_text(ingestor: NewsIngestor):
    """Нормализация убирает лишние пробелы."""
    text = "  Банк   России   сохранил  ставку  "
    assert ingestor._normalize_text(text) == "Банк России сохранил ставку"


def test_extract_text(ingestor: NewsIngestor):
    """Извлечение текста из разных полей."""
    assert ingestor._extract_text({"text": "текст"}) == "текст"
    assert ingestor._extract_text({"content": "контент"}) == "контент"
    assert ingestor._extract_text({"body": "тело"}) == "тело"
    assert ingestor._extract_text({}) == ""


def test_shingles(ingestor: NewsIngestor):
    """Шинглы строятся из токенов."""
    shingles = ingestor._shingles("Банк России сохранил ключевую ставку на уровне четырнадцать процентов")
    assert len(shingles) > 0


def test_jaccard(ingestor: NewsIngestor):
    """Коэффициент Жаккара."""
    assert ingestor._jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert ingestor._jaccard({"a"}, {"b"}) == 0.0
    assert ingestor._jaccard({"a", "b"}, {"a"}) == 0.5


def test_is_duplicate(ingestor: NewsIngestor):
    """Идентичные новости — дубликаты."""
    a = NewsArticle(news_id="a", title="Заголовок", text="Текст новости", source="s1", published_at="")
    b = NewsArticle(news_id="b", title="Заголовок", text="Текст новости", source="s2", published_at="")
    assert ingestor._is_duplicate(a, b) is True


def test_is_not_duplicate(ingestor: NewsIngestor):
    """Разные новости — не дубликаты."""
    a = NewsArticle(news_id="a", title="Про ставку", text="Банк России сохранил ставку", source="s1", published_at="")
    b = NewsArticle(news_id="b", title="Про инфляцию", text="Инфляция замедлилась до 8 процентов", source="s2", published_at="")
    assert ingestor._is_duplicate(a, b) is False


def test_ingest_deduplicates(ingestor: NewsIngestor, sample_raw: Path):
    """Приём новостей дедуплицирует."""
    raw = json.loads(sample_raw.read_text(encoding="utf-8"))
    articles = ingestor.ingest(raw)
    assert len(articles) == 3
    # n2 — дубликат n1
    n2 = next(a for a in articles if a.news_id == "n2")
    assert n2.is_duplicate is True
    assert n2.duplicate_of == "n1"
    # n3 — уникальна
    n3 = next(a for a in articles if a.news_id == "n3")
    assert n3.is_duplicate is False


def test_ingest_skips_empty(ingestor: NewsIngestor):
    """Новости без текста пропускаются."""
    raw = [{"news_id": "n1", "title": "x"}, {"news_id": "n2", "text": "текст"}]
    articles = ingestor.ingest(raw)
    assert len(articles) == 1
    assert articles[0].news_id == "n2"


def test_save_json(ingestor: NewsIngestor, tmp_path: Path):
    """Проверяет сохранение в JSON."""
    articles = [NewsArticle(news_id="n1", title="x", text="y", source="s", published_at="")]
    json_path = tmp_path / "news.json"
    ingestor.save_json(articles, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "news_ingestor"
    assert data["count"] == 1
    assert data["unique"] == 1


def test_ingest_news_function(sample_raw: Path, tmp_path: Path):
    """Проверяет функцию ingest_news."""
    out_path = tmp_path / "news.json"
    articles = ingest_news(sample_raw, out_path)
    assert len(articles) == 3
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["count"] == 3
    assert data["duplicates"] == 1