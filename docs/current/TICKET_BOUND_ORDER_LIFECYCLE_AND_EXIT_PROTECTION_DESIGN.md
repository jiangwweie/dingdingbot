---
title: TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN
status: CURRENT_DESIGN
authority: docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md
last_verified: 2026-07-09
---

# Ticket-Bound Order Lifecycle And Exit Protection Design

Last updated: 2026-07-09

## Objective

The target is to close the **ticket-bound order lifecycle** after the current
PG action-time chain:

```text
live_signal_event
-> promotion_candidate
-> action_time_lane_input
-> action_time_ticket
-> FinalGate preflight
-> Operation Layer handoff
-> protected submit attempt
-> entry fill
-> exchange-native reduce-only exit protection
-> reconciliation
-> settlement
-> review
```

This design removes the current gap where an entry can be submitted while
**TP1 / runner / post-fill protection** remains only a semantic preview or
review plan.

## Current Facts

### Code Facts

| Area | Current fact | Risk |
| --- | --- | --- |
| **Ticket-bound submit request** | `protected_submit_attempt._submit_request` now creates **ENTRY + SL + TP1** when TP1 reference exists | Submit request still carries entry and protection orders in one command envelope |
| **Submit timing** | API submit loop sends ticket-bound request orders through the official gateway path | The full target remains an explicit post-fill exit protection owner; this design creates that PG owner |
| **Post-submit closure** | `post_submit_closure` now requires a PG **exit protection set** with **SL + TP1** | Closure is blocked when protection set is missing or incomplete |
| **Exit protection materializer** | `TicketBoundExitProtectionMaterializer` materializes PG lifecycle/protection rows after filled entry proof | It is a PG proof layer over submitted refs; it is not the official mutation owner |
| **Exit plan** | `RuntimePositionExitPlanService` is non-executing review evidence | It cannot materialize protection orders |
| **OrderLifecycleService** | Existing callbacks can react to entry/exit fills | Callback capability is not the ticket-bound mainline owner |
| **Runner protection adjuster** | `TicketBoundRunnerProtectionAdjuster` materializes PG proof after TP1 fill and a replacement runner SL ref | It records proof only after a runner SL exchange ref exists |
| **Runner mutation executor** | `TicketBoundRunnerMutationExecutor` consumes a prepared PG command, cancels the old full-size SL through an injected gateway, submits RUNNER_SL, and records the PG result | It cannot call FinalGate, change profile/sizing, or use repo files as authority |
| **Orphan protection cleanup command** | Deployed migration `098` adds `brc_ticket_bound_orphan_protection_cleanup_commands` and `orphan_protection_cleanup_command` for flat-position live-protection cleanup | It cancels only PG-linked reduce-only protection refs after `position_closed_protection_live`; exchange-only unknown orders remain blocked |
| **Lifecycle closure materializer** | `materialize_ticket_bound_lifecycle_closure` closes PG lifecycle after final exit, reconciliation, settlement, and review proofs | It requires proof IDs and flat-position confirmation; it summarizes closure and does not discover exchange truth by itself |
| **First post-submit reconciliation tick** | Deployed in Tokyo release `4b0b8a27` with `brc_ticket_bound_reconciliation_ticks` | It creates current PG reconciliation state immediately after real protected submit result; disabled smoke creates no first tick |
| **Recovery command matrix** | Deployed in Tokyo release `4b0b8a27` for SL/TP1 degraded recovery, max 3 attempts, and scope freeze writes | Scope freeze rows still need to become pre-submit hard blockers across promotion, lane, ticket, Runtime Safety State, FinalGate preflight, and protected submit |
| **ExchangeGateway** | Existing gateway can place, cancel, and read orders/fills/positions through lifecycle-ready methods | The runner proof layer must not become a second exchange mutation path |
| **Deploy status** | Post-submit first tick and recovery hardening are deployed on Tokyo at `4b0b8a272814b2458fafc1913f8d7c63219ff321` with PG `alembic=101` | Deployment proves code/migration acceptance and post-submit first-tick readiness, not a live market outcome |
| **Impact test** | Active scopes reach mock submitted -> exit protection set -> runner/final closure coverage; deployed tests cover 9 full-chain failure scenarios | Test proves entry-fill + SL/TP1 protection set materialization, runner SL, final closure, and exact lifecycle hard stops |

