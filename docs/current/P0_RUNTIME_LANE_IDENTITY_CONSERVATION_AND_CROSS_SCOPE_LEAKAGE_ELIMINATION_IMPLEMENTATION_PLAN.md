---
title: P0_RUNTIME_LANE_IDENTITY_CONSERVATION_AND_CROSS_SCOPE_LEAKAGE_ELIMINATION_IMPLEMENTATION_PLAN
status: IMPLEMENTED_LOCAL_VERIFIED_PENDING_TOKYO_DEPLOY
authority: docs/current/P0_RUNTIME_LANE_IDENTITY_CONSERVATION_AND_CROSS_SCOPE_LEAKAGE_ELIMINATION_IMPLEMENTATION_PLAN.md
design: docs/current/P0_RUNTIME_LANE_IDENTITY_CONSERVATION_AND_CROSS_SCOPE_LEAKAGE_ELIMINATION_DESIGN.md
last_verified: 2026-07-13
---

# P0 Runtime Lane Identity Conservation And Cross-Scope Leakage Elimination Implementation Plan

> **Execution instruction:** After Owner confirmation, use
> `superpowers:executing-plans` inline with review checkpoints. Do not use
> subagents unless the Owner explicitly requests delegation. This document does
> not itself authorize implementation.

## Goal

Make one PG-resolved `RuntimeLaneIdentity` immutable from registered candidate
scope through Event-Spec evaluation, named signal projection, promotion,
action-time lane, and Ticket. Prevent evaluator output, request payloads,
legacy runtime instances, or monitor fallback logic from changing the lane's
StrategyGroup, symbol, side, Event Spec, or timeframe.

## Product Decision Incorporated

The implementation must preserve the Owner's binary strategy decision:

```text
research / Replay
-> admit StrategyGroup + versioned Event-Spec scope
   or do not admit it

admitted + enabled
-> running
-> waiting_for_opportunity
-> processing when an eligible event exists
```

There is no durable production `Observe-only StrategyGroup` state. The existing
`shadow_mode=true` detector property means that the detector itself has no
exchange-write authority; it does not downshift an admitted StrategyGroup into
an indefinite non-trading tier.

The only time-bounded observation in this P0 is an engineering acceptance
window after deployment: at most **3 watcher/monitor ticks** and no more than
**60 minutes**. Once the identity and cadence checks pass, an admitted strategy
continues normal production waiting and may enter the official trading path on
the next eligible event without a second observation probation.

The three ticks prove initial load, repeat-cadence stability, and idempotency.
The 60-minute ceiling prevents scheduler failure from becoming open-ended
observation; whichever limit is reached first produces a pass or fail result.
Legacy/internal `observe_only` values may remain for research, fail-closed
defaults, and non-executing component boundaries, but they cannot govern any of
the current five admitted StrategyGroups.

## Architecture

```text
PG candidate scope
+ PG candidate-scope/Event-Spec binding
+ PG runtime-scope binding
+ PG runtime instance
+ PG current policy/profile
                |
                v
        RuntimeLaneIdentity
                |
                v
 Event-scoped strategy evaluation
                |
                v
 exact signal evidence / exact no-signal evidence
                |
                v
 named PG signal -> promotion -> action-time lane -> Ticket
```

Identity fields are copied only from the resolved lane. Evaluation output is
evidence about that lane and can never overwrite its identity. Any mismatch
fails closed as an engineering/scope-integrity outcome and creates no signal,
promotion, lane, or Ticket.

## Capability Before And After

| Dimension | Before | After |
| --- | --- | --- |
| Lane identity | Reconstructed at several boundaries | One immutable PG-resolved value object |
| Evaluator output | Generic evaluator may report a different side | Evaluated inside the bound Event-Spec side and timeframe |
| Monitor materialization | Nested output may overwrite registered side | Identity copied only from the resolved lane |
| Process outcomes | Free-form scope key can describe a false lane | Typed identity columns plus composite constraints |
| Downstream chain | IDs checked unevenly per boundary | Shared conservation guard through Ticket |
| Strategy admission | Could be confused with Observe-only runtime | Binary admission remains separate from runtime scanning |
| Live authority | Unchanged | Unchanged; FinalGate and Operation Layer remain mandatory |

