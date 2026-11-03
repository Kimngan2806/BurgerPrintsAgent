import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict

from cache.duckdb_store import db_store
from core.feature_flags import ff_manager
from harness import order_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    reason: str

    def to_tool_error(self) -> Dict[str, Any]:
        return {
            "ok": False,
            "code": self.code,
            "error": self.reason,
        }


SAFE_TOOLS = {
    "search_products",
    "get_sku_info",
    "get_base_cost",
    "get_shipping_cost",
    "get_production_time",
    "get_shipping_time",
    "check_sku_availability",
    "check_provider_status",
    "check_region_support",
    "get_order_creation_status",
    "prepare_order_review",
}

CRITICAL_TOOLS = {"create_order"}


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    decomposed = unicodedata.normalize("NFD", normalized)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return without_marks.replace("Ä‘", "d")


def _user_confirmed_sku(message: str, sku: str) -> bool:
    normalized = _normalize(message)
    normalized_sku = _normalize(sku)
    confirmation_phrases = [
        "xac nhan",
        "dong y",
        "dat ma",
        "dat sku",
        "chon ma",
        "chon sku",
        "order ma",
        "order sku",
    ]
    return normalized_sku in normalized and any(phrase in normalized for phrase in confirmation_phrases)


def _normalize_country_code(country: str) -> str:
    value = (country or "").strip()
    if len(value) == 2:
        return value.upper()

    normalized = re.sub(r"[^a-z]", "", _normalize(value))
    country_map = {
        "unitedstates": "US",
        "unitedstatesofamerica": "US",
        "usa": "US",
        "us": "US",
        "america": "US",
        "vietnam": "VN",
        "viet nam": "VN",
        "canada": "CA",
        "australia": "AU",
        "unitedkingdom": "GB",
        "uk": "GB",
        "greatbritain": "GB",
        "germany": "DE",
        "france": "FR",
    }
    return country_map.get(normalized, value.upper())


def _validate_address_consistency(address: Dict[str, Any]) -> PolicyDecision | None:
    country = _normalize_country_code(str(address.get("country") or ""))
    state = _normalize(str(address.get("state") or ""))
    city = _normalize(str(address.get("city") or ""))
    zip_code = str(address.get("zip") or "").strip()

    france_markers = {"iledefrance", "ile de france", "paris", "france"}
    if country == "US":
        if state in france_markers or city in france_markers or re.fullmatch(r"75\d{3}", zip_code):
            return PolicyDecision(
                False,
                "ADDRESS_COUNTRY_MISMATCH",
                "Cannot create order: address fields look like France, but country is US. Please confirm the full destination address again.",
            )
        if not re.fullmatch(r"\d{5}(-\d{4})?", zip_code):
            return PolicyDecision(
                False,
                "INVALID_US_ZIP",
                "Cannot create order: US zip code must look like 90026 or 90026-1234.",
            )

    if country == "FR" and not re.fullmatch(r"\d{5}", zip_code):
        return PolicyDecision(
            False,
            "INVALID_FR_ZIP",
            "Cannot create order: France postal code must be 5 digits.",
        )

    return None


def evaluate_tool_call(func_name: str, args: Dict[str, Any], user_message: str = "", session_id: str = "") -> PolicyDecision:
    if func_name in SAFE_TOOLS:
        return PolicyDecision(True, "POLICY_ALLOWED", "Safe read-only tool.")

    if func_name not in CRITICAL_TOOLS:
        return PolicyDecision(False, "TOOL_NOT_ALLOWED", f"Tool `{func_name}` is not registered in policy allowlist.")

    if func_name == "create_order":
        return _evaluate_create_order(args, user_message, session_id)

    return PolicyDecision(False, "TOOL_NOT_ALLOWED", f"Tool `{func_name}` is not allowed.")


