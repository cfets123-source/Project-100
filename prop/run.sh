#!/bin/bash
# Started by launchd on weekdays. Keeps the Mac awake (caffeinate) while the bot runs; the bot exits after 4:05 PM ET.
CFG="$HOME/.p100-prop/config"; [ -f "$CFG" ] || exit 1
. "$CFG"
FLAG=""; [ "$ORDERS" = "1" ] && FLAG="--orders"
exec /usr/bin/caffeinate -i -s "${PY:-/usr/bin/python3}" "$HOME/p100-prop/worker.py" --account "$ACCOUNT" $FLAG
