"""Модуль 3: Граф факторов и распространение шоков.

Ядро скоринга. Строит граф макрофакторов (13 узлов), принимает событие как
вектор шоков, распространяет шоки по графу (глубина 2-3, затухание, лаги)
и проецирует результат на компанию через её экспозиции (из модуля 2).

Вход: JSON с профилями компаний (модуль 2) + событие (JSON).
Выход: JSON с воздействием на компании и путями вклада.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Макрофакторы (должны совпадать с модулем 2)
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

# Граф факторов: направленные рёбра (source -> target) со знаком и силой.
# Знак: +1 (усиливает), -1 (ослабляет). Сила: 0..1.
# Источник: макроэкономическая логика (ставка -> кредитование, инфляция -> потребление и т.д.)
FACTOR_GRAPH: dict[str, dict[str, dict[str, float]]] = {
    "key_rate": {
        "lending": {"sign": -1.0, "strength": 0.8},   # рост ставки -> дороже кредиты
        "bonds": {"sign": -1.0, "strength": 0.7},     # рост ставки -> падение облигаций
        "inflation": {"sign": -1.0, "strength": 0.5}, # рост ставки -> сдерживание инфляции
        "consumption": {"sign": -1.0, "strength": 0.4}, # рост ставки -> меньше потребление
        "real_estate": {"sign": -1.0, "strength": 0.5}, # рост ставки -> дороже ипотека
        "currency": {"sign": 1.0, "strength": 0.4},   # рост ставки -> укрепление валюты
    },
    "inflation": {
        "consumption": {"sign": -1.0, "strength": 0.6}, # инфляция -> меньше потребление
        "key_rate": {"sign": 1.0, "strength": 0.7},   # инфляция -> ЦБ поднимает ставку
        "gdp": {"sign": -1.0, "strength": 0.4},       # инфляция -> тормозит ВВП
        "real_estate": {"sign": 1.0, "strength": 0.3}, # инфляция -> рост цен на недвижимость
    },
    "consumption": {
        "gdp": {"sign": 1.0, "strength": 0.7},        # потребление -> ВВП
        "inflation": {"sign": 1.0, "strength": 0.4},  # потребление -> инфляция
    },
    "gdp": {
        "consumption": {"sign": 1.0, "strength": 0.5},
        "labor_market": {"sign": 1.0, "strength": 0.6}, # ВВП -> занятость
    },
    "labor_market": {
        "consumption": {"sign": 1.0, "strength": 0.5}, # занятость -> потребление
        "inflation": {"sign": 1.0, "strength": 0.3},  # зарплаты -> инфляция
    },
    "bonds": {
        "key_rate": {"sign": -1.0, "strength": 0.6},  # падение облигаций -> ставка
        "lending": {"sign": 1.0, "strength": 0.4},    # доходность облигаций -> кредиты
    },
    "gold": {
        "currency": {"sign": -1.0, "strength": 0.3},  # золото -> слабее валюта
        "inflation": {"sign": 1.0, "strength": 0.4},  # золото -> инфляционные ожидания
    },
    "commodities": {
        "inflation": {"sign": 1.0, "strength": 0.6},  # сырьё -> инфляция
        "currency": {"sign": 1.0, "strength": 0.5},   # сырьё -> курс
        "logistics": {"sign": 1.0, "strength": 0.3},
    },
    "currency": {
        "inflation": {"sign": 1.0, "strength": 0.5},  # слабая валюта -> инфляция
        "logistics": {"sign": 1.0, "strength": 0.4},  # курс -> стоимость импорта
        "commodities": {"sign": 1.0, "strength": 0.3},
    },
    "sanctions": {
        "logistics": {"sign": -1.0, "strength": 0.8}, # санкции -> логистика хуже
        "currency": {"sign": -1.0, "strength": 0.6},  # санкции -> слабее валюта
        "inflation": {"sign": 1.0, "strength": 0.5},  # санкции -> инфляция
        "commodities": {"sign": -1.0, "strength": 0.4},
    },
    "logistics": {
        "inflation": {"sign": 1.0, "strength": 0.5},  # логистика дороже -> инфляция
        "consumption": {"sign": -1.0, "strength": 0.3},
    },
    "real_estate": {
        "consumption": {"sign": 1.0, "strength": 0.3},
        "inflation": {"sign": 1.0, "strength": 0.3},
    },
    "lending": {
        "consumption": {"sign": 1.0, "strength": 0.4}, # кредиты -> потребление
        "gdp": {"sign": 1.0, "strength": 0.4},        # кредиты -> ВВП
        "real_estate": {"sign": 1.0, "strength": 0.5}, # кредиты -> недвижимость
    },
}

# Параметры распространения
MAX_DEPTH = 3          # максимальная глубина распространения
DECAY = 0.5            # затухание на каждом шаге
MIN_IMPACT = 0.05      # минимальный вклад, ниже которого игнорируем


@dataclass
class Shock:
    """Шок по фактору от события."""

    factor: str
    direction: float  # +1 (вверх), -1 (вниз), 0 (нейтрально)
    magnitude: float  # 0..1 (величина)
    horizon: str = "quarter"  # горизонт эффекта
    source: str = "event"     # происхождение

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImpactPath:
    """Путь вклада (для объяснимости)."""

    path: list[str]          # цепочка факторов: ["key_rate", "lending"]
    impact: float            # накопленный вклад
    sign: float              # знак влияния
    depth: int               # глубина пути

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CompanyImpact:
    """Воздействие события на компанию."""

    company_id: str
    total_impact: float          # суммарное воздействие
    factor_impacts: dict[str, float]  # вклад по каждому фактору
    top_paths: list[ImpactPath]  # топ-пути вклада
    confidence: float            # уверенность

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "total_impact": self.total_impact,
            "factor_impacts": self.factor_impacts,
            "top_paths": [p.to_dict() for p in self.top_paths],
            "confidence": self.confidence,
        }


class ShockPropagator:
    """Распространяет шоки по графу факторов и проецирует на компании."""

    def __init__(
        self,
        factor_graph: dict | None = None,
        max_depth: int = MAX_DEPTH,
        decay: float = DECAY,
        min_impact: float = MIN_IMPACT,
    ):
        self.factor_graph = FACTOR_GRAPH if factor_graph is None else factor_graph
        self.max_depth = max_depth
        self.decay = decay
        self.min_impact = min_impact

    def _walk_paths(self, shock: Shock, max_depth: int | None = None):
        """Enumerate bounded simple paths; never feed a cycle back into its origin.

        max_depth counts graph edges; direct exposure is a zero-edge path.
        The same walker drives both totals and explanations.
        """
        from collections import deque
        depth = self.max_depth if max_depth is None else max_depth
        frontier = deque([([shock.factor], shock.direction * shock.magnitude)])
        while frontier:
            path, value = frontier.popleft()
            yield path, value
            if len(path) - 1 >= depth:
                continue
            for target, edge in self.factor_graph.get(path[-1], {}).items():
                if target in path:
                    continue
                contribution = value * edge["sign"] * edge["strength"] * self.decay
                if abs(contribution) >= self.min_impact:
                    frontier.append((path + [target], contribution))

    def propagate_shock(self, shock: Shock, max_depth: int | None = None) -> dict[str, float]:
        impacts: dict[str, float] = {}
        for path, value in self._walk_paths(shock, max_depth):
            impacts[path[-1]] = impacts.get(path[-1], 0) + value
        return impacts

    def propagate_shocks(self, shocks: list[Shock]) -> dict[str, float]:
        """Распространяет несколько шоков. Суммирует вклады по факторам."""
        total: dict[str, float] = {}
        for shock in shocks:
            impacts = self.propagate_shock(shock)
            for factor, impact in impacts.items():
                total[factor] = total.get(factor, 0) + impact
        return total

    def impact_on_company(
        self, exposures: dict[str, float], shocks: list[Shock]
    ) -> CompanyImpact:
        """Считает воздействие события на компанию через её экспозиции.

        Воздействие = сумма по факторам: экспозиция_компании * вклад_шока.
        Вклады нормализуются к [-1, 1] (tanh), чтобы масштаб был согласован
        между модулями. Confidence учитывает глубину путей и согласованность.
        """
        factor_impacts = self.propagate_shocks(shocks)
        total = 0.0
        per_factor: dict[str, float] = {}
        for factor, shock_impact in factor_impacts.items():
            exposure = exposures.get(factor, 0.0)
            contribution = exposure * shock_impact
            if abs(contribution) >= self.min_impact:
                per_factor[factor] = round(contribution, 4)
                total += contribution

        # Нормализация к [-1, 1] (tanh) — согласованный масштаб
        total_norm = self._normalize(total)

        # Топ-пути вклада (для объяснимости)
        top_paths = self._top_paths(shocks, exposures, limit=5)

        # Confidence: учитывает глубину путей и согласованность знаков
        confidence = self._compute_confidence(shocks, top_paths)

        return CompanyImpact(
            company_id="",
            total_impact=round(total_norm, 4),
            factor_impacts=per_factor,
            top_paths=top_paths,
            confidence=confidence,
        )

    def _normalize(self, value: float) -> float:
        """Нормализует значение к [-1, 1] через tanh."""
        import math
        return math.tanh(value)

    def _compute_confidence(
        self, shocks: list[Shock], top_paths: list[ImpactPath]
    ) -> float:
        """Считает уверенность на основе глубины путей и согласованности.

        - Глубина 1 (прямые пути) -> высокая уверенность
        - Глубина 2-3 (косвенные) -> ниже
        - Противоположные знаки путей -> ниже (неопределённость)
        """
        if not top_paths:
            return 0.5
        # Средняя глубина
        avg_depth = sum(p.depth for p in top_paths) / len(top_paths)
        depth_conf = max(0.3, 1.0 - (avg_depth - 1) * 0.2)
        # Согласованность знаков
        signs = [p.sign for p in top_paths]
        pos = sum(1 for s in signs if s > 0)
        neg = sum(1 for s in signs if s < 0)
        consistency = max(pos, neg) / len(signs) if signs else 0.5
        return round(depth_conf * consistency, 2)

    def _top_paths(self, shocks: list[Shock], exposures: dict[str, float], limit: int = 5) -> list[ImpactPath]:
        paths = []
        for shock in shocks:
            for path, value in self._walk_paths(shock):
                contribution = value * exposures.get(path[-1], 0)
                if abs(contribution) >= self.min_impact:
                    paths.append(ImpactPath(path=path, impact=round(contribution, 4),
                        sign=1.0 if contribution >= 0 else -1.0, depth=len(path)))
        paths.sort(key=lambda p: abs(p.impact), reverse=True)
        return paths[:limit]

    def impact_on_all_companies(
        self, profiles: list[dict], shocks: list[Shock]
    ) -> list[CompanyImpact]:
        """Считает воздействие на все компании из профилей."""
        results: list[CompanyImpact] = []
        for profile in profiles:
            exposures = profile.get("exposures", {})
            impact = self.impact_on_company(exposures, shocks)
            impact.company_id = profile.get("company_id", "")
            impact.confidence *= profile.get("confidence", 1.0)
            results.append(impact)
        return results

    def save_json(
        self, impacts: list[CompanyImpact], out_path: str | Path
    ) -> Path:
        """Сохраняет результаты в JSON (для передачи между модулями)."""
        out = Path(out_path)
        data = {
            "module": "shock_propagation",
            "version": "1.0",
            "count": len(impacts),
            "impacts": [i.to_dict() for i in impacts],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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


def propagate_event(
    profiles_json: str | Path,
    event: dict,
    out_path: str | Path,
) -> list[CompanyImpact]:
    """Удобная функция: читает профили (JSON), распространяет событие, сохраняет.

    Args:
        profiles_json: путь к JSON с профилями компаний (модуль 2).
        event: событие в формате JSON (с полем shocks).
        out_path: путь для JSON-результата.
    """
    # Читаем профили
    data = json.loads(Path(profiles_json).read_text(encoding="utf-8"))
    profiles = data.get("profiles", [])

    # Извлекаем шоки из события
    shocks = []
    for s in event.get("shocks", []):
        shocks.append(
            Shock(
                factor=s.get("factor", ""),
                direction=s.get("direction", 0.0),
                magnitude=s.get("magnitude", 0.0),
                horizon=s.get("horizon", "quarter"),
                source=s.get("source", "event"),
            )
        )

    propagator = ShockPropagator()
    impacts = propagator.impact_on_all_companies(profiles, shocks)
    propagator.save_json(impacts, out_path)
    return impacts


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print(
            "Использование: python propagator.py <profiles_json> <event_json> <out_path>"
        )
        sys.exit(1)
    event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    propagate_event(sys.argv[1], event, sys.argv[3])
    print("Воздействие рассчитано.")