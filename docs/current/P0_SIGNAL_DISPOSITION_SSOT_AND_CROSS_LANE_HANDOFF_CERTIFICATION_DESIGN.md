---
title: P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_DESIGN
status: PROPOSED_FOR_OWNER_CONFIRMATION
authority: docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_DESIGN.md
last_verified: 2026-07-13
---

# P0 Signal Disposition SSOT And Cross-Lane Handoff Certification

## Executive Decision

The next medium-scale P0 mainline should replace repeated interpretation of
strategy evaluation output with one typed `SignalDispositionDecision`, then
certify the conservation invariant across all current StrategyGroups, candidate
lanes, Event Specs, and pre-Ticket boundaries.

This is not a CPM/SOL special case. It is one shared production-chain repair:

```text
raw live facts
-> pure strategy evaluation
-> one SignalDispositionDecision
-> transparent API transport
-> PG signal projector
-> named signal or exact lane-scoped process outcome
-> promotion
-> single action-time lane
-> Ticket or exact lane-scoped process outcome
```

The design does not change strategy thresholds, strategy direction semantics,
candidate scope, capital, leverage, sizing, runtime profile, FinalGate,
Operation Layer, protection, or exchange-write authority.

## Problem Statement

Production acceptance on 2026-07-13 captured this shape:

```text
StrategyGroup = CPM-RO-001
symbol = SOLUSDT
side = short
nested evaluator signal_type = would_enter
outer runtime status = waiting_for_signal
signal_event_ids = []
PG outcome = pg_live_signal_event_materialization_failed:
             runtime_summary_blocked:waiting_for_signal
```

The previous P0 made this contradiction durable and Owner-visible. It did not
remove the contradiction's producer-side cause.

The current shared path interprets the same result repeatedly:

| Layer | Current interpretation | Risk |
| --- | --- | --- |
| Evaluation service | Uses signal type, side, semantics binding, output mismatches, and blockers | Most complete result, but no single downstream disposition |
| Observation Cycle API | Collapses every non-ready evaluation to `waiting_for_signal` with one generic blocker | Engineering, observe-only, invalid, and market-negative outcomes lose their distinct meaning |
| Active observation monitor | Extracts nested `signal_type=would_enter` independently of the outer status | Can reconstruct a candidate that the API simultaneously calls waiting |
| PG signal materializer | Rechecks runtime status, blockers, Event Spec authority, facts, and freshness | Sees contradictory upstream fields and must guess which is authoritative |
| Watcher / server monitor | Infers readiness or failure from PG write results | Can conserve the contradiction but cannot resolve it |

This violates the project principle that one current fact has one owner
projector and one business meaning.

## Objective Facts And Bounded Inferences

### Objective Facts

1. All five active mainline StrategyGroups use the shared runtime strategy
   evaluation service, Observation Cycle API, active observation monitor, and
   PG live-signal materializer.
2. The current WIP covers five StrategyGroups, 22 candidate lanes, and six
   current Event Specs.
3. The Observation Cycle API currently maps every evaluation result other than
   `READY_FOR_SEMANTIC_BINDING` to outer `waiting_for_signal`.
4. The monitor separately extracts nested `signal_type=would_enter`.
5. Promotion already rejects `execution_eligible != true`.
6. Promotion and Ticket sequence code already writes PG process outcomes, but
   existing code presence is not proof that every missing downstream object is
   explained per lane.

### Bounded Inferences

1. The defect class can affect every lane using the shared path; this does not
   prove that all 22 lanes have already failed in production.
2. The confirmed CPM/SOL/short event may be an evaluation mismatch, an
   observe-only result, or another exact evaluator blocker hidden by the API's
   generic status. The implementation must recover the exact nested reason
   before classifying the event.
3. Signal-to-Promotion, Promotion-to-Lane, and Lane-to-Ticket are risk-adjacent
   boundaries. They are in certification scope, but they are not declared
   defective until the RED conservation census proves a violation.

## Alternatives

