# TC-TINY-001D-1: Controlled Testnet Order Lifecycle Smoke — Proposal & Runbook

**Status**: PROPOSAL — awaiting Owner approval
**Date**: 2026-05-19
**Prepared by**: Claude (execution worker)
**Authorization boundary**: Owner must approve before Step 9 (first testnet ENTRY)

---

## 1. Verdict

**READY FOR OWNER REVIEW** — all preconditions are satisfied or documented. No blockers prevent proposal from being approved. Two items require Owner decision before execution.

---

## 2. Preconditions

| # | Condition | Status | Notes |
|---|-----------|--------|-------|
| P-1 | 001D-0 observe-only preflight PASS | PASS | Completed 2026-05-19, all phases 1-9, zero mutations |
| P-2 | RUNTIME_PROFILE=sim1_eth_runtime | CONFIRMED | Only profile in PG, active=true, readonly=true |
| P-3 | EXCHANGE_TESTNET=true | CONFIRMED | In .env, also default in code (`runtime_config.py:348`) |
| P-4 | GKS active=true | CONFIRMED | reason=GKS_SEEDED_ACTIVE, updated_by=ops_seed_gks_state |
| P-5 | Startup guard default blocked | CONFIRMED | `default_armed=False` in `startup_trading_guard.py:30` |
| P-6 | No live key / no live profile | CONFIRMED | Single PG profile has no credential fields; keys are env-sourced with EXCHANGE_TESTNET=true |
| P-7 | Testnet account funded | CONFIRMED | Balance: 8283.92 USDT (available) |
| P-8 | StrategySignalV2 observe disabled | CONFIRMED | Runtime log: `StrategySignalV2 observe disabled` |
| P-9 | No Direction A | CONFIRMED | Not activated in 001D-0 |

### P-10: Reconciliation Read Model FK Persistence Bug

**Finding**: During 001D-0, the periodic reconciliation cycle (10:06:33) triggered a `ForeignKeyViolationError` on `reconciliation_read_model_mismatches.report_id`. The report INSERT and mismatch INSERTs are within the same `session.begin()` transaction (`pg_reconciliation_read_model_repository.py:38-67`). The most likely root cause is a duplicate `report_id` UNIQUE constraint violation on the report INSERT, which rolls back the entire transaction; the mismatch INSERT's FK error is a secondary symptom visible in the error log.

**Impact on 001D-1**: NON-BLOCKING. The reconciliation read model is a reporting layer only. The actual reconciliation logic (`build_read_model()`) still runs and detects mismatches. Protection health monitoring is unaffected. The stale data hygiene items (821 local SL rows) will persist but are classified as `report_only`, not `block`.

**Decision**: Proceed without fixing. If the bug recurs during 001D-1, it will produce an ERROR log but will not crash the runtime (caught by `_save_reconciliation_result_best_effort` at `periodic_reconciliation.py:140`).

### P-11: RUNTIME_CONTROL_API_ENABLED

Required for Steps 3 (arm startup guard) and 5 (disable GKS). Must be set to `true` for the duration of Steps 3-5, then can be set back to `false`.

### P-12: PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED

Keep `false` throughout. Prevents Feishu alert fan-out during test.

---

## 3. Owner Approval Boundary

### What produces the first real testnet ENTRY

**Step 9** in the execution sequence below is the first step that submits a real order to the Binance testnet exchange via `ExchangeGateway.place_order()` → `rest_exchange.create_order()`.

Everything before Step 9 is either:
- Read-only verification (Steps 1-2, 4)
- Internal state mutation with no exchange contact (Steps 3, 5-8)
- Verification that the synthetic signal passes all guard checks (Step 7-8)

### What Owner must approve

1. **Arm startup guard** (Step 3) — internal state change, no exchange contact
2. **Disable GKS** (Step 5) — PG state change, no exchange contact, but unblocks execution path
3. **Proceed to Step 9** — first testnet ENTRY order submission

### What 001D-1 allows

- Testnet ENTRY, SL, TP on ETH/USDT:USDT perpetual
- Maximum 1 test entry cycle (ENTRY → fill → SL/TP mount → exit)
- Order size: 0.01 ETH (notional ~21.24 USDT, minimum viable)
- All operations on Binance testnet only

