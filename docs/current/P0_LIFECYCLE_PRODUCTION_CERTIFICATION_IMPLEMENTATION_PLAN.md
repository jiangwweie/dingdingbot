---
title: P0_LIFECYCLE_PRODUCTION_CERTIFICATION_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-11
---

# P0 Production Lifecycle Wiring And Continuous Reconciliation Implementation Plan

The architecture and authority boundary are defined by
`docs/current/P0_LIFECYCLE_PRODUCTION_CERTIFICATION_AND_CLOSURE_DESIGN.md`.

**Program ID:** `P0-LC`

**Execution owner:** Codex. Any bounded implementation delegated to another
agent must first receive a separate task card satisfying
`docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md`; this document alone is not a
Claude task authorization. `src/infrastructure/exchange_gateway.py` remains a
Codex-owned core file.

**Goal:** Make every production-shaped ticket progress from protected-submit truth to deterministic protection/recovery/runner/finalization and one Live Outcome row, or one exact hard blocker, without ambiguous exchange mutation.

**Architecture:** First fail-close lifecycle mutation that still runs inside the
current long PG transaction. Then separate immutable historical Ticket exchange
identity from current ENTRY qualification, produce account mode by
account+exchange, add `NettingDomainKey` ownership/source-specific holds, and
extend the existing `brc_ticket_bound_exchange_commands` authority for every
place/cancel effect. Only the committed claim -> transaction-free network I/O
-> committed result/reconciliation runner may re-enable lifecycle mutation.
Fill projection, independent settlement, finalization, and terminal outcome
then consume that typed truth.

**Tech Stack:** Python 3, SQLAlchemy, PostgreSQL/Alembic, Pydantic, pytest/pytest-asyncio, systemd, existing ExchangeGateway.

## Global Constraints

- No second lifecycle, recovery, runner, reconciliation, or file-authority path.
- No new ENTRY order from lifecycle maintenance.
- No FinalGate or Operation Layer bypass.
- No live profile, symbol/side, leverage, notional, sizing, or attempt-cap expansion.
- No unknown exchange-only order cancellation/adoption.
- Historical Ticket risk reduction and current ENTRY authority are separate decisions; a paused/retired current scope cannot make an existing Ticket unprotectable.
- New ENTRY remains fail-closed until durable lifecycle mutation capability is deployed and certified.
- Every account-mode fact and gateway binding carries exact `account_id + exchange_id`; no global or inferred account mode.
- Every exchange read/write receives the PG-mapped venue symbol. Hedge-capable reads/writes preserve exact `positionSide`; buy/sell does not imply a hedge side.
- One-way conflict scope is `account + exchange + instrument + NET`; hedge conflict scope is the same prefix plus `HEDGE:LONG|SHORT`.
- A domain hold is source-specific. One Ticket or projector may not clear another source's hold.
- `decimal.Decimal` for financial values.
- PG/current services are runtime authority; no recurring JSON/MD artifacts.
- Network I/O must not occur while an uncommitted transaction holds the only command intent/result truth.
- A timeout after an exchange call is `outcome_unknown`, never ordinary retryable failure.
- Before the short-transaction runner is certified, any lifecycle mutation path not already owned by a committed durable command fails before gateway I/O.
- Correctly persisted `business_blocked` is a successful worker run; only system/process failures return non-zero.
- A natural signal with a different `signal_event_id` preempts engineering at the next safe transaction boundary unless an unprotected position or unknown exchange outcome is active.
- No-active-lifecycle cadence creates zero exchange calls, zero state-transition rows, and zero files.

---

## File Map

