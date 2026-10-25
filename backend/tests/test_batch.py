import uuid

import pytest

from backend.app.analytics import AnalysisFailure
from backend.tests.conftest import register
from backend.worker import Worker, analyze_material


@pytest.fixture
def batch(authorized):
    client, db, settings, headers = authorized
    template = db.one(
        "SELECT id FROM materials WHERE material_type='news' AND jsonb_array_length(analysis_data->'shocks')>0 ORDER BY id LIMIT 1"
    )["id"]
    ids = []
    with db.transaction() as conn:
        for i in range(5):
            ids.append(
                conn.execute(
                    """INSERT INTO materials(source_id,source_ref,material_type,title,body,published_at,processing_status,analysis_data,is_demo)
                SELECT source_id,%s,material_type,title,body,published_at,'ready',analysis_data,is_demo FROM materials WHERE id=%s RETURNING id""",
                    ("test-batch-" + str(i), template),
                ).fetchone()["id"]
            )
    response = client.post(
        "/api/v1/analyses", headers=headers, json={"material_ids": ids, "max_events": 5, "min_score": 0}
    )
    assert response.status_code == 202
    return client, db, settings, headers, response.json()["id"], ids


def test_partial_batch_publishes_each_result_before_completion(batch, monkeypatch):
    client, db, settings, headers, job, ids = batch
    calls = []

    def analyze(*args):
        calls.append(args[4]["id"])
        if len(calls) == 2:
            progress = client.get("/api/v1/analyses/" + job, headers=headers).json()
            assert progress["status"] == "running"
            assert progress["summary"]["processed"] == progress["summary"]["created"] == 1
            assert len(progress["insight_ids"]) == 1
            iid = progress["insight_ids"][0]
            assert client.get("/api/v1/feed", headers=headers).json()["total"] == 1
            assert client.get(f"/api/v1/insights/{iid}", headers=headers).status_code == 200
            # Visibility is still bounded to the owner.
            other = register(client, email="other-batch@example.test")
            assert client.get("/api/v1/feed", headers=other).json()["total"] == 0
            assert client.get(f"/api/v1/insights/{iid}", headers=other).status_code == 404
            raise AnalysisFailure([], "llm_timeout")
        return analyze_material(*args)

    monkeypatch.setattr("backend.worker.analyze_material", analyze)
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert len(calls) == 5
    assert result["status"] == "completed" and result["error_code"] is None
    assert result["summary"]["processed"] == result["summary"]["total"] == 5
    assert result["summary"]["created"] == 4 and result["summary"]["failed"] == 1
    assert len(result["insight_ids"]) == client.get("/api/v1/feed", headers=headers).json()["total"] == 4
    failed = [x["material_id"] for x in result["summary"]["materials"] if x["status"] == "failed"]
    assert failed == [calls[1]]
    # Retry uses the existing API, without re-running the four successful materials.
    retried = client.post("/api/v1/analyses", headers=headers, json={"material_ids": failed, "max_events": 1})
    assert retried.status_code == 202 and retried.json()["parameters"]["material_ids"] == failed


@pytest.mark.parametrize("skip_first", [False, True])
def test_all_failed_or_skipped_plus_failed(batch, monkeypatch, skip_first):
    client, db, settings, headers, job, _ = batch
    calls = []

    def analyze(*args):
        calls.append(1)
        if skip_first and len(calls) == 1:
            return None, []
        raise AnalysisFailure([], "llm_auth_failed")

    monkeypatch.setattr("backend.worker.analyze_material", analyze)
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert len(calls) == 5 and result["summary"]["processed"] == 5
    assert result["status"] == ("completed" if skip_first else "failed")
    assert result["summary"]["failed"] == (4 if skip_first else 5)
    assert result["summary"]["skipped"] == int(skip_first)
    assert not result["insight_ids"]


def test_lost_lease_does_not_publish_unfinished_material(batch, monkeypatch):
    client, db, settings, headers, job, _ = batch
    calls = []

    def analyze(*args):
        calls.append(1)
        payload = analyze_material(*args)
        if len(calls) == 2:
            with db.transaction() as conn:
                conn.execute("UPDATE analysis_jobs SET lease_owner=%s WHERE id=%s", (uuid.uuid4(), job))
        return payload

    monkeypatch.setattr("backend.worker.analyze_material", analyze)
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert result["status"] == "running" and len(result["insight_ids"]) == 1
    with db.transaction() as conn:
        conn.execute("UPDATE analysis_jobs SET heartbeat_at=NOW()-INTERVAL '10 minutes' WHERE id=%s", (job,))
    assert Worker(db, settings).claim() is None
    recovered = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert recovered["status"] == "failed" and recovered["error_code"] == "worker_lease_expired"
    assert len(recovered["insight_ids"]) == client.get("/api/v1/feed", headers=headers).json()["total"] == 1


def test_indirect_only_influence_has_verifiable_factor_refs(batch, monkeypatch):
    from types import SimpleNamespace

    client, db, settings, headers, job, _ = batch

    def own_impact(self, profiles, shocks):
        return [
            SimpleNamespace(
                to_dict=lambda: {
                    "company_id": profiles[0]["company_id"],
                    "total_impact": 0,
                    "factor_impacts": {},
                    "top_paths": [],
                    "confidence": 0.6,
                }
            )
        ]

    monkeypatch.setattr("backend.app.analytics.ShockPropagator.impact_on_all_companies", own_impact)
    monkeypatch.setattr(
        "backend.app.analytics.assess_context",
        lambda *a: {
            "direct_count": 1,
            "examined_count": 1,
            "profiled_count": 1,
            "indirect_signal": 0.4,
            "top_paths": [{"factor_impacts": {"inflation": 0.3}}],
            "note": "test",
            "truncated": False,
        },
    )
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert result["summary"]["created"] == 5 and result["summary"]["failed"] == 0
    insight = client.get("/api/v1/insights/" + str(result["insight_ids"][0]), headers=headers).json()
    assert insight["payload"]["factor_impact"]["factor_impacts"] == {}
    assert insight["payload"]["channels"]["ai_conclusion"][0]["refs"] == ["inflation"]
    assert insight["payload"]["verification"]["status"] == "passed"


def test_invalid_model_output_has_safe_error_details(batch, monkeypatch):
    client, db, settings, headers, job, _ = batch
    worker = Worker(db, settings)
    worker.llm.settings = settings.model_copy(update={"llm_mode": "live"})
    monkeypatch.setattr(
        worker.llm,
        "json",
        lambda *a: {
            "headline": "A sufficiently long headline",
            "interpretation": "A sufficiently long interpretation based on the source.",
            "actions": ["private-model-output"] * 6,
        },
    )
    worker.run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert result["status"] == "failed" and result["error_code"] == "llm_invalid_output"
    assert result["summary"]["failed"] == 5
    runs = db.all("SELECT steps FROM analysis_runs WHERE job_id=%s", (job,))
    assert all(any(x["tool"] == "output.validate" for x in r["steps"]) for r in runs)
    assert "private-model-output" not in str(runs)
