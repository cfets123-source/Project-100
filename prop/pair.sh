#!/bin/bash
# Connects this Mac's prop bot to the Veloikos app. Get the code in the app: Prop challenge -> Get pairing code.
#   bash ~/p100-prop/pair.sh CODE
[ -n "$1" ] || { echo "Usage: bash ~/p100-prop/pair.sh CODE (from the app)"; exit 1; }
security delete-generic-password -s p100-prop-token >/dev/null 2>&1 || true
security add-generic-password -s p100-prop-token -a p100 -w "$1"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "X-Prop-Token: $1" \
  -d '{"status":{"note":"Mac paired"},"events":[{"id":"pair-'"$(date +%s)"'","time":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","kind":"day","text":"Mac paired with the app"}]}' \
  https://trade.veloikos.com/prop/feed)
[ "$code" = "200" ] && echo "PAIRED - the app now shows this Mac's bot." || echo "Pairing failed (HTTP $code). Get a new code in the app and try again."
