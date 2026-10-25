import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from backend.app.connections import build_context, neighbors, rebuild_payment_connections
from backend.app.main import create_app
from backend.bootstrap import bootstrap
from backend.tests.conftest import register


def company(db, uid, group=None):
    return db.one(
        "INSERT INTO organizations(synthetic_u,group_id,profile_data) VALUES(%s,%s,%s) RETURNING id",
        (uid, group, Jsonb({"MAINOKVED_NAME": "Торговля"})),
    )["id"]


def test_observed_links_preserve_ambiguity_and_cycles(system):
    _, db, _ = system
    a, b, c = company(db, "U_TEST_A", "g"), company(db, "U_TEST_B", "g"), company(db, "U_TEST_C")
    with db.transaction() as conn:
        for i, (payer, beneficiary, amount) in enumerate(
            [(a, b, 10), (a, b, 20), (a, a, 100), (b, c, 100), (c, a, 100)]
        ):
            conn.execute(
                "INSERT INTO payment_flows(payer_id,beneficiary_id,amount,payment_count,source_ref,source_row) VALUES(%s,%s,%s,1,'test',%s)",
                (payer, beneficiary, amount, i + 1),
            )
        conn.execute(
            "INSERT INTO person_organization_links(synthetic_f,organization_id) VALUES('F_TEST',%s),('F_TEST',%s)",
            (a, c),
        )
    assert rebuild_payment_connections(db) == 3
    pair = db.one("SELECT * FROM payment_connections WHERE payer_id=%s AND beneficiary_id=%s", (a, b))
    assert pair["observation_count"] == 2
    assert pair["amount"] is pair["payer_share"] is None
    links = neighbors(db, a)
    assert {"payment", "group", "shared_person"} <= {x["relation_type"] for x in links}
    assert all(x["dependency_weight"] is None for x in links)
    graph = build_context(db, a, max_depth=4)
    assert graph["paths"]
    assert all(len(p["nodes"]) == len(set(p["nodes"])) for p in graph["paths"])
    assert all(p["weight"] <= 1 and not p["dependency_confirmed"] for p in graph["paths"])
    assert build_context(db, a, max_depth=1)["paths"]
    assert all(p["depth"] == 1 for p in build_context(db, a, max_depth=1)["paths"])


def test_chain_decay_and_bound(system):
    _, db, _ = system
    ids = [company(db, "U_CHAIN_" + str(i)) for i in range(5)]
    with db.transaction() as conn:
        for a, b in zip(ids, ids[1:]):
            conn.execute(
                "INSERT INTO organization_relations(organization_id,counterparty_id,relation_type,dependency_weight,evidence) VALUES(%s,%s,'supplier',0.8,'test')",
                (a, b),
            )
    graph = build_context(db, ids[0], max_depth=3, decay=0.5)
    assert [p["depth"] for p in graph["paths"]] == [1, 2, 3]
    assert [p["weight"] for p in graph["paths"]] == [0.8, 0.32, 0.128]
    limited = build_context(db, ids[0], max_nodes=2)
    assert len(limited["paths"]) == 1 and limited["truncated"]


def test_organizer_mode_filters_and_profile_switch(system):
    client, db, settings = system
    headers = register(client)
    organizer = company(db, "U_REAL_TEST")
    config = settings.model_copy(update={"data_mode": "organizers"})
    with TestClient(create_app(config, db)) as real:
        catalog = real.get("/api/v1/organizations").json()
        assert catalog["total"] == 1
        materials = real.get("/api/v1/materials", headers=headers).json()
        assert all(not x["is_demo"] for x in materials["items"])
        assert real.post("/api/v1/analyses", headers=headers, json={"max_events": 1}).status_code == 409
        changed = real.patch("/api/v1/me", headers=headers, json={"organization_id": organizer})
        assert changed.status_code == 200 and changed.json()["org_id"] == organizer
        assert real.get("/api/v1/me/organization", headers=headers).json()["data_origin"] == "organizers"


def test_bootstrap_requires_real_files(system, tmp_path):
    _, db, _ = system
    with pytest.raises(RuntimeError, match="demo fallback is disabled"):
        bootstrap(db, tmp_path)
