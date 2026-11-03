import asyncio
import json
import logging
import unicodedata
import google.generativeai as genai

from core.config import settings
from agent.prompts import SYSTEM_PROMPT
from agent.domain_knowledge import build_domain_context
from agent.tools import agent_tools
from core.session import session_manager
from agent.byteplus_agent import BytePlusChatSession
from agent.vertex_agent import VertexChatSession
from harness.default_tools import tool_registry
from harness.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

# Cấu hình Gemini API
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY is missing! Agent will fail to respond.")

# Khởi tạo model
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    tools=[agent_tools],
    system_instruction=SYSTEM_PROMPT
)

tool_executor = ToolExecutor(tool_registry)
MAX_TOOL_ROUNDS = 4


def slim_product(product: dict) -> dict:
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "display_name": product.get("display_name"),
        "category": product.get("category"),
        "material": product.get("material"),
        "print_techniques": product.get("print_techniques", []),
        "description": (product.get("description") or "")[:500],
    }


def slim_sku(sku: dict) -> dict:
    return {
        "sku_code": sku.get("sku_code"),
        "product_id": sku.get("product_id"),
        "color": sku.get("color"),
        "size": sku.get("size"),
        "material": sku.get("material"),
        "provider_id": sku.get("provider_id"),
        "provider_name": sku.get("provider_name"),
        "price": sku.get("price"),
        "second_price": sku.get("second_price"),
        "addition_price": sku.get("addition_price"),
    }


def is_waiting_placeholder(text: str) -> bool:
    """Detect answers that promise background work but do not actually return results."""
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in [
            "vui lòng đợi",
            "đợi trong giây lát",
            "chờ trong giây lát",
            "tôi sẽ kiểm tra",
            "tôi cần một chút thời gian",
            "kiểm tra trong hệ thống",
        ]
    )


def normalize_error_message(error: Exception) -> str:
    message = str(error)
    if "429" in message and "quota" in message.lower():
        return "Gemini API đã hết quota tạm thời. Vui lòng thử lại sau hoặc đổi API key khác."
    return message


def get_function_calls(response) -> list:
    """Extract function calls from the response shape used by google-generativeai."""
    calls = []
    for part in getattr(response, "parts", []):
        function_call = getattr(part, "function_call", None)
        if function_call and getattr(function_call, "name", ""):
            calls.append(function_call)
    return calls


def user_explicitly_confirmed_sku(message: str, sku: str) -> bool:
    normalized = unicodedata.normalize("NFKC", message).casefold()
    normalized_sku = unicodedata.normalize("NFKC", sku).casefold()
    confirmation_phrases = [
        "xác nhận",
        "đồng ý",
        "đặt mã",
        "đặt sku",
        "chọn mã",
        "chọn sku",
        "order mã",
        "order sku",
    ]
    return normalized_sku in normalized and any(phrase.casefold() in normalized for phrase in confirmation_phrases)


