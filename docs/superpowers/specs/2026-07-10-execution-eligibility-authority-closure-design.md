# Execution Eligibility Authority Closure Design

> **Status:** Owner-approved direction, written-spec review gate before implementation planning

## Purpose

This specification closes the first confirmed P0 authority leak in the current
pre-trade runtime:

```text
observe-only StrategyFamilySignalOutput
-> PG live signal event
-> promotion candidate
-> real-submit action-time lane
-> ticket / Runtime Safety State / protected submit
```

The implementation must make **signal grade** and **required execution mode**
first-class, fail-closed authority facts from detector output through protected
submit. It must not optimize any StrategyGroup, grant a new signal grade, change
live profile, change sizing, or call the exchange.

## Current Evidence

The current domain output already carries:

```text
required_execution_mode = observe_only
not_order = true
not_execution_intent = true
```

The watcher summary preserves `required_execution_mode`, but the PG live-signal
writer selects every `would_enter` summary without using that field. The
subsequent PG promotion, lane, ticket, Runtime Safety State, submit-mode decision,
and protected-submit tables do not carry an immutable execution-eligibility
envelope.

Tokyo current state at the audit checkpoint contained 54 live-signal rows, all
with `required_execution_mode=observe_only`. Those rows had already produced
promotion, lane, ticket, handoff, and Runtime Safety State history. There was no
current real submit, position, or protection set at the checkpoint.

## Scope Decomposition

The full audit identified three dependent subprojects. They must not be merged
into one implementation batch.

| Order | Subproject | This specification |
| --- | --- | --- |
| **P0-1** | **Execution eligibility authority closure** | In scope |
| **P0-2** | **Durable exchange command and unknown-outcome recovery** | Separate specification after P0-1 review |
| **P0-3** | **Process outcome, current projection, and lifecycle-monitor closure** | Separate specification after P0-2 design |

This specification deliberately stops after P0-1. It may reveal that every
current active evaluator is observe-only; that is a correct fail-closed result,
not a reason to silently promote a signal grade.

## Alternatives

### Option A: Patch The Watcher Only

Reject `required_execution_mode=observe_only` inside
`runtime_active_observation_monitor.py` and leave downstream schemas unchanged.

**Advantage:** smallest change.

**Rejected because:** a different writer, seed, migration, API, or future
projector could recreate the same leak. The submit boundary would still have no
independent proof of execution eligibility.

### Option B: End-To-End Authority Envelope

Add typed signal-grade semantics, persist them as first-class PG columns, copy
and verify them at every authority transition, bind them into ticket identity,
and recheck them at Runtime Safety State and protected submit.

**Advantage:** closes the problem class instead of one producer; supports future
trial-grade and production-grade signals without changing the authority model.

**Cost:** one migration and coordinated changes across the vertical action-time
slice.

**Decision:** recommended and approved direction.

### Option C: Replace The Whole Pre-Trade Runtime

Build a new signal/event/ticket state machine and retire the current PG chain.

**Advantage:** clean-sheet semantics.

**Rejected because:** unnecessarily large blast radius; duplicates already valid
ticket, budget, protection, FinalGate, and Operation Layer identities. The core
abstractions should be extended, not shadowed by a second runtime.

## Core Decision

### Signal Grade

Introduce one strict enum with these values:

| Value | Meaning | May enter real-submit promotion |
| --- | --- | ---: |
| `observe_only_signal` | Live or replay observation for review, parity, and fact repair | No |
| `trial_grade_signal` | Signal may enter a scoped small-capital official path when all downstream gates pass | Yes |
| `production_grade_signal` | Signal may enter a production-grade official path when all downstream gates pass | Yes |
| `invalid_signal` | Invalid detector output or unusable identity | No |

### Required Execution Mode

Introduce one strict enum with these values:

| Value | Meaning | Eligibility |
| --- | --- | --- |
| `observe_only` | Observation and review only | False |
| `trial_live` | Scoped trial path may continue | True |
| `production_live` | Production-grade path may continue | True |

The valid mapping is:

```text
observe_only_signal -> observe_only
trial_grade_signal -> trial_live
production_grade_signal -> production_live
invalid_signal -> observe_only and rejected lifecycle state
```

No implicit mapping is allowed. Missing, unknown, or mismatched values fail
closed.

