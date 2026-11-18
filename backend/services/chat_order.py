import unicodedata

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from core.config import settings
from services.commerce import review_draft, submit_draft


CONFIRM_COMMAND = 'XÁC NHẬN ĐƠN HÀNG'
REVIEW_COMMAND = 'XEM BẢN DUYỆT'
START_COMMAND = 'tôi muốn đặt hàng'
ASK_SKU = 'Bạn muốn đặt SKU nào? Bạn có thể gửi mã SKU đầy đủ hoặc tên sản phẩm để mình tra catalog.'


def is_command(text, command):
    def normalize(value):
        return ' '.join(''.join(
            ch for ch in unicodedata.normalize('NFD', value.casefold())
            if unicodedata.category(ch) != 'Mn'
        ).replace('đ', 'd').split())

    return normalize(text) == normalize(command)


def order_chat_reply(events, conversation, message):
    if not any(
        msg['role'] == 'user' and is_command(msg['content'].strip('.!?'), START_COMMAND)
        for msg in conversation['messages'][-16:]
    ):
        return None
    for event in reversed(events):
        result = event['result']
        if event['tool'] == 'update_draft' and result.get('updated') and result['draft']['lines']:
            draft = result['draft']
            items = ', '.join(f"`{line['sku']}` × {line['quantity']}" for line in draft['lines'])
            return f'Đã lưu đơn nháp gồm {items}.'
        if event['tool'] != 'get_sku_info':
            continue
        if result.get('code') == 'SKU_VARIANT_REQUIRED':
            options = [f"- `{sku['sku_code']}` · {sku['color']} · {sku['size']}" for sku in result['options'][:5]]
            return '\n'.join([f"Hãy chọn mã SKU đầy đủ cho dòng `{result['base_code']}`.", '', *options])
        sku = result.get('sku', {}).get('sku_code')
        if sku and message.strip().casefold() in {sku.casefold(), 'sku: ' + sku.casefold()}:
            return f'Bạn muốn đặt bao nhiêu sản phẩm cho SKU `{sku}`?'
    return None


def order_preview(review):
    summary = review['summary']
    address = summary['address']
    rows = [
        f"- {line.get('product_name') or line['sku']} · `{line['sku']}` × **{line['quantity']}**"
        f" · Thiết kế {line['file']['name']}"
        + (f" · Giá catalog {line['catalog_price']} USD/chiếc" if line.get('catalog_price') is not None else '')
        for line in summary['lines']
    ]
    destination = ', '.join(address[key] for key in ('street', 'city', 'state', 'zip', 'country') if address.get(key))
    mode = 'Sandbox (đơn thử)' if summary['sandbox'] else 'Đơn thật'
    instruction = (
        f'Khi đã kiểm tra nội dung và file in, nhắn **{CONFIRM_COMMAND}** trong 10 phút để gửi đúng bản duyệt này.'
        if settings.ENABLE_ORDER_SUBMISSION and settings.BURGERPRINTS_API_KEY
        else 'Máy chủ chưa bật gửi đơn. Bản duyệt dùng để kiểm tra thông tin đã lưu.'
    )
    return '\n'.join([
        f"**Bản duyệt đơn v{review['draft_version']} · {mode}**", '', *rows, '',
        f"- Người nhận: {address['name']}",
        f"- Email: {address.get('email', '')}",
        f"- Điện thoại: {address.get('phone', '')}",
        f"- Giao đến: {destination}", '',
        'Phí giao hàng, thuế và phụ phí chưa được xác nhận. Hãy đối chiếu file với mẫu in của SKU.',
        summary['transaction_notice'], '',
        instruction,
    ])


def submission_message(submission, summary):
    result = submission['result']
    if submission['state'] == 'created':
        mode = 'Đơn thử' if summary['sandbox'] else 'Đơn hàng'
        status = result.get('status') or result.get('order_status') or 'BurgerPrints đã tạo đơn'
        rows = [f"- {line.get('product_name') or line['sku']} · `{line['sku']}` × {line['quantity']}"
                for line in summary['lines']]
        return '\n'.join([
            f'**{mode} đã được tạo trên BurgerPrints.**', '',
            f"- Order ID: `{result['order_id']}`", *rows,
            f'- Trạng thái: {status}', '',
            'Bạn có thể đối chiếu trong mục **Đơn hàng**.',
        ])
    if submission['state'] == 'rejected':
        details = []
        errors = result.get('errors') or []
        if isinstance(errors, dict):
            errors = [errors]
        elif isinstance(errors, str):
            errors = [errors]
        for error in errors:
            if isinstance(error, str):
                details.append(error)
            elif isinstance(error, dict):
                details.extend(str(value) for value in error.values() if value)
        reason = ' · '.join(str(item) for item in (result.get('message'), *details) if item)
        return ('**BurgerPrints chưa tạo đơn.**\n\n'
                f"Lý do: {reason or 'API từ chối yêu cầu và không trả chi tiết.'}\n\n"
                'Hãy sửa thông tin trong đơn nháp, xem lại bản duyệt rồi xác nhận lại.')
    return (f"Đang xác minh kết quả tại BurgerPrints. Mã tham chiếu: `{submission['reference']}`. "
            'Hãy kiểm tra mục **Đơn hàng** trước khi gửi lại.')


async def preview_chat_order(owner, conversation):
    ident = conversation.get('draft_id')
    if not ident:
        return None, 'Chưa có đơn nháp. Bạn muốn đặt mã SKU hoặc sản phẩm nào?'
    from services.commerce import workspace

    try:
        draft = await run_in_threadpool(workspace.get, owner, ident, 'draft')
        review = await review_draft(owner, ident, draft['version'], chat_confirmation=True)
    except HTTPException as error:
        return None, str(error.detail)
    return {'id': review['id'], 'draft_id': ident}, order_preview(review)


async def confirm_chat_order(owner, conversation):
    reference = conversation.get('chat_order_review')
    if not reference or reference['draft_id'] != conversation.get('draft_id'):
        return f'Bạn cần xem bản duyệt trước khi xác nhận. Nhắn **{REVIEW_COMMAND}** để kiểm tra đơn.'
    from services.commerce import workspace

    try:
        review = await run_in_threadpool(workspace.get, owner, reference['id'], 'review')
        submission = await submit_draft(owner, reference['draft_id'], review['id'], chat_confirmation=True)
    except HTTPException as error:
        return f'**Chưa gửi đơn.** {error.detail} Nhắn **{REVIEW_COMMAND}** sau khi kiểm tra lại.'
    return submission_message(submission, review['summary'])
