import hashlib
import json
import time
from typing import Any, Dict


PRESENTED_SKU_TTL_SECONDS = 30 * 60
ORDER_REVIEW_TTL_SECONDS = 10 * 60
DUPLICATE_ORDER_TTL_SECONDS = 10 * 60

_presented_skus: Dict[str, Dict[str, float]] = {}
_order_reviews: Dict[str, Dict[str, Any]] = {}
_created_order_fingerprints: Dict[str, float] = {}


def _now() -> float:
    return time.time()


def _cleanup() -> None:
    now = _now()
    for session_id, skus in list(_presented_skus.items()):
        _presented_skus[session_id] = {
            sku: ts for sku, ts in skus.items()
            if now - ts <= PRESENTED_SKU_TTL_SECONDS
        }
        if not _presented_skus[session_id]:
            del _presented_skus[session_id]

    for token, review in list(_order_reviews.items()):
        if now - float(review.get("created_at") or 0) > ORDER_REVIEW_TTL_SECONDS:
            del _order_reviews[token]

    for fingerprint, ts in list(_created_order_fingerprints.items()):
        if now - ts > DUPLICATE_ORDER_TTL_SECONDS:
            del _created_order_fingerprints[fingerprint]


def order_fingerprint(args: Dict[str, Any]) -> str:
    address = args.get("address") or {}
    stable = {
        "sku": str(args.get("sku") or "").strip().upper(),
        "quantity": int(args.get("quantity") or 0),
        "address": {
            key: str(address.get(key) or "").strip().casefold()
            for key in ["name", "street", "city", "state", "zip", "country"]
        },
        "design_url_front": str(args.get("design_url_front") or "").strip(),
    }
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mark_sku_presented(session_id: str, sku: str) -> None:
    if not session_id or not sku:
        return
    _cleanup()
    _presented_skus.setdefault(session_id, {})[sku.strip().upper()] = _now()


def was_sku_presented(session_id: str, sku: str) -> bool:
    if not session_id or not sku:
        return False
    _cleanup()
    return sku.strip().upper() in _presented_skus.get(session_id, {})


def create_order_review(session_id: str, args: Dict[str, Any], summary: Dict[str, Any]) -> str:
    _cleanup()
    fingerprint = order_fingerprint(args)
    token = hashlib.sha256(f"{session_id}:{fingerprint}:{_now()}".encode("utf-8")).hexdigest()[:24]
    _order_reviews[token] = {
        "session_id": session_id,
        "fingerprint": fingerprint,
        "summary": summary,
        "created_at": _now(),
    }
    return token


def is_order_review_valid(session_id: str, token: str, args: Dict[str, Any]) -> bool:
    _cleanup()
    review = _order_reviews.get(str(token or ""))
    if not review:
        return False
    return (
        review.get("session_id") == session_id
        and review.get("fingerprint") == order_fingerprint(args)
    )


def is_duplicate_order(args: Dict[str, Any]) -> bool:
    _cleanup()
    return order_fingerprint(args) in _created_order_fingerprints


def mark_order_created(args: Dict[str, Any]) -> None:
    _cleanup()
    _created_order_fingerprints[order_fingerprint(args)] = _now()
