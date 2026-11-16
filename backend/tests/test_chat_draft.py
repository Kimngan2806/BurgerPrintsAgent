import asyncio
from io import BytesIO

from PIL import Image

from agent import tool_handlers
from cache.duckdb_store import DuckDBStore
from core.chat_context import conversation_context, owner_context
from core.config import settings
from core.workspace import Workspace
from routers import workspace as routes


def test_chat_draft_preserves_address_and_asset_as_quantity_changes(tmp_path, monkeypatch):
    import core.workspace as workspace_module
    import services.commerce as commerce
    import cache.duckdb_store as catalog_module

    monkeypatch.setattr(settings, 'DUCKDB_PATH', ':memory:')
    monkeypatch.setattr(settings, 'FILE_STORAGE_PATH', str(tmp_path / 'files'))
    store = DuckDBStore()
    monkeypatch.setattr(catalog_module, 'db_store', store)
    monkeypatch.setattr(tool_handlers, 'db_store', store)
    workspace = Workspace(tmp_path / 'workspace.db')
    for module in (workspace_module, commerce, routes):
        monkeypatch.setattr(module, 'workspace', workspace)

    url = 'https://example.test/design.png'
    fetched = []

    async def fetch_design(value):
        fetched.append(value)
        buffer = BytesIO()
        Image.new('RGB', (12, 12)).save(buffer, format='PNG')
        return buffer.getvalue()

    monkeypatch.setattr(routes, 'fetch_design', fetch_design)
    sku = 'USTG5000-White-M'
    store.replace_snapshot([{'id': 'USTG5000', 'name': 'Test Tee'}], [
        {'product_id': 'USTG5000', 'sku_code': sku, 'size': 'M', 'color': 'White'},
        {'product_id': 'USTG5000', 'sku_code': 'USTG5000-Black-L', 'size': 'L', 'color': 'Black'},
    ], [])
    owner = workspace.register('sample-seller', 'test-password-1234')
    conversation = workspace.create(owner, 'conversation', {'messages': [
        {'role': 'user', 'content': f'Chọn mã {sku}. File thiết kế: {url}'},
    ]})
    owner_token = owner_context.set(owner)
    conversation_token = conversation_context.set(conversation['id'])
    try:
        options = asyncio.run(tool_handlers.get_sku_info({'sku_code': 'USTG5000'}))
        assert options['code'] == 'SKU_VARIANT_REQUIRED'
        assert {option['sku_code'] for option in options['options']} == {sku, 'USTG5000-Black-L'}
        draft = asyncio.run(tool_handlers.update_draft({}))['draft']
        assert draft['address']['country'] == ''
        unselected = asyncio.run(tool_handlers.update_draft({'version': draft['version'], 'lines': [
            {'sku': 'USTG5000-Black-L', 'quantity': 5},
        ]}))
        assert unselected['ok'] is False
        invented_url = 'https://example.test/invented.png'
        rejected = asyncio.run(tool_handlers.update_draft({'version': draft['version'], 'lines': [
            {'sku': sku, 'quantity': 5, 'design_url_front': invented_url},
        ]}))
        assert rejected['ok'] is False
        assert fetched == []

        saved = asyncio.run(tool_handlers.update_draft({'version': draft['version'], 'lines': [
            {'sku': sku, 'quantity': 5, 'design_url_front': url},
        ], 'address': {'name': 'Test Buyer', 'country': 'US'}}))
        assert saved['updated']
        draft = saved['draft']
        assert fetched == [url]
        asset = draft['lines'][0]['asset_id']
        assert workspace.get(owner, asset, 'asset')['validation']['ok']

        updated = asyncio.run(tool_handlers.update_draft({'version': draft['version'], 'lines': [
            {'sku': sku, 'quantity': 2},
        ], 'address': {'email': 'buyer@example.test', 'phone': '+1 212 555 0100'}}))['draft']
        assert updated['lines'][0] == {'sku': sku, 'quantity': 2, 'asset_id': asset, 'position': 'front'}
        assert updated['address']['name'] == 'Test Buyer'
        assert updated['address']['email'] == 'buyer@example.test'
    finally:
        owner_context.reset(owner_token)
        conversation_context.reset(conversation_token)
        store.close()
