"""Manual production-order test.

This script calls the real BurgerPrints create-order API with sandbox=False.
It can create a real order and incur charges. It requires RUN_REAL_ORDER=YES.
"""

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

load_dotenv(BACKEND_ROOT / ".env", override=False)

SOURCE_DUCKDB = BACKEND_ROOT / "catalog.duckdb"
TEST_DUCKDB = BACKEND_ROOT / "catalog_manual_test.duckdb"
shutil.copyfile(SOURCE_DUCKDB, TEST_DUCKDB)
os.environ["DUCKDB_PATH"] = str(TEST_DUCKDB)

from agent.gemini_agent import execute_tool  # noqa: E402
from cache.duckdb_store import db_store  # noqa: E402


TEST_SKU = "USBG5000DTF-Black-S"
DESIGN_URL_FRONT = os.getenv("DESIGN_URL_FRONT", "").strip()
ORDER_ARGS = {
    "sku": TEST_SKU,
    "quantity": 1,
    "address": {
        "name": "John Carter",
        "street": "2458 West Sunset Blvd",
        "city": "Los Angeles",
        "state": "California",
        "zip": "90026",
        "country": "US",
    },
    "design_url_front": DESIGN_URL_FRONT,
    "shipping_method": "standard",
}


async def main() -> int:
    print("WARNING: this test creates a REAL production order (sandbox=False).")
    if os.getenv("RUN_REAL_ORDER") != "YES":
        print("ABORTED: set RUN_REAL_ORDER=YES only when you intend to create and pay for a real order.")
        return 2

    if not DESIGN_URL_FRONT.startswith(("http://", "https://")):
        print("ABORTED: set DESIGN_URL_FRONT to a public http/https image URL before creating a real order.")
        return 2

    if not db_store.get_sku_by_code(TEST_SKU):
        print(f"FAIL: SKU `{TEST_SKU}` not found in DuckDB.")
        return 1

    result = await execute_tool(
        "create_order",
        ORDER_ARGS,
        user_message=f"Xác nhận đặt SKU {TEST_SKU}",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "created" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
