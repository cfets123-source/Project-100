"""Read-only broker polling for emergency exits while the live worker is halted."""
from __future__ import annotations

import argparse
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.runtime.alpaca_live_emergency_exit import reconcile_emergency_exits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    while True:
        with Session(engine) as db:
            print(reconcile_emergency_exits(db, cfg), flush=True)
        if args.once:
            return 0
        time.sleep(max(60.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
