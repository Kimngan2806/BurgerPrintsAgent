import logging
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Phải load env đầu tiên để config có giá trị
load_dotenv()

from core.config import settings
from cache.duckdb_store import db_store
from cache import sync as catalog_sync
from search.hybrid_search import hybrid_searcher
from core.feature_flags import ff_manager
from routers.chat import router as chat_router
from routers.catalog_debug import router as catalog_debug_router
from routers.workspace import router as workspace_router
from core.workspace import current_owner, workspace

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def maintain_catalog():
    if settings.CACHE_SYNC_ON_STARTUP:
        rebuild_fn = hybrid_searcher.build_index if settings.BUILD_SEARCH_INDEX_ON_STARTUP else None
        await catalog_sync.sync_catalog_to_cache(rebuild_search_index_fn=rebuild_fn)

    interval = max(60, settings.CATALOG_SYNC_INTERVAL_SECONDS)
    retry_delay = 30
    while settings.CATALOG_SYNC_INTERVAL_SECONDS > 0:
        if settings.BURGERPRINTS_API_KEY and not db_store.catalog_ready:
            await asyncio.sleep(min(interval, retry_delay))
            retry_delay = min(retry_delay * 2, 600)
        else:
            await asyncio.sleep(interval)
            retry_delay = 30
        await catalog_sync.sync_catalog_to_cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("BurgerPrintsAgent backend starting")
    if settings.BUILD_SEARCH_INDEX_ON_STARTUP and not settings.CACHE_SYNC_ON_STARTUP:
        hybrid_searcher.build_index(db_store.get_all_products_raw())

    sync_task = asyncio.create_task(maintain_catalog())
    try:
        yield
    finally:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("BurgerPrintsAgent backend shutting down")
            db_store.close()

# Khởi tạo app
app = FastAPI(
    title="BurgerPrintsAgent API",
    description="API cho AI Assistant hỗ trợ tìm kiếm sản phẩm POD",
    version="1.0.0",
    lifespan=lifespan
)

# Cấu hình CORS để frontend React gọi được
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(',')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(catalog_debug_router, prefix="/api", tags=["Catalog Debug"], dependencies=[Depends(current_owner)])
app.include_router(workspace_router, prefix="/api", tags=["Workspace"])

@app.get("/health", tags=["System"])
async def health_check():
    payload = {
        "status": "ok",
        "release": os.getenv("RENDER_GIT_COMMIT", "")[:12],
        "workspace_storage": workspace.backend,
        "search_ready": True,
        "catalog_ready": db_store.catalog_ready,
        "catalog_sync_status": catalog_sync.catalog_sync_status,
        "vector_search_ready": hybrid_searcher.is_ready,
        "harness_active": ff_manager.is_active()
    }
    return payload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
