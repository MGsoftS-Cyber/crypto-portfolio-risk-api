# Development plan per part

These stages describe the included implementation and its dependencies; they are not calendar commitments.

1. Foundation/contracts: initialize Python, requirements, config, strict decimal strings and examples. Deliver bounded USD ledger models. Acceptance: reject floats, negatives, nonfinite values and invalid event shapes.
2. Accounts/database: User,LoginSession,Portfolio,Dataset,Analysis,RequestRecord; Argon2/session/CSRF; Alembic. Depends on1. Acceptance: isolated owners, logout, safe errors, migration creates all entities.
3. Imports: parse exact transaction/price CSV headers; normalize dates/IDs/sequence; reject illegal ledger transitions. Depends on1–2. Acceptance: reviewed valid rows, useful errors, duplicate detection, no partial persisted writes.
4. Financial engine: cash/positions/cost pools, buy/sell fees, realized/unrealized, allocation and reconciliation. Depends on3. Acceptance: worked81USD fixture and full-sale dust test; missing prices never fill automatically.
5. Historical risk: daily valuation, start-of-day flow adjustment, chained NAV, drawdown, volatility, historicalVaR/ES. Depends on4. Acceptance: deposit does not create profit/return, zero-capital gaps disable statistics, sample limits work.
6. Explainable unusual changes: concentration/change/turnover rules then optional IsolationForest. Depends on5. Acceptance: deterministic temporal holdout; a later changed sample cannot change earlier scores; evidence and limitations returned.
7. API integration: durable idempotent writes, frozen snapshots, report/CSV exports and read-only CoinGecko adapter. Depends on2–6. Acceptance: same key replays, foreign IDs rejected, all five exports pass, market errors handled with mocked responses.
8. Delivery: HTTP demo client, OpenAPI, pinned dependencies, Docker recipe, CI, complete guide. Depends onall. Acceptance:36tests, lint/format, SQLite migration and real local smoke pass. Docker/PostgreSQL runtime remains unverified here.

Future stages are separate work: React/mobile dashboard, exchange CSV adapters, crypto-native fees/swaps/staking, multi-currency FX, event-time returns, organizations/roles, OAuth/service keys, background imports, retention, distributed throttling and monitored deployment. Each needs its own schema/analytics tests; avoid adding a paid provider dependency to core accounting.
