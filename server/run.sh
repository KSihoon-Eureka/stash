#!/bin/bash
# Starts the Stash receiver. Token is generated once and kept in ~/.config/stash/token.
# Usage: ./run.sh [--vault PATH] [--compile] [--port N]
set -euo pipefail
cd "$(dirname "$0")"

TOKEN_FILE="$HOME/.config/stash/token"
if [ ! -s "$TOKEN_FILE" ]; then
  mkdir -p "$(dirname "$TOKEN_FILE")"
  python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
export STASH_TOKEN="$(cat "$TOKEN_FILE")"
PORT="${STASH_PORT:-8765}"

echo "Stash 수신 서버 — iPhone Stash 앱에 아래 값을 입력하세요"
TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
[ -n "$TS_IP" ] && echo "  주소 (Tailscale, 어디서나): $TS_IP:$PORT"
[ -n "$LAN_IP" ] && echo "  주소 (같은 Wi-Fi):        $LAN_IP:$PORT"
echo "  토큰: $STASH_TOKEN"
echo

exec python3 stash_server.py --port "$PORT" "$@"
