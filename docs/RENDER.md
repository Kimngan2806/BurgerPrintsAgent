# Deploy demo miễn phí trên Render

Ứng dụng được đóng gói thành **một Docker Web Service**: nginx nhận cổng `$PORT`, chuyển `/api/*` và `/health` tới FastAPI, phần giao diện tới Next.js standalone. Dùng cùng origin để cookie đăng nhập và ảnh preview hoạt động qua HTTPS; proxy API tắt buffering cho SSE.

## Cấu hình dịch vụ

| Trường | Giá trị |
|---|---|
| Repository / branch | `Kimngan2806/BurgerPrintsAgent` / `main` |
| Language | Docker |
| Root Directory | để trống |
| Dockerfile Path | `./Dockerfile` |
| Docker Build Context Directory | `.` |
| Region | Singapore |
| Compute | Free, $0/tháng |
| Health Check Path | `/health` |
| Docker Command | để trống, dùng CMD trong Dockerfile |

Có thể dùng file `render.yaml` tại thư mục gốc để tạo cùng cấu hình bằng Blueprint. Không chứa API key; deploy giao diện trước được.

## Biến môi trường

```dotenv
PRIMARY_MODEL_PROVIDER=gemini
COOKIE_SECURE=true
STORE_DISPLAY_NAME=BurgerPrints Demo
WORKSPACE_DATABASE_URL=postgresql://...
WORKSPACE_DB_PATH=/app/data/workspace.sqlite3
DUCKDB_PATH=/app/data/catalog.duckdb
FILE_STORAGE_PATH=/app/data/designs
BUILD_SEARCH_INDEX_ON_STARTUP=false
CACHE_SYNC_ON_STARTUP=true
CATALOG_SYNC_INTERVAL_SECONDS=21600
ORDER_SANDBOX=true
ENABLE_ORDER_SUBMISSION=false
```

`deploy/start.py` tự lấy `RENDER_EXTERNAL_URL` để đặt `PUBLIC_FILE_BASE_URL` và CORS nếu chưa đặt riêng. Khi dùng custom domain, cấu hình hai giá trị này thành URL HTTPS của domain đó.

Để giữ tài khoản và lịch sử chat qua các lần khởi động lại, tạo PostgreSQL (chẳng hạn [Neon Free](https://neon.com/docs/guides/render)) rồi đặt URL kết nối đầy đủ, gồm `sslmode=require`, vào `WORKSPACE_DATABASE_URL` trong **Environment** của dịch vụ Render. Khi đã cấu hình URL, ứng dụng tạo bảng trong PostgreSQL lúc khởi động và lưu tài khoản, phiên đăng nhập, hội thoại và đơn nháp ở đó. Với URL trống, ứng dụng dùng SQLite tại `WORKSPACE_DB_PATH`. Chuỗi kết nối chứa mật khẩu và chỉ nên lưu trong biến môi trường.

Không cần nhập API key để build, mở giao diện, đăng ký tài khoản ứng dụng, lưu đơn nháp trống và dùng công cụ tính kịch bản. Phần trả lời AI cần key của model; catalog BurgerPrints cần key của store. Thêm key sau tại **Environment → Add Environment Variable**, lưu và redeploy:

- `GEMINI_API_KEY`: lấy từ [Google AI Studio](https://aistudio.google.com/api-keys).
- `BURGERPRINTS_API_KEY`: lấy trong phần Preferences/settings của fulfillment store BurgerPrints; xem [tài liệu chính thức](https://api-docs.burgerprints.com/).

Nếu dùng BytePlus: đặt `PRIMARY_MODEL_PROVIDER=byteplus`, `SEEDANCE_API_KEY` và model/URL phù hợp thay cho key Gemini. Nếu dùng Vertex: cấu hình project/location và service account theo quy trình của Google, không commit file credential.

Để chuyển sang OpenRouter miễn phí, đặt `PRIMARY_MODEL_PROVIDER=openrouter` và thêm `OPENROUTER_API_KEY` từ [OpenRouter](https://openrouter.ai/keys). Mặc định dùng `cohere/north-mini-code:free`, có hỗ trợ gọi công cụ. Nếu Render đã có `OPENROUTER_MODEL`, cập nhật biến này để chọn model mới. `BURGERPRINTS_API_KEY` dùng để đồng bộ catalog và kết nối đơn hàng.

Để bật Gemini Flash Lite tính phí qua OpenRouter, đặt `PRIMARY_MODEL_PROVIDER=openrouter` và `OPENROUTER_MODEL=google/gemini-3.1-flash-lite` trong **Environment**. Tài khoản OpenRouter cần có credit. Tạo key cho chatbot, đặt trần chi tiêu và nhập key vào `OPENROUTER_API_KEY` trên Render. Chọn **Save and deploy** sau khi bản hỗ trợ Flash Lite đã lên Live. [API key OpenRouter](https://openrouter.ai/keys) · [Biến môi trường trên Render](https://render.com/docs/configure-environment-variables)

Để thử gửi đơn từ chat trên Render, đặt `ORDER_SANDBOX=true` và `ENABLE_ORDER_SUBMISSION=true`. Khi xem xong bản duyệt trong chat, nhắn `XÁC NHẬN ĐƠN HÀNG` để gửi phiên bản đã duyệt. Nhắn `XEM BẢN DUYỆT` nếu đã sửa đơn hoặc bản duyệt hết hạn.

## Giới hạn đã chọn cho demo Free

Theo [Render Free](https://render.com/docs/free), dịch vụ có thể ngủ sau 15 phút không hoạt động và mất thay đổi trên ổ đĩa khi khởi động lại. Khi có `WORKSPACE_DATABASE_URL` và key BurgerPrints, ứng dụng lưu bản catalog gần nhất đã đồng bộ thành công vào PostgreSQL. Nếu DuckDB trống lúc khởi động, ứng dụng nạp bản đó với thời điểm đồng bộ gốc rồi làm mới theo lịch. Lần đầu cần đồng bộ đầy đủ để tạo bản lưu. File thiết kế đã tải lên vẫn nằm trên ổ đĩa. Dữ liệu đã bị Render xóa trước khi kết nối PostgreSQL cần bản sao lưu để khôi phục.

Bản Render dùng `requirements-runtime.txt`, không nạp Torch/SentenceTransformer/FAISS; tìm kiếm sử dụng DuckDB. Khi muốn dùng vector index, cần image chứa bộ requirements đầy đủ và dung lượng RAM phù hợp.

## Kiểm tra sau deploy

1. `/health` trả HTTP 200, `release` cho biết commit đang chạy trên Render, và `workspace_storage` là `postgresql` nếu đã đặt URL.
2. Trang gốc hiển thị đăng nhập/đăng ký.
3. Đăng ký tài khoản thử, mở trang làm việc và tạo đơn nháp.
4. Có API key: kiểm tra `catalog_ready` sau khi đồng bộ nền. `catalog_snapshot_status` là `stored` khi PostgreSQL đã nhận bản lưu và `restored` khi DuckDB được nạp lại từ bản lưu đó.
5. Khởi động lại dịch vụ, đăng nhập với cùng tài khoản thử và mở lại hội thoại từ lịch sử.
6. Giữ `ENABLE_ORDER_SUBMISSION=false` cho demo giao diện. Để thử giao dịch, dùng PostgreSQL và nghiệm thu luồng sandbox trước.

Không có Docker daemon trong môi trường Windows chuẩn bị repo này. Build frontend, kiểm thử backend và kiểm tra file cấu hình được chạy tại máy; việc build/run Linux Docker được xác nhận qua lần deploy Render thực tế.
