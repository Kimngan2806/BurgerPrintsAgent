import json

from api.burgerprints import BurgerPrintsClient
from api.models import OrderAddress, OrderRequest
from cache.duckdb_store import db_store
from core.feature_flags import ff_manager
from harness import order_state
from harness.design_validator import validate_design_url
from search.hybrid_search import hybrid_searcher


bp_client = BurgerPrintsClient()


def slim_product(product: dict) -> dict:
    return {
        'image_url': _extract_product_image(product),
        'catalog_updated_at': product.get('cached_at'),
        'attribute_note': 'Material/category/techniques may be inferred from catalog description.',
        "id": product.get("id"),
        "name": product.get("name"),
        "display_name": product.get("display_name"),
        "category": product.get("category"),
        "material": product.get("material"),
        "print_techniques": product.get("print_techniques", []),
        "description": (product.get("description") or "")[:500],
    }


def slim_sku(sku: dict) -> dict:
    return {
        "sku_code": sku.get("sku_code"),
        "product_id": sku.get("product_id"),
        "color": sku.get("color"),
        "size": sku.get("size"),
        "material": sku.get("material"),
        "provider_id": sku.get("provider_id"),
        "provider_name": sku.get("provider_name"),
        "price": sku.get("price"),
        "second_price": sku.get("second_price"),
        "addition_price": sku.get("addition_price"),
    }


