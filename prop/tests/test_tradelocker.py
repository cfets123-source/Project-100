"""TradeLocker (Eightcap Challenges) accounts: client protocol, static loss limit, news blackout, fleet integration."""
import datetime as dt
import io
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import guard  # noqa: E402
import news  # noqa: E402
import tradelocker as tlmod  # noqa: E402
import worker  # noqa: E402
from test_fleet import Acct, FakeMultiAPI  # noqa: E402
from test_prop import run_day, trading_days  # noqa: E402

ET = worker.ET
POS_COLS = ["id", "tradableInstrumentId", "routeId", "side", "qty", "avgPrice", "stopLossId", "takeProfitId",
            "openDate", "unrealizedPl", "strategyId"]
ORD_COLS = ["id", "tradableInstrumentId", "routeId", "qty", "side", "type", "status", "filledQty", "avgPrice", "price",
            "stopPrice", "validity"]
ACC_COLS = ["balance", "projectedBalance", "availableFunds", "todayNet", "positionsCount", "ordersCount"]


class FakeTL:
    """In-memory TradeLocker backend for one account and one US100 CFD (pv $1/point/lot)."""

    def __init__(self, price_fn, balance=5000.0, hedging=True):
        # hedging=True copies the real Eightcap account (2026-11-05): every order opens its own position
        self.price_fn, self.bal, self.hedging = price_fn, balance, hedging
        self.pos = {}      # id -> [side, qty, avg]
        self.ord = {}      # id -> [side, qty, price]
        self.n, self.calls, self.placed = 100, [], []

    def _fill(self, side, qty, px, closing=False):
        if self.hedging and not closing:
            self.n += 1
            self.pos[self.n] = [side, qty, px]
            return
        net = sum(q if s == "buy" else -q for s, q, _ in self.pos.values())
        d = qty if side == "buy" else -qty
        if net and (net > 0) != (d > 0):     # reduce / close (net position)
            (pid, (s, q, avg)), = self.pos.items()
            closed = min(abs(d), q)
            self.bal += (px - avg) * closed * (1 if s == "buy" else -1)
            if abs(q - closed) < 1e-9:
                del self.pos[pid]
            else:
                self.pos[pid][1] = round(q - closed, 8)
            rest = abs(d) - closed
            if rest > 1e-9:
                self.n += 1
                self.pos[self.n] = [side, rest, px]
        elif net:
            (pid, (s, q, avg)), = self.pos.items()
            self.pos[pid] = [s, q + qty, (avg * q + px * qty) / (q + qty)]
        else:
            self.n += 1
            self.pos[self.n] = [side, qty, px]

    @property
    def max_sides(self):
        return self._max_sides

    def _track(self):
        self._max_sides = max(getattr(self, "_max_sides", 0), len({s for s, _, _ in self.pos.values()}))

    def _touch(self):
        self._track()
        px = self.price_fn()
        for oid, (side, qty, lim) in list(self.ord.items()):
            if (side == "sell" and px >= lim) or (side == "buy" and px <= lim):
                del self.ord[oid]
                self._fill(side, qty, lim)

    def __call__(self, req, timeout=20):
        u = urllib.parse.urlparse(req.full_url)
        path, q = u.path.replace("/backend-api", ""), dict(urllib.parse.parse_qsl(u.query))
        body = json.loads(req.data.decode()) if req.data else None
        m = req.get_method()
        self.calls.append((m, path, dict(req.header_items()), body))
        if path != "/auth/jwt/token":
            assert req.get_header("Authorization") == "Bearer A"
        if path.startswith("/trade/"):
            assert req.get_header("Accnum") == "1"
        self._touch()
        px = self.price_fn()
        if path == "/auth/jwt/token":
            assert body == {"email": "me@x.com", "password": "pw", "server": "EIGHTCAP-DEMO"}
            out = {"accessToken": "A", "refreshToken": "R"}
        elif path == "/auth/jwt/all-accounts":
            out = {"accounts": [{"id": 11, "accNum": 1, "name": "Eightcap 5K", "accountBalance": self.bal}]}
        elif path == "/trade/config":
            out = {"s": "ok", "d": {"positionsConfig": {"columns": [{"id": c} for c in POS_COLS]},
                                    "ordersConfig": {"columns": [{"id": c} for c in ORD_COLS]},
                                    "accountDetailsConfig": {"columns": [{"id": c} for c in ACC_COLS]}}}
        elif path == "/trade/accounts/11/instruments":
            out = {"s": "ok", "d": {"instruments": [{"tradableInstrumentId": 77, "name": "US100",
                                                     "routes": [{"id": 5, "type": "TRADE"}, {"id": 6, "type": "INFO"}]}]}}
        elif path == "/trade/accounts/11/state":
            out = {"s": "ok", "d": {"accountDetailsData": [self.bal, self.bal, self.bal, 0, len(self.pos), len(self.ord)]}}
        elif path == "/trade/accounts/11/positions" and m == "GET":
            out = {"s": "ok", "d": {"positions": [[pid, 77, 5, s, q, a, 0, 0, 0, 0, ""] for pid, (s, q, a) in self.pos.items()]}}
        elif path == "/trade/accounts/11/positions" and m == "DELETE":
            assert q["tradableInstrumentId"] == "77"
            for pid, (s, qty, a) in list(self.pos.items()):
                self.bal += (px - a) * qty * (1 if s == "buy" else -1)
                del self.pos[pid]
            out = {"s": "ok"}
        elif path == "/trade/accounts/11/orders" and m == "GET":
            out = {"s": "ok", "d": {"orders": [[oid, 77, 5, qq, s, "limit", "New", 0, 0, p, 0, "GTC"]
                                               for oid, (s, qq, p) in self.ord.items()]}}
        elif path == "/trade/accounts/11/orders" and m == "POST":
            assert body["routeId"] == 5 and body["tradableInstrumentId"] == "77"
            self.placed.append(body)
            self.n += 1
            if body["type"] == "market":
                assert body["validity"] == "IOC"
                self._fill(body["side"], float(body["qty"]), px)
            else:
                assert body["validity"] == "GTC" and body["price"]
                self.ord[self.n] = [body["side"], float(body["qty"]), float(body["price"])]
            out = {"s": "ok", "d": {"orderId": str(self.n)}}
        elif path.startswith("/trade/orders/") and m == "DELETE":
            self.ord.pop(int(path.rsplit("/", 1)[1]), None)
            out = {"s": "ok"}
        elif path == "/trade/quotes":
            assert q["routeId"] == "6"
            out = {"s": "ok", "d": {"ap": px + 0.5, "bp": px - 0.5}}
        else:
            raise AssertionError("unexpected %s %s" % (m, path))

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        self._track()
        return R(json.dumps(out).encode())


