"""Multi-account trading and the consistency rule."""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import guard  # noqa: E402
import worker  # noqa: E402
from test_prop import FakeOpener, run_day, trading_days  # noqa: E402
from topstepx import TopstepXError  # noqa: E402

ET = worker.ET


class Acct:
    def __init__(self, aid, name, balance, simulated=True, can_trade=True):
        self.aid, self.name, self.bal, self.sim, self.can = aid, name, balance, simulated, can_trade
        self.pos, self.avg = 0, None


class FakeMultiAPI:
    """Several accounts on one login sharing one price feed."""

    def __init__(self, days, accts):
        self.days, self.now, self.accts = days, None, {a.aid: a for a in accts}
        self.orders, self.tags, self.bar_calls, self.fail_on = [], set(), 0, None

    def accounts(self):
        return [{"id": a.aid, "name": a.name, "balance": a.bal, "canTrade": a.can, "simulated": a.sim}
                for a in self.accts.values()]

    def contract(self, symbol="MNQ", live=False):
        return {"id": "CON.F.US.MNQ.Z26", "tickSize": 0.25, "tickValue": 0.5, "activeContract": True, "name": "MNQZ6"}

    def bars(self, cid, start, end, **k):
        self.bar_calls += 1
        s, e, out = worker.to_et(start), worker.to_et(end), []
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
        a = self.accts[aid]
        if not a.pos:
            return []
        return [{"contractId": "CON.F.US.MNQ.Z26", "type": 1 if a.pos > 0 else 2, "size": abs(a.pos), "averagePrice": a.avg}]

    def _fill(self, a, delta):
        px = self.last_price()
        if a.pos + delta == 0:
            a.bal += (px - a.avg) * a.pos * 2
            a.pos, a.avg = 0, None
        else:
            a.avg = px if not a.pos else a.avg
            a.pos += delta

    def market(self, aid, cid, side, size, tag=None):
        if self.fail_on == aid:
            raise TopstepXError("network: timeout")
        assert tag not in self.tags, "duplicate tag across accounts"
        self.tags.add(tag)
        self._fill(self.accts[aid], size if side == 0 else -size)
        self.orders.append((aid, side, size, tag))

    def close(self, aid, cid):
        a = self.accts[aid]
        if a.pos:
            self._fill(a, -a.pos)


def fleet(tmp_path, api, selector="ALL", orders=True, feed=None):
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    return worker.Fleet(api, selector, orders, home=str(tmp_path), clock=lambda: api.now,
                        feed=feed or worker.Feed(token=""))


def test_rules_scale_with_account_size_and_type():
    assert guard.size_k("50KTC-SKU-V2-DLL-702120-18548271") == 50 and guard.size_k("150KTC-1") == 150
    assert guard.kind_for("50KTC-SKU-V2-DLL-702120-18548271") == "combine"
    assert guard.kind_for("EXPRESS-50K-1") == "funded" and guard.kind_for("50K-PRACTICE") == "practice"
    st = guard.apply_rules(guard.ChallengeState(150000, 150000), "150KTC-9")
    assert (st.target, st.mll, st.daily_stop) == (9000, 4500, 2400) and st.floor == 145500
    funded = guard.apply_rules(guard.ChallengeState(50000, 50000), "EXPRESS-50K-1")
    guard.new_day(funded, "2026-10-22", 54000)
    assert funded.required_target() is None and not funded.passed      # funded accounts keep trading


def test_consistency_rule_raises_target_instead_of_stopping_early():
    st = guard.apply_rules(guard.ChallengeState(50000, 50000), "50KTC-1")
    guard.new_day(st, "2026-10-22", 50000)
    allowed, flat, _ = guard.check(st, 50000, 2000)          # one big day: +$2,000 would need a $4,000 target
    assert allowed and not flat and st.required_target(2000) == 4000
    guard.new_day(st, "2026-10-23", 52000)                    # yesterday's +$2,000 is remembered
    assert st.best_day == 2000
    assert guard.check(st, 52000, 1000)[0] is True            # +$3,000 total is not enough any more
    allowed, flat, why = guard.check(st, 52000, 2000)         # +$4,000 total passes
    assert not allowed and "target" in why and st.passed


def test_old_saved_state_loads_with_new_fields():
    old = {"start_balance": 50000.0, "eod_high": 50000.0, "day": "2026-10-22", "day_start_balance": 50000.0,
           "halted_day": "", "halted_reason": "", "passed": False, "finished": False, "notes": [], "unknown": 1}
    st = guard.apply_rules(guard.ChallengeState.from_dict(old), "50KTC-1")
    assert st.best_day == 0 and st.target == 3000


def test_select_accounts_never_trades_live_or_disabled_accounts():
    accts = [{"id": 1, "name": "50KTC-A", "canTrade": True, "simulated": True},
             {"id": 2, "name": "EXPRESS-50K-B", "canTrade": True, "simulated": True},
             {"id": 3, "name": "LIVE-50K-C", "canTrade": True, "simulated": False},
             {"id": 4, "name": "50KTC-D", "canTrade": False, "simulated": True},
             {"id": 5, "name": "50K-PRACTICE", "canTrade": True, "simulated": True}]
    assert [a["id"] for a in worker.select_accounts(accts, "ALL")] == [1, 2]
    assert [a["id"] for a in worker.select_accounts(accts, "50k")] == [1, 2, 5]
    assert [a["id"] for a in worker.select_accounts(accts, "live,practice")] == [5]


