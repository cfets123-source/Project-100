"""Binance.US crypto worker: BTC/ETH/SOL, 24/7, breakout + trend signals.

Separate account and lot scope from the Alpaca allocator (modes "binance" and
"binance-paper"). Each UTC day the frozen scanner rules run on completed Binance.US
daily bars; a coin with a breakout or trend signal is bought with up to one third of
the account (one position per coin). Every lot is protected by this worker: market
sell when the bid crosses its stop or target, plus the rule's time limit / exit once
per UTC day. No exchange-resident stop yet: if the worker is down, lots are unwatched.

History (Yahoo daily, 3 slots, 0.05%/side): 2018-20 $100->$214 (worst drop 20%),
2021-Sep26 $522 (36%), last 12 months $117 (12%) vs buy-and-hold BTC $206/$290/$74.
Owner-accepted experiment, not validated. Live needs owner acceptance of
BINANCE_CRYPTO_VERSION, BINANCE_EXECUTION_ENABLED=true and a trade-enabled API key.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import time
import uuid

from sqlalchemy.orm import Session

from app.audit.logger import log_and_commit
from app.brokers.binance_us_trader import PAIRS, BinanceError
from app.models.models import AllocatorLot, AllocatorState
from app.research.multi_market_rules import RULES, indicators, rule_exit, signals_on_last_bar
from app.strategies.allocator import CIRCUIT_BREAKER, daily_exit, price_exit

BINANCE_CRYPTO_VERSION = "binance-crypto-signals-v1"
SLOTS = 3
SIGNAL_RULES = ("breakout", "trend")
FEE = 0.0002          # Binance.US taker on most pairs
CASH_BUFFER = 0.50


def _utc_today(now) -> dt.date:
    return now.astimezone(dt.timezone.utc).date()


def _state(db, mode) -> AllocatorState:
    st = db.get(AllocatorState, mode)
    if st is None:
        st = AllocatorState(mode=mode, peak_equity=0.0, halted=False)
        db.add(st)
        db.commit()
    return st


def _open(db, mode):
    return db.query(AllocatorLot).filter_by(mode=mode, status="open").all()


_signal_cache: dict = {}


def todays_signals(trader, today) -> list[dict]:
    """Signals formed by yesterday's completed UTC bar; computed once per UTC day."""
    if _signal_cache.get("day") != today:
        out, bars_by = [], {}
        for pair in PAIRS:
            try:
                bars = trader.daily_bars(pair)
            except BinanceError:
                continue
            bars_by[pair] = bars
            out += [s for s in signals_on_last_bar(pair, bars) if s["rule"] in SIGNAL_RULES]
        _signal_cache.update(day=today, signals=out, bars=bars_by)
    return _signal_cache["signals"]


def _bars(trader, pair, today):
    if _signal_cache.get("day") == today and pair in _signal_cache.get("bars", {}):
        return _signal_cache["bars"][pair]
    return trader.daily_bars(pair)


def _fill(order: dict):
    qty = float(order.get("executedQty") or 0)
    quote = float(order.get("cummulativeQuoteQty") or 0)
    return qty, (quote / qty if qty > 0 else None)


def _recover(venue, paper, pair, cid):
    if paper:
        return None
    try:
        res = venue.order(pair, cid)
        return res if float(res.get("executedQty") or 0) > 0 else None
    except BinanceError:
        return None


class PaperBook:
    """Simulated fills at the live Binance.US book for the paper account."""

    def __init__(self, trader):
        self.trader = trader

    def buy_usd(self, pair, usd, client_id):
        ask = self.trader.book(pair)["ask"]
        qty = usd * (1 - FEE) / ask
        return {"status": "FILLED", "executedQty": str(qty), "cummulativeQuoteQty": str(usd), "clientOrderId": client_id}

    def sell_qty(self, pair, qty, client_id):
        bid = self.trader.book(pair)["bid"]
        return {"status": "FILLED", "executedQty": str(qty), "cummulativeQuoteQty": str(qty * bid * (1 - FEE)),
                "clientOrderId": client_id}


