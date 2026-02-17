#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GW_PORT="${GW_PORT:-18080}"
UI_PORT="${UI_PORT:-18787}"
GW_LOG="/tmp/pixie_smoke_gateway.log"
UI_LOG="/tmp/pixie_smoke_ui.log"
UI_PID=0

rm -f "$GW_LOG" "$UI_LOG"

(zeroclaw gateway --port "$GW_PORT" >"$GW_LOG" 2>&1) &
GW_PID=$!

cleanup() {
  if [[ "$UI_PID" -gt 0 ]]; then
    kill "$UI_PID" >/dev/null 2>&1 || true
    wait "$UI_PID" >/dev/null 2>&1 || true
  fi
  kill "$GW_PID" >/dev/null 2>&1 || true
  wait "$GW_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 160); do
  if grep -Eq 'X-Pairing-Code: [0-9]{6}' "$GW_LOG"; then
    break
  fi
  sleep 0.25
done

PAIRING_CODE="$(grep -Eo 'X-Pairing-Code: [0-9]{6}' "$GW_LOG" | tail -n1 | awk '{print $2}')"
if [[ -z "${PAIRING_CODE:-}" ]]; then
  echo "Failed to read pairing code from gateway logs"
  sed -n '1,120p' "$GW_LOG"
  exit 1
fi

echo "Pairing code: $PAIRING_CODE"

(cargo run -q -- --serve --bind "127.0.0.1:${UI_PORT}" --gateway-url "http://127.0.0.1:${GW_PORT}" >"$UI_LOG" 2>&1) &
UI_PID=$!

for _ in $(seq 1 160); do
  if curl -fsS "http://127.0.0.1:${UI_PORT}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

echo "Health:"
curl -fsS "http://127.0.0.1:${UI_PORT}/api/health"
echo

echo "Pairing:"
curl -fsS -X POST "http://127.0.0.1:${UI_PORT}/api/pairing" \
  -H "Content-Type: application/json" \
  -d "{\"pairing_code\":\"${PAIRING_CODE}\"}"
echo

echo "Chat:"
curl -fsS -X POST "http://127.0.0.1:${UI_PORT}/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"Say exactly: pixie-frontend-ok"}'
echo

echo "Frontend smoke test complete."
