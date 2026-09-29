"""Stage Runner v1 worker (paper or live).

Both modes reuse the existing guarded cycles; this module only supplies the
strategy and its owner-accepted bounds.  Live requires, in addition to the
owner acceptance row: live state, LIVE_TRADING_ENABLED, read-only verification,
ALPACA_BRACKET_TIME_IN_FORCE=gtc and WHOLE_SHARES_ONLY=true.
"""
from __future__ import annotations

import argparse
import time

from app.audit.logger import log_and_commit
from app.services.owner_experiment import require_owner_experiment
from app.strategies.stage_runner import STAGE_RUNNER_VERSION, TRADE_SYMBOL, StageRunner


def required_settings_problem(cfg) -> str | None:
    if str(getattr(cfg, "ALPACA_BRACKET_TIME_IN_FORCE", "day")).lower() != "gtc":
        return "stage_runner_requires_gtc_brackets"
    if not getattr(cfg, "WHOLE_SHARES_ONLY", False):
        return "stage_runner_requires_whole_shares"
    return None


def build_strategy(db, *, mode: str, cfg) -> StageRunner:
    record = require_owner_experiment(db, STAGE_RUNNER_VERSION)
    override = float(cfg.STARTING_CAPITAL) if mode == "paper" else None
    return StageRunner(max_equity=record.max_equity, floor_equity=record.floor_equity,
                       equity_override=override)


def run_once(db, cfg, *, mode: str, account_id: str | None = None) -> dict:
    problem = required_settings_problem(cfg)
    if problem:
        log_and_commit(db, "stage_runner_blocked", {"reason": problem})
        return {"entries": [], "reason": problem}
    try:
        strategy = build_strategy(db, mode=mode, cfg=cfg)
    except RuntimeError as exc:
        return {"entries": [], "reason": str(exc)}
    if mode == "live":
        from app.runtime.alpaca_live_worker import run_cycle
        result = run_cycle(db, cfg, strategy=strategy, symbols=(TRADE_SYMBOL,))
    else:
        from app.runtime.alpaca_paper_execution_worker import run_cycle
        result = run_cycle(db, cfg, account_id, [TRADE_SYMBOL], strategy=strategy,
                           state_id="stage-runner-paper-1")
    if strategy.last_skip:
        result = {**result, "strategy_skip": strategy.last_skip}
    return result


def main() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.brokers.alpaca_adapter import AlpacaBrokerError
    from app.core.config import Settings
    from app.db.session import initialize_schema

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--mode", choices=("paper", "live"), required=True)
    parser.add_argument("--account-id", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=60.0)
    args = parser.parse_args()
    if args.mode == "paper" and not args.account_id:
        parser.error("--account-id is required in paper mode")
    cfg = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)

    def cycle():
        with Session(engine) as db:
            try:
                result = run_once(db, cfg, mode=args.mode, account_id=args.account_id)
            except AlpacaBrokerError as exc:
                log_and_commit(db, "stage_runner_broker_error", {"error": type(exc).__name__})
                result = {"entries": [], "reason": "broker_error"}
            print({"strategy": STAGE_RUNNER_VERSION, "mode": args.mode, **result}, flush=True)

    if args.mode == "live":
        from app.runtime.alpaca_live_worker_lock import exclusive_live_worker
        lock = exclusive_live_worker(args.database)
    else:
        from contextlib import nullcontext
        lock = nullcontext()
    with lock:
        while True:
            cycle()
            if args.once:
                break
            time.sleep(max(15.0, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
