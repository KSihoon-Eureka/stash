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
TS_IP="$(/sbin/ifconfig | grep -oE 'inet 100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9.]+' | head -1 | cut -d' ' -f2)"
echo "  주소 (Tailscale): ${TS_IP:-Tailscale 꺼짐 — 켜거나 --host 지정}:$PORT"
echo "  토큰: $STASH_TOKEN"
echo

exec python3 stash_server.py --port "$PORT" "$@"