| File | Responsibility |
| --- | --- |
| `src/application/action_time/process_outcome_relevance.py` | Decide whether a lane process outcome still owns current blocker authority |
| `src/application/action_time/exchange_scope.py` | Resolve immutable `TicketHistoricalExchangeScope`; validate separate `CurrentEntryEligibility` |
| `src/application/action_time/account_safe_facts.py` | Collect signed read-only account mode with explicit account/exchange identity |
| `src/application/action_time/runtime_pg_fact_snapshots.py` | Persist Ticket fact lineage and the account+exchange current mode projection |
| `src/application/action_time/exchange_order_ownership.py` | Classify all active/unresolved PG-linked exchange orders by Ticket and `NettingDomainKey` |
| `src/application/action_time/netting_domain_hold.py` | Materialize and source-specifically resolve domain holds on the existing freeze authority |
| `src/application/action_time/exchange_snapshot_provider.py` | Read and normalize all required exchange truth views |
| `src/interfaces/api_trading_console.py` | Bind the runtime gateway to explicit PG-compatible account/exchange identity and validate command scope before dispatch |
| `src/infrastructure/exchange_gateway.py` | Adapter-owned complete order views, position-side preservation, account-mode read, and hedge reduce-intent translation |
| `src/application/action_time/ticket_bound_fill_projector.py` | Project exchange fills into canonical ticket/protection/lifecycle state |
| `src/application/action_time/exchange_command.py` | Existing durable exchange-command state, extended for lifecycle place/cancel claims |
| `src/domain/ticket_bound_exchange_command.py` | Kind-specific command invariants and transitions |
| `src/application/action_time/ticket_bound_lifecycle_finalizer.py` | Final exit, settlement, outcome, review, and lifecycle closure coordinator |
| `src/application/action_time/lifecycle_maintenance_scheduler.py` | Bounded orchestration over current scopes; no duplicate authority |
| `scripts/run_ticket_bound_lifecycle_maintenance_once.py` | Short-transaction production runner and global deadline |
| `migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py` | Account+exchange mode current projection and source-specific domain fields/indexes on the existing freeze table |
| `migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py` | Typed scope/reduce intent, place/cancel source, target, claim/lease, and outcome fields on the existing command table |
| `scripts/verify_tokyo_runtime_governance_postdeploy.py` | Lifecycle-aware postdeploy acceptance |
| `scripts/ops/check_tokyo_runtime_ops_health_once.py` | Lifecycle service/table/critical-state health |

---

## Migration Order

| Order | Migration | Schema responsibility | Mutation authority |
| --- | --- | --- | --- |
| `113` | `2026-07-11-113_create_exchange_account_mode_and_domain_holds.py` | Create `brc_exchange_account_modes_current`; add account/exchange/instrument/mode/position-side/`netting_domain_key`, source-specific resolution fields, and indexes to `brc_ticket_bound_scope_freezes`; replace broad active-freeze uniqueness | None |
| `114` | `2026-07-11-114_extend_exchange_commands_for_lifecycle.py` | Extend `brc_ticket_bound_exchange_commands` with command kind/source, exact exchange scope, reduce intent, cancel target, lease/claim, attempt, and observation/result refs | None until Task 5 tests and Task 9 phase-two enablement pass |

Migration `113` must land before typed snapshot/ownership code. Migration `114`
must land before any legacy recovery/runner/cleanup executor delegates to the
durable runner. Neither migration creates a second command, freeze, snapshot,
or evidence authority.

---

### Task 1: Current Process-Outcome Relevance

