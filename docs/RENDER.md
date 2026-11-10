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

Không cần nhập API key để build, mở giao diện, đăng ký tài khoản ứng dụng, lưu đơn nháp trống và dùng công cụ tính kịch bản. Phần trả lời AI cần key của model; catalog BurgerPrints cần key của store. Thêm key sau tại **Environment → Add Environment Variable**, lưu và redeploy:

- `GEMINI_API_KEY`: lấy từ [Google AI Studio](https://aistudio.google.com/api-keys).
- `BURGERPRINTS_API_KEY`: lấy trong phần Preferences/settings của fulfillment store BurgerPrints; xem [tài liệu chính thức](https://api-docs.burgerprints.com/).

Nếu dùng BytePlus: đặt `PRIMARY_MODEL_PROVIDER=byteplus`, `SEEDANCE_API_KEY` và model/URL phù hợp thay cho key Gemini. Nếu dùng Vertex: cấu hình project/location và service account theo quy trình của Google, không commit file credential.

Để chuyển sang OpenRouter miễn phí, đặt `PRIMARY_MODEL_PROVIDER=openrouter` và thêm `OPENROUTER_API_KEY` từ [OpenRouter](https://openrouter.ai/keys). Mặc định dùng [Gemma 4 31B (free)](https://openrouter.ai/google/gemma-4-31b-it%3Afree), có hỗ trợ gọi công cụ. Có thể đặt `OPENROUTER_MODEL` thành model khác có hậu tố `:free` và hỗ trợ gọi công cụ. Chatbot chỉ yêu cầu nhà cung cấp không thu thập dữ liệu và không chuyển sang model tính phí nếu không có endpoint phù hợp. `BURGERPRINTS_API_KEY` vẫn dùng riêng để đồng bộ catalog.

## Giới hạn đã chọn cho demo Free

Theo [Render Free](https://render.com/docs/free), dịch vụ có thể ngủ sau 15 phút không hoạt động; khi restart, redeploy hoặc ngủ, thay đổi filesystem có thể bị mất. Vì SQLite, catalog và file upload đang nằm ở filesystem, tài khoản/lịch sử/đơn nháp/file của demo có thể mất. Không bật tạo đơn thật hoặc dùng demo này làm nơi lưu giao dịch cần giữ lâu dài.

Bản Render dùng `requirements-runtime.txt`, không nạp Torch/SentenceTransformer/FAISS; tìm kiếm sử dụng DuckDB. Khi muốn dùng vector index, cần image chứa bộ requirements đầy đủ và dung lượng RAM phù hợp.

## Kiểm tra sau deploy

1. `/health` trả HTTP 200.
2. Trang gốc hiển thị đăng nhập/đăng ký.
3. Đăng ký tài khoản thử, mở trang làm việc và tạo đơn nháp.
4. Có API key: xác nhận log sync catalog thành công, thử một câu chat và kiểm tra stream.
5. Giữ `ENABLE_ORDER_SUBMISSION=false` cho demo giao diện. Để thử giao dịch, chuyển sang lưu trữ bền vững và nghiệm thu luồng sandbox trước.

Không có Docker daemon trong môi trường Windows chuẩn bị repo này. Build frontend, kiểm thử backend và kiểm tra file cấu hình được chạy tại máy; việc build/run Linux Docker được xác nhận qua lần deploy Render thực tế.
