#!/bin/bash
# Adds a TradeLocker prop account (Eightcap Challenges, Goat Funded Trader ...) for the bot. The password is typed here
# (hidden) and stored only in the macOS Keychain. New accounts start in DRY RUN (no orders) until the test is confirmed.
# Run:  bash ~/p100-prop/add-tradelocker.sh
set -e
CFG="$HOME/.p100-prop/tradelocker.json"; mkdir -p "$HOME/.p100-prop"
echo "Firm: eightcap (1-step) or gft (Goat Funded Trader 2-step Standard):"; read -r FIRM
echo "Stage: 1 (challenge / phase 1), 2 (phase 2, GFT only) or funded:"; read -r STAGE
echo "Account label, no spaces (e.g. EIGHTCAP-5K-1 or GFT-5K-P1):"; read -r NAME
echo "Environment: live or demo (prop challenge accounts are usually live):"; read -r ENVN
echo "TradeLocker login email:"; read -r EMAIL
echo "TradeLocker server name (shown on the TradeLocker login screen):"; read -r SERVER
echo "Account size in dollars (e.g. 5000):"; read -r SIZE
echo "TradeLocker password (it will not be shown):"; read -rs PW; echo
[ -n "$NAME" ] && [ -n "$EMAIL" ] && [ -n "$SERVER" ] && [ -n "$PW" ] && [ -n "$SIZE" ] || { echo "Missing value - nothing saved."; exit 1; }
case "$FIRM" in eightcap|gft) ;; *) echo "Firm must be eightcap or gft"; exit 1;; esac
case "$STAGE" in 1|2|funded) ;; *) echo "Stage must be 1, 2 or funded"; exit 1;; esac
case "$ENVN" in demo|live) ;; *) echo "Environment must be demo or live"; exit 1;; esac
SECRET="p100-tl-$NAME"
security delete-generic-password -s "$SECRET" >/dev/null 2>&1 || true
security add-generic-password -s "$SECRET" -a p100 -w "$PW"
unset PW
/usr/bin/python3 - "$CFG" "$FIRM" "$STAGE" "$NAME" "$ENVN" "$EMAIL" "$SERVER" "$SIZE" "$SECRET" <<'PY'
import json, os, sys
path, firm, stage, name, env, email, server, size, secret = sys.argv[1:]
size = float(size)
# firm rules: (phase targets, static max loss, firm daily loss, minimum trading days per phase)
PRESETS = {"eightcap": {"label": "Eightcap", "targets": {"1": 0.10}, "mll": 0.08, "daily": 0.04, "min_days": 5},
           "gft": {"label": "Goat Funded Trader", "targets": {"1": 0.10, "2": 0.05}, "mll": 0.10, "daily": 0.05, "min_days": 3}}
p = PRESETS[firm]
if stage != "funded" and stage not in p["targets"]:
    sys.exit("%s has no stage %s" % (p["label"], stage))
funded = stage == "funded"
rules = {"mll": p["mll"] * size, "daily_stop": 0.75 * p["daily"] * size, "mll_buffer": 0.012 * size,
         "static_mll": True, "consistency": 1.0, "min_days": 0 if funded else p["min_days"]}
if not funded:
    rules["target"] = p["targets"][stage] * size
cfg = json.load(open(path)) if os.path.exists(path) else []
cfg = [c for c in cfg if c.get("name") != name]
cfg.append({"firm": p["label"], "name": name, "env": env, "email": email, "server": server, "secret": secret,
            "acc_num": None, "symbol": None, "start_balance": size, "kind": "funded" if funded else "combine",
            "leverage": 3, "point_value": None, "tick": 0.01, "orders": False, "news_blackout": True, "rules": rules})
json.dump(cfg, open(path, "w"), indent=1)
print("Saved %s (%s stage %s, dry run). Next: python3 ~/p100-prop/worker.py --check" % (name, p["label"], stage))
PY
