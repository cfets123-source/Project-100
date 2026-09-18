"""Continuous read-only Alpaca paper monitor.

This is deliberately separate from the replay worker. It establishes a durable
external-data history before an explicit paper-execution worker is permitted.
"""
import argparse
import json
import signal
import threading
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import initialize_schema
from app.brokers.alpaca_connection import load_read_only_adapter
from app.runtime.alpaca_paper_monitor import run_cycle


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--symbols", required=True, help="comma-separated equity symbols")
    p.add_argument("--interval", type=float, default=15)
    p.add_argument("--once", action="store_true")
    args = p.parse_args(argv)
    if not 5 <= args.interval <= 300:
        raise ValueError("interval must be between 5 and 300 seconds")
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        raise ValueError("at least one symbol is required")
    cfg = Settings()
    engine = create_engine(args.database, connect_args={"timeout": 10} if args.database.startswith("sqlite") else {})
    initialize_schema(engine)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        with Session(engine) as db:
            adapter, paper = load_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
            if not paper: raise RuntimeError("monitor refuses non-paper credential")
            report = run_cycle(db, adapter, cfg, symbols)
            print(json.dumps({"ready": report["ready"], "failures": report["failures"]}), flush=True)
        if args.once: return 0
        stop.wait(args.interval)

if __name__ == "__main__":
    raise SystemExit(main())
