---
title: P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_IMPLEMENTATION_PLAN
status: PROPOSED_AWAITING_OWNER_CONFIRMATION
authority: docs/current/P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_IMPLEMENTATION_PLAN.md
implements: docs/current/P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_DESIGN.md
last_verified: 2026-07-19
design_branch: codex/budget-model-review-20260714
local_head: 3e0c265550cb62491adf8d05af3dd598151006c4
production_head: 1aa05462795b0ae26d51837d73c3a90f9a86f19c
production_schema_count: 138
owner_decision: PENDING
implementation_state: NOT_STARTED
deployment_state: NO_CHANGE
exchange_write: 0
---

# P0 Ticket Exit Runner Production Closure Implementation Plan

## 1. Program Summary

**Program ID:** RNR-P0

**Design authority:**
docs/current/P0_TICKET_EXIT_RUNNER_PRODUCTION_CLOSURE_DESIGN.md

**Execution owner:** Codex.

**Current state:** Proposed and awaiting Owner confirmation. This plan is not
implementation authority until the Owner confirms the paired design and this
execution sequence.

**Goal:** Close the complete Ticket-bound TP1, moving-stop Runner, invalidation,
time-stop, final-exit and terminal projection chain without creating a second
scheduler, a second exchange writer, an in-memory position thread, a manual
Owner operation, or a file-backed runtime authority.

The target production path is:

~~~text
30-second lifecycle oneshot
-> select bounded due scopes from PG
-> fetch exchange and due closed-candle truth outside PG transactions
-> persist immutable static references and dynamic facts
-> run one Ticket exit state machine
-> persist one deterministic exchange command when required
-> dispatch through the existing unique command worker
-> reconcile exact command/order/fill identity
-> update protection generation
-> final exit, cleanup, settlement and terminal projection
~~~

**Runner is not an independent thread.** It is a policy stage inside the
existing short-lived lifecycle worker. The 15-minute behavior is represented
by PG watermarks and closed-candle identity, not by a sleeping process.

## 2. Known Objective Baseline

| Surface | Current verified fact | Implementation consequence | Source |
| --- | --- | --- | --- |
| Local branch | codex/budget-model-review-20260714 | implementation stays on this focused branch | current git |
| Local HEAD | 3e0c265550cb62491adf8d05af3dd598151006c4 | RED baseline and future release parent | current git |
| Tokyo HEAD | 1aa05462795b0ae26d51837d73c3a90f9a86f19c | deploy diff must remain explicit | Tokyo release manifest |
| Tokyo schema | 138 | next additive migration is 139 | Tokyo PG |
| Lifecycle cadence | about 30 seconds | no new Runner timer is needed | systemd |
| Durable mutation | enabled | reuse current command worker | Tokyo PG and journal |
| Active maintainable lifecycle | zero at verification time | no-active canary is available | Tokyo PG and journal |
| Pending nonterminal command | zero at verification time | deployment may proceed only if rechecked | Tokyo PG |
| ticket_exit_market facts | zero | scheduling is the first blocker | Tokyo PG |

## 3. Global Authority Model

Every task in this plan preserves:

~~~text
Owner controls policy.
System executes process.
Tradeability Decision answers can-trade.
Runtime Safety State answers live-submit safety.
Review updates strategy governance.
~~~

This implementation may repair engineering capability inside the already
approved policy. It does not authorize:

- a new StrategyGroup, symbol, side, account, venue or runtime profile;
- leverage, notional, quantity fraction, exposure or attempt-cap expansion;
- a TP1 market fallback;
- FinalGate or Operation Layer bypass;
- an exchange write from a fact producer, evaluator, monitor, replay or file;
- credential mutation, withdrawal or transfer;
- cancellation of active protection before replacement or flat confirmation;
- duplicate close submission after an unknown outcome.

## 4. Program-Wide Engineering Constraints

1. **One scheduler:** brc-ticket-lifecycle-maintenance.timer remains the only
   Ticket lifecycle cadence owner.
2. **One writer:** brc_ticket_bound_exchange_commands and its existing worker
   remain the only normal Ticket lifecycle exchange mutation path.
3. **PG authority:** current state, reference snapshots, facts, commands,
   fills, protection generations and terminal projections remain in PG/current
   services.
4. **No runtime files:** production no-op and active ticks create zero JSON,
   Markdown, JSONL or YAML artifacts.
5. **Decimal only:** price, quantity, fee, ATR and PnL calculations use
   decimal.Decimal.
6. **Short transactions:** public/exchange I/O occurs outside PG transactions.
7. **Bounded work:** at most one mutation command is dispatched per invocation;
   scopes and fact fetch groups remain bounded.
8. **Unknown means stop:** a timed-out or ambiguous exchange mutation becomes
   outcome_unknown and freezes the exact netting domain until reconciled.
9. **Protection first:** a replacement Runner stop is accepted before the old
   stop is cancelled; final protection is retained until position-flat truth.
10. **No hidden aliases:** static strategy references are bound by a versioned
    typed key and exact signal lineage, not by SOR-only application constants.
11. **Natural signal independence:** Tasks RNR-T00 through RNR-T10 do not require
    a natural live signal. Absence of a fresh market opportunity blocks only
    RNR-T11 live calibration.
12. **Core ownership:** changes to Codex-owned core files require direct Codex
    implementation and review. No delegated task may modify them unless its
    task card explicitly grants that file.

## 5. Target File Map

| Area | Primary files | Responsibility |
| --- | --- | --- |
| Exit reference model | src/domain/ticket_exit_policy.py | typed immutable Ticket reference snapshot and invariants |
| Exit reference binding | src/application/action_time/ticket_exit_policy_binding.py | bind exact signal evidence before submit |
| Current projection | src/application/action_time/ticket_exit_policy_projection.py | watermark, blocker, Runner generation and terminal state |
| Dynamic facts | src/application/action_time/ticket_exit_market_fact_service.py | final closed-candle facts only |
| Policy service | src/application/action_time/ticket_exit_policy_service.py | TP1, floor, structural Runner, invalidation and time-stop decisions |
| TP1 completion | new pure domain reducer plus current projector consumers | cumulative completion across all TP1 generations |
| Fill projection | src/application/action_time/ticket_bound_fill_projector.py | exact fill identity and role projection |
| Protection reconciliation | src/application/action_time/protection_reconciler.py | remaining quantity, live order identity and cleanup truth |
| Command authority | src/domain/ticket_bound_exchange_command.py and application command services | deterministic place/cancel/FINAL_EXIT intent |
| Lifecycle scheduling | src/application/action_time/lifecycle_maintenance_scheduler.py | bounded orchestration and due-fact stage |
| Production runner | scripts/run_ticket_bound_lifecycle_maintenance_once.py | global deadline, short transactions and unique command dispatch |
| Terminal closure | src/application/action_time/post_submit_closure.py and ticket_bound_lifecycle_finalizer.py | final fill, cleanup, settlement, review and terminal state |
| Schema | migrations/versions/2026-07-19-139_close_ticket_exit_runner.py | additive reference, FINAL_EXIT and due-scope schema |

