"""Create broker-side stops for external Alpaca paper positions.

This is deliberately limited to the explicitly enabled *paper* execution
adapter.  A position without a recorded Project 100 stop price is a halt
condition: guessing a stop from the current price would be unsafe.
"""
from __future__ import annotations

from app.audit.logger import log_and_commit
from app.brokers.base import OrderRequest
from app.models.models import TradeDecisionRecord
from app.services.protective_order_verification import verify_protective_orders
from app.services.state_machine import StateManager


def _stop_for_position(db, symbol: str, quantity: float) -> float | None:
    decision = (db.query(TradeDecisionRecord)
                .filter(TradeDecisionRecord.symbol == symbol,
                        TradeDecisionRecord.direction == "long",
                        TradeDecisionRecord.stop_price.isnot(None),
                        TradeDecisionRecord.position_size >= quantity)
                .order_by(TradeDecisionRecord.timestamp.desc()).first())
    if decision is None:
        return None
    return float(decision.stop_price)


def ensure_protective_stops(db, adapter, cfg) -> dict:
    """Place a sell stop for each unprotected long paper position.

    The caller must have constructed ``adapter`` through the paper-only,
    execution-gated factory.  Failure halts the system before another entry can
    be considered; this function never applies to a live credential.
    """
    if not getattr(adapter, "paper", False):
        raise RuntimeError("protective-stop manager refuses live adapter")
    check = verify_protective_orders(adapter)
    placed: list[dict] = []
    state = StateManager(db, cfg)
    positions = {str(p.get("symbol")): p for p in adapter.get_positions()}
    for symbol in check["uncovered_positions"]:
        position = positions[symbol]
        quantity = abs(float(position.get("qty") or 0))
        stop_price = _stop_for_position(db, symbol, quantity)
        if quantity <= 0 or stop_price is None:
            state.activate_kill_switch(f"paper position without recorded protective stop: {symbol}")
            log_and_commit(db, "alpaca_paper_protective_stop_failed",
                           {"symbol": symbol, "reason": "missing_recorded_stop"})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "missing_recorded_stop"}
        try:
            result = adapter.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                                       order_type="stop", stop_price=stop_price,
                                                       time_in_force="gtc"))
        except Exception as exc:  # A broker uncertainty is a halt, not a retry.
            state.activate_kill_switch(f"paper protective stop failed: {symbol}")
            log_and_commit(db, "alpaca_paper_protective_stop_failed",
                           {"symbol": symbol, "reason": type(exc).__name__})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "broker_error"}
        if result.status not in {"new", "accepted", "pending"} or not result.order_id:
            state.activate_kill_switch(f"paper protective stop rejected: {symbol}")
            log_and_commit(db, "alpaca_paper_protective_stop_failed",
                           {"symbol": symbol, "reason": "rejected", "status": result.status})
            return {"protected": False, "placed": placed, "failed": symbol,
                    "reason": "rejected"}
        placed.append({"symbol": symbol, "order_id": result.order_id, "stop_price": stop_price})
        log_and_commit(db, "alpaca_paper_protective_stop_placed", placed[-1])
    verified = verify_protective_orders(adapter)
    return {**verified, "placed": placed}
