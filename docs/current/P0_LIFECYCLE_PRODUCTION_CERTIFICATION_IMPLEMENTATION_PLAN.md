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

**Architecture:** Extend the existing ticket-bound scheduler and
`brc_ticket_bound_exchange_commands` authority. Add typed exchange scope, fill
projection, lease/claim fields to the current command core, an independent
ticket-bound settlement service, and a production finalization coordinator;
keep exchange I/O outside long PG transactions and keep PG/current services as
the only runtime authority.

**Tech Stack:** Python 3, SQLAlchemy, PostgreSQL/Alembic, Pydantic, pytest/pytest-asyncio, systemd, existing ExchangeGateway.

## Global Constraints

- No second lifecycle, recovery, runner, reconciliation, or file-authority path.
- No new ENTRY order from lifecycle maintenance.
- No FinalGate or Operation Layer bypass.
- No live profile, symbol/side, leverage, notional, sizing, or attempt-cap expansion.
- No unknown exchange-only order cancellation/adoption.
- `decimal.Decimal` for financial values.
- PG/current services are runtime authority; no recurring JSON/MD artifacts.
- Network I/O must not occur while an uncommitted transaction holds the only command intent/result truth.
- A timeout after an exchange call is `outcome_unknown`, never ordinary retryable failure.
- Correctly persisted `business_blocked` is a successful worker run; only system/process failures return non-zero.
- A natural signal with a different `signal_event_id` preempts engineering at the next safe transaction boundary unless an unprotected position or unknown exchange outcome is active.
- No-active-lifecycle cadence creates zero exchange calls, zero state-transition rows, and zero files.

---

## File Map

| File | Responsibility |
| --- | --- |
| `src/application/action_time/process_outcome_relevance.py` | Decide whether a lane process outcome still owns current blocker authority |
| `src/application/action_time/exchange_scope.py` | Resolve ticket-bound canonical identity to venue symbol/account/side scope |
| `src/application/action_time/exchange_snapshot_provider.py` | Read and normalize all required exchange truth views |
| `src/application/action_time/ticket_bound_fill_projector.py` | Project exchange fills into canonical ticket/protection/lifecycle state |
| `src/application/action_time/exchange_command.py` | Existing durable exchange-command state, extended for lifecycle place/cancel claims |
| `src/domain/ticket_bound_exchange_command.py` | Kind-specific command invariants and transitions |
| `src/application/action_time/ticket_bound_budget_settlement.py` | Independent idempotent reservation release and settlement evidence |
| `src/application/action_time/lifecycle_finalization.py` | Final exit, settlement, outcome, review, and lifecycle closure coordinator |
| `src/application/action_time/lifecycle_maintenance_scheduler.py` | Bounded orchestration over current scopes; no duplicate authority |
| `scripts/run_ticket_bound_lifecycle_maintenance_once.py` | Short-transaction production runner and global deadline |
| `migrations/versions/2026-07-11-113_*.py` | Existing exchange-command lifecycle extensions and required closure schema changes |
| `scripts/verify_tokyo_runtime_governance_postdeploy.py` | Lifecycle-aware postdeploy acceptance |
| `scripts/ops/check_tokyo_runtime_ops_health_once.py` | Lifecycle service/table/critical-state health |

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

- [ ] **Step 1: Write failing expired-source tests**

  Prove an expired/stale source with no open promotion/lane/Ticket remains the latest process row but does not override `market_wait_validated` or notify the monitor.

- [ ] **Step 2: Run the tests and verify RED**

  Run targeted Candidate Pool, Goal Status, Daily Table, and Tradeability tests; expected failure is the current unconditional persistent blocker.

- [ ] **Step 3: Implement one shared relevance predicate**

  Match `source_watermark` exactly against the current chain identity. A new
  Signal ID on the same lane is a different event. Hard failures without an
  event-scoped watermark remain current until a newer successful outcome
  supersedes the process+scope current row.

