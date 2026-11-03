# BurgerPrints API Data Fields

Tài liệu này liệt kê các nhóm dữ liệu có thể lấy từ BurgerPrints API v2, các field quan trọng, và trạng thái hiện tại trong dự án.

Base URL:

```text
https://api.burgerprints.com/v2
```

Header xác thực:

```http
api-key: <BURGERPRINTS_API_KEY>
```

## 1. Authenticated User

Endpoint:

```text
GET /v2/authenticated
```

Dùng để kiểm tra API key có hợp lệ hay không.

| Field | Ý nghĩa |
|---|---|
| `is_success` | API key hợp lệ hay không |
| `message` | Thông báo từ BurgerPrints |

Trạng thái trong dự án:

```text
Chưa lưu vào DuckDB.
```

## 2. Product List

Endpoint:

```text
GET /v2/product
```

Query params:

| Param | Ý nghĩa |
|---|---|
| `page` | Trang dữ liệu |
| `page_size` | Số item mỗi trang, tối đa 500 |

Field chính:

| Field | Ý nghĩa |
|---|---|
| `short_code` | Mã base product, ví dụ `USG5000` |
| `name` | Tên sản phẩm |
| `html_desc` | Mô tả HTML |
| `desc` | Mô tả text |
| `url` | URL sản phẩm |
| `design_type` | Loại thiết kế |
| `design_url` | URL design/template nếu có |

Trạng thái trong dự án:

```text
Đã sync vào bảng products trong DuckDB.
```

## 3. Product Detail

Endpoint:

```text
GET /v2/product/{id}
```

Ví dụ:

```text
GET /v2/product/USG5000
```

Field cấp product/base:

| Field | Ý nghĩa |
|---|---|
| `short_code` | Mã base product |
| `catalog_id` | ID catalog |
| `name` | Tên sản phẩm |
| `html_desc` | Mô tả HTML |
| `available_sizes` | Danh sách size có sẵn |
| `available_colors` | Danh sách màu có sẵn |
| `variations` | Danh sách SKU/variation |
| `design_type` | Loại thiết kế |
| `design_url` | URL design/template nếu có |

Field trong `available_sizes`:

| Field | Ý nghĩa |
|---|---|
| `id` | ID size |
| `name` | Tên size |

Field trong `available_colors`:

| Field | Ý nghĩa |
|---|---|
| `id` | ID màu |
| `name` | Tên màu |
| `color_hex` | Mã màu hex |

Field trong `variations`:

| Field | Ý nghĩa |
|---|---|
| `sku` | Mã SKU cụ thể |
| `size_id` | ID size |
| `size` | Tên size |
| `color_id` | ID màu |
| `color` | Tên màu |
| `color_hex` | Mã màu hex |
| `price` | Giá base của SKU |
| `2nd_price` | Giá item thứ 2 |
| `addition_price` | Phụ phí nếu có |
| `partner_id` | ID xưởng/partner |
| `partner_name` | Tên xưởng/partner |

Trạng thái trong dự án:

```text
Đã sync vào bảng products, skus và providers trong DuckDB.
```

## 4. Out Of Stock

Endpoint:

```text
GET /v2/product/outofstock
```

Field chính:

| Field | Ý nghĩa |
|---|---|
| `shortCode` | Mã base product |
| `shortCodeName` | Tên base product |
| `sku` | Danh sách SKU đang out of stock |

Trạng thái trong dự án:

```text
Chưa sync vào DuckDB.
Nên thêm nếu muốn tránh recommend SKU hết hàng.
```

## 5. Get All Orders

Endpoint:

```text
GET /v2/order
```

Query params:

| Param | Ý nghĩa |
|---|---|
| `sandbox` | Lấy order sandbox hay real |
| `reference` | Lọc theo reference order ID |
| `store_id` | Lọc theo store |
| `state` | Lọc theo trạng thái |
| `start_date` | Lọc từ thời điểm |
| `end_date` | Lọc đến thời điểm |
| `page` | Trang dữ liệu |
| `page_size` | Số item mỗi trang, tối đa 500 |

Trạng thái trong dự án:

```text
Chưa sync vào DuckDB.
```

## 6. Get Order Detail

Endpoint:

```text
GET /v2/order/{id}
```

Field chính:

| Field | Ý nghĩa |
|---|---|
| `id` | Mã order BurgerPrints |
| `reference_order_id` | Mã order bên hệ thống của mình |
| `production_service` | Dịch vụ sản xuất, ví dụ `Priority` |
| `status` | Trạng thái order |
| `amount` | Tổng tiền |
| `sub_amount` | Tiền sản phẩm |
| `shipping_fee` | Phí ship thực tế |
| `shipping_method` | Phương thức ship |
| `callback_url` | URL callback |
| `shipping` | Thông tin người nhận |
| `items` | Danh sách item |
| `trackings` | Tracking shipment |

Field trong `shipping`:

| Field | Ý nghĩa |
|---|---|
| `name` | Tên người nhận |
| `email` | Email người nhận |
| `phone` | Số điện thoại |
| `gift` | Có phải quà tặng không |
| `address` | Địa chỉ nhận hàng |

Field trong `shipping.address`:

| Field | Ý nghĩa |
|---|---|
| `line1` | Địa chỉ dòng 1 |
| `line2` | Địa chỉ dòng 2 |
| `city` | Thành phố |
| `state` | State/province |
| `postal_code` | Zip/postal code |
| `country` | Mã quốc gia |
| `country_name` | Tên quốc gia |
| `addr_verified` | Địa chỉ đã được verify chưa |
| `addr_verified_note` | Ghi chú verify địa chỉ |

Field trong `items`:

