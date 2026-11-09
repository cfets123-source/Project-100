"""One-shot live test of a TradeLocker prop account (Eightcap) before turning its orders on.
Buys the minimum size (0.01 lot), rests a take-profit limit far above the price, confirms both at the broker,
cancels the limit and closes. Cost: the spread on 0.01 lot (a few cents). Never runs if the account already has a
position or a resting order on the instrument, and always tries to clean up what it opened.
Run:  python3 ~/p100-prop/tl_test.py            (first account in ~/.p100-prop/tradelocker.json)
      python3 ~/p100-prop/tl_test.py --cleanup  (cancel resting orders + close the position after a failed test)
      python3 ~/p100-prop/tl_test.py EIGHTCAP-5K-1"""
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelocker as tlmod  # noqa: E402
import worker  # noqa: E402
from topstepx import BUY, SELL  # noqa: E402

TP_FRAC = 0.02   # take-profit 2% above entry: confirms a resting order without any chance of filling during the test


def wait(fn, ok, tries=10, pause=2.0, sleep=time.sleep):  # gentle polling: TradeLocker rate-limits fast loops
    val = fn()
    for _ in range(tries):
        if ok(val):
            return val
        sleep(pause)
        val = fn()
    return val


def raw(acct):
    """The broker's own position rows on the instrument (not the bot's net view): [(side, qty)]."""
    return [(str(p.get("side")).lower(), float(p.get("qty") or 0)) for p in acct.tl.positions()
            if int(p.get("tradableInstrumentId") or 0) == acct.iid]


def run_test(acct, lot=0.01, sleep=time.sleep, say=print):
    """Full-day order sequence at the minimum size, checking the broker's raw positions after every step:
    entry, reversal, an opposite order while in a position (must never create a hedge), net view, end-of-day close.
    Returns (passed, steps). acct: a tradelocker.TradeLockerAccount."""
    steps = []

    def step(name, good, info=""):
        steps.append({"step": name, "ok": bool(good), "info": info})
        say("%s %s %s" % ("OK  " if good else "FAIL", name, info))
        return good

    def settle(expect):
        return wait(lambda: raw(acct), lambda r: sorted(r) == sorted(expect), sleep=sleep)

    if raw(acct) or acct.tl.orders():
        step("account is flat with no orders", False, "refusing to test on an account that is in use")
        return False, steps
    bal0 = acct.account()["balance"]
    step("signed in, balance %.2f" % bal0, True)
    try:
        acct.market(acct.aid, acct.cid, BUY, lot, tag="tltest-buy")
        r = settle([("buy", lot)])
        if not step("1 entry: one buy position", r == [("buy", lot)], str(r)):
            return False, steps
        acct.close(acct.aid, acct.cid)
        acct.market(acct.aid, acct.cid, SELL, lot, tag="tltest-rev")
        r = settle([("sell", lot)])
        if not step("2 reversal: only one sell position", r == [("sell", lot)], str(r)):
            return False, steps
        acct.market(acct.aid, acct.cid, BUY, lot, tag="tltest-opp")
        r = settle([("buy", lot)])
        if not step("3 opposite order while short: closes first, never a hedge", r == [("buy", lot)], str(r)):
            return False, steps
        p = acct.positions()
        if not step("4 bot view matches the broker", p and abs(p[0]["size"] - lot) < 1e-9, str(p)):
            return False, steps
        acct.close(acct.aid, acct.cid)
        r = settle([])
        if not step("5 end-of-day close: no positions left", r == [], str(r)):
            return False, steps
        step("orders left", not acct.tl.orders())
        step("round trip cost %.2f" % (acct.account()["balance"] - bal0), True)
        return True, steps
    except Exception as e:  # noqa: BLE001 - report and clean up below
        step("broker call", False, "%s: %s" % (type(e).__name__, e))
        return False, steps
    finally:
        try:
            for o in acct.tl.orders():
                acct.tl.delete_order(o["id"])
            if raw(acct):
                acct.tl.close_all(acct.instr)
        except Exception as e:  # noqa: BLE001
            say("CLEANUP PROBLEM: %s - run python3 ~/p100-prop/tl_closeall.py" % e)


def cleanup(acct, say=print):
    """Cancel every order and close every position on the instrument (both sides), checked on the raw rows."""
    for o in acct.tl.orders():
        acct.tl.delete_order(o["id"])
    n = len(raw(acct))
    if n:
        acct.tl.close_all(acct.instr)
    time.sleep(3)
    left = raw(acct)
    say("closed %d positions; " % n + ("account is flat with no orders" if not left and not acct.tl.orders()
                                        else "STILL OPEN: %s - close it in TradeLocker" % left))
    return not left


def main():
    cfgs = tlmod.load_config(os.path.join(worker.HOME, "tradelocker.json"))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    want = args[0] if args else None
    cfgs = [c for c in cfgs if not want or c["name"] == want]
    if not cfgs:
        raise SystemExit("no TradeLocker account %s in ~/.p100-prop/tradelocker.json" % (want or ""))
    cfg = cfgs[0]
    tl = tlmod.TradeLocker(cfg["email"], worker.keychain(cfg["secret"]), cfg["server"], cfg.get("env", "live"))
    tl.select(cfg.get("acc_num"), cfg.get("account_id"))
    instr = tl.instrument((cfg["symbol"],) if cfg.get("symbol") else tlmod.NASDAQ_NAMES)
    acct = tlmod.TradeLockerAccount(tl, cfg, instr)
    if "--cleanup" in sys.argv:
        print("Cleaning up %s on %s" % (cfg["name"], instr.get("name")))
        cleanup(acct)
        return
    print("Testing %s (%s, %s) on %s" % (cfg["name"], cfg["server"], cfg.get("env", "live"), instr.get("name")))
    passed, steps = run_test(acct)
    rec = {"time": dt.datetime.now(worker.ET).isoformat(), "account": cfg["name"], "passed": passed, "steps": steps}
    path = os.path.join(worker.HOME, "tl_test.json")
    try:
        rows = json.load(open(path)) if os.path.exists(path) else []
    except ValueError:
        rows = []
    json.dump(rows + [rec], open(path, "w"), indent=1)
    print("TEST PASSED - safe to turn orders on." if passed else "TEST FAILED - keep orders off; paste this output to Claude.")


if __name__ == "__main__":
    main()
