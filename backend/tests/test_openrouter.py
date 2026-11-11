import asyncio
import json

import httpx
import pytest

from agent import gemini_agent
from core.config import settings


@pytest.mark.parametrize("provider_name", ["openrouter", "vietcod"])
def test_openai_compatible_provider_uses_catalog_result_to_finish_chat(monkeypatch, provider_name):
    monkeypatch.setattr(settings, "PRIMARY_MODEL_PROVIDER", provider_name)
    monkeypatch.setattr(settings, f"{provider_name.upper()}_API_KEY", "test-key")
    monkeypatch.setattr(gemini_agent, "MAX_TOOL_ROUNDS", 1)
    requests = []

    def provider(request):
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        requests.append(payload)
        if provider_name == "openrouter":
            assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
            assert payload["model"].endswith(":free")
            assert payload["provider"] == {"require_parameters": True, "data_collection": "deny"}
        else:
            assert str(request.url) == "https://router.vietcod.com/v1/chat/completions"
            assert payload["model"] == "gemini-3.8-flash-high"
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
        return [event["data"] async for event in gemini_agent.process_chat(f"{provider_name}-test", "Tìm áo thun")]

    events = asyncio.run(chat())
    assert events[-1] == "[DONE]"
    assert "".join(json.loads(event)["text"] for event in events[:-1]) == "Có áo thun Classic T-shirt."
    assert len(requests) == 2
