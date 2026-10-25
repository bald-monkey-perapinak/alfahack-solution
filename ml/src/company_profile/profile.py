"""Модуль 2: Профиль компании и экспозиции к макрофакторам.

Строит профиль компании в три слоя (observed/declared/inferred) и считает
вектор экспозиций к макрофакторам. Экспозиция — чувствительность компании
к изменению макрофактора (ставка, инфляция, валюта, санкции и т.д.).

Вход: CSV компаний (df_Uid_data_hack.csv).
Выход: JSON с профилями и экспозициями (для передачи между модулями).

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import pandas as pd

# Макрофакторы (из документов ЦМИ и кейса)
MACRO_FACTORS = [
    "key_rate",       # ключевая ставка ЦБ
    "inflation",      # инфляция
    "consumption",    # потребление
    "gdp",            # ВВП
    "labor_market",   # рынок труда
    "bonds",          # облигации / долговой рынок
    "gold",           # золото
    "commodities",    # сырьё
    "currency",       # валюта (курс)
    "sanctions",      # санкции
    "logistics",      # логистика / цепочки поставок
    "real_estate",    # недвижимость
    "lending",        # кредитование / ликвидность
]

# Чувствительность отраслей (ОКВЭД раздел) к факторам.
# Значения: 0 (нет), 1 (слабая), 2 (средняя), 3 (сильная).
INDUSTRY_EXPOSURE = {
    "A": {"commodities": 3, "currency": 2, "logistics": 2, "sanctions": 2},
    "B": {"commodities": 3, "currency": 3, "sanctions": 3, "logistics": 2},
    "C": {"commodities": 2, "currency": 2, "sanctions": 2, "logistics": 2, "key_rate": 1},
    "D": {"commodities": 3, "key_rate": 2, "inflation": 2},
    "E": {"key_rate": 2, "inflation": 1, "lending": 2},
    "F": {"key_rate": 3, "real_estate": 3, "inflation": 2, "lending": 3},
    "G": {"consumption": 3, "inflation": 2, "key_rate": 1, "logistics": 2, "currency": 2},
    "H": {"logistics": 3, "commodities": 2, "sanctions": 2, "currency": 2},
    "I": {"consumption": 2, "inflation": 1},
    "J": {"key_rate": 1, "gdp": 1},
    "K": {"key_rate": 3, "lending": 3, "bonds": 3, "gdp": 2},
    "L": {"real_estate": 3, "key_rate": 3, "inflation": 2},
    "M": {"gdp": 1},
    "N": {"gdp": 1, "consumption": 1},
    "O": {"gdp": 1},
    "P": {"gdp": 1},
    "Q": {"gdp": 1, "inflation": 1},
    "R": {"consumption": 1},
    "S": {"consumption": 1},
}

# Чувствительность банковских продуктов к факторам
PRODUCT_EXPOSURE = {
    "CL_PRODUCT_LOA_MARK": {"key_rate": 3, "lending": 3, "bonds": 2},
    "CL_PRODUCT_LEA_MARK": {"key_rate": 3, "lending": 3},
    "CL_PRODUCT_DEP_MARK": {"key_rate": 2, "bonds": 2},
    "CL_PRODUCT_GAR_MARK": {"key_rate": 2, "lending": 2},
    "FACTORING_MARK": {"key_rate": 2, "lending": 2, "logistics": 1},
}

# Чувствительность стран ВЭД к факторам
COUNTRY_EXPOSURE = {
    "КИТАЙ": {"currency": 3, "logistics": 3, "sanctions": 2},
    "ТУРЦИЯ": {"currency": 2, "logistics": 2, "sanctions": 1},
    "ИНДИЯ": {"currency": 2, "logistics": 2, "sanctions": 1},
    "ОАЭ": {"currency": 2, "logistics": 2, "sanctions": 2},
    "ГОНКОНГ": {"currency": 2, "logistics": 2, "sanctions": 2},
    "ЮЖНАЯ КОРЕЯ": {"currency": 2, "logistics": 2, "sanctions": 1},
    "УЗБЕКИСТАН": {"currency": 1, "logistics": 2},
    "КАЗАХСТАН": {"currency": 1, "logistics": 2},
    "БЕЛАРУСЬ": {"currency": 1, "logistics": 2, "sanctions": 1},
}

# Модификатор по стадии развития
ECO_MARK_MODIFIER = {
    "Оптимизация": {"key_rate": 1.2, "lending": 1.2, "inflation": 1.1},
    "Стремительный рост": {"key_rate": 1.3, "lending": 1.3, "gdp": 1.2},
    "Рождение": {"key_rate": 1.1, "lending": 1.1},
    "Бизнес в новой реальности": {"sanctions": 1.2, "currency": 1.2, "logistics": 1.2},
}


@dataclass
class CompanyProfile:
    """Профиль компании в три слоя."""

    company_id: str
    observed: dict[str, Any] = field(default_factory=dict)
    declared: dict[str, Any] = field(default_factory=dict)
    inferred: dict[str, Any] = field(default_factory=dict)
    exposures: dict[str, float] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CompanyProfileBuilder:
    """Строит профиль компании и экспозиции."""

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self.df: pd.DataFrame | None = None

    def load(self) -> pd.DataFrame:
        self.df = pd.read_csv(self.csv_path, sep=";", encoding="utf-8")
        return self.df

    def _okved_section(self, code) -> str:
        """Возвращает раздел ОКВЭД (букву) по коду.

        Сопоставление по диапазонам кодов ОКВЭД2:
        A - 01-03 (сельское хозяйство)
        B - 05-09 (добыча)
        C - 10-33 (обрабатывающие)
        D - 35 (энергетика)
        E - 36-39 (водоснабжение)
        F - 41-43 (строительство)
        G - 45-47 (торговля)
        H - 49-53 (транспорт)
        I - 55-56 (гостиницы)
        J - 58-63 (информация)
        K - 64-66 (финансы)
        L - 68 (недвижимость)
        M - 69-75 (профессиональная)
        N - 77-82 (административная)
        O - 84 (госуправление)
        P - 85 (образование)
        Q - 86-88 (здравоохранение)
        R - 90-93 (культура)
        S - 94-96 (прочие)
        """
        if pd.isna(code):
            return ""
        code_str = str(code).strip()
        if not code_str:
            return ""
        # Извлекаем первые 2 цифры кода
        digits = "".join(ch for ch in code_str if ch.isdigit())
        if len(digits) < 2:
            return ""
        num = int(digits[:2])
        ranges = [
            (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"),
            (36, 39, "E"), (41, 43, "F"), (45, 47, "G"), (49, 53, "H"),
            (55, 56, "I"), (58, 63, "J"), (64, 66, "K"), (68, 68, "L"),
            (69, 75, "M"), (77, 82, "N"), (84, 84, "O"), (85, 85, "P"),
            (86, 88, "Q"), (90, 93, "R"), (94, 96, "S"),
        ]
        for lo, hi, section in ranges:
            if lo <= num <= hi:
                return section
        return ""

    def _industry_exposure(self, okved_code) -> dict[str, float]:
        section = self._okved_section(okved_code)
        return dict(INDUSTRY_EXPOSURE.get(section, {}))

    def _product_exposure(self, row: pd.Series) -> dict[str, float]:
        exp: dict[str, float] = {}
        for col, factors in PRODUCT_EXPOSURE.items():
            if col in row.index and row[col] == 1:
                for factor, weight in factors.items():
                    exp[factor] = exp.get(factor, 0) + weight
        return exp

    def _country_exposure(self, fts_country) -> dict[str, float]:
        exp: dict[str, float] = {}
        if pd.isna(fts_country):
            return exp
        for country in str(fts_country).split(","):
            country = country.strip()
            for factor, weight in COUNTRY_EXPOSURE.get(country, {}).items():
                exp[factor] = exp.get(factor, 0) + weight
        return exp

    def _scale_exposure(self, revenue) -> dict[str, float]:
        """Экспозиция по масштабу (выручка).

        Непрерывная логарифмическая зависимость вместо жёстких порогов:
        - Очень крупные (>15 млрд): сильная экспозиция к ставке/санкциям/валюте
        - Крупные (>1 млрд): средняя
        - Малые: слабая
        """
        if pd.isna(revenue) or revenue <= 0:
            return {}
        import math
        # Логарифмическая шкала: log10(revenue)
        log_rev = math.log10(revenue)
        # Нормализуем: 1e6 -> ~0.2, 1e9 -> ~0.5, 1e10 -> ~0.7, 1e11 -> ~0.85
        scale = min(1.0, max(0.0, (log_rev - 6) / 5))
        return {
            "key_rate": 1.5 * scale,
            "sanctions": 1.5 * scale,
            "currency": 1.5 * scale,
        }

    def _normalize_exposures(self, exposures: dict[str, float]) -> dict[str, float]:
        """Нормализует экспозиции к [0, 1] (min-max по ненулевым факторам).

        Делает экспозиции сопоставимыми между компаниями.
        """
        values = [v for v in exposures.values() if v > 0]
        if not values:
            return exposures
        max_val = max(values)
        if max_val <= 0:
            return exposures
        return {k: round(v / max_val, 4) for k, v in exposures.items()}

    def _eco_mark_modifier(self, eco_mark) -> dict[str, float]:
        return dict(ECO_MARK_MODIFIER.get(eco_mark, {}))

    def build_profile(self, row: pd.Series) -> CompanyProfile:
        """Строит профиль одной компании."""
        company_id = str(row["SYNTHETIC_U"])

        observed = {
            "org_type": row.get("ORG_TYPE"),
            "okfs": row.get("OKFS_NAME"),
            "age": row.get("COMPANY_AGE_YEARS_GRADATION"),
            "eco_mark": row.get("ECO_MARK_LABEL"),
            "okved_code": _norm_okved(row.get("MAINOKVED_CODE")),
            "okved_name": row.get("MAINOKVED_NAME"),
            "negativemark": row.get("NEGATIVEMARK"),
            "workers_fns": row.get("AMOUNT_WORKERS_FNS_GRADATION"),
            "cl_type": row.get("CL_TYPE"),
            "revenue": row.get("REVENUE_COMPANY"),
            "group_id": row.get("GROUP_ID"),
            "city": row.get("CITY"),
            "region": row.get("REGION"),
            "fts_country": row.get("FTS_COUNTRY_NAME"),
            "products": {
                col: int(row[col]) if col in row.index and pd.notna(row[col]) else 0
                for col in [
                    "CL_PRODUCT_RKO_MARK", "CL_PRODUCT_GAR_MARK", "CL_PRODUCT_LOA_MARK",
                    "CL_PRODUCT_LEA_MARK", "CL_PRODUCT_DEP_MARK", "CL_PRODUCT_ZPP_MARK",
                    "FACTORING_MARK",
                ]
            },
        }

        exposures: dict[str, float] = {f: 0.0 for f in MACRO_FACTORS}
        # Аддитивная модель: все источники складываются
        for factor, weight in self._industry_exposure(row.get("MAINOKVED_CODE")).items():
            exposures[factor] = exposures.get(factor, 0) + weight
        for factor, weight in self._product_exposure(row).items():
            exposures[factor] = exposures.get(factor, 0) + weight
        for factor, weight in self._country_exposure(row.get("FTS_COUNTRY_NAME")).items():
            exposures[factor] = exposures.get(factor, 0) + weight
        for factor, weight in self._scale_exposure(row.get("REVENUE_COMPANY")).items():
            exposures[factor] = exposures.get(factor, 0) + weight
        # eco_mark как слагаемое (унификация с аддитивной моделью)
        for factor, weight in self._eco_mark_modifier(row.get("ECO_MARK_LABEL")).items():
            exposures[factor] = exposures.get(factor, 0) + weight

        # Нормализация экспозиций к [0, 1] (min-max по известным факторам)
        exposures = self._normalize_exposures(exposures)

        inferred = {
            "okved_section": self._okved_section(row.get("MAINOKVED_CODE")),
            "has_fts": bool(row.get("FTS_FLAG") == 1) if pd.notna(row.get("FTS_FLAG")) else False,
            "is_large": bool(row.get("REVENUE_COMPANY", 0) > 15_000_000_000)
            if pd.notna(row.get("REVENUE_COMPANY")) else False,
        }

        # Confidence: полнота данных, влияющих на экспозиции
        confidence = 1.0
        if pd.isna(row.get("MAINOKVED_CODE")):
            confidence -= 0.2  # нет отрасли — экспозиции неполные
        if pd.isna(row.get("FTS_COUNTRY_NAME")):
            confidence -= 0.1
        if pd.isna(row.get("ECO_MARK_LABEL")):
            confidence -= 0.1
        if pd.isna(row.get("REVENUE_COMPANY")):
            confidence -= 0.2
        # Если нет ни одного продукта и нет ВЭД — экспозиции слабые
        has_products = any(
            row.get(col, 0) == 1
            for col in ["CL_PRODUCT_LOA_MARK", "CL_PRODUCT_LEA_MARK", "CL_PRODUCT_DEP_MARK"]
        )
        if not has_products and pd.isna(row.get("FTS_COUNTRY_NAME")):
            confidence -= 0.1
        confidence = max(0.1, round(confidence, 2))

        return CompanyProfile(
            company_id=company_id,
            observed=observed,
            inferred=inferred,
            exposures=exposures,
            confidence=confidence,
        )

    def build_all(self, limit: int | None = None) -> list[CompanyProfile]:
        if self.df is None:
            self.load()
        df = self.df
        if limit:
            df = df.head(limit)
        return [self.build_profile(row) for _, row in df.iterrows()]

    def save_json(self, profiles: list[CompanyProfile], out_path: str | Path) -> Path:
        """Сохраняет профили в JSON (для передачи между модулями)."""
        out = Path(out_path)
        data = {
            "module": "company_profile",
            "version": "1.0",
            "count": len(profiles),
            "macro_factors": MACRO_FACTORS,
            "profiles": [p.to_dict() for p in profiles],
        }
        # NaN не валиден в JSON — рекурсивно очищаем
        clean_data = _clean_nan(data)
        out.write_text(
            json.dumps(clean_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out


def _clean_nan(obj: Any) -> Any:
    """Рекурсивно заменяет NaN/Infinity на None для JSON-совместимости."""
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj


def _norm_okved(code) -> str:
    """Нормализует код ОКВЭД в строку (46.51 → '46.51')."""
    if pd.isna(code):
        return ""
    return str(code).strip()


def build_profiles(
    csv_path: str | Path,
    out_path: str | Path,
    limit: int | None = None,
) -> list[CompanyProfile]:
    """Удобная функция: строит профили и сохраняет в JSON."""
    builder = CompanyProfileBuilder(csv_path)
    profiles = builder.build_all(limit=limit)
    builder.save_json(profiles, out_path)
    return profiles


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Использование: python profile.py <csv_path> <out_path> [limit]")
        sys.exit(1)
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    build_profiles(sys.argv[1], sys.argv[2], limit)