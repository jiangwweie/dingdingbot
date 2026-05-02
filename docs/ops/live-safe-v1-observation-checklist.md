# Live-safe v1 Observation Checklist — Pass 1

**Date:** 2026-05-02
**Observer:** Claude Code (OBS-001)
**Mode:** Binance testnet, `sim1_eth_runtime` profile
**Runtime duration:** ~5 minutes (20:48:51 – 20:53:31 CST)

---

## 1. Startup Evidence

| Check | Result | Timestamp | Detail |
|-------|--------|-----------|--------|
| Runtime process starts | PASS | 20:48:51 | PID 88422, `python3 src/main.py` |
| Startup reconciliation completes | PASS | 20:48:51 | 0 candidates, 0 reconciled, 0 failed, 172ms |
| Signal pipeline initialized | PASS | 20:48:51 | profile=sim1_eth_runtime, hash=359c8ca01649909b |
| Historical warmup | PASS | 20:48:51 | 2/2 symbol/timeframe pairs loaded, 200 bars replayed |
| Asset polling starts | PASS | 20:48:51 | interval=60s |
| Snapshot update task starts | PASS | 20:48:51 | polling_interval=60s |
| Periodic reconciliation task starts | PASS | 20:48:51 | symbols=['ETH/USDT:USDT'], startup_delay=30s, interval=300s |
| Order watch task starts | PASS | 20:48:51 | ETH/USDT:USDT, 1 task active |
| **SYSTEM READY - Monitoring started** | **PASS** | **20:48:51** | Phase 8 complete |
| REST API server ready | PASS | 20:48:52 | http://localhost:8000 |
| Order WS listener starts | PASS | 20:48:53 | WebSocket 订单监听已启动：ETH/USDT:USDT |
| K-line WS subscription | PASS (with reconnect) | 20:48:54 | Initial subscribe OK; 2 connection timeouts, auto-reconnected on attempt 3 |

### Startup log snippet (SYSTEM READY)

```
[2026-05-02 20:48:51] [INFO] Order watch task started: ETH/USDT:USDT
[2026-05-02 20:48:51] [INFO] Order watch tasks active: 1
[2026-05-02 20:48:51] [INFO] ============================================================
[2026-05-02 20:48:51] [INFO] SYSTEM READY - Monitoring started
[2026-05-02 20:48:51] [INFO] ============================================================
```

---

## 2. Order-Watch Evidence

| Check | Result | Detail |
|-------|--------|--------|
| Order watch task starts | PASS | `Order watch task started: ETH/USDT:USDT` |
| Order WS listener connects | PASS | `WebSocket 订单监听已启动：ETH/USDT:USDT` |
| Order watch task exits unexpectedly | NOT OBSERVED | No `Order watch task failed` in logs |
| Order update callback error | NOT OBSERVED | No `处理订单更新失败` in logs |

**Note:** No order updates were received during this observation window. This is expected — no new orders were placed, and the testnet had no active positions.

---

## 3. Periodic Reconciliation Evidence

| Check | Result | Timestamp | Detail |
|-------|--------|-----------|--------|
| First reconciliation executes | PASS | 20:49:23 | ~30s after startup (matches startup_delay=30s) |
| Reconciliation result | MISMATCH | 20:49:23 | total=2971, severe=0, warning=2971 |
| Mismatch type distribution | OBSERVED | 20:49:23 | 100% `local_order_missing_on_exchange` |
| SEVERE mismatches | NONE | 20:49:23 | severe=0 |
| Reconciliation read model failure | NOT OBSERVED | — | No `Periodic reconciliation read model failed` |
| Second reconciliation cycle | NOT OBSERVED | — | Runtime shut down before 300s interval elapsed |

### Mismatch analysis

- **2971 local_order_missing_on_exchange**: Local DB has 2971 orders in "open" status that no longer exist on the exchange. These are historical testnet orders that were filled or cancelled on the exchange but whose local status was never updated.
- **Severity**: All WARNING (no SEVERE). `local_order_missing_on_exchange` is classified as WARNING per ADR-0005.
- **Assessment**: This is a known data hygiene issue from testnet history, not a runtime bug. The reconciliation correctly detects and reports these mismatches. No P0/P1 condition.

### Reconciliation log snippet

```
[2026-05-02 20:49:23] [WARNING] Periodic reconciliation mismatches: symbol=ETH/USDT:USDT, checked_at=1777726162543, total=2971, severe=0, warning=2971
[2026-05-02 20:49:23] [WARNING] Periodic reconciliation mismatch detail: symbol=ETH/USDT:USDT, severity=WARNING, type=local_order_missing_on_exchange, reason=Local open order was not found in exchange open orders.
```

---

## 4. Snapshot Update Loop Evidence

