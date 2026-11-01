#!/bin/bash
# Keeps the receiver running in the background (starts at login, restarts on crash).
# Usage: ./install-launchagent.sh "/path/to/vault" [--compile]
set -euo pipefail
VAULT="${1:?vault path required}"; shift || true
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.sihoonkim.stash.plist"
# Resolve the Tailscale IP now, in the user's shell: the tailscale CLI can't reach the GUI app's
# daemon from inside a LaunchAgent. Tailscale IPs are stable per device. An explicit --host wins.
HOST_ARG=""
prev=""
for a in "$@"; do
  case "$a" in --host=*) HOST_ARG="${a#--host=}";; esac
  [ "$prev" = "--host" ] && HOST_ARG="$a"
  prev="$a"
done
HOST="${HOST_ARG:-${STASH_HOST:-$(tailscale ip -4 2>/dev/null | head -1)}}"
[ -n "$HOST" ] || { echo "Tailscale 주소를 찾지 못했습니다. Tailscale을 켜고 다시 실행하세요." >&2; exit 1; }
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
    <key>STASH_HOST</key><string>$HOST</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/stash.log</string>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/stash.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/com.sihoonkim.stash" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed: $PLIST  listening on $HOST  (logs: ~/Library/Logs/stash.log)"