### Versioned Authority Source

The evaluator output cannot authorize itself. The current versioned
`brc_strategy_side_event_specs` row declares the maximum signal grade and
required execution mode allowed for that event spec.

The evaluator output must match that declaration or be more restrictive:

```text
event spec declared grade/mode
and evaluator output grade/mode
-> exact match or evaluator downscope
-> never evaluator upgrade
```

An observe-only event spec cannot become trial- or production-eligible because
an evaluator, watcher, Owner policy row, or runtime scope says otherwise. A
future grade promotion requires a new reviewed StrategyGroup/event-spec version
and matching evaluator semantics.

### Signal-Is-Not-Order Invariant

`not_order=true` and `not_execution_intent=true` remain valid for every signal
grade. A signal is never an order or execution intent. Trial or production
eligibility only means the signal may enter the existing promotion and
action-time chain, where ticket, facts, budget, FinalGate, Operation Layer,
protection, account, exchange, and duplicate-submit gates remain mandatory.

## Authority Envelope

The following immutable fields form the P0-1 authority envelope:

```text
signal_grade
required_execution_mode
execution_eligible
strategy_group_id
strategy_group_version_id
event_spec_id
signal_event_id
event_time_ms
authority_source_ref
```

`execution_eligible` is derived, never independently granted:

```text
execution_eligible =
  event spec declares an eligible grade/mode
  and evaluator output matches that grade/mode
  and signal_grade in {trial_grade_signal, production_grade_signal}
  and required_execution_mode in {trial_live, production_live}
  and grade/mode mapping is valid
```

Owner policy, runtime scope, Runtime Safety State, and submit-mode policy may
further restrict this value. They cannot turn `false` into `true`.

## Data Model

### Existing Tables To Extend

Add first-class columns to:

| Table | Required additions |
| --- | --- |
| `brc_strategy_side_event_specs` | `declared_signal_grade`, `declared_required_execution_mode`, `execution_eligibility_enabled` |
| `brc_live_signal_events` | `signal_grade`, `required_execution_mode`, `execution_eligible`, `authority_source_ref` |
| `brc_promotion_candidates` | copied grade/mode/eligibility plus source signal ref |
| `brc_action_time_lane_inputs` | copied grade/mode/eligibility plus source promotion ref |
| `brc_action_time_tickets` | copied grade/mode/eligibility; values included in `ticket_hash` and version hash |
| `brc_runtime_safety_state_snapshots` | copied grade/mode/eligibility; `submit_allowed=true` requires eligibility |
| `brc_ticket_bound_submit_mode_decisions` | copied grade/mode/eligibility; real decision requires eligibility |
| `brc_ticket_bound_protected_submit_attempts` | copied grade/mode/eligibility; real submit preparation requires eligibility |

Do not add a generic JSON authority document, adapter table, compatibility
packet, or second source of truth.

### Migration Semantics

The next migration follows current migration `103` and uses sequence `104`.

The production deployment is a bounded maintenance-window migration. This is a
single-Owner, low-frequency runtime, so P0-1 must not add online dual-write,
rolling-schema compatibility, shadow tables, or zero-downtime cutover machinery.
The deploy sequence is:

```text
verify no unresolved submitted order lifecycle
-> stop watcher / dispatcher / lifecycle timer
-> apply migration 104 and fail-closed backfill
-> deploy the matching application revision
-> run read-only schema and current-state checks
-> restart timers
```

If the pre-stop lifecycle check finds an unresolved submitted order, the deploy
stops before migration. The runtime may remain unavailable during this short
maintenance window; availability is not traded against execution authority.

Migration rules:

1. Existing event-spec rows are backfilled to `observe_only_signal`,
   `observe_only`, and `execution_eligibility_enabled=false`; P0-1 does not
   silently promote any active StrategyGroup semantics.
2. Existing signal rows are backfilled to `observe_only_signal`,
   `observe_only`, and `execution_eligible=false` unless a future explicitly
   versioned migration has authoritative evidence for another value.
3. Existing downstream rows inherit the source signal values where lineage is
   complete; missing or ambiguous lineage becomes ineligible.
4. Historical terminal rows remain historical and are not rewritten as if they
   had trial or production authority.
