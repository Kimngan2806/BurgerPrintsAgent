import httpx
import asyncio
import logging
import re
import time
import unicodedata
from html import unescape
from typing import List, Dict, Any, Optional
from core.config import settings
from api.models import Product, SKU, OrderRequest, OrderResponse
from harness.api_response_policy import parse_burgerprints_error

logger = logging.getLogger(__name__)

class BurgerPrintsClient:
    def __init__(self):
        self.base_url = settings.BURGERPRINTS_API_BASE_URL.rstrip('/')
        self.headers = {
            "api-key": settings.BURGERPRINTS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.timeout = 10.0

    async def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                url = f"{self.base_url}/{endpoint.lstrip('/')}"
                if not settings.BURGERPRINTS_API_KEY:
                    logger.warning("No API key set, using mock data mode")
                    return self._mock_data(endpoint, params)
                    
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Error calling GET {endpoint}: {e}")
                if not settings.BURGERPRINTS_API_KEY:
                    return self._mock_data(endpoint, params)
                raise

    async def _post(self, endpoint: str, json_data: Dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                url = f"{self.base_url}/{endpoint.lstrip('/')}"
                if not settings.BURGERPRINTS_API_KEY:
                    return {"success": True, "message": "Mock Order Created", "data": {"id": "ORD-123"}}
                    
                response = await client.post(url, headers=self.headers, json=json_data)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Error calling POST {endpoint}: {e}")
                try:
                    return e.response.json()
                except Exception:
                    return {"is_success": False, "message": e.response.text or str(e), "errors": []}
            except Exception as e:
                logger.error(f"Error calling POST {endpoint}: {e}")
                return {"is_success": False, "message": str(e), "errors": []}

    # Mock Data Generator for stability when API fails or no key
    def _mock_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if "product" in endpoint and "pricing" not in endpoint:
            return {
                "data": [
                    {"id": "P1", "name": "Classic Unisex T-Shirt", "category": "t-shirt", "material": "100% Cotton", "style": "classic", "print_techniques": ["DTG"]},
                    {"id": "P2", "name": "Premium Hoodie", "category": "hoodie", "material": "Polyester blend", "style": "oversized", "print_techniques": ["DTG", "Embroidery"]},
                    {"id": "P3", "name": "Ceramic Mug 11oz", "category": "mug", "material": "Ceramic", "style": "standard", "print_techniques": ["Sublimation"]},
                    {"id": "P4", "name": "Classic Cotton Polo Shirt", "category": "polo", "material": "Cotton", "style": "classic collar", "print_techniques": ["DTG", "Embroidery"]},
                ]
            }
        elif "catalog/skus" in endpoint:
            return {
                "data": [
                    {"sku_code": "TS-BLK-M-US", "product_id": "P1", "color": "Black", "size": "M", "material": "Cotton", "provider_id": "US-A"},
                    {"sku_code": "TS-WHT-L-EU", "product_id": "P1", "color": "White", "size": "L", "material": "Cotton", "provider_id": "EU-A"},
                    {"sku_code": "HD-BLK-XL-US", "product_id": "P2", "color": "Black", "size": "XL", "material": "Polyester", "provider_id": "US-B"},
                    {"sku_code": "PO-WHT-M-VN", "product_id": "P4", "color": "White", "size": "M", "material": "Cotton", "provider_id": "VN-A"},
                    {"sku_code": "PO-BLK-L-VN", "product_id": "P4", "color": "Black", "size": "L", "material": "Cotton", "provider_id": "VN-A"},
                ]
            }
        elif "pricing" in endpoint:
            return {"data": {sku: 7.80 if "PO" in sku else 5.20 if "TS" in sku else 12.50 for sku in (params.get("sku_codes", "").split(",") if params else [])}}
        elif "shipping-cost" in endpoint:
            return {"data": {sku: 3.50 if "US" in sku else 4.20 for sku in (params.get("sku_codes", "").split(",") if params else [])}}
        elif "production-time" in endpoint:
            return {"data": {sku: "2-3 days" for sku in (params.get("sku_codes", "").split(",") if params else [])}}
        elif "shipping-time" in endpoint:
            return {"data": {sku: "3-5 days" for sku in (params.get("sku_codes", "").split(",") if params else [])}}
        elif "inventory" in endpoint or "status" in endpoint:
            return {"data": {code: "active" for code in (params.get("sku_codes", "").split(",") if params and "sku_codes" in params else params.get("provider_ids", "").split(",") if params else [])}}
        elif "regions" in endpoint:
            return {"data": {sku: True for sku in (params.get("sku_codes", "").split(",") if params else [])}}
        return {"data": []}

    # ==========================================
    # CACHEABLE DATA ENDPOINTS (Sync to DuckDB)
    # ==========================================
    async def get_products(self) -> List[Product]:
        products, _, _ = await self.get_catalog_snapshot(fetch_details=False)
        return [Product(**p) for p in products]

    async def get_all_skus(self) -> List[SKU]:
        _, skus, _ = await self.get_catalog_snapshot(fetch_details=True)
        return [SKU(**s) for s in skus]

    async def get_catalog_snapshot(self, fetch_details: bool = True) -> tuple[List[Dict], List[Dict], List[Dict]]:
        products = await self._fetch_all_product_bases()
        if not fetch_details:
            return products, [], []

        product_details = []
        skus = []
        providers_by_id: Dict[str, Dict[str, Any]] = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            semaphore = asyncio.Semaphore(12)

            async def fetch_detail(product: Dict[str, Any]) -> Dict[str, Any]:
                short_code = product.get("id")
                if not short_code or not settings.BURGERPRINTS_API_KEY:
                    return product
                async with semaphore:
                    try:
                        url = f"{self.base_url}/product/{short_code}"
                        response = await client.get(url, headers=self.headers)
                        response.raise_for_status()
                        detail = (response.json().get("data") or {})
                        return self._normalize_product(detail or product)
                    except Exception as e:
                        logger.warning(f"Failed to fetch product detail {short_code}: {e}")
                        return product

            product_details = await asyncio.gather(*(fetch_detail(p) for p in products))

        for product in product_details:
            for variation in product.get("variations", []):
                provider_id = str(variation.get("partner_id") or "")
                provider_name = str(variation.get("partner_name") or "")
                if provider_id and provider_id not in providers_by_id:
                    providers_by_id[provider_id] = {
                        "id": provider_id,
                        "name": provider_name or provider_id,
                        "location": self._infer_location(product.get("id", "")),
                        "countries_served": [],
                    }
                skus.append({
                    "sku_code": variation.get("sku"),
                    "product_id": product.get("id"),
                    "color": variation.get("color"),
                    "size": variation.get("size"),
                    "material": product.get("material", ""),
                    "provider_id": provider_id,
                    "size_id": variation.get("size_id"),
                    "color_id": variation.get("color_id"),
                    "color_hex": variation.get("color_hex"),
                    "price": variation.get("price"),
                    "second_price": variation.get("2nd_price"),
                    "addition_price": variation.get("addition_price"),
                    "provider_name": provider_name,
                    "raw_json": variation,
                })

        return product_details, skus, list(providers_by_id.values())

    async def _fetch_all_product_bases(self) -> List[Dict[str, Any]]:
        if not settings.BURGERPRINTS_API_KEY:
            res = self._mock_data("/product")
            return [self._normalize_product(p) for p in res.get("data", [])]

        products = []
        page = 1
        page_size = 500
        while True:
            res = await self._get("/product", {"page": str(page), "page_size": str(page_size)})
            data = res.get("data") or {}
            if isinstance(data, list):
                return [self._normalize_product(item) for item in data]
            result = data.get("result") or []
            products.extend(self._normalize_product(item) for item in result)
            total = int(data.get("total") or len(products))
            if len(products) >= total or not result:
                break
            page += 1
        logger.info(f"Fetched {len(products)} BurgerPrints products from /product")
        return products

    def _normalize_product(self, item: Dict[str, Any]) -> Dict[str, Any]:
        short_code = item.get("short_code") or item.get("id") or ""
        html_desc = item.get("html_desc") or ""
        desc = item.get("desc") or self._strip_html(html_desc)
        return {
            "id": short_code,
            "name": item.get("name") or item.get("display_name") or short_code,
            "display_name": item.get("display_name") or "",
            "catalog_id": item.get("catalog_id") or "",
            "category": self._infer_category(item.get("name", "")),
            "description": desc,
            "html_desc": html_desc,
            "material": self._infer_material(desc),
            "style": "",
            "print_techniques": self._infer_print_techniques(desc),
            "url": item.get("url") or "",
            "design_type": item.get("design_type") or "",
            "design_url": item.get("design_url"),
            "available_sizes": item.get("available_sizes") or [],
            "available_colors": item.get("available_colors") or [],
            "variations": item.get("variations") or [],
            "raw_json": item,
        }

    def _strip_html(self, text: str) -> str:
        return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()

    def _infer_category(self, name: str) -> str:
        lowered = name.lower()
        if "hoodie" in lowered:
            return "hoodie"
        if "sweatshirt" in lowered or "sweater" in lowered:
            return "sweatshirt"
        if "tank top" in lowered:
            return "tank top"
        if "shirt" in lowered or "tee" in lowered or "t-shirt" in lowered:
            return "t-shirt"
        if "mug" in lowered:
            return "mug"
        return "other"

    def _infer_material(self, desc: str) -> str:
        lowered = desc.lower()
        materials = []
        for material in ["cotton", "polyester", "fleece", "ceramic", "canvas"]:
            if material in lowered:
                materials.append(material)
        return ", ".join(materials)

    def _infer_print_techniques(self, desc: str) -> List[str]:
        lowered = desc.lower()
        techniques = []
        for label in ["DTG", "DTF", "Sublimation", "Embroidery", "Screen Printing", "Heat Transfer"]:
            if label.lower() in lowered:
                techniques.append(label)
        return techniques

    def _infer_location(self, product_id: str) -> str:
        code = product_id.upper()
        if code.startswith("US"):
            return "US"
        if code.startswith("EU"):
            return "EU"
        return ""
        
    async def get_all_providers(self) -> List[Dict]:
        res = await self._get("/catalog/providers")
        # Mock providers if none returned
        if not res.get("data"):
            return [
                {"id": "US-A", "name": "BurgerPrints US-A", "location": "US", "countries_served": ["US", "CA"]},
                {"id": "US-B", "name": "BurgerPrints US-B", "location": "US", "countries_served": ["US"]},
                {"id": "EU-A", "name": "BurgerPrints EU", "location": "EU", "countries_served": ["UK", "DE", "FR"]},
                {"id": "VN-A", "name": "BurgerPrints Vietnam", "location": "VN", "countries_served": ["VN"]}
            ]
        return res.get("data", [])

    # ==========================================
    # REALTIME DATA ENDPOINTS (Called by Agent Tools)
    # ==========================================
    async def get_base_cost(self, sku_codes: List[str]) -> Dict[str, Any]:
        # BurgerPrints public docs expose base prices inside /product/{id}
        # variations, which are synced into DuckDB. There is no documented
        # standalone /pricing endpoint.
        from cache.duckdb_store import db_store

        prices = {}
        for sku in sku_codes:
            record = db_store.get_sku_by_code(sku)
            if record and record.get("price") is not None:
                prices[sku] = record.get("price")
        return prices

    async def get_shipping_cost(self, sku_codes: List[str], destination: str) -> Dict[str, Any]:
        return {
            "_unsupported": "BurgerPrints public API docs do not expose a shipping-cost endpoint."
        }

    async def get_production_time(self, sku_codes: List[str]) -> Dict[str, Any]:
        return {
            "_unsupported": "BurgerPrints public API docs do not expose a production-time endpoint."
        }

    async def get_shipping_time(self, sku_codes: List[str], destination: str) -> Dict[str, Any]:
        return {
            "_unsupported": "BurgerPrints public API docs do not expose a shipping-time endpoint."
        }

    async def check_sku_availability(self, sku_codes: List[str]) -> Dict[str, Any]:
        from cache.duckdb_store import db_store

        return {
            sku: "present_in_catalog" if db_store.get_sku_by_code(sku) else "not_found"
            for sku in sku_codes
        }

    async def check_provider_status(self, provider_ids: List[str]) -> Dict[str, Any]:
        return {
            "_unsupported": "BurgerPrints public API docs do not expose a provider-status endpoint."
        }

    async def check_region_support(self, sku_codes: List[str], region: str) -> Dict[str, Any]:
        return {
            "_unsupported": "BurgerPrints public API docs do not expose a region-support endpoint."
        }

    async def create_order(self, order: OrderRequest) -> OrderResponse:
        shipping_country = self._normalize_country_code(order.address.country)
        reference_order_id = f"burgerprints-agent-{order.sku}-{int(time.time())}"
        payload = {
            "shipping_name": order.address.name,
            "shipping_address1": order.address.street,
            "shipping_address2": "",
            "shipping_city": order.address.city,
            "shipping_state": order.address.state,
            "shipping_zip": order.address.zip,
            "shipping_country": shipping_country,
            "reference_order_id": reference_order_id,
            "items": [
                {
                    "catalog_sku": order.sku,
                    "quantity": order.quantity,
                    "design_url_front": order.design_url_front,
                    "mockup_url_front": order.mockup_url_front or order.design_url_front,
                }
            ],
            "sandbox": False,
            "fulfillment_partner": "BurgerPrintsAgent",
        }
        res = await self._post("/order", payload)
        data = res.get("data") if isinstance(res.get("data"), dict) else {}
        order_details = data.get("order") if isinstance(data.get("order"), dict) else data
        shipping_services = (
            res.get("shipping_services")
            or data.get("shipping_services")
            or order_details.get("shipping_services")
            or []
        )
        order_id = (
            res.get("order_id")
            or res.get("id")
            or data.get("order_id")
            or data.get("id")
            or order_details.get("order_id")
            or order_details.get("id")
            or ""
        )
        is_success = bool(res.get("is_success") or res.get("success"))
        common = {
            "reference_order_id": reference_order_id,
            "sku": order.sku,
            "quantity": order.quantity,
            "destination": {
                "name": order.address.name,
                "street": order.address.street,
                "city": order.address.city,
                "state": order.address.state,
                "zip": order.address.zip,
                "country": shipping_country,
            },
            "design": {
                "design_url_front": order.design_url_front,
                "mockup_url_front": order.mockup_url_front or order.design_url_front,
            },
            "shipping_services": shipping_services if isinstance(shipping_services, list) else [],
            "order_details": order_details if isinstance(order_details, dict) else {},
            "api_response": res if isinstance(res, dict) else {"raw": res},
        }
        if is_success:
            return OrderResponse(
                order_id=str(order_id or "UNKNOWN"),
                status="created",
                message=res.get("message") or data.get("message") or "Order placed successfully",
                **common,
            )
        return OrderResponse(
            order_id=str(order_id),
            status="error",
            message=res.get("message") or data.get("message") or str(res.get("errors") or "Unknown error"),
            normalized_error=parse_burgerprints_error(res if isinstance(res, dict) else {"raw": res}),
            **common,
        )

    def _normalize_country_code(self, country: str) -> str:
        value = (country or "").strip()
        if len(value) == 2:
            return value.upper()

        decomposed = unicodedata.normalize("NFD", value.lower())
        without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
        normalized = re.sub(r"[^a-z]", "", without_marks)
        country_map = {
            "unitedstates": "US",
            "unitedstatesofamerica": "US",
            "usa": "US",
            "us": "US",
            "america": "US",
            "vietnam": "VN",
            "vietman": "VN",
            "canada": "CA",
            "australia": "AU",
            "unitedkingdom": "GB",
            "uk": "GB",
            "greatbritain": "GB",
            "germany": "DE",
            "france": "FR",
            "spain": "ES",
            "italy": "IT",
            "netherlands": "NL",
        }
        return country_map.get(normalized, value.upper())
