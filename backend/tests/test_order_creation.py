import asyncio

import pytest

from agent.gemini_agent import execute_tool
from api.burgerprints import BurgerPrintsClient
from api.models import OrderAddress, OrderRequest
from harness import order_state
from harness.api_response_policy import parse_burgerprints_error
from harness import policy_engine
from harness.policy_engine import evaluate_tool_call


VALID_SKU = "USBG5000DTF-Black-S"
VALID_ADDRESS = {
    "name": "Le Quoc Anh",
    "street": "84 Le Dinh Ly",
    "city": "Da Nang",
    "state": "Hai Chau",
    "zip": "550000",
    "country": "VN",
}


def order_args(**overrides):
    data = {
        "sku": VALID_SKU,
        "quantity": 1,
        "address": VALID_ADDRESS.copy(),
        "design_url_front": "https://example.com/design-front.png",
        "shipping_method": "standard",
    }
    data.update(overrides)
    return data


@pytest.fixture(autouse=True)
def enable_order_creation(monkeypatch):
    monkeypatch.setattr(policy_engine.ff_manager, "is_order_creation_enabled", lambda: True)
    monkeypatch.setattr(
        policy_engine.db_store,
        "get_sku_by_code",
        lambda sku: {
            "sku_code": sku,
            "product_id": "USG5000",
            "provider_id": "provider-test",
            "price": "5.39",
        } if sku == VALID_SKU else None,
    )
    monkeypatch.setattr(
        policy_engine.db_store,
        "get_provider_by_id",
        lambda provider_id: {"id": provider_id, "countries_served": []},
    )


def test_create_order_requires_exact_sku_confirmation():
    decision = evaluate_tool_call(
        "create_order",
        order_args(),
        user_message="Tôi đồng ý đặt đơn này",
    )

    assert not decision.allowed
    assert decision.code == "ORDER_CONFIRMATION_REQUIRED"


def test_create_order_rejects_unknown_sku_even_with_confirmation():
    decision = evaluate_tool_call(
        "create_order",
        order_args(sku="FAKE-SKU-DOES-NOT-EXIST"),
        user_message="Xác nhận đặt SKU FAKE-SKU-DOES-NOT-EXIST",
    )

    assert not decision.allowed
    assert decision.code == "SKU_NOT_FOUND"


def test_create_order_rejects_missing_address_field():
    address = VALID_ADDRESS.copy()
    address["zip"] = ""

    decision = evaluate_tool_call(
        "create_order",
        order_args(address=address),
        user_message=f"Xác nhận đặt SKU {VALID_SKU}",
    )

    assert not decision.allowed
    assert decision.code == "ADDRESS_REQUIRED"


def test_create_order_allows_large_quantity_at_policy_layer():
    decision = evaluate_tool_call(
        "create_order",
        order_args(quantity=100),
        user_message=f"Xác nhận đặt SKU {VALID_SKU}",
    )

    assert decision.allowed
    assert decision.code == "POLICY_ALLOWED"


def test_create_order_rejects_missing_design_url():
    decision = evaluate_tool_call(
        "create_order",
        order_args(design_url_front=""),
        user_message=f"Xac nhan dat SKU {VALID_SKU}",
    )

    assert not decision.allowed
    assert decision.code == "DESIGN_URL_REQUIRED"


def test_create_order_rejects_address_country_mismatch():
    address = {
        "name": "John Carter",
        "street": "2458 West Sunset Blvd",
        "city": "Paris",
        "state": "Ile-de-France",
        "zip": "75004",
        "country": "US",
    }

    decision = evaluate_tool_call(
        "create_order",
        order_args(address=address),
        user_message=f"Xac nhan dat SKU {VALID_SKU}",
    )

    assert not decision.allowed
    assert decision.code == "ADDRESS_COUNTRY_MISMATCH"


def test_create_order_rejects_invalid_design_url():
    decision = evaluate_tool_call(
        "create_order",
        order_args(design_url_front="not-a-public-url"),
        user_message=f"Xac nhan dat SKU {VALID_SKU}",
    )

    assert not decision.allowed
    assert decision.code == "INVALID_DESIGN_URL"


