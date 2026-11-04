"""One-shot live test of a TradeLocker prop account (Eightcap) before turning its orders on.
Buys the minimum size (0.01 lot), rests a take-profit limit far above the price, confirms both at the broker,
cancels the limit and closes. Cost: the spread on 0.01 lot (a few cents). Never runs if the account already has a
position or a resting order on the instrument, and always tries to clean up what it opened.
Run:  python3 ~/p100-prop/tl_test.py            (first account in ~/.p100-prop/tradelocker.json)
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


def wait(fn, ok, tries=20, pause=0.5, sleep=time.sleep):
    val = fn()
    for _ in range(tries):
        if ok(val):
            return val
        sleep(pause)
        val = fn()
    return val


def run_test(acct, lot=0.01, sleep=time.sleep, say=print):
    """Returns (passed, steps). acct: a tradelocker.TradeLockerAccount."""
    steps = []

    def step(name, good, info=""):
        steps.append({"step": name, "ok": bool(good), "info": info})
        say("%s %s %s" % ("OK  " if good else "FAIL", name, info))
        return good

    if acct.positions() or acct.open_orders():
        step("account is flat with no resting orders", False, "refusing to test on an account that is in use")
        return False, steps
    bal0 = acct.account()["balance"]
    step("signed in, balance %.2f" % bal0, True)
    opened, limit_id = False, None
    try:
        acct.market(acct.aid, acct.cid, BUY, lot, tag="tltest-buy")
        pos = wait(acct.positions, bool, sleep=sleep)
        opened = bool(pos)
        if not step("market buy %.2f lot filled" % lot, pos, "avg %.2f" % pos[0]["averagePrice"] if pos else "no position"):
            return False, steps
        tp = round(pos[0]["averagePrice"] * (1 + TP_FRAC), 2)
        acct.limit(acct.aid, acct.cid, SELL, lot, tp, tag="tltest-tp")
        orders = wait(acct.open_orders, bool, sleep=sleep)
        limit_id = orders[0]["id"] if orders else None
        if not step("take-profit limit resting", orders and abs(orders[0]["limitPrice"] - tp) < 0.02,
                    "sell %.2f @ %.2f" % (lot, tp) if orders else "no resting order"):
            return False, steps
        acct.cancel(acct.aid, limit_id)
        left = wait(acct.open_orders, lambda o: not o, sleep=sleep)
        if not step("take-profit cancelled", not left):
            return False, steps
        limit_id = None
        acct.close(acct.aid, acct.cid)
        flat = wait(acct.positions, lambda p: not p, sleep=sleep)
        if not step("position closed", not flat):
            return False, steps
        opened = False
        bal1 = acct.account()["balance"]
        step("round trip cost %.2f" % (bal1 - bal0), True)
        return True, steps
    except Exception as e:  # noqa: BLE001 - report and clean up below
        step("broker call", False, "%s: %s" % (type(e).__name__, e))
        return False, steps
    finally:
        try:
            for o in acct.open_orders():
                acct.cancel(acct.aid, o["id"])
            if opened and acct.positions():
                acct.close(acct.aid, acct.cid)
        except Exception as e:  # noqa: BLE001
            say("CLEANUP PROBLEM: %s - check the account in TradeLocker now" % e)


def main():
    cfgs = tlmod.load_config(os.path.join(worker.HOME, "tradelocker.json"))
    want = sys.argv[1] if len(sys.argv) > 1 else None
    cfgs = [c for c in cfgs if not want or c["name"] == want]
    if not cfgs:
        raise SystemExit("no TradeLocker account %s in ~/.p100-prop/tradelocker.json" % (want or ""))
    cfg = cfgs[0]
    tl = tlmod.TradeLocker(cfg["email"], worker.keychain(cfg["secret"]), cfg["server"], cfg.get("env", "live"))
    tl.select(cfg.get("acc_num"), cfg.get("account_id"))
    instr = tl.instrument((cfg["symbol"],) if cfg.get("symbol") else tlmod.NASDAQ_NAMES)
    acct = tlmod.TradeLockerAccount(tl, cfg, instr)
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
