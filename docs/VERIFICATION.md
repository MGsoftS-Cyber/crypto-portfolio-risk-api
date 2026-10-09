# Verification - 6 October 2026

36 tests passed: fee-aware81USD fixture; full-sale cost release; external flows and drawdown; exact price requirements; zero-capital gaps; oversell/negativecash; badfees; daysequence/IDs; decimal strings/bounds; CSV errors; risk quantiles/sample limits; temporal ML holdout/determinism; owner/CSRF/origin/session; idempotency/dedup; no partial failed analysis; optional market adapter disabled/missing/rate/stale cases.

Real Uvicorn/SQLite HTTP smoke passed: registration, demo creation,60-day analysis with scoredML, all five export formats, OpenAPI/Swagger availability and logout. examples/demo-report.json is the verified synthetic saved response; dates in a newly generated demo are relative to the run date.

Ruff lint/format and Alembic empty SQLite migration/check passed. Docker image/Compose configuration and PostgreSQL execution were not run in this environment. Live CoinGecko request was not executed; HTTP adapter contract tested with mocked responses. Upstream Starlette emitted an httpx deprecation warning; included pinned httpx worked.
