# Contributor guide

Keep Decimal accounting in ledger.py and pure evaluation orchestration in engine.py. Keep statistical floats in risk.py; never use them to update cash/cost. Add focused checks for any new transaction type, currency, fee rule or return convention. Update METHODOLOGY/PLAN and bump engine version for semantic changes. Preserve saved outputs; do not silently recompute historical reports with newer models.

Owner-check every query. Durable writes must use services.mutation and commit business effects plus receipt atomically. Add new Alembic revisions for deployed schema changes; never edit old deployed migrations. Run README checks. A PR should explain changed behavior, financial identity impact, validation and remaining limits. Keep .env, database files, private credentials and real wallet payloads out of Git. The project is a descriptive analytics API and sends no trades or blockchain transactions.
