"""Read-only broker preflight for the exact monthly ETF paper strategy.

This module cannot submit or cancel an order. A separate, exclusive paper
worker must own durable intents, the account breaker, and exit reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from app.research.monthly_etf_time_series_momentum_v3 import UNIVERSE
from app.strategies.monthly_etf_tsm_v3_paper import PaperPlan, entry_order, entry_plan

OPEN = {"new", "pending_new", "accepted", "pending", "open", "partially_filled",
        "accepted_for_bidding", "held", "stopped", "suspended", "calculated"}


@dataclass(frozen=True)
class Preflight:
    ready: bool
    reason: str
    plan: PaperPlan | None = None
    order_preview: dict | None = None


def check(adapter, *, asof_day: str, capital_cap: float,
          account_breaker_clear: bool, today_day: str | None = None) -> Preflight:
    if not getattr(adapter, "paper", False) or getattr(adapter, "allow_order_submission", True):
        raise RuntimeError("ETF preflight requires a read-only paper adapter")
    if not account_breaker_clear:
        return Preflight(False, "account_breaker_state_unverified_or_active")
    if not isfinite(capital_cap) or capital_cap <= 0:
        return Preflight(False, "invalid_capital_cap")
    current_day = today_day or datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    if asof_day != current_day:
        return Preflight(False, "asof_day_not_current_market_day")
    clock = adapter.get_market_clock()
    if not clock.get("is_open"):
        return Preflight(False, "regular_market_closed")
    account = adapter.get_account_capabilities()
    if (account.get("status") != "ACTIVE" or any(account.get(field) for field in
            ("trading_blocked", "trade_suspended_by_user", "account_blocked"))):
        return Preflight(False, "paper_account_not_tradable")
    if adapter.get_positions():
        return Preflight(False, "paper_account_has_position")
    if any(str(order.get("status")) in OPEN for order in adapter.get_orders()):
        return Preflight(False, "paper_account_has_active_order")
    day = date.fromisoformat(asof_day)
    calendar = adapter.get_market_calendar((day - timedelta(days=45)).isoformat(), asof_day)
    sessions = [str(row["date"])[:10] for row in calendar]
    if asof_day not in sessions:
        return Preflight(False, "not_a_trading_session")
    raw = adapter.get_daily_bars_many(list(UNIVERSE),
                                       (day - timedelta(days=520)).isoformat(),
                                       asof_day, adjustment="raw")
    signal = adapter.get_daily_bars_many(list(UNIVERSE),
                                          (day - timedelta(days=520)).isoformat(),
                                          asof_day, adjustment="split")
    plan = entry_plan(raw, signal, raw_adjustment="raw",
                      signal_adjustment="split", asof_day=asof_day,
                      session_days=sessions)
    if plan.reason != "eligible":
        return Preflight(False, plan.reason, plan)
    quotes = {quote.symbol: quote for quote in adapter.get_quotes(list(plan.ranked_symbols))}
    asks = {}
    for symbol, quote in quotes.items():
        mid = (quote.bid + quote.ask) / 2
        if (quote.age_seconds <= 5 and 0 < quote.bid <= quote.ask and
                mid > 0 and (quote.ask - quote.bid) / mid <= .01):
            asks[symbol] = quote.ask
    assets = {item["symbol"] for item in adapter.list_active_assets(asset_class="us_equity")
              if item.get("tradable")}
    cash = adapter.get_balances()["cash"]
    order = entry_order(plan, asks=asks, tradable=assets,
                        settled_cash=cash, capital_cap=capital_cap)
    if order is None:
        return Preflight(False, "no_fresh_affordable_tradable_quote", plan)
    return Preflight(True, "paper_order_preview_ready", plan,
                     {"symbol": order.symbol, "quantity": order.quantity,
                      "side": order.side, "order_class": order.order_class,
                      "time_in_force": order.time_in_force,
                      "stop_loss_price": order.stop_loss_price,
                      "client_order_id": order.client_order_id})
