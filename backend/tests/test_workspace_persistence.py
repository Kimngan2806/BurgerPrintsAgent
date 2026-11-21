import asyncio
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


def test_catalog_is_restored_from_postgres_with_original_freshness(reopen_workspace, monkeypatch):
    import main
    from cache import catalog_snapshot, sync
    from cache.duckdb_store import DuckDBStore

    storage = reopen_workspace()
    monkeypatch.setattr(catalog_snapshot, 'workspace', storage)
    monkeypatch.setattr(settings, 'BURGERPRINTS_API_KEY', 'catalog-test-store-key')
    monkeypatch.setattr(sync, 'catalog_snapshot_status', 'not_checked')
    if storage.backend == 'sqlite':
        assert not catalog_snapshot.enabled()
        assert asyncio.run(sync.restore_catalog()) is None
        return

    monkeypatch.setattr(settings, 'DUCKDB_PATH', ':memory:')
    monkeypatch.setattr(settings, 'CACHE_SYNC_ON_STARTUP', True)
    monkeypatch.setattr(settings, 'BUILD_SEARCH_INDEX_ON_STARTUP', False)
    monkeypatch.setattr(settings, 'CATALOG_SYNC_INTERVAL_SECONDS', 21600)
    monkeypatch.setattr(sync, 'catalog_snapshot_fetched_at', None)
    monkeypatch.setattr(sync, 'catalog_sync_status', 'not_started')
    products = [{'id': 'US-TEE', 'name': 'Áo thun trắng', 'category': 't-shirt'}]
    skus = [{'sku_code': f'WHITE-{i}', 'product_id': 'US-TEE', 'color': 'White',
             'price': '8.50', 'raw_json': {'print_area': 'front'}} for i in range(1001)]
    providers = [{'id': 'US', 'name': 'Catalog test provider'}]
    source_calls = []

    async def fetch(_, fetch_details):
        assert fetch_details
        source_calls.append(True)
        return products, skus, providers

    monkeypatch.setattr(sync.BurgerPrintsClient, 'get_catalog_snapshot', fetch)
    original = DuckDBStore()
    try:
        monkeypatch.setattr(sync, 'db_store', original)
        asyncio.run(sync.sync_catalog_to_cache())
        assert sync.catalog_snapshot_status == 'stored'
        fetched_at = original.get_sku_by_code('WHITE-1000')['cached_at']
        assert fetched_at == sync.catalog_snapshot_fetched_at
    finally:
        original.close()

    # A deploy that finishes an older sync after a newer instance cannot roll it back.
    assert catalog_snapshot.save(fetched_at - 86400, (products, skus[:1], providers)) == fetched_at
    with monkeypatch.context() as changed_key:
        changed_key.setattr(settings, 'BURGERPRINTS_API_KEY', 'other-store-key')
        assert catalog_snapshot.load() is None

    restarted = DuckDBStore()
    monkeypatch.setattr(sync, 'db_store', restarted)
    monkeypatch.setattr(main, 'db_store', restarted)

    async def boot():
        task = asyncio.create_task(main.maintain_catalog())
        try:
            async with asyncio.timeout(5):
                while sync.catalog_snapshot_status != 'restored':
                    await asyncio.sleep(0.02)
            assert restarted.catalog_ready
            assert source_calls == [True]
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    try:
        assert not restarted.catalog_ready
        asyncio.run(boot())
        assert restarted.get_product_by_id('US-TEE')['name'] == 'Áo thun trắng'
        sku = restarted.get_sku_by_code('WHITE-1000')
        assert (sku['price'], sku['cached_at']) == ('8.50', fetched_at)
        assert restarted.get_provider_by_id('US')['name'] == providers[0]['name']
    finally:
        restarted.close()
