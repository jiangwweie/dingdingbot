# Live-safe v1 Checkpoint

**Date:** 2026-05-06  
**Purpose:** Summarize live-safe foundation progress, known limitations, non-goals, and candidate next tasks. This is a reference document for owner review and future Codex / Claude Code context — not a sprint plan or task breakdown.

---

## 1. Completed Milestones

### Decision Trace Backbone v0

- Established a minimal decision trace skeleton (`TraceEvent`, `TraceService`, `JsonlTraceSink`).
- Risk decisions from `CapitalProtection.pre_order_check` are written to `logs/runtime/risk_decision.jsonl`.
- Trace failure is non-blocking: `try/except` in `TraceService.emit` ensures trace errors never affect trading.
- Current scope is a single vertical slice (risk decision → JSONL); no broader trace expansion.
- ADR-0002 documents semantics, scope, and non-goals.

### LS-001 Order Watch Runtime Closure

- Main runtime starts isolated order-watch background tasks via `_start_order_watch_tasks()`.
- Exchange order updates enter the local `OrderLifecycleService` lifecycle in real time.
- Order-watch WebSocket state is fully isolated from K-line WebSocket state (`_order_ws_running` vs `_ws_running`).
- `api.py` does not start order-watch tasks — this is explicitly out of scope.
- ADR documents semantics, scope, and non-goals.

### LS-002 Daily Risk Limits Runtime Closure v0

- `CapitalProtectionManager` daily loss and daily trade count are now active in the runtime, not dead stats.
- Daily PnL is tracked via projected realized exit deltas from `PositionProjectionService.project_exit_fill()`.
- Trade count increments on full position close (not partial TP).
- UTC day boundary reset is applied at each relevant call site.
- v0 state is in-memory only: restart loses all daily stats. This is an accepted limitation.
- ADR-0004 documents semantics, scope, and non-goals.

### LS-003a Reconciliation Read Model v0

- Established a read-only reconciliation read model via `ReconciliationService.build_read_model(symbol)`.
- Compares local open orders against exchange open orders (ghost / orphan detection).
- Compares local active positions against exchange active positions (presence / qty).
- Checks protection order coverage at `symbol + order_role` granularity (`association_scope: symbol_role_v0`).
- Mismatch severity: SEVERE for position absence and missing SL; WARNING for qty differences and missing TP.
- Does not block, recover, auto-fix, write DB, or emit trace events.
- ADR-0005 documents semantics, scope, and non-goals.

### LS-003b Periodic Reconciliation Report-only Loop

- `ReconciliationService.build_read_model()` is now called periodically from the main runtime.
- Default startup delay: 30 seconds; default interval: 300 seconds.
- Active symbols are reused from the runtime config (currently single primary symbol).
- Consistent state logs info; mismatch state logs warning summary and per-item detail.
- Single-symbol failure is isolated; does not affect other symbols or runtime health.
- Task is stored in a module-level variable, cancelled during shutdown, and awaited — not fire-and-forget.
- ADR-0006 documents semantics, scope, and non-goals.

### RTG-001 Manage update_snapshot_loop Lifecycle

- `update_snapshot_loop` is no longer fire-and-forget; task handle is stored in `_snapshot_update_task`.
- Shutdown cancels and awaits the snapshot update task across all three shutdown paths.
- Ordinary exceptions are logged and the loop continues; `CancelledError` is explicitly re-raised.
- Interval waiting uses `asyncio.wait_for(shutdown_event.wait(), timeout=...)` for fast shutdown responsiveness.
- Normal snapshot update behavior is unchanged.
- Does not modify `ws_task`, `api_task`, order-watch, reconciliation, strategy, risk rule, runtime profile, trace schema, backtest, research, or frontend.

### RTG-002 Manage ws_task / api_task Lifecycle

- `ws_task` and `api_task` are no longer local-only variables; module-level handles `_ws_task` / `_api_task` are stored.
- Shutdown cancels and awaits both tasks across all three shutdown paths.
- Cancel helpers `_cancel_ws_task()` / `_cancel_api_task()` are idempotent: None-safe, done-safe, running cancel+await, non-CancelledError logged, handle cleared in finally.
- Removed the fragile `if 'api_task' in locals()` cleanup in the finally block.
- Does not modify `subscribe_ohlcv()` internal behavior, uvicorn/API server behavior, order-watch, reconciliation, snapshot update, strategy, risk rule, runtime profile, trace schema, backtest, research, or frontend.
- Does not introduce TaskManager or task registry.

### DW-001 Remove shadowed watch_orders Definition

- Removed the obsolete shadowed `watch_orders()` definition from `ExchangeGateway` (~78 lines of dead code).
- The active `watch_orders()` implementation (with `_order_ws_running`, dedicated `order_ws_exchange`, global callback, exception protection) is unchanged.
- `_handle_order_update()` is unchanged.
- Added AST regression test to ensure only one `watch_orders()` definition exists at source level.
- No runtime behavior change.