- [ ] **Step 4: Verify current and expired cases GREEN**

  Include a fresh/open source that still blocks and a later success that clears current authority.

- [ ] **Step 5: Run PG projection-consistency tests**

  Candidate Pool, Daily Table, Goal Status, Tradeability, and Monitor must agree
  on current readiness. Add the explicit Signal A failure -> A expiry -> Signal
  B same-lane acceptance case.

### Task 2: Typed Exchange Scope And Complete Snapshot Views

**Task ID:** `P0-LC-02`; **execution owner:** Codex because this task changes
`src/infrastructure/exchange_gateway.py`.

**Files:**
- Create: `src/application/action_time/exchange_scope.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `src/application/action_time/runner_mutation_executor.py`
- Modify: `src/application/action_time/orphan_protection_cleanup_command.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_exchange_gateway.py`

**Interfaces:**
- Produces: typed `TicketBoundExchangeScope` with ticket id, instrument id, canonical symbol, exchange symbol, side/position side, runtime profile/account.
- Consumes: gateway method that returns deduplicated normal and conditional open orders.
- Exchange symbol resolution must use the PG instrument mapping; string-format inference is forbidden so future equity, precious-metal, and expiring-contract instruments use the same boundary.

- [ ] **Step 1: Write failing canonical/exchange symbol tests**

  `SUIUSDT` must resolve to `SUI/USDT:USDT`; all read/write gateway calls receive the exchange symbol while PG rows keep canonical identity.

- [ ] **Step 2: Write failing conditional-order visibility tests**

  A STOP_MARKET SL returned only by the conditional view must be visible exactly once.

- [ ] **Step 3: Write failing hedge-side and malformed-position tests**

  Opposite-side positions must not be selected; missing/malformed position must be `unknown`, never `flat`.

- [ ] **Step 4: Verify RED**

  Expected failures: direct canonical symbol gateway call, one-view open-order fetch, and first-nonzero-position selection.

- [ ] **Step 5: Implement typed resolver and gateway view aggregation**

  Extend the core gateway instead of adding a second adapter. Deduplicate by exchange order id/client order id.

- [ ] **Step 6: Add netting-aware global active order ownership classification**

  Orders owned by another Ticket are `owned_elsewhere`, not `unknown`. Then
  evaluate account + instrument + position mode + position side: a shared net
  position domain remains `active_position_resolution`; only proven isolated
  scopes may proceed independently.

- [ ] **Step 7: Verify GREEN and gateway readiness compatibility**

### Task 3: Exchange Fill Projector And Monotonic Lifecycle

**Files:**
- Create: `src/application/action_time/ticket_bound_fill_projector.py`
- Modify: `src/application/action_time/protection_reconciler.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Test: `tests/unit/test_ticket_bound_protection_reconciler.py`
- Test: `tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`

**Interfaces:**
- Consumes: typed snapshot plus current ticket-bound orders.
- Produces: idempotent fill projection summary and canonical order/lifecycle events.

- [ ] **Step 1: Write failing TP1 fill-to-runner test**

  Start with TP1 PG status `submitted` and an exchange TP1 fill. One production scheduler pass must mark TP1 `filled` and prepare runner mutation without fixture helpers.

- [ ] **Step 2: Write failing partial ENTRY tests**

  Protection quantity uses actual filled quantity; no recovery may expand exposure to requested quantity.

- [ ] **Step 3: Write failing final-exit and repeated-cadence tests**

  SL/RUNNER_SL fill plus flat position creates one final-exit lineage; three identical ticks create no duplicates or state regression.

- [ ] **Step 4: Verify RED**

- [ ] **Step 5: Implement one fill projector before reconciliation decisions**

- [ ] **Step 6: Add `runner_protected` and finalization states to bounded scheduler selection**

- [ ] **Step 7: Verify monotonic GREEN and bounded PG growth**

### Task 4: Existing Exchange-Command Authority And Transaction-Safe Runner

