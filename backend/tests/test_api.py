from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from backend.tests.conftest import register
from backend.worker import Worker


def test_auth_and_validation(system):
    client, db, settings = system
    assert client.get("/health/ready").status_code == 200
    assert client.get("/api/v1/me").status_code == 401
    headers = register(client)
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["email"] == "one@example.test"
    assert "password_hash" not in me
    login = client.post(
        "/api/v1/auth/login", json={"email": "one@example.test", "password": "test-password-123"}
    )
    assert login.status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"email": "one@example.test", "password": "wrong"}).status_code
        == 401
    )
    bad = client.post("/api/v1/auth/register", json={"password": "secret-value-never-echo"})
    assert bad.status_code == 422
    assert "secret-value-never-echo" not in bad.text
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_material_pagination_counts_only_ready_publications(authorized):
    client, db, settings, headers = authorized
    with db.transaction() as conn:
        conn.execute(
            "UPDATE materials SET processing_status='pending' WHERE id="
            "(SELECT min(id) FROM materials WHERE material_type='news')"
        )
    page = client.get("/api/v1/materials?kind=news&limit=1&offset=0", headers=headers).json()
    count = db.one(
        "SELECT count(*) AS n FROM materials WHERE material_type='news' AND processing_status='ready'"
    )["n"]
    assert page["total"] == count
    assert len(page["items"]) == min(1, count)
    assert page["limit"] == 1 and page["offset"] == 0


def test_pipeline_feed_citations_and_idempotency(authorized):
    client, db, settings, headers = authorized
    response = client.post(
        "/api/v1/analyses", json={"max_events": 3}, headers=dict(headers, **{"Idempotency-Key": "first"})
    )
    assert response.status_code == 202, response.text
    job = response.json()["id"]
    replay = client.post(
        "/api/v1/analyses", json={"max_events": 3}, headers=dict(headers, **{"Idempotency-Key": "first"})
    )
    assert replay.json()["id"] == job
    assert (
        client.post(
            "/api/v1/analyses", json={"max_events": 1}, headers=dict(headers, **{"Idempotency-Key": "first"})
        ).status_code
        == 409
    )
    assert Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert result["status"] == "completed", result
    assert result["summary"]["created"] > 0
    feed = client.get("/api/v1/feed", headers=headers).json()
    assert feed["total"] == result["summary"]["created"]
    item = client.get("/api/v1/insights/" + str(feed["items"][0]["id"]), headers=headers).json()
    assert item["payload"]["generation_mode"] == "offline"
    assert item["payload"]["verification"]["status"] == "passed"
    assert item["steps"][-1]["tool"] == "insight.verify"
    assert item["payload"]["is_demo"] is True
    for evidence in item["evidence"]:
        source = db.one("SELECT body FROM materials WHERE id=%s", (evidence["material_id"],))
        assert evidence["quote"] in source["body"]
    iid = item["id"]
    assert (
        client.post(
            f"/api/v1/insights/{iid}/feedback", headers=headers, json={"rating": "useful"}
        ).status_code
        == 200
    )
    answer = client.post(
        f"/api/v1/insights/{iid}/questions", headers=headers, json={"question": "Что делать?"}
    ).json()
    assert answer["generation_mode"] == "offline" and answer["sources"]