5. Any open promotion, lane, ticket, safety snapshot, submit decision, or submit
   attempt whose source is ineligible must fail closed on the next read or
   materialization pass.
6. The migration performs no exchange call, profile mutation, sizing mutation,
   policy expansion, or recurring file write.

### Database Constraints

Constraints must enforce at least:

```text
observe_only -> execution_eligible = false
invalid_signal -> execution_eligible = false
event spec eligibility disabled -> signal execution_eligible = false
signal grade/mode cannot exceed event spec declaration
execution_eligible = true -> valid grade/mode mapping
open live-submit promotion -> execution_eligible = true
open real-submit lane -> execution_eligible = true
active ticket progression -> execution_eligible = true
Runtime Safety submit_allowed = true -> execution_eligible = true
real_gateway_action decision -> execution_eligible = true
submit_prepared/submitted real attempt -> execution_eligible = true
```

Terminal historical rows may retain their lifecycle status while remaining
ineligible.

## Runtime Flow

```text
StrategyFamilySignalOutput
-> load versioned event-spec grade/mode declaration
-> validate exact match or evaluator downscope
-> write PG live signal with Authority Envelope
-> promotion retains observe-only evidence but excludes ineligible signal
-> lane copies and verifies envelope
-> ticket copies envelope and includes it in ticket hash
-> Runtime Safety State rechecks current ticket lineage and expiry
-> SubmitModeDecision rechecks envelope
-> protected submit independently rechecks envelope
```

No downstream component may infer eligibility from any of these alone:

```text
would_enter
source_kind=live_market
facts_validated
freshness_state=fresh
owner policy enabled
runtime scope live_submit_allowed
Runtime Safety snapshot copied from another lane
```

## Failure Semantics

This subproject uses precise domain blockers:

| Failure | Blocker |
| --- | --- |
| Missing grade or mode | `schema_invalid` with exact field detail |
| Invalid grade/mode pair | `schema_invalid` with mapping detail |
| Event-spec/evaluator authority mismatch | `schema_invalid` with `signal_execution_authority_mismatch` detail |
| Observe-only event is present | No process failure; retain observation, exclude promotion, and classify the lane `action_time_boundary_not_reproduced` |
| Downstream envelope differs from source | `hard_safety_stop` with `authority_lineage_mismatch` detail |
| Runtime Safety source expired or wrong identity | existing freshness/identity blocker plus `submit_allowed=false` |

P0-1 does not redesign CLI exit codes. Business-block versus process-health
separation is P0-3. P0-1 must still preserve the exact blocker in PG and must
not call the exchange. The narrow observe-only path must return a successful
process outcome because it is a valid observation result, not a failed
promotion attempt.

## Affected Code Boundaries

Expected implementation surface:

```text
src/domain/strategy_family_signal.py
migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py
scripts/runtime_active_observation_monitor.py
src/application/action_time/promotion_action_time_lane.py
src/application/action_time/action_time_ticket.py
src/application/action_time/runtime_safety_state.py
src/application/action_time/protected_submit_attempt.py
src/application/readmodels/strategy_live_candidate_pool.py
tests/unit/test_strategy_family_signal_contract.py
tests/unit/test_runtime_active_observation_monitor.py
tests/unit/test_pg_promotion_action_time_lane_materialization.py
tests/unit/test_action_time_ticket_materialization.py
tests/unit/test_ticket_bound_runtime_safety_state_materialization.py
tests/unit/test_ticket_bound_protected_submit_attempt.py
tests/unit/test_strategy_live_candidate_pool.py
```

`src/infrastructure/exchange_gateway.py`, live profiles, owner policy rows,
sizing defaults, FinalGate implementation, Operation Layer implementation, and
Tokyo environment files are forbidden for this subproject.

## Test Design

### Required Negative Tests

1. `would_enter + observe_only` writes observation lineage but cannot create an
   eligible promotion.
2. `live_market + fresh + facts_validated` remains ineligible when the mode is
   observe-only.
3. Observe-only exclusion is a successful watcher/process outcome and does not
   make the systemd unit fail.
4. Candidate Pool reclassifies an observe-only event-spec lane as
   `action_time_boundary_not_reproduced`, not `market_wait_validated`.
