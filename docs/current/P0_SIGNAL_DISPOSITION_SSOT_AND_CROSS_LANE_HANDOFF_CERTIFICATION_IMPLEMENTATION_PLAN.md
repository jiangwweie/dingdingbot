---
title: P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_IMPLEMENTATION_PLAN
status: PROPOSED_FOR_OWNER_CONFIRMATION
authority: docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P0 Signal Disposition SSOT And Cross-Lane Handoff Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:executing-plans` and execute inline with review checkpoints. Do
> not dispatch subagents unless the Owner explicitly requests delegation. Steps
> use checkbox syntax for tracking.

**Goal:** Replace repeated signal-result interpretation with one typed
`SignalDispositionDecision`, then prove that every current StrategyGroup lane
conserves its exact result from evaluation through named PG signal, promotion,
action-time lane, and Ticket.

**Architecture:** Extend the existing strategy signal contract and shared
evaluation result. The Observation Cycle API transports the typed disposition;
the active monitor and PG projector consume it without re-deriving meaning from
`signal_type + outer status`. Existing PG signal and process-outcome tables
remain authoritative; no new report, bridge, file authority, or lifecycle path
is introduced.

**Tech Stack:** Python 3, Pydantic, `decimal.Decimal`, SQLAlchemy, PostgreSQL
current projections, pytest, systemd watcher/server monitor, existing Tokyo
exact-head deploy path.

## Global Constraints

- No strategy threshold, direction semantic, Event Spec business rule,
  candidate symbol/side scope, capital, leverage, sizing, runtime profile,
  FinalGate, Operation Layer, protection, or exchange-write authority change.
- `domain/` remains pure and imports no I/O frameworks.
- PG/current services remain production truth.
- Do not add a table or migration unless implementation proves the design
  impossible without one; stop for architecture review before adding either.
- Do not add production JSON/MD reads, recurring JSON/MD writes, artifact CLI
  paths, or file-backed fallback.
- A missing or unknown disposition fails closed as an engineering blocker; do
  not reconstruct it from legacy field combinations.
- No-signal ticks create zero JSON/MD files and zero signal-materialization
  failure rows.
- Natural eligible signals and lifecycle safety incidents interrupt at the next
  committed transaction boundary.
- All production code changes use TDD. No implementation step starts before
  the cross-boundary RED census is captured.

---

## File Responsibility Map

| File | Responsibility after this task |
| --- | --- |
| `src/domain/strategy_family_signal.py` | Pure `SignalDisposition` enum and immutable decision value object |
| `src/application/runtime_signal_disposition.py` | One pure resolver and one API projection mapper; no I/O |
| `src/application/runtime_strategy_signal_evaluation_service.py` | Produces one required disposition on every evaluation result |
| `src/interfaces/api_trading_console.py` | Transparently transports disposition and maps only its API presentation status |
| `scripts/runtime_active_observation_monitor.py` | Preserves disposition and projects named signals or exact PG outcomes |
| `scripts/runtime_signal_watcher_tick.py` | Uses PG projector result only; no legacy ready/status reconstruction |
| `scripts/run_tokyo_runtime_server_monitor.py` | Keeps PG-backed Owner interpretation and dedupe; no signal re-evaluation |
| Existing promotion/Ticket modules | Preserve downstream identity-or-process-outcome conservation; modify only if RED census proves a violation |

## Task 1: Cross-Boundary RED Conservation Census

**Why first:** The Owner requires similar defects to be identified before a
single point is repaired. This task adds failing tests for the shared defect and
audits adjacent boundaries before production code changes.

**Files:**

- Create: `tests/unit/test_runtime_signal_disposition.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Read only: `src/application/action_time/promotion_action_time_lane.py`
- Read only: `src/application/action_time/ticket_materialization_sequence.py`

**Interfaces:**

- Consumes current evaluator outputs, API-shaped runtime summaries, PG signal
  rows, promotion rows, lane rows, Ticket rows, and runtime process outcomes.
- Produces a failing invariant matrix before the resolver exists.

- [ ] **Step 1.1: Add the exact CPM production-shape RED case**

Create a test with a typed `would_enter` output nested under an outer
`waiting_for_signal` result and assert that this combination is rejected rather
than treated as market wait:

