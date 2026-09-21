"""Read-only scheduled research scan for the live-supported equity/ETF universe."""
from __future__ import annotations

import datetime as dt

from app.audit.logger import log_and_commit
from app.markets.research_scanner import rank_research_candidates


RESEARCH_UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "TLT")
LIQUID_EQUITY_UNIVERSE = (
    "AAPL", "AMD", "AMZN", "AVGO", "BRK.B", "COST", "GOOGL", "JPM", "LLY", "META",
    "MSFT", "NFLX", "NVDA", "ORCL", "PANW", "PLTR", "TSLA", "UNH", "V", "WMT",
)


def run_scan(db, adapter, *, symbols: tuple[str, ...] = RESEARCH_UNIVERSE,
             asset_class: str = "etf", event_type: str = "market_research_scan_recorded") -> list[dict]:
    """Collect completed daily observations and persist research-only rankings."""
    end = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z")
    start = (dt.datetime.now(dt.UTC) - dt.timedelta(days=180)).strftime("%Y-%m-%dT00:00:00Z")
    observations = []
    for symbol in symbols:
        bars = adapter.get_daily_bars(symbol, start, end)
        if len(bars) < 50:
            observations.append({"symbol": symbol, "asset_class": asset_class, "market_data_ready": False,
                                 "avg_dollar_volume": 0}); continue
        close = float(bars[-1]["close"])
        sma50 = sum(float(row["close"]) for row in bars[-50:]) / 50
        momentum = close / float(bars[-21]["close"]) - 1.0
        observations.append({"symbol": symbol, "asset_class": asset_class, "market_data_ready": True,
                             "avg_dollar_volume": close * float(bars[-1]["volume"]),
                             "trend_score": (close / sma50) - 1.0,
                             "momentum_score": momentum})
    ranked = rank_research_candidates(observations)
    log_and_commit(db, event_type, {"symbols": list(symbols), "asset_class": asset_class, "ranked": ranked})
    return ranked


def run_equity_scan(db, adapter, *, symbols: tuple[str, ...] = LIQUID_EQUITY_UNIVERSE) -> list[dict]:
    """Expand research coverage without changing the approved execution universe."""
    return run_scan(db, adapter, symbols=symbols, asset_class="us_equity",
                    event_type="equity_research_scan_recorded")