5. Missing grade or mode fails closed.
6. Unknown grade or mode fails model or DB validation.
7. Grade/mode mismatch fails closed.
8. An evaluator cannot exceed the versioned event-spec declaration.
9. A forged promotion, lane, ticket, or Runtime Safety row with mismatched
   envelope cannot advance.
10. `submit_allowed=true` cannot be persisted for an ineligible ticket.
11. A real submit-mode decision cannot be created for an ineligible ticket.
12. Protected submit rejects an ineligible ticket even when upstream booleans are
   forged true.
13. Existing event specs and rows migrated without explicit authority become
    observe-only.

### Required Positive Tests

1. A typed trial-grade fixture may reach a non-executing promotion/lane/ticket
   rehearsal with the envelope unchanged.
2. A typed production-grade fixture may reach Runtime Safety evaluation, while
   exchange write remains absent in unit tests.
3. Ticket hash changes when grade or execution mode changes.
4. Disabled-smoke remains exchange-write free for eligible fixtures.

### Regression Scope

Run the focused signal/watcher/action-time/submit suites first. Before completion,
run the current 212-test audit subset and the production file-I/O/output-scope
validators. A long repository-wide suite requires a separate explicit run
decision.

## Cadence And Performance

| Dimension | Required impact |
| --- | --- |
| **Cadence** | Per watcher signal write and per action-time materialization only |
| **No-signal tick files** | `0` JSON/MD files |
| **PG row growth** | No new recurring table; only added columns on rows already written |
| **CPU** | Constant-time enum and lineage comparisons |
| **Disk** | No new report, trace, JSONL, or sidecar file |
| **Timeout** | No new subprocess, HTTP, or exchange call |
| **Retention** | Existing table retention rules remain unchanged |

## Rollback

Code rollback may disable action-time progression, but must not restore missing
authority fields or infer eligibility from old JSON payloads.

Allowed rollback:

```text
keep new columns
set execution_eligible=false
stop promotion/ticket/submit progression
forward-fix application logic
```

Forbidden rollback:

```text
remove the hard submit recheck while old rows exist
fall back to signal_payload JSON as authority
treat would_enter as execution eligible
grant eligibility from Owner policy alone
```

## Acceptance

P0-1 is complete only when:

1. Every existing event spec and signal without explicit eligible authority is
   classified observe-only after migration.
2. Observe-only signals cannot create or reuse an open real-submit promotion,
   lane, ticket, Runtime Safety submit allowance, real submit decision, or
   protected submit preparation.
3. Observe-only rows remain valid observation evidence, are excluded from
   promotion without process failure, and surface
   `action_time_boundary_not_reproduced` instead of market wait.
4. Trial/production fixtures preserve grade and mode unchanged through the
   vertical chain.
5. Protected submit independently fails closed on missing, observe-only,
   expired, or mismatched authority lineage.
6. No exchange call, live profile change, sizing change, policy expansion, or
   recurring file output is introduced.

Local implementation acceptance requires migration tests, focused vertical
tests, the existing 212-test audit subset, and file-I/O/output-scope validation.
Deployment acceptance additionally requires Tokyo migration verification and a
read-only proof that no observe-only row is current in a real-submit-capable
promotion, lane, ticket, Runtime Safety, decision, or attempt state.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: active five StrategyGroups
symbol: active PG candidate universe
stage: execution_eligibility_schema_closure
first_blocker: schema_invalid because signal grade and required execution mode are not first-class immutable authority fields through promotion, ticket, Runtime Safety State, and protected submit
evidence: current observe-only StrategyFamilySignalOutput rows have traversed PG promotion/lane/ticket/safety history while protected submit policy is armed
next_action: implement P0-1 Authority Envelope migration and fail-closed vertical checks
stop_condition: observe-only and missing/mismatched authority cannot reach any real-submit-capable current state, and eligible fixtures preserve exact lineage without exchange write
owner_action_required: no for local implementation and tests; yes only for any production policy/config change
authority_boundary: no signal-grade promotion, no live profile/sizing mutation, no FinalGate or Operation Layer bypass, no exchange write
```

## Post-P0-1 Boundary

After P0-1 is accepted, the next specification is P0-2 Durable Exchange Command
and Unknown Outcome Recovery. No active StrategyGroup evaluator is promoted to
trial or production grade as part of P0-1; StrategyGroup-specific semantic
promotion remains a later explicit policy and strategy-version decision.
