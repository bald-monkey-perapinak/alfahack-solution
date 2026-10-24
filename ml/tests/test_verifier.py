"""Тесты для модуля верификатора (verifier.verifier)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from verifier.verifier import (  # noqa: E402
    InsightVerifier,
    VerificationResult,
    verify_insights,
    INVESTMENT_PATTERNS,
)


@pytest.fixture
def verifier() -> InsightVerifier:
    return InsightVerifier()


@pytest.fixture
def valid_insight() -> dict:
    """Валидный инсайт."""
    return {
        "insight_id": "ins_1",
        "event_id": "evt_1",
        "company_id": "U_1",
        "user_id": "u1",
        "headline": "Ставка сохранена: риск для компании",
        "channels": {
            "fact": [{"text": "ЦБ сохранил ставку", "source_id": "evt_1"}],
            "bank_analytics": [],
            "ai_conclusion": [{"text": "Вклад через key_rate", "refs": ["key_rate"]}],
        },
        "actions": [{"type": "fix_rate", "label": "продукт банка"}],
        "confidence": 0.9,
        "versions": {"graph": "v1", "weights": "v1", "prompts": "v1", "models": "stub"},
        "trace_id": "trc_1",
    }


def test_verify_valid(verifier: InsightVerifier, valid_insight: dict):
    """Валидный инсайт проходит все проверки."""
    result = verifier.verify(valid_insight)
    assert result.status == "passed"
    assert all(result.checks.values())


def test_verify_missing_field(verifier: InsightVerifier, valid_insight: dict):
    """Отсутствие обязательного поля -> failed."""
    insight = dict(valid_insight)
    del insight["headline"]
    result = verifier.verify(insight)
    assert result.status == "failed"
    assert result.checks["required_fields"] is False


def test_verify_fact_without_source(verifier: InsightVerifier, valid_insight: dict):
    """Факт без source_id -> failed."""
    insight = dict(valid_insight)
    insight["channels"] = {
        "fact": [{"text": "ЦБ сохранил ставку"}],  # нет source_id
        "bank_analytics": [],
        "ai_conclusion": [{"text": "x", "refs": ["key_rate"]}],
    }
    result = verifier.verify(insight)
    assert result.status == "failed"
    assert result.checks["channels"] is False


def test_verify_ai_without_refs(verifier: InsightVerifier, valid_insight: dict):
    """AI-вывод без refs -> failed."""
    insight = dict(valid_insight)
    insight["channels"] = {
        "fact": [{"text": "ЦБ сохранил ставку", "source_id": "evt_1"}],
        "bank_analytics": [],
        "ai_conclusion": [{"text": "x"}],  # нет refs
    }
    result = verifier.verify(insight)
    assert result.status == "failed"
    assert result.checks["channels"] is False


def test_verify_quote_not_in_source(valid_insight: dict):
    """Цитата не в источнике -> warning (некритичная проверка)."""
    verifier = InsightVerifier(source_text="Совсем другой текст")
    result = verifier.verify(valid_insight)
    assert result.status == "warning"
    assert result.checks["quotes"] is False


def test_verify_quote_in_source(valid_insight: dict):
    """Цитата в источнике -> passed."""
    verifier = InsightVerifier(source_text="ЦБ сохранил ставку на уровне 14%")
    result = verifier.verify(valid_insight)
    assert result.checks["quotes"] is True


def test_verify_investment(verifier: InsightVerifier, valid_insight: dict):
    """Инвестиционная рекомендация -> failed."""
    insight = dict(valid_insight)
    insight["headline"] = "Рекомендуем купить акции компании"
    result = verifier.verify(insight)
    assert result.status == "failed"
    assert result.checks["investment"] is False


def test_verify_confidence_range(verifier: InsightVerifier, valid_insight: dict):
    """confidence вне диапазона -> warning (некритичная проверка)."""
    insight = dict(valid_insight)
    insight["confidence"] = 1.5
    result = verifier.verify(insight)
    assert result.status == "warning"
    assert result.checks["numbers"] is False


def test_verify_action_label(verifier: InsightVerifier, valid_insight: dict):
    """Действие без корректной маркировки -> warning (некритичная проверка)."""
    insight = dict(valid_insight)
    insight["actions"] = [{"type": "fix_rate", "label": "непонятно"}]
    result = verifier.verify(insight)
    assert result.status == "warning"
    assert result.checks["actions"] is False


def test_verify_all(verifier: InsightVerifier, valid_insight: dict):
    """Проверяет verify_all."""
    results = verifier.verify_all([valid_insight, dict(valid_insight)])
    assert len(results) == 2
    assert all(r.status == "passed" for r in results)


def test_save_json(verifier: InsightVerifier, valid_insight: dict, tmp_path: Path):
    """Проверяет сохранение результатов в JSON."""
    result = verifier.verify(valid_insight)
    json_path = tmp_path / "verification.json"
    verifier.save_json([result], json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "verifier"
    assert data["passed"] == 1
    assert data["failed"] == 0


def test_verify_insights_function(tmp_path: Path):
    """Проверяет функцию verify_insights."""
    insights = {
        "module": "insight_generator",
        "count": 1,
        "insights": [{
            "insight_id": "ins_1",
            "event_id": "evt_1",
            "company_id": "U_1",
            "user_id": "u1",
            "headline": "Ставка сохранена: риск для компании",
            "channels": {
                "fact": [{"text": "x", "source_id": "evt_1"}],
                "bank_analytics": [],
                "ai_conclusion": [{"text": "x", "refs": ["key_rate"]}],
            },
            "actions": [{"type": "monitor", "label": "рекомендация AI"}],
            "confidence": 0.9,
            "versions": {"graph": "v1"},
            "trace_id": "trc_1",
        }],
    }
    insights_json = tmp_path / "insights.json"
    insights_json.write_text(json.dumps(insights, ensure_ascii=False), encoding="utf-8")
    out_path = tmp_path / "verification.json"
    results = verify_insights(insights_json, out_path)
    assert len(results) == 1
    assert results[0].status == "passed"
    assert out_path.exists()


def test_investment_patterns_nonempty():
    """Должны быть инвестиционные паттерны."""
    assert len(INVESTMENT_PATTERNS) > 0