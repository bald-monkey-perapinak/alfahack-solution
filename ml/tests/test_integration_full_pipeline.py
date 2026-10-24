"""Интеграционный тест: связка модулей 3+4+5 (воздействие → ранжирование → инсайт).

Проверяет полный конвейер:
- Модуль 2 строит профили (JSON)
- Модуль 3 распространяет событие -> воздействие (JSON)
- Модуль 4 ранжирует для пользователя -> топ-N (JSON)
- Модуль 5 генерирует инсайты -> инсайты (JSON)
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
from insight_generator.analyst import generate_insights  # noqa: E402


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


def test_full_pipeline_to_insight(sample_csv: Path, tmp_path: Path):
    """Полный конвейер: профили → воздействие → ранжирование → инсайт."""
    # Модуль 2: профили
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    # Модуль 3: воздействие
    event = {
        "event_id": "evt_rate",
        "event_type": "central_bank_rate_decision",
        "title": "ЦБ сохранил ключевую ставку на уровне 14%",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    # Модуль 4: ранжирование для CFO
    user = UserProfile(user_id="u1", role="cfo")
    ranked_json = tmp_path / "ranked.json"
    rank_for_user(impacts_json, user, ranked_json, top_n=2)

    # Модуль 5: инсайты
    user_dict = {"user_id": "u1", "role": "cfo"}
    insights_json = tmp_path / "insights.json"
    insights = generate_insights(ranked_json, profiles_json, user_dict, insights_json, event)

    # Проверка
    assert len(insights) == 2
    data = json.loads(insights_json.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert data["module"] == "insight_generator"

    # U_1 (кредит) должна иметь инсайт с действием fix_rate
    insight_u1 = next(i for i in data["insights"] if i["company_id"] == "U_1")
    assert "central_bank_rate_decision" in insight_u1["headline"]
    action_types = [a["type"] for a in insight_u1["actions"]]
    assert "fix_rate" in action_types
    # Должен быть факт из события
    assert len(insight_u1["channels"]["fact"]) == 1


def test_insight_traceability(sample_csv: Path, tmp_path: Path):
    """Инсайт должен содержать версии и пути вклада (для трассируемости)."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    event = {
        "event_id": "evt_rate",
        "event_type": "central_bank_rate_decision",
        "title": "ЦБ сохранил ставку",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    user = UserProfile(user_id="u1", role="cfo")
    ranked_json = tmp_path / "ranked.json"
    rank_for_user(impacts_json, user, ranked_json, top_n=2)

    user_dict = {"user_id": "u1", "role": "cfo"}
    insights_json = tmp_path / "insights.json"
    generate_insights(ranked_json, profiles_json, user_dict, insights_json, event, trace_id="trc_1")

    data = json.loads(insights_json.read_text(encoding="utf-8"))
    insight_u1 = next(i for i in data["insights"] if i["company_id"] == "U_1")
    # Версии
    assert "graph" in insight_u1["versions"]
    assert "weights" in insight_u1["versions"]
    # trace_id
    assert insight_u1["trace_id"] == "trc_1"
    # AI-вывод (пути вклада)
    assert len(insight_u1["channels"]["ai_conclusion"]) > 0


def test_json_roundtrip_all_modules(sample_csv: Path, tmp_path: Path):
    """JSON из всех модулей валиден."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    event = {
        "event_id": "evt_rate",
        "event_type": "central_bank_rate_decision",
        "title": "ЦБ сохранил ставку",
        "shocks": [{"factor": "key_rate", "direction": 1.0, "magnitude": 0.6}],
    }
    impacts_json = tmp_path / "impacts.json"
    propagate_event(profiles_json, event, impacts_json)

    user = UserProfile(user_id="u1", role="cfo")
    ranked_json = tmp_path / "ranked.json"
    rank_for_user(impacts_json, user, ranked_json, top_n=2)

    user_dict = {"user_id": "u1", "role": "cfo"}
    insights_json = tmp_path / "insights.json"
    generate_insights(ranked_json, profiles_json, user_dict, insights_json, event)

    # Все JSON валидны
    for p in [profiles_json, impacts_json, ranked_json, insights_json]:
        data = json.loads(p.read_text(encoding="utf-8"))
        json.dumps(data, ensure_ascii=False)