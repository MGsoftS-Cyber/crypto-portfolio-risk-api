# API contracts

Auth: POST /api/auth/register or /login with email,password. Response user,csrf_token; HttpOnly crypto_session cookie. GET /api/auth/session restores the session; POST /api/auth/logout revokes it. A password is12–128 characters; boundary whitespace is rejected. Cookie lasts7days. CLI may omit Origin; supplied Origin must be allowed. Protected POSTs require X-CSRF-Token. Durable writes also require Idempotency-Key. A request key replays the saved response only for the same owner/scope/payload; different payload yields409.

GET /api/health: status and engine_version.
GET /api/v1/portfolios: own portfolio list.
POST /api/v1/portfolios: {name,base_currency:'USD'} ->201.
POST /api/v1/imports/preview: {transactions_csv,prices_csv} -> valid,rows,quality,errors; no persistence.
GET /api/v1/portfolios/{id}/datasets: dataset versions, owner scoped.
POST /api/v1/portfolios/{id}/datasets: {source,coverage_end,transactions[],prices[]} ->201.
POST /api/v1/portfolios/{id}/analyses: {dataset_id,as_of,name,enable_ml,concentration_limit,daily_change_limit,turnover_limit} ->201 frozen analysis.
GET /api/v1/analyses: latest100 own analyses.
GET /api/v1/analyses/{id}: one immutable report.
GET /api/v1/analyses/{id}/report?format=json|holdings|history|trades|alerts: attachment.
POST /api/v1/market/quotes: {asset_ids:['bitcoin','ethereum']} ->optional current prices, timestamp,age,stale.
POST /api/v1/demo: synthetic portfolio/dataset in empty catalog ->201.

Return body of analysis: id,portfolio_id,dataset_id,inputs,results,engine_version,created_at. Results contain summary,holdings,closed_positions,history,trades,risk,alerts,ml,warnings. Inputs preserve full ledgers, price assumptions and chosen thresholds. Money/quantity values are strings; ratio values are numeric fractions or null. Never multiply a decimal-string value by a binary float in a downstream accounting client.

JSON example transaction:
{"transaction_id":"B1","date":"2026-01-01","sequence":2,"kind":"buy","asset_id":"bitcoin","quantity":"2","unit_price":"100","amount":"0","fee":"4"}

Analysis example:
{"dataset_id":"returned-dataset-uuid","as_of":"2026-01-02","name":"Review","enable_ml":false,"concentration_limit":0.6,"daily_change_limit":0.1,"turnover_limit":0.5}

Error envelope: error.code/error.message; field validation adds fields with path/message, never raw values. 401 sign in;403 origin/CSRF;404 missing or outside account;409 conflicting key/account/write;422 invalid input or missing daily price;429 local auth throttle;503 optional provider disabled/rate limit;502 optional provider invalid/unavailable response. CSV free-text export neutralizes spreadsheet formula prefixes; validated decimal columns remain numeric strings.

Account ownership is checked through Portfolio on every dataset/analysis/report lookup. Swagger/docs is documentation, not a full dashboard. The included demo_client.py is a runnable session/API example. Service-to-service API keys, OAuth scopes, wallet signatures and external exchange connectors are future extensions.
