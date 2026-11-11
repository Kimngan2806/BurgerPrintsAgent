import asyncio

import httpx

from agent import tool_handlers
from api.burgerprints import BurgerPrintsClient
from cache.duckdb_store import DuckDBStore
from core.config import settings


def test_catalog_sync_collapses_aliases_and_excludes_conflicting_skus(monkeypatch):
    monkeypatch.setattr(settings, "BURGERPRINTS_API_KEY", "fixture-key")
    client = BurgerPrintsClient()
    seen = []

    def respond(request):
        code = request.url.path.rsplit("/", 1)[-1]
        seen.append(code)
        if code == "product":
            return httpx.Response(200, json={"data": {"result": [
                {"short_code": "TEE", "name": "Cotton T-Shirt"},
                {"short_code": "ALIAS", "name": "Cotton T-Shirt"},
                {"short_code": "TEE", "name": "Cotton T-Shirt"},
            ]}})
        return httpx.Response(200, json={"data": {"short_code": "TEE", "variations": [
            {"sku": "TEE-WHITE-M" if code == "TEE" else "tee-white-m", "color": "White", "size": "M"},
            {"sku": "TEE-CONFLICT", "color": "White" if code == "TEE" else "Black"},
            {"sku": ""},
        ]}})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    products, skus, providers = asyncio.run(client.get_catalog_snapshot())
    assert seen == ["product", "TEE", "ALIAS"]
    assert [product["id"] for product in products] == ["TEE"]
    assert [sku["sku_code"] for sku in skus] == ["TEE-WHITE-M"]
    monkeypatch.setattr(settings, "DUCKDB_PATH", ":memory:")
    store = DuckDBStore()
    try:
        store.replace_snapshot(products, skus, providers)
        assert store.has_catalog()
    finally:
        store.close()


def test_white_tshirt_search_filters_skus_before_limiting_products(monkeypatch):
    monkeypatch.setattr(settings, "DUCKDB_PATH", ":memory:")
    store = DuckDBStore()
    monkeypatch.setattr(tool_handlers, "db_store", store)
    args = {"query": "áo thun trắng", "color": "trắng", "size": "M"}
    try:
        assert asyncio.run(tool_handlers.search_products(args))["code"] == "CATALOG_UNAVAILABLE"

        products = [
            {"id": str(i), "name": f"A{i:02d} T-shirt", "category": "t-shirt"}
            for i in range(16)
        ] + [{"id": "white-tee", "name": "Z Cotton Tee", "category": "t-shirt"}]
        skus = [
            {"sku_code": f"BLACK-{i}", "product_id": str(i), "color": "Black", "size": "M"}
            for i in range(16)
        ] + [
            {"sku_code": "WHITE-S", "product_id": "0", "color": "White", "size": "S"},
            {"sku_code": "WHITE-M", "product_id": "white-tee", "color": " White ", "size": "M"},
        ]
        store.replace_snapshot(products, skus, [])

        result = asyncio.run(tool_handlers.search_products(args))["results"]
        assert [item["id"] for item in result] == ["white-tee"]
        assert [variant["sku_code"] for variant in result[0]["variants"]] == ["WHITE-M"]
    finally:
        store.close()
