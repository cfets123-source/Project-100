"""Read-only historical check for the cash-constrained two-position candidate."""
from __future__ import annotations

import argparse
import datetime as dt
import time
from dataclasses import replace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.alpaca_connection import load_read_only_adapter
from app.core.config import Settings
from app.db.session import Base
from app.research.daily_trend_portfolio_v2 import STRATEGY_VERSION, UNIVERSE, evaluate
from app.research.strategy_validation import assess_out_of_sample, record_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--start", default="2023-01-01T00:00:00Z")
    parser.add_argument("--split", default="2025-01-01T00:00:00Z")
    parser.add_argument("--end", default=dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT00:00:00Z"))
    args = parser.parse_args()
    cfg = Settings(DATABASE_URL=args.database)
    engine = create_engine(args.database)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=True)
        if not paper:
            raise RuntimeError("portfolio research requires read-only paper data credentials")
        data = {}
        for symbol in UNIVERSE:
            data[symbol] = adapter.get_daily_bars(symbol, args.start, args.end)
            time.sleep(0.4)
        portfolio = evaluate(data, split=args.split, risk_per_trade=.01)
        aggressive = evaluate(data, split=args.split, risk_per_trade=.02)
        result = assess_out_of_sample(portfolio.daily_returns, minimum_trades=0)
        trade_count = len(portfolio.trades)
        reasons = list(result.reasons)
        if trade_count < 30:
            reasons.append("fewer than 30 completed trades")
        # Earlier broad-strategy studies already inspected this historical
        # period. Keep the exact candidate ineligible until an independent
        # forward sample and broker paper lifecycle exist.
        reasons.append("historical period previously inspected; independent forward sample required")
        promotion = replace(result, trades=trade_count,
                            win_rate=(sum(t.raw_return > 0 for t in portfolio.trades) / trade_count
                                      if trade_count else 0.0),
                            passed=False, reasons=reasons)
        record_validation(db, strategy=STRATEGY_VERSION, result=promotion,
                          sample_start=dt.datetime.fromisoformat(args.split.replace("Z", "+00:00")),
                          sample_end=dt.datetime.fromisoformat(args.end.replace("Z", "+00:00")))
        print({"strategy": STRATEGY_VERSION, "paper_data": paper,
               "historical_trades": trade_count, "max_concurrent_positions": portfolio.max_concurrent_positions,
               "modeled_portfolio_return": result.total_return,
               "modeled_max_drawdown": result.max_drawdown,
               "higher_risk_scenario": {
                   "risk_per_trade": .02,
                   "modeled_portfolio_return": assess_out_of_sample(
                       aggressive.daily_returns, minimum_trades=0).total_return,
                   "modeled_max_drawdown": assess_out_of_sample(
                       aggressive.daily_returns, minimum_trades=0).max_drawdown},
               "live_eligible": False, "reasons": reasons}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
