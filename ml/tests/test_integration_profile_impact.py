"""Интеграционный тест: связка модулей 2 (профиль) + 3 (распространение шоков).

Проверяет полный конвейер:
- Модуль 2 строит профили компаний (JSON)
- Модуль 3 читает профили (JSON), распространяет событие, сохраняет воздействие (JSON)
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from company_profile.profile import CompanyProfileBuilder  # noqa: E402
from shock_propagation.propagator import propagate_event  # noqa: E402


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


def test_full_pipeline_profile_to_impact(sample_csv: Path, tmp_path: Path):
    """Полный конвейер: профили (модуль 2) → воздействие (модуль 3)."""
    # Модуль 2: строим профили
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    # Модуль 3: распространяем событие
    event = {
        "event_id": "evt_rate",
        "shocks": [
            {"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}
        ],
    }
    impacts_json = tmp_path / "impacts.json"
    impacts = propagate_event(profiles_json, event, impacts_json)

    # Проверка: 2 компании
    assert len(impacts) == 2
    data = json.loads(impacts_json.read_text(encoding="utf-8"))
    assert data["count"] == 2

    # U_1 (кредит + торговля) должна иметь воздействие к key_rate
    impact_u1 = next(i for i in data["impacts"] if i["company_id"] == "U_1")
    assert impact_u1["total_impact"] != 0
    assert "key_rate" in impact_u1["factor_impacts"]

    # U_2 (строительство + лизинг) тоже должна иметь воздействие
    impact_u2 = next(i for i in data["impacts"] if i["company_id"] == "U_2")
    assert impact_u2["total_impact"] != 0


def test_impact_paths_explainable(sample_csv: Path, tmp_path: Path):
    """Пути вклада должны быть объяснимыми (для трассируемости)."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    event = {
        "event_id": "evt_rate",
        "shocks": [
            {"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}
        ],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    data = json.loads(impacts_json.read_text(encoding="utf-8"))
    impact_u1 = next(i for i in data["impacts"] if i["company_id"] == "U_1")
    # Должны быть пути вклада
    assert len(impact_u1["top_paths"]) > 0
    # Каждый путь — список факторов
    for path in impact_u1["top_paths"]:
        assert isinstance(path["path"], list)
        assert len(path["path"]) >= 1
        assert path["path"][0] == "key_rate"  # начинается с шока


def test_json_roundtrip_all_modules(sample_csv: Path, tmp_path: Path):
    """JSON из всех модулей валиден и сериализуется обратно."""
    # Модуль 2
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)
    profiles_data = json.loads(profiles_json.read_text(encoding="utf-8"))
    json.dumps(profiles_data, ensure_ascii=False)

    # Модуль 3
    event = {
        "event_id": "evt_rate",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)
    impacts_data = json.loads(impacts_json.read_text(encoding="utf-8"))
    json.dumps(impacts_data, ensure_ascii=False)