```python
from scripts import runtime_active_observation_monitor


def test_would_enter_cannot_be_projected_as_waiting_for_signal():
    summary = {
        "runtime_instance_id": "runtime-cpm-sol-short",
        "strategy_family_id": "CPM-RO-001",
        "strategy_family_version_id": "CPM-RO-001-v0",
        "symbol": "SOL/USDT:USDT",
        "side": "short",
        "status": "waiting_for_signal",
        "signal_input_ref": "pg:test-signal-input",
        "signal_summary": {
            "signal_type": "would_enter",
            "side": "short",
        },
    }
    rows = runtime_active_observation_monitor._signal_projection_inputs_from_summaries(
        [summary]
    )
    assert rows[0]["signal_disposition"]["disposition"] == (
        "engineering_blocked"
    )
    assert rows[0]["signal_disposition"]["first_blocker"] == (
        "signal_disposition_missing"
    )
```

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_signal_disposition.py::test_would_enter_cannot_be_projected_as_waiting_for_signal
```

Expected before implementation: collection or assertion failure because the
typed disposition contract does not exist.

- [ ] **Step 1.2: Add one parameterized raw-evaluation case per active StrategyGroup**

The parameter set must contain exactly:

```python
ACTIVE_GROUPS = (
    "CPM-RO-001",
    "MPG-001",
    "MI-001",
    "SOR-001",
    "BRF2-001",
)
```

For every group, assert that a completed evaluation produces exactly one of
the five dispositions and never the pair `would_enter + waiting_for_signal`.

- [ ] **Step 1.3: Add the downstream identity-or-outcome invariant helper in tests**

```python
def assert_identity_or_exact_outcome(
    *,
    downstream_rows: list[dict],
    process_outcomes: list[dict],
    process_name: str,
    scope_key: str,
    source_watermark: str,
) -> None:
    matching_outcomes = [
        row
        for row in process_outcomes
        if row["process_name"] == process_name
        and row["scope_key"] == scope_key
        and row["source_watermark"] == source_watermark
    ]
    assert downstream_rows or matching_outcomes
    assert not (downstream_rows and any(
        row["process_state"] in {"retryable_failure", "hard_failure"}
        for row in matching_outcomes
    ))
```

Apply it to:

1. evaluation -> signal;
2. execution-eligible signal -> promotion;
3. arbitration-won promotion -> lane;
4. open lane -> Ticket;
5. current Ticket -> non-executing FinalGate preflight result or exact blocker.

- [ ] **Step 1.4: Run the census and record every RED class in the test names**

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_signal_disposition.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_action_time_full_chain_impact.py
```

Expected: new disposition tests fail. Existing unrelated downstream tests must
remain green. If an adjacent boundary fails the identity-or-outcome invariant,
classify whether it shares duplicate-state interpretation before Task 2.

- [ ] **Step 1.5: Stop condition before coding**

Do not edit production code until the RED report identifies, per failure:

```text
boundary
StrategyGroup
symbol
side
upstream identity
expected downstream identity
first blocker
process outcome present/missing
same root class yes/no
```

Do not create a generated report file. Preserve this evidence in test names,
pytest output, and the implementation checklist only.

## Task 2: Typed Signal Disposition Core

**Files:**

- Modify: `src/domain/strategy_family_signal.py`
- Create: `src/application/runtime_signal_disposition.py`
- Modify: `src/application/runtime_strategy_signal_evaluation_service.py`
- Test: `tests/unit/test_runtime_signal_disposition.py`
- Test: `tests/unit/test_runtime_strategy_signal_evaluation_service.py`
- Test: `tests/unit/test_strategy_family_signal_contract.py`

**Interfaces:**

- Consumes: evaluation status, typed strategy output, exact evaluation blockers.
- Produces: `SignalDispositionDecision` and
  `observation_cycle_projection(decision)`.

- [ ] **Step 2.1: Add domain enum and value-object RED tests**

Assert extra fields are forbidden, the object is immutable, engineering and
invalid dispositions require a first blocker, and no-action cannot claim
materialization.

- [ ] **Step 2.2: Add the pure domain value objects**

Add to `src/domain/strategy_family_signal.py`:

