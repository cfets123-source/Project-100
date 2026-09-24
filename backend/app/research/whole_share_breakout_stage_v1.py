"""Frozen $100-to-$500 screen: whole-share breakout with an overnight stop.

Research only. Daily OHLC cannot establish executable stop fills or order
acceptance, and this model must never be used as a live execution adapter.
"""
from __future__ import annotations

UNIVERSE = ("F", "SOFI")
STARTING_EQUITY = 100.0
LOOKBACK = 20
VOLUME_MULTIPLE = 1.5
STOP_FRACTION = .04
TARGET_FRACTION = .08
MAX_SESSIONS = 10
ROUND_TRIP_COST = .001


def simulate(bars_by_symbol: dict[str, list[dict]], start: str, end: str) -> dict:
    """Return the full daily account path, including cash and open positions."""
    indexed = {
        symbol: {row["timestamp"][:10]: row for row in bars_by_symbol[symbol]}
        for symbol in UNIVERSE
    }
    dates = sorted(set.intersection(*(set(rows) for rows in indexed.values())))
    dates = [day for day in dates if start <= day <= end]
    cash = STARTING_EQUITY
    position = None
    pending = None
    equity_path = []
    trades = []
    for index, day in enumerate(dates):
        if index < LOOKBACK:
            equity_path.append((day, cash))
            continue
        if pending and position is None:
            symbol = pending
            entry = float(indexed[symbol][day]["open"])
            qty = int(cash // entry) if entry > 0 else 0
            if qty:
                cash -= qty * entry
                position = {"symbol": symbol, "entry": entry, "qty": qty,
                            "stop": entry * (1 - STOP_FRACTION),
                            "target": entry * (1 + TARGET_FRACTION), "days": 0}
            pending = None
        if position:
            row = indexed[position["symbol"]][day]
            opening, low, high, closing = (float(row[k]) for k in ("open", "low", "high", "close"))
            position["days"] += 1
            exit_price = reason = None
            if opening <= position["stop"]:
                exit_price, reason = opening, "stop_gap"
            elif low <= position["stop"]:
                exit_price, reason = position["stop"], "stop"
            elif opening >= position["target"]:
                exit_price, reason = position["target"], "target_gap"
            elif high >= position["target"]:
                exit_price, reason = position["target"], "target"
            elif position["days"] >= MAX_SESSIONS:
                exit_price, reason = closing, "time"
            if exit_price is not None:
                gross = position["qty"] * exit_price
                fee = position["qty"] * position["entry"] * ROUND_TRIP_COST
                cash += gross - fee
                trades.append({"date": day, "symbol": position["symbol"],
                               "reason": reason, "pnl": gross - position["qty"] * position["entry"] - fee})
                position = None
        mark = cash + (position["qty"] * float(indexed[position["symbol"]][day]["close"]) if position else 0)
        equity_path.append((day, mark))
        if position or index + 1 >= len(dates):
            continue
        candidates = []
        for symbol in UNIVERSE:
            history = [indexed[symbol][d] for d in dates[index-LOOKBACK:index]]
            row = indexed[symbol][day]
            close = float(row["close"])
            high = max(float(x["high"]) for x in history)
            average_volume = sum(float(x["volume"]) for x in history) / LOOKBACK
            if high > 0 and close > high and float(row["volume"]) >= VOLUME_MULTIPLE * average_volume:
                candidates.append((close / high - 1, symbol))
        if candidates:
            pending = sorted(candidates, key=lambda item: (-item[0], item[1]))[0][1]
    peak = STARTING_EQUITY
    drawdown = 0.0
    for _, equity in equity_path:
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    final_equity = equity_path[-1][1] if equity_path else STARTING_EQUITY
    return {"start": start, "end": end, "final_equity": final_equity,
            "hit_500": any(equity >= 500 for _, equity in equity_path),
            "trades": len(trades), "max_drawdown": drawdown,
            "daily_equity": equity_path, "trade_log": trades}
