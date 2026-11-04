import asyncio
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from core.config import settings
from core.workspace import Workspace
from services import commerce
from routers import workspace as routes
from api.burgerprints import BurgerPrintsClient
from cache.duckdb_store import db_store
from harness.design_validator import validate_design_bytes


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = Workspace(tmp_path / 'transactions.sqlite3')
    monkeypatch.setattr(commerce, 'workspace', store)
    monkeypatch.setattr(routes, 'workspace', store)
    import core.workspace
    monkeypatch.setattr(core.workspace, 'workspace', store)
    monkeypatch.setattr(settings, 'FILE_STORAGE_PATH', str(tmp_path / 'files'))
    monkeypatch.setattr(settings, 'PUBLIC_FILE_BASE_URL', 'https://files.example.test')
    monkeypatch.setattr(settings, 'ENABLE_ORDER_SUBMISSION', True)
    monkeypatch.setattr(settings, 'ORDER_SANDBOX', True)
    monkeypatch.setattr(settings, 'BURGERPRINTS_API_KEY', 'test-key-never-sent')
    monkeypatch.setattr(db_store, 'get_sku_by_code', lambda code: {
        'sku_code': code.upper(), 'product_id': 'TEE', 'price': '5.50', 'cached_at': time.time(),
        'color': 'Black', 'size': 'M'} if code.upper() in {'TEE-BLACK-M', 'MUG-WHITE-L'} else None)
    # Use a fixed snapshot timestamp, like the actual catalog cache.
    stamp = time.time()
    original = db_store.get_sku_by_code
    monkeypatch.setattr(db_store, 'get_sku_by_code', lambda code: {**original(code), 'cached_at': stamp} if original(code) else None)
    monkeypatch.setattr(db_store, 'get_product_by_id', lambda code: {'name': 'Test product'})
    async def stock(self, codes):
        return {code: {'status': 'not_listed_out_of_stock', 'checked_at': time.time()} for code in codes}
    monkeypatch.setattr(BurgerPrintsClient, 'check_sku_availability', stock)
    app = FastAPI()
    app.include_router(routes.router, prefix='/api')
    from routers import chat
    monkeypatch.setattr(chat, 'workspace', store)
    app.include_router(chat.router, prefix='/api')
    return store, TestClient(app)


def register(client, name='seller-a'):
    result = client.post('/api/auth/register', json={'name': name, 'password': 'a-long-password-123'})
    assert result.status_code == 200, result.text


def image_bytes():
    data = io.BytesIO()
    Image.new('RGBA', (24, 32), (255, 0, 0, 255)).save(data, format='PNG')
    return data.getvalue()


def ready_draft(client):
    asset = client.post('/api/assets/upload', files={'file': ('art.png', image_bytes(), 'image/png')}).json()
    draft = client.post('/api/drafts').json()
    result = client.put('/api/drafts/' + draft['id'], json={
        'version': draft['version'], 'lines': [
            {'sku': 'TEE-BLACK-M', 'quantity': 2, 'asset_id': asset['id']},
            {'sku': 'MUG-WHITE-L', 'quantity': 1, 'asset_id': asset['id']}],
        'address': {'name': 'Seller', 'street': '1 Main St', 'city': 'Paris', 'country': 'FR', 'zip': '75001'},
        'acknowledge_unverified_print': True})
    assert result.status_code == 200, result.text
    return result.json(), asset


def review(client, draft):
    result = client.post(f"/api/drafts/{draft['id']}/review", json={'version': draft['version']})
    assert result.status_code == 200, result.text
    return result.json()


def test_auth_scope_and_durable_restore(env):
    store, client = env
    assert client.get('/api/work/draft').status_code == 401
    register(client)
    draft, asset = ready_draft(client)
    token = client.cookies.get('bp_session')
    owner = store.owner(token)
    reopened = Workspace(store.path)
    assert reopened.get(owner, draft['id'], 'draft')['lines'][0]['quantity'] == 2
    register(client, 'seller-b')
    assert client.get(f"/api/drafts/{draft['id']}").status_code == 404
    assert client.get(f"/api/assets/{asset['id']}/preview").status_code == 404
    assert client.get('/api/work/asset').json() == []
    assert client.get('/api/orders').json() == []


def test_version_conflict_and_confirmation_invalidation(env, monkeypatch):
    _, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    update = {k:v for k,v in draft.items() if k not in {'id','updated_at'}}
    update['lines'][0]['quantity'] = 3
    assert client.put(f"/api/drafts/{draft['id']}", json=update).status_code == 200
    assert client.put(f"/api/drafts/{draft['id']}", json=update).status_code == 409
    result = client.post(f"/api/drafts/{draft['id']}/submit", json={'review_id': approved['id'], 'confirmed': True})
    assert result.status_code == 409