### Known P0 / P1 Gaps

| Severity | Gap | Why it matters |
| --- | --- | --- |
| **P0** | No **ticket-bound exit protection set** object | Closed by `brc_ticket_bound_exit_protection_sets` |
| **P0** | No **entry fill confirmed** gate before exit protection materialization | Closed by materializer requiring full filled entry status, qty, and average price |
| **P0** | **TP1** is missing from the protected submit / protection closure truth | Closed by TP1 submit request requirement and closure protection-set requirement |
| **P0** | `protection_state=submitted` only requires SL | Closed; it now requires PG protection set completeness |
| **P0** | TP1 fill -> official SL cancel/replace and RUNNER_SL submit is not one closed ticket-bound mutation path | Code-covered and deployed by `runner_mutation_command` and `runner_mutation_executor`; next acceptance is real-signal/live-ticket observation |
| **P0** | Exchange truth is not yet the current authority for protection completeness | Code-covered and deployed by `protection_reconciler` over caller-provided exchange snapshots; next acceptance is official exchange snapshot wiring/capability audit |
| **P0** | Sequential ENTRY / SL / TP1 submit failures do not yet all map to lifecycle recovery states | Code-covered and deployed by exact lifecycle classification plus `protection_recovery_command`; next acceptance is official scheduling/API path audit |
| **P0** | First exchange-truth reconciliation tick is not yet materialized immediately after real protected submit result | Closed and deployed by migration `101` and `post_submit_reconciliation_tick` |
| **P0** | Recovery command determinism | Closed locally on `codex/p0-capital-safety-closure` for SL/TP1 degraded recovery, retry limit, scope freeze writes, current-risk pre-submit blocking, and stale/no-risk freeze resolution; Tokyo deploy remains Owner-approved |
| **P0** | Scope freeze pre-submit enforcement | Closed locally: active real-risk `brc_ticket_bound_scope_freezes` blocks matching `strategy_group_id + symbol + side` before promotion, lane, ticket, Runtime Safety State, FinalGate preflight, Operation Layer handoff, submit-mode decision, and protected submit |
| **P0** | Continuous reconciliation after first tick | Closed locally: `first_post_submit`, `scheduled`, and `recovery_check` PG reconciliation ticks are materialized without JSON/MD report authority; Tokyo deploy remains Owner-approved |
| **P1** | Stop-risk budget reservation before submit | Closed locally: Action-Time Ticket computes `entry_reference_price`, `stop_price`, `intended_qty`, `risk_at_stop`, and `risk_reservation_basis`; FinalGate, Operation Layer handoff, Runtime Safety State, and protected submit recheck the consumed budget before allowing progress |
| **P1** | Flat position with PG-linked live protection had no first-class cleanup command | Closed and deployed by migration `098` and `orphan_protection_cleanup_command` |
| **P1** | No single lifecycle state machine spans submit result, local orders, exchange refs, position projection, protection, reconciliation, settlement, and review | Closed in code by the Lifecycle Safety Core materializers, full-chain harness, recovery commands, protection reconciler, runner mutation executor, and final closure; live outcome proof waits for a future real ticket |
| **P1** | Action-time TTL behavior across the full post-submit chain | Closed locally: expired tickets still block new submit attempts, while already-submitted ticket-bound lifecycles can continue protection, runner, and final closure |

## Target Architecture