async def execute_tool(func_name: str, args: dict, user_message: str = "", session_id: str = "") -> dict:
    """Thực thi tool mapping từ tên function call của Gemini"""
    logger.info(f"Executing tool: {func_name} with args: {args}")
    return await tool_executor.execute(func_name, args, user_message=user_message, session_id=session_id)

    # Legacy mapping below remains unreachable during the Phase 2 rollout.
    try:
        policy_decision = evaluate_tool_call(func_name, args, user_message=user_message)
        logger.info(
            "Policy decision for tool %s: allowed=%s code=%s reason=%s",
            func_name,
            policy_decision.allowed,
            policy_decision.code,
            policy_decision.reason,
        )
        if not policy_decision.allowed:
            return policy_decision.to_tool_error()

        if func_name == "search_products":
            # Smart router logic
            query = args.get("query")
            cat = args.get("category")
            mat = args.get("material")
            
            if query:
                logger.info(f"Fast DuckDB search triggered for query: {query}")
                if hybrid_searcher.is_ready:
                    ids = hybrid_searcher.search(query, top_k=15)
                    results = db_store.query_products_by_ids(ids)
                else:
                    results = db_store.search_products_text(query_text=query, category=cat, material=mat, limit=15)
                # Apply SQL filter if category/material is also provided
                if cat:
                    results = [r for r in results if cat.lower() in r.get("category", "").lower()]
                if mat:
                    results = [r for r in results if mat.lower() in r.get("material", "").lower()]
            else:
                # Dùng DuckDB Structured Search
                logger.info("Structured search triggered")
                results = db_store.query_products(category=cat, material=mat, limit=15)
            return {"results": [slim_product(result) for result in results[:10]]}

        elif func_name == "get_sku_info":
            skus = db_store.get_skus_for_product(args.get("product_id"))
            return {"skus": [slim_sku(sku) for sku in skus[:50]], "total": len(skus)}
            
        elif func_name == "get_base_cost":
            return await bp_client.get_base_cost(args.get("sku_codes", []))
            
        elif func_name == "get_shipping_cost":
            return await bp_client.get_shipping_cost(args.get("sku_codes", []), args.get("destination", ""))
            
        elif func_name == "get_production_time":
            return await bp_client.get_production_time(args.get("sku_codes", []))
            
        elif func_name == "get_shipping_time":
            return await bp_client.get_shipping_time(args.get("sku_codes", []), args.get("destination", ""))
            
        elif func_name == "check_sku_availability":
            return await bp_client.check_sku_availability(args.get("sku_codes", []))
            
        elif func_name == "check_provider_status":
            return await bp_client.check_provider_status(args.get("provider_ids", []))
            
        elif func_name == "check_region_support":
            return await bp_client.check_region_support(args.get("sku_codes", []), args.get("region", ""))

        elif func_name == "get_order_creation_status":
            enabled = ff_manager.is_order_creation_enabled()
            return {
                "ok": True,
                "code": "ORDER_CREATION_ENABLED" if enabled else "ORDER_CREATION_DISABLED",
                "enabled": enabled,
            }
            
        elif func_name == "create_order":
            sku = str(args.get("sku", "")).strip()
            sku_record = db_store.get_sku_by_code(sku)

            addr_data = args.get("address", {})
            addr = OrderAddress(**addr_data)

            availability = await bp_client.check_sku_availability([sku])
            sku_status = str(availability.get(sku, "")).lower()
            if sku_status not in {"active", "present_in_catalog"}:
                return {"ok": False, "code": "SKU_INACTIVE", "error": f"Không thể tạo đơn: SKU `{sku}` hiện không active."}

            region_support = await bp_client.check_region_support([sku], addr.country)
            if not region_support.get("_unsupported") and region_support.get(sku) is not True:
                return {"ok": False, "code": "REGION_NOT_SUPPORTED", "error": f"Không thể tạo đơn: SKU `{sku}` không hỗ trợ giao đến `{addr.country}`."}

            provider_id = sku_record.get("provider_id")
            provider_status = await bp_client.check_provider_status([provider_id])
            if not provider_status.get("_unsupported") and str(provider_status.get(provider_id, "")).lower() != "active":
                return {"ok": False, "code": "PROVIDER_INACTIVE", "error": f"Không thể tạo đơn: xưởng `{provider_id}` hiện không active."}

            order_req = OrderRequest(
                sku=sku,
                quantity=args.get("quantity", 1),
                address=addr,
                shipping_method=args.get("shipping_method", "standard")
            )
            res = await bp_client.create_order(order_req)
            return res.model_dump()
            
        else:
            return {"error": f"Unknown function {func_name}"}
    except Exception as e:
        logger.error(f"Error in {func_name}: {e}")
        return {"error": str(e)}

