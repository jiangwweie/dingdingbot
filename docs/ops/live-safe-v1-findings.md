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

## 2026-05-06

- Owner accepted LS-002b daily risk stats persistence using PG aggregate + event ledger with fixed `scope_key="runtime:default"`.
- LS-002b keeps LS-002 projected realized PnL, full-close trade count, and UTC runtime date semantics; it does not introduce portfolio/account semantics or full account-true daily PnL reconstruction.
- Restore/write-through failure must fail closed for new entries with `DAILY_RISK_STATS_UNAVAILABLE`, through the existing `pre_order_check` Decision Trace deny path, while exits/protection handling/shutdown/reconciliation/circuit-breaker rebuild continue.
- Accepted LS-002b limitation: position projection save and daily stats event/aggregate write are not in one DB transaction; a crash/write window remains for future hardening.
- LS-003d reconciliation read model persistence intentionally uses dedicated read-only tables instead of startup reconciliation tables because startup reconciliation carries action/resolution semantics. LS-003d remains observational and best-effort; LS-003c block/recovery/repair behavior stays out of scope.

## 2026-05-09

- Current Owner-facing phase is `Observation + Research Methodology Reset`.
- BTC+ETH Phase 1 Direction A observation design is the only current mainline strategy-research object.
- SRR-002 is the accepted research methodology baseline for future analysis, but no current module satisfies SRR-002 standards.
- The local worktree shows one untracked research doc under `docs/ops/`, not 21 visible untracked research docs. The discrepancy should be resolved with the Owner before any submission or grouping action.
- Mac mini observation logging should remain docs-only/no-order unless separately approved; current required log dimensions are environment state, BTC/ETH signal observations, skipped signals, anomalies, and virtual risk exposure.
