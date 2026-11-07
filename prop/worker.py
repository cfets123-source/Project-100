"""Prop-challenge bot: NOISE intraday momentum on micro Nasdaq futures (MNQ) in a TopstepX account.

Runs on the owner's own computer (Topstep forbids placing orders from a VPS/remote server).
Default is DRY RUN: it reads real prices and the real account but only logs what it would do.
Real orders need --orders. Credentials come from the macOS Keychain (install.sh) or the environment.

    python3 worker.py --check                      # sign in, list accounts, contract, recent bars; no orders
    python3 worker.py --account PRACTICE           # dry run on the account whose name contains PRACTICE
    python3 worker.py --account 50K --orders       # live orders on the challenge account
    python3 worker.py --account ALL --orders       # every Combine/funded account on the login (never Live/practice)
"""
import argparse
import datetime as dt
import math
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard import ChallengeState, apply_rules, check, new_day, size_k  # noqa: E402
from noise import LAST, OPEN, decide, is_check, is_fast_check, vol_scale  # noqa: E402
from topstepx import LIMIT, BUY, LONG, SELL, TopstepX, TopstepXError  # noqa: E402
import relay as relaymod  # noqa: E402
import london as londonmod  # noqa: E402
import news as newsmod  # noqa: E402
import tradelocker as tlmod  # noqa: E402

ET = ZoneInfo("America/New_York")
HOME = os.path.expanduser("~/.p100-prop")
REJECTED_MSGS = ("not in an active trading status", "Trading is currently unavailable")  # TopstepX, 2026-11-05
MIRROR = os.path.expanduser("~/Documents/p100-prop/data")  # best-effort copy Claude can read (macOS may block it)
TARGET_NOTIONAL = 100000.0  # per $50K of account size: "size 2" in the challenge test = 2 x $50K of Nasdaq exposure
MAX_CONTRACTS_PER_50K = 3     # before volatility scaling
MAX_SCALED_PER_50K = 4        # after volatility scaling (Topstep 50K allows 50 micros)
FUNDED_ROOM_PER_CONTRACT = 2500.0  # funded accounts: one contract per $2,500 of room above the loss limit
# Aggressive mode (research/20261022-ladder rounds 4-6): bigger size, replace what fails. Turned on with AGGRESSIVE=1 in
# ~/.p100-prop/config (or --aggressive). Evaluations: 4 contracts per $50K (x volatility, up to 8); funded: 2 per $50K.
AGGR_EVAL_PER_50K, AGGR_FUNDED_PER_50K, AGGR_MAX_PER_50K, AGGR_DAILY_STOP_PER_50K = 4, 2, 8, 950.0
# Combine only (research/20261027-takeprofit): bank the trade at +$600 per $50K, re-enter at the next hourly check
TAKE_PROFIT_PER_50K = 600.0
FLATTEN_AT = dt.time(15, 55)
log = logging.getLogger("prop")


def keychain(service):
    try:
        return subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def credentials():
    user = os.environ.get("TOPSTEPX_USER") or keychain("p100-topstepx-user")
    key = os.environ.get("TOPSTEPX_KEY") or keychain("p100-topstepx-key")
    if not user or not key:
        sys.exit("TopstepX credentials not found. Run install.sh first.")
    return user, key


def flatten_time(day):
    """15:55 ET, or 12:55 ET on CME early-close days (Jul 3, day after Thanksgiving, Dec 24)."""
    thanksgiving = max(d for d in (dt.date(day.year, 11, x) for x in range(22, 29)) if d.weekday() == 3)
    early = {dt.date(day.year, 7, 3), thanksgiving + dt.timedelta(days=1), dt.date(day.year, 12, 24)}
    return dt.time(12, 55) if day in early else FLATTEN_AT