| Field | Ý nghĩa |
|---|---|
| `id` | ID item |
| `catalog_sku` | SKU catalog |
| `base_short_code` | Mã base product |
| `quantity` | Số lượng |
| `price` | Giá item |
| `amount` | Thành tiền |
| `shipping_fee` | Phí ship của item |
| `currency` | Tiền tệ |
| `size_name` | Tên size |
| `tax_amount` | Tiền thuế |
| `tax_rate` | Tỷ lệ thuế |
| `design_front_url` | Design mặt trước |
| `design_back_url` | Design mặt sau |
| `mockup_front_url` | Mockup mặt trước |
| `mockup_back_url` | Mockup mặt sau |

Field trong `trackings`:

| Field | Ý nghĩa |
|---|---|
| `carrier` | Hãng vận chuyển |
| `created_date` | Ngày tạo tracking |
| `code` | Mã tracking |
| `url` | URL tracking |

Trạng thái trong dự án:

```text
Chưa sync vào DuckDB.
Có thể dùng để lấy shipping_fee thực tế và tracking sau khi order đã tạo.
```

## 7. Create Order

Endpoint:

```text
POST /v2/order
```

Các field shipping:

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `shipping_name` | Có | Tên người nhận |
| `shipping_address1` | Có | Địa chỉ dòng 1 |
| `shipping_address2` | Không | Địa chỉ dòng 2 |
| `shipping_city` | Có | Thành phố |
| `shipping_state` | US required | State/province |
| `shipping_zip` | Có | Zip/postal code |
| `shipping_country` | Có | Mã quốc gia ISO3166 |
| `shipping_email` | Không | Email |
| `shipping_phone` | Không | Số điện thoại |

Các field order:

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `reference_order_id` | Có | Mã order bên mình |
| `production_service` | Không | Chỉ hỗ trợ `Priority` nếu áp dụng |
| `shipping_method` | Không | `economy`, `standard`, `express`, `priority express` |
| `additional_service` | Không | Ví dụ `ProActive Tracking` nếu áp dụng |
| `callback_url` | Không | Webhook callback URL |
| `sandbox` | Có | Tạo order sandbox hay real |
| `fulfillment_partner` | Không | Tên platform của mình |

Field trong `items` khi tạo order bằng catalog SKU:

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `catalog_sku` | Có | SKU từ catalog |
| `design_url_front` | Có/không tùy print area | URL design mặt trước |
| `mockup_url_front` | Không | URL mockup mặt trước |
| `design_url_back` | Có/không tùy print area | URL design mặt sau |
| `mockup_url_back` | Không | URL mockup mặt sau |
| `design_right_sleeve` | Có/không tùy product | URL design tay phải |
| `design_left_sleeve` | Có/không tùy product | URL design tay trái |
| `reference_item_id` | Không | Mã item bên mình |
| `quantity` | Có | Số lượng |

Field trong `items` khi tạo order bằng product/variant:

| Field | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `product_id` | Có | Product ID |
| `variant_id` | Có | Variant ID |
| `quantity` | Có | Số lượng |

Response:

| Field | Ý nghĩa |
|---|---|
| `is_success` | Tạo order thành công hay không |
| `message` | Thông báo |
| `order_id` | Mã order mới |
| `errors` | Danh sách lỗi nếu có |

Trạng thái trong dự án:

```text
Đã có hàm create_order.
Hiện đang gửi sandbox=true trong payload.
Cần bổ sung design_url nếu muốn tạo order thật đúng chuẩn POD.
```

## 8. Webhook

BurgerPrints sẽ POST về `callback_url` nếu mình cấu hình khi tạo order.

Method:

```text
POST <callback_url>
```

Content-Type:

```text
application/json
```

Field callback tracking:

| Field | Ý nghĩa |
|---|---|
| `order_id` | Mã order BurgerPrints |
| `reference_order_id` | Mã order bên mình |
| `carrier` | Hãng vận chuyển |
| `code` | Mã tracking |
| `url` | URL tracking |

Trạng thái trong dự án:

```text
Chưa triển khai webhook receiver.
```

## 9. Balance

Trong tài liệu BurgerPrints có mục Balance, nhưng endpoint chi tiết chưa được xác nhận trong phần dữ liệu đã đọc.

Trạng thái trong dự án:

```text
Chưa triển khai.
Cần kiểm tra lại docs hoặc hỏi BurgerPrints support để xác nhận endpoint chính xác.
```

## 10. Dữ Liệu Chưa Có Endpoint Public Rõ Ràng

Các loại dữ liệu sau chưa thấy endpoint public rõ ràng trong BurgerPrints API docs:

| Dữ liệu | Trạng thái |
|---|---|
| Shipping cost estimate trước khi tạo order | Chưa thấy endpoint public |
| Shipping time estimate | Chưa thấy endpoint public |
| Production time estimate | Chưa thấy endpoint public |
| Provider/factory realtime status | Chưa thấy endpoint public |
| Region support matrix theo SKU | Chưa thấy endpoint public |
| Shipping method khả dụng theo destination trước khi order | Chưa thấy endpoint public |

## 11. Trạng Thái Lưu Trong DuckDB Hiện Tại

Đã lưu:

```text
products
skus
providers
```

Chưa lưu:

```text
orders
order_items
trackings
out_of_stock
auth_check
balance
webhook_events
```

## 12. Gợi Ý Bổ Sung Tiếp Theo

Nên bổ sung theo thứ tự:

1. `GET /v2/product/outofstock` để tránh recommend SKU hết hàng.
2. `GET /v2/authenticated` để health check API key.
3. `GET /v2/order` và `GET /v2/order/{id}` để lưu order history, shipping_fee thực tế và tracking.
4. Webhook receiver để nhận tracking update tự động.
5. Xác minh endpoint Balance nếu cần hiển thị số dư/tình trạng billing.
