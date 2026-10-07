"""All-in allocator: buy planning, bracket adoption, software exits, reconciliation."""
import datetime as dt
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.brokers.base import OrderResult
from app.db.session import Base
from app.models import models
from app.runtime import allocator_worker as w
from app.strategies.allocator import plan_buys, floor_qty

NOW = dt.datetime(2026, 10, 8, 15, 0, tzinfo=dt.timezone.utc)  # 11:00 ET Thursday


def sig(sym, rule="breakout", mom=0.2):
    return {"symbol": sym, "rule": rule, "momentum_6m": mom}


def test_plan_spends_cash_on_satellites_when_core_is_overweight():
    buys = plan_buys(equity=105, cash=22, core_value=82, core_trend_up=True, open_satellites=[],
                     signals=[sig("AAPL", mom=.3), sig("XLE", mom=.5), sig("GLD", "trend", .1)], peak_equity=105)
    assert [b.symbol for b in buys] == ["XLE", "AAPL", "GLD"]
    assert [b.notional for b in buys] == [10.5, 10.5, 1.0] and all(b.sleeve == "satellite" for b in buys)


def test_plan_core_first_then_skips_held_unknown_and_pullback():
    buys = plan_buys(equity=200, cash=150, core_value=0, core_trend_up=True, open_satellites=["AAPL"],
                     signals=[sig("AAPL"), sig("ZZZZ"), sig("SPY", "pullback"), sig("MSFT")], peak_equity=200)
    assert buys[0].sleeve == "core" and buys[0].notional == 100
    assert [b.symbol for b in buys[1:]] == ["MSFT"] and buys[1].notional == 20


def test_circuit_breaker_and_trend_off():
    assert plan_buys(equity=40, cash=40, core_value=0, core_trend_up=True, open_satellites=[],
                     signals=[sig("MSFT")], peak_equity=100) == []
    buys = plan_buys(equity=100, cash=100, core_value=0, core_trend_up=False, open_satellites=[],
                     signals=[sig("MSFT")], peak_equity=100)
    assert [b.sleeve for b in buys] == ["satellite"]


def test_floor_qty():
    assert floor_qty(10.5, 251.3) == 0.0417 and floor_qty(5, 0) == 0


class FakeAlpaca:
    def __init__(self):
        self.positions = {"TQQQ": {"symbol": "TQQQ", "qty": "1", "avg_entry_price": "77.72"}}
        self.orders = [{"id": "p", "symbol": "TQQQ", "status": "filled", "side": "buy", "type": "market", "legs": [
            {"id": "t", "symbol": "TQQQ", "status": "new", "side": "sell", "type": "limit", "limit_price": "116.58"},
            {"id": "s", "symbol": "TQQQ", "status": "held", "side": "sell", "type": "stop", "stop_price": "58.29"}]}]
        self.prices = {"TQQQ": 82.5, "AAPL": 250.0, "XLE": 90.0, "QQQ": 754.0}
        self.cash, self.placed, self.filled = 22.0, [], {}

    def get_market_clock(self): return {"is_open": True}
    def get_positions(self): return list(self.positions.values())
    def get_orders(self): return self.orders
    def get_balances(self):
        eq = self.cash + sum(float(p["qty"]) * self.prices[s] for s, p in self.positions.items())
        return {"equity": eq, "cash": self.cash, "buying_power": self.cash}
    def get_quotes(self, syms):
        return [SimpleNamespace(symbol=s, bid=self.prices[s] - .01, ask=self.prices[s] + .01, last=self.prices[s])
                for s in syms if s in self.prices]
    def get_daily_bars(self, sym, start, end):
        d0 = dt.date(2025, 9, 1)
        return [{"timestamp": (d0 + dt.timedelta(days=i)).isoformat(), "open": 100 + i * .2, "high": 101 + i * .2,
                 "low": 99 + i * .2, "close": 100 + i * .2, "volume": 1} for i in range(400)]
    def place_order(self, o):
        self.placed.append(o)
        oid = f"o{len(self.placed)}"
        px = self.prices[o.symbol] + (.01 if o.side == "buy" else 0)
        q = float(self.positions.get(o.symbol, {}).get("qty", 0))
        q = q + o.quantity if o.side == "buy" else q - o.quantity
        self.cash += -o.quantity * px if o.side == "buy" else o.quantity * px
        if q > 1e-9:
            self.positions[o.symbol] = {"symbol": o.symbol, "qty": str(q), "avg_entry_price": str(px)}
        else:
            self.positions.pop(o.symbol, None)
        self.filled[oid] = {"status": "filled", "filled_avg_price": str(px), "filled_qty": str(o.quantity)}
        return OrderResult(order_id=oid, status="accepted")
    def get_order_status(self, oid): return self.filled[oid]


