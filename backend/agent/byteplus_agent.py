import json
from copy import deepcopy
from typing import Any, Dict, List

import httpx

from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_DECLARATIONS
from core.config import settings


def build_openai_tools() -> List[Dict[str, Any]]:
    return [{"type": "function", "function": deepcopy(tool)} for tool in TOOL_DECLARATIONS]


def _tool_arguments(value):
    try:
        return json.loads(value or "{}")
    except (ValueError, TypeError):
        return None


class OpenAICompatibleChatSession:
    def __init__(self, api_key: str, model: str, base_url: str, *, request_options=None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.request_options = request_options or {}
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self.pending_assistant_message: Dict[str, Any] | None = None

    async def send_user_message(self, content: str, *, allow_tools: bool = True) -> Dict[str, Any]:
        self.messages.append({"role": "user", "content": content})
        return await self._complete(allow_tools=allow_tools)

    async def send_tool_results(
        self, calls: List[Dict[str, Any]], results: List[Dict[str, Any]], *, allow_tools: bool = True
    ) -> Dict[str, Any]:
        if self.pending_assistant_message:
            self.messages.append(self.pending_assistant_message)
            self.pending_assistant_message = None

        for call, result in zip(calls, results):
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
        return await self._complete(allow_tools=allow_tools)

    async def force_final_answer(self) -> Dict[str, Any]:
        self.messages.append(
            {
                "role": "user",
                "content": (
                    "Stop calling tools now. Use the tool results already available and write the final consultant answer. "
                    "Keep it concise with Recommendation, Reasoning, Trade-off, and one optional follow-up."
                ),
            }
        )
        return await self._complete(allow_tools=False)

    async def _complete(self, allow_tools: bool = True) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": self.messages,
            "temperature": 0.2,
            **self.request_options,
        }
        if allow_tools:
            payload["tools"] = build_openai_tools()
            payload["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            data = self._read_completion(response)

        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            self.pending_assistant_message = message

        return {
            "text": message.get("content") or "",
            "tool_calls": [
                {
                    "id": call["id"],
                    "name": call["function"]["name"],
                    "args": _tool_arguments(call["function"].get("arguments")),
                }
                for call in tool_calls
            ],
            "usage": data.get("usage") or {},
            "model": data.get("model") or self.model,
        }

    def _read_completion(self, response: httpx.Response) -> Dict[str, Any]:
        response.raise_for_status()
        return response.json()


class BytePlusChatSession(OpenAICompatibleChatSession):
    def __init__(self):
        if not settings.SEEDANCE_API_KEY:
            raise RuntimeError("SEEDANCE_API_KEY is missing; BytePlus Seed provider cannot be used.")
        super().__init__(settings.SEEDANCE_API_KEY, settings.BYTEPLUS_MODEL, settings.BYTEPLUS_API_BASE_URL)
