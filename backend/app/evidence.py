"""Corpus retrieval and explicit limits for personalized causal explanations."""

import re
from dataclasses import dataclass, field
from datetime import timedelta

ROLE_FOCUS = {
    "cfo": ("долговая нагрузка и денежный поток", "Проверить стоимость финансирования и сценарий денежного потока"),
    "ceo": ("стратегия, спрос и операционная устойчивость", "Проверить влияние на стратегические планы и ключевые операции"),
    "treasurer": ("ликвидность, валюта и сроки платежей", "Проверить ликвидность, валютную позицию и календарь платежей"),
    "chief_accountant": ("учёт, налоги и регуляторные обязанности", "Проверить применимость изменений к учёту и отчётности"),
    "owner": ("устойчивость бизнеса и долгосрочные решения", "Оценить влияние на устойчивость и инвестиционные планы"),
    "other_executive": ("приоритеты руководителя и ключевые процессы", "Проверить влияние на приоритеты и ключевые процессы компании"),
}

_STOP = {"демонстрация", "компания", "компании", "новость", "рынка", "россии", "рост", "снижение"}
_FACTOR_QUERIES = {
    "key_rate": "ключевая ставка кредит стоимость заимствований",
    "inflation": "инфляция цены издержки",
    "consumption": "потребление спрос продажи",
    "gdp": "ВВП экономика рост",
    "labor_market": "рынок труда зарплаты занятость",
    "bonds": "облигации доходность долговой рынок",
    "gold": "золото драгоценные металлы",
    "commodities": "сырье товары commodity цены",
    "currency": "валюта курс валютный рынок",
    "sanctions": "санкции ограничения экспорт импорт",
    "logistics": "логистика перевозки транспорт доставка",
    "real_estate": "недвижимость строительство аренда",
    "lending": "кредитование займы финансирование",
}


def role_focus(role):
    return ROLE_FOCUS.get(role, ROLE_FOCUS["owner"])


def _query_terms(title, factors):
    words = [w for w in re.findall(r"[а-яёa-z]{4,}", title.lower()) if w not in _STOP]
    words += [f.replace("_", " ") for f in factors]
    return " OR ".join(dict.fromkeys(words[:8]))


def retrieve_perspectives(db, material, shocks, *, search_text=None, limit=6):
    """Search the indexed corpus; label relation, never infer shared causality."""
    factors = {s["factor"]: s["direction"] for s in shocks}
    query = _query_terms(search_text or material["title"], factors)
    if not query or material.get("published_at") is None:
        return []
    published = material["published_at"]
    rows = db.all(
        """SELECT p.material_id,p.ordinal,p.body AS quote,m.title,m.source_ref,
                  m.published_at,m.analysis_data,s.name AS source_name,
                  ts_rank_cd(p.search_vector, websearch_to_tsquery('russian', %s))
                    + CASE WHEN m.event_id=%s THEN 1.0 ELSE 0 END AS text_score
           FROM material_passages p
           JOIN materials m ON m.id=p.material_id
           JOIN sources s ON s.id=m.source_id
           WHERE m.id<>%s AND m.material_type='news' AND m.processing_status='ready'
             AND m.is_demo=%s AND m.published_at BETWEEN %s AND %s
             AND (p.search_vector @@ websearch_to_tsquery('russian', %s)
                  OR m.event_id=%s)
           ORDER BY text_score DESC,m.published_at DESC,p.id DESC LIMIT 60""",
        (
            query, material.get("event_id"), material["id"], material["is_demo"], published - timedelta(days=365),
            published + timedelta(days=7), query, material.get("event_id"),
        ),
    )
    candidates = []
    seen_materials = set()
    for row in rows:
        if row["material_id"] in seen_materials:
            continue
        other = {s["factor"]: s["direction"] for s in row["analysis_data"].get("shocks", [])}
        common = factors.keys() & other.keys()
        if not common:
            kind = "context"
        elif any(factors[f] * other[f] < 0 for f in common):
            # Opposing reported signals may describe different dates or measures.
            kind = "opposing_signal"
        else:
            kind = "same_direction"
        candidates.append(
            {
                "material_id": row["material_id"],
                "title": row["title"],
                "quote": row["quote"][:1800],
                "source_name": row["source_name"],
                "source_ref": row["source_ref"],
                "published_at": row["published_at"].isoformat(),
                "kind": kind,
                "shared_factors": sorted(common),
                "score": round(float(row["text_score"]), 4),
            }
        )
        seen_materials.add(row["material_id"])
    chosen = []
    used_sources = set()
    for item in candidates:
        if item["source_name"] not in used_sources:
            chosen.append(item)
            used_sources.add(item["source_name"])
        if len(chosen) >= limit:
            return chosen
    chosen_ids = {item["material_id"] for item in chosen}
    chosen.extend(item for item in candidates if item["material_id"] not in chosen_ids)
    return chosen[:limit]


@dataclass
class EvidenceState:
    bank: list[dict] = field(default_factory=list)
    perspectives: list[dict] = field(default_factory=list)
    searches: list[dict] = field(default_factory=list)


