> [!CAUTION]
> **SUPERSEDED** — This document describes an earlier roadmap, program model, or planning baseline that no longer represents current project direction, current constraints, or current agent instructions.
>
> It is preserved for historical traceability only.
>
> Current authoritative sources:
>
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> * `docs/canon/TECH_DEBT_BASELINE.md`
> * `docs/canon/DOCUMENT_GOVERNANCE.md`

# Live-safe v1 Findings

Use this file for program-local findings that matter during Live-safe v1.

Long-lived architecture decisions and durable collaboration rules belong in Memory MCP and `docs/adr/`.

## 2026-06-12

- RTF-001 local implementation confirms the useful split: existing
  `RuntimeExecutionIntentAdapterService` remains the owner of submit review,
  attempt outcome policy, and budget settlement creation, while
  `RuntimePostSubmitFinalizeService` is the idempotent packet owner that joins
  those facts and decides the next-attempt gate. This avoids creating another
  execution path.
- Post-submit accounting should be idempotent by default. If a
  `RuntimeExecutionSubmitOutcomeReview` already exists for an authorization,
  the accounting path should reuse it instead of creating another review before
  settlement.
- A real submitted runtime attempt must not be sent back through pre-submit
  rehearsal. If the attempt has a durable exchange submit execution result,
  local orders being `FILLED` / `CANCELED` / `OPEN`, or carrying an
  `exchange_order_id`, is post-submit evidence rather than a rehearsal
  failure.
- The consumed authorization should be frozen as `consumed` / `replay-only` /
  `reviewable`. It may be used for audit, duplicate-submit proof, budget
  settlement, attempt settlement, and review, but not for another submit or
  local order re-creation.
- The correct mainline after first-real-submit proof is
  `RuntimePostSubmitFinalize`: durable submit result -> reconciliation refresh
  -> submit outcome review -> attempt outcome policy -> budget settlement ->
  position/protection status -> next attempt gate.
- True risks are duplicate submit through old authorization, inaccurate
  budget/attempt accounting, unrecognized canceled/missing protection, and
  active-position mismatch between local PG and exchange facts.
- False blockers are missing manual evidence IDs, old local orders not being
  `CREATED`, the presence of exchange artifacts after a real submit, and
  unproven strategy alpha after the Owner accepted small bounded-loss
  right-tail experimentation.
- Execution-chain development should use local node tests and local dry-run
  packets before Tokyo integration. Tokyo should validate deployment,
  migrations, real account/order/position facts, and gated exchange actions,
  not serve as the first debugging surface for new domain/application nodes.

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
- Phase 5D exchange-connected read-only rehearsal exposed stale BTC testnet
  reduce-only conditional orders while BTC was flat. The bounded cleanup used
  the existing conditional cancel fallback and removed 6 orphan conditional
  orders. Final BTC/ETH read-only rehearsal passed with both symbols flat and
  no normal or conditional open orders. This improves testnet hygiene but still
  does not authorize multi-symbol runtime/profile changes.
- Phase 5E should begin as a design/authorization package, not as a direct
  runtime/profile change. Current runtime config is still single-symbol by
  construction (`MarketRuntimeConfig.symbols` derives from `primary_symbol`),
  and the controlled endpoints are hard-coded to ETH plus `sim1_eth_runtime`.
  The recommended 5E path is a new readonly testnet profile plus minimal
  multi-symbol market-scope support, then one runtime process with sequential
  ETH and BTC controlled exposure, explicit exposure/order caps, stop
  conditions, and rollback. Implementation and testnet execution remain Owner
  gated.
- Phase 5E implementation kept the multi-symbol change narrow: optional
  `symbols` in runtime market config, a new readonly inactive profile, and
  fixed ETH/BTC control endpoints under the Phase 5E profile. The bounded
  testnet rehearsal proved one runtime process can warm up, reconcile, and
  watch BTC+ETH simultaneously while executing a controlled ETH entry/close.
  BTC execution did not proceed because the fixed `0.001 BTC` notional was
  below min_notional and raising size would challenge the Owner cap. This is a
  cap/min-notional design blocker, not an execution failure.
