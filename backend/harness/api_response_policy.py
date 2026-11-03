import re
from typing import Any, Dict, List


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    return str(value or "")


def parse_burgerprints_error(response: Dict[str, Any]) -> Dict[str, Any]:
    text = _flatten_text(response)
    lowered = text.lower()

    if "shipping services are not available" in lowered:
        return {
            "ok": False,
            "code": "SHIPPING_SERVICE_UNAVAILABLE",
            "message": "Shipping service is not available for this SKU and destination.",
            "raw_message": text,
            "next_action": "Ask the user to change destination or choose another SKU/provider.",
        }

    if "design is required" in lowered:
        return {
            "ok": False,
            "code": "DESIGN_URL_REQUIRED_BY_API",
            "message": "BurgerPrints requires a front design image for this product.",
            "raw_message": text,
            "next_action": "Ask the user for a public design_url_front.",
        }

    if "resolution" in lowered and ("pixel" in lowered or "px" in lowered):
        resolutions: List[str] = sorted(set(re.findall(r"\b\d{3,5}\s*x\s*\d{3,5}\b", text, flags=re.I)))
        return {
            "ok": False,
            "code": "DESIGN_RESOLUTION_INVALID",
            "message": "Design image resolution is not accepted by BurgerPrints.",
            "required_resolutions": [item.replace(" ", "") for item in resolutions],
            "raw_message": text,
            "next_action": "Ask the user to resize the artwork to one of the required width x height values and send a new design_url_front.",
        }

    return {
        "ok": False,
        "code": "BURGERPRINTS_API_ERROR",
        "message": "BurgerPrints API returned an error.",
        "raw_message": text,
        "next_action": "Show the error to the user and ask for corrected input if needed.",
    }
