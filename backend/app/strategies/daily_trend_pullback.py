"""Runtime signal for the validated daily trend-pullback portfolio."""
from __future__ import annotations

import datetime as dt
import time
import uuid

from app.research.daily_trend_portfolio import (
    STOP_LOSS, STRATEGY_VERSION, TAKE_PROFIT, UNIVERSE, WARMUP_BARS,
)
from app.runtime.market_research_worker import EXPANDED_LIQUID_EQUITY_UNIVERSE

BROAD_STRATEGY_VERSION = "daily-trend-pullback-broad-equity-etf-v1"
BROAD_UNIVERSE = UNIVERSE + (
    "AAPL", "AMD", "AMZN", "AVGO", "BRK.B", "COST", "GOOGL", "JPM", "LLY", "META",
    "MSFT", "NFLX", "NVDA", "ORCL", "PANW", "PLTR", "TSLA", "UNH", "V", "WMT",
)


class DailyTrendPullback:
    """One-position, once-per-day selector matching the research hypothesis."""

    name = STRATEGY_VERSION
    universe = UNIVERSE

    def portfolio_signal(self, adapter, symbols: list[str] | tuple[str, ...] | None = None) -> dict | None:
        symbols = tuple(symbols or self.universe)
        end = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
        start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
        candidates: list[tuple[float, str, float, float, float]] = []
        for symbol in symbols:
            bars = adapter.get_daily_bars(symbol, start, end)
            if len(bars) < WARMUP_BARS:
                continue
            close = float(bars[-1]["close"])
            sma50 = sum(float(row["close"]) for row in bars[-50:]) / 50
            high5 = max(float(row["high"]) for row in bars[-5:])
            pullback = close / high5 - 1
            if close > sma50 and pullback <= -0.015:
                candidates.append((pullback, symbol, close, sma50, high5))
        if not candidates:
            return None
        # The strongest pullback can temporarily have a stale broker quote.
        # Skip it rather than returning a non-executable signal and preventing
        # the portfolio selector from considering the next valid candidate.
        for pullback, symbol, close, sma50, high5 in sorted(candidates):
            quote = next((item for item in adapter.get_quotes([symbol]) if item.symbol == symbol), None)
            if quote is None or quote.last <= 0:
                continue
            quote_age = max(float(quote.age_seconds), time.time() - float(quote.timestamp))
            if quote_age > 15.0:
                continue
            if quote.bid <= 0 or quote.ask <= 0:
                continue
            mid = (quote.bid + quote.ask) / 2
            if mid <= 0 or (quote.ask - quote.bid) / mid > 0.01:
                continue
            entry = quote.last
            day = dt.datetime.now(dt.UTC).date().isoformat()
            return {
                "symbol": symbol, "direction": "long", "strategy": self.name,
                "decision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.name}:{day}:{symbol}")),
                "entry_price": entry, "stop_price": round(entry * (1 - STOP_LOSS), 4),
                "target_price": round(entry * (1 + TAKE_PROFIT), 4),
                "thesis": "daily trend pullback above 50-day trend",
                "technical_conditions": {"close": close, "sma50": sma50,
                                         "five_day_high": high5, "pullback_pct": pullback * 100,
                                         "quote_age_seconds": quote_age,
                                         "spread_pct": (quote.ask - quote.bid) / mid * 100},
                "ai_confidence": None,
            }
        return None


class BroadDailyTrendPullback(DailyTrendPullback):
    """The independently validated broad liquid-equity and ETF variant."""
    name = BROAD_STRATEGY_VERSION
    universe = BROAD_UNIVERSE


EXPANDED_STRATEGY_VERSION = "daily-trend-pullback-expanded-equity-etf-v1"


class ExpandedDailyTrendPullback(BroadDailyTrendPullback):
    """Paper-only strategy matching the separately evaluated 79-name universe."""
    name = EXPANDED_STRATEGY_VERSION
    universe = UNIVERSE + EXPANDED_LIQUID_EQUITY_UNIVERSE


PORTFOLIO_BROAD_STRATEGY_VERSION = "daily-trend-pullback-broad-portfolio-v2"


class BroadDailyTrendPullbackPortfolioV2(BroadDailyTrendPullback):
    """Paper-research portfolio candidate selector.

    It deliberately has a new strategy version.  Its two-position behavior is
    not inherited by the validated one-position strategy or its live worker.
    """
    name = PORTFOLIO_BROAD_STRATEGY_VERSION
    max_concurrent_positions = 2

    def portfolio_signals(self, adapter, symbols: list[str] | tuple[str, ...] | None = None,
                          *, limit: int | None = None) -> list[dict]:
        symbols = tuple(symbols or self.universe)
        end = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
        start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
        candidates: list[tuple[float, str]] = []
        for symbol in symbols:
            bars = adapter.get_daily_bars(symbol, start, end)
            if len(bars) < WARMUP_BARS:
                continue
            close = float(bars[-1]["close"])
            sma50 = sum(float(row["close"]) for row in bars[-50:]) / 50
            high5 = max(float(row["high"]) for row in bars[-5:])
            pullback = close / high5 - 1
            if close > sma50 and pullback <= -0.015:
                candidates.append((pullback, symbol))
        signals: list[dict] = []
        day = dt.datetime.now(dt.UTC).date().isoformat()
        for _, symbol in sorted(candidates):
            quote = next((item for item in adapter.get_quotes([symbol]) if item.symbol == symbol), None)
            if quote is None or quote.last <= 0 or quote.bid <= 0 or quote.ask <= 0:
                continue
            quote_age = max(float(quote.age_seconds), time.time() - float(quote.timestamp))
            mid = (quote.bid + quote.ask) / 2
            if quote_age > 15.0 or mid <= 0 or (quote.ask - quote.bid) / mid > 0.01:
                continue
            entry = quote.last
            signals.append({
                "symbol": symbol, "direction": "long", "strategy": self.name,
                "decision_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.name}:{day}:{symbol}")),
                "entry_price": entry, "stop_price": round(entry * (1 - STOP_LOSS), 4),
                "target_price": round(entry * (1 + TAKE_PROFIT), 4),
                "thesis": "daily trend pullback above 50-day trend; portfolio candidate",
                "ai_confidence": None,
            })
            if len(signals) >= (limit or self.max_concurrent_positions):
                break
        return signals