- Runtime `/positions` can lag after a close because it may show the cached
  account snapshot before asset polling refreshes. For Phase 5E final flatness,
  direct Binance read-only inventory and PG active position/order repositories
  were treated as the authoritative cleanup evidence.
- Phase 5E follow-up converted the BTC min-notional blocker into a reusable
  read-only feasibility preflight. The endpoint reports whether each fixed
  controlled symbol spec is feasible under current price, min_notional, and
  cap before the entry path can place an order. This keeps the next BTC decision
  as an Owner cap/design decision instead of a runtime surprise.
- Phase 5E feasibility should prefer exchange-provided market metadata over
  conservative defaults. `ExchangeGateway.get_min_notional(symbol)` now extracts
  loaded `limits.cost.min` or Binance `MIN_NOTIONAL` / `NOTIONAL` filter values
  without making a hidden network call; default min_notional is only a fallback.
- BTC blocker handling now includes next-step decision evidence in the
  feasibility response: `next_viable_amount`, `next_viable_notional`, and
  `cap_shortfall`. For the observed blocked BTC price `77550.6`, the next
  `0.001 BTC` exchange step would be `0.002 BTC`, estimated notional
  `155.1012 USDT`, which exceeded the previous `130 USDT` cap by
  `25.1012 USDT`. This remains an Owner cap decision, not an automatic order
  sizing change.
- Owner later approved Binance testnet operations without the prior
  minimum-capital limitation. For Phase 5E testnet only, the BTC controlled
  spec is raised to `0.002 BTC` with max notional `250 USDT`; no real-live,
  mainnet, real-funds, withdrawal/transfer, or generic strategy-sizing
  authority is implied.
- Phase 5E BTC retry passed under that testnet-only authorization: feasibility
  used exchange metadata min_notional `50.0`, controlled entry completed at
  `0.002 BTC`, runtime-managed close filled, protection orders were
  terminalized/canceled, and final direct Binance testnet plus PG state was
  flat. Console order read-model side mapping also needed a display fix because
  `Direction.LONG` enum values were previously rendered through the fallback
  `SELL` branch even though the actual position was LONG.
- The stale `/api/runtime/positions` observation after Phase 5E should be fixed
  at the read-model boundary: when PG active-position lookup succeeds, PG active
  lifecycle is authoritative for whether a position exists; account snapshot
  can enrich mark price/PnL for those rows but must not resurrect a
  snapshot-only position after PG is flat.
- Daily risk stats scope should remain account-level across runtime profiles.
  The accepted LS-002b `scope_key="runtime:default"` is intentionally not
  profile-scoped or session-scoped, because daily loss/count limits are account
  risk controls. Phase rehearsals that need bounded order counts should use
  endpoint once guards, fixed caps, and session controls instead of splitting
  daily risk aggregates by profile.
- Phase 5E and later multi-symbol rehearsals should use a single inventory
  read model for preflight and final flatness evidence. The Phase 5E inventory
  endpoint reports exchange positions, exchange normal/conditional open orders,
  PG active positions, and PG open orders per symbol, plus `all_flat`; it is
  read-only and must not become a cleanup/mutation endpoint.
- Post-Phase-5E planning should prioritize long-term capability closure over
  more exchange-connected motion. The accepted direction is captured in
  `docs/ops/plc-long-term-capability-roadmap-v1.md`: complete campaign state,
  account state, multi-symbol isolation, Strategy Contract promotion, and
  evidence/rollback foundations in separable gates. The immediate recommended
  next capability is local campaign transition-table and replay proof, not a
  larger testnet run.
- PLC-STATE-001 confirms the right shape for campaign risk state hardening:
  table-driven transition rules first, deterministic replay proof second, and
  runtime event wiring after that evidence. The important guard is that
  `entry_filled` may only confirm an already armed session; it must not become
  a hidden arming path from `observe`.
- PLC-STATE-002/003/004 close the next auditability gap: campaign state is now
  ledger-backed, replayable against the durable snapshot, wired to existing
  order lifecycle callbacks, and exposed through a read-only replay evidence
  packet. This still does not authorize broader runtime/profile changes or
  real live; it creates the evidence substrate future bounded testnet
  rehearsals should collect.
