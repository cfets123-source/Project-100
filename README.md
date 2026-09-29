# Veloikos Trading

Stage-by-stage trading software: trade toward the next account milestone, sell, reconcile actual proceeds, then fund the next stage. The initial target is configurable within $200–$500, followed by $1,000, $3,000, $5,000, $10,000, $50,000, $100,000, $300,000, $500,000 and $1,000,000. A strategy can differ between stages. Returns are not guaranteed.

This workspace contains an imported development snapshot of Project 100, preserving its prior uncommitted source. Source provenance is in `audit/import-manifest.json`; the older checkout is unchanged. Account databases and credentials were not imported.

## Run locally

Use Python 3.12. Install pinned dependencies into a virtual environment, then run:

```sh
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/dashboard . Without a connected broker, balances and positions show unavailable rather than zero. Live execution defaults off. This local preview is separate from the existing server account.

```sh
.venv/bin/python -m pytest backend/tests -q --tb=short --disable-warnings
```

## September 24 repairs

- Separate configured paper/live state scopes, preserving existing emergency halts during migration.
- Account-bound, fresh, cash-flow-adjusted risk observations instead of hardcoded zero losses.
- Read-only broker risk collection, rejecting ambiguous transfers and incomplete evidence.
- Existing-position supervision before entry-strategy approval, with separate default-off management permission.
- Restricted sell adapter with durable submission intent and reconciliation after unknown outcomes.
- Persisted milestone liquidation/reconciliation/available-proceeds lifecycle; no milestone credit for additional deposits.
- Dynamic dashboard targets and explicit unavailable account data.
- Read-only account observer that forces all order-execution flags off in code.

`release/compose.api.yml` starts only the web API and read-only account observer. It does not launch a trading worker. Code tests, connection checks, broker lifecycle evidence, deployment, live activation, fills and profitability are separate facts. See `audit/IMPLEMENTATION_STATUS.md` for verified release state and outstanding work.
