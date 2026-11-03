from agent import tool_handlers
from harness.tool_registry import RiskLevel, ToolDefinition, tool_registry


def _register(name, handler, risk, timeout, retries, permissions, idempotent):
    tool_registry.register(
        ToolDefinition(
            name=name,
            handler=handler,
            risk=risk,
            timeout_seconds=timeout,
            max_retries=retries,
            required_permissions=frozenset(permissions),
            idempotent=idempotent,
        )
    )


_register("search_products", tool_handlers.search_products, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("get_sku_info", tool_handlers.get_sku_info, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("get_base_cost", tool_handlers.get_base_cost, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("get_shipping_cost", tool_handlers.get_shipping_cost, RiskLevel.READ_ONLY, 8, 1, {"catalog:read"}, True)
_register("get_production_time", tool_handlers.get_production_time, RiskLevel.READ_ONLY, 8, 1, {"catalog:read"}, True)
_register("get_shipping_time", tool_handlers.get_shipping_time, RiskLevel.READ_ONLY, 8, 1, {"catalog:read"}, True)
_register("check_sku_availability", tool_handlers.check_sku_availability, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("check_provider_status", tool_handlers.check_provider_status, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("check_region_support", tool_handlers.check_region_support, RiskLevel.READ_ONLY, 5, 1, {"catalog:read"}, True)
_register("get_order_creation_status", tool_handlers.get_order_creation_status, RiskLevel.READ_ONLY, 5, 0, {"order:read"}, True)
_register("prepare_order_review", tool_handlers.prepare_order_review, RiskLevel.READ_ONLY, 15, 0, {"order:read"}, True)
_register("create_order", tool_handlers.create_order, RiskLevel.CRITICAL, 15, 0, {"order:create"}, False)
