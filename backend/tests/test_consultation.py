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


def test_price_and_margin_followups_use_saved_products_without_a_model(tmp_path, monkeypatch):
    from core import workspace as workspace_module
    from routers import chat

    workspace = workspace_module.Workspace(tmp_path / 'prices.db')
    monkeypatch.setattr(workspace_module, 'workspace', workspace)
    monkeypatch.setattr(chat, 'workspace', workspace)
    owner = 'seller'
    products = [
        {'id': 'TEE', 'name': 'Basic Tee', 'variants': [{'sku_code': 'TEE-ASH-L', 'price': '6.00'}]},
        {'id': 'RING', 'name': 'Ring-spun Tee', 'variants': [{'sku_code': 'RING-BLK-L', 'price': '5.85'}]},
    ]
    conversation = workspace.create(owner, 'conversation', {
        'messages': [{'role': 'user', 'content': 'Mình muốn bán áo thun.'},
                     {'role': 'agent', 'content': 'Đây là hai mẫu mình tìm được.', 'products': products}],
        'products': products,
    })

    async def lookup(name, args, **kwargs):
        assert name == 'get_base_cost'
        assert args['sku_codes'] == ['TEE-ASH-L', 'RING-BLK-L']
        return {'TEE-ASH-L': '5.00', 'RING-BLK-L': '5.85'}

    def unexpected_model(*args, **kwargs):
        pytest.fail('Pricing questions with catalog data should not call the model')

    monkeypatch.setattr(gemini_agent, 'execute_tool', lookup)
    monkeypatch.setattr(gemini_agent, 'process_chat_provider', unexpected_model)

    async def send(message):
        request = chat.ChatRequest(session_id=conversation['id'], message=message)
        lease = chat.start_chat(owner, request)
        return [json.loads(event['data']) async for event in chat.stream(owner, request, lease)
                if event['data'] != '[DONE]']

    prices = asyncio.run(send('giá sản phẩm này bao nhiêu và tôi nên bán với giá bao nhiêu là lời'))
    followup = asyncio.run(send('Tôi bán Etsy US và muốn margin trên 40%'))
    assert len(prices) == len(followup) == 1
    assert '5,00 USD (giá gốc catalog)' in prices[0]['text']
    assert '6,00 USD' not in prices[0]['text']
    assert '8,34 USD' in followup[0]['text']
    assert '9,76 USD' in followup[0]['text']  # $9.75 would give exactly 40%.
    assert all(f'**{heading}**' in followup[0]['text'] for heading in ('Đề xuất', 'Lý do', 'Điểm đánh đổi'))
    assert 'phí giao' in followup[0]['text']
    saved = workspace.get(owner, conversation['id'], 'conversation')
    assert saved['messages'][-1]['content'] == followup[0]['text']
    assert 'products' not in saved['messages'][-1]
    assert saved['products'] == products


def test_localizes_english_terms_without_rewriting_the_model_answer(monkeypatch):
    class Model:
        async def send_user_message(self, text, *, allow_tools=True):
            assert allow_tools, 'Ordinary terms should be translated locally'
            return {'text': '**Recommendation:** Nếu giá gốc là 10 USD thì hãy tính gross margin sau phí giao.',
                    'tool_calls': []}

    monkeypatch.setattr(settings, 'PRIMARY_MODEL_PROVIDER', 'openrouter')
    monkeypatch.setattr(gemini_agent, 'OpenRouterChatSession', Model)
    text = asyncio.run(answer('Cách định giá sản phẩm in theo yêu cầu?'))
    assert '**Đề xuất:**' in text and 'biên lợi nhuận gộp' in text


def test_model_failure_after_catalog_lookup_still_returns_catalog_facts(monkeypatch):
    class Model:
        async def send_user_message(self, text):
            return {'text': '', 'tool_calls': [{'name': 'search_products', 'args': {'query': 'mug'}}]}

        async def send_tool_results(self, calls, results, *, allow_tools=True):
            raise TimeoutError()

    async def lookup(*args, **kwargs):
        return {'results': [{'name': 'Ceramic Mug', 'variants': [{'sku_code': 'MUG-11', 'price': '4.60'}]}]}

    monkeypatch.setattr(settings, 'PRIMARY_MODEL_PROVIDER', 'openrouter')
    monkeypatch.setattr(gemini_agent, 'OpenRouterChatSession', Model)
    monkeypatch.setattr(gemini_agent, 'execute_tool', lookup)
    text = asyncio.run(answer('Có cốc nào để in hình không?'))
    assert 'MUG-11' in text and '4.60 USD' in text
    assert 'phí giao tính riêng' in text
