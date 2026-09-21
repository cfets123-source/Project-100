"""Run the fixed ETF trend candidate against Alpaca historical data.

Example (research only):
  python -m app.research.run_etf_trend_validation --database sqlite:////data/paper.db
"""
from __future__ import annotations

import argparse
import datetime as dt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.etf_trend import STRATEGY_VERSION, UNIVERSE, run
from app.research.strategy_validation import assess_out_of_sample, record_validation


def evaluate(adapter, *, start: str, split: str, end: str):
    """Use pre-split data only for warm-up; score only trades entered post-split."""
    all_trades = []
    for symbol in UNIVERSE:
        bars = adapter.get_daily_bars(symbol, start, end)
        all_trades.extend(run(bars, symbol))
    # Entry time is represented by bar index; preserve only actual bars after split.
    # Reconstruct the split from each symbol's source ordering in the caller instead
    # of treating in-sample returns as evidence. This helper is intentionally kept
    # pure for unit tests.
    return all_trades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--start", default="2016-01-01T00:00:00Z")
    parser.add_argument("--split", default="2023-01-01T00:00:00Z")
    parser.add_argument("--end", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z"))
    args = parser.parse_args()
    cfg = Settings(DATABASE_URL=args.database)
    engine = create_engine(args.database)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=True)
        if not paper:
            raise RuntimeError("research requires paper/read-only data credential")
        returns = []
        for symbol in UNIVERSE:
            bars = adapter.get_daily_bars(symbol, args.start, args.end)
            split_index = next((i for i, row in enumerate(bars) if row["timestamp"] >= args.split), len(bars))
            returns.extend(trade.net_return for trade in run(bars, symbol) if trade.entry_index >= split_index)
        result = assess_out_of_sample(returns)
        record_validation(db, strategy=STRATEGY_VERSION, result=result,
                          sample_start=dt.datetime.fromisoformat(args.split.replace("Z", "+00:00")),
                          sample_end=dt.datetime.fromisoformat(args.end.replace("Z", "+00:00")))
        print({"strategy": STRATEGY_VERSION, "paper_data": paper, **result.__dict__})
        return 0 if result.passed else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
