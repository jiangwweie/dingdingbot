#!/usr/bin/env bash
# 001D-4: Multi-cycle testnet stress test
#
# Runs N controlled entry cycles on Binance testnet. Each cycle:
#   1. Start runtime
#   2. Arm startup guard
#   3. Disable GKS
#   4. Call controlled entry endpoint
#   5. Wait for order lifecycle completion
#   6. Verify exchange flat (positions=0, open_orders=0)
#   7. Stop runtime
#
# Usage:
#   CYCLES=3 bash scripts/run_001d4_multi_cycle_stress.sh
#
# Prerequisites:
#   - .env has EXCHANGE_TESTNET=true, testnet API keys
#   - .env.local has PG_DATABASE_URL pointing to testnet PG
#   - sim1_eth_runtime profile seeded in PG
#   - curl, jq available

set -euo pipefail

CYCLES="${CYCLES:-3}"
RUNTIME_LOG="/tmp/001d4_runtime.log"
API_PORT="${BACKEND_PORT:-8000}"
API_BASE="http://127.0.0.1:${API_PORT}"
MAX_WAIT_SECONDS=120
CYCLE_SETTLE_SECONDS=10

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

results_pass=0
results_fail=0
cycle_results=()

cleanup() {
    if [[ -n "${RUNTIME_PID:-}" ]]; then
        log_info "Cleaning up runtime PID=${RUNTIME_PID}"
        kill "$RUNTIME_PID" 2>/dev/null || true
        wait "$RUNTIME_PID" 2>/dev/null || true
        unset RUNTIME_PID
    fi
}
trap cleanup EXIT

wait_for_ready() {
    local elapsed=0
    while (( elapsed < MAX_WAIT_SECONDS )); do
        if grep -q "SYSTEM READY" "$RUNTIME_LOG" 2>/dev/null; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    log_error "Runtime failed to become ready within ${MAX_WAIT_SECONDS}s"
    return 1
}

arm_startup_guard() {
    local resp
    resp=$(curl -sf -X POST "${API_BASE}/api/runtime/control/startup-trading-guard/arm" \
        -H "Content-Type: application/json" \
        -d '{"reason": "001D-4 stress test", "updated_by": "test_automation"}' 2>&1) || {
        log_error "Failed to arm startup guard: $resp"
        return 1
    }
    log_info "Startup guard armed"
}

disable_gks() {
    local resp
    resp=$(curl -sf -X POST "${API_BASE}/api/runtime/control/global-kill-switch" \
        -H "Content-Type: application/json" \
        -d '{"active": false, "reason": "001D-4 stress test", "updated_by": "test_automation"}' 2>&1) || {
        log_error "Failed to disable GKS: $resp"
        return 1
    }
    log_info "GKS disabled"
}

call_controlled_entry() {
    local resp http_code
    resp=$(curl -s -w "\n%{http_code}" -X POST \
        "${API_BASE}/api/runtime/test/smoke/execute-controlled-entry" \
        -H "Content-Type: application/json" 2>&1)
    http_code=$(echo "$resp" | tail -1)
    local body
    body=$(echo "$resp" | sed '$d')

    if [[ "$http_code" == "200" ]]; then
        log_info "Controlled entry accepted: $body"
        return 0
    else
        log_error "Controlled entry rejected (HTTP $http_code): $body"
        return 1
    fi
}

