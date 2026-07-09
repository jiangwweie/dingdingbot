---
title: RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN
status: CURRENT_DESIGN
authority: docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md
last_verified: 2026-07-06
---

# Runtime Control State DB Table Design

## Purpose

This document defines the DB table design for moving StrategyGroup runtime
control state out of scattered JSON files and code constants.

It complements:

```text
docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md
```

The table design is intentionally split into:

- existing tables to reuse;
- new tables required for StrategyGroup runtime control state;
- read-model and export tables;
- constraints that preserve the official execution boundary.

## Design Status

This is a design document, not an applied migration.

Implementation should use Alembic migrations and SQLAlchemy ORM models under
the existing PG model pattern in `src/infrastructure/pg_models.py`.

## Naming And Type Rules

| Rule | Standard |
| --- | --- |
| Table prefix | Use `brc_` for StrategyGroup governance/control tables and `runtime_` for execution-chain tables already in use |
| Primary keys | Stable string IDs, usually `<domain>_<uuid-or-deterministic-key>` |
| Time fields | `BIGINT` epoch milliseconds for runtime/control state, matching current PG model style |
| Dynamic payloads | Use `JSONB` only for nested evidence, snapshots, or flexible details |
| Current state | Use append-only events plus current projection rows where state can change |
| Freshness | Store `observed_at_ms`, `valid_until_ms`, and `source_watermark` for runtime facts |
| Authority | Include explicit safety booleans or constraints for non-authority tables |
| Currency/notional | Use `Numeric`, not float |

## Existing Tables To Reuse

| Table | Current role | Reuse decision |
| --- | --- | --- |
| `brc_strategy_families` | Strategy family identity | Reuse as higher-level family identity |
| `brc_strategy_family_versions` | Versioned strategy family facts | Reuse for strategy semantics where StrategyGroup maps cleanly to family version |
| `brc_strategy_family_registry` | Metadata-only strategy registry | Reuse for broad registry display and compatibility |
| `brc_strategy_family_playbooks` | Playbook registry | Reuse for playbook and signal contract metadata |
| `brc_strategy_group_observations` | Read-only observation evidence | Reuse for observation evidence, not current readiness |
| `brc_strategy_group_forward_reviews` | Forward review evidence | Reuse for strategy-learning evidence |
| `brc_owner_risk_acknowledgements` | Owner risk acknowledgement metadata | Reuse as policy provenance, not live authority |
| `brc_owner_risk_acceptances` | Owner risk acceptance for funded validation | Reuse as policy provenance |
| `brc_bounded_live_trial_authorizations` | Bounded live-trial authorization metadata | Reuse when live trial scope has been authorized, still not execution permission |
| `brc_multi_carrier_budget_authorizations` | Budget authorization metadata | Reuse for budget scope provenance |
| `strategy_runtime_instances` | Runtime instance lifecycle | Reuse for installed/active runtime instances |
| `strategy_runtime_events` | Runtime instance event ledger | Reuse for runtime lifecycle transitions |
| `signal_evaluations` | Shadow signal evaluation evidence | Reuse for signal evaluation evidence |
| `order_candidates` | Shadow order candidate evidence | Reuse for non-executing candidate evidence |
| `runtime_execution_*` | Execution-chain evidence and submit boundary | Reuse for action-time and official path evidence |
| `runtime_profiles` | Runtime profile payloads | Reuse as selected profile source |
| `orders` / `positions` | Official order and position state | Reuse as execution and exposure truth |

## New Table Overview

| Table | Purpose | Priority |
| --- | --- | --- |
| `brc_strategy_groups` | Runtime-facing StrategyGroup identity and lifecycle | P1 |
| `brc_strategy_group_versions` | Versioned StrategyGroup semantics | P1 |
| `brc_required_fact_contracts` | Versioned RequiredFacts contract rows | P1 |
| `brc_strategy_side_event_specs` | Versioned StrategyGroup + side + event specs | P0 |
| `brc_strategy_event_required_facts` | Event-specific RequiredFacts and disable facts | P0 |
| `brc_candidate_scope_event_bindings` | Allowed candidate scope to event spec binding | P0 |
| `brc_owner_policy_events` | Append-only Owner/system policy changes | P0 |
| `brc_owner_policy_current` | Current scoped policy projection | P0 |
| `brc_strategy_group_candidate_scope` | Candidate symbol/side/timeframe universe | P0 |
| `brc_runtime_scope_bindings` | Runtime profile and live-submit scope binding | P0 |
| `brc_symbols` | Canonical strategy symbols | P0 |
| `brc_exchange_instruments` | Exchange instrument identity and precision | P0 |
| `brc_symbol_instrument_mappings` | Canonical symbol to exchange instrument mapping | P0 |
| `brc_watcher_runtime_coverage` | Server-backed watcher/detector coverage | P0 |
| `brc_market_data_sources` | Market data source identity | P0 |
| `brc_candle_snapshots` | Closed candle snapshots used by signal events | P0 |
| `brc_market_data_quality_events` | Data gap, stale, clock skew, and conflict events | P1 |
| `brc_runtime_fact_snapshots` | Public/account/action-time fact snapshots | P1 |
| `brc_live_signal_events` | Fresh/stale/invalid signal event records | P1 |
| `brc_pretrade_readiness_rows` | Per-symbol readiness and first blocker projection | P1 |
| `brc_promotion_candidates` | Fresh satisfied promotion candidates | P1 |
| `brc_action_time_lane_inputs` | Narrowed action-time lane input records | P1 |
| `brc_action_time_tickets` | Formal machine identity of the exact candidate trade | P0 |
| `brc_action_time_ticket_events` | Append-only ticket lifecycle events | P0 |
| `brc_budget_reservations` | Short-lived budget reservations for real-submit candidates | P0 |
| `brc_protection_references` | Strategy-event-derived protection and invalidation refs | P0 |
| `brc_execution_policies` | Order type, time-in-force, slippage, and execution intent policy | P0 |
| `brc_state_transition_events` | Append-only state transition audit events | P1 |
| `brc_runtime_safety_state_snapshots` | Runtime Safety State snapshots | P1 |
| `brc_ticket_bound_protected_submit_attempts` | Ticket-bound protected submit attempts and result identity | P0 |
| `brc_ticket_bound_post_submit_closures` | Ticket-bound protection/reconciliation/settlement/review closure state | P0 |
| `brc_projection_runs` | Projection lineage and input watermark records | P0 |
| `brc_current_projection_ownership` | Single-owner registry for current projections | P0 |
| `brc_legacy_diagnostics` | Legacy artifact diagnostics that cannot set current blockers | P1 |
| `brc_goal_status_current` | Current Goal Status projection | P0 |
| `brc_control_read_model_snapshots` | Generated read-model payload history | P2 |
| `brc_server_monitor_runs` | Tokyo server monitor run records | P1 |
| `brc_server_monitor_notifications` | Feishu notification and dedupe state | P1 |
| `brc_runtime_incidents` | Fail-closed incidents and recovery classification | P1 |
| `brc_recovery_runs` | Recovery attempts and outcomes | P1 |
| `brc_strategy_intake_cases` | Research-to-runtime strategy intake cases | P1 |
| `brc_strategy_intake_stage_events` | Append-only strategy intake stage transitions | P1 |
| `brc_strategy_review_outcomes` | Signal/ticket/order/no-trade review outcomes | P1 |
| `brc_strategy_governance_decisions` | Governance decisions from review recommendations | P1 |
| `brc_strategy_policy_change_requests` | Validated policy change requests | P1 |

## Owner-Confirmed L2-L7 Constraint Extension

This section records the Owner-confirmed L2-L7 reset that supersedes broad
file-backed or compatibility-led runtime authority.

The chain is:

```text
strategy/event/scope/policy
-> watcher coverage
-> event-specific facts
-> live signal event
-> promotion candidate
-> action-time lane
-> Action-Time Ticket
-> FinalGate ticket check
-> Operation Layer ticket handoff
-> protection / reconciliation / review
```

No repo MD, generated JSON, output artifact, local cache, old packet, or code
fallback may become current runtime authority after PG cutover.

### Confirmed Active Event Seed

The initial PG seed must include only these current event specs and their
confirmed symbol/side scope. Historical signals and replay opportunities must
not be imported as current live signals.

| StrategyGroup | Symbols | Side | Event spec | Time authority | Protection ref |
| --- | --- | --- | --- | --- | --- |
| `CPM-RO-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | `long` | `CPM-LONG` | Closed 1h trigger candle close | `pullback_low_reference` |
| `MPG-001` | `OPUSDT`, `SOLUSDT`, `AVAXUSDT`, `SUIUSDT` | `long` | `MPG-LONG` | Closed 1h trigger candle close | `momentum_floor_reference` |
| `MI-001` | `AVAXUSDT`, `ETHUSDT`, `SOLUSDT` | `long` | `MI-LONG` | Closed 1h candle anchoring 12h impulse | impulse invalidation / fast reversal threshold |
| `SOR-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `BTCUSDT` | `long` | `SOR-LONG` | Closed 15m session breakout candle close | opening range low / session invalidation |
| `SOR-001` | `ETHUSDT`, `SOLUSDT`, `AVAXUSDT`, `BTCUSDT` | `short` | `SOR-SHORT` | Closed 15m session breakdown candle close | opening range high / reclaim invalidation |
| `BRF2-001` | `BTCUSDT`, `AVAXUSDT`, `ETHUSDT` | `short` | `BRF2-SHORT` | Closed 1h rally-failure candle close | `rally_high_reference` |

Unsupported opposite sides require a new StrategyGroup or versioned strategy
variant. They must not be created by mirroring.

### Event Spec And RequiredFacts Tables

`brc_strategy_side_event_specs` must define the allowed
`strategy_group_id + strategy_group_version_id + side + event_id + timeframe`
surface.

Required fields or equivalents:

```text
event_spec_id
strategy_group_id
strategy_group_version_id
event_id
side
timeframe
event_spec_version
status
freshness_window_ms
time_authority
protection_ref_type
created_at_ms
created_by
```

