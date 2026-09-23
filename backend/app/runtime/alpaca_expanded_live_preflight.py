"""Read-only evidence check before replacing the broad live worker.

This does not switch flags, start a service, or submit an order. The operator
must also prove that the old live process has stopped before starting the new
one, because process state is outside the broker database.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.models.models import (ExternalLiveExit, ExternalLiveProtection,
                               ExternalPaperExit, ExternalPaperProtection, OrderIntent,
                               RiskReservation, StrategyValidationRecord,
                               SystemStateRecord, TradeDecisionRecord)
from app.strategies.daily_trend_pullback import EXPANDED_STRATEGY_VERSION

ACTIVE = {"new", "pending_new", "accepted", "pending", "open", "partially_filled"}
TERMINAL_STOP = {"filled", "canceled", "expired"}


def report(db, cfg) -> dict:
    blockers: list[str] = []
    validation = db.get(StrategyValidationRecord, EXPANDED_STRATEGY_VERSION)
    if validation is None or not validation.passed:
        blockers.append("expanded strategy validation has not passed")
    state = db.get(SystemStateRecord, "current")
    if state is None or state.state != "live":
        blockers.append("system is not in live state")

    paper, is_paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=True)
    live, live_is_paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if not is_paper or live_is_paper:
        blockers.append("paper and live credentials are not isolated")
    paper_accounts, live_accounts = paper.get_accounts(), live.get_accounts()
    if (len(paper_accounts) != 1 or len(live_accounts) != 1
            or not paper_accounts[0].get("account_id") or not live_accounts[0].get("account_id")
            or paper_accounts[0]["account_id"] == live_accounts[0]["account_id"]):
        blockers.append("paper and live accounts are not distinct and identifiable")
    live_account_id = str(live_accounts[0]["account_id"]) if len(live_accounts) == 1 else None
    for label, adapter in (("paper", paper), ("live", live)):
        capabilities = adapter.get_account_capabilities()
        if capabilities.get("status") != "ACTIVE" or any(
            capabilities.get(flag) for flag in
            ("trading_blocked", "trade_suspended_by_user", "account_blocked")
        ):
            blockers.append(f"{label} broker account does not permit orders")
    paper_positions, live_positions = paper.get_positions(), live.get_positions()
    paper_orders, live_orders = paper.get_orders(), live.get_orders()
    if any(float(p.get("qty") or 0) != 0 for p in paper_positions):
        blockers.append("paper broker still holds a position")
    if any(float(p.get("qty") or 0) != 0 for p in live_positions):
        blockers.append("live broker still holds a position")
    if any(str(o.get("status")) in ACTIVE for o in paper_orders):
        blockers.append("paper broker still has an active order")
    if any(str(o.get("status")) in ACTIVE for o in live_orders):
        blockers.append("live broker still has an active order")
    if live_account_id and db.query(RiskReservation).filter(
        RiskReservation.account_id == live_account_id,
        RiskReservation.status == "active",
    ).first():
        blockers.append("live risk reservation is still active")

    live_protection = (db.query(ExternalLiveProtection)
                       .order_by(ExternalLiveProtection.created_at.desc()).first())
    live_evidence = None
    if live_protection is not None:
        live_trade = (db.query(TradeDecisionRecord)
                      .filter(TradeDecisionRecord.order_id == live_protection.entry_order_id)
                      .order_by(TradeDecisionRecord.timestamp.desc()).first())
        live_stop = next((o for o in live_orders
                          if str(o.get("id")) == str(live_protection.protective_order_id)), None)
        live_exit_row = db.get(ExternalLiveExit, live_protection.entry_order_id)
        live_exit = next((o for o in live_orders
                          if str(o.get("id")) == str(live_exit_row.exit_order_id)), None) if live_exit_row else live_stop
        if not (live_trade and live_trade.status == "closed"
                and (live_trade.post_trade_analysis or {}).get("broker_reconciled") is True
                and live_trade.exit_price is not None and live_trade.pnl is not None):
            blockers.append("latest live trade ledger has not reconciled closed")
        if not (live_stop and str(live_stop.get("status")) in TERMINAL_STOP):
            blockers.append("latest live protective stop is not terminal")
        if not (live_exit and str(live_exit.get("status")) == "filled"
                and float(live_exit.get("filled_qty") or 0) > 0
                and float(live_exit.get("filled_avg_price") or 0) > 0):
            blockers.append("latest live exit fill is not verified")
        live_evidence = {"symbol": live_protection.symbol,
                         "entry_order_id": live_protection.entry_order_id,
                         "exit_order_id": str(live_exit.get("id")) if live_exit else None,
                         "stop_order_id": str(live_stop.get("id")) if live_stop else None,
                         "realized_pnl": live_trade.pnl if live_trade else None}

    trade = (db.query(TradeDecisionRecord)
             .filter(TradeDecisionRecord.strategy == EXPANDED_STRATEGY_VERSION)
             .order_by(TradeDecisionRecord.timestamp.desc()).first())
    evidence = None
    if trade is None or trade.status != "closed" or not trade.order_id:
        blockers.append("latest expanded paper trade has not closed")
    else:
        protection = db.get(ExternalPaperProtection, str(trade.order_id))
        exit_row = db.get(ExternalPaperExit, str(trade.order_id))
        by_id = {str(o.get("id")): o for o in paper_orders}
        stop = by_id.get(str(protection.protective_order_id)) if protection else None
        exit_order = by_id.get(str(exit_row.exit_order_id)) if exit_row else stop
        analysis = trade.post_trade_analysis or {}
        intents = db.query(OrderIntent).filter(OrderIntent.trade_id == trade.trade_id).all()
        active_risk = any(db.query(RiskReservation).filter(
            RiskReservation.account_id == intent.account_id,
            RiskReservation.decision_id == intent.decision_id,
            RiskReservation.status == "active").first() for intent in intents)
        if not (protection and stop and str(stop.get("status")) in TERMINAL_STOP):
            blockers.append("exact paper protective stop is not terminal")
        if not (exit_order and str(exit_order.get("status")) == "filled"
                and float(exit_order.get("filled_qty") or 0) > 0
                and float(exit_order.get("filled_avg_price") or 0) > 0):
            blockers.append("paper exit fill is not verified")
        if not (analysis.get("broker_reconciled") is True and trade.fill_price is not None
                and trade.exit_price is not None and trade.pnl is not None):
            blockers.append("paper trade ledger lacks broker-reconciled fill and P&L")
        if trade.exit_reason not in {"stop_hit", "target_hit", "session_close"}:
            blockers.append("latest paper exit was not a normal protected lifecycle")
        if active_risk:
            blockers.append("paper risk reservation is still active")
        evidence = {"symbol": trade.symbol, "trade_id": trade.trade_id,
                    "entry_order_id": trade.order_id,
                    "exit_order_id": str(exit_order.get("id")) if exit_order else None,
                    "stop_order_id": str(stop.get("id")) if stop else None,
                    "exit_reason": trade.exit_reason, "realized_pnl": trade.pnl}
    return {"ready": not blockers, "strategy": EXPANDED_STRATEGY_VERSION,
            "blockers": blockers, "paper_lifecycle": evidence,
            "live_lifecycle": live_evidence,
            "requires_worker_handoff": True, "order_submission": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    cfg = Settings()
    with Session(create_engine(args.database)) as db:
        result = report(db, cfg)
        print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
