"""Basic file checks do not certify SKU print requirements."""
import io
import ipaddress
import socket
import warnings
from dataclasses import asdict, dataclass
from urllib.parse import urlparse, urljoin
import httpx
from PIL import Image

MAX_DESIGN_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class DesignValidationResult:
    ok: bool
    code: str
    message: str
    content_type: str | None = None
    content_length: int | None = None
    width: int | None = None
    height: int | None = None
    level: str = 'basic'
    print_verified: bool = False

    def to_dict(self):
        return asdict(self)


def _is_private_host(hostname):
    try:
        addresses = [i[4][0] for i in socket.getaddrinfo(hostname, 443)]
        return not addresses or any(not ipaddress.ip_address(i).is_global for i in addresses)
    except (OSError, ValueError):
        return True


async def fetch_design(url):
    async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False) as client:
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password or _is_private_host(parsed.hostname):
                raise ValueError('Cần URL ảnh công khai; không dùng địa chỉ nội bộ hoặc link riêng tư.')
            async with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get('location', ''))
                    continue
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_DESIGN_BYTES:
                        raise ValueError('File vượt quá giới hạn 25 MB.')
                return bytes(data)
    raise ValueError('URL chuyển hướng quá nhiều lần.')


def validate_design_bytes(data):
    if not data or len(data) > MAX_DESIGN_BYTES:
        return DesignValidationResult(False, 'DESIGN_FILE_TOO_LARGE', 'File rỗng hoặc lớn hơn 25 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise ValueError('Unsupported image')
                width, height = image.size
                mime = Image.MIME[image.format]
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        return DesignValidationResult(True, 'BASIC_VALID_PRINT_UNVERIFIED',
            'Đã qua kiểm tra file cơ bản, chưa đủ dữ liệu xác nhận chuẩn in.', mime, len(data), width, height)
    except Exception:
        return DesignValidationResult(False, 'DESIGN_NOT_IMAGE', 'File lỗi hoặc không phải ảnh PNG/JPEG/WebP đọc được.')


async def validate_design_url(url):
    try:
        return validate_design_bytes(await fetch_design(url))
    except Exception:
        return DesignValidationResult(False, 'DESIGN_URL_FETCH_FAILED',
            'Không đọc được URL ảnh. Kiểm tra quyền công khai và thử tải file trực tiếp.')