**Files:**
- Create: `src/application/action_time/process_outcome_relevance.py`
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_process_outcome_relevance.py`
- Test: `tests/unit/test_strategy_live_candidate_pool.py`
- Test: `tests/unit/test_strategygroup_runtime_goal_status.py`
- Test: `tests/unit/test_daily_live_enablement_table.py`
- Test: `tests/unit/test_strategygroup_tradeability_decision.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`

**Interfaces:**
- Consumes: `runtime_process_outcome`, live signal, promotion, lane, Ticket, and complete safety/lifecycle lineage from one PG control-state snapshot.
- Produces: `process_outcome_has_current_blocking_authority(control_state, outcome) -> bool`.
- Daily Table, Goal Status, and Tradeability remain downstream Candidate Pool consumers; they must not duplicate this predicate.

- [x] **Step 1: Write failing expired-source tests**

  Prove an expired/stale source with no open promotion/lane/Ticket remains the latest process row but does not override `market_wait_validated` or notify the monitor.

- [x] **Step 2: Run the tests and verify RED**

  Run targeted Candidate Pool, Goal Status, Daily Table, and Tradeability tests; expected failure is the current unconditional persistent blocker.

- [x] **Step 3: Implement one shared relevance predicate**

  Match `source_watermark` exactly against the current chain identity. A new
  Signal ID on the same lane is a different event. Hard failures without an
  event-scoped watermark remain current until a newer successful outcome
  supersedes the process+scope current row.

- [x] **Step 4: Verify current and expired cases GREEN**

  Include a fresh/open source that still blocks and a later success that clears current authority.

- [x] **Step 5: Run PG projection-consistency tests**

  Candidate Pool, Daily Table, Goal Status, Tradeability, and Monitor must agree
  on current readiness. Add the explicit Signal A failure -> A expiry -> Signal
  B same-lane acceptance case.

### Task 2: Immediate Lifecycle Mutation Interlock

**Task ID:** `P0-LC-02`; **execution owner:** Codex.

**Files:**
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `deploy/systemd/brc-ticket-lifecycle-maintenance.service`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_runtime_signal_watcher_systemd_units.py`
- Test: `tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`

**Interfaces:**
- Produces: one explicit `lifecycle_mutation_capability_ready` decision consumed by Runtime Safety State and the lifecycle worker.
- Before Task 5 certification, production lifecycle recovery/runner/cleanup remains read-only and a new ENTRY stops at `lifecycle_mutation_capability_not_ready`.
- This is a temporary safety interlock, not a manual lifecycle operating model.

- [x] **Step 1: Write failing interlock tests**

  Prove `--allow-exchange-mutation` alone cannot call recovery, runner, cleanup,
  or any injected gateway mutation when the durable capability is absent.

- [x] **Step 2: Write failing ENTRY qualification test**

  A fresh otherwise-ready Ticket must not reach exchange write while its
  production lifecycle mutation capability is known unsafe; read-only natural
  signal acceptance still records the exact blocker.

- [x] **Step 3: Verify RED against the current production-shaped unit**

  Expected failure: the current systemd unit enables mutation and the worker
  can call gateway I/O while one outer `engine.begin()` remains open.

- [x] **Step 4: Implement the fail-closed capability gate**

  Remove unconditional production mutation enablement. Keep read-only snapshot
  observation available. The capability can become true only after migration
  `114`, durable command runner checks, and the Task 5 transaction tests pass.

- [x] **Step 5: Verify GREEN and zero mutation gateway calls**

  Run the scheduler/systemd/Runtime Safety tests and prove the interlock creates
  no JSON/MD files and no periodic PG evidence rows.

### Task 3: Account Mode, Gateway Binding, And Domain-Hold Schema

**Files:**
- Create: `migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py`
- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `src/application/action_time/runtime_pg_fact_snapshots.py`
- Create: `src/application/action_time/netting_domain_hold.py`
- Modify: `src/interfaces/api_trading_console.py`
- Test: `tests/unit/test_action_time_account_safe_facts.py`
- Test: `tests/unit/test_runtime_pg_fact_snapshots.py`
- Test: `tests/unit/test_netting_domain_hold.py`
- Test: `tests/unit/test_action_time_full_chain_impact.py`
- Test: `tests/unit/test_pg_runtime_control_state_foundation_migration.py`

**Interfaces:**
- Produces: one signed-GET account-mode fact and one current projection keyed by
  `account_id + exchange_id`; a runtime gateway binding with the same exact
  identity; source-specific domain-hold columns/indexes on the existing
  `brc_ticket_bound_scope_freezes` authority.
- The Ticket fact snapshot remains immutable lineage. The current projection is
  used only to validate present account mode and must never rewrite historical
  Ticket meaning.

- [x] **Step 1: Write failing production-producer contract tests**

  Start at Binance USD-M signed GET `/fapi/v1/positionSide/dual`. Prove the writer persists exact
  `account_id`, canonical `exchange_id`, `position_mode`,
  `position_mode_safe`, observed time, and validity without a hand-authored
  downstream `account_mode` dictionary.

