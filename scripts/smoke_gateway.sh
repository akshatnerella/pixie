#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="/tmp/pixie_gateway_test.log"
TOKEN_FILE="/tmp/pixie_gateway_token_test"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"

rm -f "$LOG_FILE" "$TOKEN_FILE"

(zeroclaw gateway --port "$GATEWAY_PORT" >"$LOG_FILE" 2>&1) &
GW_PID=$!

cleanup() {
  kill "$GW_PID" >/dev/null 2>&1 || true
  wait "$GW_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 160); do
  if grep -Eq 'X-Pairing-Code: [0-9]{6}' "$LOG_FILE"; then
    break
  fi
  if ! kill -0 "$GW_PID" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

PAIRING_CODE="$(grep -Eo 'X-Pairing-Code: [0-9]{6}' "$LOG_FILE" | tail -n1 | awk '{print $2}')"
if [[ -z "${PAIRING_CODE:-}" ]]; then
  echo "Failed to find pairing code in gateway output:"
  sed -n '1,160p' "$LOG_FILE"
  exit 1
fi

echo "Pairing code found: $PAIRING_CODE"

cargo run -q -- \
  --gateway \
  --gateway-url "http://127.0.0.1:${GATEWAY_PORT}" \
  --pairing-code "$PAIRING_CODE" \
  --token-path "$TOKEN_FILE" \
  --ticks 6 \
  --interval-ms 120 \
  --gateway-every 2 \
  --message "Say exactly: pixie-gateway-ok"

echo
echo "Saved token:"
sed -n '1,3p' "$TOKEN_FILE"

