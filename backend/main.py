import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Phải load env đầu tiên để config có giá trị
load_dotenv()

from core.config import settings
from cache.duckdb_store import db_store
from cache.sync import sync_catalog_to_cache
from search.hybrid_search import hybrid_searcher
from core.feature_flags import ff_manager
from routers.chat import router as chat_router
from routers.catalog_debug import router as catalog_debug_router

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & Shutdown events"""
    logger.info("BurgerPrintsAgent Backend Starting up...")
    
    # Init cache và search index khi khởi động
    if settings.CACHE_SYNC_ON_STARTUP:
        rebuild_fn = hybrid_searcher.build_index if settings.BUILD_SEARCH_INDEX_ON_STARTUP else None
        await sync_catalog_to_cache(rebuild_search_index_fn=rebuild_fn)
    elif settings.BUILD_SEARCH_INDEX_ON_STARTUP:
        hybrid_searcher.build_index(db_store.get_all_products_raw())
    else:
        logger.info("Fast startup enabled: using DuckDB catalog without startup sync/vector index.")
        
    yield
    
    logger.info("BurgerPrintsAgent Backend Shutting down...")
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
    allow_origins=["*"], # Trong production nên set cụ thể url của frontend
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký router
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(catalog_debug_router, prefix="/api", tags=["Catalog Debug"])

@app.get("/health", tags=["System"])
async def health_check():
    payload = {
        "status": "ok", 
        "search_ready": True,
        "vector_search_ready": hybrid_searcher.is_ready,
        "harness_active": ff_manager.is_active()
    }
    return payload

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
