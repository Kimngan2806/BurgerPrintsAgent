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


def is_premium_followup(message: str) -> bool:
    return bool(re.fullmatch(
        r'(?:ban co the |hay |thu )?so sanh (?:voi |no voi )?(?:mot )?'
        r'(?:(?:lua chon|mau|loai) )?(?:premium|cao cap) hon(?: duoc khong| khong| giup minh)?|'
        r'(?:can you |could you |please )?compare (?:it |that |this )?with (?:a )?(?:more )?premium (?:option|alternative|hoodie)',
        _plain_words(message),
    ))


def _sample_price(product, language):
    sku = product['variants'][0]
    price = f"{Decimal(str(sku['price'])):.2f}"
    return (f"{price.replace('.', ',')} USD/áo" if language == 'vi' else f"${price} USD per hoodie"), sku['sku_code']


def _advice_sections(language, recommendation, reasoning, tradeoff, question):
    headings = ('Đề xuất', 'Lý do', 'Điểm đánh đổi') if language == 'vi' else ('Recommendation', 'Reasoning', 'Trade-off')
    return '\n\n'.join([*(f'**{heading}**\n\n{text}' for heading, text in zip(headings, (recommendation, reasoning, tradeoff))), question])


def premium_hoodie_comparison(result: dict, language: str) -> str:
    if result.get('code') == 'CATALOG_UNAVAILABLE':
        return ('Catalog chưa đồng bộ nên mình chưa đối chiếu được hai mẫu và giá.' if language == 'vi'
                else 'The catalog is still syncing, so I cannot verify both hoodies and their prices yet.')
    choices = result.get('results', [])
    if len(choices) < 2:
        return ('Mình chưa tìm được mẫu được catalog ghi là cao cấp với giá để so trực tiếp. Bạn bán ở thị trường nào?'
                if language == 'vi' else 'I could not verify a priced premium option to compare. Which market are you selling in?')
    original, premium = choices
    base_price, base_code = _sample_price(original, language)
    premium_price, premium_code = _sample_price(premium, language)
    gap = Decimal(str(premium['variants'][0]['price'])) - Decimal(str(original['variants'][0]['price']))
    if language == 'vi':
        gap_vi = f'{gap:.2f}'.replace('.', ',')
        return _advice_sections(language,
            f"Nếu bạn vẫn đang thử mẫu bán đầu tiên, mình sẽ giữ **{original['name']}**. "
            f"Nếu muốn thử dòng cao cấp, có thể cân nhắc **{premium['name']}**.",
            f"Mẫu ban đầu có giá gốc **{base_price}** ở mã `{base_code}`. Mẫu cao cấp có giá gốc **{premium_price}** "
            f"ở mã `{premium_code}`, chênh **{gap_vi} USD/áo**. Nếu chưa chắc khách sẽ trả thêm, "
            'mình sẽ dành khoản chênh để thử thiết kế khác.',
            'Hai mức giá đều chưa gồm phí giao. Danh mục chưa đủ thông tin để kết luận mẫu cao cấp mềm hơn hoặc bền hơn. '
            'Nếu chất áo là lý do bạn muốn nâng cấp, nên xem mẫu thực tế trước khi chốt.',
            'Bạn định bán ở thị trường nào? Mình có thể giúp bạn so tiếp phần phí giao.')
    return _advice_sections(language,
        f"I’d keep **{original['name']}** for a first test. If you want a premium line, consider **{premium['name']}**.",
        f"The original costs **{base_price}** for `{base_code}`. The premium option costs **{premium_price}** for "
        f"`{premium_code}`, a difference of **${gap:.2f} per hoodie**. If you haven’t tested what customers will pay, I’d put the difference toward testing more designs.",
        'Both prices exclude shipping. The catalog does not establish which feels softer or lasts longer, so compare samples if fabric quality is what matters to you.',
        'Which market are you selling in? That will help narrow down the shipping costs.')


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
    name = item['name']
    price, sku = _sample_price(item, language)
    if language == 'vi':
        return _advice_sections(language,
            f"Nếu mới bán, mình sẽ bắt đầu với **{name}**. Dáng cơ bản dễ dùng để thử một vài thiết kế đầu tiên.",
            f"Mã `{sku}` có giá gốc **{price}**, chưa gồm phí giao. Bạn có thể thử xem mẫu nào có người mua trước khi bỏ thêm tiền cho dòng áo cao cấp.",
            'Nếu khách của bạn quan tâm độ mềm hoặc phom áo, nên đặt mẫu để kiểm tra trước. Giá gốc thấp cũng cần đi cùng phí giao phù hợp thì mới dễ giữ lời.',
            'Bạn định bán ở thị trường nào để mình kiểm tra phí giao và phiên bản phù hợp?'
        )
    return _advice_sections(language,
        f"I’d start with **{name}**. A basic cut gives you a practical starting point for your first designs.",
        f"SKU `{sku}` costs **{price}** before shipping. You can test what sells before spending more on a premium hoodie.",
        'Order a sample if softness or fit matters to your customers. Factor in shipping to see what margin you actually have.',
        'Which market are you selling in? I can check the relevant version and shipping cost.'
    )
