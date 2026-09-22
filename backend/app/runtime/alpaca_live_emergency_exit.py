"""One-shot, sell-only emergency exit for an uncovered live position.

This path is deliberately independent of the LIVE entry gate: a kill switch
must not prevent risk reduction. It cannot submit a buy or reset the halt.
"""
from __future__ import annotations

import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.alpaca_adapter import AlpacaBrokerAdapter
from app.brokers.alpaca_connection import load_read_only_adapter
from app.brokers.base import OrderRequest
from app.core.config import Settings
from app.models.models import AuditLogEntry, TradeDecisionRecord
from app.runtime.alpaca_live_position_manager import _finish_trade
from app.services.state_machine import HALTED, StateManager
from app.strategies.daily_trend_pullback import BroadDailyTrendPullback, DailyTrendPullback

ACTIVE = {"new", "accepted", "pending_new", "partially_filled", "held", "pending_replace"}


def emergency_exit(db, cfg, symbol: str) -> dict:
    """Queue one exact-quantity DAY sell only if live is halted and uncovered."""
    if StateManager(db, cfg).get_state() != HALTED:
        raise RuntimeError("emergency exit requires halted state")
    if not symbol.isalpha() or len(symbol) > 10:
        raise ValueError("invalid symbol")
    reader, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if paper or reader.paper:
        raise RuntimeError("emergency exit requires separate live credential")
    positions = [p for p in reader.get_positions() if p.get("symbol") == symbol]
    if len(positions) != 1:
        raise RuntimeError("expected exactly one matching live position")
    quantity = float(positions[0].get("qty") or 0)
    if quantity <= 0:
        raise RuntimeError("emergency exit requires positive long quantity")
    active = [o for o in reader.get_orders() if o.get("symbol") == symbol
              and o.get("side") == "sell" and o.get("status") in ACTIVE]
    if active:
        raise RuntimeError("active sell order already exists; no duplicate emergency exit")
    trade = (db.query(TradeDecisionRecord)
             .filter(TradeDecisionRecord.symbol == symbol,
                     TradeDecisionRecord.strategy.in_((DailyTrendPullback.name,
                                                       BroadDailyTrendPullback.name)),
                     TradeDecisionRecord.status == "open")
             .order_by(TradeDecisionRecord.timestamp.desc()).first())
    writer = AlpacaBrokerAdapter(reader.headers["APCA-API-KEY-ID"],
                                 reader.headers["APCA-API-SECRET-KEY"],
                                 paper=False, allow_order_submission=True)
    result = writer.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                             order_type="market", time_in_force="day"))
    evidence = {"symbol": symbol, "quantity": quantity, "order_id": result.order_id,
                "broker_status": result.status, "filled_qty": result.filled_qty,
                "filled": result.status == "filled" and result.filled_qty >= quantity,
                "entry_order_id": str(trade.order_id) if trade else None}
    log_and_commit(db, "alpaca_live_halted_emergency_exit_submitted", evidence)
    return evidence


def reconcile_emergency_exits(db, cfg) -> dict:
    """Read-only broker reconciliation of fills submitted during a live halt.

    A queued after-hours sell must never be treated as an exit until its exact
    broker order is filled and the broker reports the symbol flat.
    """
    if StateManager(db, cfg).get_state() != HALTED:
        return {"status": "not_halted", "closed": [], "pending": []}
    events = (db.query(AuditLogEntry)
              .filter(AuditLogEntry.event_type == "alpaca_live_halted_emergency_exit_submitted")
              .order_by(AuditLogEntry.timestamp.desc()).all())
    if not events:
        return {"status": "no_emergency_exit", "closed": [], "pending": []}
    reader, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if paper or reader.paper:
        raise RuntimeError("emergency reconciliation requires separate live credential")
    positions = {str(p.get("symbol")) for p in reader.get_positions()
                 if float(p.get("qty") or 0) != 0}
    broker_buys = {str(o.get("id")): o for o in reader.get_orders()
                   if str(o.get("side")) == "buy" and str(o.get("status")) == "filled"}
    closed, pending = [], []
    seen = set()
    for event in events:
        evidence = event.payload or {}
        symbol, order_id = str(evidence.get("symbol") or ""), str(evidence.get("order_id") or "")
        if not symbol or not order_id or order_id in seen:
            continue
        seen.add(order_id)
        trade = (db.query(TradeDecisionRecord)
                 .filter(TradeDecisionRecord.symbol == symbol,
                         TradeDecisionRecord.direction == "long",
                         TradeDecisionRecord.strategy.in_((DailyTrendPullback.name,
                                                           BroadDailyTrendPullback.name)),
                         TradeDecisionRecord.status == "open",
                         TradeDecisionRecord.order_id.isnot(None))
                 .order_by(TradeDecisionRecord.timestamp.desc()).first())
        if trade is None or event.timestamp < trade.timestamp:
            continue
        if evidence.get("entry_order_id") and str(evidence["entry_order_id"]) != str(trade.order_id):
            continue
        entry = broker_buys.get(str(trade.order_id))
        if entry is None or str(entry.get("symbol")) != symbol:
            continue
        order = reader.get_order_status(order_id)
        if str(order.get("id")) != order_id or str(order.get("symbol")) != symbol or str(order.get("side")) != "sell":
            raise RuntimeError(f"emergency exit broker identity mismatch: {order_id}")
        if symbol in positions or str(order.get("status")) != "filled":
            pending.append({"symbol": symbol, "order_id": order_id, "broker_status": order.get("status")})
            continue
        if float(order.get("filled_qty") or 0) <= 0 or float(order.get("filled_avg_price") or 0) <= 0:
            raise RuntimeError(f"filled emergency exit lacks price or quantity: {order_id}")
        if float(order["filled_qty"]) + 0.000001 < float(evidence.get("quantity") or 0):
            raise RuntimeError(f"filled emergency exit is short of submitted quantity: {order_id}")
        if _finish_trade(db, str(trade.order_id), order, "emergency_protection_failure", "live"):
            closed.append({"symbol": symbol, "order_id": order_id, "trade_id": trade.trade_id,
                           "realized_pnl": trade.pnl})
    return {"status": "reconciled", "closed": closed, "pending": pending}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--symbol")
    parser.add_argument("--confirmed-emergency-exit", action="store_true")
    parser.add_argument("--reconcile-only", action="store_true")
    args = parser.parse_args()
    if not args.reconcile_only and not args.confirmed_emergency_exit:
        raise SystemExit("explicit emergency-exit flag required")
    with Session(create_engine(args.database)) as db:
        if args.reconcile_only:
            print(reconcile_emergency_exits(db, Settings()), flush=True)
        elif args.symbol:
            print(emergency_exit(db, Settings(), args.symbol.upper()), flush=True)
        else:
            raise SystemExit("--symbol is required for an emergency exit")


if __name__ == "__main__":
    main()
