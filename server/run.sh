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
# Listen only on the Tailscale interface (traffic inside WireGuard), unless --host or STASH_HOST
# says otherwise. An explicit --host wins, as it does in argparse.
HOST_ARG=""
prev=""
for a in "$@"; do
  case "$a" in --host=*) HOST_ARG="${a#--host=}";; esac
  [ "$prev" = "--host" ] && HOST_ARG="$a"
  prev="$a"
done
export STASH_HOST="${HOST_ARG:-${STASH_HOST:-$(tailscale ip -4 2>/dev/null | head -1)}}"
if [ -z "$STASH_HOST" ]; then
  echo "Tailscale 주소를 찾지 못했습니다. Tailscale을 켜거나 STASH_HOST를 지정하세요." >&2; exit 1
fi
echo "  주소: $STASH_HOST:$PORT"
echo "  토큰: $STASH_TOKEN"
echo

exec python3 stash_server.py --port "$PORT" "$@"
