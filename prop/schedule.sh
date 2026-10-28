#!/bin/bash
# Moves the bot's daily start to 7:45 AM ET (weekdays) so the London pre-market dry run can run from 8:00.
# The New York strategy still starts trading at 9:30. Run once:  bash ~/p100-prop/schedule.sh
PL="$HOME/Library/LaunchAgents/com.veloikos.p100prop.plist"
[ -f "$PL" ] || { echo "Bot schedule not found - run install.sh first."; exit 1; }
sed -i '' 's#<key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer>#<key>Hour</key><integer>7</integer><key>Minute</key><integer>45</integer>#g' "$PL"
launchctl unload "$PL" 2>/dev/null || true
launchctl load "$PL"
grep -c '<integer>7</integer><key>Minute</key><integer>45</integer>' "$PL" | xargs -I{} echo "Start time set to 7:45 AM on {} weekdays."