def test_create_order_requires_sku_presentation_when_session_is_known():
    decision = evaluate_tool_call(
        "create_order",
        order_args(),
        user_message=f"Xac nhan dat SKU {VALID_SKU}",
        session_id="session-policy-test",
    )

    assert not decision.allowed
    assert decision.code == "SKU_PRESENTATION_REQUIRED"


def test_create_order_requires_order_review_after_sku_presentation():
    session_id = "session-review-test"
    order_state.mark_sku_presented(session_id, VALID_SKU)

    decision = evaluate_tool_call(
        "create_order",
        order_args(),
        user_message=f"Xac nhan dat SKU {VALID_SKU}",
        session_id=session_id,
    )

    assert not decision.allowed
    assert decision.code == "ORDER_REVIEW_REQUIRED"


def test_external_api_response_policy_extracts_design_resolution_error():
    parsed = parse_burgerprints_error(
        {
            "message": "Design resolution must be 4800x5400|4500x5400 pixel",
        }
    )

    assert parsed["code"] == "DESIGN_RESOLUTION_INVALID"
    assert "4800x5400" in parsed["required_resolutions"]


def test_create_order_policy_allows_valid_confirmed_order():
    decision = evaluate_tool_call(
        "create_order",
        order_args(),
        user_message=f"Xác nhận đặt SKU {VALID_SKU}",
    )

    assert decision.allowed
    assert decision.code == "POLICY_ALLOWED"


def test_create_order_tool_does_not_call_real_api(monkeypatch):
    class FakeDesignValidation:
        ok = True

        def to_dict(self):
            return {"ok": True, "code": "DESIGN_VALID"}

    async def fake_create_order(order):
        return type(
            "FakeOrderResponse",
            (),
            {
                "model_dump": lambda self: {
                    "order_id": "TEST-ORDER-1",
                    "status": "created",
                    "message": "Order created in test",
                }
            },
        )()

    monkeypatch.setattr(
        "agent.tool_handlers.bp_client.check_sku_availability",
        lambda sku_codes: _async_result({sku_codes[0]: "present_in_catalog"}),
    )
    monkeypatch.setattr(
        "agent.tool_handlers.db_store.get_sku_by_code",
        lambda sku: {
            "sku_code": sku,
            "product_id": "USG5000",
            "provider_id": "provider-test",
            "price": "5.39",
        } if sku == VALID_SKU else None,
    )
    monkeypatch.setattr(
        "agent.tool_handlers.bp_client.check_region_support",
        lambda sku_codes, region: _async_result({"_unsupported": "not implemented in test"}),
    )
    monkeypatch.setattr(
        "agent.tool_handlers.bp_client.check_provider_status",
        lambda provider_ids: _async_result({"_unsupported": "not implemented in test"}),
    )
    monkeypatch.setattr(
        "agent.tool_handlers.validate_design_url",
        lambda url: _async_result(FakeDesignValidation()),
    )
    monkeypatch.setattr("agent.tool_handlers.bp_client.create_order", fake_create_order)

    result = asyncio.run(
        execute_tool(
            "create_order",
            order_args(),
            user_message=f"Xác nhận đặt SKU {VALID_SKU}",
        )
    )

    assert result == {
        "order_id": "TEST-ORDER-1",
        "status": "created",
        "message": "Order created in test",
    }


async def _async_result(value):
    return value


def test_burgerprints_success_response_returns_full_order_details(monkeypatch):
    client = BurgerPrintsClient()

    async def fake_post(endpoint, payload):
        return {
            "is_success": True,
            "message": "Order created",
            "data": {
                "id": "BP-ORDER-123",
                "status": "pending",
                "shipping_services": [{"id": "standard", "name": "Standard Shipping"}],
                "total": "12.34",
            },
        }

    monkeypatch.setattr(client, "_post", fake_post)
    request = OrderRequest(
        sku=VALID_SKU,
        quantity=1,
        address=OrderAddress(**VALID_ADDRESS),
        design_url_front="https://example.com/design-front.png",
    )

    result = asyncio.run(client.create_order(request)).model_dump()

    assert result["order_id"] == "BP-ORDER-123"
    assert result["status"] == "created"
    assert result["sku"] == VALID_SKU
    assert result["destination"]["country"] == "VN"
    assert result["shipping_services"] == [{"id": "standard", "name": "Standard Shipping"}]
    assert result["order_details"]["total"] == "12.34"
    assert result["api_response"]["is_success"] is True
