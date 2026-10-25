"""Интеграционный тест: связка модулей 3 (распространение) + 4 (ранжирование).

Проверяет полный конвейер:
- Модуль 2 строит профили (JSON)
- Модуль 3 распространяет событие -> воздействие (JSON)
- Модуль 4 ранжирует для пользователя -> топ-N (JSON)
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
from event_ranking.ranker import rank_for_user, UserProfile  # noqa: E402


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


def test_full_pipeline_profile_impact_rank(sample_csv: Path, tmp_path: Path):
    """Полный конвейер: профили → воздействие → ранжирование."""
    # Модуль 2: профили
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    # Модуль 3: воздействие
    event = {
        "event_id": "evt_rate",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    # Модуль 4: ранжирование для CFO
    user = UserProfile(user_id="u1", role="cfo")
    ranked_json = tmp_path / "ranked.json"
    ranked = rank_for_user(impacts_json, user, ranked_json, top_n=2)

    # Проверка
    assert len(ranked) == 2
    data = json.loads(ranked_json.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert data["module"] == "event_ranking"

    # U_1 (кредит) должна иметь высокий скоринг для CFO
    ranked_u1 = next(r for r in data["ranked_events"] if r["company_id"] == "U_1")
    assert ranked_u1["score"] > 0
    assert "key_rate" in ranked_u1.get("explanation", []) or len(ranked_u1["explanation"]) > 0


def test_ranking_differs_by_role(sample_csv: Path, tmp_path: Path):
    """Разные роли должны давать разный порядок ранжирования."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    event = {
        "event_id": "evt_rate",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    # CFO и CEO
    cfo = UserProfile(user_id="cfo", role="cfo")
    ceo = UserProfile(user_id="ceo", role="ceo")
    ranked_cfo = rank_for_user(impacts_json, cfo, tmp_path / "ranked_cfo.json", top_n=2)
    ranked_ceo = rank_for_user(impacts_json, ceo, tmp_path / "ranked_ceo.json", top_n=2)

    # Оба ранжируют, но скоринги могут отличаться
    assert len(ranked_cfo) == 2
    assert len(ranked_ceo) == 2
    # Скоринг CFO для U_1 (кредит) должен быть выше, чем CEO
    # (key_rate важнее для CFO)
    score_cfo_u1 = next(r.score for r in ranked_cfo if r.company_id == "U_1")
    score_ceo_u1 = next(r.score for r in ranked_ceo if r.company_id == "U_1")
    assert score_cfo_u1 > score_ceo_u1


def test_json_roundtrip_all_modules(sample_csv: Path, tmp_path: Path):
    """JSON из всех модулей валиден."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    event = {
        "event_id": "evt_rate",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    user = UserProfile(user_id="u1", role="cfo")
    ranked_json = tmp_path / "ranked.json"
    rank_for_user(impacts_json, user, ranked_json, top_n=2)

    # Все JSON валидны
    for p in [profiles_json, impacts_json, ranked_json]:
        data = json.loads(p.read_text(encoding="utf-8"))
        json.dumps(data, ensure_ascii=False)