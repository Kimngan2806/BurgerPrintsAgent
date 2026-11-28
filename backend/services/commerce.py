"""Business decisions live here; the model cannot confirm or submit an order."""
import hashlib
import json
import secrets
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import anyio
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict
from starlette.concurrency import run_in_threadpool
from core.config import normalize_store_display_name, settings
from core.workspace import workspace


class Line(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=10000, strict=True)
    asset_id: str = ''
    position: str = 'front'


class Address(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = ''
    street: str = ''
    city: str = ''
    state: str = ''
    zip: str = ''
    country: str = 'US'
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=40)


class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    lines: list[Line] = Field(default_factory=list, max_length=50)
    address: Address = Field(default_factory=Address)
    acknowledge_unverified_print: bool = False


def draft_body(data):
    from cache.duckdb_store import db_store
    body = data.model_dump(exclude={'version'})
    for line in body['lines']:
        record = db_store.get_sku_by_code(line['sku'])
        if not record:
            raise HTTPException(422, f"SKU phải khớp chính xác: {line['sku']}. Hãy tìm và chọn lại.")
        if line['position'] != 'front':
            raise HTTPException(422, 'Chọn vị trí in mặt trước cho sản phẩm.')
        line['sku'] = record['sku_code']
    return body


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def build_review(owner, draft, *, chat_confirmation=False):
    from cache.duckdb_store import db_store
    from api.burgerprints import BurgerPrintsClient
    if not draft['lines']:
        raise HTTPException(422, 'Đơn nháp chưa có sản phẩm.')
    address = Address.model_validate(draft['address']).model_dump()
    address = {key: value.strip() for key, value in address.items()}
    required = ['name', 'street', 'city', 'zip', 'country'] + (['state'] if address['country'].upper() == 'US' else [])
    if chat_confirmation:
        required += ['email', 'phone']
    missing = [key for key in required if not address.get(key, '').strip()]
    if missing:
        labels = {'name': 'tên người nhận', 'street': 'số nhà và tên đường', 'city': 'thành phố',
                  'zip': 'mã bưu chính', 'country': 'quốc gia', 'state': 'bang', 'email': 'email',
                  'phone': 'số điện thoại'}
        raise HTTPException(422, 'Vui lòng bổ sung ' + ', '.join(labels[key] for key in missing) + '.')
    if address['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', address['email']):
        raise HTTPException(422, 'Email người nhận chưa đúng định dạng.')
    if address['phone'] and (not re.fullmatch(r'\+?[\d().\s-]+', address['phone'])
                             or not 7 <= sum(ch.isdigit() for ch in address['phone']) <= 15):
        raise HTTPException(422, 'Số điện thoại người nhận cần có từ 7 đến 15 chữ số.')
    if len(address['country']) != 2 or not address['country'].isalpha():
        raise HTTPException(422, 'Quốc gia cần mã ISO hai chữ cái, ví dụ US, VN.')
    if address['country'].upper() == 'US' and not re.fullmatch(r'\d{5}(-\d{4})?', address['zip'].strip()):
        raise HTTPException(422, 'Mã bưu chính US cần 5 chữ số hoặc ZIP+4, ví dụ 90210 hoặc 90210-1234.')
    if not chat_confirmation and not draft['acknowledge_unverified_print']:
        raise HTTPException(422, 'Chưa có quy chuẩn theo SKU. Cần tự đối chiếu template và xác nhận trước khi duyệt đơn.')
    if any(not line.get('asset_id') for line in draft['lines']):
        missing = [str(index) for index, line in enumerate(draft['lines'], 1) if not line.get('asset_id')]
        raise HTTPException(422, 'Tải hoặc chọn ảnh mặt trước cho dòng ' + ', '.join(missing) + ' trong đơn nháp.')
    assets = []
    for index, line in enumerate(draft['lines'], 1):
        asset = await run_in_threadpool(workspace.get, owner, line['asset_id'], 'asset')
        if not (Path(settings.FILE_STORAGE_PATH) / asset['storage_name']).is_file():
            raise HTTPException(422, f"Không tìm thấy tệp ảnh ở dòng {index} ({line['sku']}). Tải ảnh lên lại để duyệt đơn.")
        assets.append(asset)
    availability = await BurgerPrintsClient().check_sku_availability([line['sku'] for line in draft['lines']])
    lines = []
    for line, asset in zip(draft['lines'], assets):
        record = db_store.get_sku_by_code(line['sku'])
        if not record:
            raise HTTPException(422, 'SKU không còn trong catalog. Chọn lại biến thể.')
        if availability.get(line['sku'], {}).get('status') == 'out_of_stock':
            raise HTTPException(422, f"SKU {line['sku']} đang có trong danh sách hết hàng.")
        if not record.get('cached_at') or time.time() - record['cached_at'] > settings.CATALOG_MAX_AGE_SECONDS:
            raise HTTPException(422, 'Catalog đã cũ. Đồng bộ lại trước khi duyệt đơn.')
        if not settings.PUBLIC_FILE_BASE_URL.startswith('https://'):
            raise HTTPException(422, 'Cần cấu hình PUBLIC_FILE_BASE_URL HTTPS để fulfillment đọc file đã lưu.')
        product = db_store.get_product_by_id(record['product_id']) or {}
        lines.append({**line, 'color': record.get('color'), 'size': record.get('size'),
            'product_name': product.get('name'), 'provider': record.get('provider_name'),
            'catalog_price': record.get('price'), 'currency': 'USD', 'price_source': 'catalog',
            'catalog_updated_at': record.get('cached_at'), 'availability': availability.get(line['sku']),
            'file': {'name': asset['name'], 'sha256': asset['sha256'], 'validation': asset['validation']},
            'design_url_front': settings.PUBLIC_FILE_BASE_URL.rstrip('/') + '/api/files/' + asset['share_token']})
    return {'store': settings.display_store_name, 'sandbox': settings.ORDER_SANDBOX,
        'lines': lines, 'address': {**address, 'country': address['country'].upper()},
        'services': [], 'unknown_costs': ['shipping', 'tax', 'additional fees', 'multi-item price rules'],
        'cost_note': 'Giá catalog theo SKU; chưa phải tổng đơn. Chưa áp dụng 2nd_price/addition_price.',
        'transaction_notice': settings.STORE_TRANSACTION_NOTICE or 'Sandbox kiểm thử. Chưa xác minh cấu hình thanh toán tự động cho đơn thật.'}