| Option | Scope | Benefit | Cost / risk | Decision |
| --- | --- | --- | --- | --- |
| CPM/SOL conditional patch | Ignore or rewrite `waiting_for_signal` for one lane | Fast local change | Leaves all other lanes and duplicate interpretation intact; may wrongly advance a blocked result | Reject |
| Observation API mapping repair only | Preserve more exact outer statuses | Removes one information-loss point | Monitor and materializer still rederive meaning from multiple fields | Reject as incomplete |
| Typed Signal Disposition plus cross-lane certification | One disposition owner; API transports; PG projector executes; adjacent boundaries are certified | Removes the root ambiguity without redesigning the full lifecycle | Medium-scale coordinated change and broad regression | Adopt |
| Full Ticket / Order lifecycle state-machine rewrite | Unify every lifecycle state now | Broadest long-term cleanup | Delays trading feedback and expands beyond the exposed pre-trade defect | Defer |

## Architectural Boundary

### What Is Being Replaced

The new core abstraction replaces these independent decisions:

```text
API: evaluation ready? else waiting_for_signal
monitor: nested signal_type == would_enter?
materializer: would_enter + runtime status + blockers?
watcher: ready count + PG write count?
```

They become:

```text
evaluation result
-> resolve one SignalDispositionDecision
-> every consumer switches on decision.disposition
```

This is not a compatibility adapter or a second readiness layer. The old
re-derivation paths are deleted in the same release. A missing disposition is
fail-closed as `signal_disposition_missing`; production must not reconstruct it
from legacy combinations.

### What Is Not Being Replaced

The following remain separate authorities because they answer different
questions:

| Authority | Question |
| --- | --- |
| Signal disposition | What did the strategy evaluation mean, and may a named signal event be projected? |
| Event Spec execution eligibility | Is this named signal grade/mode within the versioned Event Spec upper bound? |
| Promotion | Which fresh execution-eligible signal wins arbitration? |
| Runtime Safety State | Is real submit safe at action time? |
| FinalGate | Does the fully materialized Ticket pass final checks? |
| Operation Layer | May the official gateway action execute? |

`SignalDispositionDecision` never grants trade/order authority.

## Typed Signal Disposition Contract

### Enum

```python
class SignalDisposition(str, Enum):
    COMPUTED_NOT_SATISFIED = "computed_not_satisfied"
    OBSERVE_ONLY_SIGNAL = "observe_only_signal"
    MATERIALIZATION_CANDIDATE = "materialization_candidate"
    ENGINEERING_BLOCKED = "engineering_blocked"
    INVALID_SIGNAL = "invalid_signal"
```

`MATERIALIZATION_CANDIDATE` is intentionally not named
`EXECUTION_ELIGIBLE_SIGNAL`. Final execution eligibility requires the PG
candidate-scope/Event-Spec upper bound, which is not owned by the pure evaluator.

### Value Object

```python
class SignalDispositionDecision(StrategyFamilySignalModel):
    disposition: SignalDisposition
    first_blocker: str | None = None
    blockers: list[str] = Field(default_factory=list)
    may_materialize_signal_event: bool
    next_action: str
    source_stage: Literal["runtime_strategy_signal_evaluation"]
    not_execution_authority: Literal[True] = True
```

The model is embedded in `RuntimeStrategySignalEvaluationResult`. It is
serialized through the existing API payload and copied into the PG signal
payload or PG process outcome lineage.

### Decision Matrix

| Evaluation fact | Disposition | Named PG signal may be attempted | Process outcome | Owner opportunity language |
| --- | --- | ---: | --- | ---: |
| Evaluator completed and returned `no_action`, `would_exit`, `would_reduce`, or `would_cancel` | `computed_not_satisfied` | No | No failure row | No |
| Evaluator returned valid `would_enter`, but grade/mode is explicitly observe-only | `observe_only_signal` | Yes, as named non-execution-eligible observation identity | Success/noop or exact projection failure | No |
| Evaluator returned valid `would_enter`, supported side, and non-observe-only grade/mode | `materialization_candidate` | Yes | Success or exact projection failure | Only after PG Event Spec resolves `execution_eligible=true` |
| Missing binding/evaluator, output mismatch, unsupported side, missing required output field, or another repairable producer defect | `engineering_blocked` | No | Exact lane-scoped failure | No |
| Evaluator output or data-quality contract is invalid | `invalid_signal` | No | Exact invalid-signal failure | No |

