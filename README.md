# 🔩 Amazon Price Monitoring System

> **Production-grade e-commerce price monitoring for Amazon India**  
> Nisargasoft Hackathon 2026 · Track: Data Engineering / Web Scraping / Market Intelligence

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Amazon Price Monitoring System                        │
│                                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────┐    │
│  │  Scrapy +   │───▶│  6-Stage     │───▶│   PostgreSQL (v15+)     │    │
│  │  Playwright │    │  Pipeline    │    │  • products             │    │
│  │  Spiders    │    │  (validate → │    │  • sellers              │    │
│  └─────┬───────┘    │   normalise →│    │  • listings             │    │
│        │            │   DB write → │    │  • price_history        │    │
│  ┌─────▼───────┐    │   alert)     │    │  • buy_box_history      │    │
│  │  ProxyPool  │    └──────┬───────┘    │  • alert_rules / alerts │    │
│  │  Fingerprint│           │            │  • scrape_jobs          │    │
│  │  Middleware │    ┌──────▼───────┐    │  • Analytics Views      │    │
│  └─────────────┘    │  FastAPI     │    └──────────────────────────┘   │
│                     │  REST + WS   │◀──────────────────┘               │
│  ┌─────────────┐    │  25+ routes  │                                   │
│  │ APScheduler │    └──────┬───────┘    ┌─────────────────────────┐    │
│  │  4 jobs     │           │            │   Next.js Dashboard     │    │
│  │  • crawl    │    ┌──────▼───────┐    │   (Port 3000)           │    │
│  │  • refresh  │    │  Analytics   │    │   7 pages, dark theme   │    │
│  │  • alerts   │    │  Service     │    │   WebSocket live feed   │    │
│  │  • mv sync  │    └──────────────┘    └─────────────────────────┘    │
│  └─────────────┘                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Structure

```
amazon-price-monitor/
│
├── amazon_monitor/                  # Scrapy project
│   ├── spiders/
│   │   ├── product_spider.py        # Targeted ASIN detail + offers spider
│   │   └── search_spider.py         # Search-result crawl spider
│   ├── items.py                     # ProductSnapshotItem (30+ fields)
│   ├── middlewares.py               # Proxy rotation, UA, delay, retry
│   ├── pipelines.py                 # 6-stage pipeline (validate→alert)
│   ├── settings.py                  # Scrapy + Playwright settings
│   └── utils/
│       ├── proxies.py               # Weighted proxy pool (health scoring)
│       ├── fingerprint.py           # Stealth JS, mouse, scroll helpers
│       └── html_store.py            # gzip raw HTML persistence
│
├── api/
│   ├── fastapi_app.py               # 25+ REST routes + WebSocket
│   ├── models.py                    # Pydantic request/response schemas
│   ├── auth.py                      # JWT authentication
│   ├── cache.py                     # Redis response caching
│   └── logging_cfg.py               # Structured JSON logging
│
├── analytics/
│   └── price_analysis.py            # AnalyticsService (OHLC, drops, etc.)
│
├── config/
│   └── settings.py                  # Pydantic-settings env config
│
├── database/
│   ├── schema.sql                   # Complete PostgreSQL DDL (9 tables,
│   │                                #   5 views, 2 materialized views,
│   │                                #   30+ indexes, 3 stored functions)
│   ├── models.py                    # SQLAlchemy ORM (9 mapped classes)
│   ├── connection.py                # Engine, session factory, MV refresh
│   ├── repository.py                # All DB read/write operations
│   └── seed.py                      # 30-day rich demo data generator
│
├── monitoring/
│   └── alerts.py                    # AlertEngine + email/Slack/webhook
│
├── scheduler/
│   └── scheduler.py                 # APScheduler: 4 jobs
│
├── frontend/                        # Next.js 16 dashboard
│   ├── app/                         # 7 pages (App Router)
│   └── lib/api.ts                   # Type-safe API client
│
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## 🗄️ Database Schema (PostgreSQL)

### Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `products` | Product catalogue | `asin` (UNIQUE), `title`, `brand`, `category` |
| `sellers` | Seller registry | `seller_id` (UNIQUE), `name`, `fulfillment_type` |
| `locations` | Geo dimension | `pincode`, `city`, `state` |
| `listings` | Live offer snapshot per seller | `asin`, `seller_id`, `price`, `mrp`, `is_buybox`, `timestamp` |
| `price_history` | Immutable time-series | `asin`, `seller_id`, `price`, `source`, `timestamp` |
| `buy_box_history` | Buy-box ownership log | `asin`, `seller_id`, `price`, `captured_at` |
| `alert_rules` | User-defined thresholds | `asin`, `condition` (JSONB), `severity` |
| `alerts` | Triggered alert events | `rule_id`, `old_value`, `new_value`, `triggered_at` |
| `scrape_jobs` | Scrape audit log | `asin`, `status`, `attempts`, `duration_ms` |

### Analytics Views (PostgreSQL)

| View | Description |
|---|---|
| `vw_latest_price` | Latest buy-box price per ASIN |
| `vw_daily_price_ohlc` | Open / High / Low / Close bars (daily) |
| `vw_buybox_current` | Current buy-box winner per product |
| `vw_price_drops` | Consecutive price-drop events (> 5%) |
| `vw_seller_competitiveness` | Win-rate + avg price per seller × ASIN |
| `mvw_category_price_summary` | **Materialized** — category-level summary |

### Index strategy

```
products     → asin (unique), category, title (GIN trigram)
sellers      → seller_id (unique), name (GIN trigram)
listings     → (asin, timestamp DESC), (asin, is_buybox, ts), (asin, price)
price_history→ (asin, timestamp DESC), (seller_id, asin, ts), timestamp
buy_box_hist → (asin, captured_at DESC), (seller_id, asin, ts)
alerts       → (asin, ts), severity, unacknowledged (partial)
scrape_jobs  → (asin, ts), status, failed (partial)
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ · Node.js 20+ · PostgreSQL 15+ (or SQLite for dev)