```python
class SignalDisposition(str, Enum):
    COMPUTED_NOT_SATISFIED = "computed_not_satisfied"
    OBSERVE_ONLY_SIGNAL = "observe_only_signal"
    MATERIALIZATION_CANDIDATE = "materialization_candidate"
    ENGINEERING_BLOCKED = "engineering_blocked"
    INVALID_SIGNAL = "invalid_signal"


class SignalDispositionDecision(StrategyFamilySignalModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: SignalDisposition
    first_blocker: str | None = None
    blockers: list[str] = Field(default_factory=list)
    may_materialize_signal_event: bool
    next_action: str = Field(min_length=1, max_length=128)
    source_stage: Literal["runtime_strategy_signal_evaluation"] = (
        "runtime_strategy_signal_evaluation"
    )
    not_execution_authority: Literal[True] = True

    @model_validator(mode="after")
    def _enforce_disposition_invariants(self) -> "SignalDispositionDecision":
        blocked = self.disposition in {
            SignalDisposition.ENGINEERING_BLOCKED,
            SignalDisposition.INVALID_SIGNAL,
        }
        if blocked and not self.first_blocker:
            raise ValueError("blocked signal disposition requires first_blocker")
        if self.disposition == SignalDisposition.COMPUTED_NOT_SATISFIED:
            if self.blockers or self.may_materialize_signal_event:
                raise ValueError("computed-not-satisfied is a non-error noop")
        return self
```

- [ ] **Step 2.3: Implement the only resolver**

Create `src/application/runtime_signal_disposition.py` with this public
signature:

```python
from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade
from src.domain.strategy_family_signal import (
    SignalDataQualityStatus,
    SignalDisposition,
    SignalDispositionDecision,
    SignalType,
    StrategyFamilySignalOutput,
)


def resolve_runtime_signal_disposition(
    *,
    evaluation_status: str,
    output: StrategyFamilySignalOutput | None,
    blockers: list[str],
) -> SignalDispositionDecision:
    exact_blockers = [str(item) for item in blockers if str(item).strip()]
    first_blocker = exact_blockers[0] if exact_blockers else None
    if output is None:
        return SignalDispositionDecision(
            disposition=SignalDisposition.ENGINEERING_BLOCKED,
            first_blocker=first_blocker or "strategy_signal_output_missing",
            blockers=exact_blockers or ["strategy_signal_output_missing"],
            may_materialize_signal_event=False,
            next_action="repair_strategy_signal_output",
        )
    if (
        output.signal_type == SignalType.INVALID
        or output.data_quality.status == SignalDataQualityStatus.INVALID
        or output.signal_grade == SignalGrade.INVALID_SIGNAL
    ):
        reason = first_blocker or "strategy_evaluator_output_invalid"
        return SignalDispositionDecision(
            disposition=SignalDisposition.INVALID_SIGNAL,
            first_blocker=reason,
            blockers=exact_blockers or [reason],
            may_materialize_signal_event=False,
            next_action="repair_invalid_signal_contract",
        )
    if output.signal_type != SignalType.WOULD_ENTER:
        return SignalDispositionDecision(
            disposition=SignalDisposition.COMPUTED_NOT_SATISFIED,
            blockers=[],
            may_materialize_signal_event=False,
            next_action="observe_next_closed_bar",
        )
    if evaluation_status == "blocked" or exact_blockers:
        reason = first_blocker or "strategy_signal_evaluation_blocked"
        return SignalDispositionDecision(
            disposition=SignalDisposition.ENGINEERING_BLOCKED,
            first_blocker=reason,
            blockers=exact_blockers or [reason],
            may_materialize_signal_event=False,
            next_action="repair_strategy_signal_evaluation",
        )
    if (
        output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL
        or output.required_execution_mode == RequiredExecutionMode.OBSERVE_ONLY
    ):
        return SignalDispositionDecision(
            disposition=SignalDisposition.OBSERVE_ONLY_SIGNAL,
            blockers=[],
            may_materialize_signal_event=True,
            next_action="record_named_observation_signal",
        )
    return SignalDispositionDecision(
        disposition=SignalDisposition.MATERIALIZATION_CANDIDATE,
        blockers=[],
        may_materialize_signal_event=True,
        next_action="materialize_pg_live_signal_event",
    )
```

Required mapping order:

