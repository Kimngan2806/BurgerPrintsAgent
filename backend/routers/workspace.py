import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from core.config import settings
from core.workspace import workspace, current_owner
from harness.design_validator import fetch_design, validate_design_bytes, MAX_DESIGN_BYTES
from services.commerce import (DraftInput, draft_body, review_draft, submit_draft,
                               submission_dict, finish_submission, profit)

router = APIRouter()


class Credentials(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=256)


@router.post('/auth/{action}')
def auth(action: str, credentials: Credentials, response: Response, request: Request):
    if action not in {'login', 'register'}:
        raise HTTPException(404)
    key = 'auth:' + hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
    with workspace.connect() as db:
        count = db.execute('SELECT COUNT(*) FROM events WHERE owner=? AND created>?', (key, time.time()-60)).fetchone()[0]
    if count >= 15:
        raise HTTPException(429, 'Thử đăng nhập quá nhiều lần. Vui lòng đợi một phút.')
    workspace.event(key, action)
    owner = (workspace.register if action == 'register' else workspace.login)(credentials.name, credentials.password)
    response.set_cookie('bp_session', workspace.token(owner), httponly=True,
                        secure=settings.COOKIE_SECURE, samesite='strict', max_age=86400 * 7, path='/')
    return {'name': credentials.name, 'store': settings.STORE_DISPLAY_NAME, 'mode': 'single_store_demo'}


@router.post('/logout')
def logout(request: Request, response: Response):
    with workspace.connect() as db:
        db.execute('DELETE FROM tokens WHERE hash=?',
                   (hashlib.sha256(request.cookies.get('bp_session', '').encode()).hexdigest(),))
    response.delete_cookie('bp_session', path='/')
    return {'ok': True}


@router.get('/me')
def me(owner=Depends(current_owner)):
    with workspace.connect() as db:
        name = db.execute('SELECT name FROM users WHERE id=?', (owner,)).fetchone()['name']
    return {'name': name, 'store': settings.STORE_DISPLAY_NAME, 'mode': 'single_store_demo',
            'sandbox': settings.ORDER_SANDBOX, 'submission_enabled': settings.ENABLE_ORDER_SUBMISSION}


@router.get('/work/{kind}')
def list_work(kind: str, owner=Depends(current_owner)):
    if kind not in {'conversation', 'draft', 'asset', 'support'}:
        raise HTTPException(404)
    results = workspace.list(owner, kind)
    if kind == 'asset':
        results = [public_asset(row) for row in results]
    return results


@router.post('/conversations')
def new_conversation(owner=Depends(current_owner)):
    return workspace.create(owner, 'conversation', {'title': 'Chat mới', 'messages': [], 'draft_id': None, 'criteria': {}})


@router.get('/conversations/{ident}')
def conversation(ident: str, owner=Depends(current_owner)):
    return workspace.get(owner, ident, 'conversation')


class DraftLink(BaseModel):
    draft_id: str


@router.put('/conversations/{ident}/draft')
def link_draft(ident: str, data: DraftLink, owner=Depends(current_owner)):
    workspace.get(owner, data.draft_id, 'draft')
    with workspace.connect() as db:
        if db.execute('SELECT 1 FROM chat_leases WHERE id=? AND expires>?', (ident, time.time())).fetchone():
            raise HTTPException(409, 'Đợi lượt trả lời hiện tại hoàn tất trước khi chuyển đơn nháp của hội thoại.')
    conversation = workspace.get(owner, ident, 'conversation')
    body = {k: v for k, v in conversation.items() if k not in {'id', 'version', 'updated_at'}}
    body['draft_id'] = data.draft_id
    return workspace.update(owner, ident, 'conversation', conversation['version'], body)


@router.get('/products')
async def products(q: str = '', color: str = '', size: str = '', max_price: float | None = None, owner=Depends(current_owner)):
    from agent.tool_handlers import search_products, get_sku_info
    from cache.duckdb_store import db_store
    if q and db_store.get_sku_by_code(q):
        exact = await get_sku_info({'sku_code': q})
        from agent.tool_handlers import _price_at_most
        variant = exact['sku']
        if (color and (variant.get('color') or '').casefold() != color.casefold()
            or size and (variant.get('size') or '').casefold() != size.casefold()
            or max_price is not None and not _price_at_most(variant.get('price'), max_price)):
            return {'results': []}
        return {'results': [{**exact['product'], 'image_url': exact['product_image_url'],
                             'variants': [exact['sku']], 'currency': 'USD'}]}
    workspace.event(owner, 'search')
    return await search_products({'query': q, 'color': color, 'size': size, 'max_price': max_price})


@router.get('/sku')
async def sku_info(code: str, owner=Depends(current_owner)):
    from agent.tool_handlers import get_sku_info
    from api.burgerprints import BurgerPrintsClient
    result = await get_sku_info({'sku_code': code})
    if result.get('ok'):
        result['availability'] = await BurgerPrintsClient().check_sku_availability([result['sku']['sku_code']])
        workspace.event(owner, 'sku_selected', result['sku']['sku_code'])
    return result