class EvidenceOrchestrator:
    """Bounded, traceable retrieval graph from the original pipeline design."""

    def __init__(self, db, bank_search):
        self.db = db
        self.bank_search = bank_search

    def run(self, material, shocks, factors):
        state = EvidenceState()
        factor_query = " ".join(_FACTOR_QUERIES.get(factor, factor.replace("_", " ")) for factor in factors)
        queries = [
            ("title", material["title"]),
            ("body", material["body"][:500]),
            ("factors", factor_query or material["title"]),
        ]
        for index, (mode, query) in enumerate(queries):
            independent_sources = len({p["source_name"] for p in state.perspectives})
            opposing = any(p["kind"] == "opposing_signal" for p in state.perspectives)
            if index == 1 and state.bank and independent_sources >= 2 and not opposing:
                break
            if index == 2 and state.bank and independent_sources >= 2 and not opposing:
                break

            bank_found = self.bank_search(self.db, query, factors, material["published_at"])
            bank_by_id = {item["material_id"]: item for item in state.bank}
            bank_by_id.update({item["material_id"]: item for item in bank_found})
            state.bank = list(bank_by_id.values())[:2]

            found = retrieve_perspectives(self.db, material, shocks, search_text=query)
            by_id = {p["material_id"]: p for p in state.perspectives}
            by_id.update({p["material_id"]: p for p in found})
            state.perspectives = list(by_id.values())[:6]
            state.searches.append(
                {
                    "query_mode": mode,
                    "reason": (
                        "initial_search"
                        if index == 0
                        else "insufficient_independent_sources_or_bank_evidence"
                        if not state.bank or len({p["source_name"] for p in state.perspectives}) < 2
                        else "opposing_signals_require_targeted_search"
                        if any(p["kind"] == "opposing_signal" for p in state.perspectives)
                        else "coverage_sufficient"
                    ),
                    "bank_ids": [b["material_id"] for b in state.bank],
                    "news_ids": [p["material_id"] for p in state.perspectives],
                    "independent_sources": len({p["source_name"] for p in state.perspectives}),
                    "opposing_signals": sum(p["kind"] == "opposing_signal" for p in state.perspectives),
                }
            )
        return state


def causal_paths(shocks, ranked_paths, material_id):
    """Factor propagation is an inferred mechanism, not an observed business loss."""
    by_factor = {s["factor"]: s for s in shocks}
    result = []
    for path in ranked_paths[:5]:
        nodes = path.get("path", [])
        if not nodes or nodes[0] not in by_factor:
            continue
        result.append(
            {
                "event_factor": nodes[0],
                "factor_path": nodes,
                "source_material_id": material_id,
                "reported_change": by_factor[nodes[0]],
                "business_effect": "hypothesis",
                "basis": "heuristic_factor_graph",
                "limitation": "Направление и величина финансового эффекта требуют данных о договорах и операциях.",
            }
        )
    return result


_CAUSAL_VERB = re.compile(r"\b(?:привел[аои]?\s+к|приводит\s+к|вызвал[аои]?|вызывает)\b", re.I)


def reported_causal_relations(material_id, text):
    """Extract only explicit source assertions; they are not verified causal facts."""
    result = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        match = _CAUSAL_VERB.search(sentence)
        if match and 20 <= len(sentence) <= 500 and len(sentence[:match.start()].strip()) >= 8:
            result.append(
                {
                    "material_id": material_id,
                    "quote": sentence,
                    "status": "reported_by_source",
                }
            )
        if len(result) == 4:
            break
    return result


def corpus_overview(db, material, factors):
    """A cheap corpus-wide thematic view, separate from query-selected passages."""
    if material.get("published_at") is None or not factors:
        return {"factor_counts": {}, "source_count": 0}
    rows = db.all(
        """SELECT shock->>'factor' AS factor, count(DISTINCT m.id) AS articles,
                  array_agg(DISTINCT m.source_id) AS source_ids
           FROM materials m
           CROSS JOIN LATERAL jsonb_array_elements(
               CASE WHEN jsonb_typeof(m.analysis_data->'shocks')='array'
                    THEN m.analysis_data->'shocks' ELSE '[]'::jsonb END
           ) shock
           WHERE m.material_type='news' AND m.processing_status='ready'
             AND m.is_demo=%s AND m.published_at BETWEEN %s AND %s
             AND shock->>'factor'=ANY(%s)
           GROUP BY shock->>'factor'""",
        (
            material["is_demo"], material["published_at"] - timedelta(days=365),
            material["published_at"] + timedelta(days=7), list(factors),
        ),
    )
    return {
        "factor_counts": {row["factor"]: int(row["articles"]) for row in rows},
        "source_count": len({source for row in rows for source in row["source_ids"]}),
        "window": "365 days before to 7 days after event publication",
    }


def evidence_coverage(material, perspectives, bank):
    return {
        "primary_material_id": material["id"],
        "additional_news": len(perspectives),
        "independent_sources": len({p["source_name"] for p in perspectives}),
        "bank_materials": len(bank),
        "opposing_signals": sum(p["kind"] == "opposing_signal" for p in perspectives),
        "sufficient_for_causal_claim": False,
    }
