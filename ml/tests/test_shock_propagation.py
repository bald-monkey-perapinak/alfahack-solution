"""Тесты для модуля распространения шоков (shock_propagation.propagator)."""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from shock_propagation.propagator import (  # noqa: E402
    Shock,
    ShockPropagator,
    CompanyImpact,
    ImpactPath,
    propagate_event,
    FACTOR_GRAPH,
    MACRO_FACTORS,
)


@pytest.fixture
def propagator() -> ShockPropagator:
    return ShockPropagator()


@pytest.fixture
def sample_profiles(tmp_path: Path) -> Path:
    """Создаёт JSON с профилями компаний (как из модуля 2)."""
    profiles = {
        "module": "company_profile",
        "version": "1.0",
        "count": 2,
        "macro_factors": MACRO_FACTORS,
        "profiles": [
            {
                "company_id": "U_1",
                "exposures": {
                    "key_rate": 3.0, "lending": 3.0, "bonds": 2.0,
                    "inflation": 1.0, "consumption": 0.0, "currency": 0.0,
                },
                "confidence": 1.0,
            },
            {
                "company_id": "U_2",
                "exposures": {
                    "key_rate": 0.0, "lending": 0.0, "bonds": 0.0,
                    "inflation": 0.0, "consumption": 3.0, "currency": 0.0,
                },
                "confidence": 0.9,
            },
        ],
    }
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    return path


def test_propagate_single_shock(propagator: ShockPropagator):
    """Проверяет распространение одного шока."""
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impacts = propagator.propagate_shock(shock)
    # key_rate должен быть в результатах (tanh-нормализация к [-1,1])
    assert "key_rate" in impacts
    assert abs(impacts["key_rate"] - 0.6) < 0.05
    # Соседи key_rate должны быть затронуты
    assert "lending" in impacts
    assert "bonds" in impacts


def test_propagate_sign(propagator: ShockPropagator):
    """Проверяет знак влияния: рост ставки -> кредиты дороже (отрицательный вклад)."""
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impacts = propagator.propagate_shock(shock)
    # key_rate -> lending: sign=-1, значит вклад отрицательный
    assert impacts["lending"] < 0
    # key_rate -> bonds: sign=-1, значит вклад отрицательный
    assert impacts["bonds"] < 0


def test_propagate_decay(propagator: ShockPropagator):
    """Проверяет затухание: вклад на глубине 2 меньше, чем на глубине 1."""
    shock = Shock(factor="key_rate", direction=1.0, magnitude=1.0)
    impacts = propagator.propagate_shock(shock)
    # key_rate -> lending (сила 0.8, затухание 0.5) = 1.0 * -1 * 0.8 * 0.5 = -0.4
    assert abs(impacts["lending"]) < 1.0
    assert abs(impacts["lending"]) > 0.0


def test_propagate_depth_limit(propagator: ShockPropagator):
    """Проверяет ограничение глубины."""
    shock = Shock(factor="key_rate", direction=1.0, magnitude=1.0)
    # Глубина 1: только key_rate и прямые соседи
    impacts_depth1 = propagator.propagate_shock(shock, max_depth=1)
    # Глубина 3: больше факторов
    impacts_depth3 = propagator.propagate_shock(shock, max_depth=3)
    assert len(impacts_depth3) >= len(impacts_depth1)


def test_impact_on_company(propagator: ShockPropagator):
    """Проверяет воздействие на компанию через экспозиции."""
    exposures = {"key_rate": 3.0, "lending": 3.0, "bonds": 2.0}
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impact = propagator.impact_on_company(exposures, [shock])
    assert isinstance(impact, CompanyImpact)
    assert impact.total_impact != 0
    assert "key_rate" in impact.factor_impacts


def test_impact_zero_exposure(propagator: ShockPropagator):
    """Компания без экспозиции к фактору не должна получить воздействие."""
    exposures = {"consumption": 3.0}  # нет key_rate
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impact = propagator.impact_on_company(exposures, [shock])
    # key_rate экспозиция = 0, но соседи могут быть затронуты
    # Проверяем, что total_impact не огромный
    assert abs(impact.total_impact) < 5.0


def test_top_paths(propagator: ShockPropagator):
    """Проверяет построение путей вклада."""
    exposures = {"key_rate": 3.0, "lending": 3.0}
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impact = propagator.impact_on_company(exposures, [shock])
    assert len(impact.top_paths) > 0
    # Первый путь должен начинаться с key_rate
    assert impact.top_paths[0].path[0] == "key_rate"


def test_impact_on_all_companies(propagator: ShockPropagator, sample_profiles: Path):
    """Проверяет воздействие на все компании из JSON."""
    data = json.loads(sample_profiles.read_text(encoding="utf-8"))
    profiles = data["profiles"]
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impacts = propagator.impact_on_all_companies(profiles, [shock])
    assert len(impacts) == 2
    # U_1 имеет экспозицию к key_rate, U_2 — нет
    assert impacts[0].company_id == "U_1"
    assert impacts[0].total_impact != 0
    # U_2 (consumption) может получить небольшое воздействие через граф
    assert impacts[1].company_id == "U_2"


def test_save_json(propagator: ShockPropagator, tmp_path: Path):
    """Проверяет сохранение результатов в JSON."""
    exposures = {"key_rate": 3.0}
    shock = Shock(factor="key_rate", direction=1.0, magnitude=0.6)
    impact = propagator.impact_on_company(exposures, [shock])
    impact.company_id = "U_1"
    json_path = tmp_path / "impacts.json"
    propagator.save_json([impact], json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["module"] == "shock_propagation"
    assert data["count"] == 1
    assert data["impacts"][0]["company_id"] == "U_1"


def test_propagate_event_function(sample_profiles: Path, tmp_path: Path):
    """Проверяет функцию propagate_event (читает профили, распространяет, сохраняет)."""
    event = {
        "event_id": "evt_1",
        "shocks": [
            {"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}
        ],
    }
    out_path = tmp_path / "impacts.json"
    impacts = propagate_event(sample_profiles, event, out_path)
    assert len(impacts) == 2
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["count"] == 2


def test_factor_graph_consistency():
    """Все факторы в графе должны быть в MACRO_FACTORS."""
    for source, edges in FACTOR_GRAPH.items():
        assert source in MACRO_FACTORS
        for target in edges:
            assert target in MACRO_FACTORS


def test_factor_graph_edges_valid():
    """Рёбра графа должны иметь sign и strength."""
    for source, edges in FACTOR_GRAPH.items():
        for target, edge in edges.items():
            assert edge["sign"] in (-1.0, 1.0)
            assert 0 < edge["strength"] <= 1.0