- [x] **Step 2: Write failing account/exchange mismatch tests**

  Wrong/missing gateway account id, `binance` versus `binance_usdm` ambiguity,
  stale mode, and a mode change after Ticket creation must all block before
  exchange I/O.

- [x] **Step 3: Write failing source-specific hold migration tests**

  Two source ids may hold the same `NettingDomainKey`; resolving one source
  leaves the other active. Remove the old one-active-freeze-per
  StrategyGroup/symbol/side uniqueness rule without deleting existing rows.

- [x] **Step 4: Verify RED**

  Expected failures: production writer lacks mode/account/exchange values,
  gateway binding lacks PG identity, and the existing freeze uniqueness shape
  collapses independent sources.

- [x] **Step 5: Implement migration `113`, producer, writer, and binding**

  The current single account still requires explicit non-secret account binding;
  require `BRC_RUNTIME_EXCHANGE_ACCOUNT_ID` plus canonical
  `BRC_RUNTIME_EXCHANGE_ID=binance_usdm` while
  the adapter may use CCXT name `binance`. No default account id or symbol
  inference is allowed. Migration application alone must not enable lifecycle
  mutation.

- [x] **Step 6: Verify GREEN, upgrade/downgrade, and producer-to-consumer shape**

### Task 4: Historical Ticket Scope, Complete Snapshots, And Global Ownership

**Task ID:** `P0-LC-04`; **execution owner:** Codex because this task changes
`src/infrastructure/exchange_gateway.py` and `src/application/reconciliation.py`.

