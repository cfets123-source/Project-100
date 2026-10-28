import datetime as dt
import os
import random
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "research", "20261013-intraday"))

import guard  # noqa: E402
import noise  # noqa: E402
import worker  # noqa: E402
from topstepx import TopstepXError  # noqa: E402

ET = worker.ET
TIMES = [(dt.datetime(2026, 1, 1, 9, 30) + dt.timedelta(minutes=5 * i)).time() for i in range(78)]


def synth_days(n, seed=1):
    rng, px, days = random.Random(seed), 20000.0, []
    for _ in range(n):
        day, trend = {}, rng.choice([-1, 0, 1]) * 0.0004
        px *= 1 + rng.gauss(0, 0.004)
        for t in TIMES:
            o = px
            px *= 1 + trend + rng.gauss(0, 0.0012)
            day[t] = (o, max(o, px) * 1.0003, min(o, px) * 0.9997, px, rng.randint(500, 2000))
        days.append(day)
    return days


def reference_positions(history, today):
    """Position path from the backtested logic in research/20261021-prop-challenge (chall_intraday.noise_days)."""
    op, prev_close = today[noise.OPEN][0], history[-1][noise.LAST][3]
    pos, path = 0, {}
    for t in sorted(today):
        if noise.is_check(t):
            s = noise.sigma(history, t)
            if s is None:
                continue
            up, dn = max(op, prev_close) * (1 + s), min(op, prev_close) * (1 - s)
            vw, c = noise.vwap(today, t), today[t][3]
            if pos > 0 and c < max(up, vw) or pos < 0 and c > min(dn, vw):
                pos = 0
            if pos == 0:
                pos = 1 if c > up else -1 if c < dn else 0
            path[t] = pos
    return path


def test_decide_matches_backtested_rules():
    days = synth_days(60)
    traded = 0
    for i in range(20, 60):
        hist, today = days[i - 20:i], days[i]
        ref, pos = reference_positions(hist, today), 0
        for t in sorted(today):
            d = noise.decide(hist, today, t, pos)
            if d is not None:
                pos = d
                assert pos == ref[t], (i, t)
                traded += pos != 0
    assert traded > 20  # the synthetic data actually exercises entries


def test_decide_matches_research_backtest_module():
    import intraday_bt  # the exact module run on the server for the published result
    days = synth_days(40, seed=7)
    hist, today = days[:20], days[20]
    assert noise.sigma(hist, dt.time(10, 25)) is not None
    assert reference_positions(hist, today)  # helper mirrors chall_intraday; module importable
    assert intraday_bt.LAST == noise.LAST


def test_guard_limits():
    st = guard.ChallengeState(start_balance=50000, eod_high=50000)
    guard.new_day(st, "2026-10-22", 50000)
    assert guard.check(st, 50000, -500)[0] is True
    allowed, flat, why = guard.check(st, 50000, -800)
    assert not allowed and flat and "daily" in why
    assert guard.check(st, 50000, 0)[2] == "stopped for today"
    guard.new_day(st, "2026-10-23", 51500)          # trailing limit rises with the end-of-day high
    assert st.floor == 49500
    allowed, flat, why = guard.check(st, 50000, -150)  # equity 49,850 is within $400 of 49,500
    assert flat and st.finished
    st2 = guard.ChallengeState(start_balance=50000, eod_high=50000)
    guard.new_day(st2, "2026-10-22", 52900)
    allowed, flat, why = guard.check(st2, 52900, 150)
    assert not allowed and "target" in why and st2.passed
    st3 = guard.ChallengeState(start_balance=50000, eod_high=56000)
    assert st3.floor == 50000                       # the limit stops at the starting balance


class FakeAPI:
    def __init__(self, days, fail_next_order=False):
        self.days, self.now = days, None
        self.bal, self.pos, self.avg = 50000.0, 0, None
        self.orders, self.closes, self.tags, self.fail_next = [], 0, set(), fail_next_order

    def accounts(self):
        return [{"id": 7, "name": "50KTC-PRACTICE-1", "balance": self.bal, "canTrade": True, "simulated": True}]

    def contract(self, symbol="MNQ", live=False):
        return {"id": "CON.F.US.MNQ.Z26", "tickSize": 0.25, "tickValue": 0.5, "activeContract": True, "name": "MNQZ6"}

    def bars(self, cid, start, end, **k):
        s = worker.to_et(start)
        e = worker.to_et(end)
        out = []
        for date, day in self.days.items():
            for t, (o, h, l, c, v) in day.items():
                ts = dt.datetime.combine(date, t, ET)
                if s <= ts and ts + dt.timedelta(minutes=5) <= e:
                    out.append({"t": worker.iso(ts), "o": o, "h": h, "l": l, "c": c, "v": v})
        return out

    def last_price(self):
        day = self.days[self.now.date()]
        done = [t for t in day if dt.datetime.combine(self.now.date(), t, ET) + dt.timedelta(minutes=5) <= self.now]
        return day[max(done)][3]

    def positions(self, aid):
        if not self.pos:
            return []
        return [{"contractId": "CON.F.US.MNQ.Z26", "type": 1 if self.pos > 0 else 2, "size": abs(self.pos),
                 "averagePrice": self.avg}]

    def _fill(self, delta):
        px = self.last_price()
        if self.pos and (self.pos > 0) != (self.pos + delta > 0) and self.pos + delta != 0:
            raise AssertionError("bot must close before reversing")
        if self.pos + delta == 0:
            self.bal += (px - self.avg) * self.pos * 2
            self.pos, self.avg = 0, None
        else:
            self.avg = px if not self.pos else self.avg
            self.pos += delta

    def market(self, aid, cid, side, size, tag=None):
        if tag in self.tags:
            raise TopstepXError("duplicate customTag")
        self.tags.add(tag)
        self._fill(size if side == 0 else -size)
        self.orders.append((side, size, tag))
        if self.fail_next:
            self.fail_next = False
            raise TopstepXError("network: timeout")  # order went through but the reply was lost
        return len(self.orders)

    def close(self, aid, cid):
        self.closes += 1
        if self.pos:
            self._fill(-self.pos)


