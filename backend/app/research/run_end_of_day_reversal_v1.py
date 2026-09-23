"""Fetch paginated paper-market data and evaluate the frozen research rule."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.research.end_of_day_reversal_v1 import UNIVERSE, evaluate


def _stats(values: list[float]) -> dict:
    equity = peak = 1.0
    drawdown = 0.0
    for value in values:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    return {"sessions": len(values), "return": equity - 1,
            "max_drawdown": drawdown}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    cfg = Settings(DATABASE_URL=args.database)
    with Session(create_engine(args.database)) as db:
        adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=True)
        if not paper or adapter.allow_order_submission:
            raise RuntimeError("research requires paper read-only data credential")
        for symbol in UNIVERSE:
            path = args.cache_dir / f"{symbol}.json"
            if path.exists():
                continue
            bars = adapter.get_intraday_bars(symbol, args.start, args.end)
            path.write_text(json.dumps(bars))
            print(json.dumps({"fetched": symbol, "bars": len(bars)}), flush=True)
            time.sleep(.5)
    data = {symbol: json.loads((args.cache_dir / f"{symbol}.json").read_text())
            for symbol in UNIVERSE}
    baseline, stressed = evaluate(data), evaluate(data, cost=.002)
    years = sorted({day[:4] for day, _ in baseline.daily_returns})
    print(json.dumps({"trades": len(baseline.trades),
                      "missing_required_bars": baseline.missing_required_bars,
                      "overall": _stats([value for _, value in baseline.daily_returns]),
                      "cost_20bp": _stats([value for _, value in stressed.daily_returns]),
                      "yearly": {year: _stats([value for day, value in baseline.daily_returns
                                               if day.startswith(year)]) for year in years},
                      "exit_reasons": dict(Counter(trade.exit_reason
                                                   for trade in baseline.trades))},
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