## Global Constraints

1. Do not change StrategyGroup thresholds, side semantics, symbols, Event-Spec
   rules, risk policy, leverage, sizing, capital, runtime profile, FinalGate,
   Operation Layer, protection, reconciliation, or exchange-write authority.
2. PG/current services remain the only runtime truth. Add no JSON/MD runtime
   readers, recurring writers, file fallback, evidence sidecar, or artifact CLI.
3. `domain/` remains pure business logic and imports no I/O framework.
4. Unknown, ambiguous, or mismatched lane identity fails closed before signal
   materialization.
5. Production no-signal ticks create zero report files and zero failure rows.
6. Natural eligible signals and lifecycle safety incidents interrupt ordinary
   work at the next committed transaction boundary.
7. Every production change is test-driven: capture the RED case before changing
   the responsible code.
8. The current five admitted StrategyGroups are not returned to probation.
9. This work does not infer a CPM short lane. CPM remains long-only unless a
   separate Owner strategy-admission decision changes its registry scope.

## File Responsibility Map

| File | Responsibility after implementation |
| --- | --- |
| `src/domain/runtime_lane_identity.py` | Immutable pure lane-identity contract and mismatch result |
| `src/application/runtime_lane_identity_service.py` | Resolve exactly one lane from PG-bound rows |
| `src/application/runtime_strategy_signal_evaluation_service.py` | Event-scoped evaluation whose result references the resolved identity |
| `src/application/readmodels/runtime_strategy_signal_input.py` | Read registered Event Spec, timeframe, scope, and runtime bindings |
| `src/interfaces/api_trading_console.py` | Transport exact identity and evidence; no generic side/status reinterpretation |
| `scripts/runtime_active_observation_monitor.py` | Materialize only exact eligible results; no side fallback |
| `src/application/runtime_process_outcome.py` | Persist typed process-outcome identity |
| `src/application/action_time/identity_conservation.py` | Shared guard for signal, promotion, lane, and Ticket boundaries |
| `migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py` | Typed live-signal/outcome lineage, constraints, indexes, and false-row reconciliation |
| Existing promotion/Ticket modules | Invoke the shared guard without changing business authority |

## Task 1: Capture The Incident And Same-Class RED Matrix

### Files

- Create: `tests/unit/test_runtime_lane_identity.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_strategy_signal_evaluation_service.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`

### Step 1.1: Freeze the current production-shape incident

Add a regression fixture with a registered CPM long lane and a nested generic
evaluator short result. The expected behavior is rejection, not materializing a
CPM short candidate and not labelling it as ordinary market wait.

```python
def test_cpm_long_lane_rejects_nested_short_output_without_materialization():
    summary = cpm_summary(
        registered_side="long",
        event_spec_id="CPM-RO-001:long:v2",
        evaluated_signal={"signal_type": "would_enter", "side": "short"},
    )

    candidates = runtime_active_observation_monitor._live_signal_candidates_from_summaries(
        [summary]
    )

    assert candidates == []
    assert summary["lane_identity"]["side"] == "long"
```

`cpm_summary` is a local test fixture defined in the same test module. It must
populate every required identity field; it must not hide PG resolution behind
a permissive dictionary default.

### Step 1.2: Add mismatch cases for every identity dimension

Parameterize the following mutations against one valid identity fixture:

| Mutation | Required result | Forbidden result |
| --- | --- | --- |
| StrategyGroup/version mismatch | `runtime_lane_identity_mismatch` | signal row |
| Symbol mismatch | `runtime_lane_identity_mismatch` | promotion row |
| Side mismatch | `runtime_lane_identity_mismatch` | action-time lane |
| Event-Spec/version mismatch | `runtime_lane_identity_mismatch` | Ticket |
| Timeframe mismatch | `runtime_lane_identity_mismatch` | silent coercion |
| Runtime-instance/scope mismatch | `runtime_lane_identity_mismatch` | fallback to another runtime |