def make_bot(tmp_path, api, orders=True):
    start = dt.date(2026, 9, 1)
    clock = lambda: api.now  # noqa: E731
    api.now = dt.datetime.combine(start, dt.time(9, 25), ET)
    return worker.Bot(api, "PRACTICE", orders, 50000.0, home=str(tmp_path), clock=clock)


def trading_days(n, seed=3):
    days, d = {}, dt.date(2026, 8, 1)
    for day in synth_days(n, seed):
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        days[d] = day
        d += dt.timedelta(days=1)
    return days


def run_day(bot, api, date):
    for minute in range(0, 400, 1):
        api.now = dt.datetime.combine(date, dt.time(9, 25), ET) + dt.timedelta(minutes=minute)
        if api.now.time() > dt.time(16, 5):
            break
        try:
            bot.step()
        except TopstepXError:
            pass


def test_bot_trades_and_is_flat_every_close(tmp_path):
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api)
    dates = sorted(api.days)[25:40]
    for d in dates:
        run_day(bot, api, d)
        assert api.pos == 0, "must be flat after the close on %s" % d
    assert api.orders, "the strategy should have traded on synthetic trending days"
    assert all(1 <= size <= 4 for _, size, _ in api.orders)


def test_dry_run_never_places_orders(tmp_path):
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api, orders=False)
    for d in sorted(api.days)[25:35]:
        run_day(bot, api, d)
    assert api.orders == [] and api.closes == 0
    assert os.path.exists(os.path.join(str(tmp_path), "status.json"))


def test_lost_reply_does_not_double_the_position(tmp_path):
    api = FakeAPI(trading_days(45), fail_next_order=True)
    bot = make_bot(tmp_path, api)
    for d in sorted(api.days)[25:40]:
        run_day(bot, api, d)
        assert abs(api.pos) <= 3
    assert len({t for _, _, t in api.orders}) == len(api.orders)


def test_daily_stop_flattens_and_stops(tmp_path):
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api)
    d = sorted(api.days)[30]
    api.now = dt.datetime.combine(d, dt.time(11, 0), ET)
    bot.step()
    api.pos, api.avg = 2, api.last_price() + 250  # pretend a 2-contract long is down $1,000
    bot.step()
    assert api.pos == 0 and bot.state.halted_day == d.isoformat()


def test_early_close_days():
    assert worker.flatten_time(dt.date(2026, 11, 27)) == dt.time(12, 55)
    assert worker.flatten_time(dt.date(2026, 12, 24)) == dt.time(12, 55)
    assert worker.flatten_time(dt.date(2026, 11, 25)) == dt.time(15, 55)


class FakeOpener:
    def __init__(self):
        self.bodies = []

    def __call__(self, req, timeout=10):
        import io
        import json as _json
        assert req.headers.get("X-prop-token") == "tok"
        self.bodies.append(_json.loads(req.data.decode()))

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(b"{}")


def test_bot_reports_status_and_each_event_once(tmp_path):
    api = FakeAPI(trading_days(45))
    opener = FakeOpener()
    start = dt.date(2026, 9, 1)
    api.now = dt.datetime.combine(start, dt.time(9, 25), ET)
    bot = worker.Bot(api, "PRACTICE", True, 50000.0, home=str(tmp_path), clock=lambda: api.now,
                     feed=worker.Feed(url="https://example.test/prop/feed", token="tok", opener=opener))
    for d in sorted(api.days)[25:32]:
        run_day(bot, api, d)
    assert opener.bodies, "the bot should report to the app"
    ids = [e["id"] for b in opener.bodies for e in b["events"]]
    assert len(ids) == len(set(ids)), "each event is sent once"
    kinds = {e["kind"] for b in opener.bodies for e in b["events"]}
    assert "day" in kinds and ({"buy", "sell"} & kinds)
    last = opener.bodies[-1]
    assert last["orders"] is True and last["contract"].startswith("CON.F.US.MNQ") and last["bars"]
    assert {"balance", "open_pnl", "position", "floor", "avg", "state"} <= set(last["status"])
    assert last["status"]["state"]["day_start_balance"] is not None


