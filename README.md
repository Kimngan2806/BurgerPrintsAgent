# 🍔 BurgerPrintsAgent — POD Catalog Assistant

> **Từ hàng trăm xưởng đến một SKU hoàn hảo, để AI agent làm phần nặng nhọc.**

AI conversational agent giúp sellers POD trên BurgerPrints tìm kiếm, so sánh, và chọn sản phẩm fulfillment qua ngôn ngữ tự nhiên (Tiếng Việt / English).

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BurgerPrintsAgent                              │
│                                                                         │
│  ┌────────────┐    ┌──────────────────────┐    ┌──────────────────┐    │
│  │  Next.js   │◄──►│   FastAPI Backend     │◄──►│  BurgerPrints   │    │
│  │  Chat UI   │SSE │                       │    │  API v2.0       │    │
│  │ (Dark Mode)│    │ ┌──────────────────┐  │    └──────────────────┘    │
│  └────────────┘    │ │ Gemini 2.5 Flash │  │                            │
│                    │ │ Function Calling  │  │    ┌──────────────────┐    │
│                    │ └──────────────────┘  │    │  Harness         │    │
│                    │                       │◄──►│  Feature Flags   │    │
│                    │ ┌──────────────────┐  │    └──────────────────┘    │
│                    │ │ Hybrid Search    │  │                            │
│                    │ │ BM25+FAISS+RRF   │  │                            │
│                    │ └──────────────────┘  │                            │
│                    │                       │                            │
│                    │ ┌──────────────────┐  │                            │
│                    │ │ DuckDB Cache     │  │                            │
│                    │ │ + TTLCache       │  │                            │
│                    │ └──────────────────┘  │                            │
│                    └──────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Technical Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| LLM | Gemini 2.5 Flash | Fast, cheap, native function calling, VN/EN multilingual |
| Framework | Native SDK (no LangChain) | Transparent, fast, easy to debug |
| Search | BM25 + FAISS + RRF | Hybrid keyword + semantic search, cross-language |
| Cache | DuckDB + TTLCache | Columnar analytics, in-process, zero infra |
| Reasoning | Function Calling (no CoT) | Structured reasoning via tools, no hallucination |
| Feature Mgmt | Harness Feature Flags | Live toggle order creation during demo |

---

## ⚡ Quick Start (≤ 10 minutes)

### Option 1: Docker (Recommended)

```bash
# 1. Clone
git clone https://github.com/your-team/burgerprints-agent.git
cd burgerprints-agent

# 2. Configure
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# Edit .env files with your API keys

# 3. Run
docker compose up --build

# 4. Open
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs
```

### Option 2: Manual Setup

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # Edit with your keys
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BURGERPRINTS_API_KEY` | ✅ | BurgerPrints API v2.0 key |
| `BURGERPRINTS_API_BASE_URL` | ✅ | API base URL |
| `GEMINI_API_KEY` | ✅ | Google AI Studio API key |
| `HARNESS_FF_SDK_KEY` | ❌ | Harness Feature Flags SDK key |

---

## 🎯 Features

### Core
- 🔍 **Natural Language Search** — "T-shirt US dưới $8, ship 5 ngày"
- 📊 **Smart Comparison** — Compare providers with real-time pricing
- 💰 **Margin Calculator** — "Margin 40% tại $24.99, gợi ý sản phẩm"
- 🌏 **Region Awareness** — SKU A ships US but not EU
- ⚡ **Hybrid Search** — BM25 keyword + FAISS semantic + RRF fusion
- 🔄 **Real-time Data** — Prices, inventory, provider status always fresh
- 🗣️ **Bilingual** — Vietnamese + English auto-detect

### Bonus
- 📦 **Order Creation** — Create fulfillment orders via API
- 🎛️ **Feature Flags** — Toggle features live with Harness
- 📡 **Streaming** — ChatGPT-like typing effect via SSE

---

## 💬 Sample Queries

```
"Tôi muốn bán T-shirt cho thị trường Mỹ, giá vốn dưới $8, ship dưới 5 ngày"
"So sánh giá Hoodie giữa các xưởng, xưởng nào ship EU rẻ nhất?"
"Tôi định bán giá $24.99, margin tối thiểu 40%, gợi ý sản phẩm"
"What's the cheapest mug that ships to Australia?"
"OK chọn SKU đầu tiên, tạo đơn 2 cái ship đến New York"
```

---

## 🧠 How It Works

### Hybrid Data Architecture

| Data Type | Strategy | Latency |
|-----------|----------|---------|
| Product names, categories, attributes | **Cached** (DuckDB, 7-day TTL) | <5ms |
| SKU mappings, provider list | **Cached** (DuckDB, 24h TTL) | <5ms |
| Base cost, shipping cost | **Realtime** (BurgerPrints API) | ~500ms |
| Production time, shipping time | **Realtime** (BurgerPrints API) | ~500ms |
| SKU status, provider status, inventory | **Realtime** (BurgerPrints API) | ~500ms |
| Region support | **Realtime** (BurgerPrints API) | ~500ms |

### Search Pipeline

```
Query → BM25 Top-50 + FAISS Top-50 → RRF Fusion → Top-30
      → DuckDB Filter → Realtime API Enrich → Top-10 → Gemini Response
```

### Performance

| Metric | Target |
|--------|--------|
| Search layer | <39ms |
| First token (streaming) | <300ms |
| Full response | <1.5s |
| Setup time | ≤10 min |

---

## 📁 Project Structure

```
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── agent/               # Gemini agent + tools
│   ├── api/                 # BurgerPrints API client
│   ├── search/              # BM25 + FAISS + RRF
│   ├── cache/               # DuckDB + TTLCache
│   ├── core/                # Config, sessions, feature flags
│   └── routers/             # API endpoints
├── frontend/
│   ├── src/app/             # Next.js pages
│   └── src/components/      # Chat UI components
├── .harness/                # CI/CD pipeline
├── docker-compose.yml       # One-command setup
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash |
| Backend | Python FastAPI |
| Frontend | Next.js 14 (App Router) |
| Cache | DuckDB + cachetools |
| Search (Sparse) | BM25 (rank-bm25) |
| Search (Dense) | FAISS + multilingual-e5-small |
| Search (Fusion) | Reciprocal Rank Fusion |
| Feature Flags | Harness FME |
| Deployment | Docker Compose |

---

## 👥 Team

Built for BurgerPrints Hackathon 2025

---

## 📄 License

MIT