Constraints:

| Constraint | Rule |
| --- | --- |
| unique current event | Partial unique current `(strategy_group_id, side, event_id)` |
| time authority | Current six event specs require `event_time_ms = trigger_candle_close_time_ms` |
| side support | Unsupported side cannot bind to event spec |
| version lineage | Historical specs remain readable after retirement |

`brc_strategy_event_required_facts` must define required facts and disable facts
for each event spec version.

Required fields or equivalents:

```text
event_required_fact_id
event_spec_id
required_facts_version_id
fact_key
fact_role
fact_surface
operator
expected_value
value_source
disable_on_match
missing_blocker_class
failed_blocker_class
freshness_ms
required_for_promotion
required_for_ticket
required_for_finalgate
status
created_at_ms
```

RequiredFacts rows must be machine evaluable. `expected_condition` may appear only
as a generated human-readable export derived from `operator`, `expected_value`,
`value_source`, and `disable_on_match`; it must not be the stored source of
runtime truth.

Current required operators are:

| Operator | Meaning |
| --- | --- |
| `eq` | observed value equals expected value |
| `neq` | observed value does not equal expected value |
| `gte` | observed value is greater than or equal to expected value |
| `lte` | observed value is less than or equal to expected value |
| `gt` | observed value is greater than expected value |
| `lt` | observed value is less than expected value |
| `in` | observed value is in expected set |
| `not_in` | observed value is not in expected set |
| `exists` | fact key exists and is non-null |
| `not_exists` | fact key is absent or null |
| `expr_ref` | expression is defined by a versioned code/schema reference, not free text |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_strategy_event_required_facts_version_key_surface` | Unique `(event_spec_id, required_facts_version_id, fact_key, fact_surface)` |
| `ck_brc_strategy_event_required_facts_operator` | `operator` is one of the supported operator values |
| `ck_brc_strategy_event_required_facts_disable_shape` | `disable_on_match=true` rows must name a `failed_blocker_class` and cannot be silently ignored |
| `ck_brc_strategy_event_required_facts_no_v0_exception` | Current production rows must not encode `explicit_not_required_for_v0` or similar transitional text |

Disable facts are fail-closed. `disable_on_match=true` means the row describes a
condition that disables promotion, ticket materialization, or a later gate when
the condition is matched.

| Runtime observation | Meaning | Required result |
| --- | --- | --- |
| Fact key exists and condition matches | Disable condition is active | Block with `disable_fact_active:<fact_key>` or the row's `failed_blocker_class` |
| Fact key exists and condition does not match | Disable condition is explicitly clear | Continue only if all other required facts pass |
| Fact key is absent from `fact_values` | Disable condition is unknown | Block with `disable_fact_missing:<fact_key>` or the row's `missing_blocker_class` |
| Fact snapshot is stale, expired, `missing`, or `unknown` | Disable condition is unknown | Block as missing/stale; never treat as clear |

`disable_on_match=true` rows must not use absence as a successful negative
signal. For example, a BRF2 short-side `strong_uptrend_disable` fact is clear
only when the current action-time fact snapshot explicitly observes the disable
condition as false. Missing, stale, unknown, or expired values remain blockers.

MI-LONG current seed has no `v0` exception. `relative_strength_confirmed` is a
hard RequiredFact for the current `MI-LONG` event spec unless a future versioned
strategy variant explicitly changes that requirement through a new
`required_facts_version_id`.

Legacy aliases from earlier drafts map as follows:

```text
expected_condition -> generated display only
explicit_not_required_for_v0 -> invalid production value
```

`brc_candidate_scope_event_bindings` must bind only authorized candidate scopes
to allowed event specs.

Required invariant:

```text
no candidate_scope_event_binding
-> no watcher runtime coverage target
-> no live_signal_event
-> no promotion_candidate
-> no action_time_lane_input
-> no Action-Time Ticket
```

### Time, Candle, And Market Data Authority

`brc_live_signal_events` must reference closed-candle market data.

Additional required fields or equivalents:

```text
event_spec_id
event_spec_version_id
candidate_scope_id
market_data_source_id
candle_snapshot_id
event_id
event_time_ms
trigger_candle_open_time_ms
trigger_candle_close_time_ms
detected_at_ms
written_at_ms
fact_snapshot_id
status
```

Required constraints:

| Constraint | Rule |
| --- | --- |
| event time | `event_time_ms = trigger_candle_close_time_ms` |
| event identity | Unique `(strategy_group_id, symbol, side, event_spec_id, event_time_ms)` |
| freshness source | `detected_at_ms`, `written_at_ms`, and `exported_at_ms` cannot define freshness |
| closed candle | Unclosed candles cannot create fresh live signal events |
| replay boundary | Replay or historical events cannot insert current live events with `status='facts_validated'` and `freshness_state='fresh'` |

`brc_candle_snapshots` must be unique by:

```text
exchange_instrument_id
timeframe
trigger_candle_open_time_ms
market_data_source_id
```

### Symbol And Instrument Authority

Runtime scope must use canonical symbols. Exchange access must use exchange
instrument IDs.

`brc_symbols`, `brc_exchange_instruments`, and
`brc_symbol_instrument_mappings` must enforce:

```text
canonical_symbol
exchange_id
market_type
settlement_asset
exchange_instrument
instrument_status
price_precision
quantity_precision
min_notional
tick_size
lot_size
```

Required invariant:

```text
no active unambiguous symbol/instrument mapping
-> no watcher scope
-> no signal
-> no ticket
-> no submit
```

String replacement must not infer instrument identity.

### Fact Snapshot Binding

`brc_runtime_fact_snapshots` must bind event-specific facts when used for
promotion and ticket lineage.

Additional required fields or equivalents:

```text
event_spec_id
event_spec_version_id
candidate_scope_id
signal_event_id
trigger_candle_close_time_ms
fact_snapshot_hash
```

Required invariant:

```text
no event-specific fact snapshot -> no live signal event
stale public facts -> no promotion
stale action-time facts -> no ticket or FinalGate pass
fact side / event mismatch -> reject
```

### Promotion, Lane, And Ticket State Machines

`brc_live_signal_events.status`, `brc_promotion_candidates.status`,
`brc_action_time_lane_inputs.status`, and `brc_action_time_tickets.status` must
be independent state machines.

Required status categories:

| Table | Required status categories |
| --- | --- |
| `brc_live_signal_events` | `detected`, `facts_validated`, `stale`, `rejected`, `superseded` |
| `brc_promotion_candidates` | `eligible`, `blocked`, `arbitration_pending`, `arbitration_won`, `arbitration_lost`, `expired` |
| `brc_action_time_lane_inputs` | `opened`, `facts_refreshing`, `ticket_pending`, `ticket_created`, `closed`, `expired`, `invalidated` |
| `brc_action_time_tickets` | `created`, `preflight_pending`, `finalgate_ready`, `finalgate_rejected`, `expired`, `superseded`, `submitted`, `closed`, `invalidated` |

Freshness is not a primary lifecycle status. It is represented by
`freshness_state` or derived from event time and freshness window:

```text
fresh = status='facts_validated'
        and freshness_state='fresh'
        and now_ms <= expires_at_ms
        and not superseded/rejected
