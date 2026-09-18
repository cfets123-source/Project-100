"""
Places a simulated protective stop in authorized PAPER/SAFE contexts. Failure
blocks new entries via SAFE mode (or preserves an existing HALTED state) and
records an audit event. This does not guarantee protection, send an alert, or
liquidate a position. Real protective execution is not implemented or authorized.
"""
from sqlalchemy.orm import Session
from app.brokers.base import BrokerAdapter, OrderRequest
from app.services.state_machine import StateManager
from app.audit.logger import log_and_commit
from app.services.broker_authorization import mutation_allowed
import math


def place_protective_stop(db: Session, broker: BrokerAdapter, state_manager: StateManager,
                           symbol: str, quantity: float, stop_price: float) -> bool:
    allowed, reason = mutation_allowed(state_manager, broker, defensive=True)
    if not allowed:
        log_and_commit(db, "protective_stop_blocked", {"symbol": symbol, "reason": reason})
        return False
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0
               for v in (quantity, stop_price)):
        log_and_commit(db, "protective_stop_blocked", {"symbol": symbol, "reason": "invalid_order_values"})
        return False
    try:
        result = broker.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                                   order_type="stop", limit_price=stop_price))
    except Exception as e:  # noqa: BLE001 — any broker-side failure is treated the same: fail safe
        state_manager.enter_safe_mode(f"protective_stop_placement_failed:{symbol}:{e}")
        log_and_commit(db, "protective_stop_failed", {"symbol": symbol, "error": str(e)})
        return False

    if result.status not in ("accepted", "filled", "partial") or not result.order_id:
        state_manager.enter_safe_mode(f"protective_stop_rejected:{symbol}")
        log_and_commit(db, "protective_stop_failed", {"symbol": symbol, "reason": "rejected", "raw": result.raw})
        return False

    log_and_commit(db, "protective_stop_placed", {"symbol": symbol, "order_id": result.order_id,
                                                    "stop_price": stop_price})
    return True
