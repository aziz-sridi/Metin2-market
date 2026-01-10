# Metin2 Market Data Warehouse (Constellation + ETL + Dashboard)

This project ingests Metin2 market listings from an external source (Metin2Alerts), loads them into a PostgreSQL data warehouse, and serves analytics to a React dashboard through a FastAPI backend.

Key folders:
- Backend/API: [api/main.py](api/main.py), routes in [api/routes](api/routes)
- ETL: [etl/pipeline.py](etl/pipeline.py), [etl/extractor.py](etl/extractor.py), [etl/transformer.py](etl/transformer.py), [etl/loader.py](etl/loader.py)
- Warehouse schema: [sql/constellation_schema.sql](sql/constellation_schema.sql)
- External sync: [sync/static_data_sync.py](sync/static_data_sync.py), [sync/auto_sync.py](sync/auto_sync.py)
- Frontend: [web](web)

---

## 1) Why a “constellation” schema?

A **constellation schema** (also called a *fact constellation* or *galaxy schema*) is a design with **multiple fact tables** that share **conformed dimensions**.

In this project, there are different “business processes” you want to analyze:
- Market listings/transactions
- Item attributes/bonuses (equipment analysis)
- Undervalued-opportunity detection
- (Planned/optional) weapon/armor/pet analysis and pre-aggregations

Each process has different measures and grain, so forcing everything into one fact table would:
- create lots of NULL columns,
- mix different grains (bad),
- make queries harder and slower,
- reduce flexibility.

So the constellation is the natural fit: **multiple facts, shared dimensions**.

---

## 2) Constellation schema overview (dimensions + facts)

### Dimension tables (what they mean)
Defined in [sql/constellation_schema.sql](sql/constellation_schema.sql):

- **dim_item**: conformed “Item” dimension (vnum, name, type/subtype, icon, tradeable/stackable).
- **dim_time**: conformed “Date” dimension (full_date, year, month, week, etc).
- **dim_transaction_type**: type of market event (e.g., LISTING).
- **dim_price_category**: optional bucketing of prices (ranges / currency).
- **dim_pet**: pet entity (for pet analysis).
- **dim_item_properties**: snowflaked properties of an item (weapon stats, armor stats, bonus stats). References dim_item.
- **dim_item_requirements**: snowflaked item requirements (level/job/etc). References dim_item.
- **dim_item_category**, **dim_job_class**: reference dimensions for categorization / class restrictions.

### Fact tables and which dimensions they use

**Fact table → Dimensions table (key)** is how you answer: “what dims does each fact have?”

| Fact table | Grain (what 1 row means) | Dimension keys (foreign keys) |
|---|---|---|
| `fact_market_transaction` | One listing/transaction event at a given sync timestamp | `dim_item (item_key)`, `dim_time (time_key)`, `dim_transaction_type (transaction_type_key)`, optional `dim_price_category (price_category_key)` |
| `fact_price_history` | One item per day (pre-aggregated metrics) | `dim_item (item_key)`, `dim_time (time_key)` |
| `fact_item_attributes` | One listing’s attribute snapshot at a given timestamp | `dim_item (item_key)`, `dim_time (time_key)` |
| `fact_undervalued_items` | One undervalued detection event (per item & day) | `dim_item (item_key)`, `dim_time (time_key)` |
| `fact_weapon_analysis` | One weapon analysis record (per weapon & day) | `dim_item (item_key)`, `dim_time (time_key)` |
| `fact_armor_analysis` | One armor analysis record (per armor & day) | `dim_item (item_key)`, `dim_time (time_key)` |
| `fact_pet_analysis` | One pet analysis record (per pet & day) | `dim_pet (pet_key)`, `dim_time (time_key)` |

### Which dimensions are common (conformed dimensions)?
These are the dimensions shared across facts (this is the “constellation” part):

- **Common across almost all item-related facts**:  
  - `dim_item` (the same surrogate key system, same meaning)
  - `dim_time` (same calendar logic)

- **Only used by some facts**:
  - `dim_transaction_type` and `dim_price_category`: mainly for `fact_market_transaction`
  - `dim_pet`: only for `fact_pet_analysis`

