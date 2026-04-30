# Live-safe v1 Findings

Use this file for program-local findings that matter during Live-safe v1.

Long-lived architecture decisions and durable collaboration rules belong in Memory MCP and `docs/adr/`.

## 2026-04-29

- Current system is treated as Sim-ready, not live-ready.
- The next priority is live-safe execution and account-level risk closure, not strategy-return optimization.
- `watch_orders` startup is the first P0 execution-chain blocker.

## 2026-04-30

- `Decision Trace Backbone v0` fits the current roadmap because it is thin-core, non-invasive, and trace-oriented rather than a broad audit platform.
- `LS-001` fits the current roadmap because it closes a live-safe runtime credibility gap without changing strategy logic, risk rules, or runtime profiles.
- `LS-002` fits the current roadmap because it activates daily limits using projected exit deltas and full-close counting without changing strategy logic, runtime profile semantics, or widening into an account risk state machine.
- Current known leftovers after `LS-001`:
  - `api.py` does not start order watch.
  - `src/infrastructure/exchange_gateway.py` still contains duplicate `watch_orders` definitions for later cleanup.
  - One order-watch task per symbol is acceptable for now but should be re-evaluated if runtime symbol count grows.
- The next real live-safe gap is `LS-002`, but it should begin with inspect + plan rather than direct implementation.

## 2026-05-01

- Post-merge review confirms the three live-safe feature commits are directionally sound and aligned with thin-core / non-invasive execution hardening.
- Hardening items that should be treated as next-iteration work:
  - `decision_trace.py` should stop importing `src.infrastructure.logger` directly; use a local standard logger inside `application/`.
  - `src/infrastructure/exchange_gateway.py` still contains duplicate `watch_orders` definitions and should be cleaned before further order-watch evolution.
  - Shared `_order_ws_running` state is acceptable for the current single-symbol runtime but must be replaced before multi-symbol runtime expansion.
  - `LS-002` daily stats are intentionally process-local in-memory state in v0; this is acceptable for current hardening but must be solved before live expansion.
- Lower-priority follow-ups:
  - `JsonlTraceSink` remains synchronous file I/O on the hot path and should be treated as v0 tech debt, not a current correctness blocker.
  - `project_exit_fill()` in `PositionProjectionService` has grown denser and is a reasonable candidate for later internal split once behavior is stable.
