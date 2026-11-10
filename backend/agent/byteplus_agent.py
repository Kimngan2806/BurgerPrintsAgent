import json
from typing import Any, Dict, List

import httpx
from google.protobuf.json_format import MessageToDict

from agent.prompts import SYSTEM_PROMPT
from agent.tools import agent_tools
from core.config import settings


def _schema_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "type_"):
        return _gemini_schema_to_json_schema(value)
    if hasattr(value, "DESCRIPTOR"):
        return MessageToDict(value, preserving_proto_field_name=True)
    raise TypeError(f"Unsupported tool schema type: {type(value).__name__}")


def _gemini_schema_to_json_schema(schema: Any) -> Dict[str, Any]:
    type_name = getattr(getattr(schema, "type_", None), "name", str(getattr(schema, "type_", ""))).lower()
    type_map = {
        "object": "object",
        "string": "string",
        "array": "array",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
    }
    output: Dict[str, Any] = {"type": type_map.get(type_name, type_name or "object")}
    if getattr(schema, "description", ""):
        output["description"] = schema.description
    if getattr(schema, "enum", None):
        output["enum"] = list(schema.enum)
    if getattr(schema, "required", None):
        output["required"] = list(schema.required)
    if getattr(schema, "properties", None):
        output["properties"] = {
            key: _gemini_schema_to_json_schema(value)
            for key, value in schema.properties.items()
        }
    if getattr(schema, "items", None):
        output["items"] = _gemini_schema_to_json_schema(schema.items)
    return output


def build_openai_tools() -> List[Dict[str, Any]]:
    declarations = getattr(agent_tools, "function_declarations", [])
    tools = []
    for declaration in declarations:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": declaration.name,
                    "description": declaration.description,
                    "parameters": _schema_to_dict(declaration.parameters),
                },
            }
        )
    return tools


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

    async def send_user_message(self, content: str) -> Dict[str, Any]:
        self.messages.append({"role": "user", "content": content})
        return await self._complete()

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
            response.raise_for_status()
            data = response.json()

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
                    "args": json.loads(call["function"].get("arguments") or "{}"),
                }
                for call in tool_calls
            ],
            "usage": data.get("usage") or {},
            "model": data.get("model") or self.model,
        }


class BytePlusChatSession(OpenAICompatibleChatSession):
    def __init__(self):
        if not settings.SEEDANCE_API_KEY:
            raise RuntimeError("SEEDANCE_API_KEY is missing; BytePlus Seed provider cannot be used.")
        super().__init__(settings.SEEDANCE_API_KEY, settings.BYTEPLUS_MODEL, settings.BYTEPLUS_API_BASE_URL)