This is what lets you join facts consistently:
- “How do undervalued deals change over time?” → join `fact_undervalued_items` to `dim_time`
- “What is the relationship between bonuses and price?” → join `fact_item_attributes` and `fact_market_transaction` through shared item+time (+ timestamp alignment)

---

## 3) ETL process (steps, where/how/why)

The ETL is orchestrated by [etl/pipeline.py](etl/pipeline.py) and usually triggered by the external sync loop in [sync/auto_sync.py](sync/auto_sync.py) (and that sync loop is started by FastAPI on startup in [api/main.py](api/main.py)).

### Step 0 — Static reference sync (English-only)
Where: [sync/static_data_sync.py](sync/static_data_sync.py)  
Why: Metin2 market listings contain numeric codes (vnum, stat IDs, etc). To label them, you sync static maps:
- item names
- stat map
- proto maps
- icons

Output goes under:
- `data/external/m2_data/...`

### Step 1 — Extract (fetch + clean + parse)
**1A) Fetch market JSON**
Where: [sync/auto_sync.py](sync/auto_sync.py)  
How:
- downloads `https://metin2alerts.com/store/public/data/{server_id}.json`
- computes SHA-256 hash of the payload
- runs ETL only if the hash changed (so you don’t reload identical data)
- writes a per-server sync-state file (e.g. `sync_state_502.json`)

Why:
- saves time & DB writes,
- avoids duplicate batches,
- makes the pipeline robust for periodic polling.

**1B) Clean with Pandas (required cleaning step)**
Where: [etl/cleaning.py](etl/cleaning.py)  
How:
- loads raw array into a Pandas DataFrame
- normalizes numeric fields (won/yang, enhancement)
- ensures valid vnum rows
- (optionally) dedupes by listing `id` if present

Why Pandas:
- fast normalization/coercion,
- easy missing-column handling,
- consistent data typing before modeling.

**1C) Parse into Python domain models**
Where: [etl/extractor.py](etl/extractor.py), models in [models/market_models.py](models/market_models.py)  
How:
- converts each listing dict into a `MarketItem`
- extracts:
  - base item info (vnum/name/type/subtype)
  - listing context (seller/job/category/quantity)
  - attributes (`attrs`, `rand`)
  - sockets, enhancement level
  - elemental attributes
  - pricing fields

Why:
- after parsing, transformations become deterministic and testable (you’re not manipulating raw JSON everywhere).

### Step 2 — Transform (business logic → dimensional + fact records)
Where: [etl/transformer.py](etl/transformer.py) and [etl/pipeline.py](etl/pipeline.py)

Main outputs produced in `ETLPipeline.transform()`:
- Item dimension rows (`dim_item`)
- Item properties rows (`dim_item_properties`)
- Time dimension rows (`dim_time`) for “today”
- Fact rows:
  - `fact_market_transaction`
  - `fact_item_attributes`
  - undervalued detections → `fact_undervalued_items`

Key “why” decisions:
- A **single batch timestamp** is used for the whole load so that listing rows across facts can be joined later (see how `transaction_timestamp` and `recorded_timestamp` are used).
- `detect_undervalued_item()` uses estimated fair value (`item.estimate_market_value()`) vs current listing price.

### Step 3 — Load (warehouse insert with PyGramETL)
Where: [etl/loader.py](etl/loader.py)  
This is where you used **PyGramETL** (your “pygram” requirement).

How PyGramETL is used:
- `ConnectionWrapper` wraps the psycopg2 connection.
- `CachedDimension` is used for dimensions:
  - `dim_item` (lookup on `item_vnum`)
  - `dim_time` (lookup on `full_date`)
  - `dim_transaction_type` (lookup on `transaction_type`)
- `FactTable` is used for facts:
  - `fact_market_transaction`
  - `fact_item_attributes`
  - `fact_undervalued_items`

Why PyGramETL:
- automatically handles **surrogate key lookup/ensure** for dimensions,
- caches dimension lookups (faster bulk loads),
- keeps “dimension logic” cleaner than writing manual upserts everywhere.

Note: `dim_item_properties` is loaded with explicit SQL upsert logic (because it has a uniqueness rule on `(item_key, property_type, stat_id)` and is not modeled as a simple dimension in PyGramETL).

---

