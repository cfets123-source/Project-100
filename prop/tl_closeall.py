"""Close EVERY open position (both sides) on the TradeLocker instrument and cancel its orders, then show what is left.
For hedging accounts, where buys and sells are separate positions. Run: python3 ~/p100-prop/tl_closeall.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelocker as tlmod  # noqa: E402
import worker  # noqa: E402
for cfg in tlmod.load_config(os.path.join(worker.HOME, "tradelocker.json")):
    tl = tlmod.TradeLocker(cfg["email"], worker.keychain(cfg["secret"]), cfg["server"], cfg.get("env", "live"))
    tl.select(cfg.get("acc_num"), cfg.get("account_id"))
    instr = tl.instrument((cfg["symbol"],) if cfg.get("symbol") else tlmod.NASDAQ_NAMES)
    for o in tl.orders():
        tl.delete_order(o["id"])
    n = len(tl.positions())
    if n:
        tl.close_all(instr)
    time.sleep(4)
    left, st = tl.positions(), tl.state()
    print("%s: closed %d positions; now open %d; balance %s; todayNet %s" % (cfg["name"], n, len(left), st.get("balance"), st.get("todayNet")))
    print("FLAT" if not left else "STILL OPEN - close them in TradeLocker")