def _evaluate_create_order(args: Dict[str, Any], user_message: str, session_id: str = "") -> PolicyDecision:
    if not ff_manager.is_order_creation_enabled():
        return PolicyDecision(False, "ORDER_CREATION_DISABLED", "TÃ­nh nÄƒng táº¡o Ä‘Æ¡n hÃ ng hiá»‡n Ä‘ang bá»‹ táº¯t bá»Ÿi quáº£n trá»‹ viÃªn.")

    sku = str(args.get("sku", "")).strip()
    if not sku:
        return PolicyDecision(False, "SKU_REQUIRED", "KhÃ´ng thá»ƒ táº¡o Ä‘Æ¡n: thiáº¿u mÃ£ SKU.")

    sku_record = db_store.get_sku_by_code(sku)
    if not sku_record:
        return PolicyDecision(False, "SKU_NOT_FOUND", f"KhÃ´ng thá»ƒ táº¡o Ä‘Æ¡n: SKU `{sku}` khÃ´ng tá»“n táº¡i trong catalog.")

    if session_id and not order_state.was_sku_presented(session_id, sku):
        return PolicyDecision(
            False,
            "SKU_PRESENTATION_REQUIRED",
            f"Cannot create order before presenting SKU `{sku}` details with get_sku_info.",
        )

    review_token = str(args.get("order_review_token") or "").strip()
    if session_id and not order_state.is_order_review_valid(session_id, review_token, args):
        return PolicyDecision(
            False,
            "ORDER_REVIEW_REQUIRED",
            "Cannot create order before returning an order summary/review to the user.",
        )

    if order_state.is_duplicate_order(args):
        return PolicyDecision(
            False,
            "DUPLICATE_ORDER_BLOCKED",
            "An identical order was created recently. Duplicate order creation is blocked.",
        )

    if not _user_confirmed_sku(user_message, sku):
        return PolicyDecision(
            False,
            "ORDER_CONFIRMATION_REQUIRED",
            (
                f"ChÆ°a táº¡o Ä‘Æ¡n. NgÆ°á»i dÃ¹ng pháº£i xÃ¡c nháº­n rÃµ mÃ£ SKU `{sku}` trong tin nháº¯n hiá»‡n táº¡i, "
                f"vÃ­ dá»¥: `XÃ¡c nháº­n Ä‘áº·t SKU {sku}`. KhÃ´ng Ä‘Æ°á»£c tá»± chá»n SKU ngáº«u nhiÃªn."
            ),
        )

    address = args.get("address") or {}
    required_address_fields = ["name", "street", "city", "state", "zip", "country"]
    missing = [field for field in required_address_fields if not address.get(field)]
    if missing:
        return PolicyDecision(
            False,
            "ADDRESS_REQUIRED",
            f"KhÃ´ng thá»ƒ táº¡o Ä‘Æ¡n: thiáº¿u thÃ´ng tin Ä‘á»‹a chá»‰ `{', '.join(missing)}`.",
        )

    address_issue = _validate_address_consistency(address)
    if address_issue:
        return address_issue

    provider = db_store.get_provider_by_id(sku_record.get("provider_id")) or {}
    supported_countries = provider.get("countries_served") or []
    destination_country = _normalize_country_code(str(address.get("country") or ""))
    if supported_countries and destination_country not in {str(country).upper() for country in supported_countries}:
        return PolicyDecision(
            False,
            "REGION_NOT_SUPPORTED",
            f"SKU `{sku}` is not supported for destination `{destination_country}` according to provider cache.",
        )

    quantity = int(args.get("quantity") or 0)
    if quantity <= 0:
        return PolicyDecision(False, "INVALID_QUANTITY", "KhÃ´ng thá»ƒ táº¡o Ä‘Æ¡n: sá»‘ lÆ°á»£ng pháº£i lá»›n hÆ¡n 0.")


    design_url_front = str(args.get("design_url_front") or "").strip()
    if not design_url_front:
        return PolicyDecision(
            False,
            "DESIGN_URL_REQUIRED",
            "Cannot create order: missing `design_url_front`. POD products require a front design URL.",
        )

    if not design_url_front.startswith(("http://", "https://")):
        return PolicyDecision(
            False,
            "INVALID_DESIGN_URL",
            "`design_url_front` must be a public http/https URL.",
        )

    return PolicyDecision(True, "POLICY_ALLOWED", "Create order policy checks passed.")
