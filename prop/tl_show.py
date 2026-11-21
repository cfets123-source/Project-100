"""Read-only: print every open position and order on the TradeLocker account(s), raw. Run: python3 ~/p100-prop/tl_show.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelocker as tlmod  # noqa: E402
import worker  # noqa: E402
for cfg in tlmod.load_config(os.path.join(worker.HOME, "tradelocker.json")):
    tl = tlmod.TradeLocker(cfg["email"], worker.keychain(cfg["secret"]), cfg["server"], cfg.get("env", "live"))
    tl.select(cfg.get("acc_num"), cfg.get("account_id"))
    st = tl.state()
    print("%s orders=%s balance=%s projected=%s todayNet=%s positions=%s" % (cfg["name"], cfg.get("orders"), st.get("balance"),
          st.get("projectedBalance"), st.get("todayNet"), st.get("positionsCount")))
    for p in tl.positions():
        print("  POSITION", {k: p.get(k) for k in ("id", "side", "qty", "avgPrice", "openDate", "unrealizedPl", "takeProfitId", "stopLossId")})
    for o in tl.orders():
        print("  ORDER   ", {k: o.get(k) for k in ("id", "side", "qty", "type", "price", "status", "positionId")})
