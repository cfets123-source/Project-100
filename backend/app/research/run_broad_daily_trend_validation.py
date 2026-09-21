"""Evaluate daily trend-pullback selection across liquid equities and ETFs."""
from __future__ import annotations

import argparse
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.daily_trend_portfolio import UNIVERSE as ETF_UNIVERSE, evaluate
from app.research.strategy_validation import assess_out_of_sample, record_validation
from app.runtime.market_research_worker import LIQUID_EQUITY_UNIVERSE


STRATEGY_VERSION = "daily-trend-pullback-broad-equity-etf-v1"
UNIVERSE = ETF_UNIVERSE + LIQUID_EQUITY_UNIVERSE


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
            raise RuntimeError("research requires the paper/read-only data credential")
        data = {symbol: adapter.get_daily_bars(symbol, args.start, args.end) for symbol in UNIVERSE}
        trades = evaluate(data, split=args.split)
        result = assess_out_of_sample([trade.applied_return for trade in trades])
        record_validation(db, strategy=STRATEGY_VERSION, result=result,
                          sample_start=dt.datetime.fromisoformat(args.split.replace("Z", "+00:00")),
                          sample_end=dt.datetime.fromisoformat(args.end.replace("Z", "+00:00")))
        print({"strategy": STRATEGY_VERSION, "paper_data": paper, "universe_size": len(UNIVERSE),
               "trades": result.trades, "win_rate": result.win_rate,
               "total_return": result.total_return, "max_drawdown": result.max_drawdown,
               "passed": result.passed, "reasons": result.reasons})
        return 0 if result.passed else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