```

Legal transitions:

| State machine | Allowed transitions |
| --- | --- |
| `brc_live_signal_events` | `detected -> facts_validated`; `detected -> rejected`; `facts_validated -> stale`; `facts_validated -> superseded`; `detected -> stale` |
| `brc_promotion_candidates` | `eligible -> arbitration_pending`; `eligible -> blocked`; `arbitration_pending -> arbitration_won`; `arbitration_pending -> arbitration_lost`; `eligible/arbitration_pending/arbitration_won/arbitration_lost -> expired` |
| `brc_action_time_lane_inputs` | `opened -> facts_refreshing`; `facts_refreshing -> ticket_pending`; `ticket_pending -> ticket_created`; `opened/facts_refreshing/ticket_pending/ticket_created -> closed`; `opened/facts_refreshing/ticket_pending -> expired`; `opened/facts_refreshing/ticket_pending/ticket_created -> invalidated` |
| `brc_action_time_tickets` | `created -> preflight_pending`; `preflight_pending -> finalgate_ready`; `preflight_pending -> finalgate_rejected`; `finalgate_ready -> submitted`; `created/preflight_pending/finalgate_ready -> expired`; `created/preflight_pending/finalgate_ready -> superseded`; `created/preflight_pending/finalgate_ready -> invalidated`; `submitted -> closed` |

Forbidden transitions:

| State machine | Forbidden examples |
| --- | --- |
| `brc_live_signal_events` | `rejected -> facts_validated`; `stale -> facts_validated`; `superseded -> facts_validated` |
| `brc_promotion_candidates` | `blocked -> arbitration_won`; `arbitration_lost -> arbitration_won`; `expired -> arbitration_won` |
| `brc_action_time_lane_inputs` | `expired -> ticket_pending`; `invalidated -> ticket_created`; `closed -> facts_refreshing` |
| `brc_action_time_tickets` | `expired -> finalgate_ready`; `finalgate_rejected -> submitted`; `submitted -> submitted`; `closed -> preflight_pending` |

Every transition must append an event row in `brc_state_transition_events` or a
domain-specific event table with:

```text
from_status
to_status
transition_reason
trigger_ref
writer
occurred_at_ms
```

Fresh signal must not imply order readiness. Promotion candidate must not imply
ticket existence.

### Action-Time Ticket

`brc_action_time_tickets` is the formal identity of one exact candidate trade.

Required fields or equivalents:

```text
ticket_id
action_time_lane_input_id
promotion_candidate_id
signal_event_id
event_spec_id
event_spec_version_id
candidate_scope_id
runtime_scope_binding_id
strategy_group_id
strategy_group_version_id
symbol
exchange_instrument_id
side
event_id
event_time_ms
trigger_candle_close_time_ms
runtime_profile_id
public_fact_snapshot_id
action_time_fact_snapshot_id
account_safe_fact_snapshot_id
account_mode_snapshot_id
budget_reservation_id
protection_ref_id
execution_policy_id
execution_policy_version
owner_policy_version
sizing_policy_version
protection_policy_version
target_notional
leverage
expires_at_ms
status
authority_boundary
ticket_hash
created_under_versions_hash
```

Constraints:

| Constraint | Rule |
| --- | --- |
| lineage | Ticket requires lane, promotion, signal, event spec, candidate scope, runtime binding, facts, budget, protection, and execution policy |
| one active ticket | One open real-submit lane has at most one active ticket |
| expiry | Ticket requires `expires_at_ms` |
| hash | `ticket_hash` covers strategy, symbol, side, event, event time, profile, notional, leverage, protection, and execution intent |
| no order authority | Ticket does not create exchange orders |

FinalGate may consume only `ticket_id` as the trade identity input.

### Budget Reservation

`brc_budget_reservations` must reserve capital before real-submit ticket
progression.

Creation order is:

```text
promotion arbitration winner
-> action_time_lane_input
-> budget_reservation scoped to lane/candidate, without requiring ticket_id
-> action_time_ticket references budget_reservation_id
-> budget_reservation may backfill ticket_id after ticket creation
```

This avoids a circular dependency between reservation creation and ticket
creation. A ticket must reference an active reservation, but a reservation must
not require `ticket_id` at initial insert.

Required fields or equivalents:

```text
budget_reservation_id
promotion_candidate_id
action_time_lane_input_id
ticket_id nullable unique
signal_event_id
event_spec_id
runtime_profile_id
account_id
strategy_group_id
symbol
side
target_notional
leverage
reserved_margin
entry_reference_price
stop_price
intended_qty
risk_at_stop
risk_reservation_basis
reserved_at_ms
expires_at_ms
status
release_reason
policy_version
```

Required invariant:

```text
available balance alone is not sufficient for real-submit progression.
ticket.budget_reservation_id must reference active budget_reservation.
budget_reservation lineage must match ticket lineage before FinalGate.
consumed budget_reservation must carry stop-risk reservation before FinalGate,
Operation Layer handoff, Runtime Safety State, and protected submit.
risk_at_stop = abs(entry_reference_price - stop_price) * intended_qty.
long stop_price must be below entry_reference_price.
short stop_price must be above entry_reference_price.
```

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_budget_reservations_active_lane` | Partial unique active reservation per `action_time_lane_input_id` |
| `uq_brc_budget_reservations_ticket` | Unique nullable `ticket_id`; once filled, one ticket binds one reservation |
| `ck_brc_budget_reservations_lineage` | StrategyGroup, symbol, side, profile, notional, leverage, and event refs must match the ticket before FinalGate |
| `ck_brc_budget_reservations_expiry` | Active reservation requires `expires_at_ms` and cannot be consumed after expiry |
| `ck_brc_budget_res_stop_risk_positive` | When `risk_at_stop` is present, `entry_reference_price`, `stop_price`, `intended_qty`, and `risk_at_stop` must all be positive |
| `ck_brc_budget_res_stop_risk_protective_side` | When `risk_at_stop` is present, long stop must be below entry and short stop must be above entry |

### Protection Reference

`brc_protection_references` must store strategy-event-derived protection refs.

Required fields or equivalents:

```text
protection_ref_id
event_spec_id
strategy_group_id
symbol
side
reference_type
reference_price
invalidation_condition
stop_order_type
stop_time_in_force
protection_policy_version
source_fact_snapshot_id
expires_at_ms
```

Required invariant:

```text
ticket without protection_ref_id -> reject
Operation Layer cannot guess stops
protection failure or detachment -> submit path not complete
```

### Execution Policy And Normalized Order Intent

`brc_execution_policies` must define execution semantics for runtime profile,
strategy, event, and side.

Required fields or equivalents:

```text
execution_policy_id
execution_policy_version
runtime_profile_id
strategy_group_id
event_spec_id
side
order_type
time_in_force
reduce_only
post_only
close_position
allowed_slippage_bps
price_protection_mode
submit_deadline_ms
cancel_if_not_filled_policy
```

Operation submit commands must persist normalized Decimal-computed order intent:

```text
ticket_id
exchange_instrument_id
side
order_type
target_notional
leverage
price_reference
raw_quantity
normalized_quantity
normalized_price
rounding_policy
min_notional_check
tick_size_check
lot_size_check
precision_check
```

Financial calculations must use Decimal. Float-based financial quantity or
price calculations are invalid.

### Account Mode And Exchange Authority

Tickets must bind account mode facts:

```text
expected_margin_mode
expected_position_mode
expected_leverage
actual_margin_mode
actual_position_mode
actual_leverage
position_side
account_mode_snapshot_id
mode_checked_at_ms
```

Operation Layer must not mutate margin mode, position mode, or leverage inside
the signal submit path. Such mutations, if ever allowed, require a separate
policy-governed administrative action.

Every real exchange write must bind:

```text
ticket_id
finalgate_pass_id
operation_submit_command_id
```

Watcher, monitor, projector, Candidate Pool, Goal Status, FinalGate,
reconciliation, and review paths must not write exchange orders.

### Owner Policy Operations And Versioning

Owner operations must append policy events and create new policy versions.

Required operation categories:

```text
enable_strategy
pause_strategy
resume_strategy
retire_strategy
narrow_scope
expand_scope
enable_ticket_eligibility
disable_ticket_eligibility
enable_real_submit
disable_real_submit
set_budget
set_runtime_profile
set_notification_policy
```

Signals, promotions, tickets, orders, protection, reconciliation, and review
must bind the policy/spec versions under which they were created. New versions
affect future events. Active tickets affected by version changes must revalidate
or invalidate.

### Review To Governance

`brc_strategy_review_outcomes`,
`brc_strategy_governance_decisions`, and
`brc_strategy_policy_change_requests` must preserve:

```text
signal_event_id
promotion_candidate_id
action_time_lane_input_id
ticket_id
order_id
stage_reached
first_blocker
market_after_event
execution_outcome
strategy_learning
governance_recommendation
owner_action_required
created_under_versions_hash
```

Review may recommend governance changes. It must not directly grant current
submit authority, expand scope, increase budget, mutate active tickets, or
reinterpret old orders under current strategy versions.

### Fail-Closed And Negative Tests

The PG implementation must include negative tests proving rejection of:

```text
CPM-RO-001 short
MPG-001 short
MI-001 short
BRF2-001 long
SOR generic signal without SOR-LONG or SOR-SHORT
unsupported symbol
generated_at as event_time_ms
live_signal_event without event_spec_id
promotion_candidate without signal_event_id
action_time_ticket without promotion_candidate_id
ticket without expires_at_ms
FinalGate without ticket_id
Operation Layer without ticket_id + finalgate_pass_id
replay event as fresh live signal
Candidate Pool JSON as authority input
duplicate live signal / promotion / ticket / accepted submit
```

## Registry Tables

### `brc_strategy_groups`

Purpose: runtime-facing identity for StrategyGroups such as `MPG-001`,
`CPM-RO-001`, `MI-001`, `SOR-001`, and `BRF2-001`.

| Column | Type | Rule |
| --- | --- | --- |
| `strategy_group_id` | `String(128)` PK | Stable StrategyGroup ID |
| `strategy_family_id` | `String(128)` nullable | Optional link to `brc_strategy_families` |
| `current_version_id` | `String(128)` nullable | Current version pointer |
| `owner_label` | `String(256)` | Short Owner-readable name |
| `status` | `String(64)` | `intake`, `active`, `paused`, `parked`, `killed`, `retired` |
| `active_wip_slot` | `String(32)` nullable | `P0-A`, `P0-B`, `P1-A`, `P1-B`, `P2-A`, or null |
| `default_tier` | `String(16)` | `L0` to `L4` |
| `tradeability_stage` | `String(64)` | Contract lifecycle stage |
| `owner_visible` | `Boolean` | Whether shown in Owner surfaces |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Last update time |
| `metadata` | `JSONB` | Non-authority metadata |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_strategy_groups_status` | Status enum listed above |
| `ck_brc_strategy_groups_tier` | Tier in `L0` to `L4` |
| `idx_brc_strategy_groups_status` | `(status, updated_at_ms)` |
| `idx_brc_strategy_groups_wip` | `(active_wip_slot)` |

Writer: registry import, Owner policy/admin flow.

Readers: Tradeability Decision, Candidate Pool, Daily Table, runtime status
projectors.

### `brc_strategy_group_versions`

Purpose: versioned StrategyGroup semantics consumed by runtime builders.

| Column | Type | Rule |
| --- | --- | --- |
| `strategy_group_version_id` | `String(128)` PK | Stable version ID |
| `strategy_group_id` | `String(128)` | Link to StrategyGroup |
| `version` | `Integer` | Monotonic version |
| `status` | `String(64)` | `draft`, `current`, `superseded`, `retired` |
| `edge_thesis` | `Text` | Short thesis |
| `trade_logic` | `Text` | Entry/exit/protection idea |
| `regime_fit` | `Text` | Regime/session/product fit |
| `supported_sides` | `JSONB` | Example: `["long"]` |
| `supported_timeframes` | `JSONB` | Timeframes |
| `risk_envelope` | `JSONB` | Loss unit, attempt cap, hard stops |
| `promotion_rules` | `JSONB` | Promotion/downshift/park/kill rules |
| `evidence_refs` | `JSONB` | Handoff/replay/review refs |
| `created_at_ms` | `BIGINT` | Insert time |
| `created_by` | `String(128)` | `system`, `owner`, or agent ID |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_strategy_group_versions_group_version` | Unique `(strategy_group_id, version)` |
| `uq_brc_strategy_group_versions_current` | Partial unique current row per StrategyGroup |
| `idx_brc_strategy_group_versions_group` | `(strategy_group_id, status)` |

Writer: registry import and reviewed strategy admission flow.

Readers: RequiredFacts builder, Tradeability Decision, Candidate Pool.

### `brc_required_fact_contracts`