### 1 — Set up Python environment

```bash
cd amazon-price-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2 — Configure environment

```bash
cp .env.example .env
# Set DATABASE_URL, PROXY_POOL, alert emails, etc.
```

### 3 — Initialise the database

```bash
# PostgreSQL (runs schema.sql automatically on first start)
export DATABASE_URL="postgresql://user:pass@localhost:5432/price_monitor"

# Or SQLite for local dev (no setup needed)
export DATABASE_URL="sqlite:///amazon_monitor.db"

# Seed 30 days of realistic demo data
python -m database.seed --force
```

### 4 — Start the API

```bash
uvicorn api.fastapi_app:app --host 0.0.0.0 --port 8000 --reload
# Docs: http://localhost:8000/docs
```

### 5 — Start the dashboard

```bash
cd frontend && npm install && npm run dev
# Dashboard: http://localhost:3000
```

### 6 — Run the scheduler

```bash
python -m scheduler.scheduler \
  --interval-minutes 30 \
  --product-refresh-minutes 15 \
  --refresh-minutes 60
```

---

## 🐳 Docker Compose (Full Stack)

```bash
docker compose up -d

# Seed demo data
docker compose exec api python -m database.seed

# Tail logs
docker compose logs -f api scheduler
```

| Service    | URL                          |
|------------|------------------------------|
| Dashboard  | http://localhost:3000        |
| API        | http://localhost:8000        |
| API Docs   | http://localhost:8000/docs   |
| Streamlit  | http://localhost:8501        |
| PostgreSQL | localhost:5432               |
| Redis      | localhost:6379               |

---

## 🕷️ Web Scraping

### Spiders

| Spider | Command | Purpose |
|---|---|---|
| `amazon_search` | `scrapy crawl amazon_search` | Category / keyword crawl |
| `product_detail` | `scrapy crawl product_detail -a asins=B0SKF6205` | Targeted ASIN refresh |

### Pipeline stages

```
100 ValidationPipeline      Drop items without ASIN
200 RawHtmlPipeline         Save gzip HTML to raw_html/<spider>/<asin>_<ts>.html.gz
250 JsonExportPipeline      Append JSONL line to output/products_<date>.jsonl
300 NormalisationPipeline   Parse prices, synthesise seller_id, alias is_buybox
400 AmazonMonitoringPipeline Write snapshot to PostgreSQL, log scrape_job row
500 AlertEvaluationPipeline Fire alert rules matching this ASIN (with cooldown)
```

### Anti-bot techniques

| Technique | Implementation |
|---|---|
| Stealth fingerprinting | `apply_stealth()` — removes `navigator.webdriver`, spoofs plugins/languages |
| Human-like interaction | `human_mouse_movement()`, `random_scroll()` |
| Proxy rotation | `ProxyPool` — weighted scoring, exponential back-off cooldown |
| User-agent rotation | `RandomUserAgentMiddleware` — 50+ real UA strings |
| Randomised delays | `HumanDelayMiddleware` + Scrapy `AUTOTHROTTLE` |
| Exponential retry | `ExponentialBackoffRetryMiddleware` — 5 attempts, jitter |
| Random viewports | `random_viewport()` — 5 realistic resolutions |
| Geo-simulation | Playwright context `timezone_id + geolocation + locale` |

---

## 📡 REST API Reference

### Products

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/products` | List products (filter by ASIN/title, active_only) |
| `GET` | `/product/{asin}` | Detail + latest price + buy-box info |