def _sell(db, venue, lot, reason, price, today) -> dict:
    cid = f"bx{lot.id.replace('-', '')[:20]}"
    try:
        res = venue.sell_qty(lot.symbol, lot.quantity, cid)
    except BinanceError as exc:
        log_and_commit(db, "binance_sell_failed", {"mode": lot.mode, "symbol": lot.symbol, "reason": reason,
                                                   "error": str(exc)[:200]})
        return {"symbol": lot.symbol, "sold": False}
    qty, px = _fill(res)
    lot.status, lot.exit_reason, lot.closed_on = "closed", reason, today.isoformat()
    lot.exit_price = px or price
    db.commit()
    log_and_commit(db, "binance_sell", {"mode": lot.mode, "symbol": lot.symbol, "qty": qty or lot.quantity,
                                        "price": lot.exit_price, "reason": reason})
    return {"symbol": lot.symbol, "sold": True, "reason": reason, "price": lot.exit_price}


def run_cycle(db: Session, trader, *, mode: str, capital: float | None = None, floor_equity: float = 50.0,
              now: dt.datetime | None = None) -> dict:
    """One pass. mode 'binance' trades the real account; 'binance-paper' simulates on live prices."""
    now = now or dt.datetime.now(dt.timezone.utc)
    today = _utc_today(now)
    st = _state(db, mode)
    if st.halted:
        return {"mode": mode, "reason": "halted", "detail": st.reason}
    paper = mode.endswith("paper")
    venue = PaperBook(trader) if paper else trader
    books = {}
    for pair in PAIRS:
        try:
            books[pair] = trader.book(pair)
        except BinanceError:
            pass
    closed = []
    if not paper:
        bal = trader.balances()
        for lot in _open(db, mode):
            base = trader.filters(lot.symbol)["base"]
            if bal.get(base, 0.0) < lot.quantity * 0.98:  # sold outside the worker
                lot.status, lot.exit_reason, lot.closed_on = "closed", "broker_exit", today.isoformat()
                closed.append(lot.symbol)
        db.commit()
    exits = []
    for lot in _open(db, mode):
        bid = books.get(lot.symbol, {}).get("bid")
        reason = price_exit(lot, bid)
        if reason:
            exits.append(_sell(db, venue, lot, reason, bid, today))
    if st.last_daily_review != today.isoformat():
        for lot in _open(db, mode):
            try:
                bars = _bars(trader, lot.symbol, today)
            except BinanceError:
                continue
            if len(bars) < 60:
                continue
            held = sum(1 for b in bars if b["timestamp"] >= lot.opened_on)
            reason = daily_exit(lot, held, rule_exit(lot.rule, indicators(bars), len(bars) - 1))
            if reason:
                exits.append(_sell(db, venue, lot, reason, books.get(lot.symbol, {}).get("bid"), today))
        st.last_daily_review = today.isoformat()
        db.commit()
    lots = _open(db, mode)
    held_value = sum(l.quantity * books.get(l.symbol, {}).get("bid", l.entry_price) for l in lots)
    if paper:
        start = capital or 100.0
        realized = sum(((l.exit_price or l.entry_price) - l.entry_price) * l.quantity
                       for l in db.query(AllocatorLot).filter_by(mode=mode, status="closed").all())
        cash = start + realized - sum(l.entry_price * l.quantity for l in lots)
    else:
        cash = trader.balances().get("USD", 0.0)
    equity = cash + held_value
    st.peak_equity = max(st.peak_equity or 0.0, equity)
    db.commit()
    buys = []
    breaker = st.peak_equity > 0 and equity < st.peak_equity * CIRCUIT_BREAKER
    if equity >= floor_equity and not breaker:
        held = {l.symbol for l in lots} | {l.symbol for l in db.query(AllocatorLot).filter_by(
            mode=mode, closed_on=today.isoformat()).all()}
        budget = cash - CASH_BUFFER
        for sig in sorted(todays_signals(trader, today), key=lambda s: -(s.get("momentum_6m") or 0)):
            if len(lots) + len(buys) >= SLOTS or sig["symbol"] in held or sig["symbol"] not in books:
                continue
            f = trader.filters(sig["symbol"])
            usd = round(min(equity / SLOTS, budget), 2)
            if not f["trading"] or usd < max(f["min_notional"], 1.0) * 1.05:
                continue
            lot_id = str(uuid.uuid4())
            cid = f"bb{lot_id.replace('-', '')[:20]}"
            try:
                res = venue.buy_usd(sig["symbol"], usd, cid)
            except BinanceError as exc:
                res = _recover(venue, paper, sig["symbol"], cid)  # outcome unknown: ask the exchange
                if res is None:
                    log_and_commit(db, "binance_buy_failed", {"mode": mode, "symbol": sig["symbol"],
                                                              "error": str(exc)[:200]})
                    continue
            if not paper and res.get("status") != "FILLED":
                time.sleep(1)
                res = _recover(venue, paper, sig["symbol"], cid) or res
            qty, px = _fill(res)
            if not qty or not px:
                log_and_commit(db, "binance_buy_unfilled", {"mode": mode, "symbol": sig["symbol"],
                                                            "status": res.get("status")})
                continue
            if not paper:  # the coin fee is deducted from the coins received
                qty = min(qty, trader.balances().get(f["base"], qty))
            rule = RULES[sig["rule"]]
            db.add(AllocatorLot(id=lot_id, mode=mode, sleeve="satellite", symbol=sig["symbol"], rule=sig["rule"],
                                quantity=qty, entry_price=px, stop_price=px * (1 - rule.stop),
                                target_price=px * (1 + rule.target), max_hold_days=rule.max_hold,
                                broker_bracket=False, opened_on=today.isoformat(),
                                order_id=res.get("clientOrderId"), confirmed=True, status="open"))
            db.commit()
            log_and_commit(db, "binance_buy", {"mode": mode, "symbol": sig["symbol"], "rule": sig["rule"],
                                               "usd": usd, "qty": qty, "price": px})
            buys.append({"symbol": sig["symbol"], "usd": usd, "price": round(px, 2)})
            budget -= usd
            held.add(sig["symbol"])
    return {"mode": mode, "strategy": BINANCE_CRYPTO_VERSION, "equity": round(equity, 2), "cash": round(cash, 2),
            "open_lots": len(_open(db, mode)), "signals": [f"{s['symbol']}:{s['rule']}" for s in
                                                          _signal_cache.get("signals", [])],
            "closed_by_broker": closed, "exits": exits, "buys": buys}