def test_success_double_click_multiple_skus_and_no_fake_mockup(env, monkeypatch):
    _, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    calls = []
    async def post(self, endpoint, payload):
        calls.append(payload)
        return {'is_success': True, 'order_id': 'BP-123'}
    monkeypatch.setattr(BurgerPrintsClient, '_post', post)
    url = f"/api/drafts/{draft['id']}/submit"
    body = {'review_id': approved['id'], 'confirmed': True}
    first = client.post(url, json=body)
    second = client.post(url, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()['reference'] == second.json()['reference']
    assert first.json()['state'] == 'created'
    assert len(calls) == 1
    assert calls[0]['sandbox'] is True
    assert len(calls[0]['items']) == 2
    assert 'mockup_url_front' not in calls[0]['items'][0]
    assert calls[0]['reference_order_id'] == first.json()['reference']


@pytest.mark.parametrize('response', [
    {'_uncertain': True, 'message': 'timeout'}, {'is_success': True}, {'code': 503}, {}])
def test_uncertain_never_retries_or_reports_success(env, monkeypatch, response):
    store, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    calls = []
    async def post(self, endpoint, payload):
        calls.append(payload)
        return response
    monkeypatch.setattr(BurgerPrintsClient, '_post', post)
    body = {'review_id': approved['id'], 'confirmed': True}
    url = f"/api/drafts/{draft['id']}/submit"
    assert client.post(url, json=body).json()['state'] == 'verifying'
    assert client.post(url, json=body).json()['state'] == 'verifying'
    assert len(calls) == 1
    update = {k:v for k,v in draft.items() if k not in {'id','updated_at'}}
    assert client.put(f"/api/drafts/{draft['id']}", json=update).status_code == 409


def test_two_workers_claim_single_submission(env, monkeypatch):
    store, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    owner = store.owner(client.cookies.get('bp_session'))
    calls = []
    async def post(self, endpoint, payload):
        calls.append(payload)
        await asyncio.sleep(.05)
        return {'is_success': True, 'order_id': 'CONCURRENT-1'}
    monkeypatch.setattr(BurgerPrintsClient, '_post', post)
    def worker():
        return asyncio.run(commerce.submit_draft(owner, draft['id'], approved['id']))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert len(calls) == 1
    assert results[0]['reference'] == results[1]['reference']


def test_asset_file_versions_and_print_level(env):
    _, client = env
    register(client)
    _, first = ready_draft(client)
    second = client.post('/api/assets/upload?previous_id=' + first['id'],
                         files={'file': ('new.png', image_bytes(), 'image/png')}).json()
    assert second['id'] != first['id'] and second['file_version'] == 2
    assert second['validation']['print_verified'] is False
    assert client.get(f"/api/assets/{first['id']}/preview").content == image_bytes()
    broken = client.post('/api/assets/upload', files={'file': ('fake.png', b'not an image', 'image/png')})
    assert broken.status_code == 422
    assert validate_design_bytes(image_bytes()).code == 'BASIC_VALID_PRINT_UNVERIFIED'


def test_profit_unknowns_zero_revenue_and_exact_decimal():
    result = commerce.profit({'sale_price': '10.10', 'quantity': 3, 'discount_percent': '10', 'production_per_item': '2.20'})
    assert result['revenue'] == '27.27'
    assert result['estimated_profit'] == '20.67'
    assert 'shipping_total' in result['unknown_costs']
    assert commerce.profit({'sale_price': 0})['margin_percent'] is None
    for bad in ['NaN', '-1', 'Infinity']:
        with pytest.raises(HTTPException):
            commerce.profit({'sale_price': bad})


def test_exact_sku_rejects_substrings_and_invalid_combinations(tmp_path, monkeypatch):
    from cache.duckdb_store import DuckDBStore
    monkeypatch.setattr(settings, 'DUCKDB_PATH', str(tmp_path / 'exact.duckdb'))
    store = DuckDBStore()
    try:
        store.seed_skus([{'sku_code': 'TEE-Black-M', 'product_id': 'TEE'}])
        assert store.get_sku_by_code('TEE') is None
        assert store.get_sku_by_code('TEE-Black-L') is None
        assert store.get_sku_by_code('tee-black-m')['sku_code'] == 'TEE-Black-M'
    finally:
        store.close()


def test_atomic_catalog_preserves_last_good_on_failure(tmp_path, monkeypatch):
    from cache.duckdb_store import DuckDBStore
    monkeypatch.setattr(settings, 'DUCKDB_PATH', str(tmp_path / 'atomic.duckdb'))
    store = DuckDBStore()
    try:
        old = [{'id': 'OLD', 'name': 'Old', 'category': 'tee'}]
        store.replace_snapshot(old, [{'sku_code': 'OLD-M', 'product_id': 'OLD'}], [])
        def fail(*args, **kwargs):
            raise RuntimeError('write interrupted')
        monkeypatch.setattr(store, 'seed_skus', fail)
        with pytest.raises(RuntimeError):
            store.replace_snapshot([{'id':'NEW', 'name':'New','category':'tee'}], [{'sku_code':'NEW-M','product_id':'NEW'}], [])
        assert store.get_product_by_id('OLD')
        assert store.get_sku_by_code('OLD-M')
        assert not store.get_product_by_id('NEW')
    finally:
        store.close()


def test_callback_duplicates_and_old_event_never_supply_status(env, monkeypatch):
    store, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    async def post(self, endpoint, payload):
        return {'is_success': True, 'order_id': 'BP-CALLBACK'}
    monkeypatch.setattr(BurgerPrintsClient, '_post', post)
    sent = client.post(f"/api/drafts/{draft['id']}/submit", json={'review_id': approved['id'], 'confirmed': True}).json()
    with store.connect() as db:
        row = db.execute('SELECT payload FROM submissions WHERE reference=?', (sent['reference'],)).fetchone()
    callback_url = json.loads(row['payload'])['callback_url'].replace(settings.PUBLIC_FILE_BASE_URL, '')
    calls = []
    async def get(self, endpoint, params=None):
        calls.append(endpoint)
        if endpoint.endswith('/tracking'):
            return {'code': 200, 'data': [{'tracking_carrier': 'USPS', 'tracking_code': '123'}]}
        return {'code': 200, 'data': {'id': 'BP-CALLBACK', 'state': 'shipped'}}
    monkeypatch.setattr(BurgerPrintsClient, '_get', get)
    assert client.post(callback_url, json={'status': 'delivered'}).status_code == 200
    assert client.post(callback_url, json={'status': 'delivered'}).json()['duplicate'] is True
    assert len(calls) == 2
    assert client.post(callback_url, json={'status': 'queued', 'timestamp': 1}).status_code == 200
    order = client.get('/api/orders').json()[0]
    assert order['result']['detail']['state'] == 'shipped'
    assert client.post(callback_url + 'bad', json={}).status_code == 404


def test_price_change_requires_new_review(env, monkeypatch):
    _, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    original = db_store.get_sku_by_code
    monkeypatch.setattr(db_store, 'get_sku_by_code', lambda code: {**original(code), 'price': '7.00'})
    result = client.post(f"/api/drafts/{draft['id']}/submit", json={'review_id': approved['id'], 'confirmed': True})
    assert result.status_code == 409


def test_account_cannot_submit_other_accounts_review(env):
    _, client = env
    register(client)
    draft, _ = ready_draft(client)
    approved = review(client, draft)
    register(client, 'different-seller')
    assert client.post(f"/api/drafts/{draft['id']}/submit", json={'review_id': approved['id'], 'confirmed': True}).status_code == 404


def test_paginated_stock_and_unknown_are_not_stock_guarantees(monkeypatch):
    async def get(self, endpoint, params):
        return {'code': 200, 'data': {'total': 2, 'result': [{'sku': ['TEE-BLACK-M']} if params['page']=='1' else {'sku': ['OTHER-SKU']}]}}
    monkeypatch.setattr(settings, 'BURGERPRINTS_API_KEY', 'fake')
    monkeypatch.setattr(BurgerPrintsClient, '_get', get)
    monkeypatch.setattr(db_store, 'get_sku_by_code', lambda sku: {'sku_code': sku})
    result = asyncio.run(BurgerPrintsClient().check_sku_availability(['TEE-BLACK-M', 'MUG-WHITE-L']))
    assert result['TEE-BLACK-M']['status'] == 'out_of_stock'
    assert result['MUG-WHITE-L']['status'] == 'not_listed_out_of_stock'
    async def broken(*args, **kwargs):
        raise RuntimeError('offline')
    monkeypatch.setattr(BurgerPrintsClient, '_get', broken)
    assert asyncio.run(BurgerPrintsClient().check_sku_availability(['MUG-WHITE-L']))['MUG-WHITE-L']['status'] == 'unknown'


def test_chat_persists_messages_and_structured_criteria(env, monkeypatch):
    _, client = env
    register(client)
    conversation = client.post('/api/conversations').json()
    from core.chat_context import tool_events, owner_context
    async def fake_chat(session_id, message):
        assert owner_context.get()
        tool_events.get().append({'type': 'tool_result', 'tool': 'search_products',
            'criteria': {'color': 'Black'}, 'result': {'results': [{'id': 'TEE', 'name': 'Test tee'}]}})
        yield {'data': json.dumps({'text': 'Có một lựa chọn trong catalog.'})}
        yield {'data': '[DONE]'}
    monkeypatch.setattr('agent.gemini_agent.process_chat', fake_chat)
    response = client.post('/api/chat/stream', json={'session_id': conversation['id'], 'message': 'Tìm áo màu đen'})
    assert response.status_code == 200 and '[DONE]' in response.text
    restored = client.get('/api/conversations/' + conversation['id']).json()
    assert restored['messages'][0]['role'] == 'user'
    assert restored['messages'][1]['role'] == 'agent'
    assert restored['criteria']['color'] == 'Black'
    assert restored['products'][0]['id'] == 'TEE'
    register(client, 'other-chat-owner')
    assert client.post('/api/chat/stream', json={'session_id': conversation['id'], 'message': 'Đọc lại'}).status_code == 404
