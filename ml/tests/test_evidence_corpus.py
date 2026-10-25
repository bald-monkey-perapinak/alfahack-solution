from datetime import datetime, timezone

from backend.app.evidence import (
    EvidenceOrchestrator,
    causal_paths,
    reported_causal_relations,
    retrieve_perspectives,
    role_focus,
)


class Corpus:
    def __init__(self, rows):
        self.rows = rows
        self.searches = []

    def all(self, query, args):
        self.searches.append(args[0])
        return self.rows


def _material():
    return {
        "id": 1,
        "title": "Рост стоимости международных перевозок",
        "body": "Стоимость международных перевозок выросла. Проверка условий доставки необходима.",
        "published_at": datetime(2026, 9, 15, tzinfo=timezone.utc),
        "is_demo": False,
    }


def _row(mid, source, direction):
    return {
        "material_id": mid,
        "ordinal": 1,
        "quote": "Стоимость перевозок изменилась после публикации тарифа.",
        "title": "Сообщение о перевозках",
        "source_ref": f"https://example.test/{mid}",
        "published_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
        "analysis_data": {"shocks": [{"factor": "logistics", "direction": direction}]},
        "source_name": source,
        "text_score": 0.5,
    }


def test_retrieval_keeps_source_diversity_and_labels_opposing_signals():
    db = Corpus([_row(2, "Первое издание", 1), _row(3, "Первое издание", 1), _row(4, "Второе издание", -1)])
    found = retrieve_perspectives(db, _material(), [{"factor": "logistics", "direction": 1}], limit=2)
    assert [item["material_id"] for item in found] == [2, 4]
    assert found[1]["kind"] == "opposing_signal"
    assert found[1]["quote"] == db.rows[2]["quote"]


def test_evidence_graph_retries_when_corpus_has_one_source():
    db = Corpus([_row(2, "Первое издание", 1)])
    state = EvidenceOrchestrator(db, lambda *_: []).run(
        _material(), [{"factor": "logistics", "direction": 1}], ["logistics"]
    )
    assert [step["query_mode"] for step in state.searches] == ["title", "body"]
    assert len(db.searches) == 2
    assert [item["material_id"] for item in state.perspectives] == [2]


def test_causal_output_separates_source_assertion_from_business_hypothesis():
    text = "Рост тарифов привел к увеличению стоимости доставки."
    reported = reported_causal_relations(1, text)
    paths = causal_paths(
        [{"factor": "logistics", "direction": 1, "magnitude": 0.3}],
        [{"path": ["logistics", "inflation"], "impact": 0.2}],
        1,
    )
    assert reported[0]["quote"] == text
    assert reported[0]["status"] == "reported_by_source"
    assert paths[0]["business_effect"] == "hypothesis"
    assert paths[0]["source_material_id"] == 1


def test_role_changes_analysis_focus_and_next_action():
    assert role_focus("cfo") != role_focus("treasurer")
    assert "учёт" in role_focus("chief_accountant")[0]
