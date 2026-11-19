import json
import re
from decimal import Decimal, InvalidOperation
from starlette.concurrency import run_in_threadpool

from api.burgerprints import BurgerPrintsClient
from api.models import OrderAddress, OrderRequest
from cache.duckdb_store import db_store
from core.feature_flags import ff_manager
from harness import order_state
from harness.design_validator import validate_design_url
from search.hybrid_search import hybrid_searcher


bp_client = BurgerPrintsClient()
YOUTH_PRODUCT = re.compile(r'\b(?:kids?|youth|child(?:ren)?|toddler|baby|infant|boys?|girls?)\b', re.I)


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
    if args.get('compare_hoodie_id'):
        return _compare_premium_hoodie(args['compare_hoodie_id'], args.get('compare_sku'))

    query = (args.get("query") or "").strip()
    category = (args.get("category") or "").strip()
    material = args.get("material")
    color = (args.get("color") or "").strip()
    size = (args.get("size") or "").strip()
    prefer_budget = args.get('prefer_budget') is True
    adult_only = args.get('adult_only') is True
    catalog_market = 'US' if args.get('catalog_market') == 'US' else ''
    choice_limit = 1 if args.get('single_recommendation') is True else 3
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

    if query and hybrid_searcher.is_ready and not (color or size or prefer_budget or adult_only or catalog_market):
        results = db_store.query_products_by_ids(hybrid_searcher.search(query, top_k=15))
        if category:
            results = [item for item in results if category.lower() in item.get("category", "").lower()]
        if material:
            results = [item for item in results if material.lower() in item.get("material", "").lower()]
    elif query or color or size or prefer_budget or adult_only or catalog_market:
        results = db_store.search_products_text(
            query, category, material, limit=None if (prefer_budget or adult_only or catalog_market) else 15,
            color=color, size=size,
        )
    else:
        results = db_store.query_products(category=category, material=material, limit=15)
    max_price = args.get('max_price')
    choices = []
    budget_choices = []
    for item in results:
        children = bool(YOUTH_PRODUCT.search(item.get('name') or ''))
        if (adult_only and children) or (catalog_market and not item['id'].upper().startswith(catalog_market)):
            continue
        variants = db_store.get_skus_for_product(item['id'])
        variants = [v for v in variants if (not color or (v.get('color') or '').strip().casefold() == color.casefold())
                    and (not size or (v.get('size') or '').strip().casefold() == size.casefold())
                    and (not catalog_market or v['sku_code'].upper().startswith(catalog_market))]
        if max_price is not None:
            variants = [v for v in variants if v.get('price') is not None and _price_at_most(v['price'], max_price)]
        if (color or size or max_price is not None or catalog_market) and not variants:
            continue
        if prefer_budget:
            known_prices = [(price, v) for v in variants if (price := _catalog_price(v.get('price'))) is not None and price > 0]
            if not known_prices:
                continue
            cheapest, variant = min(known_prices, key=lambda entry: (entry[0], entry[1]['sku_code']))
            choice = _product_choice(item, variants, variant)
        else:
            choice = _product_choice(item, variants)
        if prefer_budget:
            budget_choices.append((children, cheapest, choice))
        else:
            choices.append(choice)
        if not prefer_budget and len(choices) == choice_limit:
            break
    if prefer_budget:
        choices = [item for _, _, item in sorted(budget_choices, key=lambda entry: entry[:2])[:choice_limit]]
    return {'results': choices, 'scope': 'Matching products within the searched catalog candidates',
            'note': 'No match: ask which one condition to relax; never change constraints automatically.'}


def _product_choice(product, variants, recommended=None):
    if recommended:
        variants = [recommended, *(v for v in variants if v['sku_code'] != recommended['sku_code'])]
    entry = {**slim_product(product), 'variants': [slim_sku(v) for v in variants[:50]],
             'variant_count': len(variants), 'availability': 'not_checked', 'currency': 'USD'}
    if recommended:
        entry['recommended_sku'] = recommended['sku_code']
    return entry


def _compare_premium_hoodie(product_id, sku_code):
    original = db_store.get_product_by_id(product_id)
    if not original or original.get('category') != 'hoodie':
        return {'results': []}
    original_variants = db_store.get_skus_for_product(product_id)
    original_sku = next((v for v in original_variants if v['sku_code'] == sku_code), None)
    base_price = _catalog_price(original_sku['price']) if original_sku else None
    if base_price is None or base_price <= 0:
        return {'results': []}

    ranked = []
    for candidate in db_store.search_products_text('hoodie premium', category='hoodie', limit=None):
        name = candidate.get('name') or ''
        if (candidate['id'] == product_id or not re.search(r'\bpremium\b', name, re.I)
                or YOUTH_PRODUCT.search(name)):
            continue
        variants = db_store.get_skus_for_product(candidate['id'])
        prices = [(price, v['sku_code'], v) for v in variants
                  if (price := _catalog_price(v.get('price'))) is not None and price > base_price]
        if prices:
            price, _, variant = min(prices, key=lambda row: row[:2])
            same_style = ('zip' in name.casefold()) == ('zip' in original['name'].casefold())
            ranked.append((not same_style, price, candidate['id'], _product_choice(candidate, variants, variant)))
    if not ranked:
        return {'results': []}
    premium = min(ranked, key=lambda row: row[:3])[3]
    return {'results': [_product_choice(original, original_variants, original_sku), premium]}


