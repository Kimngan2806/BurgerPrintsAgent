import httpx

from agent.byteplus_agent import OpenAICompatibleChatSession
from core.config import settings


class OpenRouterChatSession(OpenAICompatibleChatSession):
    def __init__(self):
        api_key = settings.OPENROUTER_API_KEY.strip()
        model = settings.OPENROUTER_MODEL.strip()
        if not api_key:
            raise RuntimeError("Chatbot chưa được cấu hình OPENROUTER_API_KEY trên máy chủ.")
        if not model.endswith(":free"):
            raise RuntimeError("OPENROUTER_MODEL phải là model OpenRouter có hậu tố :free.")
        super().__init__(
            api_key, model, "https://openrouter.ai/api/v1",
            request_options={"provider": {"require_parameters": True, "data_collection": "deny"}},
        )

    async def _complete(self, allow_tools: bool = True):
        try:
            return await super()._complete(allow_tools=allow_tools)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status == 429:
                message = "OpenRouter đang giới hạn lượt gọi miễn phí. Bạn thử lại sau nhé."
            elif status in (401, 403):
                message = "OpenRouter từ chối API key. Hãy kiểm tra OPENROUTER_API_KEY trên Render."
            elif status in (404, 502, 503):
                message = "Model miễn phí trên OpenRouter đang không phục vụ được yêu cầu. Bạn thử lại sau nhé."
            else:
                message = f"OpenRouter không xử lý được yêu cầu (HTTP {status})."
            raise RuntimeError(message) from error
        except httpx.RequestError as error:
            raise RuntimeError("Chưa kết nối được với OpenRouter. Bạn thử lại sau nhé.") from error