### Step 1.3: Prove the generic API failure shape

Add an API unit test showing that the current generic response can combine an
outer `waiting_for_signal` status with a nested opposite-side `would_enter`
result. The test must fail before the API contract is corrected.

### Step 1.4: Run the RED set

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_action_time_full_chain_impact.py
```

Expected before implementation: only the new identity-conservation assertions
fail. Existing unrelated assertions remain green.

### Task 1 stop condition

Do not edit production code until every RED has a named boundary, exact
upstream identity, mutated field, expected blocker, and forbidden downstream
row. Do not create a generated report file.

## Task 2: Add The Immutable RuntimeLaneIdentity Core

### Files

- Create: `src/domain/runtime_lane_identity.py`
- Create: `src/application/runtime_lane_identity_service.py`
- Create: `tests/unit/test_runtime_lane_identity_service.py`
- Modify: `src/application/readmodels/runtime_strategy_signal_input.py`
- Create: `tests/unit/test_runtime_strategy_signal_input.py`

### Step 2.1: Define the pure immutable value object

```python
from pydantic import BaseModel, ConfigDict


class RuntimeLaneIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_scope_id: str
    candidate_scope_event_binding_id: str
    runtime_scope_binding_id: str
    runtime_instance_id: str
    runtime_profile_id: str
    policy_current_id: str
    strategy_group_id: str
    strategy_group_version_id: str
    symbol: str
    asset_class: str
    side: str
    event_spec_id: str
    event_spec_version: str
    event_id: str
    timeframe: str
    time_authority: str
```

Tests must assert immutability, forbidden extra fields, nonblank IDs, supported
side vocabulary, and exact model serialization.

### Step 2.2: Resolve exactly one lane from PG

`RuntimeLaneIdentityService.resolve(...)` must join or validate:

1. active candidate scope;
2. active candidate-scope/Event-Spec binding;
3. active runtime-scope binding;
4. selected runtime instance;
5. current policy and runtime profile;
6. current versioned Event Spec.

It returns either one `RuntimeLaneIdentity` or one typed blocker. Zero matches,
multiple matches, inactive rows, and conflicting fields are blockers; the
service must never select the first row opportunistically.

### Step 2.3: Test exact resolver outcomes

Required tests:

```text
one exact active lane -> identity
no candidate scope -> candidate_scope_missing
multiple event bindings -> candidate_scope_event_binding_ambiguous
runtime scope differs from candidate scope -> runtime_lane_identity_mismatch
runtime instance excluded by current universe -> runtime_instance_not_selected
Event Spec side differs from candidate side -> runtime_lane_identity_mismatch
Event Spec timeframe missing -> event_spec_timeframe_missing
```

### Step 2.4: Run the focused tests

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/unit/test_runtime_strategy_signal_input.py
```

Expected: all Task 2 tests pass; Task 1 downstream RED tests still fail.

## Task 3: Make Production Evaluation Event-Scoped

### Files

- Modify: `src/application/runtime_strategy_signal_evaluation_service.py`
- Modify: `src/application/readmodels/runtime_strategy_signal_input.py`
- Modify: `src/interfaces/api_trading_console.py`
- Modify: `tests/unit/test_runtime_strategy_signal_evaluation_service.py`
- Create: `tests/unit/test_runtime_observation_cycle_api.py`
- Modify: `tests/unit/test_runtime_strategy_signal_input.py`

### Step 3.1: Split production and research evaluation intent

The production entry point accepts a resolved `RuntimeLaneIdentity`. The
research/Replay entry point may inspect generic evaluator outputs, but it must
not be callable by the watcher materialization path.

```python
class RuntimeLaneEvaluationStatus(str, Enum):
    EVENT_NOT_SATISFIED = "event_not_satisfied"
    EVENT_READY = "event_ready"
    BLOCKED = "blocked"


class RuntimeStrategySignalEvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_identity: RuntimeLaneIdentity
    status: RuntimeLaneEvaluationStatus
    can_materialize_live_signal_event: bool
    evaluated_at_ms: int
    valid_until_ms: int
    signal_evidence: StrategyFamilySignal | None
    blocker: str | None
```