def test_cross_user_isolation(authorized):
    client, db, settings, first = authorized
    job = client.post("/api/v1/analyses", json={}, headers=first).json()["id"]
    Worker(db, settings).run_once()
    iid = client.get("/api/v1/feed", headers=first).json()["items"][0]["id"]
    second = register(
        client, "second@example.test"
    )  # even a user in the same company cannot read private jobs
    assert client.get("/api/v1/feed", headers=second).json()["total"] == 0
    for path in [f"/api/v1/insights/{iid}", f"/api/v1/analyses/{job}"]:
        assert client.get(path, headers=second).status_code == 404
    assert (
        client.post(
            f"/api/v1/insights/{iid}/questions", json={"question": "Покажи данные"}, headers=second
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/insights/{iid}/feedback", json={"rating": "useful"}, headers=second).status_code
        == 404
    )


def test_ingestion_requires_operator_and_deduplicates(system):
    client, db, settings = system
    body = {
        "articles": [
            {
                "title": "Новая новость о логистике",
                "body": "Стоимость перевозок выросла. Это затронуло международную логистику.",
                "source_name": "Тест",
                "source_url": "https://example.test/news/one",
                "published_at": "2026-09-16T12:00:00Z",
            }
        ]
    }
    assert client.post("/api/v1/ingestion/news", json=body).status_code == 403
    headers = {"X-Ingest-Key": "operator-test-key"}
    one = client.post("/api/v1/ingestion/news", json=body, headers=headers)
    assert one.status_code == 201, one.text
    assert len(one.json()["inserted_ids"]) == 1
    two = client.post("/api/v1/ingestion/news", json=body, headers=headers).json()
    assert two["duplicates"] == 1 and two["inserted_ids"] == []
    body["articles"][0]["published_at"] = "2026-09-16"
    assert client.post("/api/v1/ingestion/news", json=body, headers=headers).status_code == 422


def test_empty_shocks_skip_without_fabrication(authorized):
    client, db, settings, headers = authorized
    with db.transaction() as conn:
        conn.execute(
            "UPDATE materials SET analysis_data=%s WHERE material_type='news'", (Jsonb({"shocks": []}),)
        )
    job = client.post("/api/v1/analyses", json={}, headers=headers).json()["id"]
    Worker(db, settings).run_once()
    row = client.get("/api/v1/analyses/" + job, headers=headers).json()
    assert row["status"] == "completed"
    assert row["summary"]["created"] == 0
    assert row["summary"]["skipped"] == 3


def test_worker_failure_is_persisted_and_not_published(authorized, monkeypatch):
    client, db, settings, headers = authorized
    job = client.post("/api/v1/analyses", json={}, headers=headers).json()["id"]

    def fail(*args, **kwargs):
        raise RuntimeError("sensitive-provider-text")

    monkeypatch.setattr("backend.worker.analyze_material", fail)
    Worker(db, settings).run_once()
    result = client.get("/api/v1/analyses/" + job, headers=headers)
    assert result.json()["status"] == "failed"
    assert "sensitive-provider-text" not in result.text
    assert client.get("/api/v1/feed", headers=headers).json()["total"] == 0
    assert db.one("SELECT status FROM analysis_runs WHERE job_id=%s", (job,))["status"] == "failed"


def test_queue_claim_and_stale_recovery(authorized):
    client, db, settings, headers = authorized
    first = client.post("/api/v1/analyses", json={}, headers=headers).json()["id"]
    w1 = Worker(db, settings)
    w2 = Worker(db, settings)
    assert str(w1.claim()["id"]) == first
    assert w2.claim() is None
    with db.transaction() as conn:
        conn.execute(
            "UPDATE analysis_jobs SET heartbeat_at=%s WHERE id=%s",
            (datetime.now(timezone.utc) - timedelta(hours=1), first),
        )
    assert w2.claim() is None
    assert (
        client.get("/api/v1/analyses/" + first, headers=headers).json()["error_code"]
        == "worker_lease_expired"
    )


def test_migrations_and_seed_are_repeatable(system):
    from backend.manage import migrate, seed_demo

    client, db, settings = system
    before = db.one("SELECT count(*) AS n FROM materials")["n"]
    migrate(settings.database_url.get_secret_value())
    seed_demo(db)
    assert db.one("SELECT count(*) AS n FROM materials")["n"] == before


def test_live_generation_sends_minimal_context(authorized, monkeypatch):
    import json

    import httpx
    from pydantic import SecretStr

    client, db, settings, headers = authorized
    live = settings.model_copy(
        update={
            "llm_mode": "live",
            "llm_allow_external": True,
            "llm_base_url": "https://example.test/v1",
            "llm_api_key": SecretStr("test-only-key"),
            "llm_model": "approved-fixture",
            "llm_allowed_models": ["approved-fixture"],
        }
    )
    sent = []

    def respond(self, url, **kwargs):
        sent.append(json.dumps(kwargs["json"], ensure_ascii=False))
        result = {
            "headline": "Проверьте условия действующих договоров",
            "interpretation": "Влияние зависит от условий договоров. Требуется проверить сроки и механизм пересмотра цен.",
            "risks": [],
            "opportunities": [],
            "actions": ["Проверить условия договоров"],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(result)}}]},
            request=httpx.Request("POST", url),
        )

    job = client.post("/api/v1/analyses", json={"max_events": 1}, headers=headers).json()["id"]
    monkeypatch.setattr(httpx.Client, "post", respond)
    Worker(db, live).run_once()
    assert client.get("/api/v1/analyses/" + job, headers=headers).json()["status"] == "completed"
    assert sent
    for text in sent:
        assert "DEMO_" not in text and "20000000000" not in text
        assert "one@example.test" not in text and "test-password" not in text


def test_request_size_and_cors(system):
    client, _, _ = system
    response = client.post("/api/v1/auth/login", content=b"x" * 6_000_001)
    assert response.status_code == 413
    response = client.options(
        "/api/v1/analyses",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_batch_news_are_clustered(system):
    client, db, _ = system
    body = {
        "articles": [
            {
                "title": "Банк России: решение по ставке",
                "body": "Банк России повысил ключевую ставку. Решение влияет на условия новых кредитов у банков и планы финансирования.",
                "source_name": "Тест A",
                "source_url": "https://example.test/batch/a",
                "published_at": "2026-09-16T12:00:00Z",
            },
            {
                "title": "Банк России объяснил принятое решение",
                "body": "Банк России опубликовал комментарии к решению. Регулятор объяснил изменения ожиданиями инфляции и состоянием внутреннего спроса.",
                "source_name": "Тест B",
                "source_url": "https://example.test/batch/b",
                "published_at": "2026-09-16T13:00:00Z",
            },
        ]
    }
    response = client.post("/api/v1/ingestion/news", json=body, headers={"X-Ingest-Key": "operator-test-key"})
    assert response.status_code == 201
    ids = response.json()["inserted_ids"]
    assert len(ids) == 2
    rows = db.all("SELECT analysis_data FROM materials WHERE id=ANY(%s) ORDER BY id", (ids,))
    first = rows[0]["analysis_data"]["clusters"][0]
    second = rows[1]["analysis_data"]["clusters"][0]
    assert first["event_id"] == second["event_id"]
    assert len(first["news_ids"]) == 2