async def review_draft(owner, ident, version, *, chat_confirmation=False):
    draft = await run_in_threadpool(workspace.get, owner, ident, 'draft')
    if draft['version'] != version:
        raise HTTPException(409, 'Đơn đã thay đổi. Tải lại và duyệt phiên bản mới.')
    summary = await build_review(owner, draft, chat_confirmation=chat_confirmation)
    review = await run_in_threadpool(workspace.create, owner, 'review', {
        'draft_id': ident, 'draft_version': version, 'summary': summary,
        'expires_at': time.time() + 600, 'chat_confirmation': chat_confirmation,
    })
    await run_in_threadpool(workspace.event, owner, 'order_review', ident)
    return review


def existing_submission(owner, ident, version):
    with workspace.connect() as db:
        row = db.execute('SELECT * FROM submissions WHERE draft=? AND version=? AND owner=?',
                         (ident, version, owner)).fetchone()
    return submission_dict(row) if row else None


def reserve_submission(owner, ident, version, reference, payload):
    with workspace.connect(lock=f'draft:{ident}') as db:
        row = db.execute('SELECT version FROM documents WHERE id=? AND owner=? AND kind=?',
                         (ident, owner, 'draft')).fetchone()
        if not row or row['version'] != version:
            raise HTTPException(409, 'Đơn đã thay đổi. Duyệt lại.')
        existing = db.execute('SELECT * FROM submissions WHERE draft=? AND version=?', (ident, version)).fetchone()
        if existing:
            return submission_dict(existing)
        db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?)',
                   (reference, owner, ident, version, 'sending', json.dumps(payload), '{}', time.time()))