1. missing output with blocked status -> `engineering_blocked`;
2. output `INVALID` or invalid data quality -> `invalid_signal`;
3. output not `WOULD_ENTER` -> `computed_not_satisfied` with no blockers;
4. would-enter plus blocked/mismatched evaluation -> `engineering_blocked`;
5. would-enter plus observe-only grade/mode -> `observe_only_signal`;
6. valid non-observe-only would-enter -> `materialization_candidate`.

Also expose:

```python
def observation_cycle_projection(
    decision: SignalDispositionDecision,
) -> dict[str, object]:
    if decision.disposition == SignalDisposition.COMPUTED_NOT_SATISFIED:
        return {
            "status": "waiting_for_signal",
            "blockers": [],
            "next_action": "observe_next_closed_bar",
        }
    if decision.disposition == SignalDisposition.OBSERVE_ONLY_SIGNAL:
        return {
            "status": "signal_evaluated_observe_only",
            "blockers": [],
            "next_action": "record_named_observation_signal",
        }
    if decision.disposition == SignalDisposition.MATERIALIZATION_CANDIDATE:
        return {
            "status": "ready_for_signal_materialization",
            "blockers": [],
            "next_action": "materialize_pg_live_signal_event",
        }
    return {
        "status": "blocked",
        "blockers": list(decision.blockers),
        "next_action": decision.next_action,
    }
```

This mapper switches only on `decision.disposition`; it must not accept
`signal_type`, `runtime_status`, or evaluator blockers as independent inputs.

- [ ] **Step 2.4: Make disposition mandatory on every evaluation result**

Add:

```python
disposition: SignalDispositionDecision
```

to `RuntimeStrategySignalEvaluationResult`. Modify the service's central
`_result(...)` factory to call `resolve_runtime_signal_disposition(...)` once.
Pass `status.value` into the resolver. Do not set disposition independently in
individual return branches.

- [ ] **Step 2.5: Run focused core tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_signal_disposition.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_strategy_family_signal_contract.py
```

Expected: all focused tests pass; each evaluator result contains one typed
disposition.

- [ ] **Step 2.6: Commit checkpoint**

```bash
git add \
  src/domain/strategy_family_signal.py \
  src/application/runtime_signal_disposition.py \
  src/application/runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_signal_disposition.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_strategy_family_signal_contract.py
git commit -m "feat(signal): add authoritative signal disposition"
```

## Task 3: Observation API And Monitor Transport

**Files:**

- Modify: `src/interfaces/api_trading_console.py`
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `scripts/runtime_signal_watcher_tick.py`
- Create: `tests/unit/test_runtime_signal_disposition_api_contract.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_signal_watcher_tick.py`

**Interfaces:**

- Consumes: serialized `RuntimeStrategySignalEvaluationResult.disposition`.
- Produces: exact API outer status and runtime summary `signal_disposition`.

- [ ] **Step 3.1: Add API projection RED tests**

Assert the exact mapping:

```python
EXPECTED = {
    "computed_not_satisfied": ("waiting_for_signal", []),
    "observe_only_signal": ("signal_evaluated_observe_only", []),
    "materialization_candidate": ("ready_for_signal_materialization", []),
    "engineering_blocked": ("blocked", ["exact_test_blocker"]),
    "invalid_signal": ("blocked", ["exact_test_blocker"]),
}
```

The test must assert that `strategy_signal_not_ready_for_action_time_ticket` is
not synthesized for computed false, engineering, or invalid outcomes.

- [ ] **Step 3.2: Replace API generic collapse**

In `_runtime_next_attempt_observation_cycle_payload`, replace the branch based
on `evaluation.status == READY_FOR_SEMANTIC_BINDING` with:

```python
cycle = observation_cycle_projection(evaluation.disposition)
```

Use `cycle["status"]`, `cycle["blockers"]`, and `cycle["next_action"]` for the
outer response. Keep the full typed evaluation result embedded.

- [ ] **Step 3.3: Preserve disposition in monitor summaries**

Extend `_signal_summary(...)` and `_summary(...)` to carry:

```text
signal_disposition
signal_disposition_first_blocker
signal_disposition_blockers
may_materialize_signal_event
```

Delete monitor logic that interprets `signal_type=would_enter` as sufficient
candidate readiness.

Update `_overall_status(...)` so per-runtime dispositions aggregate without a
second semantic calculation:

```text
any engineering/invalid blocked -> blocked
else any materialization candidate -> ready_for_signal_materialization
else any observe-only signal -> signal_evaluated_observe_only
else all computed-not-satisfied -> waiting_for_signal
```

Add `ready_for_signal_materialization` to the watcher attention/stop vocabulary,
but keep continuation dependent on the PG projector's named signal IDs. The
outer ready status alone must not authorize Ticket creation.

- [ ] **Step 3.4: Fail closed on missing/unknown disposition**

When a runtime summary lacks the field, produce a typed engineering result:

```text
disposition=engineering_blocked
first_blocker=signal_disposition_missing
```

Do not fall back to `signal_type + outer status` reconstruction.

- [ ] **Step 3.5: Keep watcher dependent on PG result**

The watcher may render developer stdout from the typed disposition but its
post-signal continuation still depends on named PG signal IDs and PG process
outcomes. It must not create a new ready-count path.

- [ ] **Step 3.6: Run transport tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_signal_disposition_api_contract.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py
```

