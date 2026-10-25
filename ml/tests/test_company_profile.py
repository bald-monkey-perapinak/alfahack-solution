"""Тесты для модуля профиля компании и экспозиций (company_profile.profile)."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from company_profile.profile import (  # noqa: E402
    CompanyProfileBuilder,
    CompanyProfile,
    build_profiles,
    MACRO_FACTORS,
    _clean_nan,
)


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


def test_load(sample_csv: Path):
    builder = CompanyProfileBuilder(sample_csv)
    df = builder.load()
    assert len(df) == 3


def test_okved_section(sample_csv: Path):
    builder = CompanyProfileBuilder(sample_csv)
    # 46.51 — торговля (G), 41.20 — строительство (F), 62.01 — информация (J)
    assert builder._okved_section("46.51") == "G"
    assert builder._okved_section("41.20") == "F"
    assert builder._okved_section("62.01") == "J"
    assert builder._okved_section(None) == ""
    assert builder._okved_section("") == ""


def test_build_profile_observed(sample_csv: Path):
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]
    profile = builder.build_profile(row)
    assert profile.company_id == "U_1"
    assert profile.observed["okved_code"] == "46.51"
    assert profile.observed["products"]["CL_PRODUCT_LOA_MARK"] == 1
    assert profile.observed["revenue"] == 20_000_000_000.0


def test_build_profile_inferred(sample_csv: Path):
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]
    profile = builder.build_profile(row)
    assert profile.inferred["okved_section"] == "G"
    assert profile.inferred["has_fts"] is True
    assert profile.inferred["is_large"] is True


def test_exposures_industry(sample_csv: Path):
    """Торговля (G) должна иметь экспозицию к consumption."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]  # 46.51 торговля
    profile = builder.build_profile(row)
    assert profile.exposures["consumption"] > 0
    assert profile.exposures["inflation"] > 0


def test_exposures_product(sample_csv: Path):
    """Компания с кредитом должна иметь экспозицию к key_rate."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]  # CL_PRODUCT_LOA_MARK=1
    profile = builder.build_profile(row)
    assert profile.exposures["key_rate"] > 0
    assert profile.exposures["lending"] > 0


def test_exposures_country(sample_csv: Path):
    """Компания с ВЭД Китай должна иметь экспозицию к currency/logistics."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]  # FTS_COUNTRY_NAME=КИТАЙ
    profile = builder.build_profile(row)
    assert profile.exposures["currency"] > 0
    assert profile.exposures["logistics"] > 0


def test_exposures_scale(sample_csv: Path):
    """Крупная компания (>15 млрд) должна иметь экспозицию к sanctions."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]  # revenue=20 млрд
    profile = builder.build_profile(row)
    assert profile.exposures["sanctions"] > 0


def test_confidence_reduced_on_missing(sample_csv: Path):
    """Уверенность снижается при пропусках (FTS_COUNTRY_NAME)."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    # U_2: FTS_COUNTRY_NAME=None, ECO_MARK=Рождение (не None)
    row = builder.df.iloc[1]
    profile = builder.build_profile(row)
    assert profile.confidence < 1.0
    # U_1: FTS_COUNTRY_NAME=КИТАЙ, все поля есть
    row1 = builder.df.iloc[0]
    profile1 = builder.build_profile(row1)
    assert profile1.confidence == 1.0


def test_all_macro_factors_present(sample_csv: Path):
    """Все макрофакторы должны быть в экспозициях."""
    builder = CompanyProfileBuilder(sample_csv)
    builder.load()
    row = builder.df.iloc[0]
    profile = builder.build_profile(row)
    assert set(profile.exposures.keys()) == set(MACRO_FACTORS)


def test_save_json_valid(sample_csv: Path, tmp_path: Path):
    """JSON должен быть валидным и без NaN."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all()
    json_path = tmp_path / "profiles.json"
    builder.save_json(profiles, json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["count"] == 3
    assert data["module"] == "company_profile"
    # Проверяем, что нет NaN (fts_country=None для U_2)
    for p in data["profiles"]:
        assert p["observed"]["fts_country"] is None or isinstance(
            p["observed"]["fts_country"], str
        )


def test_clean_nan():
    """Проверяет рекурсивную очистку NaN."""
    import math
    data = {"a": float("nan"), "b": [1, float("nan")], "c": {"d": float("nan")}}
    clean = _clean_nan(data)
    assert clean["a"] is None
    assert clean["b"][1] is None
    assert clean["c"]["d"] is None


def test_build_profiles_function(sample_csv: Path, tmp_path: Path):
    """Проверяет функцию build_profiles."""
    json_path = tmp_path / "profiles.json"
    profiles = build_profiles(sample_csv, json_path)
    assert len(profiles) == 3
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["count"] == 3


def test_build_all_limit(sample_csv: Path):
    """Проверяет лимит на число профилей."""
    builder = CompanyProfileBuilder(sample_csv)
    profiles = builder.build_all(limit=2)
    assert len(profiles) == 2