## 6. Dependency And Execution Order

| Order | Task ID | Depends on | Main capability | Production mutation |
| ---: | --- | --- | --- | --- |
| 1 | RNR-T00 | none | freeze RED evidence and contracts | none |
| 2 | RNR-T01 | T00 | migration 139 and static reference snapshot | none |
| 3 | RNR-T02 | T01 | scheduled due 15m fact production | none |
| 4 | RNR-T03 | T01, T02 | correct Runner fact consumption | none |
| 5 | RNR-T04 | T00 | one TP1 completion reducer | none |
| 6 | RNR-T05 | T04 | residual TP1 after partial cancel/reprice | durable existing path in tests only |
| 7 | RNR-T06 | T03, T04, T05 | reliable Runner replacement | durable existing path in tests only |
| 8 | RNR-T07 | T03, T06 | exact FINAL_EXIT lineage | durable existing path in tests only |
| 9 | RNR-T08 | T04, T07 | terminal projection and exact repair | PG-only repair |
| 10 | RNR-T09 | T01-T08 | local PostgreSQL/full-chain certification | simulation only |
| 11 | RNR-T10 | T09 | Tokyo deploy and bounded canary | only inside existing authority |
| 12 | RNR-T11 | T10 | natural Ticket live calibration | only after normal gates pass |

Tasks T01 through T04 may be developed in parallel only after T00 freezes the
contracts. Integration remains sequential from T05 onward because TP1
completion, protection replacement and final-exit lineage share the same
durable state machine.

## 7. Migration 139 Contract

### 7.1 Migration identity

Proposed file:

~~~text
migrations/versions/2026-07-19-139_close_ticket_exit_runner.py
~~~

Migration 139 is additive. It must not drop or rewrite historical Ticket,
order, fill, lifecycle, settlement or review rows.

### 7.2 Schema changes

Migration 139 adds to brc_ticket_exit_policy_current:

- exit_reference_schema_version;
- exit_reference_snapshot JSONB;
- exit_reference_hash;
- exit_reference_bound_at_ms;
- terminal_at_ms.

It extends exact role constraints where required to include FINAL_EXIT in:

- brc_ticket_bound_exchange_commands;
- Ticket-bound protection/final-exit order projections;
- fill and lifecycle role constraints.

It may add one bounded due-scope partial index over:

~~~text
state
next_evaluation_not_before_ms
updated_at_ms
~~~

The index lands only if EXPLAIN using production-shaped rows proves it improves
the bounded selection plan.

### 7.3 Migration acceptance

- disposable PostgreSQL upgrade succeeds from migration 138;
- downgrade or additive-stay rollback behavior is explicitly tested;
- current rows remain readable before reference binding;
- new live-submit binding fails closed when a required reference is absent;
- legacy terminal rows are not silently reactivated;
- all existing constraints retain current accepted values;
- migration application alone cannot enable or dispatch exchange mutation.

## 8. Task Cards

### RNR-T00 — Failure Reproduction And Contract Freeze

**Task ID:** RNR-T00

**Goal:** Turn every diagnosed defect into a production-shaped failing test and
freeze the exact expected contracts before implementation changes.

**Why:** The current unit tests prove individual helpers but do not prove the
real scheduler-to-fact boundary, static/dynamic reference separation, TP1
cross-generation completion, FINAL_EXIT lineage or terminal projection.

**Allowed files:**

- tests/unit/test_ticket_exit_market_fact_service.py;
- tests/unit/test_ticket_exit_policy_service.py;
- tests/unit/test_ticket_exit_policy_tp1_reprice.py;
- tests/unit/test_ticket_bound_fill_projector.py;
- tests/unit/test_ticket_bound_protection_reconciler.py;
- tests/unit/test_ticket_bound_lifecycle_scheduler.py;
- tests/unit/test_ticket_bound_lifecycle_finalizer.py;
- tests/unit/test_ticket_exit_policy_full_chain.py;
- tests/unit/lifecycle_test_schema.py;
- one new focused test module if existing modules cannot express a full-chain
  PostgreSQL scenario.

**Forbidden files:**

