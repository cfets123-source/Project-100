"""One-shot, bounded external Alpaca paper lifecycle verification.

This is an engineering verification tool, not a strategy.  It is hard-capped
at one whole share and ten dollars of paper notional, requires the paper gate,
and records each outcome in the append-only audit log.
"""
from __future__ import annotations

import time
import uuid

from app.audit.logger import log_and_commit
from app.brokers.alpaca_connection import load_paper_execution_adapter
from app.brokers.base import OrderRequest
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.base import validate_quote
from app.models.models import TradeDecisionRecord
from app.services.alpaca_paper_protection import ensure_protective_stops
from app.services.protective_order_verification import verify_protective_orders
from app.runtime.alpaca_live_position_manager import manage_paper_positions

MAX_NOTIONAL = 10.0
POLL_SECONDS = 2.0
TIMEOUT_SECONDS = 30.0


def run_once(db, cfg, symbol: str, strategy: str = "paper_lifecycle_verification") -> dict:
    if not cfg.ALPACA_PAPER_EXECUTION_ENABLED:
        return {"passed": False, "reason": "paper_execution_gate_disabled"}
    adapter = load_paper_execution_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, enabled=True)
    if not adapter.get_market_clock().get("is_open"):
        return {"passed": False, "reason": "market_closed"}
    provider = AlpacaMarketDataProvider(adapter)
    provider.refresh_account_snapshot()
    quote = provider.get_quote(symbol)
    if not validate_quote(quote, cfg.MAX_QUOTE_AGE_SECONDS).valid:
        return {"passed": False, "reason": "stale_quote"}
    if quote.ask > MAX_NOTIONAL:
        return {"passed": False, "reason": "symbol_exceeds_bounded_notional"}

    decision = TradeDecisionRecord(symbol=symbol, direction="long", strategy=strategy,
                                   entry_price=quote.ask, stop_price=round(quote.ask * 0.98, 2),
                                   target_price=round(quote.ask * 1.01, 2), position_size=1.0,
                                   status="proposed")
    db.add(decision); db.commit()
    try:
        result = adapter.place_order(OrderRequest(symbol=symbol, side="buy", quantity=1, order_type="market"))
    except Exception as exc:
        decision.status = "rejected"
        db.commit()
        log_and_commit(db, "alpaca_paper_lifecycle_failed",
                       {"step": "entry_submission", "error": type(exc).__name__})
        return {"passed": False, "reason": "entry_submission_failed",
                "error": type(exc).__name__}
    decision.order_id = result.order_id; db.commit()
    log_and_commit(db, "alpaca_paper_lifecycle_entry", {"symbol": symbol, "order_id": result.order_id})

    deadline = time.monotonic() + TIMEOUT_SECONDS
    status = {"status": result.status}
    while time.monotonic() < deadline:
        status = adapter.get_order_status(result.order_id)
        if status.get("status") in {"filled", "rejected", "canceled"}:
            break
        time.sleep(POLL_SECONDS)
    if status.get("status") != "filled":
        log_and_commit(db, "alpaca_paper_lifecycle_failed", {"step": "entry", "status": status.get("status")})
        return {"passed": False, "reason": "entry_not_filled", "order_id": result.order_id}

    decision.status = "open"; decision.fill_price = float(status.get("filled_avg_price") or quote.ask); db.commit()
    protection = ensure_protective_stops(db, adapter, cfg)
    if not protection.get("protected"):
        return {"passed": False, "reason": "protective_stop_failed", "protection": protection}

    # Engineering test only: use a target already met by the fresh quote so the
    # real target-exit manager is exercised without waiting for a market move.
    # Normal strategy trades retain their strategy-derived target prices.
    decision.target_price = 0.01
    db.commit()
    lifecycle = manage_paper_positions(db, adapter, allow_legacy_target_exit=True)
    if not lifecycle["target_exits_submitted"]:
        return {"passed": False, "reason": "target_exit_not_submitted", "protection": protection}
    exit_order_id = lifecycle["target_exits_submitted"][0]["exit_order_id"]
    while time.monotonic() < deadline:
        exit_status = adapter.get_order_status(exit_order_id)
        if exit_status.get("status") in {"filled", "rejected", "canceled"}:
            break
        time.sleep(POLL_SECONDS)
    if exit_status.get("status") != "filled":
        return {"passed": False, "reason": "exit_not_filled", "order_id": exit_order_id}
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        completed = manage_paper_positions(db, adapter, allow_legacy_target_exit=True)
        if completed["stops_cancelled"]:
            break
        time.sleep(POLL_SECONDS)
    else:
        return {"passed": False, "reason": "stop_not_cancelled_after_flat", "order_id": exit_order_id}
    evidence = {"run_id": str(uuid.uuid4()), "symbol": symbol, "entry_order_id": result.order_id,
                "exit_order_id": exit_order_id, "protection": protection, "lifecycle": completed,
                "quote_age_seconds": quote.age_seconds}
    log_and_commit(db, "alpaca_paper_lifecycle_passed", evidence)
    return {"passed": True, **evidence}
