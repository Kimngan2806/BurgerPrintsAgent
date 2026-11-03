import asyncio
import logging
import time
from typing import Any, Dict

from harness.policy_engine import evaluate_tool_call
from harness import order_state
from harness.tool_registry import ToolRegistry


logger = logging.getLogger(__name__)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, name: str, args: Dict[str, Any], user_message: str = "", session_id: str = "") -> Dict[str, Any]:
        args = dict(args or {})
        if session_id:
            args.setdefault("_session_id", session_id)
        definition = self.registry.get(name)
        if not definition:
            return {
                "ok": False,
                "code": "TOOL_NOT_REGISTERED",
                "error": f"Tool `{name}` is not registered.",
            }

        policy = evaluate_tool_call(name, args, user_message=user_message, session_id=session_id)
        logger.info(
            "Policy decision for tool %s: allowed=%s code=%s reason=%s",
            name,
            policy.allowed,
            policy.code,
            policy.reason,
        )
        if not policy.allowed:
            return policy.to_tool_error()

        started = time.perf_counter()
        attempts = definition.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(
                    definition.handler(args),
                    timeout=definition.timeout_seconds,
                )
                logger.info(
                    "Tool completed: name=%s risk=%s attempt=%s duration_ms=%.2f",
                    name,
                    definition.risk.value,
                    attempt,
                    (time.perf_counter() - started) * 1000,
                )
                if isinstance(result, dict):
                    if name == "get_sku_info" and result.get("ok") and result.get("sku", {}).get("sku_code"):
                        order_state.mark_sku_presented(session_id, result["sku"]["sku_code"])
                    if name == "create_order" and result.get("status") == "created":
                        order_state.mark_order_created(args)
                    return result
                return {"ok": True, "data": result}
            except asyncio.TimeoutError:
                logger.warning(
                    "Tool timeout: name=%s attempt=%s timeout_seconds=%s",
                    name,
                    attempt,
                    definition.timeout_seconds,
                )
                if attempt == attempts:
                    return {
                        "ok": False,
                        "code": "TOOL_TIMEOUT",
                        "error": f"Tool `{name}` exceeded {definition.timeout_seconds} seconds.",
                    }
            except Exception as exc:
                logger.exception("Tool failed: name=%s attempt=%s", name, attempt)
                if attempt == attempts:
                    return {
                        "ok": False,
                        "code": "TOOL_EXECUTION_ERROR",
                        "error": str(exc),
                    }

        return {"ok": False, "code": "TOOL_EXECUTION_ERROR", "error": f"Tool `{name}` failed."}
