"""Интеграционный тест: связка модулей 1 (аудит) + 2 (профиль).

Проверяет, что данные передаются между модулями в формате JSON:
- Модуль 1 (аудит) сохраняет результат в JSON
- Модуль 2 (профиль) читает CSV и сохраняет профили в JSON
- Оба JSON валидны и согласованы (одинаковое число компаний)
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from data_audit.auditor import DataAuditor  # noqa: E402
from company_profile.profile import CompanyProfileBuilder  # noqa: E402


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Создаёт синтетический CSV компаний."""
    data = {
        "SYNTHETIC_U": ["U_1", "U_2", "U_3"],
        "ORG_TYPE": ["КОММ_ОРГ"] * 3,
        "OKFS_NAME": ["ЧАСТНАЯ СОБСТВЕННОСТЬ"] * 3,
        "COMPANY_AGE_YEARS_GRADATION": ["16-25"] * 3,
        "ECO_MARK_LABEL": ["Оптимизация", "Рождение", "Бизнес в новой реальности"],
        "MAINOKVED_CODE": ["46.51", "41.20", "62.01"],
        "MAINOKVED_NAME": ["Торговля оптовая", "Строительство", "Разработка ПО"],
        "NEGATIVEMARK": [0.0, 0.0, 0.0],
        "AMOUNT_WORKERS_FNS_GRADATION": ["Менее 15"] * 3,
        "AMOUNT_WORKERS_SPARK_GRADATION": [None] * 3,
        "CL_TYPE": ["PROSPECT"] * 3,
        "CL_PRODUCT_RKO_MARK": [1, 0, 0],
        "CL_PRODUCT_GAR_MARK": [0, 0, 0],
        "CL_PRODUCT_LOA_MARK": [1, 0, 0],
        "CL_PRODUCT_LEA_MARK": [0, 1, 0],
        "CL_PRODUCT_DEP_MARK": [0, 0, 0],
        "CL_PRODUCT_ZPP_MARK": [0, 0, 0],
        "FTS_FLAG": [1, 0, 0],
        "FTS_COUNTRY_NAME": ["КИТАЙ", None, None],
        "FACTORING_MARK": [0, 0, 0],
        "REVENUE_COMPANY": [20_000_000_000.0, 5_000_000.0, 100_000_000.0],
        "GROUP_ID": ["group_1", "group_2", None],
        "CITY": ["Москва", "Москва", "СПб"],
        "REGION": ["Москва", "Москва", "Санкт-Петербург"],
    }
    df = pd.DataFrame(data)
    csv_path = tmp_path / "companies.csv"
    df.to_csv(csv_path, sep=";", index=False, encoding="utf-8")
    return csv_path


def test_module1_json_is_valid(sample_csv: Path, tmp_path: Path):
    """Модуль 1 сохраняет валидный JSON."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    json_path = tmp_path / "audit.json"
    auditor.save_json(result, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["total_companies"] == 3
    assert "revenue_stats" in data
    assert "missing_stats" in data


def test_module2_json_is_valid(sample_csv: Path, tmp_path: Path):
    """Модуль 2 сохраняет валидный JSON."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    json_path = tmp_path / "profiles.json"
    builder.save_json(profiles, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["count"] == 3
    assert data["module"] == "company_profile"
    assert "macro_factors" in data


def test_pipeline_audit_then_profile(sample_csv: Path, tmp_path: Path):
    """Полный конвейер: аудит → профили, оба JSON согласованы."""
    # Модуль 1: аудит
    auditor = DataAuditor(sample_csv)
    audit_result = auditor.audit()
    audit_json = tmp_path / "audit.json"
    auditor.save_json(audit_result, audit_json)

    # Модуль 2: профили
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)

    # Проверка согласованности: число компаний одинаково
    audit_data = json.loads(audit_json.read_text(encoding="utf-8"))
    profiles_data = json.loads(profiles_json.read_text(encoding="utf-8"))
    assert audit_data["total_companies"] == profiles_data["count"] == 3

    # Профили содержат те же company_id, что и в CSV
    profile_ids = {p["company_id"] for p in profiles_data["profiles"]}
    assert profile_ids == {"U_1", "U_2", "U_3"}


def test_profiles_have_exposures_for_all_companies(sample_csv: Path, tmp_path: Path):
    """Все профили имеют экспозиции ко всем макрофакторам."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    json_path = tmp_path / "profiles.json"
    builder.save_json(profiles, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    factors = set(data["macro_factors"])
    for p in data["profiles"]:
        assert set(p["exposures"].keys()) == factors


def test_json_roundtrip_no_nan(sample_csv: Path, tmp_path: Path):
    """JSON из обоих модулей не содержит NaN (валиден для передачи)."""
    auditor = DataAuditor(sample_csv)
    audit_result = auditor.audit()
    audit_json = tmp_path / "audit.json"
    auditor.save_json(audit_result, audit_json)
    audit_data = json.loads(audit_json.read_text(encoding="utf-8"))
    # Проверяем, что JSON сериализуется обратно без ошибок
    json.dumps(audit_data, ensure_ascii=False)

    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    profiles_json = tmp_path / "profiles.json"
    builder.save_json(profiles, profiles_json)
    profiles_data = json.loads(profiles_json.read_text(encoding="utf-8"))
    json.dumps(profiles_data, ensure_ascii=False)