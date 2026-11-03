import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env", override=False)
os.environ["DUCKDB_PATH"] = str(BACKEND_ROOT / "catalog.duckdb")

from agent.gemini_agent import execute_tool  # noqa: E402
from api.burgerprints import BurgerPrintsClient  # noqa: E402
from core.feature_flags import ff_manager  # noqa: E402
from cache.duckdb_store import db_store  # noqa: E402


SKU = "USBG5000DTF-Black-S"


def percentile(values, p):
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * p))
    return ordered[index]


async def measure(name, fn, runs=5):
    values = []
    errors = []
    for _ in range(runs):
        start = time.perf_counter()
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            errors.append(str(exc))
        values.append((time.perf_counter() - start) * 1000)

    return {
        "name": name,
        "runs": runs,
        "avg_ms": round(statistics.mean(values), 2),
        "p50_ms": round(percentile(values, 0.5), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "min_ms": round(min(values), 2),
        "max_ms": round(max(values), 2),
        "errors": errors[:3],
    }


async def main():
    client = BurgerPrintsClient()
    results = []

    results.append(await measure("DuckDB get_sku_by_code", lambda: db_store.get_sku_by_code(SKU), runs=20))
    results.append(await measure("DuckDB search_products_text", lambda: db_store.search_products_text("gildan 5000 t-shirt", limit=10), runs=20))
    results.append(await measure("Harness flag is_order_creation_enabled", ff_manager.is_order_creation_enabled, runs=20))
    results.append(await measure("Tool check_sku_availability", lambda: execute_tool("check_sku_availability", {"sku_codes": [SKU]}, ""), runs=10))
    results.append(await measure("Tool get_base_cost", lambda: execute_tool("get_base_cost", {"sku_codes": [SKU]}, ""), runs=10))
    results.append(await measure("BurgerPrints GET /authenticated", lambda: client._get("/authenticated"), runs=5))
    results.append(await measure("BurgerPrints GET /product/USG5000", lambda: client._get("/product/USG5000"), runs=5))

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
