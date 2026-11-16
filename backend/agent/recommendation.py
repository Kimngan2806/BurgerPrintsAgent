import re
import unicodedata
from decimal import Decimal


def _plain_words(message: str) -> str:
    plain = ''.join(ch for ch in unicodedata.normalize('NFD', message.casefold())
                    if unicodedata.category(ch) != 'Mn').replace('đ', 'd')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', plain).split())


def beginner_hoodie_question(message: str) -> bool:
    """Recognize general advice; let the model handle extra shopping constraints."""
    plain = _plain_words(message)
    budget = r'(?:budget friendly|affordable|low cost|gia re|gia mem|tiet kiem)'
    hoodie = r'(?:hoodie|hoodies|ao hoodie|ao ni co mu)'
    beginner = r'(?:beginner|beginners|a beginner|nguoi moi(?: bat dau)?)'
    return bool(re.fullmatch(
        rf'(?:co |tu van |goi y )?{hoodie}(?: nao)? {budget} cho {beginner}(?: khong)?|'
        rf'(?:can you recommend |can you suggest |recommend |suggest |any |are there any |is there an? )?'
        rf'{budget} {hoodie} for {beginner}',
        plain,
    ))


def gross_margin_definition(message: str, language: str) -> str | None:
    plain = _plain_words(message)
    if not re.fullmatch(
        r'(?:toi moi ban )?(?:gross margin|bien loi nhuan gop) (?:nghia )?la gi(?: trong (?:pod|in theo yeu cau))?|'
        r'what is gross margin(?: in (?:pod|print on demand))?', plain,
    ):
        return None
    if language == 'vi':
        return ('**Biên lợi nhuận gộp** là phần trăm doanh thu còn lại sau khi trừ giá vốn hàng bán. '
                'Ví dụ, nếu bạn bán một áo với giá 25 USD và giá vốn là 15 USD, '
                'bạn còn 10 USD lợi nhuận gộp, tương đương **40%** giá bán. '
                'Khi tính cho cửa hàng, hãy dùng các chi phí trực tiếp thực tế của đơn để xác định giá vốn.')
    return ('**Gross margin** is the percentage of revenue left after direct costs. '
            'For example, a shirt that sells for $25 and has $15 in direct costs leaves $10 in gross profit, '
            'or a **40% gross margin**. Use your actual direct costs when calculating it for your store.')


def hoodie_recommendation(result: dict, language: str) -> str:
    choices = result.get('results', [])
    if not choices:
        unavailable = result.get('code') == 'CATALOG_UNAVAILABLE'
        if language == 'vi':
            return ('Catalog chưa đồng bộ, nên mình chưa kiểm tra được mẫu áo và giá.' if unavailable
                    else 'Mình chưa thấy mẫu áo nỉ có mũ phù hợp có giá được ghi trong catalog. Bạn định bán ở thị trường nào?')
        return ('The catalog is still syncing, so I cannot verify hoodie options and prices yet.' if unavailable
                else 'I could not find a suitable hoodie with a catalog price. Which market are you selling in?')

    item = choices[0]
    variant = item['variants'][0]
    name = item['name']
    sku = variant['sku_code']
    price = f"{Decimal(str(variant['price'])):.2f}"
    if language == 'vi':
        return (
            f"Mình sẽ bắt đầu với **{name}**. Đây là lựa chọn có giá gốc thấp trong các mẫu áo nỉ có mũ phù hợp "
            f"mình tra được. SKU `{sku}` có giá **{price.replace('.', ',')} USD/áo** trong catalog, chưa gồm phí giao.\n\n"
            'Nếu mới bán, bạn có thể dùng một mẫu cơ bản để thử thiết kế mà giữ chi phí mỗi áo ở mức dễ kiểm soát. '
            'Nếu muốn bán ở phân khúc cao cấp, nên xem mẫu thực tế để so độ mềm và dáng áo trước khi chốt.\n\n'
            'Bạn định bán ở thị trường nào để mình kiểm tra phí giao và phiên bản phù hợp?'
        )
    return (
        f"I’d start with **{name}**. It is a low base-cost option among the suitable hoodies I checked. "
        f"SKU `{sku}` is **${price} USD per hoodie** in the catalog, before shipping.\n\n"
        'A basic style keeps your unit cost manageable while you test your first designs. '
        'If you want to position it as a premium product, compare a sample for softness and fit before committing.\n\n'
        'Which market are you selling in? I can check the relevant version and shipping cost.'
    )