### Prices

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/price-history/{asin}` | Chronological rows (days/seller_id/location filters) |
| `GET` | `/price-history` | Recent rows across all ASINs |
| `GET` | `/price-history/ohlc/{asin}` | Daily/weekly OHLC candlestick bars |

### Sellers

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/sellers` | Full seller registry |
| `GET` | `/sellers/ranking` | Buy-box win rate + market share ranking |
| `GET` | `/sellers/competitiveness/{asin}` | Win-rate, avg price, high/low per seller |

### Listings & Buy Box

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/listings/{asin}` | Latest offer per seller (cheapest first) |
| `GET` | `/market/snapshot` | Cross-product latest market snapshot |
| `GET` | `/buy-box-history/{asin}` | Buy-box ownership event log |
| `GET` | `/buy-box/current` | Current winner per ASIN |
| `GET` | `/buy-box/ownership` | Ownership % per seller (× ASIN) |

### Alert Rules & Alerts

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/alert-rules` | List active rules (filter by ASIN) |
| `POST` | `/alert-rules` | Create / update rule (JSONB condition) |
| `DELETE` | `/alert-rules/{id}` | Deactivate rule |
| `GET` | `/alerts` | Fired alerts (filter unacknowledged) |
| `POST` | `/alerts/{id}/acknowledge` | Mark alert seen |

### Analytics

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/analytics/summary` | Full KPI dashboard payload |
| `GET` | `/analytics/price-trends/{asin}` | Daily avg price per seller |
| `GET` | `/analytics/price-drops` | Price drop events ≥ threshold % |
| `GET` | `/analytics/undercutting` | Sellers undercutting the market |
| `GET` | `/analytics/heatmap` | Seller × location min-price matrix |
| `GET` | `/analytics/buy-box-ownership` | Ownership % per seller |
| `POST`| `/analytics/evaluate-alerts` | Manual alert evaluation trigger |
| `WS`  | `/ws/alerts` | Real-time alert feed (30-second heartbeat) |

---

## 🔔 Alert System

### Condition types (stored as JSONB)

```jsonc
// Price drops ≥ N%  vs previous reading
{"type": "price_drop", "threshold_pct": 10}

// Price crosses fixed threshold
{"type": "price_above",  "value": 999.00}
{"type": "price_below",  "value": 250.00}

// An ASIN goes out of stock for N consecutive checks
{"type": "oos", "consecutive_checks": 3}