- all production implementation files;
- migrations;
- deploy/systemd;
- Owner policy and strategy registry rows;
- output/**.

**Requirements:**

1. Reproduce a due active exit projection for which the production scheduler
   performs no ticket_exit_market producer call.
2. Reproduce a valid closed-candle fact that is discarded because
   opening_range_high is absent from dynamic fact payload.
3. Reproduce TP1 fills split across two exchange order generations.
4. Reproduce a partial fill during TP1 cancel/reprice and prove the current
   target can become wedged or mis-sized.
5. Reproduce a strategy final close that becomes EXTERNAL_CLOSE.
6. Reproduce a flat closed lifecycle whose exit-policy current row remains
   nonterminal.
7. Add negative tests for duplicate facts, adverse stop movement, unknown
   command outcome and network work inside a transaction.

**Global Authority Model:** Tests may construct synthetic facts and commands.
They grant no runtime or exchange authority.

**Chain Position:**

~~~text
stage: ticket_bound_post_submit_lifecycle
first_blocker: event_execution_capability_not_certified
owner_action_required: false after plan confirmation
~~~

**Live Enablement State Before:** Defects are supported by production evidence
but not fully encoded as one regression contract.

**Live Enablement State After:** Every first blocker has one deterministic RED
test at its actual producer/consumer boundary.

**Blocker Removed Or Reclassified:** No production blocker is removed. Ambiguous
claims become exact failing contracts.

**Per-Symbol / Per-Fact Acceptance:** Tests use at least one long and one short
fixture; exact exchange_instrument_id is independent from display symbol.

**Stop Condition:** Stop if the failing behavior cannot be reproduced from
current tracked code and production-shaped schema. Reconcile the diagnosis
before any implementation.

**Capability Unlocked:** Safe implementation against frozen failure evidence.

**Rehearsal/Simulation Boundary:** Tests and local PostgreSQL only; zero exchange
write.

**Tests:** Run the focused modules above and preserve the exact expected RED
assertions in the task record.

**Done When:** All six positive defect reproductions and negative safety cases
fail for the intended reason, not because of fixture or schema breakage.

**Hard Stop:** Any test path that calls a real exchange, reads repo/output
runtime artifacts, or changes strategy policy.

### RNR-T01 — Migration 139 And Static Exit Reference Snapshot

**Task ID:** RNR-T01

**Goal:** Freeze every policy-required static reference from exact Ticket-bound
signal lineage before live submit.

**Why:** opening_range_high already exists in the exact signal payload, but the
current exit policy expects it later inside a dynamic candle fact that does not
own it.

**Allowed files:**

- migrations/versions/2026-07-19-139_close_ticket_exit_runner.py;
- src/domain/ticket_exit_policy.py;
- src/application/action_time/ticket_exit_policy_binding.py;
- src/application/action_time/ticket_exit_execution_binding.py;
- src/application/action_time/ticket_exit_policy_projection.py;
- src/application/action_time/fact_snapshots.py only if exact signal payload
  reading requires a typed current interface;
- tests/unit/test_ticket_exit_policy.py;
- tests/unit/test_ticket_exit_policy_binding.py;
- tests/unit/test_ticket_exit_execution_binding.py;
- tests/unit/test_ticket_exit_policy_projection.py;
- tests/unit/test_ticket_exit_policy_migration.py;
- tests/unit/lifecycle_test_schema.py.

**Forbidden files:**

- strategy detectors and policy parameter definitions;
- exchange_gateway.py;
- lifecycle command worker;
- systemd units;
- output/**.

**Requirements:**

1. Add TicketExitReferenceSnapshot and TicketExitReferenceValue typed models.
2. Require exact ticket_id, signal_event_id, StrategyGroup, strategy version,
   Event Spec/version, instrument, side and reference key identity.
3. Store Decimal values canonically and compute a deterministic SHA-256 hash.
4. Bind current SOR-LONG opening_range_high from the exact signal payload.
5. Make repeated identical binding idempotent.
6. Make a different source/value for the same Ticket a hard contradiction.
7. Fail live-submit readiness before FinalGate when a required reference is
   absent, invalid or mismatched.
8. Do not duplicate the snapshot into every dynamic market fact.
9. Keep old rows readable; bind an active historical row only through exact
   source evidence.

**Global Authority Model:** Reference binding proves semantic input. It does not
authorize a Ticket, allocate capital or call the exchange.

**Chain Position:**

~~~text
stage: action_time_ticket_exit_binding
first_blocker: required_fact_mapping_incomplete
~~~

**Live Enablement State Before:** A Ticket can reach execution binding without
an immutable exit invalidation reference snapshot.

**Live Enablement State After:** Every newly executable versioned Ticket has one
hash-bound static reference snapshot or an exact fail-closed blocker.

**Blocker Removed Or Reclassified:** static_reference_handoff_missing is removed;
missing exact source becomes execution_gate_required_fact_missing.

**Per-Symbol / Per-Fact Acceptance:** Long and short fixtures must bind distinct
reference keys without symbol-specific branching. Missing, zero, non-finite and
wrong-instrument values fail.

**Stop Condition:** Stop before deployment if any active Ticket cannot be bound
from exact immutable lineage.

**Capability Unlocked:** Runner and invalidation evaluation can consume stable
Ticket truth independent of candle facts.

**Rehearsal/Simulation Boundary:** Local PG binding only; zero exchange write.

**Tests:** Migration upgrade/downgrade, typed model, identity mismatch, hash
contradiction, idempotency and producer-to-consumer binding tests.

**Done When:** Migration 139 and binding tests are GREEN and no live-submit path
can proceed with an unbound required reference.

**Hard Stop:** Hard-coded SOR-only aliases in shared application code or later
recomputation of the opening range from unrelated candles.

### RNR-T02 — Lifecycle Due-Fact Scheduling

**Task ID:** RNR-T02

**Goal:** Invoke the existing ticket_exit_market fact producer from the
production lifecycle cadence only when a closed-candle fact is due.

**Why:** The producer exists and passes isolated tests, but Tokyo lifecycle
cadence never calls it, so production PG contains zero ticket_exit_market facts.

**Allowed files:**

- src/application/action_time/lifecycle_maintenance_scheduler.py;
- src/application/action_time/lifecycle_maintenance_service.py;
- src/application/action_time/ticket_exit_market_fact_service.py;
- scripts/run_ticket_bound_lifecycle_maintenance_once.py;
- scripts/verify_tokyo_runtime_governance_postdeploy.py;
- scripts/ops/check_tokyo_runtime_ops_health_once.py;
- tests/unit/test_ticket_bound_lifecycle_scheduler.py;
- tests/unit/test_ticket_bound_lifecycle_maintenance_service.py;
- tests/unit/test_ticket_bound_lifecycle_global_deadline.py;
- tests/unit/test_ticket_exit_market_fact_service.py;
- tests/unit/test_ticket_bound_production_lifecycle_certification.py;
- tests/unit/test_tokyo_runtime_ops_health_lifecycle.py.

**Forbidden files:**

- deploy/systemd/brc-ticket-lifecycle-maintenance.timer cadence changes;
- a new service, daemon, thread or timer;
- exchange command domain semantics;
- strategy policy values;
- output/**.

**Requirements:**

1. Select bounded due Ticket/instrument/timeframe groups from PG.
2. Exit before gateway/public client construction when no lifecycle or pending
   command exists.
3. Perform zero candle request when no fact is due.
4. Fetch one bounded closed-candle window per unique venue/instrument/timeframe
   group when due.
5. Keep candle and exchange reads outside PG transactions.
6. Persist one immutable fact per Ticket and closed-candle watermark.
7. Keep retry state in PG when the source is unavailable or stale.
8. Respect the existing 28-second global deadline and five-second candle
   timeout.
9. Create zero recurring files and zero no-op trace rows.
10. Leave command dispatch count at at most one per invocation.

**Global Authority Model:** The scheduler may materialize read facts. It may not
convert a fact into exchange authority outside the normal Ticket state machine.

**Chain Position:**

~~~text
stage: active_ticket_exit_observation
first_blocker: watcher_tick_missing_for_ticket_exit_market
~~~

**Live Enablement State Before:** Due Runner policies have no production fact
producer invocation.

**Live Enablement State After:** Every due protected Ticket obtains one fresh
closed-candle fact or one exact fact-source blocker.

**Blocker Removed Or Reclassified:** ticket_exit_market_fact_missing becomes
computed fact, source_unavailable or stale_source with retry timing.

**Per-Symbol / Per-Fact Acceptance:** Multiple Tickets sharing one canonical
instrument/timeframe reuse one network fetch while persisting distinct
Ticket-bound facts.

**Stop Condition:** Stop if the only implementation requires a second cadence
owner or holds a PG transaction during network I/O.

**Capability Unlocked:** Production Runner, invalidation and time-stop rules can
receive due market facts.

**Rehearsal/Simulation Boundary:** Read-only public candle fetch plus local PG;
no exchange mutation.

**Tests:** No-active, not-due, due, grouped fetch, timeout, stale, duplicate,
restart, global deadline and zero-file tests.

**Done When:** A production-shaped lifecycle tick creates the expected PG fact
from a due scope and a no-active tick creates no network calls or files.

**Hard Stop:** Any per-position sleep, background task surviving process exit,
new systemd unit or file watermark.

### RNR-T03 — Reference-Aware Runner Evaluation

**Task ID:** RNR-T03

**Goal:** Evaluate structural Runner, invalidation and time stop from dynamic
closed-candle facts plus the immutable Ticket reference snapshot.

**Why:** Scheduling alone is insufficient because the current consumer rejects
dynamic facts that do not contain static strategy references.

**Allowed files:**

- src/domain/ticket_exit_policy.py;
- src/application/action_time/ticket_exit_policy_service.py;
- src/application/action_time/ticket_exit_policy_projection.py;
- tests/unit/test_ticket_exit_policy.py;
- tests/unit/test_ticket_exit_policy_service.py;
- tests/unit/test_ticket_exit_policy_projection.py;
- tests/unit/test_ticket_exit_policy_full_chain.py.

**Forbidden files:**

- signal detector policy generation;
- market fact writer ownership;
- exchange gateway and command worker;
- systemd;
- output/**.

**Requirements:**

1. Load static reference values from the Ticket snapshot and candles from the
   latest valid ticket_exit_market fact.
2. Reject identity, schema, hash, timeframe, watermark or freshness mismatch.
3. Use only final closed candles.
4. Compute ATR and structure with Decimal.
5. Apply long and short direction-aware invalidation.
6. Count time stop from the exact Ticket policy anchor and closed-candle
   watermark without double counting duplicate facts.
7. Apply break-even floor independently of public-candle availability after
   TP1 completion.
8. Enforce tick alignment, monotonic movement and minimum improvement.
9. Return explicit NOOP when a computed candidate is not sufficiently better.
10. Keep evaluation pure with respect to exchange I/O.

**Global Authority Model:** Evaluation may propose a transition. Only the
durable command authority may perform exchange mutation.

**Chain Position:**

~~~text
stage: exit_policy_evaluation
first_blocker: required_fact_consumer_contract_mismatch
~~~

**Live Enablement State Before:** Valid dynamic facts are discarded because
they do not duplicate static reference data.

**Live Enablement State After:** Static and dynamic facts have separate owners
and combine deterministically at evaluation time.

**Blocker Removed Or Reclassified:** ticket_exit_market_fact_missing is no
longer emitted for a valid dynamic fact with a valid bound reference.

**Per-Symbol / Per-Fact Acceptance:** Test long and short, multiple tick sizes,
stale facts, non-final candles, wrong instrument, adverse candidate, exact
two-tick improvement and 96-bar time stop.

**Stop Condition:** Stop if any evaluator branch reaches the exchange or infers
a static reference from symbol/StrategyGroup constants.

**Capability Unlocked:** Correct Runner and final-exit decision production.

**Rehearsal/Simulation Boundary:** Pure domain and local PG decision tests only.

**Tests:** Focused domain tests plus a producer-to-binder-to-fact-to-decision
full-chain fixture.

**Done When:** Valid facts produce exact NOOP, runner_replace or final_exit
decisions and all identity/freshness negatives fail closed.

**Hard Stop:** float financial math, unversioned strategy aliases or stale
market facts producing a mutation intent.

### RNR-T04 — Unified TP1 Completion Reducer

**Task ID:** RNR-T04

**Goal:** Make one pure reducer the only TP1 completion authority across fill
projection, protection reconciliation and exit policy.

**Why:** Current services can disagree about whether any partial TP1 fill means
complete TP1, especially across replacement generations.

**Allowed files:**

- one new pure domain module under src/domain/ for TP1 completion;
- src/application/action_time/ticket_bound_fill_projector.py;
- src/application/action_time/protection_reconciler.py;
- src/application/action_time/ticket_exit_policy_service.py;
- src/application/action_time/post_submit_reconciliation_tick.py;
- tests/unit/test_ticket_bound_fill_projector.py;
- tests/unit/test_ticket_bound_protection_reconciler.py;
- tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py;
- tests/unit/test_ticket_exit_policy_service.py;
- one new focused reducer test module.

**Forbidden files:**

- exchange gateway;
- strategy policy parameters;
- scheduler cadence;
- migration other than fields already approved in 139;
- output/**.

**Requirements:**

1. Input frozen target quantity, tolerance, all distinct TP1 fill events,
   current position quantity and order terminal states.
2. Output unfilled, partial_open, partial_cancelled, complete or contradictory.
3. Deduplicate by exchange_trade_id, then exact order/trade identity, then a
   deterministic fallback.
4. Accumulate fills across all TP1 generations.
5. Never reset progress when a replacement receives a new exchange_order_id.
6. Require remaining-position agreement and synchronized stop quantity before
   entering TP1 complete.
7. Preserve entry quantity and frozen target as immutable authority.
8. Make all three consumers use the reducer result instead of local heuristics.

**Global Authority Model:** Fill facts and completion status do not create order
authority.

**Chain Position:**

~~~text
stage: tp1_fill_projection
first_blocker: lifecycle_projection_inconsistent
~~~

**Live Enablement State Before:** TP1 completion can differ by service and order
generation.

**Live Enablement State After:** One cumulative state determines protection
resize, floor activation and reprice behavior.

**Blocker Removed Or Reclassified:** partial-fill ambiguity becomes one explicit
partial or contradictory state.

**Per-Symbol / Per-Fact Acceptance:** Long/short and venue-neutral quantity
fixtures; duplicate trades, late fills, two generations, tolerance boundary
and position disagreement.

**Stop Condition:** Stop if any consumer still has an independent any-fill
equals-complete predicate.

**Capability Unlocked:** Safe residual TP1 handling and one-time Runner floor
activation.

**Rehearsal/Simulation Boundary:** Pure reducer and local projection tests.

**Tests:** Unit, PostgreSQL fixture and restart/idempotency tests.

**Done When:** Fill projector, reconciler and policy service produce identical
TP1 state for the same event set.

**Hard Stop:** Quantity accumulation using float or order-id-only identity that
loses cross-generation fills.

### RNR-T05 — TP1 Cancel/Reprice Partial-Fill Residual

**Task ID:** RNR-T05

**Goal:** Preserve the approved total TP1 target through cancel/reprice races by
submitting only the unfilled residual quantity.

**Why:** A TP1 may fill while cancellation is in progress. Reusing the original
quantity can over-reduce; treating any fill as complete can under-execute the
policy; leaving no replacement can wedge the lifecycle.

**Allowed files:**

- src/application/action_time/ticket_exit_policy_service.py;
- src/application/action_time/lifecycle_exchange_command_completion.py;
- src/application/action_time/lifecycle_exchange_command_materializer.py;
- src/application/action_time/lifecycle_maintenance_service.py;
- src/domain/ticket_bound_exchange_command.py only for deterministic source
  invariants already approved by migration 139;
- tests/unit/test_ticket_exit_policy_tp1_reprice.py;
- tests/unit/test_ticket_exit_policy_service.py;
- tests/unit/test_ticket_bound_exchange_command_materialization.py;
- tests/unit/test_ticket_bound_lifecycle_maintenance_service.py.

**Forbidden files:**

- TP1 reward multiple, target fraction, order type or market fallback policy;
- exchange gateway unless an existing typed amount is proven to be dropped;
- scheduler timer;
- output/**.

**Requirements:**

1. After confirmed cancel, recompute cumulative fills across all generations.
2. Resize active SL/RUNNER_SL to current remaining position before improving
   the stop or placing another TP1.
3. Compute residual = frozen_target - cumulative_fill.
4. Round residual down to venue quantity step.
5. Treat residual within tolerance as complete.
6. Otherwise prepare a LIMIT GTC replacement for residual only at the frozen
   TP1 price.
7. Keep market fallback forbidden.
8. Never place the replacement while cancel is outcome_unknown.
9. Never leave a stable state with no live TP1 and residual above tolerance.
10. Make command ids deterministic across restart.

**Global Authority Model:** Uses the existing lifecycle command authority only;
no direct exchange calls.

**Chain Position:**

~~~text
stage: tp1_cancel_reprice
first_blocker: lifecycle_partial_fill_race
~~~

**Live Enablement State Before:** Partial cancel/reprice can lose or duplicate
the target quantity.

**Live Enablement State After:** Total TP1 target is conserved exactly across
order generations.

**Blocker Removed Or Reclassified:** tp1_reprice_required advances to residual
replacement, completion or exact unknown/rejection blocker.

**Per-Symbol / Per-Fact Acceptance:** Quantity-step variants, partial fill
before cancel, during cancel, after cancel observation, completion tolerance
and current-position contradiction.

**Stop Condition:** Stop on unknown cancel, position disagreement, missing fill
identity or residual greater than current remaining position.

**Capability Unlocked:** TP1 can safely reach completion despite venue races.

**Rehearsal/Simulation Boundary:** Command preparation and fake worker only;
zero real exchange write.

**Tests:** Extend existing TP1 reprice tests with every race and restart point.

**Done When:** No tested race over-reduces, under-targets, duplicates a command
or leaves an unprotected/wedged partial state.

**Hard Stop:** Re-submitting full original quantity after a partial fill or
enabling market fallback.

### RNR-T06 — Runner Replacement Reliability

**Task ID:** RNR-T06

**Goal:** Make every floor or structural stop improvement follow confirmed
place-new-before-cancel-old semantics with exact generation reconciliation.

**Why:** Moving stop is a multi-command safety transition. A direct replace or
cancel-first sequence creates an unprotected interval and unknown-outcome
duplicate risk.

**Allowed files:**

- src/application/action_time/ticket_exit_policy_service.py;
- src/application/action_time/ticket_exit_policy_projection.py;
- src/application/action_time/runner_protection_adjuster.py;
- src/application/action_time/runner_mutation_command.py;
- src/application/action_time/lifecycle_exchange_command_materializer.py;
- src/application/action_time/lifecycle_exchange_command_completion.py;
- src/application/action_time/exchange_command_reconciliation.py;
- src/application/action_time/protection_reconciler.py;
- tests/unit/test_ticket_exit_policy_service.py;
- tests/unit/test_ticket_bound_runner_protection_adjuster.py;
- tests/unit/test_ticket_bound_runner_mutation_command.py;
- tests/unit/test_ticket_bound_exchange_command_reconciliation.py;
- tests/unit/test_ticket_bound_protection_reconciler.py.

**Forbidden files:**

- new exchange writer or Runner executor authority;
- cancel-first replacement;
- policy formula or minimum-tick changes;
- systemd;
- output/**.

**Requirements:**

1. Freeze proposed price, quantity, old generation and new generation in one
   deterministic decision.
2. Place the new reduce-intent RUNNER_SL through the durable command worker.
3. Keep the old stop when placement is rejected or outcome_unknown.
4. Reconcile exact side, positionSide, instrument, quantity and trigger price.
5. Prepare old-stop cancellation only after new-stop acceptance is proven.
6. If cancel is unknown, retain both identities, freeze the netting domain and
   reconcile.
7. Advance active_runner_generation only after new live and old terminal truth.
8. Make duplicate facts/restarts idempotent.
9. Never move stop adversely or by less than the policy minimum.
10. Synchronize protection quantity before price improvement.

**Global Authority Model:** Evaluator proposes; durable command worker writes;
reconciler proves; projection advances. No lower layer upgrades authority.

**Chain Position:**

~~~text
stage: runner_protection_replacement
first_blocker: event_execution_capability_not_certified
~~~

**Live Enablement State Before:** Helper behavior exists, but the full
generation transition is not certified against the new fact and TP1 model.

**Live Enablement State After:** Every stop move is monotonic, protected,
idempotent and exact-order reconciled.

**Blocker Removed Or Reclassified:** runner_replacement_not_certified becomes
runner_protected, outcome_unknown or exact rejection blocker.

**Per-Symbol / Per-Fact Acceptance:** Long and short, hedge positionSide,
different price ticks, partial position quantity, duplicate fact, restart after
every command state and two consecutive improvements.

**Stop Condition:** Stop on missing protection, unknown place/cancel result,
wrong position bucket, adverse price or quantity mismatch.

**Capability Unlocked:** Immediate break-even floor and later structural
trailing can safely reach the venue.

**Rehearsal/Simulation Boundary:** Local fake gateway and PostgreSQL command
worker only until T10.

**Tests:** Pure decision, command sequence, fake gateway, reconciliation,
restart and unknown-outcome tests.

**Done When:** No path cancels the old stop before confirmed replacement and
generation advances exactly once.

**Hard Stop:** Direct evaluator gateway call, second writer or cancellation of
the only known protection on ambiguous placement.

### RNR-T07 — First-Class FINAL_EXIT Lineage

**Task ID:** RNR-T07

**Goal:** Represent invalidation and time-stop closes as exact Ticket-owned
FINAL_EXIT commands, orders and fills.

**Why:** The current normal strategy close can be inferred as EXTERNAL_CLOSE,
which loses command ownership and weakens deterministic cleanup and review.

**Allowed files:**

- migrations/versions/2026-07-19-139_close_ticket_exit_runner.py;
- src/domain/ticket_bound_exchange_command.py;
- src/application/action_time/ticket_exit_policy_service.py;
- src/application/action_time/lifecycle_exchange_command_materializer.py;
- src/application/action_time/lifecycle_exchange_command_completion.py;
- src/application/action_time/ticket_bound_fill_projector.py;
- src/application/action_time/post_submit_closure.py;
- src/application/action_time/ticket_bound_lifecycle_finalizer.py;
- src/application/action_time/protection_reconciler.py;
- src/application/action_time/account_exchange_ownership.py;
- src/infrastructure/exchange_gateway.py only if Codex proves the existing
  reduce-intent market path cannot carry the explicit role;
- tests/unit/test_ticket_bound_exchange_command.py;
- tests/unit/test_ticket_bound_exchange_command_materialization.py;
- tests/unit/test_ticket_bound_fill_projector.py;
- tests/unit/test_ticket_bound_lifecycle_finalizer.py;
- tests/unit/test_ticket_exit_policy_full_chain.py.

**Forbidden files:**

- entry submit or sizing logic;
- external close attribution for genuine manual/exchange-side closes except to
  exclude command-owned FINAL_EXIT;
- monitor-created close decisions;
- output/**.

**Requirements:**

1. Add FINAL_EXIT to exact schema/domain role constraints.
2. Prepare only from a valid versioned invalidation or time-stop decision.
3. Use exact current remaining position quantity and close side.
4. Preserve hedge positionSide and reduce intent.
5. Use deterministic client order id and existing command worker.
6. Keep active SL/RUNNER_SL protection until final fill proves position flat.
7. On outcome_unknown, freeze exact scope and reconcile by client order id.
8. Project fills by command, local order, client order, exchange order and
   trade identities.
9. Reserve EXTERNAL_CLOSE for genuinely non-command-owned close truth.
10. Trigger cleanup only after authoritative flat confirmation.

**Global Authority Model:** FINAL_EXIT is an order role, not new authority. It
still requires existing Ticket policy, current facts, runtime safety and the
official lifecycle command path.

**Chain Position:**

~~~text
stage: strategy_final_exit
first_blocker: final_exit_lineage_missing
~~~

**Live Enablement State Before:** A normal strategy exit may appear as an
external/manual close.

**Live Enablement State After:** Strategy final exit has exact durable command,
order, fill, cleanup and review lineage.

**Blocker Removed Or Reclassified:** external_close_inference_gap is removed;
unknown or rejected writes remain explicit safety blockers.

**Per-Symbol / Per-Fact Acceptance:** Long/short, invalidation/time-stop,
positionSide, partial final fill, unknown then found, duplicate journal fill and
genuine external close negative case.

**Stop Condition:** Stop on stale/non-final fact, unbound reference, current
quantity contradiction, unknown prior final command or missing active
protection.

**Capability Unlocked:** Deterministic strategy-driven terminal exit.

**Rehearsal/Simulation Boundary:** Fake gateway through T09. Real command only
after T10 deployment and a naturally eligible Ticket.

**Tests:** Schema, domain, worker, fill, closure and restart full-chain tests.

**Done When:** Every normal invalidation/time-stop exit remains FINAL_EXIT from
decision through review and cannot be mislabelled EXTERNAL_CLOSE.

**Hard Stop:** Duplicate market close, monitor/replay authority or cancelling
protection before flat truth.

### RNR-T08 — Terminal Projection And Exact Historical Repair

**Task ID:** RNR-T08

**Goal:** Make flat reconciled position truth terminalize
brc_ticket_exit_policy_current and repair only provably closed historical rows.

**Why:** A lifecycle may close while the exit-policy current projection still
shows active quantity, Runner generation or blocker state.

**Allowed files:**

- src/application/action_time/ticket_exit_policy_projection.py;
- src/application/action_time/post_submit_closure.py;
- src/application/action_time/ticket_bound_lifecycle_finalizer.py;
- src/application/action_time/lifecycle_exchange_command_completion.py;
- scripts/repair_terminal_ticket_exit_policy_current.py if a bounded manual PG
  repair is required;
- scripts/verify_tokyo_runtime_governance_postdeploy.py;
- tests/unit/test_ticket_exit_policy_projection.py;
- tests/unit/test_ticket_bound_lifecycle_finalizer.py;
- tests/unit/test_ticket_exit_policy_full_chain.py;
- one focused repair test module.

**Forbidden files:**

- destructive migration or deletion of history;
- exchange writes from the repair;
- blanket update based on age alone;
- output/report files.

**Requirements:**

1. Terminalize only after authoritative position-flat and closure evidence.
2. Preserve terminal TP1 truth and immutable audit lineage.
3. Clear current active/pending/replaced Runner identities and blocker.
4. Set state=terminal and terminal_at_ms exactly once.
5. Refuse repair when a prepared, dispatching or unknown command exists.
6. Refuse repair when exchange/account or lifecycle identity is contradictory.
7. Make the manual repair idempotent, PG-only and dry-run by default.
8. Do not delete historical facts, commands, fills, orders, reviews or
   lifecycle events.

**Global Authority Model:** Terminal projection records truth. It creates no
trade or cleanup authority beyond already reconciled commands.

**Chain Position:**

~~~text
stage: lifecycle_terminal_projection
first_blocker: current_projection_stale
~~~

**Live Enablement State Before:** Closed lifecycle truth can coexist with an
apparently active exit-policy row.

**Live Enablement State After:** Terminal current state agrees with closure,
settlement and review truth.

**Blocker Removed Or Reclassified:** stale active current projection is removed;
ambiguous rows remain explicitly blocked for reconciliation.

**Per-Symbol / Per-Fact Acceptance:** Ordinary SL, RUNNER_SL, FINAL_EXIT and
genuine EXTERNAL_CLOSE terminal paths; open position and unknown-command
negative cases.

**Stop Condition:** Stop repair on any non-flat, unresolved, missing-identity or
contradictory row.

**Capability Unlocked:** Accurate Owner status, occupancy, lifecycle closure and
future lane admission.

**Rehearsal/Simulation Boundary:** PG-only local and read-only Tokyo preview
before any bounded repair apply.

**Tests:** Idempotency, exact eligibility, negative rows, terminal field
clearing and no-history-deletion tests.

**Done When:** New closures terminalize automatically and an exact historical
preview identifies only provably eligible rows.

**Hard Stop:** Broad UPDATE, time-based inference, exchange mutation or history
deletion.

### RNR-T09 — Local PostgreSQL And Full-Chain Certification

**Task ID:** RNR-T09

**Goal:** Certify the integrated design from signal-bound reference through
terminal lifecycle against disposable PostgreSQL and a fake exchange.

**Why:** Individual GREEN modules do not prove transaction boundaries,
cross-service state ownership, restart safety or negative cases.

**Allowed files:**

- focused tests from T00-T08;
- tests/unit/test_ticket_exit_policy_full_chain.py;
- tests/unit/test_ticket_bound_production_lifecycle_certification.py;
- scripts/run_ticket_bound_lifecycle_full_chain_simulation.py only if it remains
  stdout-only and uses typed in-memory/PG inputs;
- scripts/verify_ticket_lifecycle_phase_two_readiness.py;
- scripts/validate_current_docs_authority.py;
- scripts/audit_production_runtime_file_io.py.

**Forbidden files:**

- production exchange credentials;
- live systemd state;
- generated evidence/report files;
- policy changes made only to make tests pass.

**Requirements:**

1. Apply migrations 1 through 139 to disposable PostgreSQL.
2. Exercise exact bound signal reference and due closed-candle producer.
3. Exercise TP1 unfilled, partial, cross-generation complete and reprice races.
4. Exercise immediate floor and two structural improvements.
5. Exercise invalidation and 96-bar time stop FINAL_EXIT.
6. Restart after every durable command state.
7. Exercise place, cancel and final-exit unknown outcomes.
8. Prove all network calls occur outside PG transactions.
9. Prove no-active/no-due ticks create zero calls, rows and files beyond bounded
   PG selection.
10. Run focused, lifecycle-wide and full test suites plus file-I/O audit.

**Global Authority Model:** Simulation may unlock engineering capability but
does not grant live-submit or production exchange-write authority.

**Chain Position:**

~~~text
stage: production_shaped_certification
first_blocker: event_execution_capability_not_certified
~~~

**Live Enablement State Before:** Components are implemented but not integrated
and certified.

**Live Enablement State After:** The full chain has deterministic positive and
negative proof under production-shaped persistence and restart behavior.

**Blocker Removed Or Reclassified:** event_execution_capability_not_certified
becomes deployable_engineering_capability_ready.

**Per-Symbol / Per-Fact Acceptance:** Long/short, two canonical instruments,
different tick/step sizes and exact venue identity.

**Stop Condition:** Stop release preparation on any duplicate command, missing
protection, network-in-transaction, stale fact mutation, file growth or
projection disagreement.

**Capability Unlocked:** Bounded Tokyo deployment.

**Rehearsal/Simulation Boundary:** Entire task is non-live.

**Tests:**

~~~text
focused RED/GREEN modules
-> lifecycle regression suite
-> disposable PostgreSQL migrations
-> full-chain simulation
-> validate_current_docs_authority.py
-> audit_production_runtime_file_io.py --json
-> validate_output_artifact_scope.py --git-status --git-tracked
-> git diff --check
~~~

**Done When:** All tests pass, performance_risk.status is clear, no output
artifact is tracked and every acceptance scenario has deterministic PG truth.

**Hard Stop:** Waiving a negative safety case because no natural market signal
exists.

### RNR-T10 — Tokyo Deployment And Bounded Canary

**Task ID:** RNR-T10

**Goal:** Deploy the exact certified release and prove scheduler, schema,
read-only facts and lifecycle safety on Tokyo without forcing a market event.

**Why:** Production cadence and machine configuration are part of the defect.
Local tests cannot certify systemd identity, PG migration or real network
boundaries.

**Allowed files and surfaces:**

- deploy/systemd existing lifecycle service/timer only if T09 proves a bounded
  environment or timeout correction is required;
- scripts/verify_tokyo_runtime_governance_postdeploy.py;
- scripts/ops/check_tokyo_runtime_ops_health_once.py;
- Tokyo release directory and additive migration 139;
- read-only PG, exchange/account and journal checks;
- existing official lifecycle deployment commands.

**Forbidden actions:**

- forced order, synthetic live signal or manual position creation;
- profile, capital, leverage, notional, symbol or side expansion;
- credential mutation;
- destructive PG cleanup;
- disabling active exchange protection;
- a new Runner service or timer.

**Requirements:**

1. Recheck active positions, protection orders and unresolved commands before
   maintenance.
2. Quiesce watcher and lifecycle mutation units only for the bounded deploy
   window.
3. Deploy exact release identity and apply migration 139.
4. Bind/backfill static references only for exact eligible active Tickets.
5. Run a no-write due-scope and reference probe.
6. Restore lifecycle timer and verify 30-second cadence.
7. If no active Ticket exists, prove zero public/exchange calls and zero files.
8. If an active protected Ticket exists, keep protection live and allow only
   normal due fact/reconciliation work.
9. Restore watcher and verify Owner read models and monitor wording.
10. Archive no recurring JSON/Markdown evidence; use PG and journal as runtime
    proof.

**Global Authority Model:** Standing authorization covers bounded deploy and
normal in-boundary lifecycle work. It does not authorize a forced test trade.

**Chain Position:**

~~~text
stage: tokyo_runtime_deployment
first_blocker: deploy_certification_pending
~~~

**Live Enablement State Before:** Capability is locally certified but absent
from production.

**Live Enablement State After:** Tokyo runs the exact release/schema with one
scheduler and one writer; no-active or active-protected canary is clear.

**Blocker Removed Or Reclassified:** deploy_certification_pending becomes
market_wait_validated only if all other lane conditions are truly closed.

**Per-Symbol / Per-Fact Acceptance:** Verify exact active canonical instruments;
do not expand scope to manufacture coverage.

**Stop Condition:** Abort or freeze mutation on unresolved command, missing
protection, schema mismatch, wrong release identity, stale reference, repeated
worker failure or transaction timeout.

**Capability Unlocked:** Natural live Ticket can exercise the repaired chain.

**Rehearsal/Simulation Boundary:** No forced trade. Existing active Ticket may
continue only through normal official authority.

**Tests:** Postdeploy verifier, ops health, systemd status/journal, PG schema and
current rows, file-I/O audit, no-active or active-protected canary.

**Done When:** Exact HEAD and migration 139 are active, lifecycle timer is
healthy, no second writer exists, production file-I/O is clear and all current
positions remain exactly protected.

**Hard Stop:** Unknown exchange outcome, missing protection, duplicate writer,
wrong account/instrument binding or any required destructive migration.

### RNR-T11 — Natural Real-Ticket Calibration

**Task ID:** RNR-T11

**Goal:** Observe one naturally eligible versioned Ticket through the repaired
exit chain and capture exact live calibration truth.

**Why:** Simulation certifies engineering behavior, but venue acceptance,
real fills, fees, conditional order identities and timing require a natural
live outcome.

**Allowed surfaces:**

- existing watcher, candidate, action-time, FinalGate and Operation Layer;
- existing in-boundary real order action;
- lifecycle worker, command worker, reconciliation, settlement and review;
- read-only PG, exchange and journal forensics.

**Forbidden actions:**

- synthetic signal promotion;
- forced entry or forced TP1/Runner/final-exit market manipulation;
- strategy threshold, leverage, size or scope changes to accelerate the test;
- manual cancellation that changes the normal chain;
- file evidence as runtime authority.

**Requirements:**

1. Wait for a naturally fresh eligible signal under current Owner policy.
2. Prove exact static reference snapshot before live submit.
3. Prove entry and initial exchange-native protection.
4. Observe TP1 fill behavior if market reaches the limit.
5. Prove protection quantity synchronization after every fill delta.
6. Prove immediate floor after full TP1 target completion.
7. Prove due 15m fact and monotonic Runner generation when market structure
   permits.
8. Prove FINAL_EXIT lineage if invalidation/time stop occurs; ordinary SL or
   Runner stop remains a valid real terminal outcome.
9. Prove cleanup, settlement, review and terminal current projection.
10. Record negative evidence honestly if the natural outcome does not exercise
    every branch.

**Global Authority Model:** This task uses only current Owner-approved strategy
and normal runtime authority. No new confirmation is inserted per order.

**Chain Position:**

~~~text
stage: live_outcome_calibration
first_blocker: fresh_signal_absent only when market_wait_validated is proven
owner_action_required: false during normal bounded operation
~~~

**Live Enablement State Before:** Production capability is deployed but lacks a
natural live outcome for the new versioned path.

**Live Enablement State After:** One exact live lifecycle outcome calibrates
venue behavior; unexercised branches remain simulation-certified, not falsely
claimed as live-certified.

**Blocker Removed Or Reclassified:** live_outcome_calibration_pending is removed
only for branches actually observed.

**Per-Symbol / Per-Fact Acceptance:** Accept the first naturally eligible
current-scope Ticket. Do not choose a symbol by engineering convenience.

**Stop Condition:** Stop mutation on any standard hard-safety blocker. Continue
read-only observation when no natural signal or no applicable exit branch
occurs.

**Capability Unlocked:** Production lifecycle closure can be reported as
live-calibrated for the observed branch set.

**Rehearsal/Simulation Boundary:** Real exchange actions occur only through the
official path after all normal gates pass.

**Tests:** Exact PG command/order/fill/reconciliation/settlement lineage,
exchange readback and journal cadence evidence.

**Done When:** One natural Ticket reaches a safe terminal outcome with exact
lineage and no duplicate, stale-fact action, missing protection or manual
operation.

**Hard Stop:** Any proposal to force market conditions or weaken policy/safety
in order to finish calibration.

## 9. Integrated Acceptance Matrix

| Scenario | Fact/input proof | Required mutation sequence | Required terminal/current result |
| --- | --- | --- | --- |
| TP1 never fills, SL fills | bound reference; live SL | no Runner command | closed_by_sl; exit projection terminal |
| TP1 partial and remains open | distinct fill delta | resize protection only | partial_open; TP1 remainder live |
| TP1 partial during reprice | cumulative multi-generation fills | cancel confirmed; residual LIMIT GTC only | exact target conserved |
| TP1 completes | reducer target and position agree | floor stop place then old stop cancel | runner_protected once |
| Structure improves twice | two fresh final 15m facts | two monotonic place-before-cancel generations | generation increments exactly twice |
| Candidate improves less than two ticks | valid computed fact | none | NOOP; old protection retained |
| Invalidation fires | bound reference plus final closed candle | FINAL_EXIT command; cleanup after flat | closed_by_final_exit; terminal |
| 96-bar time stop | exact nonduplicate watermark count | FINAL_EXIT command; cleanup after flat | closed_by_final_exit; terminal |
| Runner place unknown | valid decision, ambiguous write | no old-stop cancel | domain frozen; old protection visible |
| FINAL_EXIT unknown then found | deterministic client order id | no duplicate close | exact fill lineage; terminal |
| Position flat with live protection | exchange flat plus linked orders | exact orphan cancels | no live linked orders; terminal |
| Genuine manual/exchange close | no owned command/order match | attribution only | EXTERNAL_CLOSE preserved |
| No active lifecycle | no due scopes or commands | none | zero network calls, rows and files |

## 10. Test Commands And Evidence Rules

The exact commands may be adjusted to the current test environment, but the
acceptance set must include:

~~~text
pytest focused Ticket exit and lifecycle modules
pytest lifecycle-wide regression modules
pytest disposable-PostgreSQL migration and integration modules
python3 scripts/run_ticket_bound_lifecycle_full_chain_simulation.py
python3 scripts/verify_ticket_lifecycle_phase_two_readiness.py
python3 scripts/validate_current_docs_authority.py
python3 scripts/audit_production_runtime_file_io.py --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
~~~

Evidence rules:

- machine truth comes from current code, PG, exchange readback, systemd and
  journal;
- stdout may summarize but does not become runtime authority;
- no generated JSON/Markdown evidence is committed;
- output/** remains untracked and excluded;
- performance_risk.status must be clear before production cadence acceptance;
- every skipped test must be classified and resolved before T10.

## 11. Deployment Gates

| Gate | Pass condition | Failure action |
| --- | --- | --- |
| Design authority | Owner confirms design and plan | no implementation |
| Git baseline | exact reviewed branch and commit history | stop and reconcile |
| Schema | migration 139 upgrade proven | no deploy |
| Tests | focused, regression and PostgreSQL suites GREEN | no deploy |
| File I/O | performance_risk.status=clear; zero recurring files | no deploy |
| Runtime truth | no unresolved unknown command | freeze mutation |
| Protection | every active position has exact exchange-native protection | stop deployment |
| Release identity | manifest, code and service bind exact target HEAD | rollback/quiesce |
| Canary | no-active or active-protected checks clear | keep watcher/mutation bounded |

## 12. Rollback Execution

Rollback is code-first and protection-preserving:

1. stop new lifecycle mutation claims;
2. inspect every prepared, dispatching and outcome_unknown command;
3. reconcile exact client/exchange order ids;
4. prove every non-flat position retains active exchange-native protection;
5. stop lifecycle timer only for the bounded switch;
6. restore predecessor release identity;
7. leave additive migration 139 in place unless downgrade has been explicitly
   proven safe;
8. disable new fact/FINAL_EXIT decision production through current capability
   state, not by deleting rows;
9. restore predecessor lifecycle reconciliation;
10. recheck positions, open orders, PG current state, journal and Owner status.

Rollback stops if a Runner or FINAL_EXIT result is unknown. The system must
first resolve exchange truth and may not submit a duplicate or cancel the only
known protection.

## 13. Program Completion Definition

This program is complete only when:

1. Runner remains part of the existing 30-second lifecycle oneshot and no
   independent Runner thread/service exists.
2. Every newly executable Ticket freezes exact policy-required static
   references before live submit.
3. A due active Ticket can create one fresh ticket_exit_market fact from
   production cadence.
4. The evaluator combines static Ticket references and dynamic closed candles
   without duplicating authority.
5. TP1 completion is cumulative and identical across all consumers.
6. Partial cancel/reprice preserves the exact approved TP1 target.
7. Every moving stop is monotonic, tick-valid and placed before old-stop cancel.
8. Invalidation/time-stop close uses FINAL_EXIT exact lineage.
9. Unknown outcomes never cause duplicate Runner or final-exit mutation.
10. Flat truth terminalizes the exit-policy current row and exact cleanup.
11. No-active production ticks create zero exchange/public calls and zero
    runtime files.
12. Tokyo deploy and canary are healthy.
13. Natural live calibration is reported only for branches actually observed.

## 14. Owner Confirmation Scope

Confirmation of this plan authorizes the engineering sequence RNR-T00 through
RNR-T10 on the current focused branch and bounded Tokyo deployment after all
gates pass. RNR-T11 uses only standing normal in-boundary runtime authority and
does not create a forced trade.

Confirmation approves:

- existing 30-second lifecycle scheduler as Runner cadence owner;
- migration 139 additive schema;
- Ticket-bound static reference snapshot;
- one TP1 cumulative reducer;
- residual-only TP1 replacement after partial fill;
- place-new-before-cancel-old Runner transition;
- explicit FINAL_EXIT role;
- exact non-destructive terminal projection repair.

Confirmation does not change:

- StrategyGroup or instrument scope;
- TP1 target, quantity fraction or LIMIT GTC behavior;
- moving-stop formula or minimum improvement;
- leverage, notional, capital or exposure;
- FinalGate, Operation Layer or protection safety boundaries;
- credential, withdrawal or transfer authority.

Until Owner confirms both documents, implementation remains NOT_STARTED,
deployment remains NO_CHANGE and exchange_write remains 0.