Purpose: structured RequiredFacts contract by StrategyGroup version, surface,
and fact key.

| Column | Type | Rule |
| --- | --- | --- |
| `fact_contract_id` | `String(128)` PK | Stable row ID |
| `strategy_group_version_id` | `String(128)` | Version link |
| `fact_key` | `String(128)` | Machine key |
| `fact_group` | `String(64)` | `market`, `strategy`, `derivatives`, `risk`, `account`, `exchange`, `protection` |
| `required_surface` | `String(64)` | `pretrade`, `action_time`, `finalgate`, `operation_layer`, `review` |
| `source_kind` | `String(64)` | `public_market`, `account_safe`, `watcher`, `exchange_metadata`, `derived` |
| `freshness_ms` | `BIGINT` nullable | Required freshness window |
| `missing_blocker_class` | `String(128)` | Contract blocker class |
| `failed_blocker_class` | `String(128)` | Contract blocker class |
| `required_for_live_submit` | `Boolean` | True only if live-submit hard input |
| `definition_payload` | `JSONB` | Thresholds and shape |
| `created_at_ms` | `BIGINT` | Insert time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_required_fact_contracts_version_key_surface` | Unique `(strategy_group_version_id, fact_key, required_surface)` |
| `idx_brc_required_fact_contracts_surface` | `(required_surface, fact_group)` |

Writer: registry import and fact contract migration.

Readers: watcher, Candidate Pool, action-time facts, FinalGate preflight.

## Policy And Scope Tables

### `brc_owner_policy_events`

Purpose: append-only event ledger for Owner and system policy changes.

| Column | Type | Rule |
| --- | --- | --- |
| `policy_event_id` | `String(128)` PK | Stable event ID |
| `event_type` | `String(96)` | `enable`, `pause`, `resume`, `park`, `kill`, `tier_set`, `scope_set`, `risk_acceptance`, `budget_set`, `profile_set`, `live_submit_scope_set` |
| `strategy_group_id` | `String(128)` nullable | StrategyGroup scope |
| `symbol` | `String(128)` nullable | Symbol scope |
| `side` | `String(32)` nullable | `long`, `short`, `both`, or null |
| `runtime_profile_id` | `String(128)` nullable | Runtime profile |
| `tier` | `String(16)` nullable | `L0` to `L4` |
| `policy_payload` | `JSONB` | Scope details |
| `source` | `String(64)` | `owner_explicit_authorization`, `system_migration`, `codex_seed` |
| `actor` | `String(128)` | Owner/system/agent |
| `effective_at_ms` | `BIGINT` | Effective time |
| `expires_at_ms` | `BIGINT` nullable | Expiry |
| `supersedes_event_id` | `String(128)` nullable | Superseded event |
| `revoked_at_ms` | `BIGINT` nullable | Revoke time |
| `revoke_reason` | `Text` nullable | Revoke reason |
| `created_at_ms` | `BIGINT` | Insert time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_owner_policy_events_side` | Side in `long`, `short`, `both` when present |
| `idx_brc_owner_policy_events_scope_time` | `(strategy_group_id, symbol, side, effective_at_ms)` |
| `idx_brc_owner_policy_events_type_time` | `(event_type, created_at_ms)` |

Writer: runtime status readmodel, migration seed, scoped policy tools.

Readers: policy projection, Candidate Pool, Tradeability Decision.

### `brc_owner_policy_current`

Purpose: current policy projection for fast runtime reads.

| Column | Type | Rule |
| --- | --- | --- |
| `policy_current_id` | `String(160)` PK | Deterministic scope ID |
| `scope_key` | `String(256)` | Deterministic non-null key, for example `group:MPG-001`, `symbol:MPG-001:OPUSDT`, or `side:MPG-001:OPUSDT:long` |
| `scope_level` | `String(32)` | `group`, `symbol`, or `side` |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` nullable | Symbol or null for group-level |
| `side` | `String(32)` nullable | Side or null |
| `enabled_state` | `String(64)` | `not_enabled`, `enabled`, `paused`, `parked`, `killed` |
| `tier` | `String(16)` | `L0` to `L4` |
| `runtime_profile_id` | `String(128)` nullable | Selected profile |
| `pretrade_candidate_allowed` | `Boolean` | Pre-trade candidate scope |
| `action_time_rehearsal_allowed` | `Boolean` | Non-executing rehearsal scope |
| `live_submit_allowed` | `String(64)` | `none`, `scoped`, `conditional_hard_gated` |
| `max_notional` | `Numeric` nullable | Scoped max notional |
| `leverage` | `Numeric` nullable | Scoped leverage |
| `attempt_cap` | `Integer` nullable | Attempt cap |
| `loss_unit` | `Numeric` nullable | Loss unit |
| `policy_event_ids` | `JSONB` | Events composing current state |
| `valid_from_ms` | `BIGINT` | Validity start |
| `valid_until_ms` | `BIGINT` nullable | Validity end |
| `updated_at_ms` | `BIGINT` | Projection time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_owner_policy_current_scope_key` | Unique `scope_key`; do not rely on nullable `(strategy_group_id, symbol, side)` uniqueness |
| `ck_brc_owner_policy_current_scope_level` | `scope_level` in `group`, `symbol`, `side` |
| `ck_brc_owner_policy_current_scope_shape` | `group` scope requires `symbol IS NULL AND side IS NULL`; `symbol` scope requires `symbol IS NOT NULL AND side IS NULL`; `side` scope requires both `symbol` and `side` |
| `ck_brc_owner_policy_current_live_submit` | `live_submit_allowed` enum |
| `idx_brc_owner_policy_current_enabled` | `(enabled_state, tier)` |

Writer: policy projector.

Readers: Candidate Pool, Tradeability Decision, Runtime Safety State.

### `brc_strategy_group_candidate_scope`

Purpose: DB-backed candidate universe for StrategyGroup + symbol + side.

| Column | Type | Rule |
| --- | --- | --- |
| `candidate_scope_id` | `String(160)` PK | Stable scope row ID |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol such as `SOLUSDT` |
| `exchange_symbol` | `String(128)` nullable | Exchange-specific symbol |
| `asset_class` | `String(64)` | Example: `crypto_perpetual` |
| `side` | `String(32)` | `long` or `short` |
| `timeframe` | `String(32)` nullable | Primary timeframe |
| `candidate_role` | `String(32)` | `primary`, `secondary`, `support`, `conditional` |
| `observation_scope` | `String(32)` | `none`, `readonly`, `active_observation` |
| `scope_state` | `String(64)` | `readonly_only`, `trial_scope_proposed`, `live_submit_allowed`, `conditional_action_time_rehearsal_allowed` |
| `priority_rank` | `Integer` | Lower is higher priority |
| `policy_current_id` | `String(160)` nullable | Current policy ref |
| `status` | `String(64)` | `active`, `paused`, `parked`, `revoked` |
| `valid_from_ms` | `BIGINT` | Validity start |
| `valid_until_ms` | `BIGINT` nullable | Validity end |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Update time |
| `metadata` | `JSONB` | Non-authority metadata |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_candidate_scope_active` | Partial unique active `(strategy_group_id, symbol, side)` |
| `idx_brc_candidate_scope_group_priority` | `(strategy_group_id, priority_rank)` |
| `idx_brc_candidate_scope_symbol` | `(symbol, status)` |

Writer: policy projector, candidate universe import.

Readers: watcher scope builder, Candidate Pool, Daily Table.

### `brc_runtime_scope_bindings`

Purpose: bind StrategyGroup candidate scope to runtime profile and submit
boundary.

| Column | Type | Rule |
| --- | --- | --- |
| `runtime_scope_binding_id` | `String(160)` PK | Stable binding ID |
| `candidate_scope_id` | `String(160)` | Candidate scope ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `runtime_profile_id` | `String(128)` | Runtime profile |
| `selected_strategygroup_scope` | `Boolean` | StrategyGroup binding is explicit |
| `symbol_side_scope_closed` | `Boolean` | Symbol/side closed |
| `notional_leverage_scope_closed` | `Boolean` | Notional/leverage closed |
| `server_runtime_coverage_required` | `Boolean` | Coverage required before action-time |
| `live_submit_allowed` | `Boolean` | Scoped live submit may continue only if gates pass |
| `conditional_hard_gates` | `JSONB` | Extra gates such as short squeeze clear |
| `status` | `String(64)` | `active`, `paused`, `revoked`, `expired` |
| `policy_current_id` | `String(160)` | Current policy ref |
| `valid_from_ms` | `BIGINT` | Validity start |
| `valid_until_ms` | `BIGINT` nullable | Validity end |
| `authority_boundary` | `Text` | Boundary statement |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_runtime_scope_bindings_live_submit_scope` | `live_submit_allowed` requires closed StrategyGroup, symbol/side, and notional/leverage scope |
| `uq_brc_runtime_scope_bindings_active` | Partial unique active `(strategy_group_id, symbol, side, runtime_profile_id)` |
| `idx_brc_runtime_scope_bindings_profile` | `(runtime_profile_id, status)` |

Writer: runtime scope binder.

Readers: Candidate Pool, Runtime Safety State, action-time lane builder.

## Runtime Coverage And Fact Tables

### `brc_watcher_runtime_coverage`

Purpose: current server-backed watcher/detector coverage by candidate scope.