**Files:**
- Create: `src/application/action_time/exchange_scope.py`
- Create: `src/application/action_time/exchange_order_ownership.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `src/domain/models.py`
- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `src/application/reconciliation.py`
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Test: `tests/unit/test_ticket_bound_exchange_scope.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_ls003a_reconciliation_read_model.py`
- Test: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Test: `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`

**Interfaces:**
- Produces: `resolve_ticket_historical_exchange_scope(conn, ticket_id) -> TicketHistoricalExchangeScopeResolution` and `validate_current_entry_eligibility(conn, scope, gateway_binding, now_ms) -> CurrentEntryEligibility`.
- `TicketHistoricalExchangeScope` includes Ticket/budget/runtime binding lineage,
  canonical and venue symbol, account/exchange/instrument, strategy side,
  expected mode/position side, entry/exit sides, and `NettingDomainKey`.
- The historical resolver uses mapping validity at Ticket creation. The current
  validator separately requires active present scope and durable lifecycle
  capability.

- [x] **Step 1: Write failing historical-versus-current tests**

  A mapping/binding valid at Ticket creation but now retired/paused still
  resolves existing-Ticket risk reduction; current ENTRY validation blocks.
  Missing or contradictory historical lineage hard-stops. Test `SUIUSDT ->
  SUI/USDT:USDT` and an arbitrary non-crypto venue symbol without string
  inference.

- [x] **Step 2: Write failing complete-view and position tests**

  The current Binance adapter queries default plus its actual stop/conditional
  capability view. Do not model `type=STOP_MARKET` as an independent view.
  Required-view failure and conflicting duplicates are incomplete truth.
  Empty complete scoped positions may prove flat; missing/malformed/ambiguous
  symbol or `positionSide` is unknown.

- [x] **Step 3: Write failing `NettingDomainKey` tests**

  One-way same account/instrument conflicts across StrategyGroups. Hedge same
  side conflicts; verified opposite sides isolate. StrategyGroup, Ticket, and
  runtime profile must not split a one-way net domain.

- [x] **Step 4: Write failing global ownership and hold tests**

  Compare exchange/client ids with all active or unresolved PG commands and
  protection rows for the account/instrument. Prove current Ticket,
  same-domain other Ticket, isolated other domain, unowned, and identity
  conflict classifications. One reconciler may resolve only its own hold.

- [x] **Step 5: Verify RED**

  Expected failures: canonical gateway reads, default-view-only orders,
  dropped `positionSide`, first-nonzero position selection, Ticket-local unknown
  order detection, and broad scope-freeze resolution.

- [x] **Step 6: Implement one resolver, one gateway aggregation method, and one ownership classifier**

  Move duplicated open-order view aggregation out of reconciliation into the
  core gateway. Cache one complete snapshot per `NettingDomainKey` per scheduler
  invocation. No recurring snapshot table or file is added.

- [x] **Step 7: Verify GREEN, gateway readiness compatibility, bounded calls, and zero files**

### Task 5: Existing Exchange-Command Authority And Transaction-Safe Runner

**Files:**
- Create: `migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py`
- Modify: `src/domain/ticket_bound_exchange_command.py`
- Modify: `src/application/action_time/exchange_command.py`
- Modify: `src/application/action_time/exchange_command_reconciliation.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/interfaces/api_trading_console.py`
- Modify: `src/application/action_time/protection_recovery_command.py`
- Modify: `src/application/action_time/runner_mutation_executor.py`
- Modify: `src/application/action_time/orphan_protection_cleanup_command.py`
- Test: `tests/unit/test_ticket_bound_exchange_command.py`
- Test: `tests/unit/test_ticket_bound_exchange_command_materialization.py`
- Test: `tests/unit/test_ticket_bound_exchange_command_reconciliation.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_ticket_bound_protection_recovery_command.py`
- Test: `tests/unit/test_ticket_bound_runner_mutation_executor.py`
- Test: `tests/unit/test_ticket_bound_orphan_protection_cleanup_command.py`
- Test: `tests/unit/test_pg_runtime_control_state_foundation_migration.py`

**Interfaces:**
- Produces: place/cancel claim/lease/result API on the existing
  `brc_ticket_bound_exchange_commands` authority, shared by protected submit,
  recovery, runner, and cleanup.
- Every command freezes account, exchange, canonical/venue instrument identity,
  expected mode/position side, `NettingDomainKey`, command source/kind, and
  typed open/reduce intent before claim.
- The CLI owns transaction phase boundaries; command modules retain
  command-specific stale checks and result application.
- Recovery/runner/cleanup plan tables do not own exchange results.

- [x] **Step 1: Write failing no-network-inside-transaction test**

  Instrument the engine/connection and gateway so any network call while a transaction is open fails the test.

- [x] **Step 2: Write failing all-write-path identity tests**

  Protected submit, protection recovery, runner submit, old-SL cancel, orphan
  cleanup, and ambiguous-outcome reconciliation must all use the historical
  scope's venue symbol. Hedge place commands pass exact `positionSide` and
  typed `reduce_position` intent; one-way reduce commands pass `reduce_only` and
  omit `positionSide`. Cancel validates the target domain even when the venue
  cancel API has no position-side parameter. Resolver or gateway-binding
  failure produces zero exchange calls.

- [x] **Step 3: Write failing concurrent claim test**

  Timer/API contenders may claim one command exactly once.

- [x] **Step 4: Write failing process-termination/outcome-unknown tests**

  Timeout after accepted place/cancel must preserve committed intent, create a
  source-specific hold on its `NettingDomainKey`, and require identity
  reconciliation before retry. A different Ticket success cannot clear it.

- [x] **Step 5: Write failing partial cleanup resume test**

  Successfully cancelled orders are projected before later cancel failure; the remaining linked orders can resume without repeating earlier cancels.

- [x] **Step 6: Verify RED**

- [x] **Step 7: Apply migration `114` and extend the existing command service**

  Add typed scope/reduce intent, command kind/source, cancel target identity,
  and lease fields with kind-specific constraints. Persist deterministic
  client/cancel identities before exchange I/O. Do not create a second command
  table, and do not let migration presence alone satisfy the mutation
  capability gate.

- [x] **Step 8: Refactor every mutation caller into committed phases**

  Use `short select/claim transaction -> network I/O with no PG transaction ->
  short result/outcome_unknown transaction -> optional bounded read -> short
  reconcile/advance transaction`. One claimed mutation command per invocation;
  one scope failure cannot roll back another committed scope.

- [x] **Step 9: Implement `outcome_unknown` reconciliation-before-retry**

  An expired `dispatching` lease transitions to `outcome_unknown`; it is never
  directly reclaimed for mutation.

- [x] **Step 10: Verify GREEN, migration upgrade/downgrade, command idempotency, and interlock readiness**

  Only after no-network-in-transaction, all-write-path scope, concurrent claim,
  timeout, and reconciliation tests pass may the capability report ready. The
  production systemd unit remains fail-closed until Task 9 postdeploy phase two.

### Task 6: Exchange Fill Projector And Monotonic Lifecycle

**Files:**
- Create: `src/application/action_time/ticket_bound_fill_projector.py`
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Test: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Test: `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`

**Interfaces:**
- Consumes: complete typed snapshot, global ownership classification, and current Ticket-bound orders.
- Produces: idempotent fill projection summary and canonical order/lifecycle events without resolving foreign domain holds.

- [x] **Step 1: Write failing TP1 fill-to-runner test**

  Start with TP1 PG status `submitted` and an exchange TP1 fill. One production
  scheduler pass marks TP1 `filled` and prepares one durable runner command
  without fixture helpers.

- [x] **Step 2: Write failing partial ENTRY tests**

  Protection quantity uses actual filled quantity; no recovery may expand
  exposure to requested quantity.

- [x] **Step 3: Write failing final-exit and repeated-cadence tests**

  SL/RUNNER_SL fill plus complete flat proof creates one final-exit lineage;
  three identical ticks create no duplicates, state regression, or foreign-hold
  resolution.

- [x] **Step 4: Verify RED**

- [x] **Step 5: Implement one fill projector before reconciliation decisions**

- [x] **Step 6: Add `runner_protected` and finalization states to bounded scheduler selection**

- [x] **Step 7: Verify monotonic GREEN and bounded PG growth**

### Task 7: Ticket-Bound Finalization, Settlement, Review, And Outcome

**Files:**
- Create: `src/application/action_time/ticket_bound_lifecycle_finalizer.py`
- Modify: `src/application/action_time/post_submit_closure.py`
- Modify: `src/application/action_time/live_outcome_ledger.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Test: `tests/unit/test_ticket_bound_post_submit_closure.py`
- Test: `tests/unit/test_live_outcome_ledger.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`