| Check | Result | Detail |
|-------|--------|--------|
| Snapshot update loop runs | PASS | 6 updates in ~5 minutes (every 60s) |
| Snapshot update failures | NOT OBSERVED | No `Asset snapshot update failed` |
| Balance stable | PASS | 8283.92054968 USDT throughout |
| Positions | PASS | 0 positions throughout |

### Snapshot log snippet

```
[2026-05-02 20:48:51] [DEBUG] Asset snapshot updated: balance=8283.92054968, positions=0
[2026-05-02 20:49:53] [DEBUG] Asset snapshot updated: balance=8283.92054968, positions=0
[2026-05-02 20:50:53] [DEBUG] Asset snapshot updated: balance=8283.92054968, positions=0
[2026-05-02 20:51:54] [DEBUG] Asset snapshot updated: balance=8283.92054968, positions=0
[2026-05-02 20:52:55] [DEBUG] Asset snapshot updated: balance=8283.92054968, positions=0
```

---

## 5. Risk Trace Evidence

| Check | Result | Detail |
|-------|--------|--------|
| `logs/runtime/risk_decision.jsonl` exists | NOT CREATED | No risk decisions occurred during observation |
| Trace write failure | NOT OBSERVED | No `Trace write failed` in logs |

**Note:** No `pre_order_check` was called because no new orders were triggered. The trace file is created on first write; absence is expected when no risk decisions occur.

---

## 6. TM-001 Warning Patterns

| Pattern | Count | Assessment |
|---------|-------|------------|
| `QUANTITY_PRECISION_CHECK_ERROR` | 0 | Not triggered (no risk checks) |
| `PRICE_REASONABILITY_CHECK_ERROR` | 0 | Not triggered (no risk checks) |
| `Exit projection skipped` | 0 | Not triggered (no position exits) |
| `处理订单更新失败` | 0 | Not triggered (no order updates) |
| `Periodic reconciliation read model failed` | 0 | Not triggered |
| `Asset snapshot update failed` | 0 | Not triggered |
| `Order watch task failed` | 0 | Not triggered |
| shutdown task errors | 0 | Clean shutdown |

---

## 7. Shutdown Evidence

| Check | Result | Timestamp | Detail |
|-------|--------|-----------|--------|
| SIGTERM received | PASS | 20:53:31 | `kill PID` via stop.sh |
| Graceful shutdown initiated | PASS | 20:53:31 | `Graceful shutdown initiated...` |
| K-line WS cancelled | PASS | 20:53:31 | Both 1h and 4h subscriptions cancelled |
| Order WS cancelled | PASS | 20:53:31 | `WebSocket 订单监听被取消：ETH/USDT:USDT` |
| Exchange connections closed | PASS | 20:53:32 | `Exchange connections closed` |
| Config repositories closed | PASS | 20:53:32 | `ConfigEntryRepository closed`, `Config repositories closed` |
| Database engines closed | PASS | 20:53:32 | `Database engines closed` |
| **Application shutdown complete** | **PASS** | **20:53:32** | ~1s from SIGTERM to complete |
| Shutdown errors | NONE | — | No `shutdown error`, `CancelledError`, or `Traceback` |
| Hanging tasks | NONE | — | Process exited cleanly |

### Shutdown log snippet

```
[2026-05-02 20:53:31] [INFO] Graceful shutdown initiated...
[2026-05-02 20:53:31] [INFO] WebSocket subscription cancelled for ETH/USDT:USDT 1h
[2026-05-02 20:53:31] [INFO] WebSocket subscription cancelled for ETH/USDT:USDT 4h
[2026-05-02 20:53:31] [INFO] WebSocket 订单监听被取消：ETH/USDT:USDT
[2026-05-02 20:53:32] [INFO] Exchange connections closed
[2026-05-02 20:53:32] [INFO] ConfigEntryRepository closed
[2026-05-02 20:53:32] [INFO] Config repositories closed
[2026-05-02 20:53:32] [INFO] Exchange connections closed
[2026-05-02 20:53:32] [INFO] Shutdown complete
[2026-05-02 20:53:32] [INFO] Database engines closed
[2026-05-02 20:53:32] [INFO] Application shutdown complete
```

---

## 8. Observed Anomalies

### ANOM-001: K-line WebSocket connection timeout (non-blocking)

- **Time:** 20:49:04 – 20:49:15
- **Pattern:** `WebSocket error for ETH/USDT:USDT 1h/4h: Connection timeout`
- **Count:** 4 errors (2 per timeframe)
- **Recovery:** Auto-reconnect succeeded on attempt 3
- **Impact:** No K-line data received during ~15s reconnect window; no trading impact (no active positions)
- **Classification:** Known testnet connectivity issue; not a runtime bug
- **Severity:** P2 (transient, auto-recovered)

### ANOM-002: Binance testnet API key permission check skipped