// Buy-box changes to / from a specific seller
{"type": "buybox_change", "seller_id": "INDUSTRIAL_HUB_01"}
```

### Dispatch channels

| Channel | Config key |
|---|---|
| 📧 Email (SMTP) | `ALERT_EMAIL_*` env vars |
| 💬 Slack | `SLACK_WEBHOOK_URL` |
| 🔗 HTTP webhook | `ALERT_WEBHOOK_URL` |
| 📡 WebSocket | `/ws/alerts` (built-in) |

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///amazon_monitor.db` | DB connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis (cache + Celery) |
| `SCRAPE_QUERIES` | `SKF bearing 6205,...` | Comma-separated search terms |
| `LOCATION_PINCODES` | `600001,560001,110001` | Pincodes to geo-simulate |
| `PROXY_POOL` | _(empty)_ | Comma-separated proxy URLs |
| `PRICE_DROP_THRESHOLD_PCT` | `5` | % drop to trigger price_drop alert |
| `UNDERCUT_THRESHOLD_PCT` | `3` | % gap for undercutting detection |
| `ALERT_COOLDOWN_MINUTES` | `60` | Min minutes between duplicate alerts |
| `SEED_DEMO_DATA` | `true` | Auto-seed on API startup |

---

## 🧪 Verification Commands

```bash
# Health check
curl http://localhost:8000/health

# KPI dashboard
curl http://localhost:8000/analytics/summary | python3 -m json.tool

# Price OHLC for an ASIN
curl "http://localhost:8000/price-history/ohlc/B0SKF6205?period=D" | python3 -m json.tool

# Latest offers (cheapest first)
curl http://localhost:8000/listings/B0SKF6205 | python3 -m json.tool

# Seller ranking
curl http://localhost:8000/sellers/ranking | python3 -m json.tool

# Create an alert rule
curl -X POST http://localhost:8000/alert-rules \
  -H "Content-Type: application/json" \
  -d '{"asin":"B0SKF6205","condition":{"type":"price_drop","threshold_pct":10},"severity":"warning"}'

# Unacknowledged alerts
curl "http://localhost:8000/alerts?unacknowledged_only=true" | python3 -m json.tool

# Trigger alert evaluation manually
curl -X POST http://localhost:8000/analytics/evaluate-alerts

# Run targeted spider
scrapy crawl product_detail -a asins=B0SKF6205,B0SKF6203
```

---

## 📊 Dashboard Pages

| Page | What you see |
|---|---|
| **Overview** | KPI cards, market share pie, buy-box bar, price changers, undercutting, live market table |
| **Products** | ASIN grid with search + seller offer drawer |
| **Price Trends** | Multi-seller line chart, brush scrub, OHLC bars, KPI ribbon |
| **Sellers** | Ranked cards, performance radar, competitiveness table |
| **Buy Box** | Ownership pie, current holders, area chart, event log |
| **Analytics** | Price drops, scatter, heatmap, undercutting table |
| **Alerts** | Live WebSocket feed, severity filter, acknowledge button |

---

## ✅ Evaluation Checklist

| Criterion | Status |
|---|---|
| Scrapy + Playwright scraping | ✅ |
| Proxy rotation + weighted health scoring | ✅ |
| Stealth browser fingerprinting | ✅ |
| Exponential back-off retry | ✅ |
| ASIN / title / seller / price / buy-box / MRP extraction | ✅ |
| Normalized PostgreSQL schema (3NF, 9 tables) | ✅ |
| 30+ indexes (BTREE + GIN trigram) | ✅ |
| 5 SQL views + 1 materialized view | ✅ |
| JSONB alert conditions (flexible rule engine) | ✅ |
| Historical price time-series (append-only) | ✅ |
| Daily OHLC price bars | ✅ |
| Seller competitiveness analytics | ✅ |
| Buy-box ownership tracking | ✅ |
| Undercutting detection | ✅ |
| Price-drop detection with threshold | ✅ |
| Location-based geo-simulation | ✅ |
| Scrape-job audit log | ✅ |
| Alert rule CRUD (POST/GET/DELETE) | ✅ |
| Alert acknowledgement | ✅ |
| APScheduler (4 jobs, coalesce, CLI config) | ✅ |
| FastAPI (25+ routes + WebSocket) | ✅ |
| Pydantic v2 request/response models | ✅ |
| Next.js 16 dashboard (7 pages, dark theme) | ✅ |
| Real-time WebSocket alert feed | ✅ |
| Email + Slack + webhook dispatch | ✅ |
| Docker Compose full-stack deployment | ✅ |
| Modular architecture | ✅ |
| Structured logging + error handling | ✅ |

---

*Built for Nisargasoft Amazon Hackathon 2026 · Data Engineering Track*
