"""Isolated Robinhood lifecycle worker; no strategy scan or entry submission."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.robinhood_execution import load_agentic_order_transport
from app.core.config import Settings
from app.db.session import initialize_schema
from app.models.models import (OrderIntent, RiskReservation, RobinhoodOptionLifecycle,
                               RobinhoodTradeLifecycle, TradeDecisionRecord)
from app.services.robinhood_entry import recover_uncertain_entry
from app.services.robinhood_lifecycle import reconcile_trade
from app.services.robinhood_option_lifecycle import reconcile_option_trade
from app.services.state_machine import StateManager


def run_cycle(db, cfg: Settings) -> dict:
    if not (cfg.LIVE_TRADING_ENABLED and
            (cfg.ROBINHOOD_EQUITY_EXECUTION_ENABLED or cfg.ROBINHOOD_CRYPTO_EXECUTION_ENABLED
             or cfg.ROBINHOOD_OPTIONS_EXECUTION_ENABLED)):
        return {"status": "disabled", "processed": 0}
    # A persisted preparing intent is provably before the broker-send boundary.
    # Expire it only after network preview timeouts have long passed. The entry
    # path claims the same status conditionally before any send.
    cutoff = datetime.utcnow() - timedelta(minutes=2)
    preparing = db.query(OrderIntent).filter(OrderIntent.status == "preparing",
                                              OrderIntent.created_at < cutoff).all()
    for intent in preparing:
        trade = db.get(TradeDecisionRecord, intent.trade_id)
        if trade is None or not str(trade.strategy or "").startswith("robinhood-"):
            continue
        claimed = db.query(OrderIntent).filter(OrderIntent.intent_key == intent.intent_key,
                                               OrderIntent.status == "preparing").update(
            {"status": "canceled"}, synchronize_session=False)
        if claimed == 1:
            trade.status = "rejected"
            db.query(RiskReservation).filter_by(account_id=intent.account_id,
                                                decision_id=intent.decision_id,
                                                status="active").update({"status": "released"})
            db.commit()
    rows = db.query(RobinhoodTradeLifecycle).filter(
        RobinhoodTradeLifecycle.status.notin_(["closed", "entry_failed"])).all()
    uncertain = db.query(OrderIntent).filter(OrderIntent.status.in_(["submitting", "unknown", "submitted"])).all()
    uncertain = [intent for intent in uncertain
                 if db.get(TradeDecisionRecord, intent.trade_id) is not None and
                 str(db.get(TradeDecisionRecord, intent.trade_id).strategy or "").startswith("robinhood-") and
                 db.get(RobinhoodTradeLifecycle, intent.trade_id) is None and
                 db.get(RobinhoodOptionLifecycle, intent.trade_id) is None and
                 db.get(TradeDecisionRecord, intent.trade_id).asset_class != "option"]
    option_orphans = [intent for intent in db.query(OrderIntent).filter(
        OrderIntent.status.in_(["submitting", "unknown", "submitted"])).all()
        if db.get(TradeDecisionRecord, intent.trade_id) is not None
        and db.get(TradeDecisionRecord, intent.trade_id).asset_class == "option"
        and str(db.get(TradeDecisionRecord, intent.trade_id).strategy or "").startswith("robinhood-option-")
        and db.get(RobinhoodOptionLifecycle, intent.trade_id) is None]
    if option_orphans:
        result = {"status": "safety_failure", "reason": "option_entry_lifecycle_missing",
                  "trade_ids": [intent.trade_id for intent in option_orphans]}
        StateManager(db, cfg).activate_kill_switch("Robinhood option entry lifecycle missing")
        log_and_commit(db, "robinhood_option_entry_lifecycle_missing", result)
        return {"status": "safety_failure", "processed": len(option_orphans),
                "outcomes": [result]}
    option_rows = db.query(RobinhoodOptionLifecycle).filter(
        RobinhoodOptionLifecycle.status.notin_(["closed", "entry_failed",
                                               "exit_filled_fee_pending"])).all()
    if not rows and not uncertain and not option_rows:
        return {"status": "idle", "processed": 0}
    transport = load_agentic_order_transport(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, cfg)
    outcomes = []
    for intent in uncertain:
        recovery = recover_uncertain_entry(db, transport, intent.intent_key)
        outcomes.append(recovery.__dict__)
        if recovery.status == "unknown":
            # A delayed broker response is unresolved, so no new entries may
            # pass the local-intent gate; do not submit a replacement order.
            return {"status": "entry_unresolved", "processed": len(outcomes),
                    "outcomes": outcomes}
        if recovery.status != "submitted":
            StateManager(db, cfg).activate_kill_switch(
                f"Robinhood entry recovery failed: {recovery.reason}")
            return {"status": "safety_failure", "processed": len(outcomes),
                    "outcomes": outcomes}
    rows = db.query(RobinhoodTradeLifecycle).filter(
        RobinhoodTradeLifecycle.status.notin_(["closed", "entry_failed"])).all()
    for row in rows:
        result = reconcile_trade(db, transport, row.trade_id)
        outcomes.append(result)
        if result["status"] == "emergency_pending":
            StateManager(db, cfg).activate_kill_switch(
                f"Robinhood emergency exit pending: {result['reason']}")
            log_and_commit(db, "robinhood_emergency_exit_pending", result)
        if result["status"] == "safety_failure":
            StateManager(db, cfg).activate_kill_switch(
                f"Robinhood lifecycle safety failure: {result['reason']}")
            log_and_commit(db, "robinhood_lifecycle_safety_failure", result)
            return {"status": "safety_failure", "processed": len(outcomes),
                    "outcomes": outcomes}
    for row in option_rows:
        result = reconcile_option_trade(db, transport, row.trade_id)
        outcomes.append(result)
        if result["status"] == "safety_failure":
            StateManager(db, cfg).activate_kill_switch(
                f"Robinhood option lifecycle safety failure: {result['reason']}")
            log_and_commit(db, "robinhood_option_lifecycle_safety_failure", result)
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
