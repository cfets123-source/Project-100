"""Stage Runner v1: owner-accepted, unvalidated milestone experiment.

Rule (frozen for v1):
  * Entry: account flat, QQQ's last completed daily close is above its 200-day
    simple average, and TQQQ's quote is fresh and tight.  Buy whole shares only.
  * Exit: only the broker-owned OCO bracket, stop = entry x 0.75,
    target = entry x 1.50.  Brackets must be GTC (see ALPACA_BRACKET_TIME_IN_FORCE).
  * Equity guards: no entry below ``floor_equity`` or above ``max_equity``
    (the owner-accepted experiment cap).  Milestone stages are handled by the
    existing lifecycle, not here.

This strategy has no passing research validation.  It can only execute when
the account owner has recorded an OwnerAcceptedExperiment row for its exact name.
"""
from __future__ import annotations

import datetime as dt
import time
import uuid

STAGE_RUNNER_VERSION = "stage-runner-tqqq-sma200-bracket-v1"
TRADE_SYMBOL = "TQQQ"
TREND_SYMBOL = "QQQ"
SMA_DAYS = 200
STOP_FRACTION = 0.25
TARGET_FRACTION = 0.50
MAX_QUOTE_AGE_SECONDS = 15.0
MAX_SPREAD_FRACTION = 0.005


def trend_is_up(closes: list[float], days: int = SMA_DAYS) -> tuple[bool, float | None]:
    """Last close strictly above the trailing ``days`` simple average."""
    if len(closes) < days:
        return False, None
    sma = sum(closes[-days:]) / days
    return closes[-1] > sma, sma


class StageRunner:
    name = STAGE_RUNNER_VERSION
    universe = (TRADE_SYMBOL,)

    def __init__(self, *, max_equity: float, floor_equity: float, equity_override: float | None = None):
        if not 0 < floor_equity < max_equity:
            raise ValueError("stage runner requires 0 < floor_equity < max_equity")
        self.max_equity = float(max_equity)
        self.floor_equity = float(floor_equity)
        # Paper only: size and guard from the simulated stage balance, not the
        # broker's $100k paper equity.
        self.equity_override = equity_override
        self.last_skip: dict | None = None

    def _skip(self, reason: str, **detail) -> None:
        self.last_skip = {"reason": reason, **detail}
        return None

    def portfolio_signal(self, adapter, symbols=None) -> dict | None:
        equity = (float(self.equity_override) if self.equity_override is not None
                  else float(adapter.get_balances()["equity"]))
        if equity < self.floor_equity:
            return self._skip("below_floor_equity", equity=equity)
        if equity > self.max_equity:
            return self._skip("above_experiment_cap", equity=equity)
        now = dt.datetime.now(dt.UTC)
        start = (now - dt.timedelta(days=400)).strftime("%Y-%m-%dT00:00:00Z")
        # Completed sessions only: bars end before today's UTC date.
        end = now.strftime("%Y-%m-%dT00:00:00Z")
        bars = adapter.get_daily_bars(TREND_SYMBOL, start, end)
        closes = [float(b["close"]) for b in bars]
        up, sma = trend_is_up(closes)
        if not up:
            return self._skip("trend_filter_off", close=closes[-1] if closes else None, sma200=sma)
        quote = next((q for q in adapter.get_quotes([TRADE_SYMBOL]) if q.symbol == TRADE_SYMBOL), None)
        if quote is None or quote.last <= 0 or quote.bid <= 0 or quote.ask <= 0:
            return self._skip("quote_unavailable")
        age = max(float(quote.age_seconds), time.time() - float(quote.timestamp))
        mid = (quote.bid + quote.ask) / 2
        if age > MAX_QUOTE_AGE_SECONDS:
            return self._skip("quote_stale", age=age)
        if (quote.ask - quote.bid) / mid > MAX_SPREAD_FRACTION:
            return self._skip("spread_too_wide", spread=(quote.ask - quote.bid) / mid)
        if quote.ask > equity:
            return self._skip("one_share_exceeds_equity", ask=quote.ask, equity=equity)
        entry = quote.ask
        day = now.date().isoformat()
        self.last_skip = None
        return {
            "symbol": TRADE_SYMBOL, "direction": "long", "strategy": self.name,
            "decision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.name}:{day}:{TRADE_SYMBOL}")),
            "entry_price": entry,
            "stop_price": round(entry * (1 - STOP_FRACTION), 2),
            "target_price": round(entry * (1 + TARGET_FRACTION), 2),
            "thesis": "QQQ above 200-day average; TQQQ whole-share bracket +50%/-25% (unvalidated experiment)",
            "technical_conditions": {"qqq_close": closes[-1], "qqq_sma200": sma, "equity": equity,
                                     "quote_age_seconds": age,
                                     "spread_pct": (quote.ask - quote.bid) / mid * 100},
            "ai_confidence": None,
        }