- The PLC roadmap review changes the next planning priority. The earlier
  execution-safety branch remains useful evidence, but it should not imply that
  a reliable strategy execution platform is the immediate next build. Because
  there is still no runtime-eligible strategy candidate, ADR-0011 inserts
  paper-only Playbook Governance before Human Arm Gate and Strategy Contract
  work. The next accepted phase is Playbook Governance R0: playbook registry,
  switch decision log, cooldown/hard-lock rules, CPV0_2 continuity across
  playbooks, and dry-run review. Tracks B-E runtime implementation, Phase
  5H-8 runtime-oriented work, Strategy Contract v2 implementation, and further
  paper/testnet runtime stay deferred.
- ADR-0012 refines the Owner goal again: the active business model is Bounded
  Risk Campaign, not Strategy Execution Platform. In this model, lack of stable
  alpha does not require pretending a strategy exists; it requires a campaign
  envelope that isolates risk capital, constrains attempts, carries PnL across
  playbook switches, triggers profit-protect/loss-lock states, and records an
  evidence packet. The hard control is not "no risk"; it is "no risk
  spillover, no loss-counter reset, no post-loss/post-profit risk escalation,
  and no programmatic withdrawal."
- BRC mock PnL must remain business-state evidence only. It can test
  `profit_protect`, `loss_locked`, and final outcome logic, but it must not
  mutate exchange fills, account balances, daily risk stats, or real PnL. This
  keeps the ETH/BTC testnet order rehearsal and the campaign outcome rehearsal
  deliberately separate.

## 2026-05-09

- Current Owner-facing phase is `Observation + Research Methodology Reset`.
- BTC+ETH Phase 1 Direction A observation design is the only current mainline strategy-research object.
- SRR-002 is the accepted research methodology baseline for future analysis, but no current module satisfies SRR-002 standards.
- The local worktree shows one untracked research doc under `docs/ops/`, not 21 visible untracked research docs. The discrepancy should be resolved with the Owner before any submission or grouping action.
- Mac mini observation logging should remain docs-only/no-order unless separately approved; current required log dimensions are environment state, BTC/ETH signal observations, skipped signals, anomalies, and virtual risk exposure.

## 2026-05-26

- External BRC security audit immediate safety-gate findings are repaired in
  commit `bc7e2ad`: GKS now starts fail-closed before initialize; campaign
  transition `requires_owner_review` and `requires_flat_proof` flags are
  enforced; terminal runtime states require explicit triggers; LLM cannot
  upgrade generic Owner text into testnet rehearsal without explicit
  testnet/rehearsal wording; ended campaigns reject mock PnL; fixed testnet
  rehearsal results are schema-validated before workflow persistence; and
  loss-locked ended campaigns require Owner review before a new campaign can
  be created.
- Remaining external audit work is intentionally deferred to the relevant
  capability gates and recorded in
  `docs/ops/brc-pre-deploy-audit-backlog.md`.
  It is not a blocker for local-only BRC operator work, but it is a blocker
  before Feishu callbacks, cloud deployment, cloud-exposed Web mutation
  controls, or strategy-pool execution.
- Deferred pre-deploy issues are: rotate exposed testnet/Feishu secrets if
  needed, move cloud secrets to environment/secret manager, add Feishu/Web
  signing + timestamp + nonce/idempotency replay protection, bind
  confirmations to `workflow_run_id`, add authenticated operator sessions and
  CSRF/callback protection for Web/cloud, add deployment preflight/runbook,
  and define the future strategy-pool domain/promotion bridge separately from
  BRC operation governance.
- The next capability should reduce Owner operation friction without expanding
  authority. The recommended next task is `BRC-R4-001 Local Operator Console`:
  a local-only Web surface over existing BRC APIs, ledgers, and LLM workflow
  gates. It should not add new order paths, withdrawal/transfer, real-live
  authority, strategy execution, automatic sizing, or auto-filled confirmation
  phrases.