def _json_value(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _extract_product_image(product: dict) -> str | None:
    raw = _json_value(product.get("raw_json"), {})
    candidates = [
        raw.get("image"),
        raw.get("image_url"),
        raw.get("thumbnail"),
        raw.get("thumbnail_url"),
        raw.get("mockup_url"),
    ]
    images = raw.get("images") or raw.get("gallery") or []
    if isinstance(images, list):
        for item in images:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                candidates.extend([item.get("url"), item.get("src"), item.get("image_url")])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            return candidate
    return None


def _extract_design_requirements(product: dict, sku: dict) -> dict:
    raw_product = _json_value(product.get("raw_json"), {})
    raw_sku = _json_value(sku.get("raw_json"), {})
    requirement_keys = [
        "print_area",
        "design_size",
        "design_sizes",
        "design_resolution",
        "design_resolutions",
        "required_resolution",
        "template_size",
        "artwork_size",
    ]
    raw_requirements = {}
    for key in requirement_keys:
        if raw_product.get(key):
            raw_requirements[key] = raw_product.get(key)
        if raw_sku.get(key):
            raw_requirements[key] = raw_sku.get(key)

    return {
        "design_url_front_required": True,
        "design_url_front_format": "Public http/https image URL. Example: https://domain.com/design-front.png or .jpg",
        "local_or_private_url_allowed": False,
        'resolution_note': 'Chưa có quy chuẩn theo SKU/vị trí in đã xác minh. Không áp dụng danh sách kích thước chung.',
        'print_verified': False,
        "raw_requirements": raw_requirements,
    }


async def search_products(args: dict) -> dict:
    if not db_store.has_catalog():
        return {"results": [], "code": "CATALOG_UNAVAILABLE",
                "note": "Catalog chưa có dữ liệu đồng bộ. Không thể kết luận có hay không có sản phẩm khớp."}

    query = (args.get("query") or "").strip()
    category = (args.get("category") or "").strip()
    material = args.get("material")
    color = (args.get("color") or "").strip()
    size = (args.get("size") or "").strip()
    if color.casefold() in {"trắng", "trang"}:
        color = "White"
    if category.casefold() in {"áo thun", "ao thun", "áo phông", "ao phong", "tee", "t shirt", "tshirt"}:
        category = "t-shirt"
    # Keep the white SKU constraint while searching for the product type in the catalog.
    if color.casefold() == "white" and query.casefold() in {
        "áo thun trắng", "ao thun trang", "áo phông trắng", "white t-shirt", "white t shirt", "white tee",
    }:
        query = "t-shirt"
    if query.casefold() in {"áo thun", "ao thun", "áo phông", "ao phong", "t shirt", "tshirt"}:
        query = "t-shirt"

    if query and hybrid_searcher.is_ready and not (color or size):
        results = db_store.query_products_by_ids(hybrid_searcher.search(query, top_k=15))
        if category:
            results = [item for item in results if category.lower() in item.get("category", "").lower()]
        if material:
            results = [item for item in results if material.lower() in item.get("material", "").lower()]
    elif query or color or size:
        results = db_store.search_products_text(query, category, material, color=color, size=size)
    else:
        results = db_store.query_products(category=category, material=material, limit=15)
    max_price = args.get('max_price')
    choices = []
    for item in results:
        variants = db_store.get_skus_for_product(item['id'])
        variants = [v for v in variants if (not color or (v.get('color') or '').strip().casefold() == color.casefold())
                    and (not size or (v.get('size') or '').strip().casefold() == size.casefold())]
        if max_price is not None:
            variants = [v for v in variants if v.get('price') is not None and _price_at_most(v['price'], max_price)]
        if (color or size or max_price is not None) and not variants:
            continue
        choices.append({**slim_product(item), 'variants': [slim_sku(v) for v in variants[:50]], 'variant_count': len(variants),
                        'availability': 'not_checked', 'currency': 'USD'})
        if len(choices) == 3:
            break
    return {'results': choices, 'scope': 'Matching products within the searched catalog candidates',
            'note': 'No match: ask which one condition to relax; never change constraints automatically.'}


def _price_at_most(value, maximum):
    from decimal import Decimal, InvalidOperation
    try:
        price, limit = Decimal(str(value)), Decimal(str(maximum))
        return price.is_finite() and limit.is_finite() and price >= 0 and price <= limit
    except InvalidOperation:
        return False


async def get_sku_info(args: dict) -> dict:
    sku_code = args.get("sku_code") or args.get("sku")
    if sku_code:
        sku = db_store.get_sku_by_code(sku_code)
        if not sku:
            return {"ok": False, "code": "SKU_NOT_FOUND", "sku_code": sku_code}

        product = db_store.get_product_by_id(sku.get("product_id")) or {}
        provider = db_store.get_provider_by_id(sku.get("provider_id")) or {}
        known_countries = provider.get("countries_served") or []
        return {
            "ok": True,
            "sku": slim_sku(sku),
            "product": slim_product(product),
            "product_image_url": _extract_product_image(product),
            "design_template_url": product.get("design_url"),
            "available_sizes": product.get("available_sizes", []),
            "available_colors": product.get("available_colors", []),
            "provider": {
                "id": provider.get("id") or sku.get("provider_id"),
                "name": provider.get("name") or sku.get("provider_name"),
                "location": provider.get("location"),
                "known_countries_served": known_countries,
                "countries_source": "provider_cache" if known_countries else "not_available_in_current_api_cache",
            },
            "order_requirements": _extract_design_requirements(product, sku),
            "order_flow_hint": (
                "Show this SKU/product information to the user first. If product_image_url exists, render it as a Markdown image. "
                "Before create_order, ask for destination country, required address fields, quantity, and design_url_front."
            ),
        }

    skus = db_store.get_skus_for_product(args.get("product_id"))
    return {"skus": [slim_sku(sku) for sku in skus[:50]], "total": len(skus)}


async def get_base_cost(args: dict) -> dict:
    return await bp_client.get_base_cost(args.get("sku_codes", []))


async def get_shipping_cost(args: dict) -> dict:
    return await bp_client.get_shipping_cost(args.get("sku_codes", []), args.get("destination", ""))


async def get_production_time(args: dict) -> dict:
    return await bp_client.get_production_time(args.get("sku_codes", []))


async def get_shipping_time(args: dict) -> dict:
    return await bp_client.get_shipping_time(args.get("sku_codes", []), args.get("destination", ""))


async def check_sku_availability(args: dict) -> dict:
    return await bp_client.check_sku_availability(args.get("sku_codes", []))


async def check_provider_status(args: dict) -> dict:
    return await bp_client.check_provider_status(args.get("provider_ids", []))


async def check_region_support(args: dict) -> dict:
    return await bp_client.check_region_support(args.get("sku_codes", []), args.get("region", ""))


async def get_order_creation_status(args: dict) -> dict:
    from core.config import settings
    enabled = settings.ENABLE_ORDER_SUBMISSION and bool(settings.BURGERPRINTS_API_KEY)
    return {
        "ok": True,
        "code": "ORDER_CREATION_ENABLED" if enabled else "ORDER_CREATION_DISABLED",
        "enabled": enabled,
    }


async def prepare_order_review(args: dict) -> dict:
    session_id = str(args.get("_session_id") or "")
    sku_code = str(args.get("sku") or "").strip()
    sku = db_store.get_sku_by_code(sku_code)
    if not sku:
        return {"ok": False, "code": "SKU_NOT_FOUND", "error": f"SKU `{sku_code}` was not found."}
    if session_id and not order_state.was_sku_presented(session_id, sku_code):
        return {
            "ok": False,
            "code": "SKU_PRESENTATION_REQUIRED",
            "error": f"Call get_sku_info for SKU `{sku_code}` and show product details before preparing order review.",
        }

    address = args.get("address") or {}
    required_address_fields = ["name", "street", "city", "state", "zip", "country"]
    missing = [field for field in required_address_fields if not address.get(field)]
    if missing:
        return {"ok": False, "code": "ADDRESS_REQUIRED", "missing_fields": missing}

    design_url = str(args.get("design_url_front") or "").strip()
    design_validation = await validate_design_url(design_url)
    if not design_validation.ok:
        return design_validation.to_dict()

    product = db_store.get_product_by_id(sku.get("product_id")) or {}
    summary = {
        "sku": slim_sku(sku),
        "product": slim_product(product),
        "quantity": int(args.get("quantity") or 1),
        "destination": address,
        "base_price": sku.get("price"),
        "second_item_price": sku.get("second_price"),
        "design": {
            "design_url_front": design_url,
            "validation": design_validation.to_dict(),
        },
        "shipping_note": "Shipping cost/availability is not available from current pre-order API cache and will be confirmed by BurgerPrints during order creation.",
    }
    token = order_state.create_order_review(session_id, args, summary)
    return {
        "ok": True,
        "code": "ORDER_REVIEW_READY",
        "order_review_token": token,
        "summary": summary,
        "required_confirmation": f"Xác nhận đặt SKU {sku_code}",
    }


async def create_order(args: dict) -> dict:
    return {'ok': False, 'code': 'DRAFT_CONFIRMATION_REQUIRED', 'error': 'Use the workspace review and confirmation flow.'}


async def update_draft(args: dict) -> dict:
    from core.chat_context import owner_context, conversation_context
    from core.workspace import workspace
    from services.commerce import DraftInput, draft_body
    from fastapi import HTTPException
    owner, conversation_id = owner_context.get(), conversation_context.get()
    if not owner or not conversation_id:
        return {'ok': False, 'error': 'Authentication required.'}
    conversation = workspace.get(owner, conversation_id, 'conversation')
    ident = conversation.get('draft_id')
    if not ident:
        draft = workspace.create(owner, 'draft', DraftInput(version=1).model_dump(exclude={'version'}))
        ident = draft['id']
        body = {k: v for k, v in conversation.items() if k not in {'id', 'version', 'updated_at'}}
        body['draft_id'] = ident
        workspace.update(owner, conversation_id, 'conversation', conversation['version'], body)
    else:
        draft = workspace.get(owner, ident, 'draft')
    if not args.get('lines') and not args.get('address'):
        return {'ok': True, 'draft': draft}
    try:
        # Full replacement uses the version returned by the preceding read.
        data = DraftInput(version=args.get('version', 0), lines=args.get('lines', draft['lines']),
                          address=args.get('address', draft['address']), acknowledge_unverified_print=False)
        body = draft_body(data)
        for line in body['lines']:
            if line['asset_id']:
                workspace.get(owner, line['asset_id'], 'asset')
        result = workspace.update(owner, ident, 'draft', data.version, body)
        workspace.event(owner, 'draft_saved', ident)
        return {'ok': True, 'draft': result, 'next': 'Open the draft panel to review and confirm.'}
    except HTTPException as exc:
        return {'ok': False, 'error': exc.detail}


async def calculate_profit(args: dict) -> dict:
    from services.commerce import profit
    return profit(args)
