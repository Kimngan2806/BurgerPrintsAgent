import asyncio

import httpx

import main


def test_health_responds_while_startup_catalog_sync_waits(monkeypatch):
    monkeypatch.setattr(main.settings, 'CACHE_SYNC_ON_STARTUP', True)
    monkeypatch.setattr(main.settings, 'BUILD_SEARCH_INDEX_ON_STARTUP', False)
    monkeypatch.setattr(main.settings, 'CATALOG_SYNC_INTERVAL_SECONDS', 0)
    monkeypatch.setattr(main.db_store, 'catalog_ready', False)
    monkeypatch.setattr(main.db_store, 'close', lambda: None)

    def unexpected_catalog_query():
        raise AssertionError('Health should read the cached catalog status')

    monkeypatch.setattr(main.db_store, 'has_catalog', unexpected_catalog_query)

    async def verify():
        started = asyncio.Event()
        pending = asyncio.Event()

        async def slow_startup_sync(**kwargs):
            started.set()
            await pending.wait()

        monkeypatch.setattr(main.catalog_sync, 'sync_catalog_to_cache', slow_startup_sync)
        async with main.app.router.lifespan_context(main.app):
            await started.wait()
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
                response = await client.get('/health')
            assert response.status_code == 200
            assert response.json()['catalog_ready'] is False

    asyncio.run(asyncio.wait_for(verify(), timeout=2))