- [ ] **Step 3.7: Commit checkpoint**

```bash
git add \
  src/interfaces/api_trading_console.py \
  scripts/runtime_active_observation_monitor.py \
  scripts/runtime_signal_watcher_tick.py \
  tests/unit/test_runtime_signal_disposition_api_contract.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_signal_watcher_tick.py
git commit -m "refactor(runtime): transport signal disposition without reclassification"
```

## Task 4: PG Signal Projector And Durable Outcome Mapping

**Files:**

- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify only if classifier coverage is missing:
  `src/application/runtime_process_outcome.py`
- Test: `tests/unit/test_runtime_active_observation_monitor.py`
- Test: `tests/unit/test_runtime_process_outcome.py`

**Interfaces:**

- Consumes: runtime summaries containing one typed disposition.
- Produces: named `brc_live_signal_events` rows or lane-scoped
  `live_signal_materialization` process outcomes.

- [ ] **Step 4.1: Add disposition-to-PG RED matrix**

For each disposition assert:

| Disposition | Signal row | Failure outcome |
| --- | ---: | ---: |
| computed-not-satisfied | 0 | 0 |
| observe-only | 1 named, `execution_eligible=false` | 0 on successful projection |
| materialization-candidate | 1 named when Event Spec/facts valid | 0 on success |
| engineering-blocked | 0 | 1 exact lane failure |
| invalid | 0 | 1 exact lane invalid outcome |
| missing/unknown | 0 | 1 exact schema/engineering failure |

- [ ] **Step 4.2: Replace candidate extraction**

Rename `_live_signal_candidates_from_summaries` to a disposition-oriented
function such as:

```python
def _signal_projection_inputs_from_summaries(
    summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for row in summaries:
        signal = row.get("signal_summary")
        if not isinstance(signal, dict):
            signal = {}
        decision = signal.get("signal_disposition")
        if not isinstance(decision, dict):
            decision = {
                "disposition": "engineering_blocked",
                "first_blocker": "signal_disposition_missing",
                "blockers": ["signal_disposition_missing"],
                "may_materialize_signal_event": False,
            }
        disposition = str(decision.get("disposition") or "")
        if disposition == "computed_not_satisfied":
            continue
        if disposition not in {
            "observe_only_signal",
            "materialization_candidate",
            "engineering_blocked",
            "invalid_signal",
        }:
            decision = {
                "disposition": "engineering_blocked",
                "first_blocker": "signal_disposition_unknown",
                "blockers": ["signal_disposition_unknown"],
                "may_materialize_signal_event": False,
            }
        inputs.append(
            {
                "strategy_group_id": str(row.get("strategy_family_id") or ""),
                "strategy_family_version_id": row.get(
                    "strategy_family_version_id"
                ),
                "runtime_instance_id": row.get("runtime_instance_id"),
                "symbol": _compact_symbol(row.get("symbol")),
                "side": _normalize_side(signal.get("side") or row.get("side")),
                "signal_disposition": decision,
                "signal_summary": signal,
                "signal_input_ref": row.get("signal_input_ref"),
            }
        )
    return inputs
```

