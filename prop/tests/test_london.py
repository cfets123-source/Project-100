"""London pre-market drift dry run: never trades, logs entries/exits, survives errors."""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import london  # noqa: E402
import worker  # noqa: E402
from test_fleet import Acct, FakeMultiAPI  # noqa: E402
from test_prop import run_day, trading_days  # noqa: E402

ET = worker.ET


def with_premarket(days):
    """Add 7:55 and 9:20 bars to every day: pre-market drifts up from the prior close on even days."""
    out, prev = {}, None
    for i, d in enumerate(sorted(days)):
        day = dict(days[d])
        base = prev if prev else day[dt.time(9, 30)][0]
        move = 1.003 if i % 2 == 0 else 0.997
        p755 = base * move
        p920 = p755 * (1.001 if i % 2 == 0 else 0.999)       # drift continues -> the dry run wins
        day[dt.time(7, 55)] = (p755, p755, p755, p755, 100)
        day[dt.time(9, 20)] = (p920, p920, p920, p920, 100)
        out[d] = day
        prev = day[dt.time(15, 55)][3]
    return out


def test_london_dry_run_logs_and_never_orders(tmp_path):
    api = FakeMultiAPI(with_premarket(trading_days(45)), [Acct(1, "50KTC-A", 50000.0)])
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(7, 45), ET)
    f = worker.Fleet(api, "ALL", False, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[])
    days = sorted(api.days)[25:30]
    for d in days:
        for minute in range(0, 160):
            api.now = dt.datetime.combine(d, dt.time(7, 45), ET) + dt.timedelta(minutes=minute)
            f.step()
    assert api.orders == []
    log = json.load(open(os.path.join(str(tmp_path), "london.json")))
    assert [r["date"] for r in log] == [d.isoformat() for d in days]
    assert all(r["pnl"] > 0 for r in log)
    kinds = [e["kind"] for e in f.bots[0].events]
    assert kinds.count("london") == 2 * len(days)


def test_london_problem_never_stops_trading(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    f = worker.Fleet(api, "ALL", True, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[])

    def boom(now):
        raise RuntimeError("bad data")
    f.london.step = boom
    for d in sorted(api.days)[25:35]:
        run_day(f, api, d)
    assert api.orders


def test_london_skips_a_late_start(tmp_path):
    api = FakeMultiAPI(with_premarket(trading_days(45)), [Acct(1, "50KTC-A", 50000.0)])
    d = sorted(api.days)[30]
    api.now = dt.datetime.combine(d, dt.time(8, 40), ET)
    f = worker.Fleet(api, "ALL", False, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[])
    for minute in range(0, 60):
        api.now = dt.datetime.combine(d, dt.time(8, 40), ET) + dt.timedelta(minutes=minute)
        f.step()
    assert not os.path.exists(os.path.join(str(tmp_path), "london.json"))
