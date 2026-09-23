"""Isolated Robinhood lifecycle worker; no strategy scan or entry submission."""
from __future__ import annotations

import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.robinhood_execution import load_agentic_order_transport
from app.core.config import Settings
from app.db.session import initialize_schema
from app.models.models import RobinhoodTradeLifecycle
from app.services.robinhood_lifecycle import reconcile_trade
from app.services.state_machine import StateManager


def run_cycle(db, cfg: Settings) -> dict:
    if not (cfg.LIVE_TRADING_ENABLED and
            (cfg.ROBINHOOD_EQUITY_EXECUTION_ENABLED or cfg.ROBINHOOD_CRYPTO_EXECUTION_ENABLED)):
        return {"status": "disabled", "processed": 0}
    rows = db.query(RobinhoodTradeLifecycle).filter(
        RobinhoodTradeLifecycle.status.notin_(["closed", "entry_failed"])).all()
    if not rows:
        return {"status": "idle", "processed": 0}
    transport = load_agentic_order_transport(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, cfg)
    outcomes = []
    for row in rows:
        result = reconcile_trade(db, transport, row.trade_id)
        outcomes.append(result)
        if result["status"] == "safety_failure":
            StateManager(db, cfg).activate_kill_switch(
                f"Robinhood lifecycle safety failure: {result['reason']}")
            log_and_commit(db, "robinhood_lifecycle_safety_failure", result)
            break
    return {"status": "checked", "processed": len(outcomes), "outcomes": outcomes}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    while True:
        with Session(engine) as db:
            try:
                print(run_cycle(db, cfg), flush=True)
            except Exception as exc:
                StateManager(db, cfg).activate_kill_switch(
                    f"Robinhood lifecycle worker error: {type(exc).__name__}")
                log_and_commit(db, "robinhood_lifecycle_worker_error", {"error_type": type(exc).__name__})
                print({"status": "safety_failure", "reason": type(exc).__name__}, flush=True)
        if args.once:
            break
        time.sleep(max(10, args.interval))
