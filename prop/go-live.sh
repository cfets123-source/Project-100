#!/bin/bash
# Switches the bot from dry run to REAL orders on the configured account. Undo with:  go-live.sh off
CFG="$HOME/.p100-prop/config"; . "$CFG"
if [ "$1" = "off" ]; then sed -i '' 's/^ORDERS=.*/ORDERS=0/' "$CFG"; echo "Real orders OFF (dry run)."; exit 0; fi
echo "This lets the bot place REAL orders on TopstepX account '$ACCOUNT'. Type YES to confirm:"; read -r C
[ "$C" = "YES" ] || { echo "Cancelled."; exit 1; }
sed -i '' 's/^ORDERS=.*/ORDERS=1/' "$CFG"
echo "Real orders ON for '$ACCOUNT'. Takes effect at the next start (weekdays 9:20 AM) or now with:"
echo "  launchctl kickstart -k gui/$(id -u)/com.veloikos.p100prop"
