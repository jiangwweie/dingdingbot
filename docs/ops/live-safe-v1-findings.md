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
- The clean PG Alembic blocker found during Phase 4 has been repaired for the
  current chain: migration `002` no longer references `signals` before it
  exists, migration `009` handles both historical order-role constraint names,
  and clean local PG `alembic upgrade head` reached `010 (head)`. `create_all`
  is still used afterward to restore the current runtime model shape, so future
  work should keep Alembic and `PGCoreBase` from drifting again.
- PLC Phase 4 non-real-live smoke closed the first four blockers for review:
  account/campaign gates were active in runtime, active testnet exposure saw
  normal open orders `2` plus conditional stop open orders `1`, periodic
  reconciliation was `consistent`, no protection-health missing/orphan block
  appeared, controlled close returned `FILLED`, final testnet state was
  position `0` / normal open `0` / stop open `0`, and shutdown released port
  `8001` naturally.
- Binance testnet conditional order cancellation needs a dedicated fallback:
  normal `cancel_order(id, symbol)` can return `OrderNotFound` for a conditional
  STOP_MARKET that is still visible through
  `fetch_open_orders(symbol, params={"stop": True})`. Runtime cancellation now
  verifies the same exchange id in the stop-order view and cancels with
  `params={"stop": True}`; an empty Binance cancel `status` is interpreted as
  `canceled`.
- ARCH-P4-001 resolves the two-composition-root debt exposed by Phase 4 smoke:
  `main.py` owns execution-runtime composition and shutdown; `api.py`
  receives a bound `RuntimeContext` in embedded mode and no longer creates an
  exchange gateway, execution orchestrator, startup reconciliation, or
  protection-health runtime in standalone uvicorn mode.
- Standalone API is intentionally lower priority and degraded to
  HTTP/config/read-only behavior until the API/frontend track becomes active
  again. Runtime control endpoints should return unavailable without an
  embedded context rather than silently creating a second execution runtime.
- ARCH-P4-001 acceptance repair closed the remaining compatibility edge cases:
  bound `RuntimeContext` now supports legacy `_signal_repo` / `_repository` /
  `_account_getter` reads used by console routes, and context clear removes the
  compatibility globals that otherwise could retain stale runtime handles.
- Phase 5A starts the small-scale rehearsal readiness path without widening
  real-live authority. The important architecture shift is from single-symbol
  entry checks toward platform-level gates: account-risk now prefers
  account-scope positions and total exposure, campaign state can be advanced by
  runtime events, and Strategy Contract promotion can only grant eligibility
  for the next review gate with no order/exchange/account/profile authority.
- Phase 5A bounded Binance testnet smoke passed after those gate changes:
  one controlled entry, one runtime controlled close, final runtime positions
  `0`, local active orders `0`, restored GKS/campaign/startup-guard controls,
  clean shutdown, and no missing-stop or orphan protection-health block logged.
  This supports `phase5a_first_gates_smoked_on_testnet`; it does not authorize
  repeated rehearsal, multi-symbol runtime, or real live.
- Phase 5B opened repeated testnet rehearsal without changing the real-live
  boundary. The first symbol-isolation hardening targets the highest-risk
  shared assumptions before multi-symbol expansion: order-watch running state
  now has a symbol-keyed map, and recent order-update confirmation evidence is
  indexed by symbol before falling back to legacy ids. Reconciliation and
  read-model symbol isolation remain review items, so multi-symbol runtime is
  still blocked.
- Phase 5B repeated Binance testnet passed across two fresh runtime processes.
  Each cycle completed one controlled entry and one runtime controlled close,
  ended with runtime positions `0`, local active orders `0`, restored
  GKS/campaign/startup-guard state, natural shutdown, and port `8001` release.
  This supports repeated ETH-only testnet rehearsal review, not multi-symbol or
  real-live promotion.
- Phase 5C local BTC/ETH synthetic fixture closes the first reconciliation and
  read-model proof gap: `build_read_model(symbol)` keeps other-symbol
  mismatches out, runtime positions/orders/execution-intents now support
  symbol-filtered reads, and portfolio remains an account-level aggregation.
  This is still not a multi-symbol runtime authorization because no
  exchange-connected two-symbol process, profile change, or account-risk cap
  review was performed.

## 2026-05-09

- Current Owner-facing phase is `Observation + Research Methodology Reset`.
- BTC+ETH Phase 1 Direction A observation design is the only current mainline strategy-research object.
- SRR-002 is the accepted research methodology baseline for future analysis, but no current module satisfies SRR-002 standards.
- The local worktree shows one untracked research doc under `docs/ops/`, not 21 visible untracked research docs. The discrepancy should be resolved with the Owner before any submission or grouping action.
- Mac mini observation logging should remain docs-only/no-order unless separately approved; current required log dimensions are environment state, BTC/ETH signal observations, skipped signals, anomalies, and virtual risk exposure.
