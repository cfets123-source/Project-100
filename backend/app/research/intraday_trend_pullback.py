"""Research-only 5-minute liquid-market pullback evaluator.

Entries use only a completed bar and execute at the next bar open.  This is a
hypothesis generator, not a live signal or an execution module.
"""
from __future__ import annotations

from dataclasses import dataclass

STRATEGY_VERSION = "intraday-liquid-trend-pullback-v1"
UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "NVDA", "ORCL", "PLTR", "TSLA", "V")
WARMUP_BARS, STOP_LOSS, TAKE_PROFIT, COST = 20, .0075, .015, .0004

@dataclass(frozen=True)
class Trade:
    symbol: str; entry_timestamp: str; exit_timestamp: str; applied_return: float; exit_reason: str

def evaluate(bars_by_symbol: dict[str, list[dict]]) -> list[Trade]:
    """One position at a time, next-bar entry, adverse-stop ordering."""
    trades: list[Trade] = []
    for symbol, bars in bars_by_symbol.items():
        open_trade = None
        for i in range(WARMUP_BARS, len(bars) - 1):
            row = bars[i]
            if open_trade:
                entry, stop, target, entered = open_trade
                if float(row["low"]) <= stop:
                    trades.append(Trade(symbol, entered, str(row["timestamp"]), stop / entry - 1 - COST, "stop")); open_trade = None
                elif float(row["high"]) >= target:
                    trades.append(Trade(symbol, entered, str(row["timestamp"]), target / entry - 1 - COST, "target")); open_trade = None
                continue
            sma20 = sum(float(x["close"]) for x in bars[i-19:i+1]) / 20
            high5 = max(float(x["high"]) for x in bars[i-4:i+1])
            pullback = float(row["close"]) / high5 - 1
            if float(row["close"]) > sma20 and pullback <= -.003:
                entry = float(bars[i+1]["open"])
                open_trade = (entry, entry*(1-STOP_LOSS), entry*(1+TAKE_PROFIT), str(bars[i+1]["timestamp"]))
    return sorted(trades, key=lambda x: x.entry_timestamp)
