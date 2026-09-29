"""Rolling, read-only option watchlist for forward bid/ask research.

Each trading day the worker picks short-dated contracts that a small account could
actually buy (ask x multiplier within a premium budget) on a fixed set of liquid
underlyings, then records their broker bid/ask every cycle. There is no order path:
a recorded quote is research evidence, never a trade signal.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time
from dataclasses import dataclass
from math import isfinite
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.robinhood_adapter import load_agentic_read_only_adapter
from app.core.config import Settings
from app.db.session import initialize_schema
from app.runtime.robinhood_option_quote_worker import collect_once

ET = ZoneInfo("America/New_York")
QUOTE_BATCH = 20
CALL_PAUSE_SECONDS = 0.25   # spread ~200 discovery lookups instead of bursting the broker
RETRIES = 3
RETRY_FAILED_SECONDS = 1800  # re-try symbols that failed discovery every 30 minutes
DEFAULT_UNDERLYINGS = ("SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL")


@dataclass(frozen=True)
class WatchlistConfig:
    underlyings: tuple[str, ...] = DEFAULT_UNDERLYINGS
    min_dte: int = 1
    max_dte: int = 14
    max_expirations: int = 2
    strikes_per_side: int = 8
    max_premium_usd: float = 100.0   # ask x multiplier, i.e. what one contract costs
    min_ask: float = 0.05
    per_underlying: int = 8


def strike_increment(spot: float) -> float:
    """Common US listing increments; strikes that do not exist simply return no contract."""
    if spot < 25:
        return 0.5
    if spot < 250:
        return 1.0
    return 5.0


def candidate_strikes(spot: float, option_type: str, count: int) -> list[float]:
    """At-the-money outward: calls step up, puts step down (cheaper, out of the money)."""
    inc = strike_increment(spot)
    atm = round(spot / inc) * inc
    sign = 1 if option_type == "call" else -1
    return [round(atm + sign * k * inc, 4) for k in range(count + 1) if atm + sign * k * inc > 0]


def pick_expirations(expirations: list[str], today: dt.date, cfg: WatchlistConfig) -> list[str]:
    valid = []
    for raw in sorted(set(expirations)):
        try:
            day = dt.date.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        if cfg.min_dte <= (day - today).days <= cfg.max_dte:
            valid.append(raw)
    return valid[:cfg.max_expirations]


def _chain_for(chains: list[dict], symbol: str) -> dict | None:
    for chain in chains:
        if chain.get("symbol", symbol) == symbol and chain.get("can_open_position", True) is not False:
            if isinstance(chain.get("id"), str) and isinstance(chain.get("expiration_dates"), list):
                return chain
    return None


def _call(fn, *args, sleep=None):
    """Broker read with pacing and bounded retries; the last error is re-raised."""
    sleep = sleep or time.sleep
    for attempt in range(RETRIES):
        try:
            result = fn(*args)
            sleep(CALL_PAUSE_SECONDS)
            return result
        except Exception:
            if attempt == RETRIES - 1:
                raise
            sleep(2 ** attempt)


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def select_underlying(adapter, symbol: str, today: dt.date, cfg: WatchlistConfig) -> list[dict]:
    """Return up to cfg.per_underlying affordable, quoted, tradable contracts for one symbol."""
    quotes = _call(adapter.get_quotes, [symbol])
    if not quotes:
        return []
    spot = (quotes[0].bid + quotes[0].ask) / 2
    chain = _chain_for(_call(adapter.get_option_chains, symbol), symbol)
    if chain is None or not isfinite(spot) or spot <= 0:
        return []
    contracts: dict[str, dict] = {}
    for expiration in pick_expirations(chain["expiration_dates"], today, cfg):
        for option_type in ("call", "put"):
            for strike in candidate_strikes(spot, option_type, cfg.strikes_per_side):
                for row in _call(adapter.get_option_instruments, chain["id"], expiration, f"{strike}", option_type):
                    if (row.get("state") == "active" and row.get("tradability") == "tradable"
                            and isinstance(row.get("id"), str)):
                        contracts[row["id"]] = row
    affordable = []
    for batch in _batches(list(contracts.values()), QUOTE_BATCH):
        for quote in _call(adapter.get_option_quotes, batch):
            cost = quote["ask"] * quote["multiplier"]
            if (quote["bid"] > 0 and quote["ask"] >= cfg.min_ask and cost <= cfg.max_premium_usd
                    and quote["quality_reason"] != "crossed_market"):
                affordable.append(quote)
    # Most traded first; then nearest to the money (highest ask within budget).
    affordable.sort(key=lambda q: (-(q.get("open_interest") or 0), -(q.get("volume") or 0), -q["ask"]))
    return [{"id": q["instrument_id"], "symbol": q["symbol"], "ask": q["ask"]}
            for q in affordable[:cfg.per_underlying]]


def build_watchlist(adapter, today: dt.date, cfg: WatchlistConfig) -> dict:
    ids: list[str] = []
    failures: dict[str, str] = {}
    per_symbol: dict[str, int] = {}
    for symbol in cfg.underlyings:
        try:
            picked = select_underlying(adapter, symbol, today, cfg)
        except Exception as exc:  # one bad underlying must not stop the others
            failures[symbol] = type(exc).__name__
            continue
        per_symbol[symbol] = len(picked)
        ids.extend(p["id"] for p in picked if p["id"] not in ids)
    return {"date": today.isoformat(), "option_ids": ids, "per_symbol": per_symbol,
            "failures": failures, "order_submission": False}


def market_open(now: dt.datetime) -> bool:
    et = now.astimezone(ET)
    return et.weekday() < 5 and dt.time(9, 31) <= et.time() <= dt.time(15, 59)


def collect_watchlist(db: Session, adapter, option_ids: list[str]) -> dict:
    """Collect in batches of 20; if a batch fails, retry its contracts one by one so a
    single expired or malformed contract cannot discard the other nineteen quotes."""
    inserted, failed = 0, []
    for batch in _batches(option_ids, QUOTE_BATCH):
        try:
            inserted += _call(collect_once, db, adapter, batch)["new_quotes"]
            continue
        except Exception:
            db.rollback()
        for option_id in batch:
            try:
                inserted += _call(collect_once, db, adapter, [option_id])["new_quotes"]
            except Exception:
                db.rollback()
                failed.append(option_id)
    return {"status": "observed", "contracts": len(option_ids), "new_quotes": inserted,
            "failed_contracts": len(failed), "failed_ids": failed, "order_submission": False}


def merge_watchlist(current: dict, rebuilt: dict) -> dict:
    """Keep contracts already chosen today and add symbols that failed earlier."""
    ids = list(current.get("option_ids", []))
    ids += [i for i in rebuilt["option_ids"] if i not in ids]
    per_symbol = {**current.get("per_symbol", {}), **rebuilt["per_symbol"]}
    return {**rebuilt, "option_ids": ids, "per_symbol": per_symbol}


def _config_from_env() -> WatchlistConfig:
    raw = os.getenv("ROBINHOOD_OPTION_WATCHLIST_UNDERLYINGS", "")
    symbols = tuple(s.strip().upper() for s in raw.split(",") if s.strip()) or DEFAULT_UNDERLYINGS
    budget = float(os.getenv("ROBINHOOD_OPTION_WATCHLIST_MAX_PREMIUM_USD", "100"))
    return WatchlistConfig(underlyings=symbols, max_premium_usd=budget)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--interval", type=float, default=120)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = _config_from_env()
    settings = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    watchlist: dict = {"date": None, "option_ids": []}
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        if args.once or market_open(now):
            try:
                with Session(engine) as db:
                    adapter, _ = load_agentic_read_only_adapter(db, settings.BROKER_TOKEN_ENCRYPTION_KEY)
                    today = now.astimezone(ET).date()
                    new_day = watchlist["date"] != today.isoformat()
                    retry_due = (watchlist.get("failures") and
                                 time.monotonic() - watchlist.get("built_at", 0) > RETRY_FAILED_SECONDS)
                    if new_day or not watchlist["option_ids"] or retry_due:
                        if new_day or not watchlist["option_ids"]:
                            watchlist = build_watchlist(adapter, today, cfg)
                        else:
                            retry_cfg = WatchlistConfig(**{**cfg.__dict__,
                                                           "underlyings": tuple(watchlist["failures"])})
                            watchlist = merge_watchlist(watchlist, build_watchlist(adapter, today, retry_cfg))
                        watchlist["built_at"] = time.monotonic()
                        print({"event": "watchlist_built", **{k: v for k, v in watchlist.items()
                                                             if k not in ("option_ids", "built_at")},
                               "contracts": len(watchlist["option_ids"])}, flush=True)
                    if watchlist["option_ids"]:
                        result = collect_watchlist(db, adapter, watchlist["option_ids"])
                        dropped = set(result.pop("failed_ids"))
                        watchlist["option_ids"] = [i for i in watchlist["option_ids"] if i not in dropped
                                                   or result["new_quotes"] == 0]
                        print(result, flush=True)
            except Exception as exc:
                print({"status": "read_failed", "error_type": type(exc).__name__,
                       "order_submission": False}, flush=True)
        if args.once:
            break
        time.sleep(max(60, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