**Interfaces:**
- Settlement service consumes: matching final-exit fill, flat-position proof,
  no residual linked protection, and the consumed Ticket-owned budget
  reservation. It atomically releases the reservation and records a
  deterministic settlement event.
- Finalization consumes: settlement evidence plus terminal lifecycle facts.
- Produces: review-ready closure, validated system review, final closed
  lifecycle, then one terminal Live Outcome.

- [x] **Step 1: Write failing producer-to-closure test**

  No direct lifecycle-event insertion is allowed. A flat snapshot with matching
  final fill must drive reconciliation, independent settlement, review,
  closure, and then Outcome through production services.

- [x] **Step 2: Write failing lineage-rejection tests**

  Bare `lifecycle_closed` without final-exit/reconciliation/settlement/review lineage cannot create a valid closed outcome.

- [x] **Step 3: Write failing financial projection tests**

  Fill data should populate final exit price, fee totals, realized PnL, and R multiple when inputs are available; absent funding remains explicitly unavailable, not zero.

- [x] **Step 4: Write failing hard-blocked/recovered/idempotent tests**

- [x] **Step 5: Verify RED**

- [x] **Step 6: Implement settlement service and finalization coordinator**

  Order: final reconciliation -> independent budget settlement evidence ->
  review-ready -> validated system review -> review event -> lifecycle close ->
  one final Outcome. The closure coordinator never mutates runtime budget.

- [x] **Step 7: Verify GREEN and no execution-authority leakage**

### Task 8: Production-Shaped Lifecycle Certification Harness

