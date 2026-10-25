import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.main import create_app
from backend.manage import migrate, seed_demo


@pytest.fixture
def system():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration checks")
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    test_url = make_conninfo(url, options="-c search_path=" + schema)
    db = Database(test_url)
    try:
        migrate(test_url)
        db.open()
        seed_demo(db)
        settings = Settings(
            _env_file=None, database_url=SecretStr(test_url), ingest_api_key=SecretStr("operator-test-key")
        )
        app = create_app(settings, db)
        with TestClient(app) as client:
            yield client, db, settings
    finally:
        db.close()
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def register(client, email="one@example.test", company=None):
    org = company or client.get("/api/v1/organizations").json()["items"][0]["id"]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "test-password-123",
            "name": "Тест",
            "role": "cfo",
            "organization_id": org,
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def authorized(system):
    client, db, settings = system
    return client, db, settings, register(client)
