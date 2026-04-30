# ADR-0006: Runtime Periodic Reconciliation Report-only Loop

**Status:** Accepted  
**Date:** 2026-04-30  
**Scope:** LS-003b — periodic runtime observation of reconciliation read model  

---

## 1. Context

LS-003a established a read-only reconciliation read model (`build_read_model`) that can discover local/exchange order mismatches, position mismatches, and protection coverage gaps for a single symbol. However, this model is only callable on demand. For live-safe runtime credibility, the system needs to continuously observe whether its internal state remains consistent with the exchange during normal operation, not just at startup.

Periodic observation must remain report-only at this stage. Automatically acting on mismatches — blocking symbols, creating recovery tasks, canceling orders, or repairing protection coverage — carries false-positive risk that outweighs the benefit before the system has proven stable under live conditions.

## 2. Decision

LS-003b wires the LS-003a read model into the main runtime as a periodic background task.

Changes:

- `src/application/periodic_reconciliation.py` — new module containing `run_periodic_reconciliation()`, a standalone async function implementing the periodic loop.
- `src/main.py` — Phase 7.5 instantiation of `ReconciliationService`, task creation via `_start_periodic_reconciliation_task()`, and three-site shutdown cancellation via `_cancel_periodic_reconciliation_task()`.
- `tests/unit/test_ls003b_periodic_reconciliation.py` — focused tests for loop lifecycle, shutdown, failure isolation, and report-only behavior.

Defaults: startup delay 30 seconds, interval 300 seconds, active symbols from `symbols` list (same as order-watch).

## 3. Runtime Semantics

### 3.1 Periodic loop

`run_periodic_reconciliation()` is an observation-only background task. It:

- Calls `ReconciliationService.build_read_model(symbol)` once per symbol per cycle.
- Logs structured output (info for consistent, warning for mismatches).
- Does not hold trading control authority.
- Does not modify orders, positions, protection orders, or risk state.

### 3.2 Startup delay

The loop sleeps 30 seconds before its first reconciliation cycle. This avoids overlapping with startup reconciliation (Phase 4.3), circuit breaker rebuild (Phase 4.4), and early runtime initialization. The delay does not block the main runtime; the task runs independently via `asyncio.create_task`.

### 3.3 Interval

Default 300 seconds (5 minutes). Stored as `RECONCILIATION_INTERVAL_SECONDS` constant in `periodic_reconciliation.py`. Not configurable via runtime profile. Configuration化 is deferred to a future task if needed.

### 3.4 Active symbols

Reuses the same `symbols` list computed in Phase 6 of `main.py` — currently `[primary_symbol]`. Deduplicated via `dict.fromkeys()`. No universe manager, no multi-asset abstraction.

### 3.5 Shutdown responsiveness

The interval wait uses `asyncio.wait_for(shutdown_event.wait(), timeout=...)` rather than `asyncio.sleep()`. When `_shutdown_event` is set, the loop exits immediately without waiting for the full interval to elapse. The task is cancelled and awaited during `graceful_shutdown()`, post-wait cleanup, and the `finally` block (three redundant sites, all idempotent).

## 4. Failure Policy

| Scenario | Handling |
|----------|---------|
| `build_read_model()` raises for one symbol | `try/except` catches, logs error with `exc_info=True`, continues to next symbol |
| `build_read_model()` returns mismatches | Logs warning summary + per-mismatch detail lines; no action taken |
| `build_read_model()` returns consistent | Logs info; no further action |
| Loop function itself crashes | Task terminates; logged by wrapper `_run_periodic_reconciliation_task`; runtime continues |
| Shutdown during fetch/cancel | `CancelledError` re-raised (not swallowed); normal task cancellation |
| `ReconciliationService` instantiation fails | Phase 7.5 catches exception, logs error, sets `_periodic_reconciliation_task = None`; runtime continues |

All failures are isolated. No failure path triggers block, recovery, auto-fix, or any trading behavior change.

## 5. Report-only Boundary

LS-003b explicitly does not:

- Block any symbol on mismatch.
- Create recovery tasks.
- Auto-fix protection order coverage.
- Cancel orphan exchange orders.
- Place protection orders.
- Update local order lifecycle state.
- Update position projections.
- Write to DB, PG, or SQLite.
- Write JSONL.
- Emit Decision Trace events.
- Send P0 alert notifications.
- Update frontend.

Mismatch severity levels in LS-003b are observation metadata only. They are not automated execution triggers. Any transition from report-only into a control path (blocking, recovery, repair) requires a separate LS-003c task card and re-review.

