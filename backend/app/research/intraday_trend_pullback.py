"""Research-only 5-minute liquid-market pullback evaluator.

Entries use only a completed bar and execute at the next bar open.  This is a
hypothesis generator, not a live signal or an execution module.
"""
from __future__ import annotations

from dataclasses import dataclass

STRATEGY_VERSION = "intraday-liquid-trend-pullback-portfolio-v2"
UNIVERSE = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "GLD", "AAPL", "AMD", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "NVDA", "ORCL", "PLTR", "TSLA", "V")
WARMUP_BARS, STOP_LOSS, TAKE_PROFIT, COST = 20, .0075, .015, .0004

@dataclass(frozen=True)
class Trade:
    symbol: str; entry_timestamp: str; exit_timestamp: str; applied_return: float; exit_reason: str

def evaluate(bars_by_symbol: dict[str, list[dict]]) -> list[Trade]:
    """One-account evaluator: one position, next-bar entry, daily loss lockout."""
    indexed={s:{str(r['timestamp']):(i,r) for i,r in enumerate(rows)} for s,rows in bars_by_symbol.items()}
    dates=sorted(set.intersection(*(set(v) for v in indexed.values())))
    trades=[]; open_trade=None; day=None; daily_pnl=0.0
    for stamp in dates:
        if day != stamp[:10]: day,daily_pnl=stamp[:10],0.0
        if open_trade:
            symbol,entry,stop,target,entered=open_trade; row=indexed[symbol][stamp][1]
            if float(row['low'])<=stop or float(row['high'])>=target:
                raw=(stop if float(row['low'])<=stop else target)/entry-1-COST
                trades.append(Trade(symbol,entered,stamp,raw,'stop' if raw<0 else 'target')); daily_pnl+=raw; open_trade=None
            continue
        if daily_pnl <= -0.015: continue
        candidates=[]
        for symbol,rows in bars_by_symbol.items():
            i,row=indexed[symbol][stamp]
            if i < WARMUP_BARS or i+1 >= len(rows): continue
            sma=sum(float(x['close']) for x in rows[i-19:i+1])/20; high=max(float(x['high']) for x in rows[i-4:i+1]); pull=float(row['close'])/high-1
            if float(row['close'])>sma and pull<=-.003: candidates.append((pull,symbol,i))
        if candidates:
            _,symbol,i=min(candidates); entry=float(bars_by_symbol[symbol][i+1]['open'])
            open_trade=(symbol,entry,entry*(1-STOP_LOSS),entry*(1+TAKE_PROFIT),str(bars_by_symbol[symbol][i+1]['timestamp']))
    return trades