### TM-001 CapitalProtection Fail-open Hardening

- `CapitalProtectionManager.pre_order_check()` no longer silently allows orders when quantity precision validation raises an internal dependency exception.
- Quantity precision exception path now fails closed with `QUANTITY_PRECISION_CHECK_ERROR`.
- Price reasonability exception path now fails closed with `PRICE_REASONABILITY_CHECK_ERROR`.
- Existing Decision Trace behavior is preserved: fail-closed results naturally emit `decision=deny` through the current risk decision trace path.
- Normal passing paths, strategy logic, runtime profiles, backtester, research, frontend, exchange gateway, and Decision Trace schema are unchanged.

### LS-003d Reconciliation Read Model Persistence

- Periodic reconciliation read model results are now persisted to PG via dedicated `reconciliation_read_model_reports` + `reconciliation_read_model_mismatches` tables.
- Consistent reports, mismatch reports, and fetch failure reports are all saved.
- Persistence is best-effort: write failures are logged and never propagated into trading, loop continuation, protection, shutdown, or reconciliation itself.
- `repository=None` gracefully degrades to log-only (current behavior preserved).
- Uses dedicated read-only tables instead of startup reconciliation tables because startup tables carry action/resolution semantics.
- No `cycle_id` / `run_id`; report identity is `{checked_at_ms}:{symbol}`.
- No retention policy, no REST API, no frontend, no LS-003c control path.
- Alembic revision 008.
- ADR-0007 documents semantics, scope, and non-goals.

### Freeze Gate Active Tests: TM-002 / TM-003

- TM-002 verifies exit projection no-op paths before freeze: missing local position and invalid exit fill are observable warning paths, and they do not update LS-002 daily projected PnL or closed-trade count.
- TM-002 does not introduce account-level PnL reconstruction, fee/funding expansion, historical rebuild, or daily stats persistence.
- TM-003 verifies order update parse failures are observable and do not silently kill the order-watch loop; valid later updates in the same watch batch can still reach callbacks.
- TM-003 does not introduce recovery, auto-fix, orphan cancel, symbol block, LS-003c, or exchange simulation.

---

## 2. Current Live-safe Capability

Compared to pre-live-safe state:

- **Order runtime state is more可信**: order-watch ensures local lifecycle receives real-time exchange updates; startup reconciliation can advance stale orders at boot.
- **Daily limits are real**: `pre_order_check` now enforces daily loss and daily trade count limits using live projected PnL, not dead placeholder stats.
- **Reconciliation is observable**: the system now periodically compares local and exchange state and surfaces mismatches as structured logs — reconciliation is no longer a manual-only capability.
- **All main runtime background tasks have managed lifecycle**: snapshot update, OHLCV WebSocket, API server, order-watch, and periodic reconciliation all store task handles and support cancel+await during shutdown. No fire-and-forget tasks remain in the main runtime.
- **Order-watch implementation is clean**: no duplicate `watch_orders()` definition remains; the active implementation uses isolated WS state, global callback, and exception protection.
- **Shutdown semantics are consistent**: all three shutdown paths (graceful_shutdown, post-wait, finally) follow the same cancel+await pattern for managed tasks.
- **Decision traceability exists**: risk decisions are recorded to JSONL for post-mortem analysis.
- **CapitalProtection internal check exceptions fail closed**: quantity precision and price reasonability dependency exceptions reject the order instead of silently allowing it; these rejects are traceable as `decision=deny`.
- **Freeze Gate active tests passed**: TM-002 and TM-003 cover two high-risk silent-failure paths before observation entry without expanding runtime behavior.
- **Non-invasive and rollback-friendly**: all live-safe additions are optional and none change core trading logic.

---

## 3. Known Limitations

### Infrastructure gaps

- `api.py` does not start order-watch tasks (out of LS-001 scope).
- `_order_ws_running` is a shared flag across multiple watch tasks; acceptable for single-symbol runtime but fragile for multi-symbol.
- `get_account_snapshot()` is a synchronous call; if it blocks, it blocks the event loop. Known limitation.
- No unified runtime task manager exists. This is a deliberate scope choice, not a bug.

### Daily limits

- v0 state is in-memory: runtime restart resets daily loss and trade count to zero.
- Daily PnL is projected realized PnL, not complete account-level daily loss.
- Funding fees and full fee breakdown are not fully纳入 daily loss calculation.

### CapitalProtection parameter checks

- TM-001 only hardens internal exception paths for quantity precision and price reasonability checks.
- Normal `fetch_ticker_price()` returning `None` or `0` still keeps the existing skip-check semantics in price reasonability validation.
- Tightening the normal missing-ticker path into a reject/block behavior would be a separate owner decision and task card.

### Reconciliation