| Column | Type | Rule |
| --- | --- | --- |
| `coverage_id` | `String(192)` PK | Stable coverage row ID |
| `candidate_scope_id` | `String(160)` nullable | Candidate scope ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `timeframe` | `String(32)` nullable | Timeframe |
| `detector_key` | `String(128)` | Detector ID |
| `watcher_unit` | `String(128)` | Watcher service/unit |
| `coverage_state` | `String(64)` | `covered`, `not_covered`, `stale`, `missing`, `disabled` |
| `liveness_state` | `String(64)` | `healthy`, `degraded`, `failed`, `unknown` |
| `last_tick_at_ms` | `BIGINT` nullable | Last watcher tick |
| `last_fact_snapshot_id` | `String(192)` nullable | Fact snapshot ref |
| `source_watermark` | `String(256)` nullable | Runtime head/source marker |
| `blocker_class` | `String(128)` nullable | Contract blocker |
| `blocker_detail` | `Text` nullable | Technical reason |
| `observed_at_ms` | `BIGINT` | Observation time |
| `valid_until_ms` | `BIGINT` nullable | Freshness expiry |
| `updated_at_ms` | `BIGINT` | Update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_watcher_runtime_coverage_current` | Unique current `(strategy_group_id, symbol, side, detector_key)` |
| `idx_brc_watcher_runtime_coverage_state` | `(coverage_state, liveness_state)` |
| `idx_brc_watcher_runtime_coverage_tick` | `(last_tick_at_ms)` |

Writer: Tokyo server-side monitor and watcher status collector.

Readers: Candidate Pool, Daily Table, server monitor, Runtime Safety State.

### `brc_runtime_fact_snapshots`

Purpose: store public, account-safe, strategy, and action-time fact snapshots.

| Column | Type | Rule |
| --- | --- | --- |
| `fact_snapshot_id` | `String(192)` PK | Stable snapshot ID |
| `strategy_group_id` | `String(128)` nullable | StrategyGroup when scoped |
| `symbol` | `String(128)` nullable | Symbol |
| `side` | `String(32)` nullable | Side |
| `runtime_profile_id` | `String(128)` nullable | Profile |
| `fact_surface` | `String(64)` | `public_pretrade`, `account_safe`, `action_time`, `exchange_metadata`, `protection`, `position_open_order` |
| `source_kind` | `String(64)` | Source category |
| `source_ref` | `String(512)` nullable | Path/API/run ref |
| `computed` | `Boolean` | Whether computation ran |
| `satisfied` | `Boolean` nullable | Whether facts satisfied |
| `freshness_state` | `String(64)` | `fresh`, `stale`, `missing`, `unknown` |
| `failed_facts` | `JSONB` | Failed fact keys |
| `fact_values` | `JSONB` | Structured values |
| `blocker_class` | `String(128)` nullable | Blocker if failed/missing |
| `observed_at_ms` | `BIGINT` | Observation time |
| `valid_until_ms` | `BIGINT` nullable | Expiry |
| `created_at_ms` | `BIGINT` | Insert time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `idx_brc_runtime_fact_snapshots_scope_time` | `(strategy_group_id, symbol, side, fact_surface, observed_at_ms)` |
| `idx_brc_runtime_fact_snapshots_freshness` | `(fact_surface, freshness_state, valid_until_ms)` |

Writer: watcher, server monitor, action-time fact refresher.

Readers: Candidate Pool, Runtime Safety State, FinalGate preflight services.

When a `brc_strategy_event_required_facts` row has `disable_on_match=true`,
readers must evaluate `brc_runtime_fact_snapshots.fact_values` with three states:

1. **active disable**: key exists and condition matches;
2. **explicit clear**: key exists and condition does not match;
3. **unknown disable**: key is absent or the snapshot is stale/expired/missing/unknown.

Only **explicit clear** may allow promotion, ticket materialization, or later
pre-submit readiness to continue. Unknown disable is a blocker, not a default
false value.

### `brc_live_signal_events`

Purpose: durable signal events emitted by detectors. Absence of signal is a
read-model state, not a row.

| Column | Type | Rule |
| --- | --- | --- |
| `signal_event_id` | `String(192)` PK | Stable signal ID |
| `candidate_scope_id` | `String(160)` nullable | Candidate scope ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `detector_key` | `String(128)` | Detector ID |
| `signal_type` | `String(64)` | Strategy-specific signal |
| `source_kind` | `String(64)` | `live_market`, `replay`, `historical`, `synthetic`, or `unit_test` |
| `status` | `String(64)` | `detected`, `facts_validated`, `stale`, `rejected`, `superseded` |
| `freshness_state` | `String(64)` | `fresh`, `stale`, `expired`, `unknown` |
| `confidence` | `Numeric` nullable | Confidence if available |
| `fact_snapshot_id` | `String(192)` nullable | Facts supporting signal |
| `reason_codes` | `JSONB` | Reason codes |
| `signal_payload` | `JSONB` | Details |
| `event_time_ms` | `BIGINT` | Strategy event time |
| `trigger_candle_close_time_ms` | `BIGINT` | Closed candle time authority |
| `observed_at_ms` | `BIGINT` | Detector observation/write-adjacent time, not freshness authority |
| `expires_at_ms` | `BIGINT` | Freshness expiry |
| `invalidated_at_ms` | `BIGINT` nullable | Invalidation time |
| `created_at_ms` | `BIGINT` | Insert time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `idx_brc_live_signal_events_scope_time` | `(strategy_group_id, symbol, side, observed_at_ms)` |
| `idx_brc_live_signal_events_status_expiry` | `(status, freshness_state, expires_at_ms)` |
| `uq_brc_live_signal_identity` | Unique `(strategy_group_id, symbol, side, detector_key, signal_type, event_time_ms)` |
| `ck_brc_live_signal_source_kind` | `source_kind` is `live_market`, `replay`, `historical`, `synthetic`, or `unit_test` |
| `ck_brc_live_signal_fresh_valid` | `freshness_state='fresh'` requires `status='facts_validated'` and non-expired `expires_at_ms` |
| `ck_brc_live_signal_event_time` | `event_time_ms = trigger_candle_close_time_ms` |
| `ck_brc_live_signal_no_generated_at_event_time` | `created_at_ms` must not equal `event_time_ms` and must be greater than or equal to it |
| `ck_brc_live_signal_fresh_source` | Fresh validated signal requires `source_kind='live_market'` |

Writer: live detectors/watcher.

Readers: Candidate Pool, promotion builder, server monitor.

## Pre-Trade Readiness And Promotion Tables

### `brc_pretrade_readiness_rows`

Purpose: current per-symbol readiness row used by Candidate Pool and Daily
Table.

| Column | Type | Rule |
| --- | --- | --- |
| `readiness_row_id` | `String(192)` PK | Stable current row ID |
| `candidate_scope_id` | `String(160)` nullable | Candidate scope ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `readiness_state` | `String(64)` | `missing_scope`, `observing`, `computed_not_satisfied`, `market_wait_validated`, `promotion_candidate`, `action_time_lane`, `blocked` |
| `detector_state` | `String(64)` | `missing`, `ready`, `running`, `stale` |
| `watcher_state` | `String(64)` | `missing`, `fresh`, `stale` |
| `public_facts_state` | `String(64)` | `missing`, `computed_not_satisfied`, `satisfied` |
| `signal_lifecycle_status` | `String(64)` | `absent`, `detected`, `facts_validated`, `stale`, `rejected`, `superseded` |
| `signal_freshness_state` | `String(64)` | `fresh`, `stale`, `expired`, `missing`, `unknown` |
| `risk_state` | `String(64)` | `acceptable`, `warning`, `disable` |
| `scope_state` | `String(64)` | Pre-trade contract scope state |
| `promotion_state` | `String(64)` | `idle`, `promotion_candidate`, `action_time_lane`, `blocked` |
| `first_blocker_class` | `String(128)` | Contract blocker class |
| `first_blocker_detail` | `Text` | Concise reason |
| `next_action` | `Text` | One next action |
| `stop_condition` | `Text` | Stop or exit condition |
| `evidence_ref` | `String(512)` | DB ref or export ref |
| `source_watermark` | `String(256)` nullable | Source marker |
| `computed_at_ms` | `BIGINT` | Projection time |
| `valid_until_ms` | `BIGINT` nullable | Projection freshness |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_pretrade_readiness_rows_current` | Unique current `(strategy_group_id, symbol, side)` |
| `idx_brc_pretrade_readiness_rows_blocker` | `(first_blocker_class, readiness_state)` |
| `idx_brc_pretrade_readiness_rows_promotion` | `(promotion_state, computed_at_ms)` |

Writer: Candidate Pool builder or readiness projector.

Readers: Daily Table, server monitor, runtime status projectors.

### `brc_promotion_candidates`

Purpose: record fresh satisfied candidates that may advance toward action-time
without exchange-write authority.

| Column | Type | Rule |
| --- | --- | --- |
| `promotion_candidate_id` | `String(192)` PK | Stable promotion ID |
| `signal_event_id` | `String(192)` nullable | Signal ref |
| `readiness_row_id` | `String(192)` | Readiness ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `promotion_scope` | `String(64)` | `pretrade_candidate`, `action_time_rehearsal`, `live_submit_candidate`, `conditional_action_time_rehearsal` |
| `status` | `String(64)` | `eligible`, `blocked`, `arbitration_pending`, `arbitration_won`, `arbitration_lost`, `expired` |
| `scope_state` | `String(64)` | Scope state at promotion |
| `risk_state` | `String(64)` | Risk state |
| `facts_snapshot_id` | `String(192)` nullable | Supporting facts |
| `blockers` | `JSONB` | Remaining blockers |
| `arbitration_rank` | `Integer` nullable | Rank if multiple candidates |
| `created_at_ms` | `BIGINT` | Created time |
| `expires_at_ms` | `BIGINT` | Expiry |
| `closed_at_ms` | `BIGINT` nullable | Closed time |
| `authority_boundary` | `Text` | Non-authority statement |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `idx_brc_promotion_candidates_status_rank` | `(status, arbitration_rank)` |
| `idx_brc_promotion_candidates_scope_time` | `(strategy_group_id, symbol, side, created_at_ms)` |
| `ck_brc_promotion_candidates_no_order_authority` | Stored boundary must not imply exchange write |

Writer: Candidate Pool promotion projector.

Readers: action-time lane selector, server monitor.

### `brc_action_time_lane_inputs`

Purpose: the single narrowed pre-submit lane input. This is not an order and
does not bypass FinalGate or Operation Layer.

