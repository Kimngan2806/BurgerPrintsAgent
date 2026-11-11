import asyncio

from agent import tool_handlers
from cache.duckdb_store import DuckDBStore
from core.config import settings


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