The existing `RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY` remains only
where legacy research/pre-admission compatibility still requires it. It is not
returned as the production status of an admitted Event Spec.

The following invariant is mandatory:

```python
if result.signal_evidence is not None:
    assert result.signal_evidence.side == result.lane_identity.side
```

A raw generic evaluator pattern for another side is not persisted as a current
production observation. The Event-Spec adapter classifies it as
`computed_not_satisfied` for this lane, with
`can_materialize_live_signal_event=false`, no engineering blocker, and no PG
write. Offline Replay/OFC may retain that output as research evidence outside
the production current-state path.

`runtime_lane_identity_mismatch` is reserved for corruption of the canonical
identity envelope or for a malformed payload that claims an opposite-side
signal is materializable. This distinction prevents normal broad detector
output from becoming an outage while still failing closed at the production
boundary.

### Step 3.2: Use the bound Event Spec and its timeframe

Replace the API's fixed one-hour production assumption with the exact
`RuntimeLaneIdentity.timeframe` and Event-Spec definition loaded from PG. SOR
15-minute bindings must therefore request 15-minute primary candles; CPM, MPG,
MI, and BRF2 use their own registered timeframes.

Request fields such as symbol, side, Event Spec, and timeframe become assertion
fields only. When supplied, they must equal the resolved identity; they must
never override it.

### Step 3.3: Stop collapsing mismatch into market wait

`_runtime_next_attempt_observation_cycle_payload` in
`src/interfaces/api_trading_console.py` must preserve three distinct classes:

| Class | Owner-facing normal state | Engineering/audit meaning |
| --- | --- | --- |
| Exact event not satisfied | `waiting_for_opportunity` | computed facts are false |
| Exact eligible event | `processing` | may materialize a named signal |
| Identity/evaluation fault | `temporarily_unavailable` or `needs_intervention` by severity | engineering or scope integrity blocker |

Do not expose raw internal fields as an Owner action requirement. The full
identity and blocker remain available in developer/audit payloads.

### Step 3.4: Add parity tests

For each Event Spec, feed the same closed candles to the production evaluator
and the Replay evaluator. Assert equal computed facts and equal exact-side
decision. Replay may expose additional research diagnostics; it may not apply a
different trading rule.

### Step 3.5: Run focused tests

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_strategy_signal_input.py \
  tests/unit/test_runtime_observation_cycle_api.py \
  tests/unit/test_opportunity_feedback_historical_replay.py
```

Expected: event-scoped evaluator and API tests pass; the monitor RED remains
until Task 4.

## Task 4: Remove Monitor-Side Identity Reconstruction

### Files

- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify only if the RED proves necessary:
  `scripts/runtime_signal_watcher_tick.py`
- Modify only if the RED proves necessary:
  `tests/unit/test_runtime_signal_watcher_tick.py`

### Step 4.1: Replace permissive candidate extraction

`_live_signal_candidates_from_summaries` must require all of the following:

1. a valid `lane_identity` produced by the PG resolver;
2. `can_materialize_live_signal_event is True`;
3. non-stale `evaluated_at_ms` and `valid_until_ms`;
4. selected-event signal-evidence side exactly equal to lane side;
5. no identity blocker.

Candidate identity fields are copied only from `lane_identity`. Remove logic
equivalent to:

```python
signal.get("side") or row.get("side")
```

The signal evidence may support eligibility, but it cannot supply group,
version, symbol, side, Event Spec, timeframe, runtime instance, or binding IDs.

### Step 4.2: Fail closed without retry churn

An identity-envelope mismatch or malformed materializable payload produces no
named signal and one idempotent typed process outcome. A normal exact no-signal
result, including a generic opposite-side pattern already classified as
`computed_not_satisfied`, produces neither a signal row nor a failure outcome.
Repeated monitor ticks with the same source watermark must not create duplicate
outcomes or notifications.

### Step 4.3: Revalidate immediately before PG signal insert

Inside the same transaction used for signal insertion, re-read or lock the
referenced current binding rows and verify that they remain active and equal to
the candidate identity. If policy, scope, runtime, or Event-Spec identity has
changed since evaluation, abort materialization with a typed stale-identity
outcome.

### Step 4.4: Cover positive and negative monitor cases

Required tests:

```text
exact long lane + exact long selected event -> one long named signal
exact short lane + exact short selected event -> one short named signal
long lane + raw short generic pattern -> zero signal, zero failure outcome
long lane + materializable short payload -> zero signal, exact mismatch outcome
eligible false -> zero signal, zero failure outcome
expired evidence -> zero signal, stale evidence outcome
binding changed after evaluation -> zero signal, stale identity outcome
same mismatch tick repeated -> one outcome, no duplicate notification
```

### Step 4.5: Run focused tests

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py
```

