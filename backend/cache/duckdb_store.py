import duckdb
import time
import json
import logging
import os
from typing import List, Dict, Any, Optional

from core.config import settings

logger = logging.getLogger(__name__)


def _rows(cursor):
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _product_rows(cursor, *, decode_raw=False):
    products = _rows(cursor)
    for product in products:
        product.pop("score", None)
        for field in ("print_techniques", "available_sizes", "available_colors"):
            product[field] = json.loads(product[field]) if product.get(field) else []
        if decode_raw:
            product["raw_json"] = json.loads(product["raw_json"]) if product.get("raw_json") else {}
    return products


class DuckDBStore:
    def __init__(self):
        self.db_path = settings.DUCKDB_PATH
        self.conn = self._connect_with_retry()
        self.init_schema()
        self.catalog_ready = self.has_catalog()

    def _connect_with_retry(self, retries: int = 5, delay: float = 2.0):
        """Thử kết nối DuckDB nhiều lần để xử lý stale lock khi container restart."""
        # Đảm bảo thư mục tồn tại
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_dir, exist_ok=True)
        
        # Xóa file nếu nó là 0-byte (do script trước đó tạo nhầm)
        if os.path.exists(self.db_path) and os.path.getsize(self.db_path) == 0:
            try:
                os.remove(self.db_path)
                logger.info(f"Removed invalid 0-byte file: {self.db_path}")
            except Exception as e:
                pass

        last_exc = None
        config = {"threads": 1} if os.environ.get("RENDER") == "true" else {}
        for attempt in range(1, retries + 1):
            try:
                return duckdb.connect(self.db_path, read_only=False, config=config)
            except duckdb.IOException as e:
                err_str = str(e)
                last_exc = e

                # Nếu DuckDB báo file không hợp lệ, xóa đi để nó tự tạo lại ở lượt sau
                if "not a valid" in err_str.lower() or "no such file" in err_str.lower():
                    if os.path.exists(self.db_path):
                        try:
                            os.remove(self.db_path)
                        except:
                            pass
                    # Tiếp tục retry
                elif "lock" not in err_str.lower() and "pid" not in err_str.lower():
                    raise e

                # Tự động xóa stale lock file nếu PID 0 (process đã chết)
                if "PID 0" in err_str:
                    lock_file = f"{self.db_path}.lock"
                    if os.path.exists(lock_file):
                        try:
                            os.remove(lock_file)
                            logger.info(f"Auto-removed stale lock file: {lock_file}")
                        except Exception as rm_err:
                            logger.warning(f"Could not remove {lock_file}: {rm_err}")

                logger.warning(
                    f"DuckDB lock conflict (attempt {attempt}/{retries}): {e}. "
                    f"Retrying in {delay}s..."
                )
                time.sleep(delay)
                delay = min(delay * 1.5, 10.0)
        raise last_exc


    def init_schema(self):

        """Khởi tạo schema cho cacheable data"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                material TEXT,
                style TEXT,
                print_techniques TEXT,
                display_name TEXT,
                catalog_id TEXT,
                html_desc TEXT,
                url TEXT,
                design_type TEXT,
                design_url TEXT,
                available_sizes TEXT,
                available_colors TEXT,
                raw_json TEXT,
                cached_at BIGINT NOT NULL
            );
        """)
        self._ensure_columns("products", {
            "display_name": "TEXT",
            "catalog_id": "TEXT",
            "html_desc": "TEXT",
            "url": "TEXT",
            "design_type": "TEXT",
            "design_url": "TEXT",
            "available_sizes": "TEXT",
            "available_colors": "TEXT",
            "raw_json": "TEXT",
        })
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS skus (
                sku_code TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                color TEXT,
                size TEXT,
                material TEXT,
                provider_id TEXT,
                size_id TEXT,
                color_id TEXT,
                color_hex TEXT,
                price TEXT,
                second_price TEXT,
                addition_price TEXT,
                provider_name TEXT,
                raw_json TEXT,
                cached_at BIGINT NOT NULL
            );
        """)
        self._ensure_columns("skus", {
            "size_id": "TEXT",
            "color_id": "TEXT",
            "color_hex": "TEXT",
            "price": "TEXT",
            "second_price": "TEXT",
            "addition_price": "TEXT",
            "provider_name": "TEXT",
            "raw_json": "TEXT",
        })
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT,
                countries_served TEXT,
                raw_json TEXT,
                cached_at BIGINT NOT NULL
            );
        """)
        self._ensure_columns("providers", {"raw_json": "TEXT"})

    def _ensure_columns(self, table: str, columns: Dict[str, str]):
        existing = {
            row[1]
            for row in self.conn.execute(f"PRAGMA table_info('{table}')").fetchall()
        }
        for name, column_type in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    def replace_snapshot(self, products, skus, providers, *, fetched_at=None):
        if not products or not skus:
            raise ValueError('Incomplete catalog snapshot; keeping last good catalog.')
        product_ids = {p['id'] for p in products}
        if len(product_ids) != len(products) or any(s.get('product_id') not in product_ids for s in skus):
            raise ValueError('Invalid catalog relationships.')
        if len({s['sku_code'] for s in skus}) != len(skus):
            raise ValueError('Duplicate SKU codes.')
        fetched_at = int(time.time()) if fetched_at is None else fetched_at
        # A cursor owns a separate transaction, so readers see the last committed snapshot.
        with self.conn.cursor() as writer:
            writer.execute('BEGIN TRANSACTION')
            try:
                self.seed_products(products, transaction=False, connection=writer, cached_at=fetched_at)
                self.seed_skus(skus, transaction=False, connection=writer, cached_at=fetched_at)
                self.seed_providers(providers, transaction=False, connection=writer, cached_at=fetched_at)
                writer.execute('COMMIT')
            except BaseException:
                writer.execute('ROLLBACK')
                raise
        self.catalog_ready = True

    def has_catalog(self) -> bool:
        return self.conn.execute(
            "SELECT EXISTS (SELECT 1 FROM products) AND EXISTS (SELECT 1 FROM skus)"
        ).fetchone()[0]

    def seed_products(self, products: List[Dict], transaction=True, *, connection=None, cached_at=None):
        """Cập nhật data sản phẩm vào DuckDB"""
        connection = self.conn if connection is None else connection
        now = int(time.time()) if cached_at is None else cached_at
        products = list({p.get("id"): p for p in products if p.get("id")}.values())
        
        # Dùng Appender để insert hàng loạt siêu nhanh
        if transaction:
            connection.execute("BEGIN TRANSACTION")
        connection.execute("DELETE FROM products") # Đơn giản hóa: xóa cũ, thêm mới
        
        for p in products:
            connection.execute("""
                INSERT INTO products (
                    id, name, category, description, material, style, print_techniques,
                    display_name, catalog_id, html_desc, url, design_type, design_url,
                    available_sizes, available_colors, raw_json, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                p.get("id"), 
                p.get("name"), 
                p.get("category", ""), 
                p.get("description", ""), 
                p.get("material", ""), 
                p.get("style", ""), 
                json.dumps(p.get("print_techniques", [])),
                p.get("display_name", ""),
                p.get("catalog_id", ""),
                p.get("html_desc", ""),
                p.get("url", ""),
                p.get("design_type", ""),
                p.get("design_url", ""),
                json.dumps(p.get("available_sizes", [])),
                json.dumps(p.get("available_colors", [])),
                json.dumps(p.get("raw_json", {})),
                now
            ))
            
        if transaction:
            connection.execute("COMMIT")
            self.catalog_ready = self.has_catalog()
        logger.info(f"Seeded {len(products)} products into DuckDB")

    def seed_skus(self, skus: List[Dict], transaction=True, *, connection=None, cached_at=None):
        connection = self.conn if connection is None else connection
        now = int(time.time()) if cached_at is None else cached_at
        skus = list({s.get("sku_code"): s for s in skus if s.get("sku_code")}.values())
        text_columns = (
            "sku_code", "product_id", "color", "size", "material", "provider_id",
            "size_id", "color_id", "color_hex", "price", "second_price", "addition_price", "provider_name",
        )
        fields = (*text_columns, "raw_json")
        names = ", ".join(fields)
        values = ", ".join(f"variant.{field}" for field in fields)
        structure = json.dumps([dict.fromkeys(fields, "VARCHAR")])
        insert = f"""
            INSERT INTO skus ({names}, cached_at)
            SELECT {values}, ?
            FROM unnest(from_json_strict(?, ?)) AS batch(variant)
        """
        if transaction:
            connection.execute("BEGIN TRANSACTION")
        connection.execute("DELETE FROM skus")
        # Only expand a batch of variants at a time while keeping the snapshot atomic.
        batch_size = 1000
        for offset in range(0, len(skus), batch_size):
            batch = skus[offset:offset + batch_size]
            rows = []
            for sku in batch:
                row = {}
                for field in text_columns:
                    value = sku.get(field)
                    row[field] = None if value is None else str(value)
                row["raw_json"] = json.dumps(sku.get("raw_json", {}))
                rows.append(row)
            connection.execute(insert, (now, json.dumps(rows, separators=(",", ":")), structure))
        if transaction:
            connection.execute("COMMIT")
            self.catalog_ready = self.has_catalog()
        logger.info(f"Seeded {len(skus)} SKUs into DuckDB")

    def seed_providers(self, providers: List[Dict], transaction=True, *, connection=None, cached_at=None):
        connection = self.conn if connection is None else connection
        now = int(time.time()) if cached_at is None else cached_at
        providers = list({p.get("id"): p for p in providers if p.get("id")}.values())
        if transaction:
            connection.execute("BEGIN TRANSACTION")
        connection.execute("DELETE FROM providers")
        for p in providers:
            connection.execute("""
                INSERT INTO providers (
                    id, name, location, countries_served, raw_json, cached_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                p.get("id"), p.get("name"), p.get("location"),
                json.dumps(p.get("countries_served", [])),
                json.dumps(p.get("raw_json", p)),
                now
            ))
        if transaction:
            connection.execute("COMMIT")
        logger.info(f"Seeded {len(providers)} providers into DuckDB")

    def list_mockup_products(self, kind: str, search: str, offset: int, limit: int) -> list[dict]:
        return _rows(self.conn.execute("""
            SELECT products.id, products.name
            FROM products
            WHERE products.category = ?
              AND contains(lower(concat_ws(' ', products.name, products.display_name, products.id)), lower(?))
              AND EXISTS (SELECT 1 FROM skus WHERE skus.product_id = products.id)
            ORDER BY lower(products.name), products.id
            LIMIT ? OFFSET ?
        """, (kind, search, limit, offset)))

    def mockup_colors(self, product_id: str) -> list[dict]:
        return _rows(self.conn.execute("""
            SELECT DISTINCT trim(skus.color) AS name, lower(trim(skus.color_hex)) AS hex
            FROM skus JOIN products ON products.id = skus.product_id
            WHERE products.id = ? AND products.category IN ('t-shirt', 'mug')
              AND coalesce(trim(skus.color), '') <> ''
            ORDER BY name, hex NULLS LAST
        """, (product_id,)))

    def query_products(self, category: str = None, material: str = None, limit: int = 50) -> List[Dict]:
        """Query sản phẩm dựa trên attributes (Structured search)"""
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        
        if category:
            query += " AND category ILIKE ?"
            params.append(f"%{category}%")
            
        if material:
            query += " AND material ILIKE ?"
            params.append(f"%{material}%")
            
        query += f" LIMIT {limit}"
        
        return _product_rows(self.conn.execute(query, params), decode_raw=True)

    def search_products_text(
        self, query_text: str = None, category: str = None, material: str = None, limit: int | None = 15,
        *, color: str = None, size: str = None,
    ) -> List[Dict]:
        """Fast DuckDB text search over stable catalog fields."""
        query = """
            SELECT *,
                (
                    CASE WHEN ? IS NOT NULL AND name ILIKE ? THEN 8 ELSE 0 END +
                    CASE WHEN ? IS NOT NULL AND id ILIKE ? THEN 10 ELSE 0 END +
                    CASE WHEN ? IS NOT NULL AND category ILIKE ? THEN 4 ELSE 0 END +
                    CASE WHEN ? IS NOT NULL AND description ILIKE ? THEN 2 ELSE 0 END +
                    CASE WHEN ? IS NOT NULL AND material ILIKE ? THEN 2 ELSE 0 END +
                    CASE WHEN ? IS NOT NULL AND print_techniques ILIKE ? THEN 2 ELSE 0 END
                ) AS score
            FROM products
            WHERE 1=1
        """
        params = []
        pattern = None
        if query_text:
            pattern = f"%{query_text}%"
        for _ in range(6):
            params.extend([query_text, pattern])

        words = query_text.strip().split() if query_text else []
        if words:
            for word in words:
                word_pattern = f"%{word}%"
                query += """
                    AND (
                        name ILIKE ? OR id ILIKE ? OR category ILIKE ? OR display_name ILIKE ? OR
                        description ILIKE ? OR material ILIKE ? OR print_techniques ILIKE ?
                    )
                """
                params.extend([word_pattern] * 7)

        if category:
            query += " AND category ILIKE ?"
            params.append(f"%{category}%")

        if material:
            query += " AND material ILIKE ?"
            params.append(f"%{material}%")

        if color or size:
            query += " AND EXISTS (SELECT 1 FROM skus WHERE skus.product_id = products.id"
            if color:
                query += " AND lower(trim(skus.color)) = lower(?)"
                params.append(color)
            if size:
                query += " AND lower(trim(skus.size)) = lower(?)"
                params.append(size)
            query += ")"

        query += " ORDER BY score DESC, name"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        return _product_rows(self.conn.execute(query, params))

    def query_products_by_ids(self, ids: List[str]) -> List[Dict]:
        """Lấy sản phẩm bằng list ID (Dùng cho Hybrid Search sau khi có Top-K)"""
        if not ids:
            return []
            
        # Create placeholders
        placeholders = ', '.join(['?'] * len(ids))
        query = f"SELECT * FROM products WHERE id IN ({placeholders})"
        
        results = _product_rows(self.conn.execute(query, ids), decode_raw=True)
            
        # Re-sort to match original ID order from Top-K ranking
        id_to_product = {str(p["id"]): p for p in results}
        sorted_results = [id_to_product[str(pid)] for pid in ids if str(pid) in id_to_product]
        
        return sorted_results

    def get_skus_for_product(self, product_id: str) -> List[Dict]:
        return _rows(self.conn.execute("SELECT * FROM skus WHERE product_id = ?", (product_id,)))

    def get_skus_by_base_code(self, base_code: str) -> List[Dict]:
        cursor = self.conn.execute(
            """SELECT * FROM skus WHERE upper(product_id) = upper(?)
                OR starts_with(upper(sku_code), upper(?) || '-')
                ORDER BY color, size, sku_code LIMIT 10""",
            (base_code, base_code),
        )
        return _rows(cursor)

    def get_product_by_id(self, product_id: str) -> Optional[Dict]:
        if not product_id:
            return None
        results = self.query_products_by_ids([product_id])
        return results[0] if results else None

    def get_provider_by_id(self, provider_id: str) -> Optional[Dict]:
        if not provider_id:
            return None
        row = self.conn.execute(
            "SELECT * FROM providers WHERE id = ? LIMIT 1",
            (provider_id,),
        ).fetchone()
        if not row:
            return None
        columns = [column[0] for column in self.conn.description]
        item = dict(zip(columns, row))
        item["countries_served"] = json.loads(item["countries_served"]) if item.get("countries_served") else []
        item["raw_json"] = json.loads(item["raw_json"]) if item.get("raw_json") else {}
        return item

    def get_sku_by_code(self, sku_code: str) -> Optional[Dict]:
        if not sku_code:
            return None
        row = self.conn.execute(
            "SELECT * FROM skus WHERE UPPER(sku_code) = UPPER(?) LIMIT 1",
            (sku_code,),
        ).fetchone()
        if not row:
            return None
        columns = [column[0] for column in self.conn.description]
        return dict(zip(columns, row))

    def get_all_products_raw(self) -> List[Dict]:
        """Lấy tất cả sản phẩm (dùng để build vector index)"""
        return _product_rows(self.conn.execute("SELECT * FROM products"))

    def close(self):
        self.conn.close()

# Singleton instance
db_store = DuckDBStore()