async def submit_draft(owner, ident, review_id, *, chat_confirmation=False):
    from api.burgerprints import BurgerPrintsClient
    review = await run_in_threadpool(workspace.get, owner, review_id, 'review')
    if review['draft_id'] != ident:
        raise HTTPException(409, 'Bản duyệt không thuộc đơn này. Duyệt lại đơn.')
    if bool(review.get('chat_confirmation')) != chat_confirmation:
        raise HTTPException(409, 'Hãy xác nhận ở nơi bạn đã xem bản duyệt đơn.')
    existing = await run_in_threadpool(existing_submission, owner, ident, review['draft_version'])
    if existing:
        return existing
    if review['expires_at'] < time.time():
        raise HTTPException(409, 'Bản duyệt đã hết hạn. Duyệt lại đơn.')
    draft = await run_in_threadpool(workspace.get, owner, ident, 'draft')
    if draft['version'] != review['draft_version']:
        raise HTTPException(409, 'Đơn đã sửa sau khi duyệt. Cần xác nhận phiên bản mới.')
    summary = await build_review(owner, draft, chat_confirmation=chat_confirmation)
    def stable(value):
        value = json.loads(json.dumps(value))
        value['store'] = normalize_store_display_name(value['store'])
        # Older reviews predate the optional contact fields.
        value['address'] = Address.model_validate(value['address']).model_dump()
        for line in value['lines']:
            line.pop('availability', None)
        return value
    if digest(stable(summary)) != digest(stable(review['summary'])):
        raise HTTPException(409, 'Giá, file hoặc cấu hình đã thay đổi. Duyệt lại đơn.')
    if not settings.ENABLE_ORDER_SUBMISSION or not settings.BURGERPRINTS_API_KEY:
        raise HTTPException(409, 'Chưa bật kết nối gửi đơn. Đơn nháp đã được giữ lại.')
    if not settings.ORDER_SANDBOX and not settings.STORE_TRANSACTION_NOTICE.strip():
        raise HTTPException(409, 'Cần cấu hình hệ quả thanh toán store trước khi gửi đơn thật.')
    reference = 'bpa-' + secrets.token_hex(16)
    address = summary['address']
    payload = {'reference_order_id': reference, 'sandbox': summary['sandbox'],
        'shipping_name': address['name'], 'shipping_address1': address['street'],
        'shipping_city': address['city'], 'shipping_state': address['state'],
        'shipping_zip': address['zip'], 'shipping_country': address['country'],
        'fulfillment_partner': 'BurgerPrintsAgent',
        'items': [{'catalog_sku': l['sku'], 'quantity': l['quantity'],
                   'design_url_front': l['design_url_front']} for l in summary['lines']]}
    if address['email']:
        payload['shipping_email'] = address['email']
    if address['phone']:
        payload['shipping_phone'] = address['phone']
    callback_token = secrets.token_urlsafe(32)
    payload['callback_url'] = settings.PUBLIC_FILE_BASE_URL.rstrip('/') + '/api/callbacks/' + reference + '/' + callback_token
    with anyio.CancelScope(shield=True):
        existing = await run_in_threadpool(reserve_submission, owner, ident, review['draft_version'], reference, payload)
    if existing:
        return existing
    try:
        response = await BurgerPrintsClient()._post('/order', payload)
        if response.get('is_success') is True and response.get('order_id'):
            state = 'created'
        elif response.get('is_success') is False and not response.get('_uncertain'):
            state = 'rejected'
        else:
            state = 'verifying'
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(finish_submission, reference, state, response)
    except BaseException:
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(finish_submission, reference, 'verifying', {
                'message': 'Chưa rõ kết quả. Đối chiếu mã tham chiếu; không gửi lại.',
            })
        raise
    await run_in_threadpool(workspace.event, owner, 'order_' + state, ident)
    return {'reference': reference, 'state': state, 'result': response}


def finish_submission(reference, state, result):
    with workspace.connect() as db:
        db.execute('UPDATE submissions SET state=?,result=?,updated=? WHERE reference=?',
                   (state, json.dumps(result), time.time(), reference))


def submission_dict(row):
    return {'reference': row['reference'], 'draft_id': row['draft'], 'state': row['state'],
            'updated_at': row['updated'], 'result': json.loads(row['result'])}


def profit(data):
    def amount(value):
        try:
            value = Decimal(str(value))
            if not value.is_finite() or value < 0 or value > Decimal('1000000000000'):
                raise ValueError()
            return value
        except (InvalidOperation, ValueError):
            raise HTTPException(422, 'Giá và chi phí phải là số không âm hữu hạn.')
    quantity = data.get('quantity', 1)
    if type(quantity) is not int or not 1 <= quantity <= 10000:
        raise HTTPException(422, 'Số lượng phải là số nguyên từ 1 đến 10000.')
    discount = amount(data.get('discount_percent', 0))
    if discount > 100:
        raise HTTPException(422, 'Giảm giá phải từ 0 đến 100%.')
    revenue = amount(data.get('sale_price')) * quantity * (1 - discount / 100)
    costs, unknown = {}, []
    for key in ['production_per_item', 'shipping_total', 'platform_total', 'other_total']:
        value = data.get(key)
        if value is None or value == '':
            unknown.append(key)
        else:
            costs[key] = amount(value) * (quantity if key == 'production_per_item' else 1)
    total_costs = sum(costs.values(), Decimal('0'))
    earnings = revenue - total_costs
    fmt = lambda v: str(v.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    return {'revenue': fmt(revenue), 'costs': {k: fmt(v) for k, v in costs.items()},
        'estimated_profit': fmt(earnings), 'total_known_costs': fmt(total_costs), 'profit_per_item': fmt(earnings / quantity),
        'margin_percent': fmt(earnings / revenue * 100) if revenue else None,
        'unknown_costs': unknown, 'source': 'seller_inputs', 'currency': 'USD',
        'note': 'Lợi nhuận dự kiến theo chi phí đã nhập; chưa phải lợi nhuận ròng.'}