Expected: incident regression and monitor conservation tests pass.

## Task 5: Add Typed PG Signal/Outcome Identity And Reconcile False State

### Files

- Create:
  `migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py`
- Modify: `src/application/runtime_process_outcome.py`
- Modify: `tests/unit/test_runtime_process_outcome.py`
- Create: `tests/unit/test_runtime_lane_identity_migration.py`
- Modify: `tests/unit/test_pg_runtime_control_state_foundation_migration.py`

### Step 5.1: Add typed identity to fresh live signals

Add these lineage columns to `brc_live_signal_events`:

```text
candidate_scope_event_binding_id
runtime_scope_binding_id
runtime_instance_id
strategy_group_version_id
event_spec_version
event_id
timeframe
lane_identity_key
```

The table already owns candidate scope, Event Spec, StrategyGroup, symbol, and
side. Fresh validated `live_market` rows must contain the complete identity;
historical/replay rows remain provenance and cannot become live authority.

### Step 5.2: Add nullable typed outcome columns for migration compatibility

Add the following columns to `brc_runtime_process_outcomes`:

```text
scope_kind
candidate_scope_id
candidate_scope_event_binding_id
runtime_scope_binding_id
runtime_instance_id
strategy_group_id
strategy_group_version_id
symbol
asset_class
side
event_spec_id
event_spec_version
event_id
timeframe
lane_identity_key
```

Existing historical rows remain readable. New process outcomes owned by the
runtime signal materialization path must populate the complete identity set.

### Step 5.3: Add constraints and indexes

Migration **118** must add:

1. a completeness check: fresh validated `live_market` signals contain the
   full typed identity;
2. a completeness check: runtime-lane outcomes contain either all typed
   identity columns or none for explicitly legacy rows;
3. side vocabulary check using the current registry vocabulary;
4. foreign keys where current table keys are stable and available;
5. a composite uniqueness/idempotency constraint using process name, typed
   lane identity, and source watermark;
6. indexes supporting current runtime lookup without a full scan.

Do not invent a new current-state table. If a required foreign key cannot be
made safely because an existing natural key is unstable, stop at that exact
constraint and update the design before weakening identity.

### Step 5.4: Reconcile the known false CPM-short row

The migration must identify the single known row by exact process name, exact
legacy scope key, exact source watermark, and exact blocker. It must not use a
broad `LIKE '%CPM%short%'` update.

The exact incident selector is:

```text
process_name = live_signal_materialization
scope_key = lane:CPM-RO-001:SOLUSDT:short
process_state = retryable_failure
source_watermark = strategy-runtime-d3e7af7d4f6e:1783907999999
first_blocker = pg_live_signal_event_materialization_failed:runtime_summary_blocked:waiting_for_signal
```

The row is converted to a resolved legacy-invalid-scope audit outcome. It must
not remain retryable, active, Owner-actionable, or a source of current runtime
status. Preserve the original evidence text for provenance.

Migration tests must prove:

1. the exact known row is reconciled once;
2. an unrelated CPM row is untouched;
3. rerunning upgrade logic is idempotent;
4. downgrade never resurrects a retryable false lane;
5. a new CPM short runtime-lane outcome violates the registered identity
   constraint unless a real active CPM short binding exists.

### Step 5.5: Update the typed repository API

