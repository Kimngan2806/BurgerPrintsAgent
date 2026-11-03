import logging
from cachetools import TTLCache, cached

logger = logging.getLogger(__name__)

# TTL configuration (in seconds)
# Dùng in-memory TTLCache cho các operation rất thường xuyên cần cache siêu nhanh
CACHE_CONFIG = {
    "product_name": 7 * 24 * 3600,
    "product_category": 7 * 24 * 3600,
    "sku_info": 24 * 3600,
}

# Khởi tạo các cache instance
product_cache = TTLCache(maxsize=1000, ttl=CACHE_CONFIG["product_name"])
sku_cache = TTLCache(maxsize=10000, ttl=CACHE_CONFIG["sku_info"])

@cached(cache=product_cache)
def get_cached_product_category(category: str):
    # Dummy function để test, DuckDB là source of truth chính cho queries
    pass