def test_feed_failure_never_stops_trading(tmp_path):
    api = FakeAPI(trading_days(45))

    def broken(req, timeout=10):
        raise OSError("offline")
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    bot = worker.Bot(api, "PRACTICE", True, 50000.0, home=str(tmp_path), clock=lambda: api.now,
                     feed=worker.Feed(url="https://example.test", token="tok", opener=broken))
    for d in sorted(api.days)[25:30]:
        run_day(bot, api, d)
        assert api.pos == 0
    assert api.orders


def test_hourly_checks_only():
    assert noise.is_check(dt.time(9, 55)) and noise.is_check(dt.time(14, 55))
    assert not noise.is_check(dt.time(10, 25)) and not noise.is_check(dt.time(15, 25))


def test_vol_scale_targets_one_percent_daily_and_is_clamped():
    def days(moves):
        px, out = 100.0, []
        for m in moves:
            px *= 1 + m
            out.append({noise.LAST: (px, px, px, px, 1)})
        return out
    calm = days([0.002, -0.002] * 8)       # ~0.2% daily vol -> capped at 2x
    wild = days([0.04, -0.04] * 8)         # ~4% daily vol -> floored at 0.5x
    normal = days([0.01, -0.01] * 8)       # ~1% daily vol -> about 1x
    assert noise.vol_scale(calm) == 2.0 and noise.vol_scale(wild) == 0.5
    assert 0.9 < noise.vol_scale(normal) < 1.1


def test_funded_account_sizes_by_room(tmp_path):
    api = FakeAPI(trading_days(45))
    api.accounts = lambda: [{"id": 9, "name": "EXPRESS-50K-1", "balance": 50000.0, "canTrade": True, "simulated": True}]
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    bot = worker.Bot(api, "EXPRESS", True, home=str(tmp_path), clock=lambda: api.now)
    bot.scale = 1.0
    assert bot.state.kind == "funded" and bot.state.mll_buffer == 150
    bot.room = 2000
    assert bot.size(29000) == 1
    bot.room = 6000
    assert bot.size(29000) == 2
    bot.scale = 2.0
    assert bot.size(29000) == 4


def test_aggressive_sizing(tmp_path):
    api = FakeAPI(trading_days(45))
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    bot = worker.Bot(api, "PRACTICE", True, home=str(tmp_path), clock=lambda: api.now, aggressive=True)
    bot.state.kind = "combine"
    bot.scale = 1.0
    assert bot.size(29000) == 4
    bot.scale = 2.0
    assert bot.size(29000) == 8
    bot.scale = 0.5
    assert bot.size(29000) == 2
    bot.state.kind = "funded"
    bot.scale = 1.0
    assert bot.size(29000) == 2
    combine = worker.Bot(FakeAPI(trading_days(45)), "PRACTICE", True, home=str(tmp_path / "b"),
                         clock=lambda: api.now, aggressive=True)
    combine.state.kind = "combine"
    assert worker.Bot(api, "PRACTICE", True, home=str(tmp_path / "c"), clock=lambda: api.now).aggressive is False


def test_aggressive_bot_trades_and_is_flat(tmp_path):
    api = FakeAPI(trading_days(45))
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    bot = worker.Bot(api, "PRACTICE", True, home=str(tmp_path), clock=lambda: api.now, aggressive=True)
    for d in sorted(api.days)[25:40]:
        run_day(bot, api, d)
        assert api.pos == 0
    assert api.orders and max(s for _, s, _ in api.orders) <= 8


def test_take_profit_closes_combine_trade_and_allows_reentry(tmp_path):
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api)
    bot.state.kind = "combine"
    d = sorted(api.days)[30]
    api.now = dt.datetime.combine(d, dt.time(11, 0), ET)
    bot.step()
    api.pos, api.avg = 2, api.last_price() - 160  # 2-contract long up $640
    bot.step()
    assert api.pos == 0 and bot.state.halted_day != d.isoformat()
    assert any("take profit" in e.get("text", "") for e in bot.events)
    api.pos, api.avg = 2, api.last_price() - 100  # up $400: below the target, keep holding
    bot.step()
    assert api.pos == 2


def test_take_profit_is_off_outside_combines(tmp_path):
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api)
    assert bot.state.kind == "practice" and bot.take_profit() == 0
    bot.state.kind = "funded"
    assert bot.take_profit() == 0
    bot.state.kind = "combine"
    assert bot.take_profit() == 600


def test_restart_same_day_keeps_day_start_and_best_day():
    s = guard.ChallengeState(start_balance=50000.0, eod_high=50000.0)
    guard.new_day(s, "2026-10-27", 49560.68)
    guard.new_day(s, "2026-10-27", 49833.80)       # restart after a +273.12 day
    assert s.day_start_balance == 49560.68
    guard.new_day(s, "2026-10-28", 49833.80)
    assert abs(s.best_day - 273.12) < 1e-6