def _db_with_signals(*sigs):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    for i, (sym, rule, mom) in enumerate(sigs):
        db.add(models.ScannerSignal(id=str(i), rules_version="v1", symbol=sym, rule=rule, asset_group="x",
                                    signal_date="2026-10-07", signal_close=1, stop_pct=.07, target_pct=.15,
                                    max_hold=30, momentum_6m=mom, status="waiting_entry"))
    db.commit()
    return db


def test_live_cycle_adopts_core_buys_satellites_then_stops_out():
    db, broker = _db_with_signals(("XLE", "breakout", .5), ("AAPL", "trend", .3)), FakeAlpaca()
    out = w.run_cycle(db, broker, mode="live", now=NOW)
    assert out["adopted"] == 1
    assert [b["symbol"] for b in out["buys"]] == ["XLE", "AAPL"]
    core = db.query(models.AllocatorLot).filter_by(sleeve="core").one()
    assert core.broker_bracket and core.quantity == 1 and core.stop_price == 58.29
    # fills confirmed next cycle; then XLE drops through its 7% stop
    broker.prices["XLE"] = 80.0
    out2 = w.run_cycle(db, broker, mode="live", now=NOW + dt.timedelta(minutes=1))
    assert any(e["symbol"] == "XLE" and e["reason"] == "stop" for e in out2["exits"])
    assert all(o.symbol != "TQQQ" for o in broker.placed)  # bracket core is broker-managed
    assert db.query(models.AllocatorLot).filter_by(symbol="XLE").one().status == "closed"
    # XLE is not bought back the same day
    out3 = w.run_cycle(db, broker, mode="live", now=NOW + dt.timedelta(minutes=2))
    assert "XLE" not in [b["symbol"] for b in out3["buys"]]


def test_broker_bracket_exit_is_reconciled():
    db, broker = _db_with_signals(), FakeAlpaca()
    w.run_cycle(db, broker, mode="live", now=NOW)
    broker.positions.pop("TQQQ")  # target leg filled at the broker
    broker.cash += 116.58
    w.run_cycle(db, broker, mode="live", now=NOW + dt.timedelta(minutes=1))
    lot = db.query(models.AllocatorLot).filter_by(sleeve="core", broker_bracket=True).one()
    assert lot.status == "closed" and lot.exit_reason == "broker_exit"


def test_paper_uses_virtual_capital_not_paper_balance():
    db, broker = _db_with_signals(("XLE", "breakout", .5)), FakeAlpaca()
    broker.cash = 100_000.0
    out = w.run_cycle(db, broker, mode="paper", capital_cap=100.0, now=NOW)
    assert out["cash"] < 25 and sum(b["usd"] for b in out["buys"]) <= 25


def test_market_closed_and_outside_window_do_nothing():
    db, broker = _db_with_signals(("XLE", "breakout", .5)), FakeAlpaca()
    broker.get_market_clock = lambda: {"is_open": False}
    assert w.run_cycle(db, broker, mode="live", now=NOW)["reason"] == "market_closed"
    broker2 = FakeAlpaca()
    late = dt.datetime(2026, 10, 8, 19, 45, tzinfo=dt.timezone.utc)  # 15:45 ET
    assert w.run_cycle(db, broker2, mode="live", now=late)["buys"] == []


def test_plan_rotation_swaps_only_clearly_stronger_signals():
    from app.strategies.allocator import plan_rotation
    held = [{"id": "a", "symbol": "EWT", "momentum": 0.10}, {"id": "b", "symbol": "QLD", "momentum": 0.40}]
    swaps = plan_rotation(held=held, signals=[sig("NVDA", mom=.35), sig("XLE", mom=.25), sig("EWT", mom=.9),
                                              sig("SPY", "pullback", .9)])
    assert [(i, s["symbol"]) for i, s in swaps] == [("a", "NVDA")]  # XLE only +15 pts, QLD too strong
    assert plan_rotation(held=held, signals=[sig("XLE", mom=.29)]) == []