`src/application/runtime_process_outcome.py` accepts
`RuntimeLaneIdentity | None` rather than a free-form lane dictionary. Runtime
signal materialization callers must pass identity. Legacy non-lane processes
may pass `None` and remain explicitly classified as legacy/unscoped.

### Step 5.6: Run migration and repository tests

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_lane_identity_migration.py \
  tests/unit/test_runtime_process_outcome.py \
  tests/unit/test_pg_runtime_control_state_foundation_migration.py
```

Expected: schema, idempotency, exact-row reconciliation, and repository tests
pass.

## Task 6: Conserve Identity Through Promotion, Lane, And Ticket

### Files

- Create: `src/application/action_time/identity_conservation.py`
- Create: `tests/unit/test_action_time_identity_conservation.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`

### Step 6.1: Introduce one shared pure guard

The guard compares the immutable source lane with each downstream row and
returns exact mismatches. It does not fetch PG data and does not decide trading
eligibility.

```python
def require_runtime_lane_identity_match(
    *,
    expected: RuntimeLaneIdentity,
    actual: RuntimeLaneIdentity,
    boundary: str,
) -> None:
    if expected != actual:
        raise RuntimeLaneIdentityMismatch(
            boundary=boundary,
            expected=expected,
            actual=actual,
        )
```

No caller may omit fields, compare only group/symbol/side, or reconstruct an
identity from a display scope key.

### Step 6.2: Apply the guard at every handoff

| Boundary | Upstream source | Downstream object | Failure behavior |
| --- | --- | --- | --- |
| Evaluation -> signal | resolved lane identity | named PG signal | no insert; typed outcome |
| Signal -> promotion | named PG signal | promotion candidate | no promotion; typed outcome |
| Promotion -> lane | promotion candidate | action-time lane | no lane; typed outcome |
| Lane -> Ticket | action-time lane | Ticket | no Ticket; typed outcome |
| Ticket -> preflight | Ticket | non-executing preflight | no submit; existing fail-closed gate |

Existing stronger identity checks remain, but duplicate partial comparisons
must delegate to the shared guard or be removed after equivalent tests exist.

### Step 6.3: Add source-watermark conservation

The guard coverage must include the source signal/event ID and source watermark
used for idempotency. A matching lane identity with a different event cannot
reuse a promotion, lane, or Ticket.

### Step 6.4: Run handoff regressions

```bash
python3 -m pytest -q \
  tests/unit/test_action_time_identity_conservation.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_action_time_full_chain_impact.py
```

Expected: every mismatch stops at its first boundary with one exact outcome;
valid identities preserve current promotion and Ticket behavior.

## Task 7: Certify All Current Lanes And Retire Invalid Runtime Scope

### Files

- Create: `tests/integration/test_runtime_lane_identity_certification.py`
- Modify: `tests/unit/test_certify_action_time_capability.py`
- Modify: `tests/unit/test_runtime_control_state_foundation_seed.py`
- Modify: `src/application/strategy_semantic_admission.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `tests/unit/test_strategy_semantic_admission.py`
- Modify: `tests/unit/test_runtime_control_state_repository.py`
- Modify only if required: the new migration **118**

### Step 7.1: Build the expected matrix from PG seed/current contracts

The certification must expect **22 active candidate lanes** across the five
admitted StrategyGroups and **6 versioned Event Specs**:

| StrategyGroup | Symbols | Registered sides | Event-Spec count |
| --- | ---: | --- | ---: |
| CPM-RO-001 | 4 | long | 1 |
| MPG-001 | 4 | long | 1 |
| MI-001 | 3 | long | 1 |
| SOR-001 | 4 | long and short | 2 |
| BRF2-001 | 3 | short | 1 |

The test must derive actual rows from PG/current state and compare them with the
explicit accepted matrix. It must not infer missing sides from an evaluator.

### Step 7.2: Positive certification

For all 22 lanes, prove:

