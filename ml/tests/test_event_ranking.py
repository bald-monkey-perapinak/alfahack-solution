"""Тесты для модуля ранжирования событий (event_ranking.ranker)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from event_ranking.ranker import (  # noqa: E402
    EventRanker,
    UserProfile,
    RankedEvent,
    rank_for_user,
    ROLE_FACTOR_WEIGHTS,
    WEIGHTS,
)


@pytest.fixture
def ranker() -> EventRanker:
    return EventRanker()


@pytest.fixture
def sample_impacts(tmp_path: Path) -> Path:
    """Создаёт JSON с воздействием (как из модуля 3)."""
    impacts = {
        "module": "shock_propagation",
        "version": "1.0",
        "count": 3,
        "impacts": [
            {
                "company_id": "U_1",
                "total_impact": 5.0,
                "factor_impacts": {"key_rate": 3.0, "lending": 2.0},
                "top_paths": [],
                "confidence": 1.0,
            },
            {
                "company_id": "U_2",
                "total_impact": 1.0,
                "factor_impacts": {"consumption": 1.0},
                "top_paths": [],
                "confidence": 0.9,
            },
            {
                "company_id": "U_3",
                "total_impact": 0.0,
                "factor_impacts": {},
                "top_paths": [],
                "confidence": 1.0,
            },
        ],
    }
    path = tmp_path / "impacts.json"
    path.write_text(json.dumps(impacts, ensure_ascii=False), encoding="utf-8")
    return path


def test_relevance(ranker: EventRanker):
    """Большее воздействие -> выше релевантность."""
    assert ranker._relevance(5.0) > ranker._relevance(1.0)
    assert ranker._relevance(0.0) == 0.0


def test_materiality(ranker: EventRanker):
    """Материальность растёт с воздействием, ограничена 1.0 (tanh)."""
    assert ranker._materiality(5.0) > ranker._materiality(1.0)
    assert ranker._materiality(0.0) == 0.0
    # tanh(5.0) ~ 0.9999, tanh(20.0) ~ 1.0 — оба близки к 1
    assert ranker._materiality(20.0) > 0.99


def test_urgency(ranker: EventRanker):
    """Срочность зависит от горизонта."""
    assert ranker._urgency("immediate") > ranker._urgency("quarter")
    assert ranker._urgency("quarter") == 0.4


def test_role_fit_cfo(ranker: EventRanker):
    """Для CFO факторы key_rate/lending важны."""
    factor_impacts = {"key_rate": 3.0, "lending": 2.0}
    fit = ranker._role_fit(factor_impacts, "cfo")
    assert fit > 0.5  # key_rate и lending имеют вес 1.0 для CFO


def test_role_fit_ceo(ranker: EventRanker):
    """Для CEO факторы gdp/consumption важны."""
    factor_impacts = {"gdp": 1.0, "consumption": 1.0}
    fit = ranker._role_fit(factor_impacts, "ceo")
    assert fit > 0.5


def test_score_event(ranker: EventRanker):
    """Проверяет скоринг одного события."""
    impact = {
        "company_id": "U_1",
        "total_impact": 5.0,
        "factor_impacts": {"key_rate": 3.0, "lending": 2.0},
    }
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.score_event(impact, user)
    assert isinstance(ranked, RankedEvent)
    assert ranked.score > 0
    assert "relevance" in ranked.components
    assert "materiality" in ranked.components
    assert "urgency" in ranked.components
    assert "role_fit" in ranked.components


def test_score_event_zero_impact(ranker: EventRanker):
    """Событие без воздействия должно иметь низкий скоринг."""
    impact = {
        "company_id": "U_3",
        "total_impact": 0.0,
        "factor_impacts": {},
    }
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.score_event(impact, user)
    assert ranked.score < 0.5


def test_rank_events_order(ranker: EventRanker, sample_impacts: Path):
    """Ранжирование сортирует по убыванию скоринга."""
    data = json.loads(sample_impacts.read_text(encoding="utf-8"))
    impacts = data["impacts"]
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.rank_events(impacts, user, top_n=3)
    assert len(ranked) == 3
    # Скоринги по убыванию
    scores = [r.score for r in ranked]
    assert scores == sorted(scores, reverse=True)
    # U_1 (большое воздействие) должна быть первой
    assert ranked[0].company_id == "U_1"


def test_rank_events_top_n(ranker: EventRanker, sample_impacts: Path):
    """top_n ограничивает число результатов."""
    data = json.loads(sample_impacts.read_text(encoding="utf-8"))
    impacts = data["impacts"]
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.rank_events(impacts, user, top_n=2)
    assert len(ranked) == 2


def test_rank_events_explanation(ranker: EventRanker, sample_impacts: Path):
    """Каждое событие имеет объяснение."""
    data = json.loads(sample_impacts.read_text(encoding="utf-8"))
    impacts = data["impacts"]
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.rank_events(impacts, user, top_n=3)
    for r in ranked:
        assert len(r.explanation) > 0


def test_save_json(ranker: EventRanker, tmp_path: Path):
    """Проверяет сохранение в JSON."""
    impact = {
        "company_id": "U_1",
        "total_impact": 5.0,
        "factor_impacts": {"key_rate": 3.0},
    }
    user = UserProfile(user_id="u1", role="cfo")
    ranked = ranker.score_event(impact, user)
    json_path = tmp_path / "ranked.json"
    ranker.save_json([ranked], json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "event_ranking"
    assert data["count"] == 1
    assert data["ranked_events"][0]["company_id"] == "U_1"


def test_rank_for_user_function(sample_impacts: Path, tmp_path: Path):
    """Проверяет функцию rank_for_user."""
    user = UserProfile(user_id="u1", role="cfo")
    out_path = tmp_path / "ranked.json"
    ranked = rank_for_user(sample_impacts, user, out_path, top_n=3)
    assert len(ranked) == 3
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["count"] == 3


def test_role_weights_exist():
    """Все роли имеют веса."""
    for role in ["cfo", "ceo", "treasurer", "chief_accountant", "owner", "default"]:
        assert role in ROLE_FACTOR_WEIGHTS


def test_weights_sum():
    """Сумма весов компонентов = 1.0."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 0.01