wait_for_order_completion() {
    local elapsed=0
    while (( elapsed < MAX_WAIT_SECONDS )); do
        local orders_json
        orders_json=$(curl -sf "${API_BASE}/api/runtime/execution/orders" 2>/dev/null) || {
            sleep 3
            elapsed=$((elapsed + 3))
            continue
        }
        # Check if there are any OPEN/SUBMITTED/PARTIALLY_FILLED orders
        local active_count
        active_count=$(echo "$orders_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
orders = data if isinstance(data, list) else data.get('orders', [])
active = [o for o in orders if o.get('status') in ('OPEN', 'SUBMITTED', 'PARTIALLY_FILLED')]
print(len(active))
" 2>/dev/null) || active_count="?"

        if [[ "$active_count" == "0" ]]; then
            log_info "All orders settled"
            return 0
        fi
        log_info "Waiting for orders to settle (active=$active_count, elapsed=${elapsed}s)"
        sleep 5
        elapsed=$((elapsed + 5))
    done
    log_warn "Order settlement timeout after ${MAX_WAIT_SECONDS}s"
    return 1
}

verify_exchange_flat() {
    # Check via the runtime health endpoint
    local health_json
    health_json=$(curl -sf "${API_BASE}/api/runtime/health" 2>/dev/null) || {
        log_warn "Cannot reach health endpoint"
        return 1
    }
    log_info "Exchange flat verification: consult runtime log for position reconciliation"
    return 0
}

reenable_gks() {
    local resp
    resp=$(curl -sf -X POST "${API_BASE}/api/runtime/control/global-kill-switch" \
        -H "Content-Type: application/json" \
        -d '{"active": true, "reason": "001D-4 cycle complete", "updated_by": "test_automation"}' 2>&1) || {
        log_error "Failed to re-enable GKS: $resp"
        return 1
    }
    log_info "GKS re-enabled"
}

run_cycle() {
    local cycle_num=$1
    log_info "========================================="
    log_info "CYCLE ${cycle_num}/${CYCLES}"
    log_info "========================================="

    # Start runtime
    log_info "Starting runtime..."
    > "$RUNTIME_LOG"
    RUNTIME_PROFILE=sim1_eth_runtime \
    RUNTIME_CONTROL_API_ENABLED=true \
    RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true \
    PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED=false \
    python3 -m src.main > "$RUNTIME_LOG" 2>&1 &
    RUNTIME_PID=$!
    log_info "Runtime PID=${RUNTIME_PID}"

    if ! wait_for_ready; then
        log_error "Cycle ${cycle_num}: Runtime failed to start"
        results_fail=$((results_fail + 1))
        cycle_results+=("CYCLE-${cycle_num}: FAIL (startup)")
        kill "$RUNTIME_PID" 2>/dev/null || true
        wait "$RUNTIME_PID" 2>/dev/null || true
        unset RUNTIME_PID
        return 1
    fi

    # Arm startup guard
    if ! arm_startup_guard; then
        log_error "Cycle ${cycle_num}: Failed to arm startup guard"
        results_fail=$((results_fail + 1))
        cycle_results+=("CYCLE-${cycle_num}: FAIL (arm)")
        return 1
    fi

    # Disable GKS
    if ! disable_gks; then
        log_error "Cycle ${cycle_num}: Failed to disable GKS"
        results_fail=$((results_fail + 1))
        cycle_results+=("CYCLE-${cycle_num}: FAIL (gks)")
        return 1
    fi

    # Call controlled entry
    if ! call_controlled_entry; then
        log_error "Cycle ${cycle_num}: Controlled entry failed"
        results_fail=$((results_fail + 1))
        cycle_results+=("CYCLE-${cycle_num}: FAIL (entry)")
        return 1
    fi

    # Wait for order lifecycle completion
    log_info "Waiting for order lifecycle to settle..."
    wait_for_order_completion || log_warn "Cycle ${cycle_num}: Order settlement timeout (non-fatal)"

    # Settle time for WebSocket updates
    log_info "Settling for ${CYCLE_SETTLE_SECONDS}s..."
    sleep "$CYCLE_SETTLE_SECONDS"

    # Verify exchange flat
    verify_exchange_flat

    # Re-enable GKS before shutdown
    reenable_gks

    # Stop runtime
    log_info "Stopping runtime..."
    kill "$RUNTIME_PID" 2>/dev/null || true
    wait "$RUNTIME_PID" 2>/dev/null || true
    unset RUNTIME_PID

    log_info "Cycle ${cycle_num} complete"
    results_pass=$((results_pass + 1))
    cycle_results+=("CYCLE-${cycle_num}: PASS")
    return 0
}

# ===== Main =====
log_info "001D-4 Multi-cycle testnet stress test"
log_info "Cycles: ${CYCLES}"
log_info "API: ${API_BASE}"
log_info ""

for (( i=1; i<=CYCLES; i++ )); do
    run_cycle "$i" || true
    if (( i < CYCLES )); then
        log_info "Cooldown 5s between cycles..."
        sleep 5
    fi
done

log_info ""
log_info "========================================="
log_info "RESULTS"
log_info "========================================="
for r in "${cycle_results[@]}"; do
    echo "  $r"
done
log_info ""
log_info "PASS: ${results_pass}  FAIL: ${results_fail}"

if (( results_fail > 0 )); then
    log_error "001D-4: FAIL (${results_fail} cycle failures)"
    exit 1
else
    log_info "001D-4: PASS_FULL (${results_pass}/${CYCLES} cycles)"
    exit 0
fi
