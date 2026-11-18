import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.workspace as workspace_module
from core.config import settings
from core.workspace import Workspace
from routers import chat as chat_routes
from routers import workspace as workspace_routes


@pytest.fixture(params=["sqlite", "postgres"])
def reopen_workspace(request, tmp_path):
    path = tmp_path / "workspace.sqlite3"
    if request.param == "sqlite":
        yield lambda: Workspace(path)
        return

    database_url = os.environ.get("WORKSPACE_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set WORKSPACE_TEST_POSTGRES_URL to a direct connection to a test database.")
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    schema = f"workspace_test_{uuid.uuid4().hex}"
    with psycopg.connect(database_url, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            test_conninfo = make_conninfo(database_url, options=f"-csearch_path={schema}")
            yield lambda: Workspace(path, database_url=test_conninfo)
        finally:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_conversation_history_stays_with_its_account_across_restart(reopen_workspace, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)

    def make_app(store):
        monkeypatch.setattr(workspace_module, "workspace", store)
        monkeypatch.setattr(workspace_routes, "workspace", store)
        monkeypatch.setattr(chat_routes, "workspace", store)
        app = FastAPI()
        app.include_router(workspace_routes.router, prefix="/api")
        app.include_router(chat_routes.router, prefix="/api")
        return app

    alice = {"name": "seller-alice", "password": "test-alice-password"}
    message = "Tôi muốn đặt hàng"
    with TestClient(make_app(reopen_workspace())) as before:
        assert before.post("/api/auth/register", json=alice).status_code == 200
        created = before.post("/api/conversations")
        assert created.status_code == 200
        ident = created.json()["id"]
        turn = before.post("/api/chat", json={"session_id": ident, "message": message})
        assert turn.status_code == 200
        reply = turn.json()["response"]
        assert "SKU" in reply
        saved = before.get(f"/api/conversations/{ident}").json()
        assert [(item["role"], item["content"]) for item in saved["messages"]] == [
            ("user", message), ("agent", reply),
        ]
        session = before.cookies["bp_session"]

    restarted_app = make_app(reopen_workspace())
    with TestClient(restarted_app, cookies={"bp_session": session}) as after_restart:
        assert after_restart.get("/api/work/conversation").json() == [saved]
        assert after_restart.get(f"/api/conversations/{ident}").json() == saved

    with TestClient(restarted_app) as other_seller:
        bob = {"name": "seller-bob", "password": "test-bob-password"}
        assert other_seller.post("/api/auth/register", json=bob).status_code == 200
        assert other_seller.get("/api/work/conversation").json() == []
        assert other_seller.get(f"/api/conversations/{ident}").status_code == 404
        assert other_seller.post("/api/auth/login", json=alice).status_code == 200
        assert other_seller.get("/api/work/conversation").json() == [saved]