- LS-003a/b reconciliation is report-only: does not block, recover, or auto-fix.
- Protection coverage is `symbol_role_v0` — symbol-level, not position-chain-level.
- Reconciliation does not validate `reduce_only` flag on exchange-side orders.
- Reconciliation does not validate TP/SL price reasonableness.
- Reconciliation read model history has PG persistence (best-effort, non-blocking); still no REST API / frontend display; still no LS-003c control path.
- No grace period or consecutive-mismatch confirmation in LS-003b.
- `_parse_ccxt_order` maps all `reduce_only=True` orders to `OrderRole.TP1` (including SL); this only affects metadata display and does not trigger action.

### Other

- `decision_trace.py` imports `src.infrastructure.logger` — violates application/infrastructure boundary. Known tech debt.
- `project_exit_fill()` nesting depth in `PositionProjectionService` has grown. Known tech debt.

---

## 4. Current Non-goals

The following are explicitly not in scope for the current live-safe phase:

- LS-003c control path (confirmed mismatch → block / recovery)
- Orphan order auto-cancel
- Automatic protection order re-mount
- Complete account risk state machine
- Multi-strategy support
- Multi-asset universe expansion
- Portfolio engine
- Regime detection layer
- Data feature store
- Complete trading simulator
- Frontend runtime control or Owner Console
- Research candidate auto-promotion
- Backtester changes
- Strategy logic changes
- Risk rule changes
- Runtime profile schema changes

---

## 5. Candidate Next Tasks

These are potential follow-up items. None are scheduled or prioritized — each requires owner decision and a separate task card before implementation.

### LS-003c Candidate: Confirmed Severe Mismatch Handling

Only if owner explicitly approves. Would introduce the first control-path action from reconciliation: block symbol on confirmed severe mismatch. Must define which `mismatch_type` values qualify, whether single-round or multi-round confirmation is required, and how to recover blocked symbols. Does not include auto-fix. Requires ADR. Risk level is significantly higher than LS-003a/b.

### LS-002b Candidate: Daily Stats Persistence

Persist daily loss and trade count so they survive runtime restart. Should not be confused with a complete account risk state machine — this is a narrow checkpoint/persistence task. Requires design review for storage location and recovery semantics.

### Reconciliation Report Persistence — Completed (LS-003d)

Superseded by LS-003d. Periodic reconciliation read model results are now persisted to PG via dedicated `reconciliation_read_model_reports` + `reconciliation_read_model_mismatches` tables. Best-effort, non-blocking. ADR-0007.

### Owner Console Candidate

Read-only display of reconciliation status, risk limit state, and trace summaries. No runtime control actions. No parameter hot-modification. Requires backend API design before frontend work.

### Runtime Task Governance v1 Candidate

Consider a unified task manager only if the number of background tasks continues to grow. Current managed-task pattern (module-level handle + cancel helper) is sufficient for the current task count. Do not introduce abstraction for its own sake.

### get_account_snapshot Async/Timeout Candidate

Audit whether the synchronous `get_account_snapshot()` call can block the event loop under adverse conditions. Inspect + plan only. Not for implementation in this checkpoint cycle.

---

## 6. Recommended Caution

- **Do not proceed to LS-003c (control path) without explicit owner approval.** Transitioning from report-only reconciliation to symbol blocking or recovery task creation is a significant risk-level increase.
- **Each candidate task should begin with inspect + plan**, not direct implementation. The pattern established by LS-003a/003b (inspect → plan → implement → review → ADR) has proven effective.
- **Do not merge unrelated tasks into one large task.** Persistence, frontend, block, and recovery are separate concerns with different risk profiles. Keep them in separate task cards.
- **Do not treat TM-001 as a reason to broaden risk rules.** It is a narrow fail-open bug hardening slice, not a mandate to change runtime profiles, strategy behavior, backtests, frontend, LS-003c, block/recovery, or auto-fix behavior.
- **Do not expand live-safe scope into strategy, risk rule, or runtime profile territory.** These remain outside live-safe boundaries per ADR-0001.
- **Known infrastructure gaps (logger boundary, nesting depth) should be addressed as separate cleanup tasks**, not mixed into feature work.

---

## 7. Open Questions for Owner

1. Is LS-003c (confirmed severe mismatch → block symbol) needed, and if so, when?
2. Which `mismatch_type` values should qualify for automatic symbol blocking in LS-003c?
3. Should daily stats be persisted (LS-002b), and what is the target timeline?
4. ~~Should reconciliation results be persisted beyond log-only?~~ **Resolved: Yes — LS-003d completed.**
5. Should reconciliation results be displayed in a future Owner Console?
6. Should the synchronous `get_account_snapshot()` call be audited for event-loop blocking risk?
7. When would a unified TaskManager become worth introducing?
8. Should a retention policy be added for reconciliation reports and daily risk stats?
