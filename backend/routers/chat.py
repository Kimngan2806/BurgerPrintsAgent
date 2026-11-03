from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
from api.models import ChatRequest, ChatResponse
from agent.gemini_agent import process_chat

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """
    Endpoint chat đồng bộ (không streaming). 
    Ít dùng cho frontend thực tế, chủ yếu để test nhanh qua docs.
    """
    # Gói logic async generator thành mảng
    chunks = []
    async for event in process_chat(request.session_id, request.message):
        data_str = event.get("data", "")
        if data_str == "[DONE]":
            break
        try:
            import json
            data = json.loads(data_str)
            if "text" in data:
                chunks.append(data["text"])
            elif "error" in data:
                raise HTTPException(status_code=500, detail=data["error"])
        except json.JSONDecodeError:
            pass
            
    full_text = "".join(chunks)
    return ChatResponse(response=full_text, session_id=request.session_id)

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Endpoint chat sử dụng Server-Sent Events (SSE) để streaming kết quả.
    Frontend sẽ gọi endpoint này để nhận từng token theo thời gian thực.
    """
    if not request.message or not request.session_id:
        raise HTTPException(status_code=400, detail="Missing message or session_id")
        
    return EventSourceResponse(process_chat(request.session_id, request.message))
