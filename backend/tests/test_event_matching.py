from backend.app.event_matching import event_similarity


def test_event_match_requires_direction_and_headline_overlap():
    increase = [{"factor": "key_rate", "direction": 1}]
    decrease = [{"factor": "key_rate", "direction": -1}]
    first = "Регулятор повысил ключевую ставку до двадцати процентов"
    second = "Регулятор повысил ключевую ставку после заседания"
    assert event_similarity(first, increase, second, increase) >= 0.5
    assert event_similarity(first, increase, second, decrease) == 0
    assert event_similarity(first, increase, "Спрос на металлы вырос в Азии", increase) == 0


def test_cross_batch_event_is_persisted(system):
    client, db, _ = system
    headers = {"X-Ingest-Key": "operator-test-key"}
    ids = []
    for index, title in enumerate((
        "Регулятор повысил ключевую ставку до двадцати процентов",
        "Регулятор повысил ключевую ставку после заседания",
    )):
        article = {
            "title": title,
            "body": "Регулятор повысил ключевую ставку. Новое решение изменит стоимость заимствований для бизнеса.",
            "source_name": f"Источник {index}",
            "source_url": f"https://example.test/cross-batch/{index}",
            "published_at": "2026-09-16T12:00:00Z",
            "shocks": [{"factor": "key_rate", "direction": 1, "magnitude": 0.3}],
        }
        response = client.post("/api/v1/ingestion/news", json={"articles": [article]}, headers=headers)
        assert response.status_code == 201, response.text
        ids.extend(response.json()["inserted_ids"])
    rows = db.all("SELECT event_id FROM materials WHERE id=ANY(%s) ORDER BY id", (ids,))
    assert len(rows) == 2
    assert rows[0]["event_id"] == rows[1]["event_id"] == ids[0]