def test_weekly_rotation_sells_weakest_then_buys_replacement_next_cycle(monkeypatch):
    db, broker = _db_with_signals(("XLE", "breakout", .9)), FakeAlpaca()
    broker.positions["EWT"] = {"symbol": "EWT", "qty": "0.1", "avg_entry_price": "90"}
    broker.cash = 0.6
    db.add(models.AllocatorLot(id="ewt", mode="live", sleeve="satellite", symbol="EWT", rule="breakout",
                               quantity=0.1, entry_price=90.0, stop_price=50.0, target_price=200.0,
                               max_hold_days=30, broker_bracket=False, opened_on="2026-10-01",
                               confirmed=True, status="open"))
    db.commit()
    broker.prices["EWT"] = 90.0
    monkeypatch.setattr(w, "momentum_6m", lambda reader, s, today: 0.05)
    out = w.run_cycle(db, broker, mode="live", now=NOW)
    assert out["rotations"] == [{"sold": "EWT", "for": "XLE", "for_momentum": 0.9}]
    assert db.get(models.AllocatorLot, "ewt").exit_reason == "rotation"
    assert "EWT" not in [b["symbol"] for b in out["buys"]]
    out2 = w.run_cycle(db, broker, mode="live", now=NOW + dt.timedelta(minutes=1))
    assert out2["rotations"] == [] and "XLE" in [b["symbol"] for b in out2["buys"]]


def test_crypto_capped_at_one_slot():
    buys = plan_buys(equity=200, cash=100, core_value=100, core_trend_up=True, open_satellites=[],
                     signals=[sig("BTC/USD", mom=.9), sig("ETH/USD", mom=.8), sig("MSFT", mom=.1)], peak_equity=200)
    assert [b.symbol for b in buys] == ["BTC/USD", "MSFT"]
    assert plan_buys(equity=200, cash=100, core_value=100, core_trend_up=True, open_satellites=["SOL/USD"],
                     signals=[sig("BTC/USD", mom=.9)], peak_equity=200) == []
    assert floor_qty(10.5, 112000.0, 8) == 0.00009375


class FakeCryptoAlpaca(FakeAlpaca):
    def __init__(self):
        super().__init__()
        self.prices["BTC/USD"] = 100000.0
        self.open = False

    def get_market_clock(self): return {"is_open": self.open}
    def get_account_capabilities(self): return {"crypto_status": "ACTIVE"}
    def get_asset(self, symbol): return {"min_order_size": "0.00001"}
    def get_crypto_quotes(self, syms): return self.get_quotes(syms)
    def get_crypto_daily_bars(self, sym, start, end): return self.get_daily_bars(sym, start, end)

    def get_positions(self):  # Alpaca reports crypto positions without the slash, net of the coin fee
        return [{**p, "symbol": s.replace("/", ""), "qty": str(float(p["qty"]) * (0.9985 if "/" in s else 1))}
                for s, p in self.positions.items()]

    def place_order(self, o):
        assert ("/" in o.symbol) == (o.time_in_force == "gtc")
        return super().place_order(o)


def test_crypto_trades_while_stock_market_closed(monkeypatch):
    monkeypatch.setattr(w, "_crypto_cache", {"until": 0.0, "ok": False})
    monkeypatch.setattr(w, "_min_qty_cache", {})
    db, broker = _db_with_signals(("BTC/USD", "breakout", .9), ("XLE", "breakout", .5)), FakeCryptoAlpaca()
    sat_night = dt.datetime(2026, 10, 10, 18, 0, tzinfo=dt.timezone.utc)  # Saturday
    out = w.run_cycle(db, broker, mode="live", now=sat_night)
    assert out["reason"] == "market_closed" and out["crypto"] is True
    assert [b["symbol"] for b in out["buys"]] == ["BTC/USD"]  # XLE waits for the stock session
    assert all(o.symbol != "TQQQ" for o in broker.placed)
    out2 = w.run_cycle(db, broker, mode="live", now=sat_night + dt.timedelta(minutes=1))
    lot = db.query(models.AllocatorLot).filter_by(symbol="BTC/USD").one()
    assert lot.confirmed and lot.status == "open" and out2["closed_by_broker"] == []
    assert abs(lot.quantity - float(broker.positions["BTC/USD"]["qty"]) * 0.9985) < 1e-12  # fee-adjusted
    broker.prices["BTC/USD"] = 90000.0  # through the 7% stop
    out3 = w.run_cycle(db, broker, mode="live", now=sat_night + dt.timedelta(minutes=2))
    assert any(e["symbol"] == "BTC/USD" and e["reason"] == "stop" for e in out3["exits"])
    assert broker.placed[-1].side == "sell" and broker.placed[-1].time_in_force == "gtc"