| Column | Type | Rule |
| --- | --- | --- |
| `action_time_lane_input_id` | `String(192)` PK | Stable lane input ID |
| `promotion_candidate_id` | `String(192)` nullable | Promotion ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | Side |
| `runtime_profile_id` | `String(128)` | Runtime profile |
| `lane_scope` | `String(64)` | `rehearsal`, `paper`, `conditional_rehearsal`, or `real_submit_candidate` |
| `status` | `String(64)` | `opened`, `facts_refreshing`, `ticket_pending`, `ticket_created`, `closed`, `expired`, `invalidated` |
| `signal_event_id` | `String(192)` nullable | Fresh signal ref |
| `public_fact_snapshot_id` | `String(192)` nullable | Public fact ref |
| `action_time_fact_snapshot_id` | `String(192)` nullable | Action-time fact ref |
| `runtime_scope_binding_id` | `String(160)` | Scope binding |
| `candidate_authorization_ref` | `String(256)` nullable | Candidate/auth evidence ref |
| `runtime_safety_snapshot_id` | `String(192)` nullable | Safety ref |
| `first_blocker_class` | `String(128)` nullable | Blocker |
| `created_at_ms` | `BIGINT` | Created time |
| `expires_at_ms` | `BIGINT` | Expiry |
| `closed_at_ms` | `BIGINT` nullable | Closed time |
| `authority_boundary` | `Text` | Boundary statement |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_action_time_lane_inputs_single_open_real` | Partial unique one open real-submit lane where `lane_scope='real_submit_candidate'` and `status IN ('opened', 'facts_refreshing', 'ticket_pending', 'ticket_created')` |
| `ck_brc_action_time_lane_inputs_lane_scope` | `lane_scope` in `rehearsal`, `paper`, `conditional_rehearsal`, `real_submit_candidate` |
| `idx_brc_action_time_lane_inputs_status` | `(lane_scope, status, created_at_ms)` |
| `ck_brc_action_time_lane_inputs_no_submit_bypass` | Status cannot imply order creation |

Writer: action-time lane selector.

Readers: action-time fact refresher, Runtime Safety State, FinalGate preflight.

## Projection Ownership Tables

These tables prevent DB-backed state from reproducing the current JSON-file
problem. They make current-state ownership, input lineage, and legacy diagnostic
use explicit.

### `brc_projection_runs`

Purpose: record every run that writes a current projection or exported read
model.

| Column | Type | Rule |
| --- | --- | --- |
| `projection_run_id` | `String(192)` PK | Stable run ID |
| `model_type` | `String(96)` | `candidate_pool`, `daily_live_enablement_table`, `goal_status`, `runtime_safety_state`, `server_monitor`, or other read model |
| `owner_projector` | `String(128)` | One named writer for this projection |
| `code_version` | `String(128)` nullable | Release head or build version |
| `source_mode` | `String(32)` | `db_backed`, `local_file_inventory`, or `local_migration_comparison` |
| `projection_target` | `String(64)` | `production_current`, `diagnostic`, or `export` |
| `input_watermark` | `JSONB` | Source fact/event/projection refs and timestamps |
| `source_priority` | `JSONB` | Ordered source priority used by the projector |
| `legacy_diagnostics_read` | `Boolean` | Whether legacy artifacts were inspected |
| `legacy_diagnostics_affected_current` | `Boolean` | Must be false for production current projections when DB-backed state is fresh |
| `started_at_ms` | `BIGINT` | Start time |
| `finished_at_ms` | `BIGINT` nullable | Finish time |
| `status` | `String(64)` | `running`, `succeeded`, `failed`, `stale_input`, `blocked` |
| `error_detail` | `Text` nullable | Failure detail |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_projection_runs_source_mode` | `source_mode` in `db_backed`, `local_file_inventory`, `local_migration_comparison` |
| `ck_brc_projection_runs_target` | `projection_target` in `production_current`, `diagnostic`, `export` |
| `ck_brc_projection_runs_prod_db` | `projection_target='production_current'` requires `source_mode='db_backed'` |
| `ck_brc_projection_runs_legacy_current` | `legacy_diagnostics_affected_current=false` when `source_mode='db_backed'`, `projection_target='production_current'`, and `status='succeeded'` |
| `idx_brc_projection_runs_model_time` | `(model_type, started_at_ms)` |
| `idx_brc_projection_runs_owner_status` | `(owner_projector, status)` |

Writer: owner projector for each current projection.

Readers: exporters, validators, server monitor, audit tools.

### `brc_current_projection_ownership`

Purpose: declare the only allowed writer for each current projection.

| Column | Type | Rule |
| --- | --- | --- |
| `projection_key` | `String(160)` PK | Example: `current:goal_status` |
| `model_type` | `String(96)` | Projection type |
| `projection_scope_key` | `String(256)` | Non-null scope key, for example `global`, `strategy_group:MPG-001`, or `strategy_group_symbol:MPG-001:OPUSDT` |
| `owner_projector` | `String(128)` | Only writer allowed to mutate current rows |
| `export_paths` | `JSONB` | Compatibility JSON/MD export paths |
| `legacy_writer_allowed` | `Boolean` | Must be false in production |
| `current_source_mode` | `String(32)` | `db_backed`; diagnostic/local comparison modes must not own production current projections |
| `sunset_condition` | `Text` nullable | Must be null for production current rows; local comparison rows are not production current |
| `updated_at_ms` | `BIGINT` | Last update |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_current_projection_no_legacy_prod` | Production rows require `legacy_writer_allowed=false` |
| `ck_brc_current_projection_scope_key_nonempty` | `projection_scope_key` must be non-empty |
| `uq_brc_current_projection_model_scope` | Unique `(model_type, projection_scope_key)`; this is the one-owner constraint |
| `idx_brc_current_projection_owner` | `(owner_projector, model_type)` |

Writer: migration/admin tooling.

Readers: projection validators and deployment acceptance checks.

### `brc_legacy_diagnostics`

Purpose: preserve old artifact observations without allowing them to set the
main current blocker.

| Column | Type | Rule |
| --- | --- | --- |
| `legacy_diagnostic_id` | `String(192)` PK | Stable diagnostic ID |
| `source_name` | `String(128)` | Example: `pilot_status.watcher_scope_alignment` |
| `diagnostic_type` | `String(96)` | `scope_alignment`, `missing_artifact`, `stale_report`, `runtime_report_mismatch` |
| `strategy_group_id` | `String(128)` nullable | Scope when known |
| `symbol` | `String(128)` nullable | Scope when known |
| `side` | `String(32)` nullable | Scope when known |
| `diagnostic_payload` | `JSONB` | Original diagnostic shape |
| `may_set_current_blocker` | `Boolean` | Must be false for legacy diagnostics |
| `observed_at_ms` | `BIGINT` | Observation time |
| `created_by_projection_run_id` | `String(192)` nullable | Projection that recorded it |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_legacy_diagnostics_no_current_blocker` | `may_set_current_blocker=false` |
| `idx_brc_legacy_diagnostics_scope_time` | `(strategy_group_id, symbol, side, observed_at_ms)` |

Writer: compatibility importers and diagnostics projectors.

Readers: audit tools and developer diagnostics only.

## Runtime Safety And Read Model Tables

### `brc_runtime_safety_state_snapshots`

Purpose: snapshot of live-submit safety state. This is the runtime safety read
model and must fail closed when required facts are missing or stale.

| Column | Type | Rule |
| --- | --- | --- |
| `runtime_safety_snapshot_id` | `String(192)` PK | Stable snapshot ID |
| `action_time_lane_input_id` | `String(192)` nullable | Lane ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` nullable | Symbol |
| `side` | `String(32)` nullable | Side |
| `runtime_profile_id` | `String(128)` nullable | Runtime profile |
| `safety_state` | `String(64)` | `not_ready`, `ready_for_finalgate`, `live_submit_ready`, `blocked_safety`, `market_wait_validated` |
| `submit_allowed` | `Boolean` | True only after all official gates required for this stage |
| `finalgate_ready` | `Boolean` | FinalGate precondition status |
| `operation_layer_ready` | `Boolean` | Operation Layer precondition status |
| `protection_ready` | `Boolean` | Protection status |
| `active_position_conflict` | `Boolean` | Position/open-order conflict |
| `facts_fresh` | `Boolean` | All required trusted facts are within freshness window |
| `trusted_fact_refs_complete` | `Boolean` | Required trusted fact refs exist and match expected surfaces |
| `blockers` | `JSONB` | Blockers |
| `trusted_fact_refs` | `JSONB` | Fact snapshot refs |
| `observed_at_ms` | `BIGINT` | Observation time |
| `valid_until_ms` | `BIGINT` nullable | Expiry |
| `created_at_ms` | `BIGINT` | Insert time |
| `authority_boundary` | `Text` | Boundary statement |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_runtime_safety_submit_allowed` | `submit_allowed=true` requires `safety_state='live_submit_ready'`, `finalgate_ready=true`, `operation_layer_ready=true`, `protection_ready=true`, `active_position_conflict=false`, `facts_fresh=true`, and `trusted_fact_refs_complete=true` |
| `ck_brc_runtime_safety_fact_refs_shape` | `trusted_fact_refs_complete=true` requires non-empty trusted fact refs for required surfaces |
| `idx_brc_runtime_safety_scope_time` | `(strategy_group_id, symbol, side, observed_at_ms)` |
| `idx_brc_runtime_safety_submit` | `(submit_allowed, valid_until_ms)` |

Writer: Runtime Safety State builder.

Readers: Daily Table, Candidate Pool, FinalGate preflight, runtime status
projectors.

### `brc_ticket_bound_protected_submit_attempts`

Purpose: record the official protected submit attempt for exactly one
Action-Time Ticket. This is the first PG table allowed to represent an actual
submit attempt, and it must stay bound to `ticket_id`, `finalgate_pass_id`,
`operation_layer_handoff_id`, `operation_submit_command_id`, and
`runtime_safety_snapshot_id`.