It includes observe-only, materialization-candidate, engineering-blocked,
invalid, and missing/unknown rows. It excludes only computed-not-satisfied.

- [ ] **Step 4.3: Switch projector on disposition first**

`_write_live_signal_candidate(...)` must:

1. return exact engineering/invalid failure before Event Spec lookup;
2. attempt scope/Event Spec/fact/freshness projection only for observe-only and
   materialization-candidate;
3. call `resolve_execution_eligibility(...)` as the Event Spec upper-bound
   authority;
4. assert observe-only cannot resolve `execution_eligible=true`;
5. include serialized disposition in `signal_payload`;
6. preserve stable identity and terminal/expired behavior.

- [ ] **Step 4.4: Preserve no-signal and later-success behavior**

Assert:

- computed-not-satisfied creates no process row;
- repeated same failure updates the same lane outcome rather than appending an
  unbounded current-state series;
- later same-lane success replaces the current failure;
- expired/terminal repeat is a noop/wait result, not a persistent engineering
  failure;
- no files are written.

- [ ] **Step 4.5: Run PG projector tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_process_outcome.py
```

- [ ] **Step 4.6: Commit checkpoint**

```bash
git add \
  scripts/runtime_active_observation_monitor.py \
  src/application/runtime_process_outcome.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_process_outcome.py
git commit -m "feat(runtime): project signal dispositions into PG truth"
```

Only add `src/application/runtime_process_outcome.py` if it actually changes.

## Task 5: Five-StrategyGroup, 22-Lane, Six-Event-Spec Certification

**Files:**

- Modify: `tests/unit/test_runtime_strategy_signal_evaluation_service.py`
- Modify: `tests/unit/test_action_time_full_chain_impact.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Modify production files only when a RED invariant proves a shared-path defect.

**Interfaces:**

- Consumes: raw evaluator inputs, current candidate/Event-Spec fixtures, PG
  projection functions, promotion/lane/Ticket materializers.
- Produces: full conservation certification without exchange write.

- [ ] **Step 5.1: Certify all five StrategyGroups from raw evaluator inputs**

Required groups:

```text
CPM-RO-001
MPG-001
MI-001
SOR-001
BRF2-001
```

For each, run at least:

1. computed-not-satisfied;
2. valid would-enter;
3. malformed or missing required input;
4. unsupported/mismatched semantic output where applicable.

- [ ] **Step 5.2: Certify all 22 current lanes and six Event Specs**

Extend the existing production-shaped all-scope test so every lane records:

```text
StrategyGroup
symbol
side
event_spec_id
disposition
signal_event_id or exact process outcome
promotion_candidate_id or exact process outcome
action_time_lane_input_id or exact process outcome
ticket_id or exact process outcome
```

Do not derive the lane list from Markdown/JSON. Use the existing PG/current
fixture/seed path used by the full-chain impact suite.

- [ ] **Step 5.3: Certify temporal identity cases**

For every current Event Spec class, cover:

- first observation;
- repeated same identity;
- expired observation;
- terminal prior progression;
- next distinct event identity;
- later same-lane successful materialization.

- [ ] **Step 5.4: Enforce adjacent-boundary conservation**

Apply `assert_identity_or_exact_outcome` after signal, promotion, lane, and
Ticket materialization. A missing downstream object without an exact process
outcome is a test failure even if the final aggregate status looks healthy.

- [ ] **Step 5.5: Run the full certification slice**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_action_time_full_chain_impact.py
```

Expected: every current lane has a downstream identity or exact same-lane
outcome; no exchange gateway is called.

- [ ] **Step 5.6: Commit checkpoint**

```bash
git add tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_action_time_full_chain_impact.py
git commit -m "test(runtime): certify signal disposition across active lanes"
```

If the RED census requires a shared production fix, include only the exact
producer file and state the newly proven blocker in the commit message/body.

## Task 6: Replay/Live Parity And Owner Notification Truth

**Files:**

- Modify only if resolver is not already shared:
  `src/domain/strategygroup_runtime_replay.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Modify: `src/application/owner_notification.py`
- Create: `tests/unit/test_strategygroup_runtime_replay_disposition_parity.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_owner_notification_scenarios.py`
- Test: `tests/unit/test_owner_notification_delivery.py`