### What 001D-1 does NOT allow

- Live key / live profile
- Direction A / StrategySignalV2 execution
- Auto-remount / recovery worker
- Any mainnet operation
- Multiple test cycles without re-approval

---

## 4. Execution Sequence

### Environment

```bash
export RUNTIME_PROFILE=sim1_eth_runtime
export RUNTIME_CONTROL_API_ENABLED=true    # Steps 3-5 only; set false after Step 5
export PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED=false
```

### Synthetic Signal Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| symbol | ETH/USDT:USDT | Matches runtime profile |
| direction | LONG | Only allowed direction in profile |
| order_type | MARKET | Simulates real signal entry |
| amount | 0.01 ETH | Notional ~21.24 USDT (>20 min_notional) |
| stop_loss_rr | -1.0 | Matches profile default (`initial_stop_loss_rr=-1.0`) |
| SL price | ~2103.02 (1% below entry) | Per profile's RR-based SL |
| TP targets | [1.0, 3.5] RR | Matches profile (`tp_targets=["1.0","3.5"]`) |
| TP ratios | [0.5, 0.5] | 50% at each TP level |

Capital protection check estimate:
- Single trade loss: 0.01 * 21.24 * 1% = ~0.21 USDT (limit: 82.84 USDT) → PASS
- Position limit: 0.01 * 2124 = ~21.24 USDT (limit: 8283.92 USDT) → PASS
- Daily trade count: 0 (limit: 10) → PASS
- Daily loss: 0 (limit: 828.39 USDT) → PASS
- Min balance: 8283.92 > min_balance → PASS

### Step-by-Step

#### Step 1: Start Runtime

```bash
RUNTIME_PROFILE=sim1_eth_runtime \
RUNTIME_CONTROL_API_ENABLED=true \
PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED=false \
python3 -m src.main > /tmp/001d1_runtime.log 2>&1 &
echo "PID=$!"
```

**Verify**: Wait for `SYSTEM READY - Monitoring started` in log. Confirm:
- exchange_testnet=true in safe summary
- GKS active=True restored
- Startup guard NOT_ARMED
- StrategySignalV2 observe disabled
- exchange testnet=True

#### Step 2: Verify Blocked Path

Attempt to inject a synthetic signal. It should be BLOCKED by startup guard.

```python
# One-shot script: scripts/001d1_test_signal.py
# Constructs SignalResult + OrderStrategy, calls _execution_orchestrator.execute_signal()
# Expected: status=BLOCKED, blocked_reason=STARTUP_TRADING_GUARD_NOT_ARMED
```

**Verify**: ExecutionIntent has `status=BLOCKED`, `blocked_reason=STARTUP_TRADING_GUARD_BLOCK_REASON`. No exchange call made.

**How to inject**: The running FastAPI server exposes the global `_execution_orchestrator`. The cleanest approach is a one-shot async script that:
1. Imports `src.main._execution_orchestrator` (module-level global)
2. Constructs a minimal `SignalResult` with the parameters above
3. Calls `await _execution_orchestrator.execute_signal(signal, strategy)`
4. Returns the ExecutionIntent status

Alternative: Add a temporary test endpoint `POST /api/runtime/test/execute-signal` gated behind `RUNTIME_CONTROL_API_ENABLED=true` and `EXCHANGE_TESTNET=true`. This endpoint would call `_execution_orchestrator.execute_signal()` directly. **This does NOT modify strategy logic** — it bypasses the strategy engine entirely and feeds a pre-constructed signal into the orchestrator.

#### Step 3: Arm Startup Guard

```bash
curl -s -X POST http://localhost:8000/api/runtime/control/startup-trading-guard/arm \
  -H "Content-Type: application/json" \
  -d '{"reason": "001D-1 smoke test - owner approved", "updated_by": "owner"}'
```

**Verify**: Response shows `armed=true`. Log shows `control.startup_trading_guard_arm` trace.

**Requires**: `RUNTIME_CONTROL_API_ENABLED=true`

#### Step 4: Verify GKS Still Blocks

Inject synthetic signal again. Should be BLOCKED by GKS (not startup guard this time).

