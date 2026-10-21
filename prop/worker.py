"""Prop-challenge bot: NOISE intraday momentum on micro Nasdaq futures (MNQ) in a TopstepX account.

Runs on the owner's own computer (Topstep forbids placing orders from a VPS/remote server).
Default is DRY RUN: it reads real prices and the real account but only logs what it would do.
Real orders need --orders. Credentials come from the macOS Keychain (install.sh) or the environment.

    python3 worker.py --check                      # sign in, list accounts, contract, recent bars; no orders
    python3 worker.py --account PRACTICE           # dry run on the account whose name contains PRACTICE
    python3 worker.py --account 50K --orders       # live orders on the challenge account
"""
import argparse
import datetime as dt
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard import ChallengeState, check, new_day  # noqa: E402
from noise import LAST, OPEN, decide, is_check  # noqa: E402
from topstepx import BUY, LONG, SELL, TopstepX, TopstepXError  # noqa: E402

ET = ZoneInfo("America/New_York")
HOME = os.path.expanduser("~/.p100-prop")
MIRROR = os.path.expanduser("~/Documents/p100-prop/data")  # best-effort copy Claude can read (macOS may block it)
TARGET_NOTIONAL = 100000.0  # "size 2" in the challenge test = 2 x $50K of Nasdaq exposure
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

    def send(self, bot, status):
        if not self.token:
            return False
        events = [e for e in bot.events if e["id"] not in self.sent_ids]
        body = {"status": status, "orders": bot.orders, "account": bot.account.get("name"), "contract": bot.cid,
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


class Bot:
    def __init__(self, api, account_name, orders, start_balance, symbol="MNQ", contracts=None, home=HOME, clock=None,
                 feed=None):
        self.api, self.orders, self.symbol, self.fixed_contracts = api, orders, symbol, contracts
        self.clock = clock or (lambda: dt.datetime.now(ET))
        self.home = home
        os.makedirs(home, exist_ok=True)
        accts = [a for a in api.accounts() if account_name.lower() in (a.get("name") or "").lower()]
        if len(accts) != 1:
            raise SystemExit("account '%s' matched %d accounts: %s" % (
                account_name, len(accts), [a.get("name") for a in api.accounts()]))
        self.account = accts[0]
        self.aid = self.account["id"]
        c = api.contract(symbol)
        self.cid, self.point_value = c["id"], c["tickValue"] / c["tickSize"]
        self.state_path = os.path.join(home, "state-%s.json" % self.aid)
        self.state = self._load(start_balance)
        self.history, self.history_day = [], None
        self.virtual = 0  # dry-run position (+n / -n contracts)
        self.virtual_avg = None
        self.done = set()
        self.events, self.last_bars = [], []
        self.feed = feed or Feed()

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
        with open(os.path.join(self.home, "status.json"), "w") as f:
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
        e = {"id": "%s-%d" % (now.strftime("%Y%m%d%H%M%S"), len(self.events)), "time": now.isoformat(),
             "kind": kind, "text": text, "price": price, "size": size,
             "pnl": round(pnl, 2) if pnl is not None else None}
        self.events.append(e)
        self.events = self.events[-50:]
        log.info("EVENT %s: %s", kind, text)

    # --- market/account reads --------------------------------------------------------------------------------
    def load_history(self, today):
        start = dt.datetime.combine(today - dt.timedelta(days=35), dt.time(0), ET)
        end = dt.datetime.combine(today, dt.time(0), ET)
        days = group_days(self.api.bars(self.cid, iso(start), iso(end)))
        self.history = [days[d] for d in sorted(days) if OPEN in days[d] and LAST in days[d]][-20:]
        self.history_day = today

    def today_bars(self, now):
        start = dt.datetime.combine(now.date(), OPEN, ET)
        return group_days(self.api.bars(self.cid, iso(start), iso(now))).get(now.date(), {})

    def position(self):
        if not self.orders:
            return self.virtual, self.virtual_avg
        for p in self.api.positions(self.aid):
            if p["contractId"] == self.cid:
                sign = 1 if p["type"] == LONG else -1
                return sign * p["size"], p["averagePrice"]
        return 0, None

    def balance(self):
        for a in self.api.accounts():
            if a["id"] == self.aid:
                return float(a["balance"])
        raise TopstepXError("account disappeared")

    def size(self, price):
        if self.fixed_contracts:
            return self.fixed_contracts
        return max(1, min(3, round(TARGET_NOTIONAL / (price * self.point_value))))

    # --- execution -------------------------------------------------------------------------------------------
    def go_to(self, target_sign, price, reason, tag):
        pos, _ = self.position()
        n = self.size(price)
        want = target_sign * n
        if pos == want:
            return
        log.info("%s: position %+d -> %+d at ~%.2f (%s)", "ORDER" if self.orders else "DRY RUN", pos, want, price, reason)
        _, avg = self.position()
        pnl = (price - avg) * pos * self.point_value if (pos and avg) else None
        tag = "" if self.orders else "[dry run] "
        if want == 0:
            self.event("flat", "%sClosed %+d MNQ at %.2f (%s)" % (tag, pos, price, reason), price, abs(pos), pnl)
        else:
            if pos and (pos > 0) != (want > 0):
                self.event("flat", "%sClosed %+d MNQ at %.2f to reverse" % (tag, pos, price), price, abs(pos), pnl)
            self.event("buy" if want > 0 else "sell", "%s%s %d MNQ at %.2f (%s)" % (
                tag, "Bought" if want > 0 else "Sold short", abs(want), price, reason), price, abs(want))
        if not self.orders:
            self.virtual, self.virtual_avg = want, (price if want else None)
            return
        if pos != 0 and (want == 0 or (pos > 0) != (want > 0)):
            self.api.close(self.aid, self.cid)
            pos = 0
        delta = want - pos
        if delta:
            self.api.market(self.aid, self.cid, BUY if delta > 0 else SELL, abs(delta), tag=tag)

    def flatten(self, price, reason):
        self.go_to(0, price, reason, None)

    # --- one loop iteration ----------------------------------------------------------------------------------
    def step(self):
        now = self.clock()
        today = now.date()
        if now.weekday() >= 5 or now.time() < dt.time(9, 25) or now.time() > dt.time(16, 5):
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
        pos, avg = self.position()
        open_pnl = (price - avg) * pos * self.point_value if (pos and avg) else 0.0
        bal = self.balance()
        was_passed, was_halted = self.state.passed, self.state.halted_day == self.state.day or self.state.finished
        allowed, must_flat, why = check(self.state, bal, open_pnl)
        if self.state.passed and not was_passed:
            self.event("pass", "Profit target reached at %s. Request the funded account on Topstep." % round(bal + open_pnl))
        elif not allowed and must_flat and not was_halted:
            self.event("halt", "Trading stopped: %s" % why)
        status = {"balance": bal, "open_pnl": round(open_pnl, 2), "position": pos, "price": price,
                  "floor": self.state.floor, "allowed": allowed, "note": why}
        if must_flat and pos:
            self.flatten(price, why)
        elif now.time() >= flatten_time(today):
            if pos:
                self.flatten(price, "end of day")
        elif allowed:
            sign = (pos > 0) - (pos < 0)
            for t in sorted(bars):
                closed_at = dt.datetime.combine(today, t, ET) + dt.timedelta(minutes=5)
                if not is_check(t) or t in self.done or closed_at > now:
                    continue
                if now - closed_at > dt.timedelta(minutes=4):  # too old to act on (late start / outage)
                    self.done.add(t)
                    continue
                target = decide(self.history, bars, t, sign)
                if target is not None and target != sign:
                    # the tag is unique per decision, so a retry after an unknown outcome cannot double the order
                    self.go_to(target, price, "NOISE check %s" % t.strftime("%H:%M"),
                               "noise-%s-%s-%+d" % (today.isoformat(), t.strftime("%H%M"), target))
                    sign = target
                self.done.add(t)
        self.save(status)
        self.last_bars = [[dt.datetime.combine(today, t, ET).isoformat(), *bars[t][:4]] for t in sorted(bars)]
        self.feed.send(self, status)
        return why or "ok"


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
    print("CHECK OK - no orders were placed.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--account", default="")
    ap.add_argument("--orders", action="store_true", help="place real orders (default: dry run)")
    ap.add_argument("--start-balance", type=float, default=50000.0)
    ap.add_argument("--contracts", type=int, default=None)
    ap.add_argument("--interval", type=int, default=15)
    a = ap.parse_args(argv)
    os.makedirs(HOME, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(HOME, "bot.log")), logging.StreamHandler()])
    api = TopstepX(*credentials())
    if a.check:
        return run_check(api)
    if not a.account:
        sys.exit("--account is required (part of the account name shown by --check)")
    bot = Bot(api, a.account, a.orders, a.start_balance, contracts=a.contracts)
    log.info("started on %s (%s), contract %s, %s", bot.account.get("name"), bot.aid, bot.cid,
             "LIVE ORDERS" if a.orders else "dry run")
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