def test_fleet_trades_every_account_with_its_own_size_and_is_flat_at_close(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0), Acct(2, "150KTC-B", 150000.0),
                                          Acct(3, "LIVE-50K", 50000.0, simulated=False)])
    f = fleet(tmp_path, api)
    assert [b.aid for b in f.bots] == [1, 2]
    for d in sorted(api.days)[25:40]:
        run_day(f, api, d)
        assert all(a.pos == 0 for a in api.accts.values()), d
    by = {aid: [s for a, _, s, _ in api.orders if a == aid] for aid in (1, 2, 3)}
    assert by[1] and by[2] and not by[3]
    assert max(by[1]) <= 4 and max(by[2]) > max(by[1]) and max(by[2]) <= 12
    assert len(api.tags) == len(api.orders)


def test_one_account_failing_does_not_stop_the_others(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0), Acct(2, "50KTC-B", 50000.0)])
    f = fleet(tmp_path, api)
    api.fail_on = 1
    for d in sorted(api.days)[25:35]:
        run_day(f, api, d)
    assert any(a == 2 for a, *_ in api.orders) and not any(a == 1 for a, *_ in api.orders)


def test_fleet_shares_market_data(tmp_path):
    accts = [Acct(i, "50KTC-%d" % i, 50000.0) for i in range(1, 5)]
    api = FakeMultiAPI(trading_days(45), accts)
    f = fleet(tmp_path, api)
    api.now = dt.datetime.combine(sorted(api.days)[30], dt.time(10, 31), ET)
    api.bar_calls = 0
    f.step()
    assert api.bar_calls <= 2   # history + today's bars once for all four accounts


def test_fleet_report_lists_every_account(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0), Acct(2, "EXPRESS-50K-B", 50000.0)])
    opener = FakeOpener()
    f = fleet(tmp_path, api, feed=worker.Feed(url="https://example.test/prop/feed", token="tok", opener=opener))
    for d in sorted(api.days)[25:28]:
        run_day(f, api, d)
    last = opener.bodies[-1]
    assert [a["account"] for a in last["accounts"]] == ["50KTC-A", "EXPRESS-50K-B"]
    assert last["accounts"][1]["status"]["kind"] == "funded" and last["accounts"][1]["status"]["target"] is None
    assert last["accounts"][0]["status"]["target"] >= 3000
    ids = [e["id"] for b in opener.bodies for e in b["events"]]
    assert len(ids) == len(set(ids)) and {e["account"] for b in opener.bodies for e in b["events"]} == {"50KTC-A", "EXPRESS-50K-B"}


def test_dry_run_fleet_places_no_orders(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0), Acct(2, "50KTC-B", 50000.0)])
    f = fleet(tmp_path, api, orders=False)
    for d in sorted(api.days)[25:32]:
        run_day(f, api, d)
    assert api.orders == []
    assert os.path.exists(os.path.join(str(tmp_path), "status-1.json"))


class CmdOpener(FakeOpener):
    """App feed that hands out the dashboard's "Close trade now" command until it is acknowledged."""

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def __call__(self, req, timeout=10):
        import io
        import json as _json
        r = super().__call__(req, timeout)
        ack = self.bodies[-1].get("ack")
        if ack and ack["id"] == self.cmd["id"]:
            self.cmd = dict(self.cmd, status="done")
        reply = {"ok": True, "command": self.cmd if self.cmd["status"] == "pending" else None}
        r.close()

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return R(_json.dumps(reply).encode())


