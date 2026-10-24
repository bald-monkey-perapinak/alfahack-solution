"""Модуль 1: Аудит данных компаний.

Анализирует CSV с профилями компаний (df_Uid_data_hack.csv):
- распределение выручки (REVENUE_COMPANY), единицы измерения
- покрытие по отраслям (ОКВЭД), регионам, группам
- доля пропусков в ключевых полях
- порог допуска (выручка > 15 млрд руб)
- банковские продукты, ВЭД, стадия развития

Результат пишется в markdown-отчёт (utf-8), т.к. консоль Windows (cp1251)
не отображает кириллицу корректно.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import pandas as pd

# Порог допуска из кейса (выручка > 15 млрд руб)
REVENUE_THRESHOLD = 15_000_000_000


@dataclass
class AuditResult:
    """Результат аудита данных компаний."""

    total_companies: int = 0
    columns: list[str] = field(default_factory=list)
    revenue_stats: dict[str, Any] = field(default_factory=dict)
    revenue_units: str = "не определены"
    above_threshold: int = 0
    above_threshold_pct: float = 0.0
    missing_revenue: int = 0
    industry_coverage: dict[str, Any] = field(default_factory=dict)
    region_coverage: dict[str, Any] = field(default_factory=dict)
    group_stats: dict[str, Any] = field(default_factory=dict)
    missing_stats: dict[str, Any] = field(default_factory=dict)
    product_stats: dict[str, Any] = field(default_factory=dict)
    fts_stats: dict[str, Any] = field(default_factory=dict)
    eco_mark_stats: dict[str, Any] = field(default_factory=dict)
    correlations: dict[str, Any] = field(default_factory=dict)  # корреляции
    threshold_recommendation: dict[str, Any] = field(default_factory=dict)  # рекомендация по порогу
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DataAuditor:
    """Аудит данных компаний из CSV."""

    def __init__(self, csv_path: str | Path, threshold: float = REVENUE_THRESHOLD):
        self.csv_path = Path(csv_path)
        self.threshold = threshold
        self.df: pd.DataFrame | None = None

    def load(self) -> pd.DataFrame:
        """Загружает CSV с правильным разделителем и кодировкой."""
        self.df = pd.read_csv(self.csv_path, sep=";", encoding="utf-8")
        return self.df

    def _missing_pct(self, col: str) -> float:
        """Доля пропусков в колонке (%)."""
        if self.df is None or col not in self.df.columns:
            return 0.0
        return round(float(self.df[col].isna().mean() * 100), 2)

    def _compute_correlations(self, df: pd.DataFrame) -> dict[str, Any]:
        """Считает корреляции между выручкой и ключевыми признаками.

        Показывает, какие признаки сильнее всего связаны с размером компании.
        """
        corr = {}
        rev = pd.to_numeric(df["REVENUE_COMPANY"], errors="coerce")
        # Признаки, которые могут коррелировать с выручкой
        features = {
            "AMOUNT_WORKERS_FNS_GRADATION": "численность (ФНС)",
            "AMOUNT_WORKERS_SPARK_GRADATION": "численность (СПАРК)",
            "FTS_FLAG": "ВЭД-флаг",
        }
        for col, label in features.items():
            if col in df.columns:
                series = pd.to_numeric(df[col], errors="coerce")
                if series.notna().sum() > 1:
                    c = rev.corr(series)
                    if pd.notna(c):
                        corr[label] = round(float(c), 3)
        # Корреляция выручки с наличием банковских продуктов
        product_cols = [
            "CL_PRODUCT_RKO_MARK", "CL_PRODUCT_GAR_MARK", "CL_PRODUCT_LOA_MARK",
            "CL_PRODUCT_LEA_MARK", "CL_PRODUCT_DEP_MARK", "CL_PRODUCT_ZPP_MARK",
            "FACTORING_MARK",
        ]
        for col in product_cols:
            if col in df.columns:
                series = pd.to_numeric(df[col], errors="coerce")
                if series.notna().sum() > 1:
                    c = rev.corr(series)
                    if pd.notna(c):
                        corr[f"продукт {col}"] = round(float(c), 3)
        return corr

    def _recommend_threshold(self, df: pd.DataFrame) -> dict[str, Any]:
        """Рекомендует порог допуска (абсолютный + относительный).

        Если абсолютный порог (15 млрд) отсекает слишком мало/много компаний,
        предлагает относительный порог по перцентилю.
        """
        rev = pd.to_numeric(df["REVENUE_COMPANY"], errors="coerce").dropna()
        if len(rev) == 0:
            return {"recommended": "нет данных", "reason": "нет выручки"}
        p90 = float(rev.quantile(0.90))
        p95 = float(rev.quantile(0.95))
        p99 = float(rev.quantile(0.99))
        above_abs = int((rev > self.threshold).sum())
        pct_above = above_abs / len(rev) * 100

        # Рекомендация: если абсолютный порог отсекает <5% или >50% — нужен относительный
        if pct_above < 5:
            rec = {
                "recommended": "относительный порог (P90)",
                "reason": f"Абсолютный порог {self.threshold:,.0f} отсекает только {pct_above:.1f}% компаний",
                "p90": p90,
                "p95": p95,
                "p99": p99,
                "companies_above_p90": int((rev > p90).sum()),
            }
        elif pct_above > 50:
            rec = {
                "recommended": "относительный порог (P50-P75)",
                "reason": f"Абсолютный порог {self.threshold:,.0f} пропускает {pct_above:.1f}% компаний — слишком широко",
                "p90": p90,
                "p95": p95,
                "p99": p99,
                "companies_above_p90": int((rev > p90).sum()),
            }
        else:
            rec = {
                "recommended": "абсолютный порог (15 млрд)",
                "reason": f"Порог отсекает {pct_above:.1f}% компаний — приемлемо",
                "p90": p90,
                "p95": p95,
                "p99": p99,
                "companies_above_p90": int((rev > p90).sum()),
            }
        return rec

    def audit(self) -> AuditResult:
        """Выполняет полный аудит данных."""
        if self.df is None:
            self.load()

        result = AuditResult()
        df = self.df
        result.total_companies = len(df)
        result.columns = list(df.columns)

        # --- Выручка ---
        rev = df["REVENUE_COMPANY"]
        result.missing_revenue = int(rev.isna().sum())
        rev_clean = rev.dropna()
        result.revenue_stats = {
            "min": float(rev_clean.min()) if len(rev_clean) else None,
            "max": float(rev_clean.max()) if len(rev_clean) else None,
            "median": float(rev_clean.median()) if len(rev_clean) else None,
            "mean": float(rev_clean.mean()) if len(rev_clean) else None,
            "p25": float(rev_clean.quantile(0.25)) if len(rev_clean) else None,
            "p75": float(rev_clean.quantile(0.75)) if len(rev_clean) else None,
            "p90": float(rev_clean.quantile(0.90)) if len(rev_clean) else None,
            "p99": float(rev_clean.quantile(0.99)) if len(rev_clean) else None,
            "zeros": int((rev_clean == 0).sum()),
        }
        # Определение единиц: если max > 1e12, вероятно копейки; если ~1e6-1e9, рубли
        if result.revenue_stats["max"]:
            mx = result.revenue_stats["max"]
            if mx > 1e12:
                result.revenue_units = "вероятно, копейки (значения > 1e12)"
            elif mx > 1e9:
                result.revenue_units = "вероятно, рубли (значения до ~1e9-1e10)"
            else:
                result.revenue_units = "неоднозначно (значения < 1e9)"

        # Порог допуска
        result.above_threshold = int((rev_clean > self.threshold).sum())
        result.above_threshold_pct = round(
            result.above_threshold / result.total_companies * 100, 2
        ) if result.total_companies else 0.0

        # --- Отрасли (ОКВЭД) ---
        okved = df["MAINOKVED_CODE"].dropna()
        result.industry_coverage = {
            "unique_okved_codes": int(okved.nunique()),
            "top_industries": (
                df["MAINOKVED_NAME"].dropna().value_counts().head(10).to_dict()
            ),
        }

        # --- Регионы ---
        region = df["REGION"].dropna()
        result.region_coverage = {
            "unique_regions": int(region.nunique()),
            "top_regions": region.value_counts().head(10).to_dict(),
        }

        # --- Группы ---
        grp = df["GROUP_ID"].dropna()
        result.group_stats = {
            "unique_groups": int(grp.nunique()),
            "companies_in_groups": int((df["GROUP_ID"].notna()).sum()),
            "avg_group_size": round(float(grp.value_counts().mean()), 2) if len(grp) else 0,
        }

        # --- Пропуски ---
        result.missing_stats = {
            col: self._missing_pct(col)
            for col in [
                "REVENUE_COMPANY", "MAINOKVED_CODE", "MAINOKVED_NAME",
                "REGION", "CITY", "GROUP_ID", "FTS_COUNTRY_NAME",
                "AMOUNT_WORKERS_FNS_GRADATION", "AMOUNT_WORKERS_SPARK_GRADATION",
                "ECO_MARK_LABEL", "NEGATIVEMARK",
            ]
        }

        # --- Банковские продукты ---
        product_cols = [
            "CL_PRODUCT_RKO_MARK", "CL_PRODUCT_GAR_MARK", "CL_PRODUCT_LOA_MARK",
            "CL_PRODUCT_LEA_MARK", "CL_PRODUCT_DEP_MARK", "CL_PRODUCT_ZPP_MARK",
            "FACTORING_MARK",
        ]
        result.product_stats = {
            col: int((df[col] == 1).sum()) if col in df.columns else 0
            for col in product_cols
        }

        # --- ВЭД ---
        result.fts_stats = {
            "fts_flag_1": int((df["FTS_FLAG"] == 1).sum()) if "FTS_FLAG" in df.columns else 0,
            "unique_countries": int(df["FTS_COUNTRY_NAME"].dropna().nunique()),
            "top_countries": (
                df["FTS_COUNTRY_NAME"].dropna().value_counts().head(10).to_dict()
            ),
        }

        # --- Стадия развития ---
        result.eco_mark_stats = {
            "unique": int(df["ECO_MARK_LABEL"].dropna().nunique()),
            "distribution": df["ECO_MARK_LABEL"].dropna().value_counts().to_dict(),
        }

        # --- Корреляции ---
        result.correlations = self._compute_correlations(df)

        # --- Рекомендация по порогу ---
        result.threshold_recommendation = self._recommend_threshold(df)

        # --- Предупреждения ---
        if result.missing_revenue > 0:
            result.warnings.append(
                f"Пропущено выручки: {result.missing_revenue} компаний "
                f"({round(result.missing_revenue / result.total_companies * 100, 2)}%)"
            )
        if result.revenue_stats.get("zeros", 0) > 0:
            result.warnings.append(
                f"Нулевая выручка: {result.revenue_stats['zeros']} компаний"
            )
        if result.above_threshold == 0:
            result.warnings.append(
                "Ни одна компания не проходит порог 15 млрд — нужен относительный порог"
            )
        elif result.above_threshold < 50:
            result.warnings.append(
                f"Мало компаний выше порога ({result.above_threshold}) — "
                "нужен относительный порог (верхний перцентиль)"
            )
        # Добавляем рекомендацию по порогу в предупреждения
        rec = result.threshold_recommendation
        if rec.get("recommended", "").startswith("относительный"):
            result.warnings.append(
                f"Рекомендация: {rec['recommended']} — {rec['reason']}"
            )

        return result

    def to_markdown(self, result: AuditResult) -> str:
        """Форматирует результат аудита в markdown."""
        lines = [
            "# Аудит данных компаний",
            "",
            f"**Всего компаний:** {result.total_companies}",
            f"**Колонок:** {len(result.columns)}",
            "",
            "## Выручка (REVENUE_COMPANY)",
            "",
            f"- Единицы: **{result.revenue_units}**",
            f"- Пропущено: {result.missing_revenue}",
            f"- Нулевых: {result.revenue_stats.get('zeros', 0)}",
            f"- Min: {result.revenue_stats.get('min')}",
            f"- Max: {result.revenue_stats.get('max')}",
            f"- Median: {result.revenue_stats.get('median')}",
            f"- Mean: {result.revenue_stats.get('mean')}",
            f"- P25: {result.revenue_stats.get('p25')}",
            f"- P75: {result.revenue_stats.get('p75')}",
            f"- P90: {result.revenue_stats.get('p90')}",
            f"- P99: {result.revenue_stats.get('p99')}",
            "",
            "## Порог допуска (выручка > 15 млрд)",
            "",
            f"- Компаний выше порога: **{result.above_threshold}** "
            f"({result.above_threshold_pct}%)",
            "",
            "## Отрасли (ОКВЭД)",
            "",
            f"- Уникальных кодов ОКВЭД: {result.industry_coverage.get('unique_okved_codes')}",
            f"- Топ-10 отраслей: {json.dumps(result.industry_coverage.get('top_industries', {}), ensure_ascii=False)}",
            "",
            "## Регионы",
            "",
            f"- Уникальных регионов: {result.region_coverage.get('unique_regions')}",
            f"- Топ-10 регионов: {json.dumps(result.region_coverage.get('top_regions', {}), ensure_ascii=False)}",
            "",
            "## Группы",
            "",
            f"- Уникальных групп: {result.group_stats.get('unique_groups')}",
            f"- Компаний в группах: {result.group_stats.get('companies_in_groups')}",
            f"- Средний размер группы: {result.group_stats.get('avg_group_size')}",
            "",
            "## Пропуски (%)",
            "",
            "| Поле | Пропуски % |",
            "|---|---|",
        ]
        for col, pct in result.missing_stats.items():
            lines.append(f"| {col} | {pct} |")

        lines += [
            "",
            "## Банковские продукты",
            "",
            "| Продукт | Компаний |",
            "|---|---|",
        ]
        for col, cnt in result.product_stats.items():
            lines.append(f"| {col} | {cnt} |")

        lines += [
            "",
            "## ВЭД",
            "",
            f"- FTS_FLAG=1: {result.fts_stats.get('fts_flag_1')}",
            f"- Уникальных стран: {result.fts_stats.get('unique_countries')}",
            f"- Топ-10 стран: {json.dumps(result.fts_stats.get('top_countries', {}), ensure_ascii=False)}",
            "",
            "## Стадия развития",
            "",
            f"- Распределение: {json.dumps(result.eco_mark_stats.get('distribution', {}), ensure_ascii=False)}",
            "",
            "## Корреляции с выручкой",
            "",
        ]
        if result.correlations:
            for label, c in result.correlations.items():
                lines.append(f"- {label}: **{c}**")
        else:
            lines.append("- Нет данных для корреляций")

        lines += [
            "",
            "## Рекомендация по порогу",
            "",
            f"- Рекомендация: **{result.threshold_recommendation.get('recommended', '—')}**",
            f"- Причина: {result.threshold_recommendation.get('reason', '—')}",
            f"- P90 выручки: {result.threshold_recommendation.get('p90', '—')}",
            f"- P95 выручки: {result.threshold_recommendation.get('p95', '—')}",
            f"- P99 выручки: {result.threshold_recommendation.get('p99', '—')}",
            "",
            "## Предупреждения",
            "",
        ]
        if result.warnings:
            for w in result.warnings:
                lines.append(f"- ⚠️ {w}")
        else:
            lines.append("- Нет предупреждений")

        return "\n".join(lines)

    def save_report(self, result: AuditResult, out_path: str | Path) -> Path:
        """Сохраняет отчёт в файл (utf-8)."""
        out = Path(out_path)
        out.write_text(self.to_markdown(result), encoding="utf-8")
        return out

    def save_json(self, result: AuditResult, out_path: str | Path) -> Path:
        """Сохраняет результат аудита в JSON (для передачи между модулями).

        Данные между модулями передаются в формате JSON — это ключевое
        требование архитектуры. JSON-файл содержит структурированный результат
        аудита, который следующий модуль может прочитать напрямую.
        """
        out = Path(out_path)
        out.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out


def run_audit(
    csv_path: str | Path,
    out_path: str | Path,
    json_path: str | Path | None = None,
) -> AuditResult:
    """Удобная функция: загружает, аудирует, сохраняет отчёт (md + json).

    Args:
        csv_path: путь к CSV компаний.
        out_path: путь для markdown-отчёта.
        json_path: путь для JSON-результата (для передачи между модулями).
            Если None, JSON сохраняется рядом с md-отчётом с суффиксом .json.
    """
    auditor = DataAuditor(csv_path)
    result = auditor.audit()
    auditor.save_report(result, out_path)
    if json_path is None:
        json_path = str(Path(out_path).with_suffix(".json"))
    auditor.save_json(result, json_path)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Использование: python data_audit.py <csv_path> <out_path> [json_path]")
        sys.exit(1)
    json_arg = sys.argv[3] if len(sys.argv) > 3 else None
    run_audit(sys.argv[1], sys.argv[2], json_arg)
    print("Отчёт сохранён (md + json).")