**Files:**
- Create: `migrations/versions/2026-07-11-113_extend_ticket_bound_exchange_commands_for_lifecycle.py`
- Modify: `src/domain/ticket_bound_exchange_command.py`
- Modify: `src/application/action_time/exchange_command.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Modify: `src/application/action_time/lifecycle_maintenance_scheduler.py`
- Modify: `src/application/action_time/protection_recovery_command.py`
- Modify: `src/application/action_time/runner_mutation_executor.py`
- Modify: `src/application/action_time/orphan_protection_cleanup_command.py`
- Test: `tests/unit/test_ticket_bound_lifecycle_scheduler.py`
- Test: `tests/unit/test_ticket_bound_protection_recovery_command.py`
- Test: `tests/unit/test_ticket_bound_runner_mutation_executor.py`
- Test: `tests/unit/test_ticket_bound_orphan_protection_cleanup_command.py`
- Test: `tests/unit/test_pg_runtime_control_state_foundation_migration.py`

**Interfaces:**
- Produces: place/cancel claim/lease/result API on the existing
  `brc_ticket_bound_exchange_commands` authority, shared by protected submit,
  recovery, runner, and cleanup.
- The CLI owns transaction phase boundaries; command modules retain command-specific stale checks and result application.
- Recovery/runner/cleanup plan tables do not own exchange results.

- [ ] **Step 1: Write failing no-network-inside-transaction test**

  Instrument the engine/connection and gateway so any network call while a transaction is open fails the test.

- [ ] **Step 2: Write failing concurrent claim test**

  Timer/API contenders may claim one command exactly once.

- [ ] **Step 3: Write failing process-termination/outcome-unknown tests**

  Timeout after accepted SL/RUNNER submit must preserve committed intent and require identity reconciliation before retry.

- [ ] **Step 4: Write failing partial cleanup resume test**

  Successfully cancelled orders are projected before later cancel failure; the remaining linked orders can resume without repeating earlier cancels.

- [ ] **Step 5: Verify RED**

- [ ] **Step 6: Extend the existing exchange-command schema and service**

  Add command kind/source, cancel target identity, and lease fields with
  kind-specific constraints. Use short transactions and a lease/`FOR UPDATE
  SKIP LOCKED` claim. Persist deterministic client/cancel identities before
  exchange I/O. Do not create a second command table.

- [ ] **Step 7: Refactor CLI into select/claim, network, result, reconcile phases**

  One mutation-capable scope per invocation. One scope failure must not roll back another committed scope.

- [ ] **Step 8: Implement `outcome_unknown` reconciliation-before-retry**

  An expired `dispatching` lease transitions to `outcome_unknown`; it is never
  directly reclaimed for mutation.

- [ ] **Step 9: Verify GREEN, migration upgrade/downgrade, and command idempotency**

### Task 5: Ticket-Bound Finalization, Settlement, Review, And Outcome

**Files:**
- Create: `src/application/action_time/ticket_bound_budget_settlement.py`
- Create: `src/application/action_time/lifecycle_finalization.py`
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

- [ ] **Step 1: Write failing producer-to-closure test**

  No direct lifecycle-event insertion is allowed. A flat snapshot with matching
  final fill must drive reconciliation, independent settlement, review,
  closure, and then Outcome through production services.

- [ ] **Step 2: Write failing lineage-rejection tests**

  Bare `lifecycle_closed` without final-exit/reconciliation/settlement/review lineage cannot create a valid closed outcome.

- [ ] **Step 3: Write failing financial projection tests**

  Fill data should populate final exit price, fee totals, realized PnL, and R multiple when inputs are available; absent funding remains explicitly unavailable, not zero.

- [ ] **Step 4: Write failing hard-blocked/recovered/idempotent tests**

- [ ] **Step 5: Verify RED**

- [ ] **Step 6: Implement settlement service and finalization coordinator**

  Order: final reconciliation -> independent budget settlement evidence ->
  review-ready -> validated system review -> review event -> lifecycle close ->
  one final Outcome. The closure coordinator never mutates runtime budget.

- [ ] **Step 7: Verify GREEN and no execution-authority leakage**

### Task 6: Production-Shaped Lifecycle Certification Harness

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

- [ ] **Step 1: Add a test that rejects privileged fixture insertion**

- [ ] **Step 2: Build six-Event-Spec producer-to-lifecycle certification cases**

- [ ] **Step 3: Add same-symbol multi-StrategyGroup/multi-side ownership cases**

- [ ] **Step 4: Add timeout, partial fill, repeated cadence, retry exhaustion, and final closure cases**

- [ ] **Step 5: Verify all 22 rehearsal scopes reach simulated closed outcome or one expected deterministic blocker**

### Task 7: Cadence, Systemd, Postdeploy, And Ops Health

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
- Ops health returns non-zero for critical active lifecycle ambiguity. The
  lifecycle worker itself exits zero for a correctly persisted
  `business_blocked` result and non-zero only for process/system failures.

- [ ] **Step 1: Write failing global-deadline/systemd-budget tests**

- [ ] **Step 2: Write failing lifecycle unit/table/postdeploy tests**

- [ ] **Step 3: Write failing false-green ops health tests**

- [ ] **Step 4: Implement deadline, unit verification, PG lifecycle checks, and critical exit semantics**

- [ ] **Step 5: Verify no-active-lifecycle tick is zero-call/zero-row/zero-file**

### Task 8: Documentation, Full Verification, Commit, Deploy

**Files:**
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/P0_C_PRODUCTION_LIFECYCLE_SCHEDULER_AND_SNAPSHOT_SOURCE_DESIGN.md`
- Modify: `docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Update implementation status and remove stale release/migration facts**

- [ ] **Step 2: Run all targeted lifecycle and pre-trade projection tests**

- [ ] **Step 3: Run the full test suite**

- [ ] **Step 4: Run production file-I/O, output-scope, current-doc authority, migration, and diff audits**

- [ ] **Step 5: Review diff against every design acceptance item**

- [ ] **Step 6: Commit and push the focused branch**

- [ ] **Step 7: Execute controlled Tokyo deploy with migration and timer quiescence**

- [ ] **Step 8: Run postdeploy no-exchange-write production certification**

- [ ] **Step 9: Verify PG current truth and document the only remaining market-dependent calibration**

## Final Completion Checklist

- [ ] 22/22 scopes have correct current blocker relevance, and a new Signal ID cannot inherit an old same-lane blocker.
- [ ] Canonical and exchange symbols never cross authority boundaries incorrectly.
- [ ] Conditional protection orders and side-scoped positions are visible.
- [ ] ENTRY/TP1/SL/RUNNER fills project without fixture-only state changes.
- [ ] One existing exchange-command table owns protected-submit, recovery, runner, and cleanup mutation results.
- [ ] No network I/O depends on an uncommitted command intent/result transaction.
- [ ] Timeout/termination becomes `outcome_unknown` and reconciles before retry.
- [ ] Runner-protected tickets remain scheduled through final exit.
- [ ] Independent settlement, review, lifecycle closure, and terminal Live Outcome have production callers in that order.
- [ ] Full-chain rehearsal certification begins at production producer boundaries without writing production PG.
- [ ] No-active cadence stays zero-call/zero-row/zero-file.
- [ ] Postdeploy and ops health cover lifecycle units/tables/critical states.
- [ ] Full tests and audits pass.
- [ ] Tokyo release and PG migration match the pushed commit.
- [ ] Only genuine live-market calibration remains.

## Safe Interrupt Rule

At every task boundary, first inspect PG for an unprotected position or
`outcome_unknown`. Those safety states preempt all other work. Otherwise a new
different `signal_event_id` preempts the next engineering step at a committed
transaction boundary for the natural-signal acceptance path; after its result
is persisted, implementation resumes at the same checklist item.
