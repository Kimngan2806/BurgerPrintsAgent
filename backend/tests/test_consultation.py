import asyncio
import json

import httpx
import pytest

from agent import gemini_agent, tool_handlers
from agent.language import reply_language
from cache.duckdb_store import DuckDBStore
from core.chat_context import owner_context
from core.config import settings


@pytest.mark.parametrize('message, previous, expected', [
    ('Có hoodie nào budget-friendly cho beginner không?', [], 'vi'),
    ('Co hoodie nao budget friendly cho nguoi moi khong?', [], 'vi'),
    ('Any budget-friendly hoodies for a beginner?', [], 'en'),
    ('5', ['Can you find a hoodie?'], 'en'),
    ('5', ['Mình muốn đặt áo thun.'], 'vi'),
    ('Any hoodie màu trắng?', ['What is a hoodie?'], 'vi'),
])
def test_reply_language_uses_current_user_language(message, previous, expected):
    assert reply_language(message, previous) == expected


async def answer(message):
    events = [event['data'] async for event in gemini_agent.process_chat('consultation-test', message)]
    return ''.join(json.loads(event).get('text', '') for event in events if event != '[DONE]')


def test_definition_remains_localized_and_does_not_invent_products():
    vi = asyncio.run(answer('Tôi mới bán, gross margin nghĩa là gì?'))
    en = asyncio.run(answer('What is gross margin in print on demand?'))
    assert 'Biên lợi nhuận gộp' in vi and '40%' in vi and 'gross margin' not in vi.lower() and 'SKU' not in vi
    assert 'Gross margin' in en and '40%' in en


def test_budget_hoodie_consultation_uses_catalog_prices_and_one_adult_recommendation(monkeypatch):
    monkeypatch.setattr(settings, 'DUCKDB_PATH', ':memory:')
    store = DuckDBStore()
    monkeypatch.setattr(tool_handlers, 'db_store', store)
    products = [{'id': f'HOOD-{i}', 'name': f'A{i:02d} Hoodie', 'category': 'hoodie'} for i in range(16)] + [
        {'id': 'KID', 'name': 'Kids Hoodie', 'category': 'hoodie'},
        {'id': 'BASE', 'name': 'Unisex Hoodie | Gildan 18500', 'category': 'hoodie'},
    ]
    skus = [{'sku_code': f'HOOD-{i}-M', 'product_id': f'HOOD-{i}', 'price': '16'} for i in range(16)] + [
        {'sku_code': 'KID-XS', 'product_id': 'KID', 'price': '5'},
        {'sku_code': 'BASE-BLACK-M', 'product_id': 'BASE', 'price': '14'},
        {'sku_code': 'BASE-WHITE-M', 'product_id': 'BASE', 'price': '11.5'},
    ]
    try:
        store.replace_snapshot(products, skus, [])
        vi = asyncio.run(answer('Có hoodie nào budget-friendly cho beginner không?'))
        en = asyncio.run(answer('Any budget-friendly hoodies for a beginner?'))
        assert 'Gildan 18500' in vi and 'BASE-WHITE-M' in vi and '11,50 USD' in vi
        assert 'chưa gồm phí giao' in vi and 'Kids Hoodie' not in vi and vi.count('?') == 1
        assert 'Gildan 18500' in en and '$11.50 USD' in en and 'before shipping' in en
    finally:
        store.close()


def test_openrouter_rewrites_untranslated_content_before_streaming(monkeypatch):
    monkeypatch.setattr(settings, 'PRIMARY_MODEL_PROVIDER', 'openrouter')
    monkeypatch.setattr(settings, 'OPENROUTER_API_KEY', 'fixture-key')
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert 'bằng tiếng Việt' in payload['messages'][-1]['content']
            text = 'Mình đề xuất mẫu này. **Trade-off:** It is more expensive.'
        else:
            assert 'tools' not in payload
            text = 'Mình đề xuất mẫu này. Điểm đánh đổi là giá cao hơn.'
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': text}}]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs))
    result = asyncio.run(answer('Mẫu nào hợp để bán trước?'))
    assert result == 'Mình đề xuất mẫu này. Điểm đánh đổi là giá cao hơn.'
    assert len(requests) == 2


def test_premium_followup_compares_remembered_sku_without_calling_model(tmp_path, monkeypatch):
    from core import workspace as workspace_module

    monkeypatch.setattr(settings, 'DUCKDB_PATH', ':memory:')
    store = DuckDBStore()
    monkeypatch.setattr(tool_handlers, 'db_store', store)
    workspace = workspace_module.Workspace(tmp_path / 'chat.db')
    monkeypatch.setattr(workspace_module, 'workspace', workspace)
    owner = workspace.register('seller', 'fixture-only-password')
    message = 'hãy so sánh với một lựa chọn premium hơn'
    conversation = workspace.create(owner, 'conversation', {'messages': [
        {'role': 'user', 'content': 'Có hoodie nào budget-friendly cho beginner không?'},
        {'role': 'agent', 'content': 'Mình chọn mẫu Gildan.'},
        {'role': 'user', 'content': message},
    ], 'products': [{'id': 'BASE', 'name': 'Gildan 18500', 'category': 'hoodie',
                     'variants': [{'sku_code': 'BASE-M'}]}]})
    token = owner_context.set(owner)
    try:
        store.replace_snapshot([
            {'id': 'BASE', 'name': 'Gildan 18500 Hoodie', 'category': 'hoodie'},
            {'id': 'PREMIUM', 'name': 'AOP Premium Hoodie', 'category': 'hoodie'},
            {'id': 'KIDS', 'name': 'Kids Premium Hoodie', 'category': 'hoodie'},
        ], [
            {'sku_code': 'BASE-M', 'product_id': 'BASE', 'price': '11.5'},
            {'sku_code': 'PREMIUM-M', 'product_id': 'PREMIUM', 'price': '26'},
            {'sku_code': 'KIDS-M', 'product_id': 'KIDS', 'price': '15'},
        ], [])

        async def run():
            return [json.loads(e['data'])['text'] async for e in gemini_agent.process_chat(conversation['id'], message)
                    if e['data'] != '[DONE]']

        text = ''.join(asyncio.run(run()))
        assert all(f'**{heading}**' in text for heading in ('Đề xuất', 'Lý do', 'Điểm đánh đổi'))
        assert 'BASE-M' in text and 'PREMIUM-M' in text and '26,00' in text
        assert 'Kids Premium Hoodie' not in text
    finally:
        owner_context.reset(token)
        store.close()
