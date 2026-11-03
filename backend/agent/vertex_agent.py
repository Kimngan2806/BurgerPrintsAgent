import json
import logging
from typing import Any, Dict, List

from google import genai
from google.genai import types

from agent.byteplus_agent import build_openai_tools
from agent.prompts import SYSTEM_PROMPT
from core.config import settings

logger = logging.getLogger(__name__)


def _vertex_tools() -> List[types.Tool]:
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


class VertexChatSession:
    def __init__(self):
        self.client = genai.Client(
            vertexai=True,
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
        )
        self.history: List[types.Content] = []
        self.pending_calls: List[Dict[str, Any]] = []

    async def send_user_message(self, content: str) -> Dict[str, Any]:
        self.history.append(types.Content(role="user", parts=[types.Part(text=content)]))
        return await self._complete(allow_tools=True)

    async def send_tool_results(self, calls: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> Dict[str, Any]:
        parts = [
            types.Part.from_function_response(name=call["name"], response=result)
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
            temperature=0.2,
            tools=_vertex_tools() if allow_tools else None,
        )
        response = await self.client.aio.models.generate_content(
            model=settings.VERTEX_MODEL,
            contents=self.history,
            config=config,
        )

        candidate_content = response.candidates[0].content
        self.history.append(candidate_content)
        tool_calls = []
        text_parts = []
        for part in candidate_content.parts or []:
            if part.function_call:
                tool_calls.append(
                    {
                        "id": f"vertex-{len(self.history)}-{len(tool_calls)}",
                        "name": part.function_call.name,
                        "args": dict(part.function_call.args or {}),
                    }
                )
            elif part.text:
                text_parts.append(part.text)

        return {
            "text": "".join(text_parts),
            "tool_calls": tool_calls,
            "usage": {},
            "model": settings.VERTEX_MODEL,
        }
