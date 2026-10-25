"""Тесты для модуля аналитика (insight_generator.analyst)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from insight_generator.analyst import (  # noqa: E402
    InsightGenerator,
    Insight,
    StubLLMClient,
    generate_insights,
)


@pytest.fixture
def generator() -> InsightGenerator:
    return InsightGenerator()


@pytest.fixture
def sample_ranked(tmp_path: Path) -> Path:
    """Создаёт JSON с ранжированными событиями (как из модуля 4)."""
    ranked = {
        "module": "event_ranking",
        "version": "1.0",
        "count": 2,
        "ranked_events": [
            {
                "event_id": "evt_1",
                "company_id": "U_1",
                "score": 0.67,
                "components": {"relevance": 0.85, "materiality": 0.58, "urgency": 0.4, "role_fit": 0.78},
                "impact": 5.83,
                "explanation": ["Высокая релевантность"],
                "factor_impacts": {"key_rate": 3.0, "lending": 2.0},
                "top_paths": [
                    {"path": ["key_rate"], "impact": 3.0, "sign": 1.0, "depth": 1},
                    {"path": ["key_rate", "lending"], "impact": -1.2, "sign": -1.0, "depth": 2},
                ],
            },
            {
                "event_id": "evt_1",
                "company_id": "U_2",
                "score": 0.5,
                "components": {"relevance": 0.6, "materiality": 0.3, "urgency": 0.4, "role_fit": 0.5},
                "impact": 1.0,
                "explanation": ["Умеренное воздействие"],
                "factor_impacts": {"consumption": 1.0},
                "top_paths": [
                    {"path": ["consumption"], "impact": 1.0, "sign": 1.0, "depth": 1},
                ],
            },
        ],
    }
    path = tmp_path / "ranked.json"
    path.write_text(json.dumps(ranked, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def sample_profiles(tmp_path: Path) -> Path:
    """Создаёт JSON с профилями компаний."""
    profiles = {
        "module": "company_profile",
        "version": "1.0",
        "count": 2,
        "profiles": [
            {
                "company_id": "U_1",
                "observed": {
                    "products": {"CL_PRODUCT_LOA_MARK": 1, "CL_PRODUCT_LEA_MARK": 1},
                },
                "inferred": {"has_fts": True},
                "confidence": 1.0,
            },
            {
                "company_id": "U_2",
                "observed": {
                    "products": {"CL_PRODUCT_LOA_MARK": 0, "CL_PRODUCT_LEA_MARK": 0},
                },
                "inferred": {"has_fts": False},
                "confidence": 0.9,
            },
        ],
    }
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    return path


def test_stub_llm_client():
    """Заглушка LLM не вызывает реальный API."""
    client = StubLLMClient()
    assert client.generate("test") == "STUB_RESPONSE"


def test_generate_insight_basic(generator: InsightGenerator):
    """Проверяет базовую генерацию инсайта."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "title": "ЦБ сохранил ставку",
        "event_type": "central_bank_rate_decision",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [{"path": ["key_rate"], "impact": 3.0}],
    }
    profile = {
        "company_id": "U_1",
        "observed": {"products": {"CL_PRODUCT_LOA_MARK": 1}},
        "inferred": {"has_fts": True},
        "confidence": 1.0,
    }
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, event["top_paths"])
    assert isinstance(insight, Insight)
    assert insight.event_id == "evt_1"
    assert insight.company_id == "U_1"
    assert insight.user_id == "u1"
    assert insight.headline != ""
    assert "fact" in insight.channels
    assert "ai_conclusion" in insight.channels
    assert "bank_analytics" in insight.channels


def test_generate_insight_channels(generator: InsightGenerator):
    """Проверяет три канала."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "title": "ЦБ сохранил ставку",
        "event_type": "central_bank_rate_decision",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [{"path": ["key_rate"], "impact": 3.0}],
    }
    profile = {"company_id": "U_1", "observed": {}, "inferred": {}, "confidence": 1.0}
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, event["top_paths"])
    # Факт из события
    assert len(insight.channels["fact"]) == 1
    assert insight.channels["fact"][0]["text"] == "ЦБ сохранил ставку"
    # AI-вывод из путей
    assert len(insight.channels["ai_conclusion"]) == 1
    # Аналитика банка пока пуста
    assert len(insight.channels["bank_analytics"]) == 0


def test_generate_insight_actions_loan(generator: InsightGenerator):
    """Компания с кредитом должна получить действие fix_rate при росте ставки."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [],
    }
    profile = {
        "company_id": "U_1",
        "observed": {"products": {"CL_PRODUCT_LOA_MARK": 1, "CL_PRODUCT_LEA_MARK": 0}},
        "inferred": {"has_fts": False},
        "confidence": 1.0,
    }
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [])
    action_types = [a["type"] for a in insight.actions]
    assert "fix_rate" in action_types


