import json
import logging
from typing import Any, Dict, List

from google import genai
from google.genai import errors, types

from agent.byteplus_agent import build_openai_tools
from agent.prompts import SYSTEM_PROMPT
from core.config import settings

logger = logging.getLogger(__name__)


def _google_tools() -> List[types.Tool]:
    declarations = []
    for tool in build_openai_tools():
        function = tool["function"]
        declarations.append(
            types.FunctionDeclaration(
                name=function["name"],
                description=function["description"],
                parameters=function["parameters"],
            )
        )
    return [types.Tool(function_declarations=declarations)]


class GoogleChatSession:
    def __init__(self, client: genai.Client, model: str, temperature: float | None = None):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.history: List[types.Content] = []

    async def send_user_message(self, content: str) -> Dict[str, Any]:
        self.history.append(types.Content(role="user", parts=[types.Part(text=content)]))
        return await self._complete(allow_tools=True)

    async def send_tool_results(self, calls: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        parts = [
            types.Part(function_response=types.FunctionResponse(
                id=call.get("id"), name=call["name"], response=result,
            ))
            for call, result in zip(calls, results)
        ]
        self.history.append(types.Content(role="user", parts=parts))
        return await self._complete(allow_tools=True)

    async def force_final_answer(self) -> Dict[str, Any]:
        self.history.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Stop calling tools now. Use the available tool results and write the final consultant answer. "
                            "Keep it concise with Recommendation, Reasoning, Trade-off, and one optional follow-up."
                        )
                    )
                ],
            )
        )
        return await self._complete(allow_tools=False)

    async def _complete(self, allow_tools: bool) -> Dict[str, Any]:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=self.temperature,
            tools=_google_tools() if allow_tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=self.history,
            config=config,
        )

        if not response.candidates or not response.candidates[0].content:
            raise RuntimeError("Gemini không trả về nội dung. Vui lòng thử lại.")
        candidate_content = response.candidates[0].content
        self.history.append(candidate_content)
        tool_calls = []
        text_parts = []
        for part in candidate_content.parts or []:
            if part.function_call:
                tool_calls.append(
                    {
                        "id": part.function_call.id,
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args or {}),
                    }
                )
            elif part.text and not part.thought:
                text_parts.append(part.text)

        return {
            "text": "".join(text_parts),
            "tool_calls": tool_calls,
            "usage": {},
            "model": self.model,
        }


class VertexChatSession(GoogleChatSession):
    def __init__(self):
        super().__init__(genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        ), settings.VERTEX_MODEL, temperature=0.2)


class GeminiChatSession(GoogleChatSession):
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("Thiếu GEMINI_API_KEY. Vui lòng cấu hình khóa Gemini trên máy chủ.")
        super().__init__(genai.Client(api_key=settings.GEMINI_API_KEY, vertexai=False), settings.GEMINI_MODEL)

    async def _complete(self, allow_tools: bool) -> Dict[str, Any]:
        try:
            return await super()._complete(allow_tools)
        except errors.ServerError as exc:
            fallback = settings.GEMINI_FALLBACK_MODEL
            # A model must receive its own history and thought signatures.
            if (exc.code != 503 or not fallback or fallback == self.model
                    or any(content.role == "model" for content in self.history)):
                raise
            logger.warning("Gemini model %s is unavailable; using %s for this chat.", self.model, fallback)
            self.model = fallback
            return await super()._complete(allow_tools)