### Invariants

1. Exactly one disposition exists for every completed evaluation result.
2. `computed_not_satisfied` has no engineering blocker and creates no signal
   materialization process failure.
3. `observe_only_signal` can preserve named observation identity but always has
   `execution_eligible=false` and cannot enter promotion.
4. `materialization_candidate` does not guarantee execution eligibility; it
   requires Event Spec authority resolution in the PG projector.
5. `engineering_blocked` and `invalid_signal` must carry `first_blocker`.
6. A missing disposition is an engineering blocker, never market wait.
7. `waiting_for_signal` is an API/Owner projection of
   `computed_not_satisfied`, not an independent business status.

## API Contract

The Observation Cycle API must transport the decision without independently
inspecting `signal_type`.

| Disposition | Outer API status | Outer blockers | Next step |
| --- | --- | --- | --- |
| `computed_not_satisfied` | `waiting_for_signal` | `[]` | `observe_next_closed_bar` |
| `observe_only_signal` | `signal_evaluated_observe_only` | `[]` | `record_named_observation_signal` |
| `materialization_candidate` | `ready_for_signal_materialization` | `[]` | `materialize_pg_live_signal_event` |
| `engineering_blocked` | `blocked` | Exact disposition blockers | Exact repair action |
| `invalid_signal` | `blocked` | Exact invalid reason | `repair_invalid_signal_contract` |

The API must no longer emit the generic
`strategy_signal_not_ready_for_action_time_ticket` blocker for every non-ready
result. No-action is not a blocker; engineering and invalid results preserve
their exact blockers.

## PG Signal Projection Contract

### Input

The active observation monitor preserves these fields per runtime summary:

```text
runtime_instance_id
strategy_group_id
strategy_family_version_id
symbol
side
signal_disposition
signal_input_ref
evaluation output
evaluation blockers
```

The projector selects work from `signal_disposition`, not from
`signal_type=would_enter` alone.

### Projection Results

| Disposition | PG result |
| --- | --- |
| `computed_not_satisfied` | No `brc_live_signal_events`; no `live_signal_materialization` failure |
| `observe_only_signal` | Named PG signal identity allowed; Event Spec/evaluator resolution must produce `execution_eligible=false` |
| `materialization_candidate` | Named PG signal identity on valid scope/Event Spec/facts/freshness; otherwise exact lane failure |
| `engineering_blocked` | No signal; lane-scoped `live_signal_materialization` failure with exact first blocker |
| `invalid_signal` | No signal; lane-scoped invalid-signal process outcome |
| missing/unknown disposition | No signal; `signal_disposition_missing` or `signal_disposition_unknown` engineering failure |

The signal payload records the disposition for audit. Existing
`brc_runtime_process_outcomes` remains the failure/current-outcome store; no
table or migration is required unless implementation proves an unavoidable
typed-column need.

## Cross-Boundary Conservation Invariant

Every pre-Ticket boundary must satisfy:

```text
upstream object says may advance
-> downstream object exists
OR
-> exact PG process outcome exists for the same lane and source watermark
```

### Boundary Matrix

| Boundary | Upstream advance fact | Required downstream fact | Allowed alternative |
| --- | --- | --- | --- |
| Evaluation -> Signal | disposition is observe-only or materialization candidate | named signal event | exact `live_signal_materialization` outcome |
| Signal -> Promotion | fresh signal has `execution_eligible=true` | promotion candidate | exact `promotion_action_time_lane` lane outcome |
| Promotion -> Lane | promotion status is `arbitration_won` | action-time lane | exact arbitration/terminal/failure outcome |
| Lane -> Ticket | lane is open/current and ticket-pending | Action-Time Ticket | exact `action_time_ticket_sequence` lane outcome |
| Ticket -> FinalGate input | Ticket is current and facts are fresh | non-executing FinalGate preflight input/result | exact action-time/safety blocker |