def test_generate_insight_actions_currency(generator: InsightGenerator):
    """Компания с ВЭД должна получить валютное действие при валютном шоке."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 2.0,
        "factor_impacts": {"currency": 2.0},
        "top_paths": [],
    }
    profile = {
        "company_id": "U_1",
        "observed": {"products": {"CL_PRODUCT_LOA_MARK": 0}},
        "inferred": {"has_fts": True},
        "confidence": 1.0,
    }
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [])
    action_types = [a["type"] for a in insight.actions]
    assert "currency_hedge" in action_types


def test_generate_insight_no_actions(generator: InsightGenerator):
    """Без релевантных признаков должно быть действие monitor."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 0.5,
        "factor_impacts": {"gdp": 0.5},
        "top_paths": [],
    }
    profile = {
        "company_id": "U_1",
        "observed": {"products": {}},
        "inferred": {"has_fts": False},
        "confidence": 1.0,
    }
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [])
    action_types = [a["type"] for a in insight.actions]
    assert "monitor" in action_types


def test_generate_insight_why_it_matters(generator: InsightGenerator):
    """why_it_matters должен содержать затронутые факторы."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0, "lending": 2.0},
        "top_paths": [],
    }
    profile = {"company_id": "U_1", "observed": {}, "inferred": {}, "confidence": 1.0}
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [])
    factors = [w["factor"] for w in insight.why_it_matters]
    assert "key_rate" in factors
    assert "lending" in factors


def test_generate_for_ranked(generator: InsightGenerator, sample_ranked: Path, sample_profiles: Path):
    """Проверяет генерацию для ранжированных событий."""
    ranked_data = json.loads(sample_ranked.read_text(encoding="utf-8"))
    profiles_data = json.loads(sample_profiles.read_text(encoding="utf-8"))
    user = {"user_id": "u1", "role": "cfo"}
    source_event = {"title": "ЦБ сохранил ставку", "event_type": "central_bank_rate_decision"}
    insights = generator.generate_for_ranked(
        ranked_data["ranked_events"], profiles_data["profiles"], user, source_event
    )
    assert len(insights) == 2
    # U_1 должна иметь заголовок с event_type
    insight_u1 = next(i for i in insights if i.company_id == "U_1")
    assert "central_bank_rate_decision" in insight_u1.headline


def test_save_json(generator: InsightGenerator, tmp_path: Path):
    """Проверяет сохранение инсайтов в JSON."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [],
    }
    profile = {"company_id": "U_1", "observed": {}, "inferred": {}, "confidence": 1.0}
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [])
    json_path = tmp_path / "insights.json"
    generator.save_json([insight], json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "insight_generator"
    assert data["count"] == 1
    assert data["insights"][0]["company_id"] == "U_1"


def test_generate_insights_function(sample_ranked: Path, sample_profiles: Path, tmp_path: Path):
    """Проверяет функцию generate_insights."""
    user = {"user_id": "u1", "role": "cfo"}
    source_event = {"title": "ЦБ сохранил ставку", "event_type": "central_bank_rate_decision"}
    out_path = tmp_path / "insights.json"
    insights = generate_insights(sample_ranked, sample_profiles, user, out_path, source_event)
    assert len(insights) == 2
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["count"] == 2


def test_insight_has_versions_and_trace(generator: InsightGenerator):
    """Инсайт должен содержать версии и trace_id (для трассируемости)."""
    event = {
        "event_id": "evt_1",
        "company_id": "U_1",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [],
    }
    profile = {"company_id": "U_1", "observed": {}, "inferred": {}, "confidence": 1.0}
    user = {"user_id": "u1", "role": "cfo"}
    insight = generator.generate_insight(event, profile, user, [], trace_id="trc_123")
    assert insight.trace_id == "trc_123"
    assert "graph" in insight.versions
    assert "weights" in insight.versions
    assert "prompts" in insight.versions
    assert "models" in insight.versions


# --- Тесты LLM-генерации и fallback ---


class MockLLMClient:
    """Имитирует реальный LLMClient (generate_json)."""

    def __init__(self, response: dict | None = None, model: str = "mock-model"):
        self.response = response
        self.model = model
        self.calls = 0

    def generate_json(self, prompt: str, **kwargs):
        self.calls += 1
        return self.response


def _llm_event() -> dict:
    return {
        "event_id": "evt_1",
        "company_id": "U_1",
        "title": "ЦБ сохранил ставку",
        "event_type": "central_bank_rate_decision",
        "impact": 5.83,
        "factor_impacts": {"key_rate": 3.0},
        "top_paths": [{"path": ["key_rate"], "impact": 3.0}],
    }


def _llm_profile() -> dict:
    return {
        "company_id": "U_1",
        "observed": {"products": {"CL_PRODUCT_LOA_MARK": 1}},
        "inferred": {"has_fts": True},
        "confidence": 1.0,
    }


def test_llm_generates_insight():
    """Реальный LLM-клиент генерирует инсайт через generate_json."""
    llm_response = {
        "headline": "Рост ставки — риск для кредитного портфеля",
        "channels": {
            "fact": [{"text": "ЦБ сохранил ставку", "source_id": "evt_1"}],
            "bank_analytics": [{"text": "Ставка остаётся высокой"}],
            "ai_conclusion": [{"text": "Кредиты дорожают", "refs": ["key_rate"]}],
        },
        "why_it_matters": [{"factor": "key_rate", "impact": 3.0, "origin": "observed"}],
        "actions": [{"type": "fix_rate", "label": "продукт банка", "rationale": "Зафиксировать ставку", "product_id": "CL_PRODUCT_LOA_MARK", "priority": 1}],
        "cost_of_inaction": {"description": "Потери при бездействии", "severity": "high", "timeframe": "quarter"},
        "confidence": 0.95,
    }
    mock = MockLLMClient(response=llm_response)
    gen = InsightGenerator(llm_client=mock)
    insight = gen.generate_insight(_llm_event(), _llm_profile(), {"user_id": "u1", "role": "cfo"}, _llm_event()["top_paths"])
    assert mock.calls == 1  # LLM вызван
    assert insight.headline == "Рост ставки — риск для кредитного портфеля"
    assert insight.channels["bank_analytics"]  # канал заполнен из LLM
    assert insight.versions["models"] == "mock-model"
    assert insight.confidence == 0.95


def test_llm_fallback_on_none():
    """При None от LLM — fallback на детерминированную логику."""
    mock = MockLLMClient(response=None)
    gen = InsightGenerator(llm_client=mock)
    insight = gen.generate_insight(_llm_event(), _llm_profile(), {"user_id": "u1", "role": "cfo"}, _llm_event()["top_paths"])
    assert mock.calls == 1  # LLM вызван, но вернул None
    assert insight.headline != ""  # fallback-заголовок
    assert insight.versions["models"] == "stub"  # fallback-версия


def test_llm_fallback_on_exception():
    """При исключении в LLM — fallback на детерминированную логику."""

    class RaisingClient:
        def generate_json(self, prompt, **kwargs):
            raise RuntimeError("LLM недоступен")

    gen = InsightGenerator(llm_client=RaisingClient())
    insight = gen.generate_insight(_llm_event(), _llm_profile(), {"user_id": "u1", "role": "cfo"}, _llm_event()["top_paths"])
    assert insight.headline != ""
    assert insight.versions["models"] == "stub"


def test_stub_client_uses_deterministic():
    """Заглушка (StubLLMClient) не вызывает generate_json — детерминированная логика."""
    gen = InsightGenerator()  # по умолчанию StubLLMClient
    insight = gen.generate_insight(_llm_event(), _llm_profile(), {"user_id": "u1", "role": "cfo"}, _llm_event()["top_paths"])
    assert insight.versions["models"] == "stub"
    assert insight.headline != ""


def test_llm_fills_missing_fields():
    """LLM вернул частичный JSON — недостающие поля заполняются детерминированно."""
    llm_response = {"headline": "Только заголовок"}  # нет channels/actions/why
    mock = MockLLMClient(response=llm_response)
    gen = InsightGenerator(llm_client=mock)
    insight = gen.generate_insight(_llm_event(), _llm_profile(), {"user_id": "u1", "role": "cfo"}, _llm_event()["top_paths"])
    assert insight.headline == "Только заголовок"
    # Каналы заполнены из события/путей
    assert len(insight.channels["fact"]) == 1
    assert len(insight.channels["ai_conclusion"]) == 1
    # Действия из детерминированной логики (есть кредит + ставка)
    action_types = [a["type"] for a in insight.actions]
    assert "fix_rate" in action_types