import httpx

from agent.byteplus_agent import OpenAICompatibleChatSession
from core.config import settings


FREE_MODEL_ROUTER = "openrouter/free"
RETRYABLE_STATUSES = {404, 408, 429, 500, 502, 503, 504}
RETRYABLE_ERROR_TYPES = {
    "not_found", "rate_limit_exceeded", "provider_overloaded", "provider_unavailable", "timeout", "server",
}
TERMINAL_ROUTING_ERROR_TYPES = {
    "authentication", "permission_denied", "payment_required", "content_policy_violation", "refusal",
}


class _OpenRouterCompletionError(Exception):
    def __init__(self, status: int, retryable: bool):
        super().__init__(f"OpenRouter completion failed (HTTP {status}).")
        self.status = status
        self.retryable = retryable


class OpenRouterChatSession(OpenAICompatibleChatSession):
    def __init__(self):
        api_key = settings.OPENROUTER_API_KEY.strip()
        model = settings.OPENROUTER_MODEL.strip()
        if not api_key:
            raise RuntimeError("Chatbot chưa được cấu hình OPENROUTER_API_KEY trên máy chủ.")
        if model != FREE_MODEL_ROUTER and not model.endswith(":free"):
            raise RuntimeError("OPENROUTER_MODEL phải là openrouter/free hoặc một model có hậu tố :free.")
        super().__init__(
            api_key, model, "https://openrouter.ai/api/v1",
            request_options={"provider": {"require_parameters": True, "data_collection": "deny"}},
        )

    async def _complete(self, allow_tools: bool = True):
        try:
            try:
                return await super()._complete(allow_tools=allow_tools)
            except _OpenRouterCompletionError as error:
                if self.model == FREE_MODEL_ROUTER or not error.retryable:
                    raise
                self.model = FREE_MODEL_ROUTER
                # Reasoning data can carry signatures tied to the original model.
                for message in self.messages:
                    message.pop("reasoning", None)
                    message.pop("reasoning_details", None)
                    for call in message.get("tool_calls") or []:
                        call.pop("extra_content", None)
                return await super()._complete(allow_tools=allow_tools)
        except _OpenRouterCompletionError as error:
            status = error.status
            if status == 429:
                message = "OpenRouter đang giới hạn lượt gọi miễn phí. Bạn thử lại sau nhé."
            elif status in (401, 403):
                message = "OpenRouter từ chối API key. Hãy kiểm tra OPENROUTER_API_KEY trên Render."
            elif status in RETRYABLE_STATUSES:
                message = "Model miễn phí trên OpenRouter đang không phục vụ được yêu cầu. Bạn thử lại sau nhé."
            else:
                message = f"OpenRouter không xử lý được yêu cầu (HTTP {status})."
            raise RuntimeError(message) from error
        except httpx.RequestError as error:
            raise RuntimeError("Chưa kết nối được với OpenRouter. Bạn thử lại sau nhé.") from error

    def _read_completion(self, response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError:
            if response.is_success:
                raise
            data = {}

        error = data.get("error") if isinstance(data, dict) else None
        if response.is_success and isinstance(data, dict) and not error:
            choices = data.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                error = choices[0].get("error")
        if response.is_success and not error:
            return data

        status = response.status_code
        error_type = None
        if isinstance(error, dict):
            if response.is_success:
                status = error.get("code")
                if not isinstance(status, int) or not 400 <= status <= 599:
                    status = 502
            metadata = error.get("metadata")
            if isinstance(metadata, dict):
                error_type = metadata.get("error_type")

        retryable = status in RETRYABLE_STATUSES
        if isinstance(error_type, str):
            retryable = retryable and (
                error_type in RETRYABLE_ERROR_TYPES
                or (status == 404 and error_type not in TERMINAL_ROUTING_ERROR_TYPES)
            )
        if status == 429 and response.headers.get("Retry-After") not in (None, "0"):
            retryable = False
        raise _OpenRouterCompletionError(status, retryable)