**Interfaces:**

- Consumes: typed disposition, PG signal/event eligibility, PG process outcome.
- Produces: parity assertions and plain deduplicated Owner notification intent.

- [ ] **Step 6.1: Prove Replay/Live disposition parity**

For the same typed evaluation result, Replay and Live must produce the same
disposition. Replay must not create PG current rows or any trading authority.

- [ ] **Step 6.2: Preserve notification separation**

Assert:

- computed-not-satisfied -> quiet;
- observe-only named signal -> quiet;
- named fresh `execution_eligible=true` signal -> opportunity processing card;
- engineering/invalid outcome -> Chinese no-order system-processing card;
- repeated event -> PG dedupe suppression;
- watcher direct Feishu remains impossible.

- [ ] **Step 6.3: Run parity and notification tests**

```bash
python3 -m pytest -q \
  tests/unit/test_strategygroup_runtime_replay_disposition_parity.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_runtime_signal_watcher_tick.py
```

- [ ] **Step 6.4: Commit checkpoint**

```bash
git add \
  src/domain/strategygroup_runtime_replay.py \
  scripts/run_tokyo_runtime_server_monitor.py \
  src/application/owner_notification.py \
  tests/unit/test_strategygroup_runtime_replay_disposition_parity.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  tests/unit/test_runtime_signal_watcher_tick.py
git commit -m "test(runtime): align disposition parity and owner truth"
```

Only stage files that actually changed.

## Task 7: Regression, Governance, Integration, And Tokyo Acceptance

**Files:**

- Modify after implementation evidence exists:
  `docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_DESIGN.md`
- Modify:
  `docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`

**Interfaces:**

- Consumes: complete local test/audit evidence and exact deploy head.
- Produces: integrated `dev`, exact Tokyo release, PG-backed production
  acceptance, and current roadmap truth.

- [ ] **Step 7.1: Run targeted tests**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_signal_disposition.py \
  tests/unit/test_runtime_signal_disposition_api_contract.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_process_outcome.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py
```

- [ ] **Step 7.2: Run pre-trade chain regression**

```bash
python3 -m pytest -q \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_action_time_finalgate_preflight_api.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py
```

- [ ] **Step 7.3: Run governance and performance gates**

```bash
python3 -m compileall -q src scripts
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py --json --fail-on-risk
git diff --check
```

Required:

```text
current_docs_authority_valid
output_artifact_scope_valid
performance_risk.status=clear
performance_risk.risk_count=0
```

- [ ] **Step 7.4: Review safety and authority diff**

Confirm no changed file modifies:

```text
strategy thresholds
candidate scope
capital or leverage
order sizing defaults
runtime profiles
FinalGate bypass
Operation Layer bypass
exchange gateway write behavior
protection or reconciliation authority
```

- [ ] **Step 7.5: Update current docs from fresh evidence**

Change both task documents to `COMPLETED_AND_DEPLOYED` only after production
acceptance. Record exact test counts, implementation-bearing head, final exact
release head, migration count, and natural-event result without turning docs
into runtime authority.

- [ ] **Step 7.6: Commit, integrate, and push**

```bash
git status --short
git add \
  src/domain/strategy_family_signal.py \
  src/application/runtime_signal_disposition.py \
  src/application/runtime_strategy_signal_evaluation_service.py \
  src/interfaces/api_trading_console.py \
  scripts/runtime_active_observation_monitor.py \
  scripts/runtime_signal_watcher_tick.py \
  scripts/run_tokyo_runtime_server_monitor.py \
  src/application/owner_notification.py \
  tests/unit/test_runtime_signal_disposition.py \
  tests/unit/test_runtime_signal_disposition_api_contract.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_strategy_family_signal_contract.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_runtime_process_outcome.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_strategygroup_runtime_replay_disposition_parity.py \
  tests/unit/test_tokyo_runtime_server_monitor.py \
  tests/unit/test_owner_notification_scenarios.py \
  tests/unit/test_owner_notification_delivery.py \
  docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_DESIGN.md \
  docs/current/P0_SIGNAL_DISPOSITION_SSOT_AND_CROSS_LANE_HANDOFF_CERTIFICATION_IMPLEMENTATION_PLAN.md \
  docs/current/MAIN_CONTROL_ROADMAP.md \
  docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md
