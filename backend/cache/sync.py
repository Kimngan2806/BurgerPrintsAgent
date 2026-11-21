import asyncio
import logging
import time

import httpx

from api.burgerprints import BurgerPrintsClient
from cache import catalog_snapshot
from cache.duckdb_store import db_store
from core.config import settings

logger = logging.getLogger(__name__)
catalog_sync_status = 'not_started'
catalog_snapshot_status = 'not_checked'
catalog_snapshot_fetched_at = None


async def _write_local_catalog(fetched_at, catalog):
    writer = asyncio.create_task(asyncio.to_thread(db_store.replace_snapshot, *catalog, fetched_at=fetched_at))
    try:
        await asyncio.shield(writer)
    except asyncio.CancelledError:
        # Wait for DuckDB to finish the transaction before shutdown closes it.
        try:
            await writer
        except Exception:
            logger.exception('Catalog write failed during shutdown.')
        raise


async def restore_catalog():
    global catalog_sync_status, catalog_snapshot_status, catalog_snapshot_fetched_at
    if not catalog_snapshot.enabled():
        catalog_snapshot_status = 'disabled'
        return None
    if db_store.catalog_ready:
        return None

    catalog_snapshot_status = 'loading'
    try:
        saved = await asyncio.to_thread(catalog_snapshot.load)
        if saved is None:
            catalog_snapshot_status = 'missing'
            return None
        fetched_at, catalog = saved
        await _write_local_catalog(fetched_at, catalog)
    except Exception:
        catalog_snapshot_status = 'restore_error'
        logger.warning('Could not restore the PostgreSQL catalog snapshot.', exc_info=True)
        return None

    catalog_snapshot_status = 'restored'
    catalog_snapshot_fetched_at = fetched_at
    catalog_sync_status = 'ready'
    logger.info('Catalog restored from PostgreSQL using the original timestamp %s.', fetched_at)
    return fetched_at


async def sync_catalog_to_cache(rebuild_search_index_fn=None):
    """Fetch the BurgerPrints catalog and replace the local snapshot."""
    global catalog_sync_status, catalog_snapshot_status, catalog_snapshot_fetched_at
    logger.info("Starting catalog sync from API to DuckDB...")
    client = BurgerPrintsClient()
    if not settings.BURGERPRINTS_API_KEY:
        catalog_sync_status = 'missing_key'
        logger.warning('Catalog sync skipped: no API key. Retaining last good snapshot.')
        return
    
    catalog_sync_status = 'syncing'
    try:
        catalog = await client.get_catalog_snapshot(fetch_details=True)
        fetched_at = int(time.time())
        await _write_local_catalog(fetched_at, catalog)

        catalog_sync_status = 'ready'
        logger.info("Catalog sync completed successfully.")

        if catalog_snapshot.enabled():
            catalog_snapshot_status = 'saving'
            try:
                persisted_at = await asyncio.to_thread(catalog_snapshot.save, fetched_at, catalog)
            except Exception:
                catalog_snapshot_status = 'save_error'
                logger.warning('Could not save the PostgreSQL catalog snapshot.', exc_info=True)
            else:
                catalog_snapshot_status = 'stored'
                catalog_snapshot_fetched_at = persisted_at
                logger.info('Catalog snapshot saved to PostgreSQL.')

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
