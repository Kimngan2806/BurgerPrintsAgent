import asyncio
import logging
from api.burgerprints import BurgerPrintsClient
from cache.duckdb_store import db_store
from core.config import settings
# We will import HybridSearch dynamically in sync to avoid circular imports

logger = logging.getLogger(__name__)

async def sync_catalog_to_cache(rebuild_search_index_fn=None):
    """
    Kéo data từ BurgerPrints API và lưu vào DuckDB.
    Được gọi lúc startup.
    """
    logger.info("Starting catalog sync from API to DuckDB...")
    client = BurgerPrintsClient()
    if not settings.BURGERPRINTS_API_KEY:
        logger.warning('Catalog sync skipped: no API key. Retaining last good snapshot.')
        return
    
    try:
        # 1. Fetch stable catalog data from BurgerPrints /product endpoints.
        products_dict, skus_dict, providers = await client.get_catalog_snapshot(fetch_details=True)
        
        # 3. Seed DuckDB
        db_store.replace_snapshot(products_dict, skus_dict, providers)
        
        logger.info("Catalog sync completed successfully.")
        
        # 4. Rebuild Hybrid Search Index
        if rebuild_search_index_fn:
            logger.info("Rebuilding search index...")
            all_products = db_store.get_all_products_raw()
            rebuild_search_index_fn(all_products)
            logger.info("Search index rebuilt.")
            
    except Exception as e:
        logger.error(f"Failed to sync catalog: {e}")
