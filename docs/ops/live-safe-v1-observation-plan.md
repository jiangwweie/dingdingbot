> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical roadmap, readiness, rehearsal, safety, or phase artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
>
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> * `docs/canon/TECH_DEBT_BASELINE.md`
> * `docs/canon/DOCUMENT_GOVERNANCE.md`

# Live-safe v1 Observation Plan

**Date:** 2026-05-06  
**Status:** Active  
**Purpose:** Define the observation period for Live-safe v1 after foundation governance is complete. The goal is to validate runtime behavior stability, not to expand functionality.

---

## 1. Freeze Scope

The following capabilities are frozen during the observation period. No active expansion unless a clear bug is discovered.

| Milestone | ADR | Status |
|-----------|-----|--------|
| Decision Trace Backbone v0 | ADR-0002 | Frozen |
| Order Watch Runtime Closure | — | Frozen |
| Daily Risk Limits Runtime Closure v0 | ADR-0004 | Frozen |
| Reconciliation Read Model v0 | ADR-0005 | Frozen |
| Periodic Reconciliation Report-only Loop | ADR-0006 | Frozen |
| Reconciliation Read Model Persistence | ADR-0007 | Frozen |
| RTG-001 Manage update_snapshot_loop lifecycle | — | Frozen |
| RTG-002 Manage ws_task / api_task lifecycle | — | Frozen |
| DW-001 Remove shadowed watch_orders definition | — | Frozen |
| TM-001 CapitalProtection fail-open hardening | — | Frozen |
| TM-002 Exit projection observability active test | — | Frozen |
| TM-003 Order update parse observability active test | — | Frozen |

Bug fixes are allowed. Feature expansions are not.

---

## 2. Observation Goals

During the observation period, verify the following:

- **Order-watch task** runs stably without unexpected exits.
- **Order updates** enter the local `OrderLifecycleService` lifecycle correctly.
- **Periodic reconciliation** executes on schedule without persistent fetch failures.
- **Reconciliation mismatches** are genuine, not false positives.
- **Reconciliation persistence** writes succeed without blocking the loop or affecting trading.
- **Daily stats** update correctly via projected exit delta and full position close.
- **Snapshot update loop** runs without persistent failures.
- **Shutdown** is clean: no hanging tasks, no resource leaks.
- **Trace writes** remain best-effort and never affect trading decisions.
- **CapitalProtection fail-closed hardening** behaves as expected: precision / price reasonability internal dependency exceptions reject orders and emit deny traces.
- **Exit projection no-op paths** remain observable when local position state is missing or an exit fill cannot be projected.
- **Order update parse failures** remain observable and do not stop order-watch processing of subsequent valid updates.
- **Logs** are sufficient for the owner to understand runtime state without code access.

---

## 3. Runtime Logs to Watch

| Log Pattern | Level | What It Indicates |
|-------------|-------|-------------------|
| `Order watch started` / `stopped` | INFO | Order-watch task lifecycle |
| `Order watch task failed` | ERROR | Order-watch unexpected exit |
| `Order update callback error` | ERROR | Callback exception in order processing |
| `Periodic reconciliation consistent` | INFO | No mismatch detected |
| `Periodic reconciliation mismatches` | WARNING | Mismatch detected — check detail lines |
| `Periodic reconciliation mismatch detail` | WARNING | Per-mismatch severity, type, reason |
| `Periodic reconciliation read model failed` | ERROR | Fetch or comparison failure |
| `Daily risk limit reject` | WARNING | Daily loss or trade count limit triggered |
| `Asset snapshot update failed` | ERROR | Snapshot loop exception |
| `WS task shutdown error` / `API task shutdown error` | WARNING | Non-CancelledError during task cleanup |
| `Trace write failed` | ERROR | JSONL write failure (non-blocking) |
| `QUANTITY_PRECISION_CHECK_ERROR` | WARNING / trace | Quantity precision dependency exception rejected by CapitalProtection |
| `PRICE_REASONABILITY_CHECK_ERROR` | WARNING / trace | Price reasonability dependency exception rejected by CapitalProtection |
| `decision=deny` with TM-001 reason code | trace | Expected trace outcome for TM-001 fail-closed rejects |
| `Exit projection skipped` | WARNING | Exit fill could not update local position projection or daily stats |
| `处理订单更新失败` | ERROR | Order update parse failed; later valid updates should continue processing |

---

## 4. Known Acceptable Limitations

These limitations are accepted during the observation period:

- Daily stats are in-memory; runtime restart resets daily loss and trade count to zero.
- Reconciliation is report-only; does not block, recover, or auto-fix.
- Protection coverage is `symbol_role_v0` (symbol-level, not position-chain-level).
- Reconciliation read model history has PG persistence (best-effort, non-blocking); still no REST API / frontend display; still no LS-003c control path.
- No frontend display of reconciliation or risk state.
- `get_account_snapshot()` is a synchronous call; may block the event loop under adverse conditions.
- Normal `fetch_ticker_price()` returning `None` or `0` still keeps the existing skip-check semantics in price reasonability validation; TM-001 did not change this path.
- Exit projection missing-position or invalid-fill paths are observable no-ops; they do not reconstruct PnL from account history.
- Order update parse failures are observable no-ops; they do not trigger recovery, auto-fix, or symbol blocking.
- No automatic repair of any kind.
- No LS-003c control path (mismatch → block symbol).

---

## 5. Stop / Escalation Conditions

If any of the following occur, pause further expansion and prioritize investigation or fix:

| Condition | Severity | Action |
|-----------|----------|--------|
| Order-watch task exits repeatedly | **P0** | Investigate root cause before any other work |
| Periodic reconciliation fetch failures are persistent | **P1** | Check exchange connectivity and gateway state |
| High-frequency SEVERE mismatches (e.g., missing SL) | **P1** | Verify local/exchange state consistency manually |
| Snapshot update loop fails persistently | **P1** | Check gateway REST connectivity |
| Shutdown leaves hanging tasks | **P1** | Audit cancel+await paths |
| Trace write failure affects runtime | **P0** | Trace is designed to be non-blocking; if it blocks, this is a bug |
| Daily stats double-count or miss counts | **P1** | Verify exit delta and full-close logic |
| TM-001 reason code appears repeatedly or rejects expected normal orders | **P1** | Investigate dependency health and false-reject risk before expanding scope |
| Exit projection skipped appears repeatedly for real exit fills | **P1** | Investigate local position lifecycle consistency before trusting daily stats |
| Order update parse failures repeat for exchange payloads | **P1** | Inspect parser compatibility and payload shape; do not auto-recover without separate approval |
| Local/exchange position stays inconsistent across multiple reconciliation cycles | **P0** | Manual investigation required |

---

## 6. Candidate Follow-up Triggers

### LS-002b: Daily Stats Persistence

**Trigger when:**
- Runtime requires frequent restarts (deploy, upgrade, crash recovery).
- Owner cannot accept the daily risk window resetting after restart.
- Observation shows daily stats continuity is operationally important.

### Reconciliation Report Persistence — Completed (LS-003d)

Superseded by LS-003d. Periodic reconciliation read model results are now persisted to PG. Best-effort, non-blocking. ADR-0007.

### LS-003c: Confirmed Severe Mismatch Handling

**Trigger when:**
- Reconciliation false-positive rate is proven low enough through observation data.
- Mismatch types and severity distribution are stable and well-understood.
- Owner explicitly accepts the transition from report-only to control path.
- Block conditions and recovery procedures are defined and documented.
- An ADR is written and approved.

**Do not trigger LS-003c based on a single mismatch observation.**

### Owner Console Read-only Display

**Trigger when:**
- Backend has stable read model or report data available.
- Owner needs to understand system state without reading logs.
- The scope is explicitly read-only: no runtime control, no parameter modification.

### get_account_snapshot Async Audit

**Trigger when:**
- Snapshot update loop shows latency spikes.
- Event loop responsiveness is a concern.
- Only inspect + plan; no implementation commitment.

---

## 7. Non-goals During Observation

The following are explicitly out of scope during the observation period:

- Block symbol on mismatch.
- Recovery task auto-creation.
- Orphan order auto-cancel.
- Protection order auto-remount.
- Expanding TM-001 into broader risk-rule changes.
- Frontend runtime control.
- Multi-strategy support.
- Multi-asset universe expansion.
- Portfolio engine.
- Regime detection layer.
- Complete account risk state machine.

---

## 8. Recommended Observation Period

Run the system in sim / paper / testnet mode for a sufficient period to accumulate:

- Multiple startup and shutdown cycles.
- Multiple order update sequences.
- Multiple reconciliation loop cycles (both consistent and mismatch states).
- At least one daily boundary crossing (UTC midnight) to verify daily stats reset.
- At least one graceful shutdown to verify task cleanup.

Do not commit to a specific duration. Proceed to the next phase only when observation data is sufficient and no escalation conditions are active.

---

## 9. Owner Questions

1. Should Live-safe v1 be formally frozen at this point?
2. Should the next phase focus on strategy module stabilization instead of further live-safe expansion?
3. Should LS-002b (daily stats persistence) be prioritized before other candidates?
4. ~~Is reconciliation report persistence needed, or is log-only sufficient for the foreseeable future?~~ **Resolved: LS-003d completed.**
5. Is an Owner Console read-only display needed, or are logs sufficient?
6. Under what conditions would LS-003c (mismatch → block) become worth the risk?