def _catalog_price(value):
    try:
        price = Decimal(str(value))
        return price if price.is_finite() and price >= 0 else None
    except InvalidOperation:
        return None


def _price_at_most(value, maximum):
    price, limit = _catalog_price(value), _catalog_price(maximum)
    return price is not None and limit is not None and price <= limit


async def get_sku_info(args: dict) -> dict:
    sku_code = (args.get("sku_code") or args.get("sku") or "").strip()
    if sku_code:
        sku = db_store.get_sku_by_code(sku_code)
        if not sku:
            options = db_store.get_skus_by_base_code(sku_code)
            if options:
                return {'ok': False, 'code': 'SKU_VARIANT_REQUIRED', 'base_code': sku_code,
                        'options': [slim_sku(option) for option in options],
                        'note': 'Show a few exact options and have the seller choose a complete SKU. Never choose one automatically.'}
            if not db_store.has_catalog():
                return {'ok': False, 'code': 'CATALOG_UNAVAILABLE', 'note': 'Catalog chưa đồng bộ.'}
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
                "Ask for quantity, then save the draft and collect recipient, contact, address and design information."
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


def chat_draft(owner, conversation_id):
    from core.workspace import workspace
    from services.commerce import Address, DraftInput
    conversation = workspace.get(owner, conversation_id, 'conversation')
    ident = conversation.get('draft_id')
    if not ident:
        first_draft = DraftInput(version=1, address=Address(country=''))
        draft = workspace.create(owner, 'draft', first_draft.model_dump(exclude={'version'}))
        ident = draft['id']
        body = {k: v for k, v in conversation.items() if k not in {'id', 'version', 'updated_at'}}
        body['draft_id'] = ident
        workspace.update(owner, conversation_id, 'conversation', conversation['version'], body)
    else:
        draft = workspace.get(owner, ident, 'draft')
    return conversation, draft


async def update_draft(args: dict) -> dict:
    from core.chat_context import owner_context, conversation_context
    from core.workspace import workspace
    from services.commerce import DraftInput, draft_body
    from fastapi import HTTPException
    from pydantic import ValidationError
    owner, conversation_id = owner_context.get(), conversation_context.get()
    if not owner or not conversation_id:
        return {'ok': False, 'error': 'Authentication required.'}
    conversation, draft = await run_in_threadpool(chat_draft, owner, conversation_id)
    ident = draft['id']
    if 'lines' not in args and 'address' not in args:
        return {'ok': True, 'draft': draft}
    try:
        if args.get('version') != draft['version']:
            return {'ok': False, 'error': 'Đơn nháp đã thay đổi. Hãy đọc lại phiên bản hiện tại trước khi lưu.'}
        address = {**draft['address'], **(args.get('address') or {})}
        lines = [dict(line) for line in args.get('lines', draft['lines'])]
        design_urls = [line.pop('design_url_front', '') for line in lines]
        for line in lines:
            if 'asset_id' not in line:
                previous = [old for old in draft['lines'] if old['sku'].casefold() == line.get('sku', '').casefold()]
                if len(previous) == 1:
                    line['asset_id'] = previous[0]['asset_id']
        data = DraftInput(version=draft['version'], lines=lines, address=address, acknowledge_unverified_print=False)
        body = draft_body(data)
        seller_messages = [message['content'] for message in conversation.get('messages', [])[-16:]
                           if message['role'] == 'user']
        current_skus = {line['sku'].casefold() for line in draft['lines']}
        for line in body['lines']:
            sku = line['sku']
            selection = re.compile(rf'(?<![\w-]){re.escape(sku)}(?![\w-])', re.IGNORECASE)
            if sku.casefold() not in current_skus and not any(selection.search(message) for message in seller_messages):
                return {'ok': False, 'error': f'Vui lòng nhắn lại mã SKU đầy đủ bạn chọn: {sku}.'}
            if line['asset_id']:
                await run_in_threadpool(workspace.get, owner, line['asset_id'], 'asset')
        if any(design_urls):
            from routers.workspace import ImportFile, import_file

            provided_urls = {
                url.rstrip('.,;!?') for message in seller_messages
                for url in re.findall(r'https?://[^\s<>\[\]()]+', message)
            }
            if any(url and (url not in provided_urls or len(url) > 2048) for url in design_urls):
                return {'ok': False, 'error': 'Vui lòng gửi URL ảnh thiết kế công khai để mình gắn vào đơn nháp.'}
            imported_assets = {}
            for line, url in zip(body['lines'], design_urls):
                if url:
                    if url not in imported_assets:
                        asset = await import_file(ImportFile(url=url, name='Thiết kế mặt trước'), owner=owner)
                        imported_assets[url] = asset['id']
                    line['asset_id'] = imported_assets[url]
        result = await run_in_threadpool(workspace.update, owner, ident, 'draft', data.version, body)
        await run_in_threadpool(workspace.event, owner, 'draft_saved', ident)
        return {'ok': True, 'updated': True, 'draft': result,
                'next': 'Ask for any missing fields. The app displays the review and confirmation instructions when ready.'}
    except HTTPException as exc:
        return {'ok': False, 'error': exc.detail}
    except (ValidationError, TypeError, ValueError, AttributeError):
        return {'ok': False, 'error': 'Thông tin đơn nháp chưa đúng định dạng. Kiểm tra SKU, số lượng và địa chỉ.'}


async def calculate_profit(args: dict) -> dict:
    from services.commerce import profit
    return profit(args)
