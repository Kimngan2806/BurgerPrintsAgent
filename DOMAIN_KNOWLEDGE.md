# Domain Knowledge cho BurgerPrintsAgent

Tài liệu này chứa kiến thức tham khảo về Print-on-Demand (POD), fulfillment và
kinh doanh sản phẩm in theo yêu cầu. Nội dung được thiết kế để sau này đưa vào
RAG hoặc domain knowledge tool.

Domain knowledge dùng để **giải thích, tư vấn và xếp hạng lựa chọn**. Nó không
thay thế dữ liệu catalog hoặc dữ liệu realtime từ tool.

## 1. Quy tắc sử dụng

- Không dùng tài liệu này để khẳng định giá, trạng thái SKU/provider, khả năng
  ship hoặc thời gian giao hàng hiện tại.
- Giá, availability, region support và thời gian phải được xác minh bằng tool.
- Khi kiến thức domain mâu thuẫn với dữ liệu catalog/tool, ưu tiên dữ liệu
  catalog/tool và giải thích giới hạn.
- Không suy đoán thuộc tính sản phẩm nếu catalog không cung cấp.

---

## 2. Thuật ngữ POD và Fulfillment

### Print-on-Demand

Print-on-Demand (POD) là mô hình sản xuất sau khi có đơn hàng. Seller không cần
giữ tồn kho trước.

**Ưu điểm**

- Vốn ban đầu thấp.
- Giảm rủi ro tồn kho.
- Dễ thử nghiệm nhiều thiết kế và niche.

**Hạn chế**

- Biên lợi nhuận thường thấp hơn tự sản xuất số lượng lớn.
- Phụ thuộc vào provider về chất lượng, tốc độ và tồn kho phôi.
- Khó kiểm soát trải nghiệm giao hàng hoàn toàn.

### Fulfillment

Fulfillment là toàn bộ quá trình xử lý đơn hàng:

```text
Nhận đơn -> sản xuất/in -> kiểm tra -> đóng gói -> vận chuyển
```

### Provider / Factory / Print Provider

Đơn vị thực hiện sản xuất và fulfillment. Vị trí nhà máy ảnh hưởng lớn đến:

- Base cost.
- Processing time.
- Shipping cost.
- Shipping time.
- Region support.

Provider gần thị trường đích thường giao nhanh hơn, nhưng không phải lúc nào
cũng có tổng chi phí thấp nhất.

### SKU

SKU là mã định danh một biến thể cụ thể của sản phẩm. Một SKU có thể đại diện
cho tổ hợp:

```text
Sản phẩm + màu sắc + kích thước + chất liệu + provider
```

Không được coi hai SKU khác nhau là cùng một sản phẩm có thể thay thế tự động.

### MOQ

MOQ là số lượng đặt hàng tối thiểu. POD thường hỗ trợ MOQ bằng 1, nhưng cần xác
minh theo provider hoặc sản phẩm.

---

## 3. Chi phí và chỉ số tài chính

### Base Cost

Chi phí gốc để sản xuất một sản phẩm. Base Cost thường chưa bao gồm vận chuyển
và các phụ phí.

### Shipping Cost

Chi phí vận chuyển từ provider tới người nhận. Chi phí phụ thuộc vào:

- SKU và khối lượng.
- Quốc gia hoặc khu vực nhận hàng.
- Shipping method.
- Số lượng sản phẩm.

### Fulfillment Cost

Tổng chi phí trực tiếp để fulfillment đơn:

```text
Fulfillment Cost = Base Cost + Shipping Cost + phụ phí đã biết
```

Phụ phí có thể gồm phí sản phẩm bổ sung, phí vận chuyển vùng xa hoặc các phí
dịch vụ khác.

### Gross Profit và Gross Margin

```text
Gross Profit = Selling Price - Fulfillment Cost

Gross Margin = Gross Profit / Selling Price * 100%
```

Gross Margin chưa phản ánh đầy đủ lợi nhuận cuối cùng nếu chưa tính quảng cáo,
refund, phí nền tảng, thuế và chi phí vận hành.

### ROI

ROI đo mức sinh lời trên vốn đầu tư:

```text
ROI = Net Profit / Investment Cost * 100%
```

