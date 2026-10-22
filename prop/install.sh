#!/bin/bash
# Installs the prop-challenge bot on this Mac. Run in Terminal:  bash ~/Documents/p100-prop/install.sh
# - stores your TopstepX username + API key in the macOS Keychain (typed by you, never shown or sent anywhere else)
# - copies the bot to ~/p100-prop and schedules it for weekdays 9:20 AM (keeps the Mac awake while it runs)
# - starts in DRY RUN (no orders). go-live.sh switches real orders on.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"; DST="$HOME/p100-prop"; CFG="$HOME/.p100-prop"
mkdir -p "$DST" "$CFG"
cp "$SRC"/topstepx.py "$SRC"/noise.py "$SRC"/guard.py "$SRC"/worker.py "$SRC"/run.sh "$SRC"/go-live.sh "$SRC"/pair.sh "$DST"/
chmod +x "$DST"/run.sh "$DST"/go-live.sh "$DST"/pair.sh
command -v python3 >/dev/null || { echo "python3 missing: run  xcode-select --install  then re-run this script"; exit 1; }
python3 -c "import zoneinfo" || { echo "python3 is older than 3.9; install Python 3 from python.org"; exit 1; }
echo "TopstepX sign-in username (the platform username, not your email):"; read -r U
echo "TopstepX API key (paste it; it will not be shown):"; read -rs K; echo
security delete-generic-password -s p100-topstepx-user >/dev/null 2>&1 || true
security delete-generic-password -s p100-topstepx-key  >/dev/null 2>&1 || true
security add-generic-password -s p100-topstepx-user -a p100 -w "$U"
security add-generic-password -s p100-topstepx-key  -a p100 -w "$K"
unset K
echo "Checking the connection (no orders)..."
python3 "$DST/worker.py" --check
echo; echo "Accounts to trade: ALL = every Combine and funded account on this login, now and future (never Live or practice),"
echo "or part of one account name (e.g. 50K):"; read -r A
printf 'ACCOUNT=%s\nORDERS=0\nPY=%s\n' "$A" "$(command -v python3)" > "$CFG/config"
PL="$HOME/Library/LaunchAgents/com.veloikos.p100prop.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PL" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.veloikos.p100prop</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DST/run.sh</string></array>
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>20</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$CFG/launchd.log</string>
  <key>StandardErrorPath</key><string>$CFG/launchd.log</string>
</dict></plist>
PLIST
launchctl unload "$PL" 2>/dev/null || true
launchctl load "$PL"
echo; echo "Pairing code from the app (Prop challenge -> Get pairing code), or press Enter to skip:"; read -r P
[ -n "$P" ] && bash "$DST/pair.sh" "$P"
echo; echo "INSTALLED. The bot runs weekdays from 9:20 AM (Mac time, set for Eastern) in DRY RUN on account '$A'."
echo "Log: $CFG/bot.log   Status: $CFG/status.json (copy in ~/Documents/p100-prop/data)"
echo "To place real orders later:  bash $DST/go-live.sh"
