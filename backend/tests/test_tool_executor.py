import asyncio

from harness.tool_executor import ToolExecutor
from harness.tool_registry import RiskLevel, ToolDefinition, ToolRegistry


def test_registry_rejects_retry_for_non_idempotent_tool():
    async def handler(args):
        return {"ok": True}

    registry = ToolRegistry()
    try:
        registry.register(
            ToolDefinition(
                name="unsafe_retry",
                handler=handler,
                risk=RiskLevel.CRITICAL,
                timeout_seconds=1,
                max_retries=1,
                required_permissions=frozenset({"order:create"}),
                idempotent=False,
            )
        )
    except ValueError as exc:
        assert "cannot be retried" in str(exc)
    else:
        raise AssertionError("Expected registry to reject retries for non-idempotent tool")


def test_executor_returns_structured_error_for_unknown_tool():
    result = asyncio.run(ToolExecutor(ToolRegistry()).execute("missing_tool", {}))

    assert result["ok"] is False
    assert result["code"] == "TOOL_NOT_REGISTERED"


def test_executor_applies_timeout():
    async def slow_handler(args):
        await asyncio.sleep(0.1)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="search_products",
            handler=slow_handler,
            risk=RiskLevel.READ_ONLY,
            timeout_seconds=0.01,
            max_retries=0,
            required_permissions=frozenset({"catalog:read"}),
            idempotent=True,
        )
    )

    result = asyncio.run(ToolExecutor(registry).execute("search_products", {}))

    assert result["ok"] is False
    assert result["code"] == "TOOL_TIMEOUT"