- **Time:** 20:48:51
- **Pattern:** `Failed to check Binance API key restrictions on testnet; skipping withdraw-permission enforcement`
- **Reason:** `binance does not have a testnet/sandbox URL for sapi endpoints`
- **Impact:** Withdraw-permission enforcement skipped on testnet (by design)
- **Classification:** Known testnet limitation; expected behavior
- **Severity:** Informational

### ANOM-003: 2971 local_order_missing_on_exchange mismatches

- **Time:** 20:49:23
- **Pattern:** `Periodic reconciliation mismatches: total=2971, severe=0, warning=2971`
- **Root cause:** Local DB has 2971 orders in "open" status that no longer exist on the exchange (historical testnet orders)
- **Impact:** Log noise (2971 WARNING lines); no SEVERE mismatches; no runtime impact
- **Classification:** Data hygiene issue; reconciliation correctly detects and reports
- **Severity:** P2 (log noise, not a runtime bug; cleanup is a separate concern)

---

## 9. P0/P1 Escalation Check

Per observation plan Section 5, check escalation conditions:

| Condition | Observed? | Action |
|-----------|-----------|--------|
| Order-watch task exits repeatedly | NO | — |
| Periodic reconciliation fetch failures persistent | NO | — |
| High-frequency SEVERE mismatches | NO | severe=0 |
| Snapshot update loop fails persistently | NO | — |
| Shutdown leaves hanging tasks | NO | — |
| Trace write failure affects runtime | NO | — |
| Daily stats double-count or miss counts | NOT OBSERVED | No daily boundary crossing |
| Local/exchange position stays inconsistent across multiple cycles | NOT OBSERVED | Only 1 reconciliation cycle |

**No P0/P1 conditions observed.**

---

## 10. Observation Gaps

The following items could not be verified in this short observation pass:

- **Order update callback**: No order updates were received (no active positions, no new orders).
- **Risk decision trace**: No `pre_order_check` was called; `risk_decision.jsonl` was not created.
- **Daily boundary crossing**: Runtime did not cross UTC midnight; daily stats reset not verified.
- **Second reconciliation cycle**: Runtime shut down before 300s interval; only 1 cycle observed.
- **Signal generation and order flow**: No Pinbar signals generated during observation window.

**Recommendation:** A longer observation pass (>= 30 minutes) or a pass that crosses a UTC midnight boundary would provide more complete evidence. Alternatively, a second pass after cleaning the 2971 stale open orders would produce cleaner reconciliation logs.

---

## 11. Files and Paths

| Item | Path | Exists? |
|------|------|---------|
| Main log | `logs/dingdingbot.log` | YES (3110 lines) |
| Backend capture | `logs/backend.log` | YES |
| PID file | `logs/backend.pid` | YES (stale after shutdown) |
| Risk trace | `logs/runtime/risk_decision.jsonl` | NO (not created — no risk decisions) |
| Rotated log | `logs/dingdingbot.log.2026-04-30.log` | YES (from previous run) |

---

## 12. Commands Used

```bash
# Start runtime
source venv/bin/activate
export PYTHONPATH="/Users/jiangwei/Documents/final:$PYTHONPATH"
nohup python3 src/main.py > logs/backend.log 2>&1 &
echo $! > logs/backend.pid

# Health check
curl -s http://localhost:8000/api/health

# Graceful shutdown
kill $(cat logs/backend.pid)

# Log searches
grep "SYSTEM READY" logs/dingdingbot.log
grep "Application shutdown complete" logs/dingdingbot.log
grep "Order watch" logs/dingdingbot.log
grep "Periodic reconciliation" logs/dingdingbot.log
grep "Asset snapshot" logs/dingdingbot.log
grep -E "QUANTITY_PRECISION_CHECK_ERROR|PRICE_REASONABILITY_CHECK_ERROR" logs/dingdingbot.log
grep -E "Exit projection skipped|处理订单更新失败" logs/dingdingbot.log
grep -E "Periodic reconciliation read model failed|shutdown error" logs/dingdingbot.log
```

---

## 13. Conclusion

Live-safe v1 Pass 1 completed successfully. All core runtime capabilities functioned correctly:

- Startup reached SYSTEM READY
- Order-watch task started and remained stable
- Periodic reconciliation executed and correctly detected 2971 WARNING mismatches (stale testnet data)
- Snapshot update loop ran stably at 60s intervals
- Graceful shutdown completed cleanly in ~1s with no hanging tasks or errors

No P0/P1 escalation conditions were observed. Three anomalies were noted (K-line WS timeout, testnet API key skip, stale order mismatches), all classified as P2 or informational.

The observation window was too short to verify order update callbacks, risk decision traces, daily boundary crossing, or multiple reconciliation cycles. A longer pass is recommended for more complete coverage.