class Feed:
    """Reports status to the Veloikos app (display only). Failures never affect trading."""

    def __init__(self, url=None, token=None, opener=None):
        self.url = url or os.environ.get("PROP_FEED_URL") or "https://trade.veloikos.com/prop/feed"
        self.token = token if token is not None else (os.environ.get("PROP_FEED_TOKEN") or keychain("p100-prop-token"))
        self.open = opener or urllib.request.urlopen
        self.sent_ids = set()
        self.command = None      # latest owner command from the app (e.g. the "Close trade now" button)
        self.pending_ack = None  # result of a handled command, reported on the next send

    def send(self, bot, status):
        if not self.token:
            return False
        events = [e for e in bot.events if e["id"] not in self.sent_ids]
        body = {"status": dict(status, state=bot.state.to_dict()), "orders": bot.orders, "account": bot.account.get("name"), "contract": bot.cid,
                "bars": bot.last_bars[-90:], "events": events}
        req = urllib.request.Request(self.url, data=json.dumps(body, default=str).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Prop-Token": self.token})
        try:
            with self.open(req, timeout=10) as r:
                r.read()
            self.sent_ids.update(e["id"] for e in events)
            return True
        except Exception as exc:  # noqa: BLE001 - reporting must never stop trading
            log.warning("app report failed: %s", type(exc).__name__)
            return False

    def send_fleet(self, fleet):
        """One report for all accounts: the first account at top level (older app versions) plus an accounts list."""
        if not self.token or not fleet.bots:
            return False
        lead = fleet.bots[0]
        events = [e for b in fleet.bots for e in b.events if e["id"] not in self.sent_ids]
        accounts = [{"account": b.account.get("name"), "orders": b.orders, "contract": b.cid, "firm": b.firm,
                     "estimated": b.estimated,
                     "status": dict(b.last_status, state=b.state.to_dict())} for b in fleet.bots]
        body = {"status": accounts[0]["status"], "orders": lead.orders, "account": lead.account.get("name"),
                "contract": lead.cid, "bars": lead.last_bars[-90:], "events": events, "accounts": accounts}
        ack = self.pending_ack
        if ack:
            body["ack"] = ack
        req = urllib.request.Request(self.url, data=json.dumps(body, default=str).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "X-Prop-Token": self.token})
        try:
            with self.open(req, timeout=10) as r:
                raw = r.read()
            self.sent_ids.update(e["id"] for e in events)
            if ack is not None and self.pending_ack is ack:
                self.pending_ack = None
            try:
                reply = json.loads(raw or b"{}")
                self.command = reply.get("command") if isinstance(reply, dict) else None
            except (ValueError, TypeError):
                self.command = None
            return True
        except Exception as exc:  # noqa: BLE001 - reporting must never stop trading
            log.warning("app report failed: %s", type(exc).__name__)
            return False


def to_et(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET)


