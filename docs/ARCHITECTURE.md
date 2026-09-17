# Project 100 — Phase 1 Architecture

## Pipeline (enforced order, no shortcuts)
Market Data → Strategy Engine → AI Analysis → Signal → **Risk Engine (final authority)**
→ Order Validator → Broker Adapter → Execution → Audit Log

LLM output is never passed to `BrokerAdapter.place_order` directly. Signals pass through
`app/risk/engine.py::RiskEngine.evaluate()`, a pure deterministic function, before any
order is constructed.

## Repo layout
```
backend/app/
  core/config.py      # ALL risk params, single source of truth (env-driven)
  db/session.py        # SQLAlchemy engine (sqlite dev, postgres prod via DATABASE_URL)
  models/models.py     # AuditLogEntry, TradeDecisionRecord, StrategyStats, SystemStateRecord, AccountSnapshot
  brokers/base.py       # BrokerAdapter interface + Quote/OrderRequest/OrderResult
  brokers/paper_broker.py  # PaperBrokerAdapter (Phase 1 implementation)
  risk/engine.py        # RiskEngine — deterministic veto authority
  strategies/base.py     # BaseStrategy interface
  audit/logger.py        # append-only audit log helpers
  main.py                 # FastAPI shell: /health, /system/state, /config/risk
```

## Phase 1 status: PASS
- 24/24 tests passing (risk engine, paper broker, audit log, API shell).
- Default state on boot: `AUTONOMY_LEVEL=0` (research only), `TRADING_MODE=paper`,
  `AUTO_EXECUTION=false`, margin/options/shorts/leverage all disabled.
- Not yet implemented: RobinhoodAdapter, ETradeAdapter, market data provider,
  scanner/watchlist, catalyst engine, signal scoring, backtester, frontend, Docker,
  Celery/Redis, kill switch, self-pause/safe-mode logic. These are Phase 2+.

## Deferred infra decisions
- Postgres/Redis/Docker not stood up yet in this sandbox — `DATABASE_URL` defaults
  to sqlite so the app is runnable without external infra during scaffolding.
  Swap to postgres via env var when infra is provisioned; no code change needed.