The implementation starts with a RED census over all five boundaries before
changing production code. A proven violation sharing the duplicate-status root
cause joins this task. A different Owner-policy or hard-safety blocker remains
separate and is recorded precisely rather than bypassed.

## Cross-Strategy Certification Matrix

### Required Scope

| Dimension | Required coverage |
| --- | --- |
| StrategyGroups | `CPM-RO-001`, `MPG-001`, `MI-001`, `SOR-001`, `BRF2-001` |
| Candidate lanes | All 22 current `StrategyGroup + symbol + side` rows from PG/current fixtures |
| Event Specs | All six current versioned Event Specs |
| Dispositions | All five dispositions |
| Temporal cases | First observation, duplicate identity, expired observation, terminal prior identity, later same-lane success |
| Fact cases | Satisfied, computed false, missing, stale, malformed, conflict |

### Required Negative Assertions

The suite must reject every occurrence of:

```text
would_enter + waiting_for_signal
ready + no signal_event_id + no exact process outcome
observe_only + promotion candidate
observe_only + Owner opportunity notification
execution_eligible signal + no promotion and no process outcome
winning promotion + no lane and no process outcome
open lane + no Ticket and no process outcome
expired/terminal identity reopened as current
engineering failure + market_wait_validated
```

Production-shaped tests must start from raw evaluator inputs or typed in-memory
fixtures. They must not inject a privileged downstream-complete dictionary that
bypasses the producer contract.

## Replay / Live Parity

Replay and Live must call the same pure disposition resolver. They may use
different fact sources, but they may not map the same typed evaluator result to
different dispositions.

Replay remains non-authority. It may certify rule parity and disposition
mapping; it cannot create live signal identity, promotion, Ticket, FinalGate
evidence, Operation Layer authority, or exchange writes.

## Blocker Classification

| Condition | Contract class |
| --- | --- |
| Valid evaluation with false strategy facts | `computed_not_satisfied` |
| Valid observe-only would-enter | `event_execution_capability_not_certified` for live enablement, not a runtime failure |
| Missing/invalid disposition or producer handoff | `schema_invalid` / engineering |
| Replay and Live disposition differ for the same typed result | `replay_live_rule_mismatch` |
| Current detector/scope/Event Spec cannot materialize a valid candidate | Earliest precise detector/scope/profile/event blocker |
| Fresh execution-eligible signal cannot reach candidate/lane/Ticket | `action_time_boundary_not_reproduced` plus exact process blocker |
| Every non-market blocker closed and no fresh eligible signal | `market_wait_validated` |

No generic `waiting_for_market`, `waiting_for_signal`, or `missing_fact` may
replace the precise class during planning or acceptance.

## Owner Notification Contract

The previous P0 server-monitor ownership remains unchanged.

| PG fact | Owner result |
| --- | --- |
| `computed_not_satisfied` | Quiet |
| named observe-only signal | Quiet; available only for strategy review surfaces |
| named fresh execution-eligible signal | Plain opportunity-processing notification |
| engineering/invalid materialization failure | Plain no-order system-processing notification |
| exact Owner-policy intervention required | Typed intervention notification |

Watcher direct Feishu remains deleted. Server monitor PG dedupe remains the only
production Owner notification path.

## Cadence And Performance

| Dimension | Contract |
| --- | --- |
| Watcher cadence | One disposition resolution per evaluated runtime per tick; no replay or broad scan in cadence |
| No-signal files | Zero JSON/MD files per tick |
| PG row growth | No process row for computed-not-satisfied; at most one current process-outcome upsert per non-noop lane plus existing signal writes |
| CPU | Pure enum/model resolution only; heavy cross-lane certification runs in tests/deploy gates, not watcher cadence |
| API/network | Existing per-runtime API call remains; no additional production round trip |
| Timeouts | Existing watcher API and systemd bounds remain authoritative |
| Disk/retention | No new runtime files; existing PG retention and manual archive-only rules apply |
| Migration | Expected none; any proposed migration is a design-change stop requiring review before implementation continues |