CFG = {"firm": "Eightcap", "name": "EIGHTCAP-5K-1", "env": "demo", "server": "EIGHTCAP-DEMO", "email": "me@x.com",
       "secret": "p100-tl-eightcap-1", "acc_num": 1, "symbol": "US100", "start_balance": 5000, "kind": "combine",
       "leverage": 3, "point_value": 1.0, "tick": 0.01, "orders": True,
       "rules": {"target": 500, "mll": 400, "daily_stop": 150, "mll_buffer": 60, "static_mll": True, "consistency": 1.0}}


class NoNews:
    def __init__(self):
        self.windows = []

    def blocked(self, now):
        for a, b in self.windows:
            if a <= now <= b:
                return True, "news: test"
        return False, ""


def test_client_protocol():
    fake = FakeTL(lambda: 25000.0)
    tl = tlmod.TradeLocker("me@x.com", "pw", "EIGHTCAP-DEMO", "demo", opener=fake)
    assert tl.select(1)["id"] == 11
    ins = tl.instrument(("US100",))
    acct = tlmod.TradeLockerAccount(tl, CFG, ins)
    acct.cid = "MNQ"
    assert acct.account()["balance"] == 5000.0 and acct.positions() == []
    acct.market(None, None, worker.BUY, 0.6, tag="noise-x")
    (p,) = acct.positions()
    assert p["type"] == worker.LONG and abs(p["size"] - 0.6) < 1e-9 and p["averagePrice"] == 25000.0
    oid = acct.limit(None, None, worker.SELL, 0.6, 25131.5)
    (o,) = acct.open_orders()
    assert o["id"] == oid and o["side"] == worker.SELL and o["limitPrice"] == 25131.5 and o["type"] == worker.LIMIT
    acct.cancel(None, oid)
    assert acct.open_orders() == []
    acct.close(None, None)
    assert acct.positions() == []
    assert abs(acct.price() - 25000.0) < 1e-9


