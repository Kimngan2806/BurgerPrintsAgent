def product_names(results):
    names = set()
    for name, result in results:
        if name == 'search_products':
            products = result.get('results') or []
        elif name == 'get_sku_info':
            products = [result.get('product') or {}]
        else:
            continue
        names.update(product['name'] for product in products if product.get('name'))
    return names


def recovered_reply(results, language):
    vi = language == 'vi'
    for name, result in reversed(results):
        if name == 'calculate_profit' and result.get('estimated_profit') is not None:
            profit = result['estimated_profit']
            percentage = result.get('margin_percent')
            text = (f'Lợi nhuận dự kiến theo chi phí bạn đã nhập là **{profit} USD**.'
                    if vi else f'Estimated profit using the costs you entered is **{profit} USD**.')
            if percentage is not None:
                text += (f' Biên lợi nhuận dự kiến là **{percentage}%**.'
                         if vi else f' The estimated margin is **{percentage}%**.')
            if result.get('unknown_costs'):
                text += (' Các khoản bạn để trống có thể làm thay đổi kết quả.'
                         if vi else ' Any costs left blank may change the result.')
            return text
        if name == 'get_base_cost' and (prices := [(code, price) for code, price in result.items()
                                                   if not code.startswith('_') and price is not None
                                                   and str(price).replace('.', '', 1).isdigit()]):
            heading = 'Giá gốc theo catalog' if vi else 'Catalog base prices'
            return f'**{heading}**\n\n' + '\n'.join(f'- `{code}`: **{price} USD**' for code, price in prices[:3])

    for name, result in reversed(results):
        if name == 'get_sku_info' and result.get('ok') and result.get('sku'):
            products = [{**(result.get('product') or {}), 'variants': [result['sku']]}]
        elif name == 'search_products' and result.get('results'):
            products = result['results']
        else:
            continue
        rows = []
        for product in products[:3]:
            variants = product.get('variants') or []
            if not variants:
                continue
            sku = next((v for v in variants if v.get('sku_code') == product.get('recommended_sku')), variants[0])
            if not sku.get('sku_code'):
                continue
            label = f"**{product['name']}** · " if product.get('name') else ''
            price = f" · {sku['price']} USD" if sku.get('price') is not None else ''
            rows.append(f"- {label}`{sku['sku_code']}`{price}")
        if rows:
            heading = ('Mình tra được các mẫu sau. Giá hiển thị là giá gốc, phí giao tính riêng.'
                       if vi else 'I found these catalog options. The base prices shown exclude shipping.')
            return heading + '\n\n' + '\n'.join(rows)

    if any(result.get('code') == 'CATALOG_UNAVAILABLE' for _, result in results):
        return ('Danh mục sản phẩm đang được nạp. Khi dữ liệu sẵn sàng, mình mới kiểm tra được mẫu và giá.'
                if vi else 'The catalog is loading. I can check products and prices once it is ready.')
    return None
