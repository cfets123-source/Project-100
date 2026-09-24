"""Read-only forward option bid/ask collection for a fixed contract watchlist.

This worker has no order transport, execution flag, or strategy promotion path.
It records actual broker observations; a quote alone is not a trade signal.
"""
from __future__ import annotations

import argparse
import os
import time
from math import isfinite

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_adapter import load_agentic_read_only_adapter
from app.core.config import Settings
from app.db.session import initialize_schema
from app.models.models import RobinhoodOptionQuoteObservation


def _nonnegative_integer(value: object) -> int | None:
    if value is None:
        return None
    number = int(value)
    if number < 0 or str(number) != str(value):
        raise ValueError("Invalid option quote size or activity")
    return number


def collect_once(db: Session, adapter, option_ids: list[str]) -> dict:
    contracts = adapter.get_option_instruments_by_ids(option_ids)
    quotes = adapter.get_option_quotes(contracts)
    if len(quotes) != len(option_ids):
        raise ValueError("Incomplete option research quotes")
    inserted = 0
    for contract, quote in zip(contracts, quotes, strict=True):
        if (contract["id"] != quote["instrument_id"] or
                contract.get("state") != "active" or contract.get("tradability") != "tradable"):
            raise ValueError("Option research quote or contract mismatch")
        bid, ask = float(quote["bid"]), float(quote["ask"])
        multiplier, strike = float(quote["multiplier"]), float(quote["strike"])
        if not all(isfinite(v) for v in (bid, ask, multiplier, strike)) or multiplier <= 0 or strike <= 0:
            raise ValueError("Invalid option research price or contract")
        as_of = str(quote["as_of"])
        if db.query(RobinhoodOptionQuoteObservation).filter_by(
                option_id=contract["id"], broker_as_of=as_of).first():
            continue
        db.add(RobinhoodOptionQuoteObservation(
            option_id=contract["id"], symbol=str(quote["symbol"]),
            expiration=str(quote["expiration"]), option_type=str(quote["type"]),
            strike=strike, multiplier=multiplier, bid=bid, ask=ask,
            bid_size=_nonnegative_integer(quote.get("bid_size")),
            ask_size=_nonnegative_integer(quote.get("ask_size")),
            volume=_nonnegative_integer(quote.get("volume")),
            open_interest=_nonnegative_integer(quote.get("open_interest")),
            quality_reason=str(quote["quality_reason"]), broker_as_of=as_of))
        inserted += 1
    db.commit()
    return {"status": "observed", "contracts": len(option_ids), "new_quotes": inserted,
            "order_submission": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--interval", type=float, default=120)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    option_ids = [item.strip() for item in os.getenv("ROBINHOOD_OPTION_RESEARCH_IDS", "").split(",")
                  if item.strip()]
    if not option_ids:
        print({"status": "disabled", "reason": "no_fixed_contracts", "order_submission": False})
        return 0
    cfg = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    while True:
        try:
            with Session(engine) as db:
                adapter, _ = load_agentic_read_only_adapter(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY)
                print(collect_once(db, adapter, option_ids), flush=True)
        except Exception as exc:
            print({"status": "read_failed", "error_type": type(exc).__name__,
                   "order_submission": False}, flush=True)
        if args.once:
            break
        time.sleep(max(60, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
