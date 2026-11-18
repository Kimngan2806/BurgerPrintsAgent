import asyncio
import logging

import httpx

from api.burgerprints import BurgerPrintsClient
from cache.duckdb_store import db_store
from core.config import settings
# We will import HybridSearch dynamically in sync to avoid circular imports

logger = logging.getLogger(__name__)
catalog_sync_status = 'not_started'


async def sync_catalog_to_cache(rebuild_search_index_fn=None):
    """Fetch the BurgerPrints catalog and replace the local snapshot."""
    global catalog_sync_status
    logger.info("Starting catalog sync from API to DuckDB...")
    client = BurgerPrintsClient()
    if not settings.BURGERPRINTS_API_KEY:
        catalog_sync_status = 'missing_key'
        logger.warning('Catalog sync skipped: no API key. Retaining last good snapshot.')
        return
    
    catalog_sync_status = 'syncing'
    try:
        products_dict, skus_dict, providers = await client.get_catalog_snapshot(fetch_details=True)

        writer = asyncio.create_task(asyncio.to_thread(db_store.replace_snapshot, products_dict, skus_dict, providers))
        try:
            await asyncio.shield(writer)
        except asyncio.CancelledError:
            # Wait for the transaction to finish before the app closes the database.
            try:
                await writer
            except Exception:
                logger.exception("Catalog snapshot failed while shutting down.")
            raise

        catalog_sync_status = 'ready'
        
        logger.info("Catalog sync completed successfully.")
        
        if rebuild_search_index_fn:
            logger.info("Rebuilding search index...")
            all_products = db_store.get_all_products_raw()
            rebuild_search_index_fn(all_products)
            logger.info("Search index rebuilt.")
            
    except httpx.HTTPStatusError as e:
        catalog_sync_status = f'upstream_http_{e.response.status_code}'
        logger.warning('BurgerPrints rejected catalog sync: HTTP %s', e.response.status_code)
    except httpx.RequestError as e:
        catalog_sync_status = 'upstream_timeout' if isinstance(e, httpx.TimeoutException) else 'upstream_unreachable'
        logger.warning('Could not reach BurgerPrints catalog: %s', type(e).__name__)
    except Exception as e:
        catalog_sync_status = 'ready' if db_store.catalog_ready else 'invalid_snapshot'
        logger.error(f"Failed to sync catalog: {e}")