### Responsibility Split

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| **Action-Time Ticket** | Identify the exact candidate trade | Submit or protect orders |
| **FinalGate / Operation Layer** | Authorize exactly one ticket-bound submit command | Bypass runtime safety |
| **Protected Submit Attempt** | Submit the ticket-bound ENTRY / SL / TP1 envelope through the official gateway path and record the result | Pretend a position is protected before fill/protection proof |
| **Exit Protection Materializer** | Record a PG protection set from already-submitted ENTRY / SL / TP1 refs | Call exchange directly or pretend proof rows are exchange truth |
| **Protection Reconciler** | Compare PG protection set with exchange open orders, fills, position, and local OrderLifecycle | Create new entry orders or silently overwrite PG truth |
| **Runner Protection Adjuster** | Record the official-path replacement RUNNER_SL proof in PG after TP1 fill | Call exchange directly, add exposure, or invent strategy-side exits |
| **Official Runner Mutation Path** | Cancel/replace old SL and submit RUNNER_SL through ticket-bound Operation Layer authority | Bypass Operation Layer or mutate protection from proof-only code |
| **Post-Submit Closure** | Summarize protection/reconciliation/settlement/review state and close lifecycle when final proofs exist | Call exchange, mutate budget, or fake review evidence |
| **Owner Read Model** | Explain what happened in plain language | Infer trading permission from raw internals |

### State Machine

```text
ticket_finalgate_ready
-> submit_prepared
-> entry_submit_sent
-> entry_accepted
-> entry_fill_pending
-> entry_filled
-> exit_protection_materializing
-> exit_protection_submitted
-> exit_protection_reconciled
-> position_protected
-> tp1_fill_pending
-> tp1_filled
-> sl_adjust_pending
-> runner_protected
-> final_exit_detected
-> reconciliation_matched
-> budget_settled
-> review_recorded
-> lifecycle_closed
```

Terminal hard-stop states:

```text
submit_failed
entry_unknown
entry_orphaned
protection_missing
protection_submit_failed
protection_reconciliation_mismatch
tp1_or_sl_orphaned
runner_mutation_failed
position_closed_protection_live
review_blocked
```

## PG Tables

### `brc_ticket_bound_order_lifecycle_runs`

Purpose: one lifecycle coordinator row per **Action-Time Ticket**.

| Column | Rule |
| --- | --- |
| `lifecycle_run_id` | Stable ID from `ticket_id` |
| `ticket_id` | Unique |
| `protected_submit_attempt_id` | Nullable until submit attempt exists |
| `strategy_group_id`, `symbol`, `side` | Must match ticket |
| `runtime_profile_id` | Must match ticket |
| `status` | State machine status above |
| `entry_local_order_id` | Required after entry submit |
| `entry_exchange_order_id` | Required after exchange accepts entry |
| `entry_fill_confirmed` | True only after OrderLifecycle/exchange proof |
| `entry_filled_qty`, `entry_avg_price` | Required after fill |
| `exit_protection_set_id` | Required after protection materialization |
| `first_blocker` | First active lifecycle blocker |
| `blockers`, `warnings` | JSONB diagnostics |
| `created_at_ms`, `updated_at_ms` | Runtime time |

Required constraints:

- unique `ticket_id`;
- `position_protected` requires `entry_fill_confirmed=true`;
- `position_protected` requires `exit_protection_set_id IS NOT NULL`;
- terminal hard-stop statuses must have `first_blocker IS NOT NULL`;
- no live profile, sizing, withdrawal, or transfer mutation flags may ever be
  true.

### `brc_ticket_bound_exit_protection_sets`

Purpose: the exact exchange-native protection bundle for one filled entry.

| Column | Rule |
| --- | --- |
| `exit_protection_set_id` | Stable ID from `ticket_id + entry_exchange_order_id` |
| `ticket_id` | Unique active protection set per ticket |
| `protected_submit_attempt_id` | Submit attempt ref |
| `entry_local_order_id`, `entry_exchange_order_id` | Required |
| `strategy_group_id`, `symbol`, `side` | Must match ticket |
| `entry_filled_qty`, `entry_avg_price` | Required |
| `status` | `pending`, `materializing`, `submitted`, `reconciled`, `degraded`, `failed`, `closed` |
| `sl_order_id`, `tp1_order_id` | Required for `submitted/reconciled` |
| `runner_qty` | Remaining quantity after TP1 |
| `protection_complete` | True only when SL and TP1 are both valid reduce-only exchange orders |
| `reconciled_with_exchange` | True only after exchange/order/local refs match |
| `first_blocker`, `blockers`, `warnings` | Current lifecycle blocker |

Required constraints:

- `protection_complete=true` requires non-null SL and TP1 refs;
- SL and TP1 must both be `reduce_only=true`;
- no entry expansion order can be referenced;
- a set cannot be `closed` until position is flat or lifecycle review records
  why residual runner protection remains.

### `brc_ticket_bound_exit_protection_orders`

Purpose: one row per SL/TP1/runner-adjustment order.

| Column | Rule |
| --- | --- |
| `exit_protection_order_id` | Stable role-specific ID |
| `exit_protection_set_id` | Parent set |
| `ticket_id` | Ticket ref |
| `role` | `SL`, `TP1`, `SL_ADJUSTMENT`, `RUNNER_SL` |
| `local_order_id` | OrderLifecycle local ID |
| `exchange_order_id` | Exchange order ID after accepted |
| `status` | `planned`, `submitted`, `open`, `partially_filled`, `filled`, `cancel_pending`, `cancelled`, `replace_pending`, `replaced`, `failed` |
| `order_type` | `STOP_MARKET` for SL, `LIMIT` for TP1 |
| `side` | Reduce-only close side |
| `qty`, `price`, `trigger_price` | Order quantity and price refs |
| `reduce_only` | Must be true |
| `replaces_exit_protection_order_id` | Required for replacements |
| `created_at_ms`, `updated_at_ms` | Runtime time |

Required constraints:

- all rows must have `reduce_only=true`;
- TP1 rows require `price`;
- SL rows require `trigger_price`;
- replacement rows require a replaced order ref;
- open SL quantity must never exceed current remaining position by more than
  the symbol step tolerance.

### `brc_ticket_bound_lifecycle_events`

Purpose: append-only event ledger for audit and read models.

Events:

```text
entry_submitted
entry_accepted
entry_filled
exit_protection_materialization_started
sl_submitted
tp1_submitted
exit_protection_reconciled
tp1_filled
sl_cancel_requested
runner_sl_submitted
final_exit_detected
reconciliation_matched
budget_settled
review_recorded
hard_stopped
```

## Materializers And Services

### Implemented Current Layer

This branch adds the first machine-checkable lifecycle layer:

```text
protected_submit_attempt submitted
-> entry fill confirmed
-> brc_ticket_bound_order_lifecycle_runs
-> brc_ticket_bound_exit_protection_sets
-> brc_ticket_bound_exit_protection_orders
-> post_submit_closure
```

The implemented materializer is intentionally **PG-only**:

- it reads `brc_ticket_bound_protected_submit_attempts`;
- it requires **ENTRY** status `FILLED`;
- it requires filled quantity to cover requested entry quantity;
- it requires average execution price;
- it requires **SL** and **TP1** exchange order refs;
- it writes lifecycle/protection rows and lifecycle events;
- it does not call FinalGate, Operation Layer, OrderLifecycle, exchange,
  live profile, sizing, withdrawal, or transfer paths.

This layer now covers the **PG proof** shape for:

```text
submitted attempt
-> entry fill proof
-> SL + TP1 proof
-> runner SL proof
-> final exit / reconciliation / settlement / review proof
```

It does not complete the official exchange mutation and reconciliation target.
The implementation-ready closure is defined in
`docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`.

### `TicketBoundOrderLifecycleService`

Single owner of lifecycle state transitions.

Inputs:

- `ticket_id`;
- `protected_submit_attempt_id`;
- local OrderLifecycle state;
- exchange order refs;
- position projection;
- runtime safety state;
- protection set rows.

Outputs:

- lifecycle run row;
- lifecycle events;
- current blocker.

### `TicketBoundExitProtectionMaterializer`

Runs only after **entry fill confirmed**.

Responsibilities:

1. Load the ticket-bound lifecycle run.
2. Prove entry order is filled through OrderLifecycle and/or exchange fact.
3. Record ticket-bound protection order refs:
   - SL reduce-only stop-market for full filled qty;
   - TP1 reduce-only limit for the strategy/event-defined TP1 ratio;
   - runner qty = filled qty - TP1 qty.
4. Write protection set and order rows.
5. Mark lifecycle `position_protected` only after PG refs prove submitted
   SL and TP1 rows.
6. Leave exchange truth confirmation to the protection reconciler.

Forbidden:

