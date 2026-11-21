#!/bin/bash
# Turns aggressive sizing on (bigger size: about 4 contracts per $50K in evaluations) or off. Takes effect at the next
# start (weekdays 9:20 AM).   bash ~/p100-prop/aggressive.sh on   |   bash ~/p100-prop/aggressive.sh off
CFG="$HOME/.p100-prop/config"
grep -q '^AGGRESSIVE=' "$CFG" || echo 'AGGRESSIVE=0' >> "$CFG"
if [ "$1" = "on" ]; then sed -i '' 's/^AGGRESSIVE=.*/AGGRESSIVE=1/' "$CFG"; echo "Aggressive sizing ON from the next start."
elif [ "$1" = "off" ]; then sed -i '' 's/^AGGRESSIVE=.*/AGGRESSIVE=0/' "$CFG"; echo "Aggressive sizing OFF (standard sizing)."
else echo "usage: aggressive.sh on|off"; exit 1; fi
cat "$CFG"