**Verify**: ExecutionIntent has `status=BLOCKED`, `blocked_reason=KILL_SWITCH`.

#### Step 5: Disable GKS (OWNER APPROVAL REQUIRED)

```bash
curl -s -X POST http://localhost:8000/api/runtime/control/global-kill-switch \
  -H "Content-Type: application/json" \
  -d '{"active": false, "reason": "001D-1 controlled smoke - owner approved testnet only", "updated_by": "owner"}'
```

**Verify**: Response shows `active=false`. GKS is now inactive.

**Requires**: `RUNTIME_CONTROL_API_ENABLED=true`

After this step, set `RUNTIME_CONTROL_API_ENABLED=false` (no more mutations needed via API).

#### Step 6: Inject Synthetic Signal (OWNER APPROVAL REQUIRED — first exchange contact)

```bash
# One-shot script that constructs synthetic SignalResult and calls execute_signal()
# Entry: MARKET LONG 0.01 ETH/USDT:USDT
# SL: -1.0 RR (~2103.02)
# TP1: 1.0 RR (~2145.50), 50%
# TP2: 3.5 RR (~2198.28), 50%
```

#### Step 7: Verify ExecutionIntent

**Verify** (via log + `GET /api/runtime/execution/intents`):
- Intent status transitions: PENDING → (guard checks pass) → SUBMITTED
- CapitalProtection trace: `decision=allow`, all checks pass
- Log shows `create_order_chain` for ENTRY order
- Log shows `place_order` for ENTRY with `reduce_only=False`

#### Step 8: Verify CapitalProtection Allow Trace

```bash
curl -s http://localhost:8000/api/runtime/events | python3 -m json.tool
```

**Verify**: Trace event `capital_protection:ETH/USDT:USDT:market:*` shows `decision=allow` with metadata including all check results.

#### Step 9: Verify Testnet ENTRY Submitted

**Verify** (via log):
- `place_order` call to Binance testnet with symbol=ETH/USDT:USDT, type=market, side=buy, amount=0.01
- Exchange returns order with `exchange_order_id`
- Local order transitions to SUBMITTED → OPEN/FILLED
- Order-watch WebSocket receives order update

#### Step 10: Verify Exchange-Native SL/TP Mounted

**Verify** (via log):
- After ENTRY fill, `_protect_filled_entry` → `_mount_protection_orders` is called
- SL order: `place_order` with `order_type=stop_market`, `reduce_only=True`, side=sell
- TP1 order: `place_order` with `order_type=limit`, `reduce_only=True`, side=sell, qty=0.005
- TP2 order: `place_order` with `order_type=limit`, `reduce_only=True`, side=sell, qty=0.005
- All three orders have exchange_order_ids assigned
- Intent status: PROTECTING → COMPLETED

#### Step 11: Verify Order-Watch Updates

**Verify** (via log):
- WebSocket `watch_orders` receives updates for all 3 orders (ENTRY + SL + TP1/TP2)
- Dedup logic (G-002) is active — no duplicate processing
- `update_order_from_exchange` transitions match exchange state

#### Step 12: Trigger or Wait for Exit Fill

Two options:

**Option A — Wait for natural fill** (may take hours/days depending on market):
- SL or TP will trigger when ETH price moves to the level
- Proceed to Step 13 when fill occurs

**Option B — Manual testnet position close** (faster, controlled):
- Use Binance testnet UI or API to manually close the 0.01 ETH position at market
- This will trigger the SL/TP order fills via WebSocket
- Proceed to Step 13 immediately

**Recommended**: Option B for controlled timeline. Owner should decide.

#### Step 13: Verify PositionProjection and Daily Stats

**Verify PositionProjection** (via `GET /api/runtime/positions`):
- Position `pos_{signal_id}` exists
- `is_closed=true` after exit fill
- `realized_pnl` is computed
- `current_qty=0` or near-zero

**Verify Daily Stats** (query PG):
```sql
SELECT * FROM daily_risk_stats_aggregates
WHERE scope_key = 'runtime:default' AND stats_date = CURRENT_DATE;
```
- `trade_count >= 1`
- `realized_pnl` matches the PnL from the test trade

#### Step 14: Verify Reconciliation

Wait for next periodic reconciliation cycle (300s interval) or trigger manually.