`scripts/audit_production_runtime_file_io.py --json --fail-on-risk` must report
`performance_risk.status=clear` before deployment.

## Rollout And Rollback

### Rollout

1. Add RED cross-boundary census tests before production changes.
2. Add typed disposition and convert evaluator results.
3. Convert API and monitor transport in the same release.
4. Convert PG projector and delete legacy signal-type/status re-derivation.
5. Run five-StrategyGroup / 22-lane / six-Event-Spec certification.
6. Run adjacent boundary conservation tests through Ticket and non-executing
   FinalGate preflight.
7. Deploy exact `dev` head to Tokyo.
8. Run one watcher tick and one server-monitor tick without exchange write.
9. Treat the next distinct natural eligible event as a P0 interrupt acceptance.

There is no dual-reader rollout. Missing disposition fails closed, so mixed
generation is prevented by the existing deploy quiescence and exact-head
capability certification ordering.

### Rollback

1. Stop watcher/monitor/lifecycle timers through the official deploy path.
2. Switch the Tokyo release symlink to the previous exact-head release.
3. Restore timers and verify postdeploy health.
4. Keep new PG signal payload keys and process outcomes as forward-compatible
   audit data; no destructive cleanup is required.

Rollback does not change Owner policy, runtime profiles, positions, orders, or
credentials.

## WIP And Natural-Event Interrupt

This becomes the single active medium-scale engineering lane. It does not add a
sixth StrategyGroup or expand the 22-lane candidate universe.

A distinct natural execution-eligible signal, unprotected position, unknown
exchange outcome, or active lifecycle safety incident interrupts work at the
next committed transaction boundary. Natural acceptance uses the deployed
official path and then returns to the interrupted checklist item.

## Acceptance Criteria

1. Every evaluation has exactly one typed disposition.
2. The Observation Cycle API no longer produces `would_enter +
   waiting_for_signal`.
3. `CPM-RO-001 + SOLUSDT + short` is deterministically classified as an exact
   disposition with its true first blocker or observe-only meaning.
4. All five StrategyGroups, all 22 lanes, and all six Event Specs pass positive,
   negative, malformed, stale, duplicate, terminal, and later-success cases.
5. Every upstream may-advance fact has either its downstream identity or one
   exact same-lane/source-watermark PG outcome through Ticket.
6. Observe-only signals never enter promotion or Owner opportunity language.
7. Computed-not-satisfied creates no engineering failure row and may become
   market wait only after the full market-wait checklist is satisfied.
8. Missing/unknown disposition fails closed and is never reconstructed from
   legacy field combinations.
9. Replay and Live use the same disposition resolver.
10. No FinalGate, Operation Layer, exchange write, order, position, strategy
    parameter, capital, leverage, sizing, or live-profile authority changes.
11. No-signal ticks create zero JSON/MD files and production file-I/O risk is
    clear.
12. Tokyo exact-head deploy and watcher/server-monitor production acceptance
    pass before the task is marked complete.

## Chain Position

```text
chain_position: fresh_signal_promotion
strategy_group_id: current five StrategyGroups
symbol: current 22 candidate lanes
stage: evaluation_output_to_named_pg_signal
first_blocker: conflicting_signal_semantics:would_enter_plus_waiting_for_signal
evidence: CPM-RO-001/SOLUSDT/short live_signal_materialization outcome and shared code path
signal_event_id: none for the captured event
promotion_candidate_id: none
action_time_lane_input_id: none
ticket_id: none
next_action: implement one typed SignalDispositionDecision after cross-boundary RED census
stop_condition: every may-advance result has a downstream identity or exact same-lane PG process outcome
owner_action_required: false
authority_boundary: no strategy parameter, capital, profile, FinalGate, Operation Layer, or exchange-write expansion
```

## Owner Confirmation Boundary

No unresolved Owner policy, capital, risk, leverage, symbol-scope, strategy
parameter, or production-stage decision is identified in this design.

Owner confirmation of this document authorizes implementation of the bounded
engineering task only. It does not authorize any expansion listed outside the
standing runtime boundary.
