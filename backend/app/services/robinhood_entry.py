"""Gated Robinhood entry path with durable intent and broker-reference recovery.

This is called only by a future separately validated strategy worker. No API
endpoint or scheduled Robinhood entry worker invokes it during staging.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import floor, isfinite
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from app.brokers.base import Quote
from app.brokers.robinhood_execution import RobinhoodOrderTransport
from app.models.models import (OrderIntent, RobinhoodStrategyReadiness,
                               StrategyValidationRecord, TradeDecisionRecord)
from app.risk.engine import RiskEngine, TradeProposal
from app.schemas.signal import SignalSchema
from app.services import risk_budget
from app.services.robinhood_lifecycle import record_entry
from app.services.state_machine import StateManager


OPEN_ORDER_STATES = {"new", "pending", "queued", "confirmed", "accepted", "open", "partially_filled"}


@dataclass
class EntryResult:
    status: str
    reason: str
    trade_id: str | None = None
    order_id: str | None = None


def _key(account_id: str, decision_id: str) -> str:
    return hashlib.sha256(f"robinhood|{account_id}|{decision_id}".encode()).hexdigest()


def _ref(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, key))


def _fresh_quote(transport: RobinhoodOrderTransport, asset_class: str, symbol: str) -> Quote:
    if asset_class == "equity":
        quotes = transport.adapter.get_quotes([symbol])
        if len(quotes) != 1 or quotes[0].symbol != symbol:
            raise ValueError("equity_quote_unavailable")
        return quotes[0]
    quotes = transport.adapter.get_crypto_quotes([symbol])
    if len(quotes) != 1 or not quotes[0]["valid_for_execution"]:
        raise ValueError("crypto_quote_not_executable")
    q = quotes[0]
    import datetime as dt
    ts = dt.datetime.fromisoformat(q["as_of"].replace("Z", "+00:00")).timestamp()
    return Quote(provider="robinhood_mcp", symbol=symbol, timestamp=ts,
                 age_seconds=q["age_seconds"], bid=q["bid"], ask=q["ask"],
                 last=q["mark"], market_status="open")


def _order_args(symbol: str, quantity: float) -> dict:
    return {"symbol": symbol, "side": "buy", "quantity": quantity,
            "order_type": "market"}


def submit_validated_entry(db, transport: RobinhoodOrderTransport, cfg, *,
                           raw_signal: dict, asset_class: str,
                           avg_dollar_volume: float, sector: str | None,
                           daily_pnl_pct: float, weekly_drawdown_pct: float,
                           total_drawdown_pct: float) -> EntryResult:
    """Submit one fully checked long entry; never retries an uncertain send."""
    try:
        signal = SignalSchema(**raw_signal)
    except ValidationError:
        return EntryResult("blocked", "invalid_signal")
    if asset_class not in {"equity", "crypto"} or signal.direction != "long":
        return EntryResult("blocked", "unsupported_asset_or_direction")
    if not signal.strategy.startswith(f"robinhood-{asset_class}-"):
        return EntryResult("blocked", "wrong_strategy_asset_class")
    validation = db.get(StrategyValidationRecord, signal.strategy)
    if validation is None or validation.passed is not True:
        return EntryResult("blocked", "strategy_not_validated")
    readiness = db.get(RobinhoodStrategyReadiness, signal.strategy)
    if (readiness is None or readiness.asset_class != asset_class or
            readiness.simulated_lifecycle_passed is not True or readiness.enabled is not True):
        return EntryResult("blocked", "robinhood_strategy_not_enabled")
    if (asset_class == "equity" and not transport.allow_equity or
            asset_class == "crypto" and not transport.allow_crypto):
        return EntryResult("blocked", "broker_asset_execution_disabled")
    allowed, why = StateManager(db, cfg).live_broker_mutation_allowed()
    if not allowed:
        return EntryResult("blocked", why)
    account_id = transport.adapter.designated_account_id
    key = _key(account_id, signal.decision_id)
    if db.get(OrderIntent, key) is not None:
        return EntryResult("blocked", "duplicate_decision")
    if db.query(OrderIntent).filter(OrderIntent.account_id == account_id,
                                    OrderIntent.status.in_(["preparing", "submitting", "unknown"])).first():
        return EntryResult("blocked", "unresolved_order_intent")
    # All open orders and both asset-class positions share the Agentic account.
    positions = transport.adapter.get_positions() + transport.adapter.get_crypto_positions()
    if len(positions) >= cfg.MAX_POSITIONS:
        return EntryResult("blocked", "max_positions_reached")
    orders = transport.adapter.get_orders() + transport.adapter.get_crypto_orders()
    if any(str(o.get("state") or o.get("status") or "").lower() in OPEN_ORDER_STATES for o in orders):
        return EntryResult("blocked", "existing_open_broker_order")
    try:
        quote = _fresh_quote(transport, asset_class, signal.symbol)
        if (quote.ask <= 0 or abs(signal.entry_price - quote.ask) / quote.ask > 0.005 or
                (asset_class == "equity" and quote.market_status != "open")):
            return EntryResult("blocked", "entry_price_or_market_status_changed")
        balances = transport.adapter.get_balances()
        equity = float(balances["equity"])
        buying_power = (transport.adapter.get_buying_power() if asset_class == "equity"
                        else transport.adapter.get_crypto_buying_power())
        if not all(isfinite(v) for v in (equity, buying_power)) or equity <= 0 or buying_power <= 0:
            return EntryResult("blocked", "account_unfunded_or_invalid")
    except (ValueError, KeyError, TypeError):
        return EntryResult("blocked", "market_or_account_data_unavailable")
    risk = RiskEngine(cfg).evaluate(TradeProposal(
        symbol=signal.symbol, direction="long", entry_price=signal.entry_price,
        stop_price=signal.stop_price, quote=quote, strategy=signal.strategy,
        account_equity=equity, avg_dollar_volume=avg_dollar_volume,
        sector=sector, open_position_count=len(positions),
        daily_pnl_pct=daily_pnl_pct, weekly_drawdown_pct=weekly_drawdown_pct,
        total_drawdown_pct=total_drawdown_pct))
    if not risk.approved:
        return EntryResult("blocked", ",".join(risk.reasons))
    quantity = (float(floor(risk.position_size)) if asset_class == "equity"
                else floor(risk.position_size * 1e8) / 1e8)
    if quantity <= 0:
        return EntryResult("blocked", "unprotectable_or_too_small")
    reservation = risk_budget.reserve(
        db, account_id=account_id, decision_id=signal.decision_id,
        risk_dollars=quantity * abs(signal.entry_price - signal.stop_price),
        notional=quantity * signal.entry_price, account_equity=equity,
        buying_power=buying_power, sector=sector, cfg=cfg)
    if not reservation.approved:
        return EntryResult("blocked", reservation.reason)
    intent = OrderIntent(intent_key=key, decision_id=signal.decision_id,
                         account_id=account_id, symbol=signal.symbol, side="buy",
                         quantity=quantity, status="preparing")
    trade = TradeDecisionRecord(symbol=signal.symbol, asset_class=asset_class,
                                strategy=signal.strategy, direction="long",
                                entry_thesis=signal.thesis, technical_conditions=signal.technical_conditions,
                                entry_price=signal.entry_price, stop_price=signal.stop_price,
                                target_price=signal.target_price, position_size=quantity,
                                risk_dollars=quantity * abs(signal.entry_price - signal.stop_price),
                                risk_engine_result={"approved": True, "reasons": []}, status="open")
    db.add_all([intent, trade])
    db.commit()
    intent.trade_id = trade.trade_id
    db.commit()
    preview = transport.preview_equity if asset_class == "equity" else transport.preview_crypto
    submit = transport.submit_equity if asset_class == "equity" else transport.submit_crypto
    order = _order_args(signal.symbol, quantity)
    try:
        trade.order_preview = preview(**order)
        if not isinstance(trade.order_preview, dict) or trade.order_preview.get("errors") or trade.order_preview.get("rejected"):
            intent.status = "rejected"
            trade.status = "rejected"
            risk_budget.release(db, reservation.reservation_id)
            db.commit()
            return EntryResult("blocked", "broker_preview_rejected", trade.trade_id)
        # State, quote, and buying power are checked again after the network preview.
        allowed, why = StateManager(db, cfg).live_broker_mutation_allowed()
        if not allowed:
            raise ValueError(why)
        _fresh_quote(transport, asset_class, signal.symbol)
        current_bp = (transport.adapter.get_buying_power() if asset_class == "equity"
                      else transport.adapter.get_crypto_buying_power())
        if current_bp < quantity * quote.ask:
            raise ValueError("buying_power_changed")
    except Exception as exc:
        intent.status = "rejected"
        trade.status = "rejected"
        risk_budget.release(db, reservation.reservation_id)
        db.commit()
        return EntryResult("blocked", f"pre_submission_check_failed:{type(exc).__name__}", trade.trade_id)
    claimed = db.query(OrderIntent).filter(OrderIntent.intent_key == key,
                                           OrderIntent.status == "preparing").update(
        {"status": "submitting"}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        return EntryResult("blocked", "entry_intent_changed_before_send", trade.trade_id)
    db.commit()
    try:
        result = submit(ref_id=_ref(key), **order)
        order_id = str(result.get("id") or result.get("order_id") or "")
        if not order_id:
            raise ValueError("broker_order_id_missing")
    except Exception:
        intent.status = "unknown"
        db.commit()
        return EntryResult("unknown", "broker_submission_uncertain", trade.trade_id)
    intent.status = "submitted"
    intent.broker_order_id = order_id
    trade.order_id = order_id
    db.commit()
    record_entry(db, trade_id=trade.trade_id, account_id=account_id,
                 asset_class=asset_class, symbol=signal.symbol, quantity=quantity,
                 stop_price=signal.stop_price, entry_order_id=order_id)
    return EntryResult("submitted", "broker_order_recorded", trade.trade_id, order_id)


def recover_uncertain_entry(db, transport: RobinhoodOrderTransport, intent_key: str) -> EntryResult:
    """Read broker history by stable ref; never resubmit the entry."""
    intent = db.get(OrderIntent, intent_key)
    if intent is None or intent.status not in {"submitting", "unknown", "submitted"}:
        return EntryResult("blocked", "no_uncertain_entry")
    trade = db.get(TradeDecisionRecord, intent.trade_id)
    if trade is None or not trade.strategy.startswith(f"robinhood-{trade.asset_class}-"):
        return EntryResult("blocked", "trade_record_mismatch")
    if intent.account_id != transport.adapter.designated_account_id:
        return EntryResult("blocked", "wrong_agentic_account")
    if not intent.broker_order_id:
        found = transport.find_order_by_ref(trade.asset_class, _ref(intent_key))
        if found is None:
            return EntryResult("unknown", "broker_reference_not_yet_found", trade.trade_id)
        intent.broker_order_id = str(found.get("id") or found.get("order_id") or "")
        if not intent.broker_order_id:
            return EntryResult("unknown", "broker_order_id_missing", trade.trade_id)
    trade.order_id = intent.broker_order_id
    intent.status = "submitted"
    db.commit()
    from app.models.models import RobinhoodTradeLifecycle
    if db.get(RobinhoodTradeLifecycle, trade.trade_id) is None:
        record_entry(db, trade_id=trade.trade_id, account_id=intent.account_id,
                     asset_class=trade.asset_class, symbol=trade.symbol,
                     quantity=intent.quantity, stop_price=trade.stop_price,
                     entry_order_id=intent.broker_order_id)
    return EntryResult("submitted", "broker_order_recovered", trade.trade_id,
                       intent.broker_order_id)
