"""Модуль 7: Оркестратор (супервайзер на LangGraph).

Связывает все модули в агентную систему. Принимает событие + профиль
пользователя, вызывает модули по цепочке и управляет состоянием.

Поток: событие → профиль → воздействие → ранжирование → аналитик → верификатор.

Каждый шаг логируется (для трассируемости). Данные между модулями в JSON.

ВАЖНО: LangGraph используется для графа управления. LLM-вызовы абстрагированы
(сейчас заглушка). Реальный провайдер подключается позже.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable


# Добавляем src в путь (для запуска из любого места)
SRC = Path(__file__).resolve().parent.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Импортируем модули
from company_profile.profile import CompanyProfileBuilder
from shock_propagation.propagator import ShockPropagator, Shock
from event_ranking.ranker import EventRanker, UserProfile
from insight_generator.analyst import InsightGenerator
from verifier.verifier import InsightVerifier


@dataclass
class PipelineState:
    """Состояние пайплайна (передаётся между узлами LangGraph)."""

    event: dict = field(default_factory=dict)
    user: dict = field(default_factory=dict)
    profiles: list[dict] = field(default_factory=list)
    impacts: list[dict] = field(default_factory=list)
    ranked: list[dict] = field(default_factory=list)
    insights: list[dict] = field(default_factory=list)
    verification: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)  # журнал шагов
    error: str = ""

    def log(self, step: str, data: Any = None):
        """Логирует шаг (для трассируемости)."""
        self.trace.append({"step": step, "data": data})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineOrchestrator:
    """Оркестратор пайплайна на LangGraph."""

    def __init__(
        self,
        csv_path: str | Path,
        llm_client: Any = None,
    ):
        self.csv_path = Path(csv_path)
        self.profile_builder = CompanyProfileBuilder(csv_path)
        self.propagator = ShockPropagator()
        self.ranker = EventRanker()
        self.analyst = InsightGenerator(llm_client)
        self.verifier = InsightVerifier()
        self.graph = self._build_graph()

    def _build_graph(self):
        # Own sequential runner: orchestration does not depend on an agent framework.
        return self

    def invoke(self, state):
        for node in (self._node_build_profiles, self._node_propagate, self._node_rank):
            node(state)
            if state.error:
                return state.to_dict()
        if self._route_after_rank(state) == "generate":
            self._node_generate_insights(state)
            self._node_verify(state)
        return state.to_dict()

    def _route_after_rank(self, state: PipelineState) -> str:
        """Маршрутизация после ранжирования."""
        if not state.ranked:
            state.log("skip_insights", {"reason": "no ranked events"})
            return "end"
        return "generate"

    def _node_build_profiles(self, state: PipelineState) -> dict:
        """Узел: строит профили компаний."""
        state.log("build_profiles")
        try:
            profiles = self.profile_builder.build_all()
            state.profiles = [p.to_dict() for p in profiles]
        except Exception as e:
            state.error = f"build_profiles: {e}"
            state.log("error", {"step": "build_profiles", "error": str(e)})
        return {"profiles": state.profiles, "trace": state.trace, "error": state.error}

    def _node_propagate(self, state: PipelineState) -> dict:
        """Узел: распространяет шоки события."""
        state.log("propagate")
        try:
            # Извлекаем шоки из события
            shocks = []
            for s in state.event.get("shocks", []):
                shocks.append(
                    Shock(
                        factor=s.get("factor", ""),
                        direction=s.get("direction", 0.0),
                        magnitude=s.get("magnitude", 0.0),
                        horizon=s.get("horizon", "quarter"),
                        source=s.get("source", "event"),
                    )
                )
            impacts = self.propagator.impact_on_all_companies(state.profiles, shocks)
            state.impacts = [i.to_dict() for i in impacts]
        except Exception as e:
            state.error = f"propagate: {e}"
            state.log("error", {"step": "propagate", "error": str(e)})
        return {"impacts": state.impacts, "trace": state.trace, "error": state.error}

    def _node_rank(self, state: PipelineState) -> dict:
        """Узел: ранжирует события для пользователя."""
        state.log("rank")
        try:
            user = UserProfile(**state.user)
            ranked = self.ranker.rank_events(state.impacts, user, top_n=10)
            state.ranked = [r.to_dict() for r in ranked]
        except Exception as e:
            state.error = f"rank: {e}"
            state.log("error", {"step": "rank", "error": str(e)})
        return {"ranked": state.ranked, "trace": state.trace, "error": state.error}

    def _node_generate_insights(self, state: PipelineState) -> dict:
        """Узел: генерирует инсайты."""
        state.log("generate_insights")
        insights = self.analyst.generate_for_ranked(
            state.ranked, state.profiles, state.user, state.event
        )
        state.insights = [i.to_dict() for i in insights]
        return {"insights": state.insights, "trace": state.trace}

    def _node_verify(self, state: PipelineState) -> dict:
        """Узел: верифицирует инсайты."""
        state.log("verify")
        results = self.verifier.verify_all(state.insights)
        state.verification = [r.to_dict() for r in results]
        return {"verification": state.verification, "trace": state.trace}

    def run(self, event: dict, user: dict) -> PipelineState:
        """Запускает пайплайн."""
        initial = PipelineState(event=event, user=user)
        result = self.graph.invoke(initial)
        # LangGraph возвращает dict — конвертируем обратно в PipelineState
        if isinstance(result, dict):
            state = PipelineState(**result)
        else:
            state = result
        return state

    def save_json(self, state: PipelineState, out_path: str | Path) -> Path:
        """Сохраняет результат пайплайна в JSON."""
        out = Path(out_path)
        out.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out


def run_pipeline(
    csv_path: str | Path,
    event: dict,
    user: dict,
    out_path: str | Path,
) -> PipelineState:
    """Удобная функция: запускает полный пайплайн."""
    orchestrator = PipelineOrchestrator(csv_path)
    state = orchestrator.run(event, user)
    orchestrator.save_json(state, out_path)
    return state


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print(
            "Использование: python orchestrator.py <csv_path> <event_json> <user_json> <out_path>"
        )
        sys.exit(1)
    event = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    user = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    run_pipeline(sys.argv[1], event, user, sys.argv[4])
    print("Пайплайн выполнен.")