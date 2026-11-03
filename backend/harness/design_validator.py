import ipaddress
import socket
import struct
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx


MAX_DESIGN_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
DEFAULT_ALLOWED_RESOLUTIONS = {
    (4800, 5400),
    (2100, 2400),
    (4200, 4800),
    (2400, 3200),
    (2800, 3200),
    (4500, 5400),
    (2400, 3197),
    (4050, 4650),
    (3000, 4000),
    (4500, 5000),
    (3600, 4795),
    (4050, 4050),
    (3600, 4800),
    (4500, 5100),
    (2935, 3374),
    (2953, 3374),
    (4535, 5480),
    (4500, 4200),
    (4500, 3600),
    (4500, 5700),
    (4500, 5143),
    (3400, 4500),
    (3951, 4919),
    (4500, 5600),
    (3692, 4800),
}


@dataclass(frozen=True)
class DesignValidationResult:
    ok: bool
    code: str
    message: str
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "width": self.width,
            "height": self.height,
            "allowed_resolutions": [f"{w}x{h}" for w, h in sorted(DEFAULT_ALLOWED_RESOLUTIONS)],
        }


def _is_private_host(hostname: str) -> bool:
    if not hostname:
        return True
    lowered = hostname.lower()
    if lowered in {"localhost"} or lowered.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(lowered)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except Exception:
        return True
    return False


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in {0xD8, 0xD9}:
            continue
        if i + 2 > len(data):
            return None
        length = int.from_bytes(data[i:i + 2], "big")
        if length < 2 or i + length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if i + 7 <= len(data):
                height = int.from_bytes(data[i + 3:i + 5], "big")
                width = int.from_bytes(data[i + 5:i + 7], "big")
                return width, height
        i += length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP") or len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    return None


def _image_size(data: bytes) -> tuple[int, int] | None:
    return _png_size(data) or _jpeg_size(data) or _webp_size(data)


async def validate_design_url(url: str) -> DesignValidationResult:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return DesignValidationResult(False, "INVALID_DESIGN_URL", "Design URL must start with http:// or https://.")
    if _is_private_host(parsed.hostname or ""):
        return DesignValidationResult(False, "PRIVATE_DESIGN_URL", "Design URL must be public and cannot point to localhost/private network.")

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"Range": "bytes=0-1048575"})
            response.raise_for_status()
    except Exception as exc:
        return DesignValidationResult(False, "DESIGN_URL_FETCH_FAILED", f"Could not fetch design URL: {exc}")

    content_type = (response.headers.get("content-type") or "").split(";")[0].lower()
    content_length_header = response.headers.get("content-length")
    content_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
    if content_length and content_length > MAX_DESIGN_BYTES:
        return DesignValidationResult(False, "DESIGN_FILE_TOO_LARGE", "Design file is too large.", content_type, content_length)
    if content_type == "image/svg+xml" or urlparse(url).path.lower().endswith(".svg"):
        return DesignValidationResult(False, "SVG_DESIGN_NOT_ALLOWED", "SVG design files are not allowed for order creation.", content_type, content_length)
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return DesignValidationResult(False, "INVALID_DESIGN_CONTENT_TYPE", "Design URL must return PNG, JPEG, or WebP image.", content_type, content_length)

    size = _image_size(response.content)
    if not size:
        return DesignValidationResult(False, "DESIGN_NOT_IMAGE", "Design URL did not return a readable image.", content_type, content_length)
    width, height = size
    if (width, height) not in DEFAULT_ALLOWED_RESOLUTIONS:
        return DesignValidationResult(
            False,
            "DESIGN_RESOLUTION_INVALID",
            f"Design resolution {width}x{height} is not accepted for this product.",
            content_type,
            content_length,
            width,
            height,
        )
    return DesignValidationResult(True, "DESIGN_VALID", "Design image is valid.", content_type, content_length, width, height)
