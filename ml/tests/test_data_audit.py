"""Тесты для модуля аудита данных (data_audit.auditor).

Используют синтетический CSV, чтобы не зависеть от реальных данных кейса.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# Добавляем src в путь для импорта
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from data_audit.auditor import DataAuditor, AuditResult, run_audit  # noqa: E402


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """Создаёт синтетический CSV компаний."""
    data = {
        "SYNTHETIC_U": ["U_1", "U_2", "U_3", "U_4", "U_5"],
        "ORG_TYPE": ["КОММ_ОРГ"] * 5,
        "OKFS_NAME": ["ЧАСТНАЯ СОБСТВЕННОСТЬ"] * 5,
        "COMPANY_AGE_YEARS_GRADATION": ["16-25"] * 5,
        "ECO_MARK_LABEL": ["Оптимизация", "Рождение", "Оптимизация", "Рождение", "Оптимизация"],
        "MAINOKVED_CODE": ["46.51", "52.29", "46.51", "41.20", "62.01"],
        "MAINOKVED_NAME": [
            "Торговля оптовая компьютерами",
            "Деятельность вспомогательная прочая",
            "Торговля оптовая компьютерами",
            "Строительство жилых зданий",
            "Разработка ПО",
        ],
        "NEGATIVEMARK": [0.0, 0.0, 0.0, 0.0, 0.0],
        "AMOUNT_WORKERS_FNS_GRADATION": ["Менее 15"] * 5,
        "AMOUNT_WORKERS_SPARK_GRADATION": [None] * 5,
        "CL_TYPE": ["PROSPECT"] * 5,
        "CL_PRODUCT_RKO_MARK": [1, 0, 1, 0, 1],
        "CL_PRODUCT_GAR_MARK": [0, 0, 0, 0, 0],
        "CL_PRODUCT_LOA_MARK": [1, 0, 0, 0, 0],
        "CL_PRODUCT_LEA_MARK": [0, 1, 0, 0, 0],
        "CL_PRODUCT_DEP_MARK": [0, 0, 1, 0, 0],
        "CL_PRODUCT_ZPP_MARK": [0, 0, 0, 1, 0],
        "FTS_FLAG": [1, 0, 0, 0, 0],
        "FTS_COUNTRY_NAME": ["КИТАЙ", None, None, None, None],
        "FACTORING_MARK": [0, 0, 0, 0, 0],
        "REVENUE_COMPANY": [20_000_000_000.0, 5_000_000.0, 100_000_000.0, 50_000_000.0, 1_000_000.0],
        "GROUP_ID": ["group_1", "group_1", "group_2", None, "group_3"],
        "CITY": ["Москва", "Москва", "СПб", "Новосибирск", "Казань"],
        "REGION": ["Москва", "Москва", "Санкт-Петербург", "Новосибирская область", "Татарстан"],
    }
    df = pd.DataFrame(data)
    csv_path = tmp_path / "companies.csv"
    df.to_csv(csv_path, sep=";", index=False, encoding="utf-8")
    return csv_path


def test_load(sample_csv: Path):
    """Проверяет загрузку CSV с разделителем ';'."""
    auditor = DataAuditor(sample_csv)
    df = auditor.load()
    assert len(df) == 5
    assert "SYNTHETIC_U" in df.columns
    assert "REVENUE_COMPANY" in df.columns


def test_audit_total_companies(sample_csv: Path):
    """Проверяет подсчёт компаний."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    assert result.total_companies == 5


def test_audit_revenue_stats(sample_csv: Path):
    """Проверяет статистику выручки."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    assert result.revenue_stats["min"] == 1_000_000.0
    assert result.revenue_stats["max"] == 20_000_000_000.0
    assert result.revenue_stats["zeros"] == 0


def test_audit_threshold(sample_csv: Path):
    """Проверяет порог допуска (выручка > 15 млрд)."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    # Только U_1 с выручкой 20 млрд проходит порог
    assert result.above_threshold == 1
    assert result.above_threshold_pct == 20.0


def test_audit_missing(sample_csv: Path):
    """Проверяет подсчёт пропусков."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    # FTS_COUNTRY_NAME: 4 из 5 пропущено = 80%
    assert result.missing_stats["FTS_COUNTRY_NAME"] == 80.0
    # SPARK: все 5 пропущено = 100%
    assert result.missing_stats["AMOUNT_WORKERS_SPARK_GRADATION"] == 100.0


def test_audit_products(sample_csv: Path):
    """Проверяет подсчёт банковских продуктов."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    assert result.product_stats["CL_PRODUCT_RKO_MARK"] == 3
    assert result.product_stats["CL_PRODUCT_LOA_MARK"] == 1
    assert result.product_stats["CL_PRODUCT_LEA_MARK"] == 1


def test_audit_fts(sample_csv: Path):
    """Проверяет статистику ВЭД."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    assert result.fts_stats["fts_flag_1"] == 1
    assert result.fts_stats["unique_countries"] == 1


def test_audit_eco_mark(sample_csv: Path):
    """Проверяет распределение стадий развития."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    assert result.eco_mark_stats["unique"] == 2
    assert result.eco_mark_stats["distribution"]["Оптимизация"] == 3
    assert result.eco_mark_stats["distribution"]["Рождение"] == 2


def test_audit_warnings_low_threshold(sample_csv: Path):
    """Проверяет предупреждение при малом числе компаний выше порога."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    # 1 компания выше порога из 5 — мало, должно быть предупреждение
    assert any("Мало компаний выше порога" in w for w in result.warnings)


def test_save_json(sample_csv: Path, tmp_path: Path):
    """Проверяет сохранение результата в JSON."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    json_path = tmp_path / "audit.json"
    auditor.save_json(result, json_path)
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["total_companies"] == 5
    assert "revenue_stats" in data
    assert "missing_stats" in data


def test_run_audit_creates_both(sample_csv: Path, tmp_path: Path):
    """Проверяет, что run_audit создаёт и md, и json."""
    md_path = tmp_path / "audit.md"
    json_path = tmp_path / "audit.json"
    result = run_audit(sample_csv, md_path, json_path)
    assert md_path.exists()
    assert json_path.exists()
    assert result.total_companies == 5
    # JSON читается обратно
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["total_companies"] == 5


def test_audit_result_to_dict(sample_csv: Path):
    """Проверяет, что AuditResult сериализуется в dict (для JSON)."""
    auditor = DataAuditor(sample_csv)
    result = auditor.audit()
    d = result.to_dict()
    assert isinstance(d, dict)
    assert d["total_companies"] == 5
    assert isinstance(d["revenue_stats"], dict)
    assert isinstance(d["missing_stats"], dict)