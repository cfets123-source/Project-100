"""Owner-accepted experiments: bounded live/paper use of an UNVALIDATED strategy.

An acceptance row is created only by the account owner through
``python -m app.services.owner_experiment accept``.  It is separate from, and
never satisfies, ``require_passing_validation``.
"""
from __future__ import annotations

import argparse

from app.models.models import OwnerAcceptedExperiment
from app.strategies.stage_runner import STAGE_RUNNER_VERSION
from app.strategies.allocator import ALLOCATOR_VERSION

OWNER_EXPERIMENT_STRATEGIES = frozenset({STAGE_RUNNER_VERSION, ALLOCATOR_VERSION})
ACKNOWLEDGEMENT = ("I accept that this strategy has NOT passed research validation, "
                   "that the full amount at risk can be lost down to the floor, and that "
                   "historical tests do not predict future results.")


def require_owner_experiment(db, strategy: str) -> OwnerAcceptedExperiment:
    if strategy not in OWNER_EXPERIMENT_STRATEGIES:
        raise RuntimeError(f"owner_experiment_not_allowed:{strategy}")
    record = db.get(OwnerAcceptedExperiment, strategy)
    if record is None or record.revoked:
        raise RuntimeError(f"owner_experiment_not_accepted:{strategy}")
    return record


def accept(db, strategy: str, *, accepted_by: str, max_equity: float, floor_equity: float,
           acknowledgement: str) -> OwnerAcceptedExperiment:
    if strategy not in OWNER_EXPERIMENT_STRATEGIES:
        raise ValueError(f"owner_experiment_not_allowed:{strategy}")
    if acknowledgement.strip() != ACKNOWLEDGEMENT:
        raise ValueError("acknowledgement text must match exactly")
    if not 0 < floor_equity < max_equity:
        raise ValueError("require 0 < floor_equity < max_equity")
    record = db.get(OwnerAcceptedExperiment, strategy)
    if record is None:
        record = OwnerAcceptedExperiment(strategy=strategy)
        db.add(record)
    record.accepted_by, record.max_equity, record.floor_equity = accepted_by, max_equity, floor_equity
    record.acknowledgement, record.revoked = ACKNOWLEDGEMENT, False
    db.commit()
    return record


def revoke(db, strategy: str) -> None:
    record = db.get(OwnerAcceptedExperiment, strategy)
    if record is not None:
        record.revoked = True
        db.commit()


def main() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.db.session import initialize_schema

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("accept", "revoke", "show"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--strategy", default=STAGE_RUNNER_VERSION)
    parser.add_argument("--by", default="account-owner")
    parser.add_argument("--max-equity", type=float, default=250.0)
    parser.add_argument("--floor-equity", type=float, default=50.0)
    parser.add_argument("--i-accept", default="")
    args = parser.parse_args()
    engine = create_engine(args.database)
    initialize_schema(engine)
    with Session(engine) as db:
        if args.action == "accept":
            if args.i_accept.strip() != ACKNOWLEDGEMENT:
                print({"accepted": False, "required_text": ACKNOWLEDGEMENT})
                return 2
            r = accept(db, args.strategy, accepted_by=args.by, max_equity=args.max_equity,
                       floor_equity=args.floor_equity, acknowledgement=args.i_accept)
        elif args.action == "revoke":
            revoke(db, args.strategy)
        r = db.get(OwnerAcceptedExperiment, args.strategy)
        print({"strategy": args.strategy, "accepted": bool(r and not r.revoked),
               "max_equity": r and r.max_equity, "floor_equity": r and r.floor_equity})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
