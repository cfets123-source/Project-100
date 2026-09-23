"""Read-only broker polling for emergency exits while the live worker is halted."""
from __future__ import annotations

import argparse
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.brokers.alpaca_connection import load_read_only_adapter
from app.runtime.alpaca_live_emergency_exit import reconcile_emergency_exits
from app.services.reconciliation import reconcile_all_pending


def reconcile_live_entry_intents(db, cfg) -> dict:
    """Recover live entry fills and prices without constructing a writer."""
    adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, paper=False)
    if paper or adapter.paper:
        raise RuntimeError("live intent reconciliation refuses paper credential")
    accounts = adapter.get_accounts()
    if len(accounts) != 1 or not accounts[0].get("account_id"):
        raise RuntimeError("live intent reconciliation requires one account")
    account_id = str(accounts[0]["account_id"])
    resolved = reconcile_all_pending(db, adapter, account_id=account_id)
    return {"account_id": account_id, "intents_checked": len(resolved),
            "order_submission": False}


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
            print({"entries": reconcile_live_entry_intents(db, cfg),
                   "emergency_exits": reconcile_emergency_exits(db, cfg)}, flush=True)
        if args.once:
            return 0
        time.sleep(max(60.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