- submit additional entry;
- place or cancel exchange orders;
- increase position;
- change leverage;
- mutate runtime profile;
- bypass FinalGate or Operation Layer;
- treat JSON/MD as current truth.

### `TicketBoundRunnerProtectionAdjuster`

Runs after **TP1 fill**.

Responsibilities:

1. Confirm TP1 fill.
2. Load the existing PG protection set and SL/TP1 rows.
3. If TP1 is filled but **RUNNER_SL** ref is missing, mark
   `sl_adjust_pending` with `runner_sl_exchange_order_id_required`.
4. Require an already-created replacement **RUNNER_SL** exchange order ref
   from the official ticket-bound path.
5. Record the original SL as replaced and TP1 as filled in PG proof rows.
6. Record runner SL proof and lifecycle events in PG.
7. Mark `runner_protected` only after the runner SL proof exists.
8. Leave the official cancel/replace/submit exchange mutation to the
   ticket-bound Operation Layer path.

Forbidden:

- call exchange cancel/replace directly;
- call FinalGate or Operation Layer;
- change live profile, sizing, leverage, credentials, withdrawal, or transfer;
- treat a filled TP1 as protected without a **RUNNER_SL** proof.

### `TicketBoundRunnerMutationCommand` And Executor

Runs after **TP1 fill** and before runner proof materialization.

Current implementation:

1. `runner_mutation_command` creates one PG command intent for an
   `exit_protection_set_id`.
2. `runner_mutation_executor` consumes the prepared command and calls an
   injected gateway.
3. The result is recorded in PG and then consumed by
   `TicketBoundRunnerProtectionAdjuster`.

P0-C production wiring must keep **ProtectionMutationPlan** explicit before
executor invocation. The default local implementation is
`submit_new_runner_sl_then_cancel_old`, so old SL remains live until the new
RUNNER_SL is confirmed.

| Plan | Rule |
| --- | --- |
| **keep_existing_sl** | If the current SL safely covers remaining qty and is not worse than runner policy, do not mutate exchange orders |
| **submit_new_runner_sl_then_cancel_old** | Prefer when exchange allows overlapping reduce-only protection and qty constraints remain valid |
| **cancel_old_then_submit_runner_sl** | Use only when exchange forbids overlap or old SL must be removed first |
| **emergency_reduce** | Use only through official recovery authority when protection cannot be restored |
| **manual_intervention_required** | Use when PG/exchange identity or qty facts cannot prove a safe automated action |

Forbidden:

- add a second runner mutation service beside the existing command/executor;
- call runner executor without a selected plan;
- treat cancel-first as the default safety model;
- mark `runner_protected` before exchange and PG refs reconcile.

### `TicketBoundLifecycleMaintenanceService`

Runs after **protected submit attempt** or **exit protection set** exists. It is
the production wiring coordinator for the existing lifecycle modules.

Responsibilities:

1. Materialize ENTRY / SL / TP1 protection state from an existing protected
   submit attempt.
2. Prepare and, only when explicitly allowed, execute missing SL/TP1 protection
   recovery through the injected official gateway.
3. Reconcile PG protection rows with caller-provided exchange snapshot facts.
4. Prepare and, only when explicitly allowed, execute runner mutation after TP1
   fill.
5. Materialize RUNNER_SL proof after the official mutation result exists.
6. Prepare and, only when explicitly allowed, execute linked orphan protection
   cleanup after flat-position proof.
7. Return final blockers from current PG lifecycle/protection state rather than
   stale intermediate action history.

Forbidden:

- create a signal, promotion, lane, ticket, FinalGate pass, or Operation Layer
  handoff;
- fetch exchange state inside the service loop;
- write repo/output/report JSON or Markdown;
- execute exchange mutation unless `allow_exchange_mutation=true` and an
  official gateway is injected;
- create a parallel recovery, runner, reconciler, or cleanup authority.

### `TicketBoundLifecycleClosureMaterializer`

Runs after **final exit** is known and the position is flat.

Responsibilities:

1. Load the submitted attempt, lifecycle run, protection set, protection
   orders, and post-submit closure row from PG.
2. Require a final reduce-only exit order that belongs to the ticket-bound
   protection set.