@router.post('/drafts')
def new_draft(owner=Depends(current_owner)):
    return workspace.create(owner, 'draft', DraftInput(version=1).model_dump(exclude={'version'}))


@router.get('/drafts/{ident}')
def get_draft(ident: str, owner=Depends(current_owner)):
    return workspace.get(owner, ident, 'draft')


@router.put('/drafts/{ident}')
def save_draft(ident: str, data: DraftInput, owner=Depends(current_owner)):
    workspace.get(owner, ident, 'draft')
    body = draft_body(data)
    for line in body['lines']:
        if line['asset_id']:
            workspace.get(owner, line['asset_id'], 'asset')
    result = workspace.update(owner, ident, 'draft', data.version, body)
    workspace.event(owner, 'draft_saved', ident)
    return result


class Version(BaseModel):
    version: int


@router.post('/drafts/{ident}/review')
async def review(ident: str, data: Version, owner=Depends(current_owner)):
    return await review_draft(owner, ident, data.version)


class Confirmation(BaseModel):
    review_id: str
    confirmed: bool


@router.post('/drafts/{ident}/submit')
async def submit(ident: str, data: Confirmation, owner=Depends(current_owner)):
    if data.confirmed is not True:
        raise HTTPException(422, 'Cần bấm xác nhận bản duyệt đơn.')
    return await submit_draft(owner, ident, data.review_id)


def public_asset(row):
    return {k: v for k, v in row.items() if k not in {'share_token', 'storage_name'}}


def store_asset(owner, data, name, tags='', previous_id=''):
    validation = validate_design_bytes(data)
    if not validation.ok:
        raise HTTPException(422, validation.message)
    previous = workspace.get(owner, previous_id, 'asset') if previous_id else None
    sha = hashlib.sha256(data).hexdigest()
    folder = Path(settings.FILE_STORAGE_PATH)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / sha).write_bytes(data)
    asset = workspace.create(owner, 'asset', {'name': name[:160], 'tags': tags[:300],
        'sha256': sha, 'storage_name': sha, 'share_token': secrets.token_urlsafe(32),
        'file_version': previous['file_version'] + 1 if previous else 1,
        'previous_id': previous_id, 'validation': validation.to_dict()})
    workspace.event(owner, 'design_uploaded', asset['id'])
    return public_asset(asset)


@router.post('/assets/upload')
async def upload(file: UploadFile, previous_id: str = '', owner=Depends(current_owner)):
    data = await file.read(MAX_DESIGN_BYTES + 1)
    await file.close()
    return store_asset(owner, data, file.filename or 'Thiết kế', previous_id=previous_id)


class ImportFile(BaseModel):
    url: str = Field(max_length=2048)
    name: str = Field(min_length=1, max_length=160)
    previous_id: str = ''


@router.post('/assets/import')
async def import_file(data: ImportFile, owner=Depends(current_owner)):
    try:
        content = await fetch_design(data.url)
    except Exception:
        raise HTTPException(422, 'Link không đọc được. Kiểm tra quyền công khai hoặc tải file trực tiếp.')
    return store_asset(owner, content, data.name, previous_id=data.previous_id)


class AssetEdit(BaseModel):
    version: int
    name: str = Field(min_length=1, max_length=160)
    tags: str = Field(max_length=300)


@router.patch('/assets/{ident}')
def edit_asset(ident: str, data: AssetEdit, owner=Depends(current_owner)):
    row = workspace.get(owner, ident, 'asset')
    body = {k: v for k, v in row.items() if k not in {'id', 'version', 'updated_at'}}
    body.update(name=data.name, tags=data.tags)
    return public_asset(workspace.update(owner, ident, 'asset', data.version, body))