| Column | Type | Rule |
| --- | --- | --- |
| `protected_submit_attempt_id` | `String(192)` PK | Stable attempt ID |
| `ticket_id` | `String(192)` | Action-Time Ticket ref |
| `finalgate_pass_id` | `String(256)` | FinalGate pass ref |
| `operation_layer_handoff_id` | `String(192)` | Operation Layer handoff ref |
| `operation_submit_command_id` | `String(192)` | Unique submit command ref |
| `runtime_safety_snapshot_id` | `String(192)` | Runtime Safety State ref |
| `action_time_lane_input_id` | `String(192)` | Lane ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | `long` or `short` |
| `runtime_profile_id` | `String(128)` | Runtime profile |
| `submit_mode` | `String(64)` | `disabled_smoke` or `real_gateway_action` |
| `status` | `String(64)` | `blocked`, `submit_prepared`, `disabled_smoke_passed`, `submitted`, `submit_failed`, `hard_stopped` |
| `submit_allowed` | `Boolean` | True only when the referenced Runtime Safety State allows submit |
| `blockers` | `JSONB` | Submit blockers |
| `warnings` | `JSONB` | Submit warnings |
| `trusted_fact_refs` | `JSONB` | Copied trusted fact refs from Runtime Safety State |
| `submit_request` | `JSONB` | Ticket-bound entry/protection order request |
| `submit_result` | `JSONB` | Gateway/OrderLifecycle result or disabled-smoke result |
| `identity_evidence` | `JSONB` | Result identity proof and mismatch blockers |
| `official_operation_layer_submit_called` | `Boolean` | Official protected submit boundary was entered |
| `exchange_write_called` | `Boolean` | Real exchange write was attempted/succeeded |
| `order_created` | `Boolean` | Local order objects were created |
| `order_lifecycle_called` | `Boolean` | OrderLifecycle submit/update path was called |
| `withdrawal_or_transfer_created` | `Boolean` | Must remain false |
| `live_profile_changed` | `Boolean` | Must remain false |
| `order_sizing_changed` | `Boolean` | Must remain false |
| `authority_boundary` | `Text` | Boundary statement |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Last update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_ticket_submit_command` | One protected submit attempt per `operation_submit_command_id` |
| `ck_brc_ticket_submit_disabled_no_effects` | `disabled_smoke` cannot set exchange/order lifecycle side effects |
| `ck_brc_ticket_submit_submitted_effects` | `submitted` requires `real_gateway_action`, `submit_allowed=true`, official submit called, exchange write called, and OrderLifecycle called |
| `ck_brc_ticket_submit_no_forbidden_effects` | Withdrawal/transfer, live profile mutation, and order sizing mutation must remain false |
| `idx_brc_ticket_submit_ticket_status` | `(ticket_id, status, created_at_ms)` |
| `idx_brc_ticket_submit_safety` | `(runtime_safety_snapshot_id, status)` |

Writer: ticket-bound protected submit adapter only.

Readers: dispatcher, post-submit reconciliation, budget settlement, Review
Ledger, server monitor, runtime diagnostics.

### `brc_ticket_bound_post_submit_closures`

Purpose: record the official post-submit closure state for exactly one
`protected_submit_attempt_id`. This table does not submit orders and does not
settle budget by itself. It records whether the submitted ticket has entered
protection, reconciliation, settlement, and review closure.

| Column | Type | Rule |
| --- | --- | --- |
| `post_submit_closure_id` | `String(192)` PK | Stable closure ID |
| `protected_submit_attempt_id` | `String(192)` | Unique protected submit attempt ref |
| `ticket_id` | `String(192)` | Action-Time Ticket ref |
| `finalgate_pass_id` | `String(256)` | FinalGate pass ref |
| `operation_layer_handoff_id` | `String(192)` | Operation Layer handoff ref |
| `operation_submit_command_id` | `String(192)` | Submit command ref |
| `runtime_safety_snapshot_id` | `String(192)` | Runtime Safety State ref |
| `action_time_lane_input_id` | `String(192)` | Lane ref |
| `strategy_group_id` | `String(128)` | StrategyGroup |
| `symbol` | `String(128)` | Symbol |
| `side` | `String(32)` | `long` or `short` |
| `status` | `String(64)` | `blocked`, `reconciliation_pending`, `reconciliation_matched`, `settlement_ready`, `review_ready`, `closed` |
| `protection_state` | `String(64)` | `submitted`, `missing`, `failed`, or `unknown` |
| `reconciliation_state` | `String(64)` | `not_checked`, `matched`, `mismatch`, or `blocked` |
| `settlement_state` | `String(64)` | `not_started`, `held_until_position_resolved`, `released`, or `blocked` |
| `review_state` | `String(64)` | `not_recorded`, `recorded`, or `blocked` |
| `first_blocker` | `String(160)` nullable | First post-submit blocker |
| `blockers` | `JSONB` | Current post-submit blockers |
| `submitted_order_refs` | `JSONB` | Submitted entry/protection order refs from the attempt result |
| `reconciliation_evidence` | `JSONB` | Reconciliation refs, empty until real reconciliation runs |
| `settlement_evidence` | `JSONB` | Settlement refs, empty until settlement runs |
| `review_evidence` | `JSONB` | Review refs, empty until review records |
| `next_action` | `Text` | Next official post-submit action |
| `finalgate_called` | `Boolean` | Must remain false |
| `operation_layer_called` | `Boolean` | Must remain false |
| `exchange_write_called` | `Boolean` | Must remain false |
| `order_created` | `Boolean` | Must remain false |
| `order_lifecycle_called` | `Boolean` | Must remain false |
| `withdrawal_or_transfer_created` | `Boolean` | Must remain false |
| `live_profile_changed` | `Boolean` | Must remain false |
| `order_sizing_changed` | `Boolean` | Must remain false |
| `runtime_budget_mutated` | `Boolean` | Must remain false |
| `authority_boundary` | `Text` | Boundary statement |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Last update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_ticket_post_submit_attempt` | One closure row per protected submit attempt |
| `ck_brc_ticket_post_submit_no_effects` | Closure cannot call FinalGate, Operation Layer, exchange write, OrderLifecycle, budget mutation, profile mutation, sizing mutation, withdrawal, or transfer |
| `ck_brc_ticket_post_submit_closed_truth` | `closed` requires submitted protection, matched reconciliation, released settlement, recorded review, and no first blocker |
| `idx_brc_ticket_post_submit_ticket_status` | `(ticket_id, status, created_at_ms)` |
| `idx_brc_ticket_post_submit_scope` | `(strategy_group_id, symbol, created_at_ms)` |

Writer: ticket-bound post-submit closure materializer only.

Readers: post-submit reconciliation, budget settlement, Review Ledger, server
monitor, runtime diagnostics.

### `brc_goal_status_current`

Purpose: current StrategyGroup runtime goal-status projection. This is the
Owner/developer status summary, not a submit authority source.

| Column | Type | Rule |
| --- | --- | --- |
| `goal_status_current_id` | `String(160)` PK | Deterministic current row ID |
| `projection_run_id` | `String(192)` | Projection run ref |
| `status` | `String(96)` | `healthy_waiting`, `fresh_signal_processing`, `temporarily_unavailable`, `blocked`, `unknown` |
| `chain_position` | `String(128)` | Current chain position |
| `top_strategy_group_id` | `String(128)` nullable | Current nearest lane StrategyGroup |
| `top_symbol` | `String(128)` nullable | Current nearest lane symbol |
| `top_side` | `String(32)` nullable | Current nearest lane side |
| `fresh_signal_present` | `Boolean` | True only from current readiness/signal projection |
| `ready_for_real_order_action` | `Boolean` | Must be false unless Runtime Safety State allows submit |
| `selected_strategygroup_scope_ready` | `Boolean` | Scope status from current projection |
| `watcher_liveness_healthy` | `Boolean` | Watcher/coverage status from current projection |
| `runtime_coverage_state` | `String(64)` | `complete`, `partial`, `missing`, `stale`, `unknown` |
| `blockers` | `JSONB` | Main current blockers |
| `legacy_diagnostic_refs` | `JSONB` | Legacy diagnostics observed but not authoritative |
| `source_watermark` | `JSONB` | Candidate Pool/readiness/fact/safety refs |
| `computed_at_ms` | `BIGINT` | Projection time |
| `valid_until_ms` | `BIGINT` nullable | Freshness expiry |
| `authority_boundary` | `Text` | Must state no submit authority |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_goal_status_current_single` | Exactly one current row |
| `ck_brc_goal_status_ready_submit` | `ready_for_real_order_action=true` requires a referenced Runtime Safety State with `submit_allowed=true` |
| `ck_brc_goal_status_legacy_not_blocker` | `legacy_diagnostic_refs` cannot by itself populate `blockers` when current coverage projection is complete |
| `idx_brc_goal_status_status_time` | `(status, computed_at_ms)` |

Writer: Goal Status projector only.

Readers: server monitor, runtime status projectors, diagnostics,
goal-status export.

### `brc_control_read_model_snapshots`

Purpose: store generated read-model payloads before exporting controlled JSON
snapshots.

| Column | Type | Rule |
| --- | --- | --- |
| `read_model_snapshot_id` | `String(192)` PK | Stable snapshot ID |
| `projection_run_id` | `String(192)` nullable | Projection lineage ref |
| `model_type` | `String(96)` | `tradeability_decision`, `candidate_pool`, `daily_live_enablement_table`, `runtime_safety_state`, `goal_status`, `owner_runtime_status` |
| `schema_version` | `String(128)` | Payload schema |
| `status` | `String(96)` | Model-specific status |
| `payload` | `JSONB` | Generated payload |
| `source_watermark` | `JSONB` | Source rows and versions |
| `owner_projector` | `String(128)` | Export/read-model writer |
| `input_watermark` | `JSONB` | Input refs used for this payload |
| `output_path` | `String(512)` nullable | Export path |
| `is_current` | `Boolean` | Current snapshot flag |
| `generated_at_ms` | `BIGINT` | Generated time |
| `generated_by` | `String(128)` | Builder |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_control_read_model_current` | Partial unique current `(model_type)` |
| `idx_brc_control_read_model_type_time` | `(model_type, generated_at_ms)` |