3. Require flat-position confirmation.
4. Require reconciliation, settlement, and review evidence IDs.
5. Mark the final exit order filled.
6. Mark protection set `closed`.
7. Mark post-submit closure `closed` with:
   - `reconciliation_state=matched`;
   - `settlement_state=released`;
   - `review_state=recorded`.
8. Mark lifecycle `lifecycle_closed`.
9. Append lifecycle events:
   - `final_exit_detected`;
   - `reconciliation_matched`;
   - `budget_settled`;
   - `review_recorded`;
   - `lifecycle_closed`.

Forbidden:

- call exchange;
- call FinalGate or Operation Layer;
- mutate runtime budget;
- create review facts without a review evidence ID;
- close lifecycle when position flatness is unproven;
- close lifecycle from JSON/MD/report files.

## Failure Matrix

The recovery-command authority for this matrix is
`docs/current/POST_SUBMIT_RECONCILIATION_AND_RECOVERY_COMMAND_DESIGN.md`.

| Failure | System action | Owner action |
| --- | --- | --- |
| Entry submit failed before fill | Mark attempt failed; no protection materialization | None unless repeated |
| Entry exchange id missing | Hard stop lifecycle as `entry_unknown` | Notify if unresolved |
| Entry filled but SL submit failed | Mark `protection_missing`; freeze `strategy_group_id + symbol + side`; prepare `submit_missing_sl` immediately | Owner notified if recovery fails or retry limit is exhausted |
| SL submitted but TP1 failed | Mark `protection_degraded`; keep SL protection; prepare `submit_missing_tp1`; do not mark protection complete | Owner notified if recovery fails or retry limit is exhausted |
| TP1 filled but runner mutation failed | Mark `runner_mutation_failed` or `runner_mutation_degraded`; keep existing SL when safe; prepare runner recovery | Owner notified if recovery fails or retry limit is exhausted |
| Position flat but protection orders still open | Cancel/terminalize only through official reduce-only/order-cancel path | Notify if cancel fails |
| Exchange has protection but PG lacks refs | Do not auto-cancel and do not auto-adopt; freeze scope unless PG-linked identity proof exists | Notify if identity cannot be proven |
| PG says protected but exchange lacks SL/TP1 | Hard stop; mark protection mismatch | Owner notified |

The implementation-level failure matrix, including ENTRY unknown, partial fill,
TP1 rejected, runner mutation failed, and flat-position-with-live-protection
branches, is authoritative in
`docs/current/TICKET_BOUND_LIFECYCLE_SAFETY_CORE_IMPLEMENTATION_PLAN.md`.

## Tests

### Focused Tests

| Test | Must prove |
| --- | --- |
| `test_exit_protection_blocks_before_entry_fill` | No SL/TP1 materialization before entry fill |
| `test_exit_protection_materializes_sl_and_tp1_after_entry_fill` | Filled entry creates reduce-only SL and TP1 rows |
| `test_position_not_protected_without_tp1` | SL-only cannot become `position_protected` |
| `test_runner_adjuster_waits_before_tp1_fill` | Runner SL proof cannot materialize before TP1 fill and must not mark lifecycle blocked |
| `test_runner_adjuster_recovers_from_sl_adjust_pending` | Missing runner SL ref is recoverable after the official ref appears |
| `test_runner_adjuster_materializes_runner_sl_after_tp1_fill` | TP1 fill plus official runner SL ref marks `runner_protected` |
| `test_tokyo_ops_l2_l7_summary_flags_tp1_fill_without_runner_sl` | Server health flags TP1 filled without runner SL proof |
| `test_lifecycle_closure_records_final_exit_reconciliation_settlement_review` | Final exit plus reconciliation / settlement / review proofs close lifecycle |
| `test_lifecycle_closure_blocks_without_final_exit_proofs` | Missing final-exit or review evidence cannot close lifecycle |
| `test_tokyo_ops_l2_l7_summary_flags_lifecycle_closure_projection_mismatch` | Server health flags lifecycle/closure projection drift |
| `test_protection_submit_failure_blocks_new_entries` | Entry fill + failed protection creates hard stop |
| `test_orphan_exchange_protection_requires_identity_proof` | Exchange orphan protection cannot silently become current truth |
| `test_first_reconciliation_tick_created_after_real_submit_result` | Real protected submit result creates one `first_post_submit` reconciliation tick |
| `test_disabled_smoke_does_not_create_first_reconciliation_tick` | Disabled smoke remains rehearsal and creates no exchange-truth tick |
| `test_entry_filled_missing_sl_prepares_immediate_recovery` | ENTRY filled or open position with missing SL bypasses visibility grace and prepares `submit_missing_sl` |
| `test_tp1_missing_is_degraded_not_complete` | TP1 missing creates `protection_degraded` and `submit_missing_tp1`, not `protection_complete` |
| `test_unknown_exchange_only_order_freezes_scope_without_cancel` | Unknown exchange-only order freezes exact scope and does not cancel or adopt the order |

