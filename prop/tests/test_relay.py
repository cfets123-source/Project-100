"""Accounts at other firms traded through a webhook relay (Lucid etc.)."""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import relay  # noqa: E402
import worker  # noqa: E402
from test_fleet import Acct, FakeMultiAPI, fleet  # noqa: E402
from test_prop import FakeOpener, run_day, trading_days  # noqa: E402
from topstepx import BUY, SELL, TopstepXError  # noqa: E402

LUCID = {"firm": "Lucid", "name": "LUCID-50K-FLEX-1", "size_k": 50, "kind": "combine", "start_balance": 50000,
         "ticker": "MNQZ2026", "secret": "p100-relay-lucid-1", "rules": {"consistency": 0.4}}


class Hook:
    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=10):
        self.calls.append(json.loads(req.data.decode()))

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(b"ok")


def test_book_tracks_position_and_realized_pnl(tmp_path):
    px = [100.0]
    hook = Hook()
    r = relay.RelayAPI(LUCID, lambda: px[0], str(tmp_path), "https://hook.test/x", hook)
    r.market(None, None, BUY, 2, tag="t1")
    px[0] = 105.0
    r.market(None, None, SELL, 2, tag="t2")
    assert r.book["pos"] == 0 and abs(r.book["realized"] - (20 - 4 * 0.37)) < 1e-9
    assert [c["action"] for c in hook.calls] == ["buy", "sell"] and hook.calls[0]["ticker"] == "MNQZ2026"
    r.market(None, None, SELL, 1, tag="t3")
    px[0] = 103.0
    r.close(None, None)
    assert hook.calls[-1]["action"] == "exit" and r.book["pos"] == 0
    assert abs(r.balance() - (50000 + 20 - 4 * 0.37 + 4 - 2 * 0.37)) < 1e-9
    again = relay.RelayAPI(LUCID, lambda: px[0], str(tmp_path))          # book survives a restart
    assert again.book["realized"] == r.book["realized"]
    try:
        again.market(None, None, BUY, 1, tag="t1")
        assert False, "duplicate tag must be refused"
    except TopstepXError:
        pass


def test_relay_failure_is_an_api_problem(tmp_path):
    def broken(req, timeout=10):
        raise OSError("down")
    r = relay.RelayAPI(LUCID, lambda: 100.0, str(tmp_path), "https://hook.test/x", broken)
    try:
        r.market(None, None, BUY, 1, tag="x")
        assert False
    except TopstepXError:
        assert r.book["pos"] == 0      # nothing booked when the order did not go out


def test_fleet_trades_topstep_and_relay_accounts_together(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    hook, opener = Hook(), FakeOpener()
    api.now = worker.dt.datetime.combine(worker.dt.date(2026, 9, 1), worker.dt.time(9, 25), worker.ET)
    f = worker.Fleet(api, "ALL", True, home=str(tmp_path), clock=lambda: api.now,
                     feed=worker.Feed(url="https://example.test/prop/feed", token="tok", opener=opener),
                     relays=[LUCID], secret_fn=lambda name: "https://hook.test/x", relay_opener=hook)
    assert [b.firm for b in f.bots] == ["Topstep", "Lucid"]
    lucid = f.bots[1]
    assert lucid.state.kind == "combine" and lucid.state.consistency == 0.4 and lucid.estimated
    for d in sorted(api.days)[25:40]:
        run_day(f, api, d)
        assert lucid.api.book["pos"] == 0, "relay account must be flat after the close"
    assert hook.calls and {c["action"] for c in hook.calls} <= {"buy", "sell", "exit"}
    topstep_orders = [o for o in api.orders if o[0] == 1]
    assert len(hook.calls) >= len(topstep_orders) > 0      # same signal on both firms
    last = opener.bodies[-1]
    assert [(a["firm"], a["estimated"]) for a in last["accounts"]] == [("Topstep", False), ("Lucid", True)]


def test_relay_without_webhook_is_dry_run(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    hook = Hook()
    api.now = worker.dt.datetime.combine(worker.dt.date(2026, 9, 1), worker.dt.time(9, 25), worker.ET)
    f = worker.Fleet(api, "ALL", True, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[LUCID], secret_fn=lambda name: None, relay_opener=hook)
    for d in sorted(api.days)[25:32]:
        run_day(f, api, d)
    assert hook.calls == [] and f.bots[1].orders is False and api.orders
