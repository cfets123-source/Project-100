"""All-in allocator v1 (owner-accepted, unvalidated live experiment).

Half the account follows Stage Runner's TQQQ rule (core); the other half is split
across up to five satellite positions taken from the frozen multi-market scanner
rules (trend start + 20-day breakout, all US markets). Fractional shares are used
everywhere so no cash sits idle.

Protection:
* A TQQQ lot that already carries a broker GTC bracket stays broker-managed.
* Every other lot is protected by this worker: it sells at market when the last
  price crosses the lot's stop or target, and once per day applies the rule's
  time limit / exit condition. Overnight gaps are not covered until the open.
* Circuit breaker: no new buys when equity is below 50% of its recorded peak.

The pure decision functions below take plain data so they can be tested without
a broker; the worker in runtime/allocator_worker.py does all broker I/O.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.research.multi_market_rules import RULES, group_of

ALLOCATOR_VERSION = "allocator-core-satellite-v1"
CORE_SYMBOL = "TQQQ"
CORE_WEIGHT = 0.50
SATELLITE_SLOTS = 5
SATELLITE_RULES = ("breakout", "trend")
SATELLITE_GROUPS = ("large stock", "index/sector ETF", "leveraged ETF", "bonds/commodities/intl", "crypto")
MAX_CRYPTO_SLOTS = 1  # backtest (rotc.py): capped at one crypto slot it never underperformed; uncapped did
CORE_STOP, CORE_TARGET, CORE_MAX_HOLD = 0.25, 0.50, 10_000
MIN_ORDER_USD = 1.00
CIRCUIT_BREAKER = 0.50
QTY_DECIMALS = 4
CRYPTO_QTY_DECIMALS = 8
ROTATION_MARGIN = 0.20  # weekly swap: candidate 6-mo momentum must beat the weakest holding by 20 points
ROTATION_MIN_HOLD_SESSIONS = 5  # a satellite must be held a full trading week before it can be swapped out


@dataclass(frozen=True)
class Buy:
    sleeve: str
    symbol: str
    rule: str
    notional: float
    stop_pct: float
    target_pct: float
    max_hold: int


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def floor_qty(notional: float, price: float, decimals: int = QTY_DECIMALS) -> float:
    if price <= 0:
        return 0.0
    step = 10 ** decimals
    return math.floor(notional / price * step) / step


def plan_buys(*, equity: float, cash: float, core_value: float, core_trend_up: bool,
              open_satellites: list[str], signals: list[dict], peak_equity: float,
              core_weight: float = CORE_WEIGHT, slots: int = SATELLITE_SLOTS,
              exclude: set | None = None) -> list[Buy]:
    """Decide new buys from current balances. Cash is spent core-first, then satellites."""
    if equity <= 0 or cash < MIN_ORDER_USD:
        return []
    if peak_equity > 0 and equity < peak_equity * CIRCUIT_BREAKER:
        return []
    buys: list[Buy] = []
    budget = cash
    core_gap = equity * core_weight - core_value
    if core_trend_up and core_gap >= MIN_ORDER_USD:
        amount = round(min(core_gap, budget), 2)
        if amount >= MIN_ORDER_USD:
            buys.append(Buy("core", CORE_SYMBOL, "stage-runner", amount, CORE_STOP, CORE_TARGET, CORE_MAX_HOLD))
            budget -= amount
    free_slots = slots - len(open_satellites)
    if free_slots <= 0 or budget < MIN_ORDER_USD:
        return buys
    per_slot = equity * (1 - core_weight) / slots
    held = set(open_satellites) | {CORE_SYMBOL} | set(exclude or ())
    ranked = sorted((s for s in signals if s["rule"] in SATELLITE_RULES
                     and group_of(s["symbol"]) in SATELLITE_GROUPS and s["symbol"] not in held),
                    key=lambda s: -(s.get("momentum_6m") or 0))
    seen = set()
    crypto_held = sum(1 for x in open_satellites if is_crypto(x))
    for s in ranked:
        if free_slots <= 0 or budget < MIN_ORDER_USD or s["symbol"] in seen:
            continue
        if is_crypto(s["symbol"]) and crypto_held >= MAX_CRYPTO_SLOTS:
            continue
        amount = round(min(per_slot, budget), 2)
        if amount < MIN_ORDER_USD:
            break
        rule = RULES[s["rule"]]
        buys.append(Buy("satellite", s["symbol"], s["rule"], amount, rule.stop, rule.target, rule.max_hold))
        seen.add(s["symbol"])
        budget -= amount
        free_slots -= 1
        crypto_held += is_crypto(s["symbol"])
    return buys


def plan_rotation(*, held: list[dict], signals: list[dict], margin: float = ROTATION_MARGIN,
                  exclude: set | None = None) -> list[tuple[str, dict]]:
    """Weekly swap: sell the weakest-momentum satellite when a new signal is clearly stronger.

    held: eligible satellites as {"id", "symbol", "momentum"} (current 6-month return).
    Returns [(lot_id_to_sell, replacement_signal)], strongest replacement first.
    Backtest 2011-Sep 2026 (rot.py): beat hold-to-exit in every period at a similar drawdown.
    """
    held_syms = {h["symbol"] for h in held} | {CORE_SYMBOL} | set(exclude or ())
    cands, seen = [], set()
    for sig in sorted(signals, key=lambda x: -(x.get("momentum_6m") or 0)):
        if (sig["rule"] in SATELLITE_RULES and group_of(sig["symbol"]) in SATELLITE_GROUPS
                and sig["symbol"] not in held_syms and sig["symbol"] not in seen):
            seen.add(sig["symbol"])
            cands.append(sig)
    pool, swaps = [h for h in held if h.get("momentum") is not None], []
    crypto_held = sum(1 for h in held if is_crypto(h["symbol"]))
    for sig in cands:
        if not pool:
            break
        weakest = min(pool, key=lambda h: h["momentum"])
        if (sig.get("momentum_6m") or 0) < weakest["momentum"] + margin:
            break
        if is_crypto(sig["symbol"]) and crypto_held - is_crypto(weakest["symbol"]) >= MAX_CRYPTO_SLOTS:
            continue
        swaps.append((weakest["id"], sig))
        pool.remove(weakest)
        crypto_held += is_crypto(sig["symbol"]) - is_crypto(weakest["symbol"])
    return swaps


def price_exit(lot, last: float) -> str | None:
    """Software stop/target for a lot without a broker bracket."""
    if lot.broker_bracket or last is None or last <= 0:
        return None
    if last <= lot.stop_price:
        return "stop"
    if last >= lot.target_price:
        return "target"
    return None


def daily_exit(lot, held_sessions: int, rule_exit_now: bool) -> str | None:
    """Once-per-day time limit and rule exit (satellites only)."""
    if lot.broker_bracket or lot.sleeve != "satellite":
        return None
    if held_sessions >= lot.max_hold_days:
        return "time_limit"
    if rule_exit_now:
        return "rule_exit"
    return None
