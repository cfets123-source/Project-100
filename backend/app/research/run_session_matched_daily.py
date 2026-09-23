"""Read-only historical diagnostic for the actual fractional same-day horizon."""
from __future__ import annotations

import argparse
import json
import time as clock
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.research.session_matched_daily import evaluate_session, select_signals


def _stats(values: list[float]) -> dict:
    equity = peak = 1.0
    drawdown = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return {"trades": len(values), "return": equity - 1,
            "max_drawdown": drawdown,
            "win_rate": sum(value > 0 for value in values) / len(values) if values else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--daily-json", type=Path, required=True)
    parser.add_argument("--cache-json", type=Path, required=True)
    parser.add_argument("--start", default="2025-01-01")
    args = parser.parse_args()
    daily = json.loads(args.daily_json.read_text())
    signals = select_signals(daily, start=args.start)
    by_symbol: dict[str, set[str]] = defaultdict(set)
    for signal in signals:
        by_symbol[signal.symbol].add(signal.entry_day)
    cache = json.loads(args.cache_json.read_text()) if args.cache_json.exists() else {}
    cfg = Settings(DATABASE_URL=args.database)
    with Session(create_engine(args.database)) as db:
        adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=True)
        if not paper or adapter.allow_order_submission:
            raise RuntimeError("research requires paper read-only data credential")
        for symbol, days in sorted(by_symbol.items()):
            if symbol in cache:
                continue
            end_day = (date.fromisoformat(max(days)) + timedelta(days=1)).isoformat()
            rows = adapter.get_intraday_bars(symbol, min(days) + "T00:00:00Z",
                                             end_day + "T00:00:00Z")
            cache[symbol] = [row for row in rows if
                             row["timestamp"][:10] in days or
                             # Eastern session may be on a different UTC day.
                             (date.fromisoformat(row["timestamp"][:10]) - timedelta(days=1)).isoformat() in days]
            args.cache_json.write_text(json.dumps(cache))
            print(json.dumps({"fetched": symbol, "symbols_done": len(cache),
                              "symbols_total": len(by_symbol), "bars": len(cache[symbol])}), flush=True)
            clock.sleep(.5)
    trades = [evaluate_session(signal, cache[signal.symbol]) for signal in signals]
    missing = sum(trade is None for trade in trades)
    by_window: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        if trade is not None:
            by_window[trade.signal.entry_day[:4]].append(trade.account_return)
    print(json.dumps({"signals": len(signals), "missing_sessions": missing,
                      "yearly": {year: _stats(values) for year, values in by_window.items()},
                      "overall": _stats([trade.account_return for trade in trades if trade is not None])},
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