def test_dashboard_close_button_closes_live_trades_once_and_trading_continues(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    opener = CmdOpener({"id": "abc123", "kind": "close_now", "status": "pending"})
    f = fleet(tmp_path, api, feed=worker.Feed(url="https://example.test/prop/feed", token="tok", opener=opener))
    d = sorted(api.days)[30]
    api.now = dt.datetime.combine(d, dt.time(11, 2), ET)
    f.step()                                        # picks up the command from the app's reply
    a = api.accts[1]
    a.pos, a.avg = 2, api.last_price() - 20         # an open trade
    api.now += dt.timedelta(minutes=1)
    f.step()                                        # acts on it, reports the ack in the same send
    assert a.pos == 0
    assert opener.bodies[-1]["ack"] == {"id": "abc123", "result": "closed 50KTC-A"}
    assert opener.cmd["status"] == "done" and f.feed.pending_ack is None
    import json as _json
    assert _json.load(open(tmp_path / "manual_closes.json"))[-1]["results"][0]["closed"]
    a.pos, a.avg = 1, api.last_price()              # a newer trade is never closed by the same command
    f.feed.command = {"id": "abc123", "kind": "close_now", "status": "pending"}
    api.now += dt.timedelta(minutes=1)
    f.step()
    assert a.pos == 1
    a.pos, a.avg = 0, None
    st = f.bots[0].state
    assert st.halted_day != d.isoformat() and not st.finished
    n = len(api.orders)
    for day in sorted(api.days)[31:36]:
        run_day(f, api, day)
    assert len(api.orders) > n and a.pos == 0       # the bot keeps trading afterwards


def test_close_button_skips_dry_run_accounts(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    f = fleet(tmp_path, api, orders=False)
    api.now = dt.datetime.combine(sorted(api.days)[30], dt.time(11, 2), ET)
    f.feed.command = {"id": "x1", "kind": "close_now", "status": "pending"}
    assert f.handle_command() == []
    assert f.feed.pending_ack == {"id": "x1", "result": "nothing open to close"}


def _bar_minutes(api, day):
    import re
    out = set()
    for _, _, _, tag in api.orders:
        m = re.search(r"-(\d{4})-[+-]\d$", tag or "")
        if m and tag.startswith("noise-") and day.isoformat() in tag:
            out.add(m.group(1)[2:])
    return out


def test_after_close_button_fast_checks_until_close_then_hourly_next_day(tmp_path):
    import noise
    api = FakeMultiAPI(trading_days(60), [Acct(1, "50KTC-A", 50000.0)])
    f = fleet(tmp_path, api)
    b, a = f.bots[0], api.accts[1]
    found = None
    for d in sorted(api.days)[25:58]:              # find a day where a fast check would act between hourly checks
        api.now = dt.datetime.combine(d, dt.time(9, 40), ET)
        f.step()
        a.pos, a.avg = 1, api.last_price()
        f.feed.command = {"id": "c-%s" % d, "kind": "close_now", "status": "pending"}
        f.step()
        assert a.pos == 0 and b.state.fast_day == d.isoformat() and b.last_status["fast"] is True
        run_day(f, api, d)
        if _bar_minutes(api, d) - {"55"}:
            found = d
            break
    assert found, "fast mode never placed an order off the hourly schedule"
    nxt = sorted(api.days)[sorted(api.days).index(found) + 1]
    run_day(f, api, nxt)
    assert _bar_minutes(api, nxt) <= {"55"} and b.last_status["fast"] is False   # hourly again the next day
    assert noise.decide([], {}, dt.time(10, 20), 0, fast=True) is None


def test_dry_run_position_survives_a_restart_the_same_day_only(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    f = fleet(tmp_path, api, orders=False)
    b = f.bots[0]
    d = sorted(api.days)[30]
    api.now = dt.datetime.combine(d, dt.time(11, 2), ET)
    b.go_to(1, 21000.0, "test", None)
    b.save()
    f2 = worker.Fleet(api, "ALL", False, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""))
    assert f2.bots[0].position() == (b.position()[0], 21000.0) and b.position()[0] > 0
    api.now = dt.datetime.combine(sorted(api.days)[31], dt.time(9, 40), ET)
    f3 = worker.Fleet(api, "ALL", False, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""))
    assert f3.bots[0].position() == (0, None)
    assert api.orders == []


def test_explicit_rejection_retries_with_a_new_tag_but_lost_reply_keeps_it(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    f = fleet(tmp_path, api)
    real, burned = api.market, []

    def flaky(aid, cid, side, size, tag=None):
        if not burned:                      # TopstepX 2026-11-05: rejects, but the tag counts as used
            burned.append(tag)
            api.tags.add(tag)
            raise TopstepXError("/api/Order/place failed: code 2 Trading is currently unavailable. "
                                "The instrument is not in an active trading status.")
        return real(aid, cid, side, size, tag=tag)
    api.market = flaky
    for d in sorted(api.days)[25:45]:
        run_day(f, api, d)
        if api.orders:
            break
    assert burned and api.orders, "the bot never traded"
    first = api.orders[0][3]
    assert first == burned[0] + "-r1", (first, burned)        # same decision, retried with a fresh tag
    assert sum(1 for o in api.orders if o[3].startswith(burned[0])) == 1   # exactly one order for that decision


def test_rejected_orders_are_not_logged_as_trades(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    f = fleet(tmp_path, api)
    real, fails = api.market, []

    def flaky(aid, cid, side, size, tag=None):
        if len(fails) < 3:                              # three rejections in a row, like 11/05
            fails.append(tag)
            raise TopstepXError("/api/Order/place failed: code 2 Trading is currently unavailable. "
                                "The instrument is not in an active trading status.")
        return real(aid, cid, side, size, tag=tag)
    api.market = flaky
    b, logged = f.bots[0], []
    orig = b.event
    b.event = lambda kind, text, *a, **k: (logged.append((kind, text)), orig(kind, text, *a, **k))[1]
    for d in sorted(api.days)[25:45]:
        run_day(f, api, d)
        if api.orders:
            break
    entries = [t for k, t in logged if k in ("buy", "sell")]
    assert len(fails) == 3 and api.orders
    assert len(entries) == sum(1 for o in api.orders if o[3] and o[3].startswith("noise-")), entries
    assert all(" MNQ at " in t for t in entries)