**Boundary:** isolated test database + mock gateway + synthetic producer input.
The result is `pre_live_rehearsal_ready`; it is forbidden from writing Tokyo PG
or presenting synthetic scopes as live-market outcomes.

**Files:**
- Modify: `src/application/action_time/full_chain_simulation_harness.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`
- Create: `tests/unit/test_ticket_bound_production_lifecycle_certification.py`

**Interfaces:**
- Starts at raw gateway/public/account responses and uses production projectors.
- Must not directly insert downstream-ready facts, signals, readiness, settlement, review, or closed lifecycle rows for the capability under test.

- [x] **Step 1: Add a test that rejects privileged fixture insertion**

- [x] **Step 2: Build six-Event-Spec producer-to-lifecycle certification cases**

- [x] **Step 3: Add historical/current identity and account-mode cases**

  Cover mapping/binding retirement after Ticket creation, current ENTRY
  rejection, signed producer shape, gateway account/exchange mismatch, one-way,
  hedge, mode change, and arbitrary future venue symbol identity.

- [x] **Step 4: Add NettingDomain ownership/hold and all-write-path cases**

  Cover same-symbol multi-StrategyGroup one-way conflict, hedge same/opposite
  side, global order ownership, two source holds, and protected-submit/recovery/
  runner/cleanup venue symbol plus hedge reduce-intent transport.

- [x] **Step 5: Add timeout, partial fill, repeated cadence, retry exhaustion, and final closure cases**

- [x] **Step 6: Add transaction, deadline, and natural-signal interrupt cases**

  No network call may observe an open PG transaction. Same signal is
  idempotent; a different identity preempts only at a committed boundary and
  never bypasses the mutation interlock.

- [x] **Step 7: Verify all 22 rehearsal scopes reach simulated closed outcome or one expected deterministic blocker**

### Task 9: Cadence, Two-Phase Deploy, And Ops Health

