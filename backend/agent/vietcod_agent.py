import httpx

from agent.byteplus_agent import OpenAICompatibleChatSession
from core.config import settings


class VietCodChatSession(OpenAICompatibleChatSession):
    def __init__(self):
        api_key = settings.VIETCOD_API_KEY.strip()
        if not api_key:
            raise RuntimeError("Chatbot chưa được cấu hình VIETCOD_API_KEY trên máy chủ.")
        super().__init__(
            api_key, settings.VIETCOD_MODEL.strip(), "https://router.vietcod.com/v1",
            # VietCod otherwise may append an SSE terminator to the JSON body.
            request_options={"stream": False},
        )

    async def _complete(self, allow_tools: bool = True):
        try:
            return await super()._complete(allow_tools=allow_tools)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status in (401, 403):
                message = "VietCod từ chối truy cập. Hãy kiểm tra key, thời hạn và model được cấp."
            elif status == 429:
                message = "VietCod đang giới hạn lượt gọi. Hãy kiểm tra hạn mức của gói hoặc thử lại sau."
            else:
                message = f"VietCod không xử lý được yêu cầu (HTTP {status})."
            raise RuntimeError(message) from error
        except httpx.RequestError as error:
            raise RuntimeError("Chưa kết nối được với VietCod. Bạn thử lại sau nhé.") from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise RuntimeError("VietCod trả phản hồi mà chatbot chưa đọc được.") from error