## 6. Current Scope

LS-003b solves:

- Making the LS-003a read model available as a continuous runtime observation.
- Providing structured reconciliation summary logs during normal operation.
- Ensuring the periodic task lifecycle is properly managed (creation, storage, shutdown cancellation, no fire-and-forget).
- Maintaining the invariant that runtime trading behavior is unchanged.

## 7. Non-goals

LS-003b explicitly does not:

- Block symbols on confirmed severe mismatch.
- Create recovery tasks.
- Repair protection orders automatically.
- Cancel orphan exchange orders.
- Persist reconciliation reports to a repository.
- Display reconciliation results in a frontend.
- Extend the Decision Trace schema.
- Modify runtime profiles, strategy logic, risk rules, backtester, or research.
- Introduce Regime, Portfolio, Multi-strategy, or Data Feature abstractions.
- Fix the unrelated `update_snapshot_loop()` fire-and-forget pattern in `main.py`.

## 8. Safety Boundaries

- Periodic reconciliation is observability, not control.
- This task does not alter trading decisions, order placement, protection order mounting, or risk rejection conditions.
- It does not alter order-watch behavior or startup reconciliation behavior.
- The periodic task is stored in a module-level variable, cancelled during shutdown, and awaited — it cannot become a fire-and-forget runtime resource leak.
- AST static analysis of `run_periodic_reconciliation()` confirms it makes exactly one `await` call per symbol cycle: `build_read_model()`. No other side-effecting calls exist.

## 9. Consequences

### Positive

- Reconciliation capability extends from LS-003a's on-demand model to continuous runtime observation.
- The system can now surface order, position, and protection coverage inconsistencies during live operation without altering behavior.
- Task lifecycle follows the established `cancel + await` pattern (same as order-watch tasks), avoiding fire-and-forget risk.
- Provides the observation foundation for future LS-003c control-path decisions.
- Provides the data foundation for a future Owner Console reconciliation display.

### Tradeoffs

- Output is log-only; no persistence means reconciliation history cannot be queried after restart.
- Consistent-state cycles produce periodic info logs (approximately 12/hour per symbol).
- False-positive mismatches produce warnings but no automated handling; owner awareness depends on log monitoring.
- No frontend visualization; reconciliation status is only visible in logs.
- No block or recovery means discovered issues require external handling.
- `main.py` integration lacks heavy runtime startup tests; correctness depends on focused unit tests of `periodic_reconciliation.py`.

## 10. Future Extensions

The following are explicitly deferred and require separate task cards:

| Item | Task | Prerequisite |
|------|------|-------------|
| Confirmed severe mismatch triggers symbol block | LS-003c | This ADR |
| Recovery task creation from reconciliation mismatch | LS-003c | This ADR |
| Grace period / consecutive mismatch confirmation | LS-003c | Design review |
| Reconciliation report persistence | LS-003d | Schema design |
| Frontend read-only reconciliation display | Owner Console | Backend API |
| Decision Trace records reconciliation mismatch | Trace expansion | Owner approval |
| P0 notifier alert on first SEVERE mismatch | Notification integration | Owner approval |
| Interval configuration via runtime profile | Config task | Owner approval |
| Unified runtime background task management | Infra cleanup | Separate scope |

## 11. Open Questions for Owner

1. **Blocking threshold:** In LS-003c, should a single grace-confirmed SEVERE mismatch trigger symbol block, or should consecutive multi-round mismatches be required first?
2. **Eligible mismatch types:** Which `mismatch_type` values qualify for automatic blocking in LS-003c? (`local_position_missing_on_exchange`? `missing_sl_protection`? All SEVERE?)
3. **Recovery task creation:** When should reconciliation be permitted to create recovery tasks — immediately in LS-003c, or only after manual operator confirmation?
4. **Report persistence:** Is log-only sufficient for the foreseeable future, or should reconciliation results be persisted to a dedicated table?
5. **Owner Console visibility:** Should reconciliation mismatch summaries appear in a future frontend dashboard?
6. **Decision Trace:** Should reconciliation observations be recorded as trace events for post-mortem analysis?
7. **Interval configuration:** Should the 300-second interval become configurable via runtime profile, or remain a compile-time constant?
8. **Background task unification:** Should `update_snapshot_loop()` and other fire-and-forget tasks be brought into the same managed lifecycle pattern as order-watch and periodic reconciliation?