**Files:**
- Modify: `deploy/systemd/brc-ticket-lifecycle-maintenance.service`
- Modify: `deploy/systemd/brc-ticket-lifecycle-maintenance.timer`
- Modify: `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- Modify: `scripts/ops/check_tokyo_runtime_ops_health_once.py`
- Modify: `scripts/plan_tokyo_runtime_governance_git_deploy.py`
- Test: `tests/unit/test_runtime_signal_watcher_systemd_units.py`
- Test: `tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py`
- Test: `tests/unit/test_tokyo_runtime_deploy_plan.py`

**Interfaces:**
- Postdeploy consumes release/systemd/PG health only and performs no exchange write.
- Deploy phase one applies migrations/code with lifecycle mutation disabled;
  phase two enables the durable capability only after account-mode producer,
  command runner, transaction, rehearsal, and no-active checks pass.
- Ops health returns non-zero for critical active lifecycle ambiguity. The
  lifecycle worker itself exits zero for a correctly persisted
  `business_blocked` result and non-zero only for process/system failures.

- [x] **Step 1: Write failing global-deadline/systemd-budget tests**

  Prove `TimeoutStartSec > application_global_deadline + shutdown_margin`, one
  mutation command per invocation, no new claim after deadline, and no
  multi-scope `4 * 8s` worst-case plan.

- [x] **Step 2: Write failing phase-one interlock and migration postdeploy tests**

  Require migrations `113` and `114`, exact production account-mode shape,
  explicit gateway binding, and zero reachable legacy direct mutation before
  phase two.

- [x] **Step 3: Write failing false-green ops health tests**

- [x] **Step 4: Implement deadline, unit verification, PG lifecycle checks, and critical exit semantics**

- [x] **Step 5: Verify no-active-lifecycle tick is zero-call/zero-row/zero-file**

- [x] **Step 6: Verify phase-two capability enablement is mechanically gated**

  The deploy plan must quiesce the timer, refuse enablement until all gate
  checks pass, and define rollback as disabling only the capability flag while
  commands and holds remain. The actual Tokyo phase-two action occurs in Task
  10 after full verification.

### Task 10: Documentation, Full Verification, Commit, Deploy

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md`
- Modify: `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Update implementation status and remove stale release/migration facts**

- [x] **Step 2: Run all targeted lifecycle and pre-trade projection tests**

- [x] **Step 3: Run the full test suite**

- [x] **Step 4: Run production file-I/O, output-scope, current-doc authority, migration, and diff audits**

- [x] **Step 5: Review diff against every design acceptance item**

- [x] **Step 6: Commit and push the focused branch**

- [x] **Step 7: Execute controlled Tokyo phase-one deploy with migrations and timer quiescence**

- [x] **Step 8: Run postdeploy no-exchange-write production certification and only then phase-two capability enablement**

- [x] **Step 9: Verify PG current truth and document the only remaining market-dependent calibration**

## Final Completion Checklist

- [x] 22/22 scopes have correct current blocker relevance, and a new Signal ID cannot inherit an old same-lane blocker.
- [x] Historical Ticket identity and current ENTRY qualification are separate: current pause/retirement blocks new exposure without disabling existing-Ticket risk reduction.
- [x] Production account-mode facts and gateway binding agree on exact account/exchange identity; stale, missing, malformed, foreign-account, and mode-change cases fail closed.
- [x] `NettingDomainKey` is shared across StrategyGroups in one-way mode and isolates only proven hedge sides/subaccounts.
- [x] Global ownership distinguishes current Ticket, other Ticket same/isolated domain, unowned, and identity conflict.
- [x] Multiple source-specific holds may coexist; one source cannot clear another source's hold.
- [x] Canonical and exchange symbols never cross authority boundaries incorrectly on any snapshot, protected-submit, recovery, runner, cleanup, or reconciliation call.
- [x] Conditional protection orders and side-scoped positions are complete; required-view failure or malformed/ambiguous position is unknown, not flat.
- [x] Hedge reduce intent transports exact `positionSide`; one-way/hedge venue parameter differences do not weaken business reduce semantics.
- [x] ENTRY/TP1/SL/RUNNER fills project without fixture-only state changes.
- [x] One existing exchange-command table owns protected-submit, recovery, runner, and cleanup mutation results.
- [x] No network I/O depends on an uncommitted command intent/result transaction.
- [x] Timeout/termination becomes `outcome_unknown` and reconciles before retry.
- [x] Before short-transaction certification and postdeploy phase-two enablement, lifecycle mutation and new ENTRY remain fail-closed.
- [x] Runner-protected tickets remain scheduled through final exit.
- [x] Independent settlement, review, lifecycle closure, and terminal Live Outcome have production callers in that order.
- [x] Full-chain rehearsal certification begins at production producer boundaries without writing production PG.
- [x] No-active cadence stays zero-call/zero-row/zero-file.
- [x] Postdeploy and ops health cover lifecycle units/tables/critical states.
- [x] Application global deadline plus shutdown margin is strictly below systemd timeout, and one invocation claims at most one mutation command.
- [x] A different natural Signal ID preempts engineering only after higher safety work and at a committed boundary; it never bypasses an incomplete capability.
- [x] Full tests and audits pass.
- [x] Tokyo release and PG migration match the pushed commit.
- [x] Only genuine live-market calibration remains.

## Safe Interrupt Rule

At every task boundary and before every command claim, inspect PG in this order:

1. **Safety interrupt:** unprotected position, `outcome_unknown`, unowned order,
   or critical active domain hold preempts all other work.
2. **Natural-signal acceptance interrupt:** a different new
   `signal_event_id` pauses engineering only at a committed transaction
   boundary, runs the production acceptance path, and persists the exact
   reached stage/blocker. Same identity is idempotent.
3. **Engineering certification:** when neither interrupt exists, continue the
   same P0-LC checklist item without waiting for market opportunity.

Natural-signal acceptance cannot enable mutation, clear a foreign hold, or
bypass account/exchange/mode, Runtime Safety State, FinalGate, or Operation
Layer. After its result is persisted, implementation resumes at the same
checklist item.