**Verify** (via log):
- `Periodic reconciliation mismatches: symbol=ETH/USDT:USDT` — check `severe=0`
- No new `DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE` for the test order
- All test orders (ENTRY + SL/TP) are found on exchange or marked as closed/filled

#### Step 15: Re-enable GKS

```bash
# Temporarily set RUNTIME_CONTROL_API_ENABLED=true for this step
curl -s -X POST http://localhost:8000/api/runtime/control/global-kill-switch \
  -H "Content-Type: application/json" \
  -d '{"active": true, "reason": "001D-1 complete - restore kill switch", "updated_by": "owner"}'
```

**Verify**: Response shows `active=true`. Set `RUNTIME_CONTROL_API_ENABLED=false`.

#### Step 16: Stop Runtime

```bash
kill <PID>
```

#### Step 17: Verify Audit Trail

After runtime stops, query PG:

```sql
-- ExecutionIntents
SELECT * FROM execution_intents WHERE signal_id LIKE 'sig_%' ORDER BY created_at DESC LIMIT 5;

-- Daily risk stats
SELECT * FROM daily_risk_stats_events WHERE position_id LIKE 'pos_sig_%' ORDER BY created_at DESC LIMIT 5;

-- Orders
SELECT id, role, status, exchange_order_id, filled_qty, signal_id
FROM orders WHERE signal_id LIKE 'sig_%' ORDER BY created_at DESC LIMIT 10;
```

---

## 5. Stop Conditions

Any of the following requires **immediate runtime kill** and Owner report:

| # | Condition | Action |
|---|-----------|--------|
| S-1 | EXCHANGE_TESTNET=false detected in log or env | KILL runtime, report |
| S-2 | GKS active=false without explicit Owner approval | KILL runtime, report |
| S-3 | Startup guard armed without explicit Owner approval | KILL runtime, report |
| S-4 | Any order on mainnet / non-testnet exchange | KILL runtime, report |
| S-5 | Any order for symbol other than ETH/USDT:USDT | KILL runtime, report |
| S-6 | Order amount > 0.01 ETH (unauthorized size) | KILL runtime, report |
| S-7 | No SL mounted after ENTRY fill | KILL runtime, report (unprotected position) |
| S-8 | ProtectionHealth CRITICAL | KILL runtime, report |
| S-9 | Reconciliation severe_count > 0 | KILL runtime, report |
| S-10 | Feishu alert fan-out (external alerts firing) | KILL runtime, report |
| S-11 | Any exchange mutation outside planned Steps 6/9/10 | KILL runtime, report |
| S-12 | Live key / live profile detected | KILL runtime, report |
| S-13 | CapitalProtection denies with unexpected reason | KILL runtime, report |
| S-14 | 3+ consecutive unexpected order submissions | KILL runtime, report |

---

## 6. Success Criteria

001D-1 is **PASS** if ALL of the following are confirmed:

| # | Criterion | Evidence |
|---|-----------|----------|
| SC-1 | Startup guard blocked path works | ExecutionIntent with `blocked_reason=STARTUP_TRADING_GUARD_BLOCK_REASON` |
| SC-2 | GKS blocked path works | ExecutionIntent with `blocked_reason=KILL_SWITCH` |
| SC-3 | CapitalProtection allow trace emitted | Trace event with `decision=allow` and all check results |
| SC-4 | Testnet ENTRY submitted | Exchange order ID returned, local order SUBMITTED/OPEN |
| SC-5 | Exchange-native SL mounted | `place_order(stop_market, reduce_only=True)` with exchange_order_id |
| SC-6 | Exchange-native TP mounted | `place_order(limit, reduce_only=True)` x2 with exchange_order_ids |
| SC-7 | Order-watch receives updates | WebSocket callback processes ENTRY + SL/TP updates |
| SC-8 | PositionProjection updates | Position record with `is_closed=true` and `realized_pnl` set |
| SC-9 | Daily stats updated | `daily_risk_stats_aggregates.trade_count >= 1` |
| SC-10 | No unprotected position | At all times, if ENTRY is filled, SL is mounted |
| SC-11 | Reconciliation clean | `severe=0` in periodic reconciliation |
| SC-12 | Full audit trail | ExecutionIntent, trace events, order records all queryable |
| SC-13 | Zero stop conditions triggered | None of S-1 through S-14 occurred |