### Impact Tests

The current 22-scope full chain test must advance from:

```text
mock submitted -> post-submit closure reconciliation_pending
```

to:

```text
mock submitted
-> mock entry filled
-> exit protection set submitted with SL + TP1
-> position_protected
-> TP1 filled
-> runner_protected
-> final exit proof
-> post-submit closure closed
-> lifecycle_closed
```

## Runtime Cadence And Performance

| Cadence | Rule |
| --- | --- |
| No-signal watcher tick | Must not create lifecycle rows |
| Submit tick | Creates at most one lifecycle run for one ticket |
| Entry fill check | Bounded to active submitted attempts only |
| Protection reconciliation | Bounded to open lifecycle runs and active positions |
| Retention | Closed lifecycle rows are retained in PG with compact event ledger; heavy exchange snapshots are archive-only |
| Logging | Syslog emits one-line summary only; detailed order refs remain in PG |

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scope
stage: p0_capital_safety_local_closure
first_blocker: review_validation_and_deploy_approval_pending
evidence: local branch codex/p0-capital-safety-closure implements current-risk scope freeze blocking, stale/no-risk freeze resolution, scheduled/recovery reconciliation ticks, and Live Outcome Ledger PG projection; Tokyo release remains 4b0b8a27 until Owner-approved deploy
next_action: finish review and validation, then deploy only with explicit Owner approval
stop_condition: active real-risk brc_ticket_bound_scope_freezes blocks matching StrategyGroup + symbol + side before any new submit path can form, stale/no-risk freezes resolve after exchange truth disproves risk, continuous ticks continue until closure/recovery/hard stop, terminal real tickets produce outcome rows, and each ticket-bound submit has stop-risk reservation
owner_action_required: no for current observation; yes before future deployment or authority expansion
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write outside official ticket-bound gateway path
```

## Implementation Order

1. **Implemented**: add PG schema for lifecycle runs, protection sets, protection
   orders, and lifecycle events.
2. **Implemented**: require TP1 reference before protected submit readiness.
3. **Implemented proof layer**: add `TicketBoundExitProtectionMaterializer`.
4. **Implemented proof layer**: update post-submit closure so `protection_state=submitted`
   requires a complete PG SL + TP1 protection set.
5. **Implemented proof coverage**: extend 22-scope impact tests with mock entry fill and protection
   set.
6. **Implemented proof layer**: add runner SL proof adjuster for TP1 fill.
7. **Implemented proof layer**: add PG proof closure for final exit -> reconciliation ->
   settlement -> review.
8. **Implemented**: implement Lifecycle Safety Core full-chain harness.
9. **Implemented**: implement sequential submit failure recovery states.
10. **Implemented**: implement exchange protection reconciler.
11. **Implemented and deployed as lifecycle repair**: implement official runner
    mutation executor for the ticket-bound Operation Layer handoff.
12. **Implemented and deployed as lifecycle repair**: implement official missing
    SL/TP1 protection recovery command and executor.
13. **Designed**: first post-submit reconciliation tick and deterministic
    recovery command matrix.
14. **Next gate**: implement first tick, recovery command determinism, scheduler
    integration, focused tests, deploy, and observe the next real ticket through
    read-only server health plus ticket-bound lifecycle acceptance.
