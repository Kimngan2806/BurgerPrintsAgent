import asyncio
import json
import sys
from threading import Event

import anyio
import httpx
from fastapi import FastAPI

from agent import gemini_agent
from api.models import ChatRequest
from core.workspace import Workspace
from routers import chat


def test_slow_chat_storage_leaves_health_responsive(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'workspace.db')
    monkeypatch.setattr(chat, 'workspace', workspace)
    # The deterministic order opener works without importing the model agent.
    monkeypatch.setitem(sys.modules, 'agent.gemini_agent', None)
    owner = 'seller-id'
    conversation = workspace.create(owner, 'conversation', {'messages': []})
    waiting, resume, storage_timed_out = Event(), Event(), Event()
    get = workspace.get

    def slow_first_get(*args):
        if not waiting.is_set():
            waiting.set()
            if not resume.wait(5):
                storage_timed_out.set()
        return get(*args)

    monkeypatch.setattr(workspace, 'get', slow_first_get)
    app = FastAPI()
    app.include_router(chat.router, prefix='/api')
    app.dependency_overrides[chat.current_owner] = lambda: owner

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    async def verify():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            request = asyncio.create_task(client.post('/api/chat', json={
                'session_id': conversation['id'], 'message': 'Tôi muốn đặt hàng',
            }))
            try:
                assert await asyncio.to_thread(waiting.wait, 5)
                response = await client.get('/health')
                assert response.json() == {'status': 'ok'}
                assert not storage_timed_out.is_set()
            finally:
                resume.set()
                response = await request
            assert response.status_code == 200
            assert 'SKU' in response.json()['response']

    asyncio.run(verify())


def test_disconnected_stream_saves_partial_reply_and_releases_lease(tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'workspace.db')
    monkeypatch.setattr(chat, 'workspace', workspace)
    owner = 'seller-id'
    conversation = workspace.create(owner, 'conversation', {'messages': []})
    request = ChatRequest(session_id=conversation['id'], message='Tư vấn áo thun')

    async def verify():
        streamed = anyio.Event()

        async def process_chat(*_):
            yield {'data': json.dumps({'text': 'Mình gợi ý áo thun trắng.'})}
            streamed.set()
            await anyio.sleep_forever()

        monkeypatch.setattr(gemini_agent, 'process_chat', process_chat)
        lease = chat.start_chat(owner, request)

        async def consume():
            async for _ in chat.stream(owner, request, lease):
                pass

        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            with anyio.fail_after(5):
                await streamed.wait()
            group.cancel_scope.cancel()

        saved = workspace.get(owner, conversation['id'], 'conversation')
        assert [message['content'] for message in saved['messages']] == [
            request.message, 'Mình gợi ý áo thun trắng.',
        ]
        assert saved['messages'][-1]['interrupted'] is True
        retry_lease = chat.start_chat(owner, request)
        assert retry_lease != lease
        chat.release_chat(request.session_id, retry_lease)

    anyio.run(verify)