1. one active candidate scope;
2. one active Event-Spec binding;
3. one selected runtime scope and runtime instance;
4. exact symbol, side, Event Spec, version, and timeframe agreement;
5. exact no-signal can remain normal market wait;
6. exact eligible event can materialize one named signal;
7. identity reaches promotion, lane, and Ticket unchanged in simulation;
8. simulation never grants exchange-write authority.

### Step 7.3: Negative certification

For each StrategyGroup family, mutate symbol, side, Event Spec, timeframe, and
runtime instance one at a time. Assert zero signal, promotion, lane, and Ticket,
plus one typed first blocker where persistence is appropriate.

Add the explicit CPM rule:

```python
assert no_active_lane(strategy_group_id="CPM-RO-001", side="short")
```

### Step 7.4: Resolve orphan/legacy runtime instances

Any runtime instance not selected by the current PG candidate universe must be
excluded from production evaluation and materialization. If it has no current
audit or recovery obligation, retire it through the existing PG runtime-state
transition. Do not delete historical provenance and do not create a JSON
inventory.

### Step 7.5: Enforce binary admission semantics

Certification asserts that every enabled production StrategyGroup is admitted
to its bounded official path. No test or readmodel may describe a current
admitted group as a durable Observe-only tier. Non-admitted strategy variants
belong to Replay/research or a parked registry state, not the production
candidate set.

For every active candidate lane, require:

```text
semantic admission = trial_grade_capable
Event Spec signal grade = trial_grade_signal
Event Spec execution mode = trial_live
execution_eligibility_enabled = true
```

Any other semantic conclusion prevents active production admission; it does
not start an Observe-only timer. Historical conclusions remain auditable.

### Step 7.6: Run certification

```bash
python3 -m pytest -q \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/unit/test_certify_action_time_capability.py \
  tests/unit/test_runtime_control_state_foundation_seed.py \
  tests/unit/test_strategy_semantic_admission.py \
  tests/unit/test_runtime_control_state_repository.py
```

Expected: 22/22 positive lanes pass, every injected mismatch fails closed, and
no unregistered CPM short lane exists.

## Task 8: Full Verification, Deployment, And Natural-Event Acceptance

### Files

- Modify: `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`
- Modify: `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md`
- Modify: `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`
- Modify: `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md`
- Modify if the implementation changes deployment acceptance:
  `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Do not create runtime evidence files in the repository.

The contract edits must record binary production admission, distinguish watcher
market scanning from an Observe-only StrategyGroup tier, and preserve legacy
technical enums only outside active production governance.

### Step 8.1: Run static and full regression checks

```bash
python3 -m compileall -q src scripts tests
python3 -m pytest -q
git diff --check
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py --json --fail-on-risk
```

Required result:

```text
all tests green
tracked output changes = 0
performance_risk.status = clear
new recurring JSON/MD reads/writes = 0
```

### Step 8.2: Verify migration chain locally

```bash
find migrations/versions -maxdepth 1 -type f -name '*.py' | wc -l
find migrations/versions -maxdepth 1 -type f -name '*.py' -print | sort | tail -n 1
```

Expected after implementation:

```text
118
migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py
```

### Step 8.3: Prepare a focused implementation commit

Before commit, inspect:

```bash
git status --short
git diff --stat
git diff --check
```

Stage only files listed by this plan or explicitly justified by a RED test.
Commit message:

```text
fix: conserve runtime lane identity across live path
```

### Step 8.4: Build a non-executing Tokyo deploy plan

After the implementation commit is pushed to an approved remote branch, resolve
the actual current Tokyo release and deployed head through the read-only probe.
Then run the release preparation and plan commands with exact values:

```bash
python3 scripts/prepare_tokyo_runtime_governance_release.py \
  --json \
  --deployed-head <CURRENT_TOKYO_HEAD> \
  --expected-min-migrations 118 \
  --expected-latest-migration 2026-07-13-118_conserve_runtime_lane_identity.py

python3 scripts/plan_tokyo_runtime_governance_git_deploy.py \
  --json \
  --git-ref <PUSHED_BRANCH> \
  --target-commit <IMPLEMENTATION_COMMIT> \
  --previous-release <CURRENT_TOKYO_RELEASE> \
  --expected-deployed-head <CURRENT_TOKYO_HEAD> \
  --expected-remote-migration-count 117 \
  --expected-remote-latest-migration 2026-07-12-117_extend_owner_notifications.py \
  --expected-latest-migration 2026-07-13-118_conserve_runtime_lane_identity.py