def test_static_loss_limit_does_not_trail():
    s = guard.ChallengeState(start_balance=5000.0, eod_high=5000.0)
    guard.apply_rules(s, "EIGHTCAP-5K-1", "combine", CFG["rules"])
    guard.new_day(s, "2026-11-02", 5300.0)
    guard.new_day(s, "2026-11-03", 5350.0)
    assert s.static_mll and s.floor == 4600.0       # Topstep would trail to 4,950
    t = guard.ChallengeState(start_balance=50000.0, eod_high=50000.0)
    guard.new_day(t, "2026-11-02", 51000.0)
    guard.new_day(t, "2026-11-03", 51000.0)
    assert t.floor == 49000.0 and not t.static_mll  # Topstep: trails the EOD high


def test_news_calendar_and_fallback(tmp_path):
    feed = [{"title": "FOMC Statement", "country": "USD", "impact": "High", "date": "2026-11-04T14:00:00-05:00"},
            {"title": "Minor", "country": "USD", "impact": "Low", "date": "2026-11-04T10:00:00-05:00"},
            {"title": "ECB", "country": "EUR", "impact": "High", "date": "2026-11-04T08:15:00-05:00"}]

    def ok(req, timeout=15):
        return io.BytesIO(json.dumps(feed).encode())
    cal = news.NewsCalendar(str(tmp_path), ET, opener=ok)
    at = lambda h, m: dt.datetime(2026, 11, 4, h, m, tzinfo=ET)  # noqa: E731
    assert cal.blocked(at(13, 52))[0] and cal.blocked(at(14, 10))[0]
    assert not cal.blocked(at(13, 45))[0] and not cal.blocked(at(10, 0))[0] and not cal.blocked(at(14, 15))[0]

    def down(req, timeout=15):
        raise OSError("offline")
    cal2 = news.NewsCalendar(str(tmp_path / "x"), ET, opener=down)
    os.makedirs(str(tmp_path / "x"))
    assert cal2.blocked(at(10, 5))[0] and cal2.blocked(at(13, 55))[0] and not cal2.blocked(at(11, 0))[0]


def make_fleet(tmp_path, nonews=None, cfg=None):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)
    def px():
        try:
            return api.last_price() - 100.0
        except ValueError:   # before the first bar of the day
            return 25000.0
    fake = FakeTL(px)

    def factory(email, pw, server, env):
        return tlmod.TradeLocker(email, pw, server, env, opener=fake)
    f = worker.Fleet(api, "ALL", True, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[], secret_fn=lambda name: "pw", tl_configs=[cfg or CFG], tl_factory=factory,
                     news=nonews or NoNews())
    return api, fake, f


def test_fleet_trades_eightcap_alongside_topstep(tmp_path):
    api, fake, f = make_fleet(tmp_path)
    assert [b.firm for b in f.bots] == ["Topstep", "Eightcap"]
    ec = f.bots[1]
    assert ec.state.static_mll and ec.state.target == 500 and ec.orders
    assert ec.size_k == 5 and f.bots[0].size_k == 50   # dashboard label "Eval 5K"
    for d in sorted(api.days)[25:40]:
        run_day(f, api, d)
        assert fake.pos == {} and fake.ord == {}, "Eightcap account must be flat with no orders after %s" % d
    mk = [b for b in fake.placed if b["type"] == "market"]
    assert mk and api.orders, "both firms trade the same signals"
    assert all(0.01 <= float(b["qty"]) <= 2.0 and abs(float(b["qty"]) * 100 - round(float(b["qty"]) * 100)) < 1e-6 for b in mk)
    assert not any(b["type"] == "limit" for b in fake.placed), "no resting limit on a hedging account"
    assert fake.max_sides == 1, "the account never held buy and sell positions at the same time"


def test_news_window_blocks_eightcap_orders_only(tmp_path):
    nn = NoNews()
    api, fake, f = make_fleet(tmp_path, nn)
    days = sorted(api.days)[25:40]
    for d in days:
        nn.windows = [(dt.datetime.combine(d, dt.time(9, 25), ET), dt.datetime.combine(d, dt.time(16, 5), ET))]
        run_day(f, api, d)
    assert [b for b in fake.placed if b["type"] == "market"] == [], "no Eightcap orders inside news windows"
    assert api.orders, "Topstep keeps trading"


def test_tradelocker_problem_never_stops_topstep(tmp_path):
    api = FakeMultiAPI(trading_days(45), [Acct(1, "50KTC-A", 50000.0)])
    api.now = dt.datetime.combine(dt.date(2026, 9, 1), dt.time(9, 25), ET)

    def broken(email, pw, server, env):
        raise ValueError("login rejected")
    f = worker.Fleet(api, "ALL", True, home=str(tmp_path), clock=lambda: api.now, feed=worker.Feed(token=""),
                     relays=[], secret_fn=lambda name: "pw", tl_configs=[CFG], tl_factory=broken, news=NoNews())
    assert [b.firm for b in f.bots] == ["Topstep"]


