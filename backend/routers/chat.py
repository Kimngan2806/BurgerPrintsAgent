import asyncio
import json
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from api.models import ChatRequest, ChatResponse
from core.workspace import current_owner, workspace
from core.chat_context import owner_context, conversation_context, tool_events

router = APIRouter()


def start_chat(owner, request):
    workspace.get(owner, request.session_id, 'conversation')
    lease = secrets.token_hex(16)
    with workspace.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS chat_leases(id TEXT PRIMARY KEY, token TEXT, expires REAL)')
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM chat_leases WHERE expires<?', (time.time(),))
        if db.execute('SELECT 1 FROM chat_leases WHERE id=?', (request.session_id,)).fetchone():
            raise HTTPException(409, 'Phiên chat đang trả lời ở tab khác. Đợi hoàn tất rồi thử lại.')
        db.execute('INSERT INTO chat_leases VALUES(?,?,?)', (request.session_id, lease, time.time() + 600))
    return lease


async def stream(owner, request, lease):
    from agent.gemini_agent import process_chat
    tokens = [owner_context.set(owner), conversation_context.set(request.session_id), tool_events.set([])]
    content, failed = '', False
    try:
        conversation = workspace.get(owner, request.session_id, 'conversation')
        body = {k: v for k, v in conversation.items() if k not in {'id', 'version', 'updated_at'}}
        body['title'] = request.message[:65] if not body['messages'] else body['title']
        body['messages'].append({'id': secrets.token_hex(8), 'role': 'user', 'content': request.message})
        workspace.update(owner, request.session_id, 'conversation', conversation['version'], body)
        async with asyncio.timeout(180):
            async for event in process_chat(request.session_id, request.message):
                if event.get('data') == '[DONE]':
                    continue
                data = json.loads(event['data'])
                content += data.get('text', '')
                if data.get('error'):
                    content += '\n\nLỗi: ' + data['error']
                    failed = True
                yield event
        for event in tool_events.get():
            yield {'data': json.dumps(event, ensure_ascii=False, default=str)}
    except asyncio.CancelledError:
        failed = True
        raise
    except Exception:
        failed = True
        content += '\nPhản hồi bị gián đoạn. Dữ liệu đã nhập vẫn được lưu; hãy thử lại.'
        yield {'data': json.dumps({'error': 'Phản hồi gián đoạn. Vui lòng thử lại.'})}
    finally:
        try:
            conversation = workspace.get(owner, request.session_id, 'conversation')
            body = {k: v for k, v in conversation.items() if k not in {'id', 'version', 'updated_at'}}
            for event in tool_events.get() or []:
                if event['tool'] == 'search_products':
                    body['criteria'] = event.get('criteria', {})
                    body['products'] = event['result'].get('results', [])
            body['messages'].append({'id': secrets.token_hex(8), 'role': 'agent',
                'content': content or 'Đã dừng trả lời. Đơn hàng không bị hủy.', 'interrupted': failed})
            workspace.update(owner, request.session_id, 'conversation', conversation['version'], body)
            workspace.event(owner, 'chat_error' if failed else 'chat_completed', request.session_id)
        finally:
            with workspace.connect() as db:
                db.execute('DELETE FROM chat_leases WHERE id=? AND token=?', (request.session_id, lease))
            owner_context.reset(tokens[0])
            conversation_context.reset(tokens[1])
            tool_events.reset(tokens[2])
    yield {'data': '[DONE]'}


@router.post('/chat', response_model=ChatResponse)
async def chat_sync(request: ChatRequest, owner=Depends(current_owner)):
    lease = start_chat(owner, request)
    chunks = []
    async for event in stream(owner, request, lease):
        if event['data'] != '[DONE]':
            data = json.loads(event['data'])
            if data.get('text'):
                chunks.append(data['text'])
    return ChatResponse(response=''.join(chunks), session_id=request.session_id)


@router.post('/chat/stream')
async def chat_stream(request: ChatRequest, owner=Depends(current_owner)):
    lease = start_chat(owner, request)
    return EventSourceResponse(stream(owner, request, lease))
