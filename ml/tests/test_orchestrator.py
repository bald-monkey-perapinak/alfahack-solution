"""Тесты для модуля оркестратора (orchestrator.orchestrator)."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from orchestrator.orchestrator import (  # noqa: E402
    PipelineOrchestrator,
    PipelineState,
    run_pipeline,
)


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Создаёт синтетический CSV компаний."""
    data = {
        "SYNTHETIC_U": ["U_1", "U_2"],
        "ORG_TYPE": ["КОММ_ОРГ"] * 2,
        "OKFS_NAME": ["ЧАСТНАЯ СОБСТВЕННОСТЬ"] * 2,
        "COMPANY_AGE_YEARS_GRADATION": ["16-25"] * 2,
        "ECO_MARK_LABEL": ["Оптимизация", "Рождение"],
        "MAINOKVED_CODE": ["46.51", "41.20"],
        "MAINOKVED_NAME": ["Торговля оптовая", "Строительство"],
        "NEGATIVEMARK": [0.0, 0.0],
        "AMOUNT_WORKERS_FNS_GRADATION": ["Менее 15"] * 2,
        "AMOUNT_WORKERS_SPARK_GRADATION": [None] * 2,
        "CL_TYPE": ["PROSPECT"] * 2,
        "CL_PRODUCT_RKO_MARK": [1, 0],
        "CL_PRODUCT_GAR_MARK": [0, 0],
        "CL_PRODUCT_LOA_MARK": [1, 0],
        "CL_PRODUCT_LEA_MARK": [0, 1],
        "CL_PRODUCT_DEP_MARK": [0, 0],
        "CL_PRODUCT_ZPP_MARK": [0, 0],
        "FTS_FLAG": [1, 0],
        "FTS_COUNTRY_NAME": ["КИТАЙ", None],
        "FACTORING_MARK": [0, 0],
        "REVENUE_COMPANY": [20_000_000_000.0, 5_000_000.0],
        "GROUP_ID": ["group_1", "group_2"],
        "CITY": ["Москва", "Москва"],
        "REGION": ["Москва", "Москва"],
    }
    df = pd.DataFrame(data)
    csv_path = tmp_path / "companies.csv"
    df.to_csv(csv_path, sep=";", index=False, encoding="utf-8")
    return csv_path


@pytest.fixture
def sample_event() -> dict:
    return {
        "event_id": "evt_rate",
        "event_type": "central_bank_rate_decision",
        "title": "ЦБ сохранил ключевую ставку на уровне 14%",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }


@pytest.fixture
def sample_user() -> dict:
    return {"user_id": "u1", "role": "cfo"}


def test_orchestrator_builds_graph(sample_csv: Path):
    """Оркестратор строит граф LangGraph."""
    orch = PipelineOrchestrator(sample_csv)
    assert orch.graph is not None


def test_orchestrator_run(sample_csv: Path, sample_event: dict, sample_user: dict):
    """Полный прогон пайплайна."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    assert isinstance(state, PipelineState)
    assert len(state.profiles) == 2
    assert len(state.impacts) == 2
    assert len(state.ranked) == 2
    assert len(state.insights) == 2
    assert len(state.verification) == 2


def test_orchestrator_trace(sample_csv: Path, sample_event: dict, sample_user: dict):
    """Трассировка содержит все шаги."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    steps = [t["step"] for t in state.trace]
    assert steps == ["build_profiles", "propagate", "rank", "generate_insights", "verify"]


def test_orchestrator_verification_passed(sample_csv: Path, sample_event: dict, sample_user: dict):
    """Все инсайты проходят верификацию."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    for v in state.verification:
        assert v["status"] == "passed"


def test_orchestrator_save_json(sample_csv: Path, sample_event: dict, sample_user: dict, tmp_path: Path):
    """Сохранение результата в JSON."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    json_path = tmp_path / "pipeline.json"
    orch.save_json(state, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["profiles"]) == 2
    assert len(data["insights"]) == 2
    assert len(data["trace"]) == 5


def test_run_pipeline_function(sample_csv: Path, sample_event: dict, sample_user: dict, tmp_path: Path):
    """Проверяет функцию run_pipeline."""
    out_path = tmp_path / "pipeline.json"
    state = run_pipeline(sample_csv, sample_event, sample_user, out_path)
    assert isinstance(state, PipelineState)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["insights"]) == 2


def test_orchestrator_insights_have_actions(sample_csv: Path, sample_event: dict, sample_user: dict):
    """Инсайты содержат действия."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    for insight in state.insights:
        assert len(insight["actions"]) > 0


def test_orchestrator_insights_have_channels(sample_csv: Path, sample_event: dict, sample_user: dict):
    """Инсайты содержат три канала."""
    orch = PipelineOrchestrator(sample_csv)
    state = orch.run(sample_event, sample_user)
    for insight in state.insights:
        assert "fact" in insight["channels"]
        assert "bank_analytics" in insight["channels"]
        assert "ai_conclusion" in insight["channels"]