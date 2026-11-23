import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR

from agent.recommendation import _advice_sections, _plain_words


MARGIN_TERM = re.compile(r'\b(?:margin|bien loi nhuan|ty suat loi nhuan)\b')
PRICE_QUESTION = re.compile(r'\b(?:gia bao nhieu|gia san pham|gia mau|ban bao nhieu|ban gia bao nhieu|'
                            r'how much|what price|cost of|price of|selling price)\b')
TARGET = re.compile(r'(?<![\w.,-])(?P<strict>\b(?:hon|tren|vuot|over|above|more than)\s+|(?<![=])>\s*)?'
                    r'(?P<percent>-?\d{1,5}(?:[.,]\d{1,5})?)\s*%')
EXPLICIT_COST = re.compile(r'[$₫€£]|\b(?:usd|vnd|dollars?|dong)\b', re.IGNORECASE)


def pricing_request(message):
    plain = _plain_words(message)
    normalized = ''.join(ch for ch in unicodedata.normalize('NFD', message.casefold())
                         if unicodedata.category(ch) != 'Mn').replace('đ', 'd')
    targets = list(TARGET.finditer(normalized))
    supplied_amount = EXPLICIT_COST.search(normalized)
    if MARGIN_TERM.search(plain) and len(targets) == 1 and not supplied_amount:
        target = targets[0]
        other_text = normalized[:target.start()] + normalized[target.end():]
        if re.search(r'(?<![\w-])\d+(?![\w-])', other_text):
            return None
        if re.search(r'\b(?:search|tim san pham|tim mau|so sanh|compare|roi|markup|quang cao|advertising|'
                     r'giam gia|discount|tax|thue|bang phi|fee schedule)\b', plain):
            return None
        return Decimal(target['percent'].replace(',', '.')), bool(target['strict'])
    if (PRICE_QUESTION.search(plain) and not supplied_amount and not targets
            and re.search(r'\b(?:nay|do|kia|tren|dau tien|thu hai|thu ba|this|that|first|second|third|it)\b', plain)
            and not re.search(r'\b(?:ship|giao hang|van chuyen|shipping|compare|so sanh|discount|giam gia)\b', plain)):
        return None, False
    return None


def price_candidates(message, remembered):
    candidates = []
    explicit = []
    seen = set()
    for product in remembered:
        variants = {sku['sku_code']: sku for sku in product.get('variants', []) if sku.get('sku_code')}
        if not variants:
            continue
        selected = variants.get(product.get('recommended_sku')) or next(iter(variants.values()))
        if selected['sku_code'] not in seen:
            candidates.append((product.get('name'), selected))
            seen.add(selected['sku_code'])
        explicit.extend((product.get('name'), sku) for code, sku in variants.items()
                        if re.search(rf'(?<![\w-]){re.escape(code)}(?![\w-])', message, re.IGNORECASE))
    if explicit:
        return list({sku['sku_code']: (name, sku) for name, sku in explicit}.values())[:3]
    plain = _plain_words(message)
    if re.search(r'\bsku\s*[:#]?\s+[\w-]*\d[\w-]*', message, re.IGNORECASE):
        return []
    for index, ordinal in enumerate(('dau tien|thu nhat|first', 'thu hai|second', 'thu ba|third')):
        if re.search(rf'\b(?:{ordinal})\b', plain):
            return candidates[index:index + 1]
    return candidates[:3]


def _usable_price(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount.is_finite() and 0 < amount <= 1_000_000 else None


def _money(amount, language):
    value = f'{amount:.2f}'
    return f"{value.replace('.', ',')} USD" if language == 'vi' else f'${value} USD'


def pricing_answer(request, candidates, current_prices, language):
    target, strict = request
    vi = language == 'vi'
    if target is not None and not 0 <= target < 100:
        return ('Bạn hãy chọn biên lợi nhuận từ 0% đến dưới 100% để tính giá bán khi có chi phí.'
                if vi else 'Choose a margin from 0% up to, but below, 100% to price an item with costs.')

    rows = []
    for name, sku in candidates:
        code = sku['sku_code']
        price = _usable_price(current_prices.get(code))
        source = 'giá gốc catalog' if vi else 'catalog base price'
        if price is None:
            price = _usable_price(sku.get('price'))
            source = 'giá gốc ở lần tra trước' if vi else 'base price from the previous lookup'
        if price is None:
            continue
        item = f"**{name}** · `{code}`" if name else f'`{code}`'
        row = f'- {item}: {_money(price, language)} ({source})'
        if target is not None:
            floor = price / (1 - target / 100)
            minimum = (floor.quantize(Decimal('.01'), rounding=ROUND_FLOOR) + Decimal('.01')
                       if strict else floor.quantize(Decimal('.01'), rounding=ROUND_CEILING))
            row += f' → từ **{_money(minimum, language)}**' if vi else f' → from **{_money(minimum, language)}**'
        rows.append(row + '.')

    if target is None:
        prices = '\n'.join(rows)
        if vi:
            return ((prices + '\n\n') if prices else 'Mình chưa có giá gốc đã xác nhận cho mẫu bạn hỏi. ') + (
                'Để chọn giá bán có lời, hãy cộng giá gốc, phí giao và phí nền tảng cho mỗi sản phẩm. '
                'Bạn muốn giữ biên lợi nhuận bao nhiêu phần trăm?'
            )
        return ((prices + '\n\n') if prices else 'I don’t have a verified base price for that item. ') + (
            'Start with the base price, shipping, and marketplace fees per item. What margin are you aiming for?'
        )

    percentage = format(target.normalize(), 'f')
    if vi:
        percentage = percentage.replace('.', ',')
        goal = f"{'trên ' if strict else ''}{percentage}%"
        recommendation = (f'Đây là các mức giá sàn để nhắm biên lợi nhuận **{goal}**, nếu chỉ tính giá gốc:\n\n'
                          + '\n'.join(rows) if rows else
                          f'Để nhắm biên lợi nhuận **{goal}**, áp dụng công thức cho tổng chi phí trên một sản phẩm.')
        return _advice_sections(language, recommendation,
            f'Chia tổng chi phí cho **(1 − {percentage}%)**. Nếu mục tiêu là vượt mức này, chọn giá cao hơn kết quả.',
            'Mức sàn sẽ tăng khi cộng phí giao, phí nền tảng và các chi phí khác. '
            'Với khoản phí tính theo phần trăm doanh thu, cần tính theo tỷ lệ phí thay vì cộng một số tiền cố định.',
            'Bạn có giá gốc và phí giao thực tế cho một SKU để mình tính sát hơn không?' if not rows else
            'Bạn có phí giao và phí nền tảng trên mỗi sản phẩm để mình tính sát hơn không?')
    goal = f"{'above ' if strict else ''}{percentage}%"
    recommendation = (f'Here are the price floors for **{goal} margin** using base prices alone:\n\n' + '\n'.join(rows)
                      if rows else f'To aim for **{goal} margin**, use the total cost for one item in the formula.')
    return _advice_sections(language, recommendation,
        f'Divide total cost by **(1 − {percentage}%)**. To exceed the target, price above that result.',
        'Shipping, marketplace fees, and other costs raise the floor. Percentage-based fees need to be calculated '
        'as a share of revenue.',
        'Do you have the base price and shipping cost for a SKU so I can calculate it?' if not rows else
        'What are your shipping and marketplace fees per item?')
