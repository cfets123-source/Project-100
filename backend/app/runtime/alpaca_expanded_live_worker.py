"""Isolated live route for the separately validated expanded equity/ETF strategy.

This process must replace, never overlap, the broad live worker on one account.
The compose profile and final activation flag both default to off.
"""
from __future__ import annotations

import argparse
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.alpaca_adapter import AlpacaBrokerError
from app.core.config import Settings
from app.runtime.alpaca_live_worker import run_cycle
from app.runtime.alpaca_live_worker_lock import exclusive_live_worker
from app.strategies.daily_trend_pullback import ExpandedDailyTrendPullback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=60.0)
    args = parser.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    strategy = ExpandedDailyTrendPullback()
    with exclusive_live_worker(args.database):
        while True:
            with Session(engine) as db:
                try:
                    result = run_cycle(db, cfg, strategy=strategy, symbols=strategy.universe)
                except AlpacaBrokerError as exc:
                    log_and_commit(db, "alpaca_expanded_live_worker_rate_limited",
                                   {"error": type(exc).__name__})
                    result = {"started": True, "entries": [], "reason": "broker_rate_limited"}
                print(result, flush=True)
            if args.once:
                return 0
            time.sleep(max(5.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