---

## 7. Rollback / Cleanup

### Immediate post-test cleanup

1. **GKS re-enabled**: Already done in Step 15 (`active=true`)
2. **Runtime stopped**: Already done in Step 16
3. **Check for residual testnet open orders**:
   ```bash
   # Via Binance testnet API or exchange gateway
   # Cancel any remaining SL/TP orders that were not filled
   ```
4. **Check for residual testnet positions**:
   ```bash
   # If position still open on testnet, manually close via:
   # - Binance testnet UI
   # - Or exchange gateway: place_order(symbol, "market", "sell", 0.01, reduce_only=True)
   ```

### What to do if testnet position remains

- **DO NOT** auto-close via production code (would require restarting runtime)
- Manually close via Binance testnet web UI
- Record the close in the findings log

### What NOT to do

- Do not clean up PG test data (orders, positions, intents, daily stats) — these serve as audit trail
- Do not auto-clean any live data (there should be none)
- Do not reset GKS to active=false after test

---

## 8. Required Fixes Before Execution

### Must-fix: None

All conditions are met for execution.

### Recommended: Synthetic Signal Injection Mechanism

The codebase has **no API endpoint** for injecting a synthetic signal into the live execution pipeline. The `ExecutionOrchestrator.execute_signal()` is an internal method with no HTTP exposure.

**Options**:

| Option | Description | Risk | Effort |
|--------|-------------|------|--------|
| A. Test script | One-shot async script that imports `src.main._execution_orchestrator` and calls `execute_signal()` directly | Low — script runs in same process, touches no strategy code | Small |
| B. Temporary test endpoint | Add `POST /api/runtime/test/execute-signal` gated behind `RUNTIME_CONTROL_API_ENABLED=true` + `EXCHANGE_TESTNET=true` | Low — controlled exposure, removed after test | Small |
| C. Wait for natural signal | Let Pinbar strategy fire naturally on ETH/USDT:USDT 1h | None — no code change | Unpredictable timing (hours to days) |

**Recommendation**: Option B. Add a temporary test endpoint that is explicitly scoped for 001D-1. The endpoint should:
- Accept `SignalResult`-compatible JSON in request body
- Validate `EXCHANGE_TESTNET=true` at runtime (reject if false)
- Validate `RUNTIME_CONTROL_API_ENABLED=true` (already gated by middleware)
- Call `_execution_orchestrator.execute_signal(signal, strategy)` directly
- Return ExecutionIntent status

This does NOT modify strategy logic, Direction A, or StrategySignalV2 execution. It bypasses the strategy engine entirely.

### Nice-to-have: Fix reconciliation FK bug

The `report_id` UNIQUE constraint + `session.begin()` transaction pattern is correct in code but produces FK violations under specific conditions (likely duplicate `report_id` from concurrent cycles). Non-blocking for 001D-1 but should be tracked for a future fix task.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Testnet order fills at unexpected price | Medium | Low (testnet only, min size) | MARKET order, no slippage concern on testnet |
| SL/TP mount fails on testnet | Low | Medium (unprotected position) | Stop condition S-7, manual close if needed |
| Reconciliation FK bug recurs | Medium | Low (log only, no crash) | Caught by best-effort handler |
| Feishu alert fires despite disabled flag | Very Low | Low (noise only) | PROTECTION_HEALTH_EXTERNAL_ALERTS_ENABLED=false |
| Stale local SL rows interfere with test | Very Low | None (report_only, no active positions) | No mitigation needed |
| Testnet API rate limit hit | Low | Low (retry/delay) | Single cycle, minimal API calls |

---

## 10. Next Tasks (post-001D-1)

| Task | Description | Blocked by |
|------|-------------|------------|
| 001D-2 | Fix reconciliation read model FK persistence bug | 001D-1 PASS |
| 001D-3 | Clean stale local PG orders (821 SL rows) | 001D-2 |
| 001D-4 | Multi-cycle testnet stress test (3-5 cycles) | 001D-1 PASS |
| 001D-5 | Protection health alert integration test | 001D-1 PASS |