Không nên tính hoặc khẳng định ROI nếu chưa có dữ liệu về chi phí đầu tư liên
quan.

### Conversion Rate

Tỷ lệ người mua trên tổng người truy cập:

```text
Conversion Rate = Orders / Visitors * 100%
```

### AOV

Average Order Value là giá trị trung bình mỗi đơn:

```text
AOV = Revenue / Number of Orders
```

AOV có thể tăng bằng bundle, upsell hoặc cross-sell.

---

## 4. Thời gian và vận chuyển

### Processing Time

Thời gian provider cần để sản xuất, kiểm tra và đóng gói. Processing Time không
bao gồm thời gian vận chuyển.

### Shipping Time

Thời gian kiện hàng di chuyển từ provider tới người nhận.

### Tổng thời gian dự kiến

```text
Estimated Total Time = Processing Time + Shipping Time
```

Đây vẫn chỉ là ước tính và có thể thay đổi bởi cuối tuần, ngày lễ, hải quan hoặc
sự cố vận chuyển.

### Shipping Methods

| Phương thức | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| Economy | Rẻ, chậm, dễ delay | User ưu tiên chi phí |
| Standard | Cân bằng giá và tốc độ | Phần lớn đơn thông thường |
| Express | Nhanh, chi phí cao | Quà tặng, deadline, mùa lễ |
| Worldwide | Phủ nhiều quốc gia | Cross-border, cần kiểm tra region |

### Fulfillment Delay

Chậm trễ có thể xảy ra do:

- Provider overload.
- Thiếu phôi hoặc vật liệu.
- Lỗi sản xuất.
- Vận chuyển hoặc hải quan.
- Thời tiết và ngày lễ.

### Q4 Overload

Q4 thường có lượng đơn tăng mạnh vì mùa lễ. Khi tư vấn cho Q4 nên ưu tiên:

- Provider có trạng thái ổn định.
- Processing time ngắn.
- Nhà máy gần thị trường đích.
- Khoảng đệm thời gian trước deadline.

Không được khẳng định provider đang overload nếu chưa kiểm tra realtime.

---

## 5. Công nghệ in

### DTG

Direct-to-Garment in trực tiếp lên vải.

**Phù hợp**

- Cotton hoặc sản phẩm có tỷ lệ cotton cao.
- Thiết kế nhiều màu, chi tiết hoặc gradient.
- Số lượng nhỏ theo mô hình POD.

**Điểm cần cân nhắc**

- Kết quả phụ thuộc chất liệu và xử lý vải.
- Không mặc định mọi sản phẩm cotton đều hỗ trợ DTG.

### DTF

Direct-to-Film in lên màng rồi ép nhiệt lên sản phẩm.

**Phù hợp**

- Cotton, polyester và nhiều loại blend.
- Thiết kế cần màu sắc nổi bật, đường nét rõ.
- Nhiều loại apparel.

**Điểm cần cân nhắc**

- Cảm giác bề mặt có thể khác DTG.
- Cần xác minh provider/SKU hỗ trợ.

### Sublimation

Mực chuyển nhiệt thấm vào sợi vật liệu.

**Phù hợp**

- Polyester.
- Đồ thể thao.
- Thiết kế phủ rộng hoặc all-over print.

**Không phù hợp**

- Sản phẩm không phải polyester hoặc không được provider hỗ trợ.

### Screen Printing

In lụa thường hiệu quả khi sản xuất số lượng lớn.

**Phù hợp**

- Thiết kế ít màu.
- Đơn số lượng lớn.

**Hạn chế với POD**

- Chi phí setup khiến đơn số lượng nhỏ kém hiệu quả.

### Embroidery

Thêu tạo cảm giác cao cấp và bền.

**Phù hợp**

- Logo đơn giản.
- Hat, polo hoặc apparel premium.

**Điểm cần cân nhắc**

- Chi phí cao hơn.
- Thiết kế quá chi tiết có thể không phù hợp.

### Heat Transfer

Thiết kế được ép nhiệt từ màng hoặc vật liệu trung gian. Khả năng tương thích và
độ bền phụ thuộc vật liệu, quy trình và provider.

---

## 6. Chất liệu và phom dáng