## 4) How plots/visuals are generated and sent to the frontend

You have **two** visualization paths in the backend, and the React frontend uses **client-side Plotly**.

### A) React Plotly charts (JSON API → Plotly.js in browser)
Frontend dependencies in [web/package.json](web/package.json):
- `plotly.js-dist-min`
- `react-plotly.js`

Flow:
1. React page calls an API function in [web/src/lib/api.js](web/src/lib/api.js)
2. FastAPI returns JSON (arrays of dates/prices/rows)
3. React builds Plotly traces and renders charts locally

Examples:
- Price history chart:
  - Frontend: [web/src/pages/PriceHistoryPage.jsx](web/src/pages/PriceHistoryPage.jsx)
  - Endpoint: `GET /api/dashboard/non-equipment/history`
  - Backend implementation: [api/routes/dashboard.py](api/routes/dashboard.py)
  - Returned JSON looks like:
    - `series[]` with `dates[]`, `min_price_yang[]`, `avg_price_yang[]`, etc.
  - React turns those arrays into Plotly `scatter` traces.

- Equipment bonus impact chart:
  - Frontend: [web/src/pages/EquipmentAnalysisPage.jsx](web/src/pages/EquipmentAnalysisPage.jsx)
  - Endpoint: `GET /api/dashboard/equipment/bonus-impact`
  - Backend computes bonus impact (median with/without bonus) and returns rows.
  - React renders a Plotly `bar` chart with premiums.

Why this approach:
- Backend sends **data**, not pixels.
- Frontend controls styling (dark mode, hover formats, responsiveness).

### B) Server-rendered Plotly (Plotly HTML embedded into a Jinja template)
Where: [api/routes/dashboard.py](api/routes/dashboard.py)  
Endpoint:
- `GET /dashboard` returns an HTML page.
- Plotly figures are converted using `fig.to_html(...)` and inserted into a Jinja template.

This is useful for a “Python-only” dashboard demo without relying on the React app.

### C) Matplotlib → Base64 PNG (image-in-JSON)
Where: [api/routes/analytics.py](api/routes/analytics.py)  
Endpoint:
- `GET /api/analytics/dashboard-chart/{item_vnum}` returns:
  - `chart_data: "data:image/png;base64,...."`

This is a classic API style if you want to render images directly (e.g. `<img src="...">`).
In the current React UI, you mostly use Plotly JSON-driven charts instead.

---

## 5) Running the project (local)

### Backend (FastAPI)
1) Install Python deps:
- `pip install -r requirements.txt`

2) Create Postgres DB and apply schema:
- Run [sql/constellation_schema.sql](sql/constellation_schema.sql) in your PostgreSQL instance.

3) Configure env vars (examples):
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Optional:
  - `EXTERNAL_SERVER_IDS="502,71"`
  - `EXTERNAL_STATIC_OUTPUT_DIR="./data/external"`
  - `EXTERNAL_SYNC_MIN_MINUTES`, `EXTERNAL_SYNC_MAX_MINUTES`

4) Start API:
- `python api/main.py`
- Docs: `http://localhost:8000/docs`

On startup the API:
- syncs static reference files once,
- starts a background loop to fetch market JSON and run ETL when data changes.

### Frontend (React + Vite)
From [web](web):
- `npm install`
- `npm run dev`

The frontend expects the FastAPI server on the same origin (or proxied) because it calls paths like `/api/dashboard/...`.

---

## 6) “What should I say in my report / defense?” (quick narrative)

- I chose a constellation schema because I have multiple fact tables representing different analyses (transactions, attributes, undervalued detections, etc.) that share conformed dimensions (`dim_item`, `dim_time`).
- My ETL is automated:
  - static reference sync provides English labels,
  - market sync fetches and hashes payloads to detect change,
  - ETL parses listings into models and loads the warehouse.
- I used Pandas explicitly for the cleaning/normalization step.
- I used PyGramETL for dimensional loading and surrogate key management (fast, reliable dimension ensure + fact insert).
- For visualization:
  - backend returns JSON series and stats,
  - frontend renders interactive Plotly charts (better UX),
  - I also implemented alternative plotting approaches (server Plotly HTML, Matplotlib base64) as backend-driven visualization options.