```

The angle-bracket values must be filled from current read-only facts in the
same deployment turn. Stale remembered values are forbidden.

### Step 8.5: Apply through the official deploy path

Use `scripts/execute_tokyo_runtime_governance_git_deploy.py --apply` with the
same exact release, head, migration, and branch values produced by Step 8.4.
Deploy success does not grant live-submit authority and does not bypass current
FinalGate or Operation Layer checks.

### Step 8.6: Read-only postdeploy acceptance

```bash
python3 scripts/verify_tokyo_runtime_governance_postdeploy.py \
  --json \
  --expected-current-head <IMPLEMENTATION_COMMIT> \
  --expected-migration-count 118 \
  --expected-latest-migration 2026-07-13-118_conserve_runtime_lane_identity.py
```

Then observe at most **3 watcher/monitor ticks** and no more than **60 minutes**.
Acceptance requires:

1. all current lane summaries carry exact PG identity;
2. no current or retryable CPM-short process outcome;
3. no cross-side, cross-symbol, cross-Event-Spec, or cross-timeframe candidate;
4. no duplicate outcome/notification churn;
5. no repository report files created by production cadence;
6. services and PG connections remain healthy.

If these checks pass, the engineering observation window closes. The five
admitted StrategyGroups stay in normal production running/waiting state; they
are not held in Observe-only mode.

### Step 8.7: Natural-event acceptance

The next eligible event from any admitted lane interrupts ordinary work. Verify
the exact identity at:

```text
resolved lane
-> evaluation
-> named PG signal
-> promotion
-> action-time lane
-> Ticket
-> non-executing preflight
```

If current Runtime Safety State, FinalGate, and Operation Layer authorize the
official submit, continue through the existing bounded real-order path under
standing authorization. This P0 adds no separate Owner per-order confirmation
and no observation delay.

### Step 8.8: Rollback condition

Rollback the release, not PG history, if any of these occur:

1. migration or service startup fails;
2. lane identity cannot be resolved for a currently admitted lane;
3. false cross-scope signal materializes;
4. duplicate submit risk appears;
5. protection, reconciliation, or lifecycle safety regresses;
6. production cadence creates new runtime JSON/MD artifacts.

Keep the runtime fail-closed. Do not restore the former permissive side fallback
as a quick recovery.

## Completion Gate

This task is complete only when all of the following are true:

- [x] One immutable PG-resolved lane identity exists.
- [x] Production evaluation is Event-Spec/side/timeframe scoped.
- [x] Evaluator evidence cannot overwrite lane identity.
- [x] Monitor and PG projection reject every cross-scope mismatch.
- [x] Process outcomes carry typed identity and cannot encode a false current lane.
- [x] The known false CPM-short row is exactly reconciled.
- [x] Promotion, lane, and Ticket conserve identity and event watermark.
- [x] All 22 current lanes pass positive and negative certification.
- [x] No durable Observe-only StrategyGroup tier exists.
- [x] Full regression and production file-I/O audit pass.
- [ ] Tokyo postdeploy checks pass within 3 ticks / 60 minutes.
- [ ] Natural-event acceptance remains the next live proof, not an engineering blocker.

## Execution State

The Owner confirmed this package and implementation proceeded without a second
design loop. Local evidence at this revision is:

- migration `118` with
  `2026-07-13-118_conserve_runtime_lane_identity.py` as the migration head;
- `3001 passed, 1 skipped` from the complete test suite;
- `performance_risk.status=clear` and zero recurring JSON/MD report-file risk
  from the production file-I/O audit;
- current docs authority and output-artifact scope validation passing.

The remaining work is restricted to the official Tokyo deployment, its
read-only postdeploy checks, and the bounded three-tick/60-minute smoke. A
natural eligible event remains a live acceptance event, not a prerequisite for
this local engineering closure.