### Cotton

- Mềm và thoáng.
- Phù hợp sản phẩm mặc thường ngày.
- Thường phù hợp DTG.

### Ringspun Cotton

Sợi cotton được xử lý để mềm và mịn hơn cotton cơ bản. Thường mang cảm giác cao
cấp hơn.

### Airlume Cotton

Loại cotton được xử lý để tạo bề mặt mềm và đồng đều. Thường xuất hiện ở dòng
apparel premium.

### Pre-shrunk Cotton

Vải đã được xử lý nhằm giảm co rút sau khi giặt. Không có nghĩa là hoàn toàn
không co.

### Polyester

- Bền, chống nhăn và mau khô.
- Phù hợp đồ thể thao.
- Cần thiết cho Sublimation.

### Cotton Blend

Kết hợp cotton với polyester hoặc vật liệu khác để cân bằng độ mềm, độ bền và
khả năng giữ phom.

### Fleece

Chất liệu lót nỉ phù hợp hoodie và thời tiết lạnh. Có thể làm tăng trọng lượng
và shipping cost.

### GSM

GSM đo định lượng và độ dày tương đối của vải:

- Lightweight: nhẹ, mát, thường rẻ hơn.
- Heavyweight: dày, cảm giác cao cấp, nhưng nóng và có thể tăng chi phí ship.

Không nên dùng GSM làm tiêu chí chất lượng duy nhất.

### Phom dáng

| Phom | Đặc điểm |
|---|---|
| Unisex | Phổ biến, phù hợp nhiều nhóm khách |
| Oversized | Rộng, phong cách streetwear/Gen Z |
| Athletic Fit | Ôm hơn, phù hợp phong cách thể thao |

---

## 7. Marketplace và hành vi khách hàng

### Etsy

- Khách hàng quan tâm thiết kế độc bản, cá nhân hóa và cảm giác thủ công.
- Có khả năng chấp nhận mức giá premium hơn nếu giá trị thiết kế rõ ràng.
- Phù hợp niche cụ thể và sản phẩm làm quà.

### Amazon

- Khách hàng ưu tiên tốc độ giao hàng, sự tiện lợi và độ tin cậy.
- Sản phẩm phổ thông có mức cạnh tranh cao.
- Provider gần thị trường và shipping ổn định thường quan trọng.

### TikTok Shop

- Hành vi mua chịu ảnh hưởng mạnh bởi nội dung, cảm xúc và trend.
- Khách hàng thường nhạy cảm với giá.
- Tốc độ thử nghiệm sản phẩm và creative quan trọng.

### Shopify

- Phù hợp xây dựng thương hiệu riêng.
- Seller kiểm soát trải nghiệm, dữ liệu khách hàng và chiến lược giá tốt hơn.
- Cần tự tạo traffic và xây dựng niềm tin.

### Cross-border

Cross-border là bán hàng xuyên biên giới. Khi tư vấn cần cân nhắc:

- Vị trí provider và người nhận.
- Shipping cost/time.
- Region support.
- Hải quan và nguy cơ delay.

---

## 8. Chiến lược kinh doanh tham khảo

### Seller mới

T-shirt thường phù hợp để bắt đầu vì:

- Base cost tương đối thấp.
- Nhu cầu rộng.
- Dễ thử nghiệm niche và thiết kế.

Sau khi tìm được sản phẩm có tín hiệu tốt, seller có thể mở rộng sang hoodie
hoặc sản phẩm premium để tăng AOV và margin.

Đây là chiến lược tham khảo, không phải quy tắc bắt buộc cho mọi seller.

### Niche

Niche là nhóm khách hàng có sở thích hoặc đặc điểm cụ thể, ví dụ:

- Người nuôi thú cưng.
- Y tá.
- Game thủ.
- Người yêu thể thao.

Tập trung niche giúp thông điệp và thiết kế cụ thể hơn, nhưng niche quá nhỏ có
thể giới hạn quy mô.

### Winning Product và Scale

Winning Product là sản phẩm đã chứng minh được nhu cầu hoặc hiệu suất bán hàng.
Scale có thể gồm:

- Tăng ngân sách quảng cáo.
- Mở rộng biến thể.
- Mở rộng marketplace hoặc khu vực.
- Thêm sản phẩm liên quan.

