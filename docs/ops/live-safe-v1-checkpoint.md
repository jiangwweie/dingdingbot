# Live-safe v1 Checkpoint

**Date:** 2026-04-30  
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
- Duplicate `watch_orders` definition in `exchange_gateway.py` remains for later cleanup.

### LS-002 Daily Risk Limits Runtime Closure v0

- `CapitalProtectionManager` daily loss and daily trade count are now active in the runtime, not dead stats.
- Daily PnL is tracked via projected realized exit deltas from `PositionProjectionService.project_exit_fill()`.
- Trade count increments on full position close (not partial TP).
- UTC day boundary reset is applied at each relevant call site.
- v0 state is in-memory only: restart loses all daily stats. This is an accepted limitation.
- ADR-0003 documents semantics, scope, and non-goals.

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

---

## 2. Current Live-safe Capability

Compared to pre-live-safe state:

- **Order runtime state is more可信**: order-watch ensures local lifecycle receives real-time exchange updates; startup reconciliation can advance stale orders at boot.
- **Daily limits are real**: `pre_order_check` now enforces daily loss and daily trade count limits using live projected PnL, not dead placeholder stats.
- **Reconciliation is observable**: the system now periodically compares local and exchange state and surfaces mismatches as structured logs — reconciliation is no longer a manual-only capability.
- **Decision traceability exists**: risk decisions are recorded to JSONL for post-mortem analysis.
- **Non-invasive and rollback-friendly**: all live-safe additions are optional (trace is `Optional`, reconciliation loop can be disabled by not starting the task), and none change core trading logic.

---

## 3. Known Limitations

### Infrastructure gaps

- `api.py` does not start order-watch tasks (out of LS-001 scope).
- `exchange_gateway.py` contains duplicate `watch_orders` definitions — the old one is dead code but remains in the file.
- `_order_ws_running` is a shared flag across multiple watch tasks; acceptable for single-symbol runtime but fragile for multi-symbol.
- `update_snapshot_loop()` is fire-and-forget: no stored task reference, no cancellation, no await during shutdown. Not addressed by current live-safe scope.

### Daily limits

- v0 state is in-memory: runtime restart resets daily loss and trade count to zero.
- Daily PnL is projected realized PnL, not complete account-level daily loss.
- Funding fees and full fee breakdown are not fully纳入 daily loss calculation.

### Reconciliation

- LS-003a/b reconciliation is report-only: does not block, recover, or auto-fix.
- Protection coverage is `symbol_role_v0` — symbol-level, not position-chain-level.
- Reconciliation does not validate `reduce_only` flag on exchange-side orders.
- Reconciliation does not validate TP/SL price reasonableness.
- No reconciliation report persistence: observation history is log-only and lost on restart.
- No grace period or consecutive-mismatch confirmation in LS-003b.
- `_parse_ccxt_order` maps all `reduce_only=True` orders to `OrderRole.TP1` (including SL); this only affects metadata display and does not trigger action.

### Other

- `decision_trace.py` imports `src.infrastructure.logger` — violates application/infrastructure boundary. Known tech debt.
- `project_exit_fill()` nesting depth in `PositionProjectionService` has grown. Known tech debt.

---

## 4. Current Non-goals

The following are explicitly not in scope for the current live-safe phase:

- Multi-strategy support
- Multi-asset universe expansion
- Portfolio engine
- Regime detection layer
- Data feature store
- Complete account risk state machine
- Automatic reconciliation repair or auto-fix
- Orphan order auto-cancel
- Automatic protection order re-mount
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

### Cleanup Candidate: duplicate `watch_orders` definition

Remove the shadowed, dead `watch_orders` definition from `exchange_gateway.py`. Does not change active behavior. Requires focused regression tests on order-watch to confirm no implicit reliance on the old definition.

### Runtime Task Governance Candidate

Audit all background tasks in `main.py`. Address fire-and-forget patterns (notably `update_snapshot_loop`). Establish a unified task creation, storage, cancellation, and await pattern. Does not change trading logic. Could be a low-risk infra cleanup.

### LS-003c Candidate: Confirmed Severe Mismatch Handling

Only if owner explicitly approves. Would introduce the first control-path action from reconciliation: block symbol on confirmed severe mismatch. Must define which `mismatch_type` values qualify, whether single-round or multi-round confirmation is required, and how to recover blocked symbols. Does not include auto-fix. Requires ADR.

### LS-002b Candidate: Daily Stats Persistence

Persist daily loss and trade count so they survive runtime restart. Should not be confused with a complete account risk state machine — this is a narrow checkpoint/persistence task. Requires design review for storage location and recovery semantics.

### Owner Console Candidate

Read-only display of reconciliation status, risk limit state, and trace summaries. No runtime control actions. Requires backend API design before frontend work.

---

## 6. Recommended Caution

- **Do not proceed to LS-003c (control path) without explicit owner approval.** Transitioning from report-only reconciliation to symbol blocking or recovery task creation is a significant risk-level increase.
- **Each candidate task should begin with inspect + plan**, not direct implementation. The pattern established by LS-003a/003b (inspect → plan → implement → review → ADR) has proven effective.
- **Do not expand live-safe scope into strategy, risk rule, or runtime profile territory.** These remain outside live-safe boundaries per ADR-0001.
- **Known infrastructure gaps (fire-and-forget tasks, duplicate definitions, logger boundary) should be addressed as separate cleanup tasks**, not mixed into feature work.

---

## 7. Open Questions for Owner

1. Should the duplicate `watch_orders` definition be cleaned up before further order-watch evolution?
2. Should runtime background task governance (`update_snapshot_loop` fire-and-forget, unified cancel pattern) be addressed before LS-003c?
3. Is LS-003c (confirmed severe mismatch → block symbol) needed, and if so, when?
4. Which `mismatch_type` values should qualify for automatic symbol blocking in LS-003c?
5. Should daily stats be persisted (LS-002b), and what is the target timeline?
6. Should reconciliation results be displayed in a future Owner Console?
7. Should the live-safe task board be unified or consolidated now that LS-003a/b are complete?
