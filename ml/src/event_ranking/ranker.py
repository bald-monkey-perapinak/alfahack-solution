"""Модуль 4: Ранжирование событий под запрос пользователя.

Принимает воздействие событий на компании (модуль 3) + профиль пользователя
(роль, отрасль, задачи) и считает скоринг: релевантность × материальность ×
срочность × соответствие роли. Ранжирует события для конкретного пользователя.

Вход: JSON с воздействием (модуль 3) + профиль пользователя (JSON).
Выход: JSON с ранжированным списком событий и объяснением.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Роли пользователей и их приоритеты факторов
# Значения: вес фактора для роли (0..1)
ROLE_FACTOR_WEIGHTS: dict[str, dict[str, float]] = {
    "cfo": {
        "key_rate": 1.0, "lending": 1.0, "bonds": 0.8, "inflation": 0.8,
        "currency": 0.7, "gdp": 0.5, "consumption": 0.4,
    },
    "ceo": {
        "gdp": 1.0, "consumption": 0.8, "sanctions": 0.8, "commodities": 0.7,
        "key_rate": 0.6, "inflation": 0.6, "logistics": 0.6,
    },
    "treasurer": {
        "key_rate": 1.0, "lending": 1.0, "currency": 0.9, "bonds": 0.8,
        "inflation": 0.6, "logistics": 0.5,
    },
    "chief_accountant": {
        "inflation": 0.8, "key_rate": 0.7, "currency": 0.5,
        "gdp": 0.4, "lending": 0.4,
    },
    "owner": {
        "gdp": 0.9, "sanctions": 0.8, "commodities": 0.8, "consumption": 0.7,
        "key_rate": 0.7, "inflation": 0.7, "logistics": 0.6,
    },
    "default": {
        "key_rate": 0.7, "inflation": 0.7, "gdp": 0.6, "consumption": 0.6,
        "sanctions": 0.6, "currency": 0.5, "lending": 0.5,
    },
}

# Веса компонентов скоринга
WEIGHTS = {
    "relevance": 0.4,     # релевантность (воздействие на компанию)
    "materiality": 0.3,   # материальность (масштаб воздействия)
    "urgency": 0.2,       # срочность (горизонт)
    "role_fit": 0.1,      # соответствие роли
}

# Горизонт -> вес срочности
HORIZON_URGENCY = {
    "immediate": 1.0,   # немедленно
    "week": 0.8,        # неделя
    "month": 0.6,       # месяц
    "quarter": 0.4,     # квартал
    "year": 0.2,        # год
}


@dataclass
class UserProfile:
    """Профиль пользователя (персоны)."""

    user_id: str
    role: str = "default"          # cfo, ceo, treasurer, chief_accountant, owner
    industry: str = ""             # отрасль интереса
    tasks: list[str] = field(default_factory=list)  # задачи
    company_ids: list[str] = field(default_factory=list)  # компании пользователя
    horizon: str = "quarter"       # горизонт планирования

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RankedEvent:
    """Ранжированное событие для пользователя."""

    event_id: str
    company_id: str
    score: float
    components: dict[str, float]   # вклад каждого компонента
    impact: float                  # воздействие на компанию
    explanation: list[str]         # объяснение (для трассируемости)
    factor_impacts: dict[str, float] = field(default_factory=dict)  # вклад по факторам
    top_paths: list[dict] = field(default_factory=list)  # пути вклада

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventRanker:
    """Ранжирует события для конкретного пользователя."""

    def __init__(self, weights: dict | None = None):
        self.weights = weights or WEIGHTS

    def _role_weights(self, role: str) -> dict[str, float]:
        return ROLE_FACTOR_WEIGHTS.get(role, ROLE_FACTOR_WEIGHTS["default"])

    def _relevance(self, impact: float) -> float:
        """Релевантность: нормализованное воздействие на компанию.

        Использует tanh (согласовано с propagator), impact -> [0, 1].
        """
        import math
        return abs(math.tanh(impact))

    def _materiality(self, impact: float) -> float:
        """Материальность: масштаб воздействия.

        Использует tanh (согласовано с propagator). Не дублирует relevance:
        relevance — направление+величина, materiality — только величина.
        """
        import math
        return abs(math.tanh(impact))

    def _urgency(self, horizon: str) -> float:
        """Срочность: вес по горизонту."""
        return HORIZON_URGENCY.get(horizon, 0.4)

    def _role_fit(
        self, factor_impacts: dict[str, float], role: str
    ) -> float:
        """Соответствие роли: взвешенное по величине вклада.

        Факторы с большим вкладом учитываются сильнее.
        """
        role_weights = self._role_weights(role)
        if not factor_impacts:
            return 0.0
        total_weight = 0.0
        total_impact = 0.0
        for factor, impact in factor_impacts.items():
            if abs(impact) > 0:
                total_weight += role_weights.get(factor, 0.0) * abs(impact)
                total_impact += abs(impact)
        return total_weight / total_impact if total_impact else 0.0

    def score_event(
        self,
        impact: dict,
        user: UserProfile,
        horizon: str = "quarter",
    ) -> RankedEvent:
        """Считает скоринг одного события для пользователя.

        Скоринг: взвешенная сумма + нелинейные взаимодействия.
        Высокая срочность усиливает материальность (мультипликативный бонус).
        """
        total_impact = impact.get("total_impact", 0.0)
        factor_impacts = impact.get("factor_impacts", {})

        relevance = self._relevance(total_impact)
        materiality = self._materiality(total_impact)
        urgency = self._urgency(horizon)
        role_fit = self._role_fit(factor_impacts, user.role)

        # Базовая взвешенная сумма
        score = (
            self.weights["relevance"] * relevance
            + self.weights["materiality"] * materiality
            + self.weights["urgency"] * urgency
            + self.weights["role_fit"] * role_fit
        )

        # Нелинейное взаимодействие: срочность усиливает материальность
        # (важное И срочное событие поднимается выше суммы отдельных вкладов)
        interaction = 0.1 * materiality * urgency
        score += interaction

        # Объяснение
        explanation = []
        if relevance > 0.5:
            explanation.append(f"Высокая релевантность: воздействие {total_impact:.2f}")
        if materiality > 0.5:
            explanation.append(f"Высокая материальность: {materiality:.2f}")
        if role_fit > 0.5:
            explanation.append(f"Соответствует роли {user.role}: {role_fit:.2f}")
        if interaction > 0.05:
            explanation.append("Срочное и материальное событие (усилено)")
        if not explanation:
            explanation.append("Умеренное воздействие на компанию")

        return RankedEvent(
            event_id=impact.get("event_id", ""),
            company_id=impact.get("company_id", ""),
            score=round(score, 4),
            components={
                "relevance": round(relevance, 4),
                "materiality": round(materiality, 4),
                "urgency": round(urgency, 4),
                "role_fit": round(role_fit, 4),
            },
            impact=total_impact,
            explanation=explanation,
            factor_impacts=factor_impacts,
            top_paths=impact.get("top_paths", []),
        )

    def rank_events(
        self,
        impacts: list[dict],
        user: UserProfile,
        top_n: int = 10,
    ) -> list[RankedEvent]:
        """Ранжирует все события для пользователя, возвращает топ-N."""
        ranked = [
            self.score_event(impact, user)
            for impact in impacts
            if not user.company_ids or impact.get("company_id") in user.company_ids
        ]
        ranked.sort(key=lambda r: r.score, reverse=True)
        return ranked[:top_n]

    def save_json(
        self, ranked: list[RankedEvent], out_path: str | Path
    ) -> Path:
        """Сохраняет ранжированный список в JSON."""
        out = Path(out_path)
        data = {
            "module": "event_ranking",
            "version": "1.0",
            "count": len(ranked),
            "ranked_events": [r.to_dict() for r in ranked],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def rank_for_user(
    impacts_json: str | Path,
    user: UserProfile,
    out_path: str | Path,
    top_n: int = 10,
) -> list[RankedEvent]:
    """Удобная функция: читает воздействие (модуль 3), ранжирует для пользователя."""
    data = json.loads(Path(impacts_json).read_text(encoding="utf-8"))
    impacts = data.get("impacts", [])
    ranker = EventRanker()
    ranked = ranker.rank_events(impacts, user, top_n=top_n)
    ranker.save_json(ranked, out_path)
    return ranked


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print(
            "Использование: python ranker.py <impacts_json> <user_json> <out_path> [top_n]"
        )
        sys.exit(1)
    user_data = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    user = UserProfile(**user_data)
    top_n = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    rank_for_user(sys.argv[1], user, sys.argv[3], top_n)
    print("Ранжирование выполнено.")