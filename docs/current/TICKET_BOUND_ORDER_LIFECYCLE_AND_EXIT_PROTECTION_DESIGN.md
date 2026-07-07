# Ticket-Bound Order Lifecycle And Exit Protection Design

Last updated: 2026-07-08

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
| **Exit protection materializer** | `TicketBoundExitProtectionMaterializer` materializes PG lifecycle/protection rows after filled entry proof | It records already-submitted exchange refs; it does not call exchange |
| **Exit plan** | `RuntimePositionExitPlanService` is non-executing review evidence | It cannot materialize protection orders |
| **OrderLifecycleService** | Existing callbacks can react to entry/exit fills | Callback capability is not the ticket-bound mainline owner |
| **Runner protection adjuster** | `TicketBoundRunnerProtectionAdjuster` materializes PG proof after TP1 fill and a replacement runner SL ref | It records an official-path result; it does not call exchange or cancel/replace itself |
| **ExchangeGateway** | Existing gateway can place and cancel orders | The runner proof layer must not become a second exchange mutation path |
| **Impact test** | 22 active scopes reach mock submitted -> exit protection set -> post-submit closure | Test proves entry-fill + SL/TP1 protection set materialization; focused tests prove runner SL proof materialization |

### Known P0 / P1 Gaps

| Severity | Gap | Why it matters |
| --- | --- | --- |
| **P0** | No **ticket-bound exit protection set** object | Closed by `brc_ticket_bound_exit_protection_sets` |
| **P0** | No **entry fill confirmed** gate before exit protection materialization | Closed by materializer requiring full filled entry status, qty, and average price |
| **P0** | **TP1** is missing from the protected submit / protection closure truth | Closed by TP1 submit request requirement and closure protection-set requirement |
| **P0** | `protection_state=submitted` only requires SL | Closed; it now requires PG protection set completeness |
| **P1** | TP1 fill -> SL quantity adjustment has no ticket-bound owner | Closed by PG runner protection proof materializer requiring TP1 fill and replacement runner SL exchange ref |
| **P1** | No single lifecycle state machine spans submit result, local orders, exchange refs, position projection, protection, reconciliation, settlement, and review | Fixes remain local and regress at integration boundaries |
| **P1** | Action-time TTL is not tested against the full post-submit chain | Fast opportunities may expire before lifecycle proof completes |

## Target Architecture

### Responsibility Split

| Layer | Responsibility | Must not do |
| --- | --- | --- |
| **Action-Time Ticket** | Identify the exact candidate trade | Submit or protect orders |
| **FinalGate / Operation Layer** | Authorize exactly one ticket-bound submit command | Bypass runtime safety |
| **Protected Submit Attempt** | Submit entry through the official gateway path and record the attempt | Pretend a position is protected before fill/protection proof |
| **Exit Protection Materializer** | After entry fill, create reduce-only SL and TP1, persist protection set | Expand position, mutate sizing/profile, bypass Operation Layer |
| **Protection Reconciler** | Compare PG protection set with exchange open orders and local OrderLifecycle | Create new entry orders |
| **Runner Protection Adjuster** | React to TP1 fill by recording the official-path replacement runner SL proof in PG | Call exchange directly, add exposure, or invent strategy-side exits |
| **Post-Submit Closure** | Summarize protection/reconciliation/settlement/review state | Call exchange or mutate order lifecycle |
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
sl_adjust_failed
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

This layer now covers **TP1 fill -> runner SL proof -> runner protected**.
The remaining non-closed lifecycle work is **final exit -> reconciliation ->
settlement -> review**.

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
3. Compute executable protection orders:
   - SL reduce-only stop-market for full filled qty;
   - TP1 reduce-only limit for the strategy/event-defined TP1 ratio;
   - runner qty = filled qty - TP1 qty.
4. Place SL and TP1 through the official exchange gateway.
5. Register/update local orders in OrderLifecycle.
6. Write protection set and order rows.
7. Mark lifecycle `position_protected` only after PG + exchange refs match.

Forbidden:

- submit additional entry;
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
5. Record the original SL as replaced and TP1 as filled.
6. Record runner SL proof and lifecycle events in PG.
7. Mark `runner_protected` only after the runner SL proof exists.

Forbidden:

- call exchange cancel/replace directly;
- call FinalGate or Operation Layer;
- change live profile, sizing, leverage, credentials, withdrawal, or transfer;
- treat a filled TP1 as protected without a **RUNNER_SL** proof.

## Failure Matrix

| Failure | System action | Owner action |
| --- | --- | --- |
| Entry submit failed before fill | Mark attempt failed; no protection materialization | None unless repeated |
| Entry exchange id missing | Hard stop lifecycle as `entry_unknown` | Notify if unresolved |
| Entry filled but SL submit failed | Mark `protection_submit_failed`; block new entries; require reduce-only recovery | Owner may review abnormal recovery |
| SL submitted but TP1 failed | Mark `protection_submit_failed`; position is not fully protected; block new entries | Owner may review degraded hold/close |
| TP1 filled but SL adjust failed | Mark `sl_adjust_failed`; block new entries; notify | Owner may review recovery |
| Position flat but protection orders still open | Cancel/terminalize only through official reduce-only/order-cancel path | Notify if cancel fails |
| Exchange has protection but PG lacks refs | Import/reconcile as orphan protection only after identity proof | Notify if identity cannot be proven |
| PG says protected but exchange lacks SL/TP1 | Hard stop; mark protection mismatch | Owner notified |

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
| `test_protection_submit_failure_blocks_new_entries` | Entry fill + failed protection creates hard stop |
| `test_orphan_exchange_protection_requires_identity_proof` | Exchange orphan protection cannot silently become current truth |

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
-> post-submit closure protection_complete_reconciliation_pending
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
stage: post_submit_order_lifecycle
first_blocker: final_exit_reconciliation_settlement_review_missing
evidence: PG exit protection set materializer covers ENTRY fill -> SL + TP1 protection; PG runner adjuster covers TP1 fill -> RUNNER_SL proof
next_action: implement PG lifecycle closure from final exit detection through reconciliation, settlement, and review
stop_condition: one ticket can pass mock submit -> entry fill -> SL/TP1 protection -> TP1 fill -> runner protected -> final exit -> reconciliation matched -> budget settled -> review recorded without file authority or exchange bypass
owner_action_required: no
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write outside official ticket-bound gateway path
```

## Implementation Order

1. **Done**: add PG schema for lifecycle runs, protection sets, protection
   orders, and lifecycle events.
2. **Done**: require TP1 reference before protected submit readiness.
3. **Done**: add `TicketBoundExitProtectionMaterializer`.
4. **Done**: update post-submit closure so `protection_state=submitted`
   requires a complete PG SL + TP1 protection set.
5. **Done**: extend 22-scope impact tests with mock entry fill and protection
   set.
6. **Next**: add runner SL cancel/replace adjuster for TP1 fill.
7. **Next**: close final exit -> reconciliation -> settlement -> review with
   PG lifecycle events and read-model explanation.
8. **Deploy gate**: run read-only health checks plus non-trading mock lifecycle
   acceptance before any real order opportunity is allowed to rely on the new
   chain.