def main() -> int:
    from sqlalchemy import create_engine
    from app.brokers.binance_us_trader import BinanceUSTrader, load_trader
    from app.core.config import Settings
    from app.db.session import initialize_schema
    from app.services.owner_experiment import require_owner_experiment

    p = argparse.ArgumentParser()
    p.add_argument("--database", required=True)
    p.add_argument("--mode", choices=("paper", "live"), required=True)
    p.add_argument("--capital", type=float, default=100.0, help="paper: virtual account size")
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=float, default=60)
    args = p.parse_args()
    cfg = Settings()
    engine = create_engine(args.database)
    initialize_schema(engine)
    while True:
        try:
            with Session(engine) as db:
                if args.mode == "live":
                    rec = require_owner_experiment(db, BINANCE_CRYPTO_VERSION)
                    if os.getenv("BINANCE_EXECUTION_ENABLED", "false").lower() != "true":
                        raise RuntimeError("BINANCE_EXECUTION_ENABLED is not true")
                    trader = load_trader(db, cfg.BROKER_TOKEN_ENCRYPTION_KEY, enabled=True)
                    result = run_cycle(db, trader, mode="binance", floor_equity=rec.floor_equity)
                else:
                    result = run_cycle(db, BinanceUSTrader(), mode="binance-paper", capital=args.capital)
        except Exception as exc:
            result = {"mode": args.mode, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        print(result, flush=True)
        if args.once:
            return 0
        time.sleep(max(20.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