Writer: read-model builders.

Readers: exporters, diagnostics, runtime status projectors.

## Server Monitor Tables

### `brc_server_monitor_runs`

Purpose: production server-side readonly monitor run records.

| Column | Type | Rule |
| --- | --- | --- |
| `monitor_run_id` | `String(192)` PK | Stable run ID |
| `automation_id` | `String(128)` | Monitor identity |
| `runtime_head` | `String(128)` nullable | Runtime git head |
| `started_at_ms` | `BIGINT` | Start time |
| `finished_at_ms` | `BIGINT` nullable | Finish time |
| `status` | `String(64)` | `quiet`, `notify`, `failed`, `degraded` |
| `quiet_reason` | `Text` nullable | Quiet reason |
| `notify_reason` | `Text` nullable | Notify reason |
| `blocker_classes` | `JSONB` | Blockers observed |
| `systemd_status` | `JSONB` | Unit states |
| `source_refs` | `JSONB` | DB/read model refs |
| `forbidden_effects` | `JSONB` | Must stay false |
| `created_at_ms` | `BIGINT` | Insert time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `ck_brc_server_monitor_forbidden_effects` | No FinalGate, Operation Layer, exchange write, order create, profile mutation, sizing mutation |
| `idx_brc_server_monitor_runs_status_time` | `(status, started_at_ms)` |
| `idx_brc_server_monitor_runs_automation` | `(automation_id, started_at_ms)` |

Writer: Tokyo server-side monitor.

Readers: runtime status projectors, notification service, deploy acceptance.

### `brc_server_monitor_notifications`

Purpose: Feishu notification event and dedupe state.

| Column | Type | Rule |
| --- | --- | --- |
| `notification_id` | `String(192)` PK | Stable notification ID |
| `dedupe_key` | `String(256)` | Deterministic dedupe key |
| `automation_id` | `String(128)` | Monitor identity |
| `strategy_group_id` | `String(128)` nullable | StrategyGroup |
| `symbol` | `String(128)` nullable | Symbol |
| `blocker_class` | `String(128)` nullable | Blocker |
| `checkpoint` | `String(128)` | Monitor checkpoint |
| `notification_state` | `String(64)` | `pending`, `sent`, `failed`, `suppressed`, `retrying` |
| `first_seen_at_ms` | `BIGINT` | First observed |
| `last_notified_at_ms` | `BIGINT` nullable | Last sent |
| `last_seen_at_ms` | `BIGINT` | Last observed |
| `send_attempts` | `Integer` | Attempt count |
| `last_error` | `Text` nullable | Send error |
| `feishu_response` | `JSONB` | Response preview |
| `created_at_ms` | `BIGINT` | Insert time |
| `updated_at_ms` | `BIGINT` | Update time |

Checks and indexes:

| Constraint/index | Rule |
| --- | --- |
| `uq_brc_server_monitor_notifications_dedupe` | Unique `dedupe_key` |
| `idx_brc_server_monitor_notifications_state` | `(notification_state, updated_at_ms)` |
| `idx_brc_server_monitor_notifications_scope` | `(strategy_group_id, symbol, blocker_class)` |

Writer: server monitor notifier.

Readers: notifier retry loop, runtime audit.

## Migration Mapping From Current Files

| Current source family | DB target |
| --- | --- |
| Retired StrategyGroup registry seed provenance | Archive-only seed provenance for `brc_strategy_groups`, `brc_strategy_group_versions`, existing strategy family tables |
| Retired StrategyGroup handoff JSON family | `brc_strategy_group_versions`, `brc_required_fact_contracts`, evidence refs |
| Retired runtime tier policy JSON family | `brc_owner_policy_events`, `brc_owner_policy_current` |
| Retired Owner pre-trade authorization JSON family | `brc_owner_policy_events`, `brc_owner_policy_current`, `brc_strategy_group_candidate_scope`, `brc_runtime_scope_bindings` |
| `DEFAULT_CANDIDATE_UNIVERSE` in scripts | `brc_strategy_group_candidate_scope` |
| `DEFAULT_SIDE_SCOPE` and broad side fallbacks in scripts | `brc_strategy_group_candidate_scope`, `brc_candidate_scope_event_bindings` |
| Retired active-observation latest export family | `brc_watcher_runtime_coverage`, `brc_pretrade_readiness_rows` |
| Retired public/account fact latest export family | `brc_runtime_fact_snapshots` |
| Retired Tradeability latest export family | `brc_control_read_model_snapshots` export |
| Retired Candidate Pool latest export family | `brc_pretrade_readiness_rows`, `brc_promotion_candidates`, `brc_action_time_lane_inputs`, plus explicit export |
| Retired Daily Table latest export family | `brc_control_read_model_snapshots` explicit export |
| server `strategygroup-runtime-goal-status.json` | `brc_goal_status_current` plus export |
| projection run metadata currently implicit in script execution | `brc_projection_runs`, `brc_current_projection_ownership` |
| legacy report diagnostics such as `pilot_status.watcher_scope_alignment` | `brc_legacy_diagnostics` |
| server monitor dedupe JSON | `brc_server_monitor_notifications` |
| server monitor latest JSON | `brc_server_monitor_runs` plus export |

## Implementation Batches

### Batch 1: P0 Source-Of-Truth Closure

Tables:

- `brc_projection_runs`;
- `brc_current_projection_ownership`;
- `brc_owner_policy_events`;
- `brc_owner_policy_current`;
- `brc_strategy_group_candidate_scope`;
- `brc_runtime_scope_bindings`;
- `brc_watcher_runtime_coverage`;
- `brc_goal_status_current`.

Acceptance:

- Candidate universe no longer comes from code constants;
- Owner pre-trade authorization no longer comes from hand-edited docs JSON as
  runtime source;
- server runtime coverage has per-symbol rows;
- Goal Status has one owner projector and cannot be overwritten by legacy
  post-step or product-state refresh paths.

### Batch 2: P1 Strategy And Facts Closure

Tables:

- `brc_strategy_groups`;
- `brc_strategy_group_versions`;
- `brc_required_fact_contracts`;
- `brc_runtime_fact_snapshots`;
- `brc_live_signal_events`.

Acceptance:

- Strategy semantics and RequiredFacts are versioned;
- RequiredFacts are machine-evaluable with explicit operator/value/disable
  fields, not free-text `expected_condition` authority;
- fact snapshots have source and freshness;
- fresh signal events are stored as events, not inferred from output file
  presence.

### Batch 3: P1 Promotion And Action-Time Closure

Tables:

- `brc_pretrade_readiness_rows`;
- `brc_promotion_candidates`;
- `brc_action_time_lane_inputs`;
- `brc_budget_reservations`;
- `brc_protection_references`;
- `brc_action_time_tickets`;
- `brc_runtime_safety_state_snapshots`.

Acceptance:

- five active StrategyGroups have per-symbol readiness rows;
- fresh satisfied candidates promote without exchange-write authority;
- at most one open real-submit action-time lane input exists;
- budget reservations can be created before ticket creation without circular
  dependency and must bind to the ticket before FinalGate;
- ticket, lane, promotion, and live-signal status transitions follow explicit
  legal transition graphs and write audit events.

### Batch 4: P1/P2 Read Models And Monitor

Tables:

- `brc_control_read_model_snapshots`;
- `brc_server_monitor_runs`;
- `brc_server_monitor_notifications`.

Acceptance:

- Daily Table and Candidate Pool are exports from DB-backed read models;
- Tokyo server monitor owns production quiet/notify;
- Feishu dedupe no longer depends on local cache files.

## Safety Constraints

Every non-execution table in this design must preserve these invariants:

| Invariant | Required behavior |
| --- | --- |
| No FinalGate bypass | No row can imply FinalGate has passed unless it references official FinalGate evidence |
| No Operation Layer bypass | No row can create Operation Layer authority |
| No exchange write | Policy, readiness, promotion, monitor, and read-model rows cannot create orders |
| No stale-fact submit | Runtime Safety State must fail closed when required fact snapshots are stale |
| No duplicate submit | Single active action-time real-submit lane and idempotency checks remain mandatory |
| No scope expansion by import | Seed/import tools must not silently expand symbol, side, notional, leverage, or profile |
| No local monitor fallback | Production monitor state comes from Tokyo server-side DB/read-model path |

## Minimal Repository Read Shape

The DB-backed repository should assemble one control state object with this
shape for builders:

```json
{
  "strategy_groups": [],
  "strategy_group_versions": [],
  "required_fact_contracts": [],
  "strategy_side_event_specs": [],
  "strategy_event_required_facts": [],
  "owner_policy_events": [],
  "owner_policy_current": [],
  "candidate_scope": [],
  "candidate_scope_event_bindings": [],
  "runtime_scope_bindings": [],
  "execution_policies": [],
  "watcher_runtime_coverage": [],
  "runtime_fact_snapshots": [],
  "live_signal_events": [],
  "pretrade_readiness_rows": [],
  "promotion_candidates": [],
  "action_time_lane_inputs": [],
  "budget_reservations": [],
  "protection_references": [],
  "action_time_tickets": [],
  "action_time_ticket_events": [],
  "runtime_safety_state": [],
  "goal_status_current": {},
  "projection_runs": [],
  "current_projection_ownership": [],
  "control_read_model_snapshots": [],
  "server_monitor_runs": [],
  "server_monitor_notifications": []
}
```

Builders may export JSON/MD, but must not mutate policy, runtime scope, live
profiles, sizing defaults, or exchange state.

## Chain Position

```text
chain_position: runtime_control_state_table_design
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: db_schema_design
first_blocker: policy, candidate universe, runtime coverage, and generated read models still have mixed file and code sources
next_action: implement P0 repository boundary and migrate owner policy plus candidate universe tables first
stop_condition: Candidate Pool, Daily Table, and server monitor consume DB/repository state and JSON output becomes export-only
owner_action_required: no
authority_boundary: schema work is non-executing and must not call FinalGate, Operation Layer, or exchange write
```
