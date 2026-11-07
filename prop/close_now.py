"""Owner's "close now" button: closes the open trade on every live account right now and logs it.
It does NOT stop the bot: the bot keeps running and re-enters at its next hourly check if the rules still say so.
Run:  python3 ~/p100-prop/close_now.py"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worker  # noqa: E402
from topstepx import LIMIT, TopstepX  # noqa: E402

LOG = os.path.join(worker.HOME, "manual_closes.json")


def close_all(api, accounts, cid, now, log_path=LOG):
    done = []
    for a in accounts:
        for o in api.open_orders(a["id"]):           # resting take-profit first, so it can't fill after the close
            if o.get("contractId") == cid and o.get("type") == LIMIT:
                api.cancel(a["id"], o["id"])
        pos = [p for p in api.positions(a["id"]) if p.get("contractId") == cid]
        if not pos:
            done.append({"account": a.get("name"), "closed": False, "note": "already flat"})
            continue
        p = pos[0]
        api.close(a["id"], cid)
        done.append({"account": a.get("name"), "closed": True, "size": p.get("size"),
                     "side": "long" if p.get("type") == 1 else "short", "avg": p.get("averagePrice")})
    rec = {"time": now.isoformat(), "results": done}
    hist = json.load(open(log_path)) if os.path.exists(log_path) else []
    with open(log_path, "w") as f:
        json.dump(hist + [rec], f, indent=1)
    return done


def main():
    api = TopstepX(*worker.credentials())
    cfg = dict(l.strip().split("=", 1) for l in open(os.path.join(worker.HOME, "config")) if "=" in l)
    accounts = worker.select_accounts(api.accounts(), cfg.get("ACCOUNT", "ALL"))
    cid = api.contract("MNQ")["id"]
    for r in close_all(api, accounts, cid, dt.datetime.now(worker.ET)):
        if r["closed"]:
            print("CLOSED %s: %s %s @ avg %s" % (r["account"], r["side"], r["size"], r["avg"]))
        else:
            print("%s: %s" % (r["account"], r["note"]))
    print("Done. The bot keeps running and can re-enter at its next hourly check.")


if __name__ == "__main__":
    main()
