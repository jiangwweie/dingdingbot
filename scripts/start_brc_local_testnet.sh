#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ -f ".env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.local"
  set +a
fi

# Local acceptance defaults. Production/cloud must override these explicitly.
export EXCHANGE_TESTNET=true
export RUNTIME_PROFILE=brc_btc_eth_testnet_runtime
export RUNTIME_CONTROL_API_ENABLED=true
export RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "BRC local testnet defaults:"
echo "  EXCHANGE_TESTNET=${EXCHANGE_TESTNET}"
echo "  RUNTIME_PROFILE=${RUNTIME_PROFILE}"
echo "  RUNTIME_CONTROL_API_ENABLED=${RUNTIME_CONTROL_API_ENABLED}"
echo "  RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=${RUNTIME_TEST_SIGNAL_INJECTION_ENABLED}"
echo "  BACKEND_PORT=${BACKEND_PORT}"
echo "  FRONTEND_PORT=${FRONTEND_PORT}"

APPLY=true python3 scripts/seed_brc_profile.py

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

python3 src/main.py &
BACKEND_PID=$!

(
  cd gemimi-web-front
  VITE_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}" npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

echo
echo "BRC local testnet console:"
echo "  frontend: http://127.0.0.1:${FRONTEND_PORT}/guide"
echo "  backend:  http://127.0.0.1:${BACKEND_PORT}"
echo
echo "Press Ctrl+C to stop both processes."

wait "$BACKEND_PID" "$FRONTEND_PID"
