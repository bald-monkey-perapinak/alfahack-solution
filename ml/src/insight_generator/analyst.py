"""Модуль 5: Аналитик (LLM-интерпретация события для пользователя).

Превращает ранжированное событие + профиль компании + пути вклада в
персонализированный инсайт с разделением «факт / аналитика банка / AI-вывод»
и предлагает действия (Next Best Action).

ВАЖНО: LLM-вызовы абстрагированы через интерфейс LLMClient. Сейчас используется
заглушка (StubLLMClient), которая генерирует детерминированный инсайт из
структурированных данных. Реальный LLM-провайдер подключается позже.

Вход: JSON с ранжированными событиями (модуль 4) + профиль компании + пути вклада.
Выход: JSON с инсайтами.

Данные между модулями передаются в формате JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Insight:
    """Персонализированный инсайт для пользователя."""

    insight_id: str
    event_id: str
    company_id: str
    user_id: str
    headline: str                       # заголовок-вывод
    channels: dict[str, list[dict]]     # факт / аналитика банка / AI-вывод
    why_it_matters: list[dict]          # признаки компании
    actions: list[dict]                 # Next Best Action
    confidence: float                   # уверенность
    versions: dict[str, str]            # версии графа, весов, промптов
    trace_id: str                       # идентификатор трассы
    cost_of_inaction: dict = field(default_factory=dict)  # цена бездействия

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMClient(Protocol):
    """Интерфейс LLM-клиента (абстракция над провайдером)."""

    def generate(self, prompt: str, **kwargs) -> str:
        """Генерирует текст по промпту."""
        ...


class StubLLMClient:
    """Заглушка LLM-клиента. Генерирует детерминированный инсайт из данных.

    Не вызывает реальный LLM. Используется для разработки и тестов.
    Реальный провайдер подключается позже через тот же интерфейс.
    """

    def generate(self, prompt: str, **kwargs) -> str:
        """Возвращает заглушку (не вызывает LLM)."""
        return "STUB_RESPONSE"


class InsightGenerator:
    """Генерирует инсайт из ранжированного события и профиля компании.

    Если передан реальный LLM-клиент (LLMClient), инсайт генерируется через
    внешний LLM-сервис (generate_json). При недоступности LLM или ошибке
    парсинга ответа используется детерминированный fallback (StubLLMClient).
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self.llm = llm_client or StubLLMClient()

    def _build_llm_prompt(
        self,
        event: dict,
        profile: dict,
        user: dict,
        paths: list[dict],
    ) -> str:
        """Строит промпт для LLM-генерации инсайта.

        LLM должен вернуть JSON с полями инсайта. Код валидирует ответ и
        заполняет недостающие поля из детерминированной логики.
        """
        impact = event.get("impact", event.get("total_impact", 0.0))
        role = user.get("role", "default")
        company_id = profile.get("company_id", "")
        observed = profile.get("observed", {})
        products = observed.get("products", {})
        factor_impacts = event.get("factor_impacts", {})

        # Компактное описание профиля для промпта
        profile_desc = {
            "company_id": company_id,
            "okved": observed.get("okved_name", ""),
            "region": observed.get("region", ""),
            "revenue": observed.get("revenue"),
            "products": {k: v for k, v in products.items() if v},
            "has_fts": profile.get("inferred", {}).get("has_fts", False),
        }

        # Пути вклада (для объяснимости)
        paths_desc = [
            {"path": p.get("path", []), "impact": p.get("impact", 0.0)}
            for p in paths
        ]

        prompt = f"""Ты — аналитик банка. Сгенерируй персонализированный инсайт для клиента по событию.

Событие: {event.get('title', '')} (тип: {event.get('event_type', 'событие')})
Воздействие на компанию: {impact:.2f} (положительное — возможность, отрицательное — риск)
Роль пользователя: {role}
Профиль компании: {profile_desc}
Вклад по факторам: {factor_impacts}
Пути вклада: {paths_desc}

Верни ТОЛЬКО JSON (без markdown-обёртки) со следующей структурой:
{{
  "headline": "короткий заголовок-вывод (следствие для компании, не пересказ события)",
  "channels": {{
    "fact": [{{"text": "факт из события", "source_id": "источник"}}],
    "bank_analytics": [{{"text": "аналитика банка"}}],
    "ai_conclusion": [{{"text": "AI-вывод", "refs": ["фактор1", "фактор2"]}}]
  }},
  "why_it_matters": [{{"factor": "фактор", "impact": 0.0, "origin": "observed"}}],
  "actions": [{{"type": "тип_действия", "label": "продукт банка|рекомендация AI", "rationale": "обоснование", "product_id": "ID", "priority": 1}}],
  "cost_of_inaction": {{"description": "что будет при бездействии", "severity": "low|medium|high", "timeframe": "quarter"}},
  "confidence": 0.9
}}
Не давай инвестиционных рекомендаций (не советуй покупать/продавать акции, не обещай гарантированную доходность)."""
        return prompt

    def _parse_llm_insight(
        self,
        data: dict,
        event: dict,
        profile: dict,
        user: dict,
        paths: list[dict],
        trace_id: str,
    ) -> Insight:
        """Собирает Insight из JSON-ответа LLM, заполняя недостающие поля.

        Гибридный подход: берём то, что вернул LLM, но гарантируем корректность
        обязательных полей через детерминированную логику.
        """
        impact = event.get("impact", event.get("total_impact", 0.0))
        company_id = profile.get("company_id", "")
        event_id = event.get("event_id", "")

        # Headline: из LLM или fallback
        headline = data.get("headline") or self._build_headline(event, impact, user.get("role", "default"))

        # Channels: гарантируем наличие всех трёх каналов
        channels = data.get("channels") or {}
        fact = channels.get("fact") or []
        bank = channels.get("bank_analytics") or []
        ai = channels.get("ai_conclusion") or []
        # Если LLM не вернул факт — берём из события
        if not fact and event.get("title"):
            fact = [{"text": event["title"], "source_id": event.get("event_id", "")}]
        # Если LLM не вернул AI-вывод — строим из путей вклада
        if not ai:
            ai = [
                {
                    "text": f"Вклад через факторы: {' -> '.join(p.get('path', []))}",
                    "impact": p.get("impact", 0.0),
                    "refs": p.get("path", []),
                }
                for p in paths
            ]
        channels = {"fact": fact, "bank_analytics": bank, "ai_conclusion": ai}

        # why_it_matters: из LLM или из factor_impacts
        why = data.get("why_it_matters") or []
        if not why:
            why = [
                {"factor": f, "impact": v, "origin": "observed"}
                for f, v in event.get("factor_impacts", {}).items()
                if abs(v) > 0
            ]

        # actions: из LLM или детерминированная логика
        actions = data.get("actions") or self._build_actions(event, profile, impact)

        # cost_of_inaction: из LLM или детерминированная логика
        cost = data.get("cost_of_inaction") or self._build_cost_of_inaction(event, impact)

        # confidence: из LLM (валидируем диапазон) или из профиля
        confidence = data.get("confidence", profile.get("confidence", 1.0))
        if not (0 <= confidence <= 1):
            confidence = profile.get("confidence", 1.0)

        return Insight(
            insight_id=f"ins_{event_id}_{company_id}",
            event_id=event_id,
            company_id=company_id,
            user_id=user.get("user_id", ""),
            headline=headline,
            channels=channels,
            why_it_matters=why,
            actions=actions,
            cost_of_inaction=cost,
            confidence=confidence,
            versions={
                "graph": "v1",
                "weights": "v1",
                "prompts": "v1",
                "models": getattr(self.llm, "model", "llm"),
            },
            trace_id=trace_id,
        )

    def _build_headline(
        self, event: dict, impact: float, role: str
    ) -> str:
        """Строит заголовок-вывод (следствие, а не событие)."""
        event_type = event.get("event_type", "событие")
        if impact > 0:
            direction = "возможность"
        elif impact < 0:
            direction = "риск"
        else:
            direction = "нейтрально"
        return (
            f"{event_type}: {direction} для вашей компании "
            f"(воздействие {impact:.2f})"
        )

    def _build_channels(
        self, event: dict, paths: list[dict]
    ) -> dict[str, list[dict]]:
        """Строит три канала: факт / аналитика банка / AI-вывод."""
        channels = {
            "fact": [],
            "bank_analytics": [],
            "ai_conclusion": [],
        }
        # Факт: из события
        if event.get("title"):
            source_id = event.get("event_id", "") or event.get("source_id", "")
            channels["fact"].append(
                {"text": event["title"], "source_id": source_id}
            )
        # AI-вывод: из путей вклада
        for path in paths:
            channels["ai_conclusion"].append(
                {
                    "text": f"Вклад через факторы: {' -> '.join(path['path'])}",
                    "impact": path.get("impact", 0.0),
                    "refs": path.get("path", []),
                }
            )
        # Аналитика банка: пока пусто (заполняется из ЦМИ позже)
        return channels

    def _build_actions(
        self, event: dict, profile: dict, impact: float
    ) -> list[dict]:
        """Строит Next Best Action на основе профиля компании."""
        actions = []
        products = profile.get("observed", {}).get("products", {})
        factor_impacts = event.get("factor_impacts", {})

        # Если есть кредит и затронута ставка -> фиксация ставки
        if products.get("CL_PRODUCT_LOA_MARK") and abs(factor_impacts.get("key_rate", 0)) > 0:
            actions.append(
                {
                    "type": "fix_rate",
                    "label": "продукт банка",
                    "rationale": "Рост ставки -> зафиксировать ставку по кредиту",
                    "product_id": "CL_PRODUCT_LOA_MARK",
                    "priority": 1,
                }
            )
        # Если есть ВЭД и затронута валюта -> валютный продукт
        if profile.get("inferred", {}).get("has_fts") and abs(factor_impacts.get("currency", 0)) > 0:
            actions.append(
                {
                    "type": "currency_hedge",
                    "label": "продукт банка",
                    "rationale": "Валютный риск -> хеджирование",
                    "product_id": "FTS",
                    "priority": 2,
                }
            )
        # Если есть лизинг и затронута ставка -> пересмотр лизинга
        if products.get("CL_PRODUCT_LEA_MARK") and abs(factor_impacts.get("key_rate", 0)) > 0:
            actions.append(
                {
                    "type": "review_leasing",
                    "label": "рекомендация AI",
                    "rationale": "Рост ставки -> пересмотреть условия лизинга",
                    "product_id": "CL_PRODUCT_LEA_MARK",
                    "priority": 3,
                }
            )
        # Если есть депозит и рост ставки -> открыть/увеличить депозит (возможность)
        if products.get("CL_PRODUCT_DEP_MARK") and factor_impacts.get("key_rate", 0) > 0:
            actions.append(
                {
                    "type": "open_deposit",
                    "label": "продукт банка",
                    "rationale": "Рост ставки -> выгодно разместить депозит",
                    "product_id": "CL_PRODUCT_DEP_MARK",
                    "priority": 2,
                }
            )
        # Если есть факторинг и проблемы с ликвидностью/логистикой -> факторинг
        if products.get("FACTORING_MARK") and abs(factor_impacts.get("logistics", 0)) > 0:
            actions.append(
                {
                    "type": "use_factoring",
                    "label": "продукт банка",
                    "rationale": "Логистические риски -> ускорить оборот через факторинг",
                    "product_id": "FACTORING_MARK",
                    "priority": 3,
                }
            )
        # Если есть гарантия и санкционные риски -> банковская гарантия
        if products.get("CL_PRODUCT_GAR_MARK") and abs(factor_impacts.get("sanctions", 0)) > 0:
            actions.append(
                {
                    "type": "get_guarantee",
                    "label": "продукт банка",
                    "rationale": "Санкционные риски -> обеспечить обязательства гарантией",
                    "product_id": "CL_PRODUCT_GAR_MARK",
                    "priority": 3,
                }
            )
        # Если сильный негативный шок по ставке и есть кредит -> реструктуризация
        if products.get("CL_PRODUCT_LOA_MARK") and factor_impacts.get("key_rate", 0) < -0.5:
            actions.append(
                {
                    "type": "restructure_loan",
                    "label": "рекомендация AI",
                    "rationale": "Сильный рост ставки -> рассмотреть реструктуризацию",
                    "product_id": "CL_PRODUCT_LOA_MARK",
                    "priority": 1,
                }
            )
        # Если действий нет -> мониторинг с конкретным триггером
        if not actions:
            actions.append(
                {
                    "type": "monitor",
                    "label": "рекомендация AI",
                    "rationale": "Следить за развитием ситуации по затронутым факторам",
                    "product_id": None,
                    "priority": 5,
                }
            )
        # Сортируем по приоритету
        actions.sort(key=lambda a: a.get("priority", 5))
        return actions

    def _build_cost_of_inaction(
        self, event: dict, impact: float
    ) -> dict:
        """Строит цену бездействия (что будет, если ничего не делать)."""
        if abs(impact) < 0.1:
            return {
                "description": "Влияние на компанию минимально",
                "severity": "low",
                "timeframe": "quarter",
            }
        if impact < 0:
            return {
                "description": f"Риск финансовых потерь при бездействии (воздействие {abs(impact):.2f})",
                "severity": "high" if abs(impact) > 0.5 else "medium",
                "timeframe": "quarter",
            }
        return {
            "description": f"Упущенная возможность при бездействии (воздействие {impact:.2f})",
            "severity": "medium",
            "timeframe": "quarter",
        }

    def generate_insight(
        self,
        event: dict,
        profile: dict,
        user: dict,
        paths: list[dict],
        trace_id: str = "",
    ) -> Insight:
        """Генерирует инсайт из события, профиля и путей вклада.

        Сначала пробует LLM-генерацию (если подключён реальный LLMClient).
        При недоступности LLM или ошибке парсинга ответа — fallback на
        детерминированную логику.
        """
        # Пробуем LLM-генерацию (только если это реальный клиент, не заглушка)
        if not isinstance(self.llm, StubLLMClient):
            llm_insight = self._generate_with_llm(event, profile, user, paths, trace_id)
            if llm_insight is not None:
                return llm_insight

        # Fallback: детерминированная логика
        # impact может быть в поле 'impact' (ранжирование) или 'total_impact' (воздействие)
        impact = event.get("impact", event.get("total_impact", 0.0))
        role = user.get("role", "default")

        headline = self._build_headline(event, impact, role)
        channels = self._build_channels(event, paths)
        actions = self._build_actions(event, profile, impact)

        # why_it_matters: признаки компании, которые сработали
        why_it_matters = []
        for factor, impact_val in event.get("factor_impacts", {}).items():
            if abs(impact_val) > 0:
                why_it_matters.append(
                    {
                        "factor": factor,
                        "impact": impact_val,
                        "origin": "observed",
                    }
                )

        return Insight(
            insight_id=f"ins_{event.get('event_id', '')}_{profile.get('company_id', '')}",
            event_id=event.get("event_id", ""),
            company_id=profile.get("company_id", ""),
            user_id=user.get("user_id", ""),
            headline=headline,
            channels=channels,
            why_it_matters=why_it_matters,
            actions=actions,
            cost_of_inaction=self._build_cost_of_inaction(event, impact),
            confidence=profile.get("confidence", 1.0),
            versions={
                "graph": "v1",
                "weights": "v1",
                "prompts": "v1",
                "models": "stub",
            },
            trace_id=trace_id,
        )

    def _generate_with_llm(
        self,
        event: dict,
        profile: dict,
        user: dict,
        paths: list[dict],
        trace_id: str,
    ) -> Insight | None:
        """Генерирует инсайт через LLM (generate_json). Возвращает None при неудаче."""
        try:
            prompt = self._build_llm_prompt(event, profile, user, paths)
            data = self.llm.generate_json(prompt)
            if not data or not isinstance(data, dict):
                return None
            return self._parse_llm_insight(data, event, profile, user, paths, trace_id)
        except Exception:
            # Любая ошибка LLM — fallback на детерминированную логику
            return None

    def generate_for_ranked(
        self,
        ranked_events: list[dict],
        profiles: list[dict],
        user: dict,
        source_event: dict | None = None,
        trace_id: str = "",
    ) -> list[Insight]:
        """Генерирует инсайты для ранжированных событий.

        Args:
            ranked_events: ранжированные события (модуль 4).
            profiles: профили компаний (модуль 2).
            user: профиль пользователя.
            source_event: исходное событие (с title/event_type) для заголовка.
            trace_id: идентификатор трассы.
        """
        # Строим карту профилей по company_id
        profile_map = {p.get("company_id"): p for p in profiles}
        insights = []
        for ranked in ranked_events:
            company_id = ranked.get("company_id", "")
            profile = profile_map.get(company_id, {})
            paths = ranked.get("top_paths", [])
            # Обогащаем ранжированное событие полями из исходного события
            enriched = dict(ranked)
            if source_event:
                enriched["title"] = source_event.get("title", "")
                enriched["event_type"] = source_event.get("event_type", "событие")
                # event_id из исходного события, если в ранжированном пусто
                if not enriched.get("event_id"):
                    enriched["event_id"] = source_event.get("event_id", "")
            insight = self.generate_insight(
                enriched, profile, user, paths, trace_id
            )
            insights.append(insight)
        return insights

    def save_json(self, insights: list[Insight], out_path: str | Path) -> Path:
        """Сохраняет инсайты в JSON."""
        out = Path(out_path)
        data = {
            "module": "insight_generator",
            "version": "1.0",
            "count": len(insights),
            "insights": [i.to_dict() for i in insights],
        }
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def generate_insights(
    ranked_json: str | Path,
    profiles_json: str | Path,
    user: dict,
    out_path: str | Path,
    source_event: dict | None = None,
    trace_id: str = "",
) -> list[Insight]:
    """Удобная функция: читает ранжированные события + профили, генерирует инсайты.

    Args:
        ranked_json: путь к JSON с ранжированными событиями (модуль 4).
        profiles_json: путь к JSON с профилями компаний (модуль 2).
        user: профиль пользователя (dict).
        out_path: путь для JSON-результата.
        source_event: исходное событие (с title/event_type) для заголовка.
        trace_id: идентификатор трассы.
    """
    ranked_data = json.loads(Path(ranked_json).read_text(encoding="utf-8"))
    ranked_events = ranked_data.get("ranked_events", [])

    profiles_data = json.loads(Path(profiles_json).read_text(encoding="utf-8"))
    profiles = profiles_data.get("profiles", [])

    generator = InsightGenerator()
    insights = generator.generate_for_ranked(
        ranked_events, profiles, user, source_event, trace_id
    )
    generator.save_json(insights, out_path)
    return insights


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print(
            "Использование: python analyst.py <ranked_json> <profiles_json> <user_json> <out_path> [event_json]"
        )
        sys.exit(1)
    user = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    source_event = None
    if len(sys.argv) > 5:
        source_event = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
    generate_insights(sys.argv[1], sys.argv[2], user, sys.argv[4], source_event)
    print("Инсайты сгенерированы (заглушка).")