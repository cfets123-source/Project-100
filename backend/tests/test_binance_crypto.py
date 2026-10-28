"""Binance.US crypto worker: signals -> buys, software stops, live fee/recovery handling."""
import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.binance_us import BinanceError
from app.brokers.binance_us_trader import floor_step
from app.db.session import Base
from app.models import models
from app.runtime import binance_crypto_worker as w

NOW = dt.datetime(2026, 10, 10, 3, 0, tzinfo=dt.timezone.utc)  # Saturday night: crypto still trades


def sig(sym, rule="breakout", mom=.5):
    return {"symbol": sym, "rule": rule, "momentum_6m": mom}


class FakeTrader:
    def __init__(self, live=False):
        self.px = {"BTC/USD": 100000.0, "ETH/USD": 4000.0, "SOL/USD": 200.0}
        self.bal = {"USD": 100.0, "BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        self.orders, self.fail_next_buy, self.live = {}, False, live

    def book(self, pair):
        p = self.px[pair]
        return {"bid": p * 0.9999, "ask": p * 1.0001, "last": p}

    def filters(self, pair):
        return {"step": "0.00001", "min_notional": 1.0, "base": pair.split("/")[0], "trading": True}

    def daily_bars(self, pair):
        return [{"timestamp": (dt.date(2025, 8, 1) + dt.timedelta(days=i)).isoformat(), "open": 1, "high": 1,
                 "low": 1, "close": 1 + i * .001, "volume": 1} for i in range(300)]

    def balances(self):
        return dict(self.bal)

    def buy_usd(self, pair, usd, cid):
        qty = usd / self.px[pair]
        self.bal["USD"] -= usd
        self.bal[pair.split("/")[0]] += qty * 0.9998  # fee taken in coin
        self.orders[cid] = {"status": "FILLED", "executedQty": str(qty), "cummulativeQuoteQty": str(usd),
                            "clientOrderId": cid}
        if self.fail_next_buy:
            self.fail_next_buy = False
            raise BinanceError("Binance.US request outcome unknown (network)")
        return self.orders[cid]

    def sell_qty(self, pair, qty, cid):
        base = pair.split("/")[0]
        q = float(floor_step(qty, "0.00001"))
        assert q <= self.bal[base] + 1e-12
        self.bal[base] -= q
        self.bal["USD"] += q * self.px[pair]
        return {"status": "FILLED", "executedQty": str(q), "cummulativeQuoteQty": str(q * self.px[pair])}

    def order(self, pair, cid):
        if cid not in self.orders:
            raise BinanceError("not found")
        return self.orders[cid]


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_paper_buys_one_third_each_and_caps_three_coins(monkeypatch):
    monkeypatch.setattr(w, "todays_signals", lambda t, d: [sig("SOL/USD", mom=.9), sig("BTC/USD", "trend", .4),
                                                           sig("ETH/USD", mom=.2), sig("SOL/USD", "trend", .8)])
    db, t = _db(), FakeTrader()
    out = w.run_cycle(db, t, mode="binance-paper", capital=99.0, now=NOW)
    assert [b["symbol"] for b in out["buys"]] == ["SOL/USD", "BTC/USD", "ETH/USD"]
    assert all(abs(b["usd"] - 33.0) < .01 for b in out["buys"][:2]) and out["buys"][2]["usd"] <= 32.5
    assert w.run_cycle(db, t, mode="binance-paper", capital=99.0, now=NOW + dt.timedelta(minutes=1))["buys"] == []


def test_software_stop_sells_and_no_same_day_rebuy(monkeypatch):
    monkeypatch.setattr(w, "todays_signals", lambda t, d: [sig("SOL/USD")])
    db, t = _db(), FakeTrader()
    w.run_cycle(db, t, mode="binance-paper", now=NOW)
    t.px["SOL/USD"] = 180.0  # -10%, breakout stop is -7%
    out = w.run_cycle(db, t, mode="binance-paper", now=NOW + dt.timedelta(minutes=1))
    assert out["exits"][0]["reason"] == "stop" and out["buys"] == []
    lot = db.query(models.AllocatorLot).filter_by(mode="binance-paper").one()
    assert lot.status == "closed" and lot.exit_price < lot.entry_price


def test_live_records_fee_net_quantity_and_recovers_unknown_outcome(monkeypatch):
    monkeypatch.setattr(w, "todays_signals", lambda t, d: [sig("ETH/USD")])
    db, t = _db(), FakeTrader(live=True)
    t.fail_next_buy = True  # network drop after the exchange filled the order
    out = w.run_cycle(db, t, mode="binance", now=NOW)
    assert [b["symbol"] for b in out["buys"]] == ["ETH/USD"]
    lot = db.query(models.AllocatorLot).filter_by(mode="binance").one()
    assert abs(lot.quantity - t.bal["ETH"]) < 1e-12  # sells can never exceed what we hold
    out2 = w.run_cycle(db, t, mode="binance", now=NOW + dt.timedelta(minutes=1))
    assert out2["buys"] == [] and len(t.orders) == 1  # no duplicate buy


def test_live_detects_coins_sold_outside_the_worker(monkeypatch):
    monkeypatch.setattr(w, "todays_signals", lambda t, d: [sig("BTC/USD")])
    db, t = _db(), FakeTrader(live=True)
    w.run_cycle(db, t, mode="binance", now=NOW)
    t.bal["BTC"] = 0.0
    out = w.run_cycle(db, t, mode="binance", now=NOW + dt.timedelta(minutes=1))
    assert out["closed_by_broker"] == ["BTC/USD"]


def test_floor_step_rounds_down():
    assert str(floor_step(0.123456789, "0.00001")) == "0.12345"