Không nên kết luận một sản phẩm là winning chỉ dựa trên cảm nhận; cần dữ liệu
bán hàng và hiệu suất.

### Chọn vị trí provider

Khi bán cho thị trường Mỹ, US factory thường có lợi thế về shipping time và trải
nghiệm khách hàng. Tuy nhiên vẫn cần so sánh:

- Tổng fulfillment cost.
- Processing và shipping time realtime.
- Provider status.
- Chất lượng và SKU availability.

---

## 9. Quan hệ tương thích dùng để tư vấn

Các quan hệ này dùng để lọc hoặc xếp hạng, nhưng phải xác minh bằng catalog/tool:

```text
Cotton + thiết kế chi tiết        -> thường phù hợp DTG
Polyester + đồ thể thao           -> thường phù hợp Sublimation
Nhiều loại vải + màu nổi bật      -> có thể phù hợp DTF
Đơn số lượng lớn + thiết kế ít màu -> có thể phù hợp Screen Printing
Logo đơn giản + sản phẩm premium  -> có thể phù hợp Embroidery
Mùa lạnh                          -> cân nhắc Hoodie/Fleece
Thị trường Mỹ                     -> cân nhắc US provider
Deadline gần                      -> cân nhắc Express
Ưu tiên chi phí                   -> cân nhắc Economy/Standard
```

Từ “thường phù hợp” hoặc “cân nhắc” rất quan trọng: đây không phải khẳng định
SKU/provider cụ thể hỗ trợ lựa chọn đó.

---

## 10. Cảnh báo và giới hạn tư vấn

Agent nên cảnh báo khi phù hợp:

- Giá realtime hoặc phụ phí chưa được lấy đầy đủ.
- Margin chưa gồm ads, refund, phí marketplace hoặc thuế.
- Shipping time chỉ là ước tính.
- Q4 hoặc mùa lễ có nguy cơ delay.
- Cross-border có thể chịu ảnh hưởng bởi hải quan.
- Provider/SKU compatibility chưa được xác minh.
- ROI không thể kết luận khi thiếu dữ liệu đầu tư.

---

## 11. Câu hỏi domain knowledge mẫu

Các câu hỏi sau phù hợp để truy xuất từ knowledge base:

- POD khác giữ tồn kho truyền thống như thế nào?
- Base Cost và Fulfillment Cost khác nhau ra sao?
- DTG và DTF phù hợp trường hợp nào?
- Vì sao Sublimation cần polyester?
- GSM ảnh hưởng trải nghiệm sản phẩm thế nào?
- Etsy và Amazon khác nhau về hành vi khách hàng ra sao?
- Seller mới nên bắt đầu với loại sản phẩm nào?
- Vì sao Q4 dễ xảy ra fulfillment delay?
- Processing Time và Shipping Time khác nhau thế nào?
- Khi nào nên cân nhắc US factory?

Các câu hỏi sau phải gọi tool thay vì chỉ dùng knowledge base:

- SKU nào đang active?
- Giá hiện tại của SKU là bao nhiêu?
- Provider nào đang overload?
- SKU này có ship đến Việt Nam không?
- Shipping time hiện tại là bao lâu?
- Tính năng tạo đơn đang bật hay tắt?

---

## 12. Gợi ý cấu trúc khi chuyển sang RAG

Không nên lưu toàn bộ tài liệu thành một chunk. Có thể chia theo metadata:

```json
{
  "id": "printing.sublimation.compatibility",
  "category": "printing_technology",
  "topic": "sublimation",
  "content": "Sublimation phù hợp polyester và đồ thể thao...",
  "tags": ["polyester", "sportswear", "compatibility"],
  "requires_realtime_verification": true
}
```

Nhóm chunk đề xuất:

- `pod_fundamentals`
- `financial_metrics`
- `shipping`
- `printing_technology`
- `materials_and_fit`
- `marketplaces`
- `business_strategy`
- `compatibility_rules`
- `warnings_and_limitations`

Mỗi chunk nên ngắn, tập trung một chủ đề và có metadata
`requires_realtime_verification` để nhắc agent khi nào cần gọi tool.
