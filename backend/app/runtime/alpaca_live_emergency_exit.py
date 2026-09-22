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
from app.services.state_machine import HALTED, StateManager

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
    writer = AlpacaBrokerAdapter(reader.headers["APCA-API-KEY-ID"],
                                 reader.headers["APCA-API-SECRET-KEY"],
                                 paper=False, allow_order_submission=True)
    result = writer.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                             order_type="market", time_in_force="day"))
    evidence = {"symbol": symbol, "quantity": quantity, "order_id": result.order_id,
                "broker_status": result.status, "filled_qty": result.filled_qty,
                "filled": result.status == "filled" and result.filled_qty >= quantity}
    log_and_commit(db, "alpaca_live_halted_emergency_exit_submitted", evidence)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--confirmed-emergency-exit", action="store_true")
    args = parser.parse_args()
    if not args.confirmed_emergency_exit:
        raise SystemExit("explicit emergency-exit flag required")
    with Session(create_engine(args.database)) as db:
        print(emergency_exit(db, Settings(), args.symbol.upper()), flush=True)


if __name__ == "__main__":
    main()
