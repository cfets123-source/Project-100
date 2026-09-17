"""
Places the protective stop order that must exist for every filled entry. If the
broker rejects/fails this call, we fail SAFE: block new entries via SAFE mode and
alert, rather than leaving a filled position with no protection and rather than
silently liquidating it (spec: distinguish "stop new risk" from "emergency
liquidation" — this function only ever does the former).
"""
from sqlalchemy.orm import Session
from app.brokers.base import BrokerAdapter, OrderRequest
from app.services.state_machine import StateManager
from app.audit.logger import log_and_commit


def place_protective_stop(db: Session, broker: BrokerAdapter, state_manager: StateManager,
                           symbol: str, quantity: float, stop_price: float) -> bool:
    try:
        result = broker.place_order(OrderRequest(symbol=symbol, side="sell", quantity=quantity,
                                                   order_type="stop", limit_price=stop_price))
    except Exception as e:  # noqa: BLE001 — any broker-side failure is treated the same: fail safe
        state_manager.enter_safe_mode(f"protective_stop_placement_failed:{symbol}:{e}")
        log_and_commit(db, "protective_stop_failed", {"symbol": symbol, "error": str(e)})
        return False

    if result.status == "rejected":
        state_manager.enter_safe_mode(f"protective_stop_rejected:{symbol}")
        log_and_commit(db, "protective_stop_failed", {"symbol": symbol, "reason": "rejected", "raw": result.raw})
        return False

    log_and_commit(db, "protective_stop_placed", {"symbol": symbol, "order_id": result.order_id,
                                                    "stop_price": stop_price})
    return True