def test_minimum_trading_days_hold_after_target(tmp_path):
    from test_prop import FakeAPI, make_bot
    api = FakeAPI(trading_days(45))
    bot = make_bot(tmp_path, api)
    bot.state.kind, bot.state.target, bot.state.min_days, bot.state.consistency = "combine", 1.0, 4, 1.0
    days = sorted(api.days)[25:40]
    for d in days:
        run_day(bot, api, d)
        assert api.pos == 0
        if bot.state.passed:
            break
    assert bot.state.passed and len(bot.state.trade_days) >= 4
    holds = [o for o in api.orders if (o[2] or "").startswith("minday-")]
    assert all(o[1] == 1 for o in holds), "hold-mode trades are the minimum size"
    assert len(set(o[2] for o in holds)) == len(holds), "at most one per day"


def test_no_minimum_days_rule_for_topstep(tmp_path):
    s = guard.ChallengeState(start_balance=50000.0, eod_high=50000.0)
    guard.new_day(s, "2026-11-02", 52000.0)          # earlier days made +2,000; today +1,100 (consistency OK)
    ok, flat, why = guard.check(s, 53100.0, 0.0)
    assert s.passed and not s.target_hit and s.min_days == 0



def _tl_acct(fake):
    tl = tlmod.TradeLocker("me@x.com", "pw", "EIGHTCAP-DEMO", "demo", opener=fake)
    tl.select(1, None)
    instr = tl.instrument(("US100",))
    return tlmod.TradeLockerAccount(tl, CFG, instr)


def test_tl_test_round_trip_passes_and_leaves_account_flat():
    import tl_test
    fake = FakeTL(lambda: 21000.0)                 # hedging account, like the real one
    acct = _tl_acct(fake)
    ok, steps = tl_test.run_test(acct, sleep=lambda s: None, say=lambda s: None)
    assert ok, steps
    assert fake.pos == {} and fake.ord == {} and fake.max_sides == 1
    assert not any(b["type"] == "limit" for b in fake.placed)


def test_tl_test_catches_a_hedging_bug():
    import tl_test
    fake = FakeTL(lambda: 21000.0)
    acct = _tl_acct(fake)
    acct.market = lambda aid, cid, side, size, tag=None: acct.tl.place(acct.instr, "buy" if side == worker.BUY else "sell", size)
    ok, steps = tl_test.run_test(acct, sleep=lambda s: None, say=lambda s: None)
    assert not ok and fake.pos == {}               # fails at step 3 and still cleans up both sides


def test_tl_test_refuses_an_account_in_use():
    import tl_test
    fake = FakeTL(lambda: 21000.0)
    acct = _tl_acct(fake)
    acct.market(acct.aid, None, worker.BUY, 0.05)
    n = len(fake.placed)
    ok, steps = tl_test.run_test(acct, sleep=lambda s: None, say=lambda s: None)
    assert not ok and len(fake.placed) == n and fake.pos   # nothing placed, the existing trade untouched


def test_rate_limit_429_waits_and_retries():
    import urllib.error
    fake = FakeTL(lambda: 21000.0)
    calls = {"n": 0}

    def flaky(req, timeout=20):
        if "/orders" in req.full_url and req.get_method() == "GET" and calls["n"] < 2:
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
        return fake(req, timeout)
    slept = []
    tl = tlmod.TradeLocker("me@x.com", "pw", "EIGHTCAP-DEMO", "demo", opener=flaky, sleep=slept.append)
    tl.select(1, None)
    assert tl.orders() == [] and slept == [2, 4]


def test_tl_test_cleanup_flattens_hedged_positions(monkeypatch):
    import tl_test
    monkeypatch.setattr(tl_test.time, "sleep", lambda s: None)
    fake = FakeTL(lambda: 21000.0)
    acct = _tl_acct(fake)
    acct.tl.place(acct.instr, "buy", 0.03)
    acct.tl.place(acct.instr, "sell", 0.03)      # net zero, two real positions (the 11/05 situation)
    acct.tl.place(acct.instr, "buy", 0.01, "limit", 20000.0)
    assert tl_test.cleanup(acct, say=lambda s: None) and fake.pos == {} and fake.ord == {}


