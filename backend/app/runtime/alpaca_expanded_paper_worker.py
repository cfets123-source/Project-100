"""Default-off paper worker for the separately validated expanded strategy."""
from __future__ import annotations

import argparse
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.runtime.alpaca_paper_execution_worker import run_cycle
from app.strategies.daily_trend_pullback import ExpandedDailyTrendPullback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--account-id", default="alpaca-paper-expanded")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=180.0)
    args = parser.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    strategy = ExpandedDailyTrendPullback()
    while True:
        with Session(engine) as db:
            print(run_cycle(db, cfg, args.account_id, list(strategy.universe), strategy=strategy,
                            state_id="alpaca-paper-expanded-1"), flush=True)
        if args.once:
            return 0
        time.sleep(max(5.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
