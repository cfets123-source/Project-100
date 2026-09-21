"""Read-only scheduled research scan for the live-supported equity/ETF universe."""
from __future__ import annotations

import datetime as dt

from app.audit.logger import log_and_commit
from app.markets.research_scanner import rank_research_candidates


RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "TLT")


def run_scan(db, adapter, *, symbols: tuple[str, ...] = RESEARCH_UNIVERSE) -> list[dict]:
    """Collect completed daily observations and persist research-only rankings."""
    end = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
    start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
    observations = []
    for symbol in symbols:
        bars = adapter.get_daily_bars(symbol, start, end)
        if len(bars) < 50:
            observations.append({"symbol": symbol, "asset_class": "etf", "market_data_ready": False,
                                 "avg_dollar_volume": 0}); continue
        close = float(bars[-1]["close"])
        sma50 = sum(float(row["close"]) for row in bars[-50:]) / 50
        momentum = close / float(bars[-21]["close"]) - 1.0
        observations.append({"symbol": symbol, "asset_class": "etf", "market_data_ready": True,
                             "avg_dollar_volume": close * float(bars[-1]["volume"]),
                             "trend_score": (close / sma50) - 1.0,
                             "momentum_score": momentum})
    ranked = rank_research_candidates(observations)
    log_and_commit(db, "market_research_scan_recorded", {"symbols": list(symbols), "ranked": ranked})
    return ranked
