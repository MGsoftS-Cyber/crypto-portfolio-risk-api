# Crypto Portfolio & Risk Manager API

Python 3.12 / FastAPI / Pydantic / Decimal / NumPy / scikit-learn / SQLAlchemy / Alembic. Version 1.0.0, MIT project source. Track spot holdings, buys, sells, USD fees, weighted-average cost, realized/unrealized profit, allocation, daily values, cash-flow-adjusted drawdowns and historical risk. Explain unusual changes with deterministic thresholds and optional unsupervised Isolation Forest. API-only delivery: Swagger UI is included; a custom React dashboard is a future client.

## Run locally, no paid service

```sh
cd backend
python3.12 -m venv .venv
# Windows: .venv\Scripts\activate
. .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8008
```

Open http://localhost:8008/docs. API health: /api/health. Schema: /openapi.json. Local database is backend/crypto.db, which must not be committed. All accounting and ML work locally using supplied data. No API key, private wallet key or paid server is required.

From repository root, run a synthetic end-to-end client:

```sh
# Use the backend virtual environment's Python executable
backend/.venv/bin/python scripts/demo_client.py
# Windows: backend\.venv\Scripts\python.exe scripts\demo_client.py
```

The script registers a disposable demo account with a random password, creates a synthetic portfolio, analyzes 60 days, checks all exports, saves demo-report.json and signs out. Its random credentials are not printed. Do not run it against a shared production service just to test installation; it creates synthetic account data.

## Docker alternative

Copy .env.example to .env and replace POSTGRES_PASSWORD with a long random URL-safe value. Run `docker compose up --build`, then open http://localhost:8088/docs. The API image runs non-root; PostgreSQL 17 is internal with a persistent volume. No default account. Local COOKIE_SECURE=false is for localhost HTTP. For a hosted service configure HTTPS, Secure cookies and exact origins. Docker/PostgreSQL execution remains unverified in this creation environment.

## API workflow

POST /api/auth/register (email, password), retain cookies and returned csrf_token. Send X-CSRF-Token on authenticated POSTs. Create a portfolio through /api/v1/portfolios. Preview CSV strings through /api/v1/imports/preview. Save source, coverage_end, normalized transactions and prices into /api/v1/portfolios/{id}/datasets. Analyze dataset_id/as_of through /api/v1/portfolios/{id}/analyses. Read and export the frozen result. Durable writes also require Idempotency-Key; retries retain the same key/payload.

Swagger can issue cookies from registration; copy csrf_token into the endpoint's X-CSRF-Token header parameter and set an Idempotency-Key for durable actions. The Python client handles this automatically. There is no API-key authorization field: this release uses account sessions. CLI clients can omit Origin; a supplied Origin must match ALLOWED_ORIGINS.

## Import definitions

Transactions header: `transaction_id,date,sequence,kind,asset_id,quantity,unit_price,amount,fee`.
Prices header: `date,asset_id,close`.
Kinds: deposit, withdrawal, buy, sell. USD base only. JSON money, prices and quantities must be decimal strings. Cash flows require amount >0, no asset, zero quantity and unit_price. Trades require asset_id, positive quantity/price and zero amount. All fees are USD cash. Daily external cash flows must precede trades and are modeled at beginning of the UTC day. Use stable asset IDs such as bitcoin, not ambiguous exchange tickers. Numeric sequences order same-day events.

The import starts with a full account history and initial funding. Unknown opening holdings are not guessed. An opening deposit plus buy can represent an agreed historical acquisition only when quantity/cost/date and cash reconciliation are known. Staking, swaps, native-token fees, derivatives, shorting, wallet transfers and currency conversion are outside this ledger contract.

Missing exact daily closing prices for held assets cause analysis failure; no forward-fill. A dataset may be saved with incomplete prices so the owner can keep an import version, but valuation explicitly refuses that version until a complete new version is submitted. Prices after as_of are not used. Current optional quotes never replace historical closing prices automatically.

## Optional current CoinGecko quotes

Set COINGECKO_DEMO_API_KEY in the API environment; POST /api/v1/market/quotes with asset_ids (1–20). Fixed provider host, 10-second timeout, redirect disabled, freshness metadata and safe errors. Current quotes may be stale and are not historical closes. Live access requires provider terms/quotas and was tested with mocked responses only; a live provider request was not executed here. Prices supplied by the user make the core independent of a vendor.

## Checks

```sh
cd backend
ruff format --check app tests migrations
ruff check app tests migrations
pytest -q
alembic upgrade head
alembic check
```

36 tests and a real local HTTP smoke workflow passed. See docs/VERIFICATION.md and the separate programming/conception/planning PDF. Contributors: update definitions and tests with semantic changes; use a new migration for schema changes and a new engine version for changed historical calculations. Saved snapshots retain their original evidence.