def test_hedged_leftovers_are_flattened_before_any_new_trade():
    fake = FakeTL(lambda: 21000.0)
    acct = _tl_acct(fake)
    acct.tl.place(acct.instr, "buy", 0.03)
    acct.tl.place(acct.instr, "sell", 0.03)
    try:
        acct.positions()
        raise AssertionError("expected an error")
    except tlmod.TopstepXError as e:
        assert "hedging" in str(e)
    assert fake.pos == {}


def _funded_state():
    st = guard.ChallengeState(start_balance=5000.0, eod_high=5000.0)
    rules = {"mll": 400, "daily_stop": 150, "mll_buffer": 60, "static_mll": True, "consistency": 1.0, "min_days": 0,
             "cycle_cap": 250, "cycle_days": 14, "payout_min_days": 7, "payout_day_share": 0.30, "payout_split": 0.8}
    return guard.apply_rules(st, "EIGHTCAP-5K-F", "funded", rules)


def test_payout_stage_stops_at_the_cap_and_needs_seven_days():
    st = _funded_state()
    guard.new_day(st, "2026-12-01", 5000.0)
    assert st.cycle_start == "2026-12-01" and st.target is None
    st.trade_days = ["2026-12-01", "2026-12-02"]
    allowed, flat, why = guard.check(st, 5000.0, 260.0)            # above the 5% cap after 2 trading days
    assert not allowed and flat and "2 of 7" in why and st.target_hit and st.cap_hit
    st.trade_days += ["2026-12-03", "2026-12-04", "2026-12-05", "2026-12-08", "2026-12-09"]
    allowed, flat, why = guard.check(st, 5260.0, 0.0)
    assert not allowed and "request the payout" in why
    assert st.payout_ready("2026-12-09", 5260.0)


def test_payable_applies_cap_and_best_day_rule():
    st = _funded_state()
    guard.new_day(st, "2026-12-01", 5000.0)
    st.cycle_best_day = 150.0                                        # one day made 150 of 200 (75% > 30%)
    gross, mine = st.payable(5200.0)
    assert gross == round(200 - (150 - 0.3 * 200), 2) and mine == round(gross * 0.8, 2)
    st.cycle_best_day = 50.0
    assert st.payable(5400.0) == (250.0, 200.0)                      # capped at 5%


def test_new_cycle_after_the_firm_resets_the_account():
    st = _funded_state()
    guard.new_day(st, "2026-12-01", 5000.0)
    st.cap_hit, st.payout_notified = True, "2026-12-01"
    guard.new_day(st, "2026-12-16", 5000.0)                          # payout paid, balance back to start
    assert st.cycle_start == "2026-12-16" and not st.cap_hit and st.cycle_best_day == 0.0
    allowed, _, _ = guard.check(st, 5000.0, 0.0)
    assert allowed


def test_payout_ready_after_fourteen_days_with_profit():
    st = _funded_state()
    guard.new_day(st, "2026-12-01", 5000.0)
    st.trade_days = ["2026-12-%02d" % d for d in range(1, 9)]
    assert not st.payout_ready("2026-12-10", 5100.0)                 # only 9 days old
    assert st.payout_ready("2026-12-15", 5100.0)
    assert not st.payout_ready("2026-12-15", 4990.0)                 # nothing to pay


def test_funded_eightcap_stops_at_the_payout_cap_and_tells_the_owner(tmp_path):
    cfg = dict(CFG, name="EIGHTCAP-5K-F", kind="funded", leverage=1.5,
               rules={"mll": 400, "daily_stop": 150, "mll_buffer": 60, "static_mll": True, "consistency": 1.0,
                      "min_days": 0, "cycle_cap": 5, "cycle_days": 14, "payout_min_days": 1, "payout_day_share": 0.3})
    api, fake, f = make_fleet(tmp_path, cfg=cfg)
    ec = f.bots[1]
    assert ec.state.kind == "funded" and ec.state.cycle_cap == 5 and ec.state.target is None
    msgs, orig = [], ec.event

    def spy(kind, text, *a, **k):
        if "Payout ready" in text:
            msgs.append(text)
        return orig(kind, text, *a, **k)
    ec.event = spy
    for d in sorted(api.days)[25:45]:
        run_day(f, api, d)
        assert fake.pos == {} and fake.max_sides == 1, d
        if ec.state.cap_hit:
            break
    assert ec.state.cap_hit and len(msgs) == 1, msgs
    n = len(fake.placed)
    run_day(f, api, sorted(api.days)[sorted(api.days).index(d) + 1])     # cap hit, no payout yet: no new trades
    assert len(fake.placed) == n and fake.pos == {}
