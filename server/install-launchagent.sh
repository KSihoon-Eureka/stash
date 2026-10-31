#!/bin/bash
# Keeps the receiver running in the background (starts at login, restarts on crash).
# Usage: ./install-launchagent.sh "/path/to/vault" [--compile]
set -euo pipefail
VAULT="${1:?vault path required}"; shift || true
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.sihoonkim.stash.plist"
ARGS=""
for a in --vault "$VAULT" "$@"; do ARGS+="    <string>$a</string>"$'\n'; done

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sihoonkim.stash</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/run.sh</string>
$ARGS  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/stash.log</string>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/stash.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/com.sihoonkim.stash" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed: $PLIST  (logs: ~/Library/Logs/stash.log)"