async def process_chat(session_id: str, message: str):
    """
    Xử lý message của user, support Function Calling vòng lặp (CoT implicit)
    và Streaming SSE kết quả cuối cùng.
    Yield từng đoạn text để SSE trả về frontend.
    """
    sess_data = session_manager.get_session(session_id)
    chat = sess_data["chat_session"]

    provider = settings.PRIMARY_MODEL_PROVIDER.lower()
    if provider == "vertex":
        async for event in process_chat_provider(session_id, message, sess_data, VertexChatSession):
            yield event
        return
    if provider == "byteplus" and settings.SEEDANCE_API_KEY:
        async for event in process_chat_provider(session_id, message, sess_data, BytePlusChatSession):
            yield event
        return
    
    if not chat:
        chat = model.start_chat()
        session_manager.set_chat_session(session_id, chat)

    # Gửi tin nhắn user cho Gemini
    # Dùng API async (send_message_async) nếu SDK support, hoặc sync trong asyncio thread
    # Gemini SDK streaming currently supports sync/async yield
    try:
        domain_context = build_domain_context(message)
        model_message = message
        if domain_context:
            model_message = f"{domain_context}\n\nUSER MESSAGE:\n{message}"
            logger.info("Injected domain context for current message.")

        response = await chat.send_message_async(model_message)
        
        # Vòng lặp Function Calling
        tool_round = 0
        wait_retry_done = False
        while True:
            func_calls = get_function_calls(response)

            # Nếu Gemini quyết định gọi function
            if func_calls:
                if tool_round >= MAX_TOOL_ROUNDS:
                    raise RuntimeError(f"Gemini exceeded the maximum of {MAX_TOOL_ROUNDS} tool rounds")
                tool_round += 1

                logger.info(f"Gemini requested {len(func_calls)} tool call(s) in parallel.")
                
                # Tạo list task chạy song song với asyncio.gather
                tasks = []
                for fc in func_calls:
                    func_name = fc.name
                    # Convert protobuf struct to dict
                    args = {k: v for k, v in fc.args.items()}
                    tasks.append(execute_tool(func_name, args, user_message=message, session_id=session_id))
                
                # Đợi tất cả tool chạy xong cùng lúc (giảm 60-70% latency so với tuần tự)
                results = await asyncio.gather(*tasks)
                
                # Gom kết quả trả lại Gemini
                parts = []
                for fc, res_dict in zip(func_calls, results):
                    # GenAI SDK requires a protobuf Part for function responses.
                    parts.append(
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fc.name,
                                response=res_dict,
                            )
                        )
                    )
                
                # Gửi kết quả lại cho Gemini, Gemini sẽ nghĩ tiếp (vòng lặp)
                response = await chat.send_message_async(parts)
            else:
                # Không gọi tool nữa, Gemini bắt đầu trả lời bằng text
                text = response.text
                if tool_round == 0 and not wait_retry_done and is_waiting_placeholder(text):
                    wait_retry_done = True
                    logger.info("Gemini returned a waiting placeholder without tool calls; retrying with explicit no-wait instruction.")
                    response = await chat.send_message_async(
                        "Bạn vừa yêu cầu người dùng chờ, nhưng hệ thống không có job nền để tự trả lời tiếp. "
                        "Không được nói chờ. Hãy dùng các tool có sẵn ngay bây giờ nếu cần tra sản phẩm/SKU/giá/ship/thời gian, "
                        "sau đó trả kết quả cụ thể trong cùng lượt. Nếu dữ liệu chưa đủ để tìm chính xác, hãy hỏi đúng thông tin còn thiếu."
                    )
                    continue

                chunk_size = 5
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i+chunk_size]
                    yield {"data": json.dumps({"text": chunk})}
                    await asyncio.sleep(0.01) # Small delay for typing effect
                
                break # Thoát vòng lặp

    except Exception as e:
        logger.error(f"Error in process_chat: {e}")
        yield {"data": json.dumps({"error": normalize_error_message(e)})}
    finally:
        # End of stream marker
        yield {"data": "[DONE]"}


async def process_chat_provider(session_id: str, message: str, sess_data: dict, session_type):
    try:
        chat = sess_data["chat_session"]
        if not isinstance(chat, session_type):
            chat = session_type()
            session_manager.set_chat_session(session_id, chat)

        domain_context = build_domain_context(message)
        model_message = message
        if domain_context:
            model_message = f"{domain_context}\n\nUSER MESSAGE:\n{message}"
            logger.info("Injected domain context for current message.")

        response = await chat.send_user_message(model_message)
        tool_round = 0

        while response["tool_calls"]:
            if tool_round >= MAX_TOOL_ROUNDS:
                logger.info("Seed reached max tool rounds; forcing final answer without more tools.")
                response = await chat.force_final_answer()
                break
            tool_round += 1

            calls = response["tool_calls"]
            logger.info("Seed requested %s tool call(s) in parallel.", len(calls))
            results = await asyncio.gather(
                *[
                    execute_tool(call["name"], call["args"], user_message=message, session_id=session_id)
                    for call in calls
                ]
            )
            response = await chat.send_tool_results(calls, results)

        text = response["text"]
        if not text:
            text = "Tôi chưa thể tạo câu trả lời từ model ở lượt này."

        for i in range(0, len(text), 5):
            yield {"data": json.dumps({"text": text[i:i + 5]})}
            await asyncio.sleep(0.01)
        yield {"data": "[DONE]"}
    except Exception as e:
        logger.error("Error in primary provider %s: %s", session_type.__name__, e)
        if (
            session_type is VertexChatSession
            and settings.FALLBACK_MODEL_PROVIDER.lower() == "byteplus"
            and settings.SEEDANCE_API_KEY
        ):
            logger.warning("Falling back from Vertex to BytePlus Seed.")
            fallback_session = BytePlusChatSession()
            session_manager.set_chat_session(session_id, fallback_session)
            async for event in process_chat_provider(session_id, message, sess_data, BytePlusChatSession):
                yield event
            return
        if session_type is VertexChatSession and settings.FALLBACK_MODEL_PROVIDER.lower() == "byteplus":
            logger.warning("BytePlus fallback is configured but SEEDANCE_API_KEY is missing; skipping fallback.")
        yield {"data": json.dumps({"error": normalize_error_message(e)})}
        yield {"data": "[DONE]"}