def file_response(row):
    return FileResponse(Path(settings.FILE_STORAGE_PATH) / row['storage_name'],
                        media_type=row['validation']['content_type'],
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=0'})


@router.get('/assets/{ident}/preview')
def preview(ident: str, owner=Depends(current_owner)):
    return file_response(workspace.get(owner, ident, 'asset'))


@router.get('/files/{token}')
def fulfillment_file(token: str):
    # Opaque capability is only disclosed in a reviewed fulfillment request.
    with workspace.connect() as db:
        rows = db.execute("SELECT * FROM documents WHERE kind='asset' AND json_extract(body,'$.share_token')=?", (token,)).fetchone()
    if not rows:
        raise HTTPException(404)
    return file_response(workspace.decode(rows))


@router.get('/orders')
def orders(owner=Depends(current_owner)):
    with workspace.connect() as db:
        db.execute("UPDATE submissions SET state='verifying' WHERE owner=? AND state='sending' AND updated<?", (owner, time.time()-180))
        rows = db.execute('SELECT * FROM submissions WHERE owner=? ORDER BY updated DESC', (owner,)).fetchall()
    return [submission_dict(row) for row in rows]


@router.post('/orders/{reference}/refresh')
async def refresh_order(reference: str, owner=Depends(current_owner)):
    from api.burgerprints import BurgerPrintsClient
    with workspace.connect() as db:
        row = db.execute('SELECT * FROM submissions WHERE reference=? AND owner=?', (reference, owner)).fetchone()
    if not row:
        raise HTTPException(404)
    client = BurgerPrintsClient()
    if not settings.BURGERPRINTS_API_KEY:
        raise HTTPException(409, 'Chưa kết nối BurgerPrints.')
    result = json.loads(row['result'])
    fetch_started = time.time()
    order_id = result.get('order_id')
    try:
        if not order_id:
            payload = json.loads(row['payload'])
            response = await client._get('/order', {'reference': reference, 'sandbox': str(payload['sandbox']).lower(), 'page_size': '50'})
            matches = response.get('data', [])
            if isinstance(matches, dict):
                matches = matches.get('result', [])
            # Exact reference only; absence does not prove rejection after a timeout.
            matches = [m for m in matches if reference in {m.get('reference_order_id'), m.get('reference_order'), m.get('reference_id')}]
            if len(matches) != 1 or not matches[0].get('id'):
                raise HTTPException(409, 'Chưa xác minh được duy nhất một đơn. Giữ nguyên trạng thái; liên hệ hỗ trợ.')
            order_id = matches[0]['id']
        detail = await client._get('/order/' + quote(str(order_id), safe=''))
        if detail.get('errors') or detail.get('code', 200) != 200:
            raise ValueError('Invalid order detail')
        tracking = await client._get('/order/' + quote(str(order_id), safe='') + '/tracking')
        result = {'order_id': order_id, 'source': 'BurgerPrints API', 'checked_at': time.time(),
                  'detail': detail.get('data', detail), 'tracking': tracking.get('data', []),
                  'note': 'Tracking không xác nhận diễn biến giao hàng ngoài dữ liệu nguồn.'}
        # Concurrent refreshes cannot overwrite a more recently fetched snapshot.
        with workspace.connect() as db:
            db.execute("UPDATE submissions SET state='created', result=?, updated=? WHERE reference=? AND updated<=?",
                       (json.dumps(result), fetch_started, reference, fetch_started))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Không cập nhật được nguồn. Dữ liệu đã lưu được giữ nguyên; thử lại việc tra cứu.')
    return {'reference': reference, 'state': 'created', 'result': result}


@router.post('/callbacks/{reference}/{token}')
async def tracking_callback(reference: str, token: str, request: Request):
    with workspace.connect() as db:
        row = db.execute('SELECT * FROM submissions WHERE reference=?', (reference,)).fetchone()
    expected = json.loads(row['payload']).get('callback_url', '').rsplit('/', 1)[-1] if row else ''
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(404)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413)
    receipt = hashlib.sha256(reference.encode() + body).hexdigest()
    with workspace.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS callback_receipts(id TEXT PRIMARY KEY, updated REAL, done INTEGER)')
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM callback_receipts WHERE id=?', (receipt,)).fetchone()
        if previous and (previous['done'] or previous['updated'] > time.time() - 120):
            return {'received': True, 'duplicate': True}
        db.execute('INSERT OR REPLACE INTO callback_receipts VALUES(?,?,0)', (receipt, time.time()))
    try:
        # Callback content is a hint, never the authority for status/ownership.
        await refresh_order(reference, row['owner'])
        with workspace.connect() as db:
            db.execute('UPDATE callback_receipts SET done=1,updated=? WHERE id=?', (time.time(), receipt))
        workspace.event(row['owner'], 'tracking_updated', reference)
    except BaseException:
        with workspace.connect() as db:
            db.execute('DELETE FROM callback_receipts WHERE id=?', (receipt,))
        raise
    return {'received': True, 'reconciled': True}


class SupportInput(BaseModel):
    message: str = Field(min_length=5, max_length=6000)
    reference: str = ''


@router.post('/support')
def support(data: SupportInput, owner=Depends(current_owner)):
    if data.reference:
        with workspace.connect() as db:
            if not db.execute('SELECT 1 FROM submissions WHERE reference=? AND owner=?', (data.reference, owner)).fetchone():
                raise HTTPException(404)
    return workspace.create(owner, 'support', {'message': data.message, 'reference': data.reference,
        'status': 'saved_locally', 'note': 'Đã lưu yêu cầu trong ứng dụng; chưa gửi ra ngoài. Chưa thực hiện hủy/hoàn tiền.'})


@router.post('/profit')
def calculate_profit(data: dict, owner=Depends(current_owner)):
    return profit(data)


@router.get('/metrics')
def metrics(owner=Depends(current_owner)):
    with workspace.connect() as db:
        rows = db.execute('SELECT name,COUNT(*) AS count FROM events WHERE owner=? GROUP BY name', (owner,)).fetchall()
    return {'events': [dict(row) for row in rows], 'note': 'Số liệu tài khoản hiện tại, chưa quy kết doanh thu tăng thêm.'}
