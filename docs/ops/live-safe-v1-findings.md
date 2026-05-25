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
- TC-TINY-001D-3 found the remaining reconciliation warning noise was local
  historical data, not current exchange risk: 821 `ETH/USDT:USDT` `OPEN` ENTRY
  rows had no active local position. They were backed up, terminalized locally
  to `CANCELED`, and audited without exchange mutation.
- TC-TINY-001D-5 confirmed Binance testnet STOP_MARKET confirmation can require
  evidence outside immediate `fetch_order`. Confirmation now accepts recent
  order-watch evidence and retries conditional `fetch_open_orders` after a
  `fetch_order` miss before raising a false protection-health critical.
- PLC Phase 1 can be promoted without exchange/runtime authority by using a
  pure read-only adapter. The adapter rejects non-frozen contracts and
  non-prior snapshots before deterministic contract evaluation, and its output
  has explicit `read_only_no_order_authority`.
- PLC Phase 2 can remain non-runtime by wrapping read-only previews into paper
  observation packets. Review status and operator notes are data only; packet
  authority explicitly forbids order placement/cancellation, exchange mutation,
  real account reads, and runtime profile changes.
- PLC Phase 3 should not execute until runtime-owned close exists. Direct
  exchange cleanup would fail the purpose of the rehearsal because it would not
  validate projection, daily stats, terminalization, and reconciliation through
  the runtime lifecycle.
- PLC Phase 3 pre-execution now has explicit campaign/account safety boundaries:
  campaign state must be armed before entry, close remains allowed as a
  risk-reducing action from armed/profit-protect/loss-locked/hard-locked, and
  account/liquidation state must fail closed for new entries when unknown,
  degraded, or critical.
- PLC Phase 3 attempt 1 exposed a post-close cleanup idempotency gap: after a
  reduce-only market close fills and Binance removes dependent protection
  orders, `OrderNotFoundError` from protection cancellation must not turn a
  flat, successfully closed position into a failed close. The runtime should
  terminalize the local protection row after confirmed flat/confirmed close
  while continuing to fail on non-idempotent cancellation errors.
- PLC Phase 3 retry passed after that fix. The important runtime lesson is that
  Binance testnet can remove reduce-only protection orders immediately after a
  full reduce-only close, so post-close cleanup must be idempotent for missing
  protection orders while preserving fail-fast behavior before the close is
  confirmed.
- PLC Phase 4 review is complete for the current evidence set, but real live is
  not authorized and not ready. The blocking gaps are account risk enforcement,
  durable campaign state enforcement, conditional SL visibility in
  protection-health, runtime control lifecycle reset, and absence of a promoted
  strategy contract.
- PLC Phase 4 local hardening converted the first four blockers into code-level
  controls: account/liquidation fail-closed gate, PG-backed campaign state
  machine, conditional STOP_MARKET read-model visibility, and startup-guard
  shutdown reset. This is still not a real-live readiness claim until PG
  migration plus non-real-live runtime/testnet smoke evidence exists.
- The current Alembic chain is not clean-install safe for PG: migration `002`
  creates `orders` with a foreign key to `signals`, but a clean schema does not
  have `signals` yet. Runtime `PGCoreBase.metadata.create_all()` can initialize
  the core PG tables, but migration-chain repair or a baseline migration is
  needed before treating Alembic head as the runtime schema authority.

## 2026-05-09

- Current Owner-facing phase is `Observation + Research Methodology Reset`.
- BTC+ETH Phase 1 Direction A observation design is the only current mainline strategy-research object.
- SRR-002 is the accepted research methodology baseline for future analysis, but no current module satisfies SRR-002 standards.
- The local worktree shows one untracked research doc under `docs/ops/`, not 21 visible untracked research docs. The discrepancy should be resolved with the Owner before any submission or grouping action.
- Mac mini observation logging should remain docs-only/no-order unless separately approved; current required log dimensions are environment state, BTC/ETH signal observations, skipped signals, anomalies, and virtual risk exposure.
