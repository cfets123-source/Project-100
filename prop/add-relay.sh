#!/bin/bash
# Adds an account at another firm (or a TradersPost paper account) that the bot trades through a webhook relay.
# The webhook URL is typed here (hidden) and stored only in the macOS Keychain. Run:  bash ~/p100-prop/add-relay.sh
set -e
CFG="$HOME/.p100-prop/relay.json"; mkdir -p "$HOME/.p100-prop"
echo "Firm name (e.g. TradersPost-Paper, Lucid, MFFU):"; read -r FIRM
echo "Account label, no spaces (e.g. TP-PAPER-1 or LUCID-50K-FLEX-1):"; read -r NAME
echo "Account type: eval, funded or practice (TradersPost paper = practice):"; read -r KIND
echo "Contract symbol the relay expects (press Enter for MNQ1!):"; read -r TICKER
echo "Webhook URL from the relay (paste it; it will not be shown):"; read -rs URL; echo
[ -n "$FIRM" ] && [ -n "$NAME" ] && [ -n "$URL" ] || { echo "Missing value - nothing saved."; exit 1; }
case "$KIND" in eval) KIND=combine;; funded|practice) ;; *) echo "Type must be eval, funded or practice"; exit 1;; esac
SECRET="p100-relay-$NAME"
security delete-generic-password -s "$SECRET" >/dev/null 2>&1 || true
security add-generic-password -s "$SECRET" -a p100 -w "$URL"
unset URL
/usr/bin/python3 - "$CFG" "$FIRM" "$NAME" "$KIND" "${TICKER:-MNQ1!}" "$SECRET" <<'PY'
import json, os, sys
path, firm, name, kind, ticker, secret = sys.argv[1:]
cfg = json.load(open(path)) if os.path.exists(path) else []
cfg = [c for c in cfg if c.get("name") != name]
cfg.append({"firm": firm, "name": name, "kind": kind, "size_k": 50, "start_balance": 50000, "ticker": ticker,
            "secret": secret})
json.dump(cfg, open(path, "w"), indent=1)
print("Saved. Accounts traded through relays:", ", ".join(c["firm"] + " " + c["name"] for c in cfg))
PY
echo "The bot picks this up at its next start (weekdays 9:20 AM). Orders go out only when real orders are ON."
