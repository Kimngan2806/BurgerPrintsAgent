import asyncio
import json

import httpx
import pytest

from agent import gemini_agent
from agent.openrouter_agent import OpenRouterChatSession
from core.config import settings


@pytest.mark.parametrize(("provider_name", "model"), [
    ("openrouter", "cohere/north-mini-code:free"),
    ("openrouter", "google/gemini-3.1-flash-lite"),
    ("vietcod", "gemini-3.8-flash-high"),
])
def test_openai_compatible_provider_uses_catalog_result_to_finish_chat(monkeypatch, provider_name, model):
    monkeypatch.setattr(settings, "PRIMARY_MODEL_PROVIDER", provider_name)
    monkeypatch.setattr(settings, f"{provider_name.upper()}_API_KEY", "test-key")
    monkeypatch.setattr(settings, f"{provider_name.upper()}_MODEL", model)
    monkeypatch.setattr(gemini_agent, "MAX_TOOL_ROUNDS", 1)
    requests = []

    def provider(request):
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == model
        if provider_name == "openrouter":
            assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
            assert payload["provider"] == {"require_parameters": True, "data_collection": "deny"}
        else:
            assert str(request.url) == "https://router.vietcod.com/v1/chat/completions"
            assert payload["stream"] is False
        if len(requests) == 1:
            assert any(tool["function"]["name"] == "search_products" for tool in payload["tools"])
            message = {"role": "assistant", "tool_calls": [{
                "id": "catalog-call", "type": "function",
                "function": {"name": "search_products", "arguments": '{"query":"T-shirt"}'},
            }]}
        else:
            assert "tools" not in payload
            assistant, result = payload["messages"][-2:]
            assert result["tool_call_id"] == assistant["tool_calls"][0]["id"] == "catalog-call"
            assert json.loads(result["content"]) == {"products": ["Classic T-shirt"]}
            message = {"role": "assistant", "content": "Có áo thun Classic T-shirt."}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    async def catalog(name, args, **kwargs):
        assert (name, args) == ("search_products", {"query": "T-shirt"})
        return {"products": ["Classic T-shirt"]}

    client_type = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(transport=httpx.MockTransport(provider), **kwargs))
    monkeypatch.setattr(gemini_agent, "execute_tool", catalog)

    async def chat():
        return [event["data"] async for event in gemini_agent.process_chat(f"{provider_name}-{model}-test", "Tìm áo thun")]

    events = asyncio.run(chat())
    assert events[-1] == "[DONE]"
    assert "".join(json.loads(event)["text"] for event in events[:-1]) == "Có áo thun Classic T-shirt."
    assert len(requests) == 2


@pytest.fixture
def router_transport(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "cohere/north-mini-code:free")
    client_type = httpx.AsyncClient

    def install(provider):
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client_type(
            transport=httpx.MockTransport(provider), **kwargs,
        ))

    return install


@pytest.mark.parametrize(("status", "body"), [
    (404, {"error": {"message": "No endpoints found", "metadata": {"error_type": "unknown_type"}}}),
    (429, {"error": {"message": "Provider rate limited"}}),
    (200, {"error": {"code": 503, "metadata": {"error_type": "provider_overloaded"}}}),
    (200, {"choices": [{
        "message": {"role": "assistant", "content": "Ignoring partial output"},
        "finish_reason": "error",
        "error": {"code": 502, "metadata": {"error_type": "provider_unavailable"}},
    }]}),
])
def test_openrouter_retries_tool_followup_on_free_router(router_transport, status, body):
    requests = []

    def provider(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "reasoning_details": [{"type": "reasoning.encrypted", "data": "primary-signature"}],
                "tool_calls": [{
                    "id": "catalog-call", "type": "function",
                    "function": {"name": "search_products", "arguments": '{"query":"hoodie"}'},
                    "extra_content": {"thought_signature": "primary-signature"},
                }],
            }
        elif len(requests) == 2:
            return httpx.Response(status, json=body)
        else:
            message = {"role": "assistant", "content": "Mình sẽ so sánh hai mẫu hoodie."}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    router_transport(provider)

    async def chat():
        session = OpenRouterChatSession()
        session.messages.extend([
            {"role": "user", "content": "Có hoodie nào giá tốt cho người mới không?"},
            {"role": "assistant", "content": "Mình gợi ý Gildan 18500."},
        ])
        initial = await session.send_user_message("So sánh với mẫu cao cấp hơn")
        return await session.send_tool_results(initial["tool_calls"], [{"products": ["Gildan 18500"]}])

    assert asyncio.run(chat())["text"] == "Mình sẽ so sánh hai mẫu hoodie."
    original, primary, fallback = requests
    primary_tool_message = primary["messages"][-2]
    assert primary_tool_message.pop("reasoning_details")
    assert primary_tool_message["tool_calls"][0].pop("extra_content")
    assert fallback == {**primary, "model": "openrouter/free"}
    assert original["model"] == primary["model"] == "cohere/north-mini-code:free"
    assert fallback["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert fallback["messages"][-1]["tool_call_id"] == "catalog-call"


@pytest.mark.parametrize(("status", "headers", "expected_models", "expected_message"), [
    (401, {}, ["cohere/north-mini-code:free"], "từ chối API key"),
    (403, {}, ["cohere/north-mini-code:free"], "từ chối API key"),
    (429, {"Retry-After": "60"}, ["cohere/north-mini-code:free"], "giới hạn lượt gọi miễn phí"),
    (503, {}, ["cohere/north-mini-code:free", "openrouter/free"], "đang không phục vụ được yêu cầu"),
])
def test_openrouter_retry_is_bounded(router_transport, status, headers, expected_models, expected_message):
    models = []

    def provider(request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(status, headers=headers, json={"error": {"message": "provider error"}})

    router_transport(provider)
    with pytest.raises(RuntimeError, match=expected_message):
        asyncio.run(OpenRouterChatSession().send_user_message("So sánh hoodie"))

    assert models == expected_models


@pytest.mark.parametrize(("status", "expected_message"), [
    (402, "số dư credit"),
    (429, "Gemini Flash Lite trên OpenRouter đang giới hạn tần suất"),
    (503, "Gemini Flash Lite trên OpenRouter đang không phục vụ được yêu cầu"),
])
def test_flash_lite_reports_paid_provider_error(router_transport, monkeypatch, status, expected_message):
    model = "google/gemini-3.1-flash-lite"
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", model)
    models = []

    def provider(request):
        models.append(json.loads(request.content)["model"])
        return httpx.Response(status, json={"error": {"message": "provider error"}})

    router_transport(provider)
    with pytest.raises(RuntimeError, match=expected_message):
        asyncio.run(OpenRouterChatSession().send_user_message("So sánh hoodie"))
    assert models == [model]