git commit -m "feat(runtime): unify signal disposition across live handoffs"
```

Review the focused branch, cherry-pick its ordered commits into `dev`, rerun the
targeted gate from `dev`, and push `origin/dev`.

- [ ] **Step 7.7: Run Tokyo deploy dry-run and apply**

Resolve exact values from current git and the deployed manifest, then run the
official deploy script:

```bash
TARGET_COMMIT="$(git rev-parse origin/dev)"
CURRENT_DEPLOYED_HEAD="$(ssh tokyo \
  'jq -r .local_git.head /home/ubuntu/brc-deploy/app/current/.brc-release-manifest.json')"
PREVIOUS_RELEASE="$(ssh tokyo 'readlink -f /home/ubuntu/brc-deploy/app/current')"
RELEASE_NAME="brc-runtime-governance-${TARGET_COMMIT:0:8}-$(date +%Y%m%d)"

python3 scripts/execute_tokyo_runtime_governance_git_deploy.py --json \
  --git-ref dev \
  --target-commit "$TARGET_COMMIT" \
  --release-name "$RELEASE_NAME" \
  --previous-release "$PREVIOUS_RELEASE" \
  --expected-deployed-head "$CURRENT_DEPLOYED_HEAD" \
  --expected-remote-migration-count 117 \
  --expected-remote-latest-migration \
    2026-07-12-117_extend_owner_notifications.py \
  --expected-latest-migration \
    2026-07-12-117_extend_owner_notifications.py
```

The dry-run must be `dry_run_ready` with zero blockers. Then run the same
command with `--apply` immediately after the script name and unchanged shell
variables.

- [ ] **Step 7.8: Run production acceptance without exchange write**

1. Verify exact release head and migration `117`.
2. Run one watcher oneshot and one server-monitor oneshot.
3. Verify watcher and monitor timers remain active.
4. Query PG process outcomes for `live_signal_materialization`.
5. Verify computed-not-satisfied creates no failure row.
6. Verify any materialization candidate has a named signal or exact lane
   failure.
7. Verify observe-only never promotes or notifies as opportunity.
8. Verify no Ticket/order/exchange write unless a distinct natural eligible
   event legitimately reaches the official path.

- [ ] **Step 7.9: Natural-event interrupt acceptance**

If a distinct natural event arrives during implementation or acceptance:

```text
persist evaluator disposition
-> persist named signal or exact signal outcome
-> persist promotion/lane/Ticket identity or exact process outcome
-> preserve FinalGate/Operation Layer/protection boundaries
-> record Owner notification delivery/dedupe
```

Do not convert replay, synthetic input, or the historical CPM/SOL event into
live authority.

## Completion Gate

The task is complete only when all are true:

- [ ] The five dispositions are mutually exclusive and mandatory.
- [ ] `would_enter + waiting_for_signal` is impossible in the shared API path.
- [ ] CPM/SOL/short has an exact deterministic disposition and first blocker.
- [ ] Five StrategyGroups, 22 lanes, and six Event Specs pass certification.
- [ ] Every may-advance boundary has a downstream identity or exact same-lane
      process outcome through Ticket.
- [ ] Replay/Live disposition parity passes.
- [ ] Owner notification truth and PG dedupe pass.
- [ ] No-signal ticks write zero JSON/MD files.
- [ ] Production file-I/O performance risk is clear.
- [ ] No authority or risk parameter expands.
- [ ] `dev`, `origin/dev`, Tokyo release manifest, and capability certification
      agree on the exact head.
- [ ] The next remaining first blocker is named from fresh PG evidence.

## Expected Live Enablement Transition

```text
Before:
evaluation output may say would_enter
-> API may say waiting_for_signal
-> no PG signal identity
-> lane process failure now conserved but producer meaning ambiguous

After:
evaluation result owns one disposition
-> API transports it without reinterpretation
-> PG creates named signal or exact lane outcome
-> execution-eligible signal creates promotion/lane/Ticket or exact boundary outcome
-> Owner sees only PG-backed product meaning
```

## Implementation Pause

This plan is intentionally paused at Owner confirmation. No production code,
test code, integration, push, or deployment step may begin from this document
until the Owner confirms the design and implementation plan.