def group_days(bars):
    """[{t,o,h,l,c,v}] -> {date: {time: (o,h,l,c,v)}} for regular-session 5-minute bars."""
    days = {}
    for b in bars:
        t = to_et(b["t"])
        if OPEN <= t.time() <= LAST:
            days.setdefault(t.date(), {})[t.time()] = (b["o"], b["h"], b["l"], b["c"], b["v"])
    return days


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Market:
    """Market data and account list shared by every account the bot trades (one API call per refresh, not per account)."""

    def __init__(self, api, cid, clock):
        self.api, self.cid, self.clock = api, cid, clock
        self._hist, self._bars, self._accts = {}, (None, None), (None, None)

    def history_bars(self, start, end):
        key = (start, end)
        if key not in self._hist:
            self._hist = {key: self.api.bars(self.cid, start, end)}
        return self._hist[key]

    def today_bars(self, start, now):
        key = (start, int(now.timestamp() // 10))
        if self._bars[0] != key:
            self._bars = (key, self.api.bars(self.cid, start, iso(now)))
        return self._bars[1]

    def last_price(self):
        bars = self._bars[1] or []
        if not bars:
            raise TopstepXError("no price yet")
        return float(max(bars, key=lambda b: b["t"])["c"])

    def accounts(self):
        key = int(self.clock().timestamp() // 5)
        if self._accts[0] != key:
            self._accts = (key, self.api.accounts())
        return self._accts[1]


def select_accounts(accounts, selector):
    """Accounts to trade. Never Live (non-simulated) accounts - Topstep forbids the API there - and never ones that
    cannot trade. ALL = every Combine and funded account (not practice); otherwise comma-separated name parts."""
    ok = [a for a in accounts if a.get("canTrade") and a.get("simulated", True) is not False]
    if (selector or "").strip().upper() == "ALL":
        return [a for a in ok if "PRACTICE" not in (a.get("name") or "").upper()]
    parts = [p.strip().lower() for p in (selector or "").split(",") if p.strip()]
    return [a for a in ok if any(p in (a.get("name") or "").lower() for p in parts)]


class Bot:
    def __init__(self, api, account_name, orders, start_balance=None, symbol="MNQ", contracts=None, home=HOME,
                 clock=None, feed=None, account=None, contract=None, market=None, aggressive=False,
                 sizer=None, tp_move_frac=None, tick=None, price_fn=None, news=None):
        self.sizer, self.tp_move_frac, self.tick, self.price_fn, self.news = sizer, tp_move_frac, tick, price_fn, news
        self.min_lot = 1  # smallest order (contracts); CFD accounts use their lot step
        self.api, self.orders, self.symbol, self.fixed_contracts = api, orders, symbol, contracts
        self.clock = clock or (lambda: dt.datetime.now(ET))
        self.home = home
        os.makedirs(home, exist_ok=True)
        if account is None:
            accts = [a for a in api.accounts() if account_name.lower() in (a.get("name") or "").lower()]
            if len(accts) != 1:
                raise SystemExit("account '%s' matched %d accounts: %s" % (
                    account_name, len(accts), [a.get("name") for a in api.accounts()]))
            account = accts[0]
        self.account = account
        self.aid = self.account["id"]
        self.size_k = size_k(self.account.get("name"))
        c = contract or api.contract(symbol)
        self.cid, self.point_value = c["id"], c["tickValue"] / c["tickSize"]
        self.market = market
        self.state_path = os.path.join(home, "state-%s.json" % self.aid)
        self.firm = self.account.get("firm", "Topstep")
        self.estimated = bool(self.account.get("estimated"))
        self.state = apply_rules(self._load(start_balance or float(self.account.get("start_balance") or self.size_k * 1000.0)),
                                 self.account.get("name"), self.account.get("kind"), self.account.get("rules"))
        self.history, self.history_day = [], None
        self.rejected_tags = {}  # order tag -> number of explicit broker rejections (see go_to)
        self.virtual = 0  # dry-run position (+n / -n contracts); restored after a restart on the same day
        self.virtual_avg = None
        if self.state.dry_day == self.clock().date().isoformat():
            self.virtual, self.virtual_avg = self.state.dry_pos, self.state.dry_avg
        self.done = set()
        self.events, self.last_bars, self.last_status, self.n_events = [], [], {}, 0
        self.feed = feed or Feed()
        self.aggressive = aggressive
        if aggressive and self.state.kind == "combine":
            self.state.daily_stop = AGGR_DAILY_STOP_PER_50K * self.size_k / 50

    # --- persistence -----------------------------------------------------------------------------------------
    def _load(self, start_balance):
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                return ChallengeState.from_dict(json.load(f))
        return ChallengeState(start_balance=start_balance, eod_high=start_balance)

    def save(self, extra=None):
        with open(self.state_path, "w") as f:
            json.dump(self.state.to_dict(), f, indent=1)
        status = {"time": self.clock().isoformat(), "account": self.account.get("name"), "orders": self.orders,
                  "state": self.state.to_dict(), **(extra or {})}
        for name in ("status.json", "status-%s.json" % self.aid):
            with open(os.path.join(self.home, name), "w") as f:
                json.dump(status, f, indent=1)
        if self.home == HOME:
            try:
                os.makedirs(MIRROR, exist_ok=True)
                with open(os.path.join(MIRROR, "status.json"), "w") as f:
                    json.dump(status, f, indent=1)
            except OSError:
                pass

    def event(self, kind, text, price=None, size=None, pnl=None):
        now = self.clock()
        self.n_events += 1
        e = {"id": "%s-%s-%d" % (self.aid, now.strftime("%Y%m%d%H%M%S"), self.n_events), "time": now.isoformat(),
             "kind": kind, "text": text, "price": price, "size": size, "account": self.account.get("name"),
             "pnl": round(pnl, 2) if pnl is not None else None}
        self.events.append(e)
        self.events = self.events[-50:]
        log.info("EVENT %s: %s", kind, text)

    # --- market/account reads --------------------------------------------------------------------------------
    def load_history(self, today):
        start = dt.datetime.combine(today - dt.timedelta(days=35), dt.time(0), ET)
        end = dt.datetime.combine(today, dt.time(0), ET)
        raw = (self.market.history_bars(iso(start), iso(end)) if self.market
               else self.api.bars(self.cid, iso(start), iso(end)))
        days = group_days(raw)
        self.history = [days[d] for d in sorted(days) if OPEN in days[d] and LAST in days[d]][-20:]
        self.history_day = today
        self.scale = vol_scale(self.history)

    def today_bars(self, now):
        start = dt.datetime.combine(now.date(), OPEN, ET)
        raw = self.market.today_bars(iso(start), now) if self.market else self.api.bars(self.cid, iso(start), iso(now))
        return group_days(raw).get(now.date(), {})

    def position(self):
        if not self.orders:
            return self.virtual, self.virtual_avg
        for p in self.api.positions(self.aid):
            if p["contractId"] == self.cid:
                sign = 1 if p["type"] == LONG else -1
                return sign * p["size"], p["averagePrice"]
        return 0, None

    def balance(self):
        for a in (self.market.accounts() if self.market else self.api.accounts()):
            if a["id"] == self.aid:
                return float(a["balance"])
        raise TopstepXError("account disappeared")

    def size(self, price):
        if self.sizer:
            return self.sizer(price, getattr(self, "scale", 1.0), self)
        if self.fixed_contracts:
            return self.fixed_contracts
        units = self.size_k / 50.0  # a 150K account trades 3x a 50K account
        if self.aggressive:
            base = AGGR_FUNDED_PER_50K if self.state.kind == "funded" else AGGR_EVAL_PER_50K
            n = max(1, int(round(base * units * getattr(self, "scale", 1.0))))
            return min(n, max(1, int(AGGR_MAX_PER_50K * units)))
        if self.state.kind == "funded":
            room = getattr(self, "room", 0.0)
            base = max(1, min(int(2 * units), int(room // FUNDED_ROOM_PER_CONTRACT)))
        else:
            cap = max(1, int(MAX_CONTRACTS_PER_50K * units))
            base = max(1, min(cap, round(TARGET_NOTIONAL * units / (price * self.point_value))))
        n = max(1, int(round(base * getattr(self, "scale", 1.0))))
        return min(n, max(1, int(MAX_SCALED_PER_50K * units)))

    def take_profit(self):
        """$ open profit at which the whole position is closed (Combine accounts only; 0 = off)."""
        return TAKE_PROFIT_PER_50K * self.size_k / 50.0 if self.state.kind == "combine" else 0.0

    def tp_dollars(self, pos, avg):
        """Take-profit in $ for the open position: a fixed move (% of price) when tp_move_frac is set (CFD accounts,
        same 0.52% move as the Topstep +$600 on 2 MNQ), otherwise take_profit()."""
        if self.tp_move_frac:
            if self.state.kind not in ("combine", "funded") or not pos or not avg:
                return 0.0
            return abs(pos) * self.point_value * avg * self.tp_move_frac
        return self.take_profit()

    def _tp_orders(self):
        """Resting take-profit limit orders of this bot on the traded contract (TopstepX accounts only)."""
        if not self.orders or not hasattr(self.api, "limit"):
            return []
        return [o for o in self.api.open_orders(self.aid) if o.get("contractId") == self.cid and o.get("type") == LIMIT]

    def cancel_tp(self):
        for o in self._tp_orders():
            self.api.cancel(self.aid, o["id"])

    def manage_tp(self, now):
        """Keep exactly one resting take-profit order at the broker for the open position (research assumed a
        resting order that fills the moment price touches the level, not a check on 5-minute closes)."""
        if not self.orders or not hasattr(self.api, "limit") or not getattr(self.api, "resting_tp", True):
            return  # accounts without a safe resting take-profit (TradeLocker hedging) use the polled take-profit
        pos, avg = self.position()
        tp = self.tp_dollars(pos, avg)
        blocked = self.news.blocked(now)[0] if self.news else False
        if not pos or not tp or not avg or blocked or now.time() >= flatten_time(now.date()):
            self.cancel_tp()  # no resting order may fill inside a news window
            return
        tick = self.tick or 0.25
        move = tp / (abs(pos) * self.point_value)
        raw = avg + move if pos > 0 else avg - move
        price = (math.ceil(raw / tick) if pos > 0 else math.floor(raw / tick)) * tick
        side = SELL if pos > 0 else BUY
        have = self._tp_orders()
        if len(have) == 1 and have[0].get("side") == side and abs(float(have[0].get("size") or 0) - abs(pos)) < 1e-9 \
                and abs(float(have[0].get("limitPrice") or 0) - price) < 1e-9:
            return
        for o in have:
            self.api.cancel(self.aid, o["id"])
        self.api.limit(self.aid, self.cid, side, abs(pos), price)
        self.event("day", "Take-profit order resting at %.2f (+$%d)" % (price, tp), price, abs(pos))

    # --- execution -------------------------------------------------------------------------------------------
    def go_to(self, target_sign, price, reason, tag):
        pos, _ = self.position()
        n = self.size(price)
        want = target_sign * n
        if abs(pos - want) < 1e-6:  # fractional lots (CFD accounts) compare with a tolerance
            return
        log.info("%s: position %+g -> %+g at ~%.2f (%s)", "ORDER" if self.orders else "DRY RUN", pos, want, price, reason)
        _, avg = self.position()
        pnl = (price - avg) * pos * self.point_value if (pos and avg) else None
        label = "" if self.orders else "[dry run] "  # display prefix only; `tag` stays the unique order tag
        # events are written only after the broker accepted the order (11/05: rejected retries were logged as trades)
        close_ev = entry_ev = None
        if pos and (want == 0 or (pos > 0) != (want > 0)):
            close_ev = ("flat", "%sClosed %s at %.2f (%s)" % (label, self.qty(pos, True), price,
                                                              reason if want == 0 else "to reverse"), price, abs(pos), pnl)
        if want and abs(want - (0 if close_ev else pos)) > 1e-6:
            entry_ev = ("buy" if want > 0 else "sell", "%s%s %s at %.2f (%s)" % (
                label, "Bought" if want > 0 else "Sold short", self.qty(want), price, reason), price, abs(want))
        if not self.orders:
            for ev in (close_ev, entry_ev):
                if ev:
                    self.event(*ev)
            self.virtual, self.virtual_avg = want, (price if want else None)
            self.state.dry_pos, self.state.dry_avg, self.state.dry_day = want, self.virtual_avg, self.clock().date().isoformat()
            return
        try:
            self.cancel_tp()  # a resting limit must never outlive the position it protects
        except TopstepXError as e:  # never let it block a close; manage_tp cancels it on the next pass
            log.warning("cancel take-profit order: %s", e)
        if pos != 0 and (want == 0 or (pos > 0) != (want > 0)):
            self.api.close(self.aid, self.cid)
            pos = 0
            if close_ev:
                self.event(*close_ev)
        delta = want - pos
        if abs(delta) > 1e-6:
            n_rej = self.rejected_tags.get(tag, 0) if tag else 0
            use = "%s-r%d" % (tag, n_rej) if n_rej else tag
            try:
                self.api.market(self.aid, self.cid, BUY if delta > 0 else SELL, abs(delta), tag=use)
            except TopstepXError as e:
                # an explicit rejection means no order exists: the retry may use a new tag (an unknown outcome keeps
                # the same tag, so a lost reply can never double the position)
                if tag and any(m in str(e) for m in REJECTED_MSGS):
                    self.rejected_tags[tag] = n_rej + 1
                raise
            if entry_ev:
                self.event(*entry_ev)
        self.mark_trade_day()

    def qty(self, n, signed=False):
        """Order size for messages: '1 MNQ' on futures, '0.02 lot' on CFD accounts (fractional lots)."""
        frac = getattr(self, "min_lot", 1) < 1
        body = ("%.2f lot" % abs(n)) if frac else ("%d MNQ" % round(abs(n)))
        return (("+" if n > 0 else "-") + body) if signed else body

    def mark_trade_day(self):
        d = self.state.day
        if d and d not in self.state.trade_days:
            self.state.trade_days = (self.state.trade_days + [d])[-60:]

    def flatten(self, price, reason):
        self.go_to(0, price, reason, None)

    # --- one loop iteration ----------------------------------------------------------------------------------
    def step(self):
        now = self.clock()
        today = now.date()
        if now.weekday() >= 5 or now.time() < dt.time(9, 25) or now.time() > dt.time(16, 5):
            if not self.last_status:   # once while closed: balances for the dashboard (one read, never an order)
                try:
                    pos, avg = self.position()
                    self.last_status = {"balance": self.balance(), "open_pnl": 0.0, "position": pos, "avg": avg,
                                        "floor": self.state.floor, "allowed": True, "note": "market closed",
                                        "kind": self.state.kind, "target": self.state.target, "size_k": self.size_k,
                                        "fast": False}
                except Exception as e:  # noqa: BLE001 - display only
                    log.warning("closed-market status: %s", e)
            return "market closed"
        if self.history_day != today:
            self.load_history(today)
            self.done = set()
            new_day(self.state, today.isoformat(), self.balance())
            log.info("new day %s: balance %.2f, trailing floor %.2f, history %d days",
                     today, self.state.day_start_balance, self.state.floor, len(self.history))
            self.event("day", "New trading day. Balance %.2f, loss limit %.2f" % (
                self.state.day_start_balance, self.state.floor))
        bars = self.today_bars(now)
        if not bars:
            return "waiting for bars"
        last_t = max(bars)
        price = bars[last_t][3]
        if self.price_fn:
            price = self.price_fn()  # CFD accounts: P&L, take-profit and size use the account's own price
        pos, avg = self.position()
        open_pnl = (price - avg) * pos * self.point_value if (pos and avg) else 0.0
        bal = self.balance()
        self.room = bal + open_pnl - self.state.floor
        was_passed, was_halted = self.state.passed, self.state.halted_day == self.state.day or self.state.finished
        allowed, must_flat, why = check(self.state, bal, open_pnl)
        if self.state.cycle_cap and self.state.payout_ready(self.state.day, bal + open_pnl) \
                and self.state.payout_notified != self.state.cycle_start:
            gross, mine = self.state.payable(bal + open_pnl)
            self.state.payout_notified = self.state.cycle_start
            self.event("pass", "Payout ready on %s: request $%.2f (you receive about $%.2f). The firm resets the account "
                               "after the payout; the bot starts a new cycle by itself." % (self.account.get("name"), gross, mine))
        if self.state.passed and not was_passed:
            self.event("pass", "Profit target reached at %s. Request the funded account on Topstep." % round(bal + open_pnl))
        elif not allowed and must_flat and not was_halted:
            self.event("halt", "Trading stopped: %s" % why)
        need = self.state.required_target(bal + open_pnl - self.state.day_start_balance)
        status = {"balance": bal, "open_pnl": round(open_pnl, 2), "position": pos, "price": price, "avg": avg,
                  "floor": self.state.floor, "allowed": allowed, "note": why, "kind": self.state.kind,
                  "target": need, "size_k": self.size_k, "fast": self.state.fast_day == self.state.day}
        news_block, news_why = self.news.blocked(now) if self.news else (False, "")
        if news_block and not must_flat:
            status["note"] = news_why
            for t in bars:  # checks that fall inside the window are skipped, not delayed
                if is_check(t):
                    closed_at = dt.datetime.combine(today, t, ET) + dt.timedelta(minutes=5)
                    if closed_at <= now:
                        self.done.add(t)
        if must_flat and pos:
            self.flatten(price, why)
        elif (self.state.target_hit and not self.state.passed and not pos and self.orders and not news_block
              and self.state.day not in self.state.trade_days and dt.time(10, 5) <= now.time() < dt.time(15, 30)):
            # target already reached: one minimum-size round trip counts the day toward the firm's minimum
            self.event("day", "Minimum-days trade %d/%d (target already reached)" % (
                len(self.state.trade_days) + 1, self.state.min_days), price, self.min_lot)
            self.api.market(self.aid, self.cid, BUY, self.min_lot, tag="minday-%s-%s" % (self.aid, self.state.day))
            self.mark_trade_day()
        elif news_block:
            pass  # inside a news window: no orders except forced risk exits above
        elif pos and self.tp_dollars(pos, avg) and open_pnl >= self.tp_dollars(pos, avg) and now.time() < flatten_time(today):
            self.flatten(price, "take profit +$%d" % self.tp_dollars(pos, avg))
        elif now.time() >= flatten_time(today):
            if pos:
                self.flatten(price, "end of day")
        elif allowed:
            sign = (pos > 0) - (pos < 0)
            fast = self.state.fast_day == self.state.day  # owner closed manually today: 5-min checks until the close
            for t in sorted(bars):
                closed_at = dt.datetime.combine(today, t, ET) + dt.timedelta(minutes=5)
                if not (is_fast_check(t) if fast else is_check(t)) or t in self.done or closed_at > now:
                    continue
                if now - closed_at > dt.timedelta(minutes=4):  # too old to act on (late start / outage)
                    self.done.add(t)
                    continue
                target = decide(self.history, bars, t, sign, fast)
                if target is not None and target != sign:
                    # the tag is unique per decision, so a retry after an unknown outcome cannot double the order
                    self.go_to(target, price, "NOISE check %s" % t.strftime("%H:%M"),
                               "noise-%s-%s-%s-%+d" % (self.aid, today.isoformat(), t.strftime("%H%M"), target))
                    sign = target
                self.done.add(t)
        try:
            self.manage_tp(now)
        except TopstepXError as e:
            log.warning("take-profit order: %s (will retry)", e)
        self.save(status)
        self.last_status = status
        self.last_bars = [[dt.datetime.combine(today, t, ET).isoformat(), *bars[t][:4]] for t in sorted(bars)]
        self.feed.send(self, status)
        return why or "ok"


class Fleet:
    """Runs the same NOISE signals on every selected account, each with its own limits, state and log."""

    def __init__(self, api, selector, orders, contracts=None, home=HOME, clock=None, feed=None, symbol="MNQ",
                 relays=None, secret_fn=None, relay_opener=None, aggressive=False, tl_configs=None, tl_factory=None,
                 news=None):
        self.clock = clock or (lambda: dt.datetime.now(ET))
        self.home, self.feed = home, feed or Feed()
        self.handled = set()  # owner command ids already acted on
        accounts = select_accounts(api.accounts(), selector)
        if not accounts:
            raise SystemExit("no tradable account matches '%s': %s" % (selector, [a.get("name") for a in api.accounts()]))
        c = api.contract(symbol)
        self.market = Market(api, c["id"], self.clock)
        quiet = Feed(token="")  # the fleet sends one combined report
        self.bots = [Bot(api, None, orders, contracts=contracts, home=home, clock=self.clock, feed=quiet,
                         account=a, contract=c, market=self.market, aggressive=aggressive) for a in accounts]
        # accounts at other firms, traded through a webhook relay (see relay.py)
        secret_fn = secret_fn or keychain
        for cfg in (relays if relays is not None else relaymod.load_config()):
            url = secret_fn(cfg["secret"]) if cfg.get("secret") else None
            r = relaymod.RelayAPI(cfg, self.market.last_price, home, url if orders else None, relay_opener)
            r.cid = c["id"]
            acct = dict(r.account(), kind=cfg.get("kind", "combine"), rules=cfg.get("rules"),
                        start_balance=cfg.get("start_balance"))
            self.bots.append(Bot(r, None, orders and bool(url), contracts=contracts, home=home, clock=self.clock,
                                 feed=quiet, account=acct, contract=c, market=relaymod.RelayMarket(self.market, r),
                                 aggressive=aggressive))
        # accounts at TradeLocker prop firms (Eightcap Challenges ...), see tradelocker.py and add-tradelocker.sh
        tl_cfgs = tl_configs if tl_configs is not None else tlmod.load_config(os.path.join(home, "tradelocker.json"))
        if tl_cfgs:
            cal = news or newsmod.NewsCalendar(home, ET)
        for cfg in tl_cfgs:
            try:
                self.bots.append(self._tl_bot(cfg, c, orders, home, quiet, secret_fn, tl_factory, cal, aggressive))
            except Exception as e:  # noqa: BLE001 - a TradeLocker problem must never stop Topstep trading
                log.warning("TradeLocker account %s not started: %s", cfg.get("name"), e)
        lead = self.bots[0]
        self.london = londonmod.LondonDrift(api, c["id"], lead.point_value, lead.event, home, to_et, iso, group_days, ET)

    def _tl_bot(self, cfg, c, orders, home, quiet, secret_fn, tl_factory, cal, aggressive):
        pw = secret_fn(cfg["secret"]) if cfg.get("secret") else None
        if not pw:
            raise ValueError("no password in the Keychain item %s" % cfg.get("secret"))
        tl = (tl_factory or tlmod.TradeLocker)(cfg["email"], pw, cfg["server"], cfg.get("env", "live"))
        tl.select(cfg.get("acc_num"), cfg.get("account_id"))
        instr = tl.instrument((cfg["symbol"],) if cfg.get("symbol") else tlmod.NASDAQ_NAMES)
        acct_api = tlmod.TradeLockerAccount(tl, cfg, instr)
        acct_api.cid = c["id"]
        # minimum order size for the firm's minimum-trading-days trades
        pv = float(cfg["point_value"])          # $ per 1.00 index point per 1.00 lot (from --check / the demo test)
        tick = float(cfg.get("tick") or 0.01)
        lev, start, step = float(cfg.get("leverage", 3.0)), float(cfg["start_balance"]), acct_api.lot_step

        def sizer(price, scale, bot):
            lots = lev * start * scale / (price * pv)
            return max(step, math.floor(lots / step + 1e-9) * step)
        acct = dict(acct_api.account(), kind=cfg.get("kind", "combine"), rules=cfg.get("rules"), start_balance=start)
        bot = Bot(acct_api, None, orders and bool(cfg.get("orders")), home=home, clock=self.clock, feed=quiet,
                   account=acct, contract={"id": c["id"], "tickSize": tick, "tickValue": tick * pv},
                   market=relaymod.RelayMarket(self.market, acct_api), aggressive=False, sizer=sizer,
                   tp_move_frac=float(cfg.get("tp_move_frac", 0.00526)), tick=tick, price_fn=acct_api.price,
                   news=cal if cfg.get("news_blackout", True) else None)
        bot.min_lot = step
        bot.size_k = int(start // 1000) if start >= 1000 else start / 1000.0  # label from the real balance (5K, not 50K)
        return bot

    def handle_command(self):
        """Owner's "Close trade now" button: close open trades on live accounts. Trading continues afterwards."""
        cmd = self.feed.command
        if not isinstance(cmd, dict) or cmd.get("kind") != "close_now" or cmd.get("status") != "pending":
            return None
        cid = cmd.get("id")
        if not cid or cid in self.handled:
            return None
        self.handled.add(cid)
        self.feed.command = None
        results = []
        for b in self.bots:
            if not b.orders:
                continue  # dry-run accounts have no real trade to close
            name = b.account.get("name")
            try:
                pos, avg = b.position()
                if not pos:
                    results.append({"account": name, "closed": False, "note": "no open trade"})
                    continue
                price = (b.last_status or {}).get("price") or avg
                b.flatten(price, "owner: close now button")
                if b.state.fast_day != b.state.day:
                    b.state.fast_day = b.state.day
                    b.event("day", "Fast mode on: checking every 5 minutes until the close (after manual close). "
                                   "Back to hourly tomorrow.")
                results.append({"account": name, "closed": True, "position": pos, "avg": avg})
            except Exception as e:  # noqa: BLE001 - one account's problem must not stop the others
                log.warning("close now on %s: %s", name, e)
                results.append({"account": name, "closed": False, "note": "error: %s" % e})
        entry = {"time": self.clock().isoformat(), "source": "dashboard", "command": cid, "results": results}
        try:
            path = os.path.join(self.home, "manual_closes.json")
            log_rows = []
            if os.path.exists(path):
                with open(path) as f:
                    log_rows = json.load(f)
            log_rows.append(entry)
            with open(path, "w") as f:
                json.dump(log_rows[-200:], f, indent=1)
        except (OSError, ValueError) as e:
            log.warning("manual close log: %s", e)
        closed = [r["account"] for r in results if r["closed"]]
        text = ("closed " + ", ".join(closed)) if closed else "nothing open to close"
        log.info("CLOSE NOW button: %s", text)
        self.feed.pending_ack = {"id": cid, "result": text}
        return results

    def step(self):
        notes = []
        try:
            self.handle_command()
        except Exception as e:  # noqa: BLE001 - a command problem must never stop trading
            log.warning("owner command problem: %s", e)
        try:
            self.london.step(self.clock())
        except Exception as e:  # noqa: BLE001 - the dry-run study must never affect trading
            log.warning("London dry run problem: %s", e)
        for b in self.bots:
            try:
                notes.append(b.step())
            except TopstepXError as e:  # one account's problem must not stop the others
                log.warning("API problem on %s: %s (will retry)", b.account.get("name"), e)
                notes.append("api problem")
        if any(b.last_status for b in self.bots):
            summary = {"time": self.clock().isoformat(), "accounts": [
                dict(b.last_status, account=b.account.get("name"), firm=b.firm, estimated=b.estimated,
                     state=b.state.to_dict()) for b in self.bots]}
            with open(os.path.join(self.home, "status.json"), "w") as f:
                json.dump(summary, f, indent=1)
            if self.home == HOME:
                try:
                    os.makedirs(MIRROR, exist_ok=True)
                    with open(os.path.join(MIRROR, "status.json"), "w") as f:
                        json.dump(summary, f, indent=1)
                except OSError:
                    pass
        self.feed.send_fleet(self)
        return "market closed" if notes and all(n == "market closed" for n in notes) else "ok"


def run_check(api):
    try:
        accounts = api.accounts()
    except TopstepXError as e:
        if "loginKey failed: code 3" in str(e) or "loginKey failed: code 1" in str(e):
            print("LOGIN REJECTED: username or API key is wrong. Re-copy the key (or create a new one after linking "
                  "ProjectX) and check the username, then run install.sh again.")
            raise SystemExit(2)
        raise
    print("Signed in to TopstepX.")
    for a in accounts:
        print("  account: %-30s id=%s balance=%s canTrade=%s simulated=%s" % (
            a.get("name"), a.get("id"), a.get("balance"), a.get("canTrade"), a.get("simulated")))
    c = api.contract("MNQ")
    print("  contract: %s %s tick %s = $%s" % (c["id"], c.get("description"), c["tickSize"], c["tickValue"]))
    now = dt.datetime.now(ET)
    bars = api.bars(c["id"], iso(now - dt.timedelta(days=3)), iso(now))
    print("  recent 5-min bars: %d (last %s close %s)" % (len(bars), bars[-1]["t"] if bars else "-",
                                                          bars[-1]["c"] if bars else "-"))
    for cfg in tlmod.load_config(os.path.join(HOME, "tradelocker.json")):
        try:
            tl = tlmod.TradeLocker(cfg["email"], keychain(cfg["secret"]), cfg["server"], cfg.get("env", "live"))
            print("TradeLocker %s (%s, %s): accounts %s" % (cfg["name"], cfg["server"], cfg.get("env", "live"),
                  [(a.get("id"), a.get("accNum"), a.get("name"), a.get("accountBalance")) for a in tl.all_accounts()]))
            tl.select(cfg.get("acc_num"), cfg.get("account_id"))
            ins = tl.instrument((cfg["symbol"],) if cfg.get("symbol") else tlmod.NASDAQ_NAMES)
            d = tl.details(ins)
            ask, bid = tl.quote(ins)
            print("  instrument %s id=%s  bid %.2f ask %.2f" % (ins.get("name"), ins.get("tradableInstrumentId"), bid, ask))
            print("  details: " + ", ".join("%s=%s" % (k, d[k]) for k in sorted(d) if not isinstance(d[k], (list, dict))))
            print("  state: " + ", ".join("%s=%s" % (k, v) for k, v in tl.state().items() if k in (
                "balance", "projectedBalance", "availableFunds", "todayNet", "positionsCount", "ordersCount")))
        except Exception as e:  # noqa: BLE001
            print("TradeLocker %s: PROBLEM %s" % (cfg.get("name"), e))
    print("CHECK OK - no orders were placed.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--account", default="")
    ap.add_argument("--orders", action="store_true", help="place real orders (default: dry run)")
    ap.add_argument("--start-balance", type=float, default=50000.0)
    ap.add_argument("--contracts", type=int, default=None)
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--aggressive", action="store_true", help="aggressive sizing (see AGGR_* constants)")
    a = ap.parse_args(argv)
    os.makedirs(HOME, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(HOME, "bot.log")), logging.StreamHandler()])
    api = TopstepX(*credentials())
    if a.check:
        return run_check(api)
    if not a.account:
        sys.exit("--account is required (ALL, or part of the account name shown by --check)")
    bot = Fleet(api, a.account, a.orders, contracts=a.contracts, aggressive=a.aggressive)
    for b in bot.bots:
        log.info("trading %s (%s, %dK %s), contract %s, %s%s", b.account.get("name"), b.aid, b.size_k, b.state.kind,
                 b.cid, "LIVE ORDERS" if a.orders else "dry run", ", AGGRESSIVE sizing" if a.aggressive else "")
    while True:
        try:
            note = bot.step()
            if note == "market closed" and dt.datetime.now(ET).time() > dt.time(16, 5):
                log.info("market closed - exiting for today")
                return
        except TopstepXError as e:
            log.warning("API problem: %s (will retry)", e)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
