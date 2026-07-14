# P0-W3 Stage-Aware PG Truth Implementation Plan

> Execute inline with strict red-green TDD. Do not call a real exchange endpoint.

**Goal:** Correct pre-action-time blocker semantics, unify runtime test/bootstrap
infrastructure, and certify SOR/BRF2 v2 events through the official PG runtime
chain.

**Architecture:** PG Event Specs declare capability; pure evaluators emit event
facts; Candidate Pool classifies the earliest stage; Goal Status aggregates only
runtime-critical blockers; forward-only migrations activate v2 semantics.

**Tech stack:** Python 3, Pydantic, SQLAlchemy, Alembic, pytest, PostgreSQL and
SQLite test fixtures.

## File Map

### New files

- `src/domain/sor_session_range_evaluator.py`: pure 15m long/short SOR evaluator.
- `tests/unit/test_sor_session_range_evaluator.py`: SOR event contract tests.
- `tests/support/runtime_control_state_schema.py`: canonical test schema installer.
- `tests/unit/test_runtime_control_state_fresh_bootstrap.py`: supported bootstrap tests.
- `migrations/versions/2026-07-10-110_certify_sor_session_events.py`: atomic SOR v2 certification.
- `migrations/versions/2026-07-10-111_certify_brf2_short_event.py`: BRF2 v2 certification.
- `tests/unit/test_sor_v2_migration.py`: SOR migration assertions.
- `tests/unit/test_brf2_v2_migration.py`: BRF2 migration assertions.

### Modified files

- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`: add the pre-execution capability blocker.
- `src/application/readmodels/strategy_live_candidate_pool.py`: classify observe-only events correctly.
- `src/application/readmodels/strategygroup_runtime_goal_status.py`: keep observe-only work out of global runtime-fact failure.
- `src/application/readmodels/runtime_strategy_signal_input.py`: source primary timeframe from current PG Event Spec.
- `src/application/runtime_strategy_signal_evaluation_service.py`: route SOR and BRF2 through trial-grade event-specific evaluators.
- `scripts/build_sor_session_scope_detector.py`: consume the pure SOR evaluator instead of owning a second rule set.
- `scripts/seed_runtime_control_state_foundation.py`: seed v2 definitions for fresh bootstrap after migrations activate them.
- Action-time test modules with partial migration fixtures: use the canonical schema installer.
- Goal Status, Candidate Pool, signal evaluation, watcher, and migration tests: assert new behavior.

## Task 1: Correct the stage-aware blocker contract

### Step 1: Write failing Candidate Pool tests

Add tests in `tests/unit/test_strategy_live_candidate_pool.py` and
`tests/unit/test_strategygroup_runtime_goal_status.py` that assert:

```python
assert observe_only_row["first_blocker"] == (
    "event_execution_capability_not_certified"
)
assert executable_row["first_blocker"] == "market_wait_validated"
assert goal_status["status"] == "healthy_waiting"
assert not any(
    "event_execution_capability_not_certified" in blocker
    for blocker in goal_status["blockers"]
)
```

The fixture must contain at least one executable market-wait row and one
observe-only row. Run:

```bash
pytest -q \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_strategygroup_runtime_goal_status.py \
  -k 'execution_capability or observe_only_does_not_poison'
```

Expected: FAIL because observe-only currently maps to
`action_time_boundary_not_reproduced` and Goal Status treats it as missing fact.

### Step 2: Implement the blocker

In `src/application/readmodels/strategy_live_candidate_pool.py`:

```python
EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED = (
    "event_execution_capability_not_certified"
)

def _event_spec_execution_eligibility_blocker(event_spec: dict[str, Any]) -> str:
    if "execution_eligibility_enabled" not in event_spec:
        return ""
    if (
        event_spec.get("execution_eligibility_enabled") is not True
        or event_spec.get("declared_signal_grade")
        not in {"trial_grade_signal", "production_grade_signal"}
        or event_spec.get("declared_required_execution_mode")
        not in {"trial_live", "production_live"}
    ):
        return EVENT_EXECUTION_CAPABILITY_NOT_CERTIFIED
    return ""
```

Map the next action to `certify_event_execution_capability_or_keep_observe_only`
and rank it after runtime coverage but before action-time.

In `src/application/readmodels/strategygroup_runtime_goal_status.py`, treat the
new class as a per-event engineering state, not a global runtime-fact outage:

```python
NON_GLOBAL_OBSERVE_ONLY_BLOCKERS = {
    "event_execution_capability_not_certified",
}
```

Exclude only these blockers from `_pg_non_market_blockers`; do not exclude
scope, watcher, safety, or action-time failures.

Add the class and exact meaning to
`docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`.

### Step 3: Run tests and commit

Run the Task 1 test command and the related daily/tradeability tests. Expected:
PASS. Commit:

```bash
git add docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md \
  src/application/readmodels/strategy_live_candidate_pool.py \
  src/application/readmodels/strategygroup_runtime_goal_status.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_strategygroup_runtime_goal_status.py
git commit -m "fix(runtime): classify event capability before action time"
```

## Task 2: Consolidate runtime-control test schema and bootstrap

### Step 1: Write failing schema/bootstrap tests

Create `tests/support/runtime_control_state_schema.py` with a wished-for API:

```python
install_runtime_control_state_schema(conn, through_revision="104")
seed_runtime_control_state(conn)
```

Create `tests/unit/test_runtime_control_state_fresh_bootstrap.py` asserting:

```python
install_runtime_control_state_schema(conn, through_revision="104")
columns = {column["name"] for column in inspect(conn).get_columns(
    "brc_strategy_side_event_specs"
)}
assert {
    "declared_signal_grade",
    "declared_required_execution_mode",
    "execution_eligibility_enabled",
} <= columns
```

Add a PostgreSQL-capable integration test for the supported fresh sequence:

```text
upgrade 106 -> deterministic seed -> upgrade head
```

Skip only when the existing PG test DSN is unavailable. Run the new unit test;
expected FAIL because the helper does not exist.

### Step 2: Implement canonical installer

The helper loads and applies exact migrations by revision, always restoring
Alembic's global `op` binding in `finally`. It must support SQLite test schemas
and must not write files. Required revision groups:

```python
FOUNDATION = "086"
RISK_AT_STOP = "103"
EXECUTION_ELIGIBILITY = "104"
```

It calls the existing deterministic seed function only when explicitly
requested.

Replace partial fixture stacks in the failing action-time modules with this
helper. Start with:

- `tests/unit/test_action_time_finalgate_preflight_materialization.py`
- `tests/unit/test_action_time_operation_layer_handoff_materialization.py`
- `tests/unit/test_action_time_full_chain_impact.py`

Then run the full suite once later to identify any additional partial fixtures.

### Step 3: Verify baseline failures are gone and commit

Run:

```bash
pytest -q \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/unit/test_action_time_operation_layer_handoff_materialization.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_runtime_control_state_fresh_bootstrap.py
```

Expected: PASS. Commit the helper, tests, and fixture replacements.

## Task 3: Make runtime signal input timeframe PG-owned

### Step 1: Write failing input-builder tests

In `tests/unit/test_runtime_strategy_signal_input_artifact_script.py`, assert
that an active PG SOR Event Spec with timeframe `15m`
causes the builder to:

```python
assert signal_input.primary_timeframe == "15m"
assert "15m" in signal_input.market_snapshot.candle_context["windows"]
assert signal_input.trigger_candle_close_time_ms == candles_15m[-1].close_time_ms
```

Also prove MPG remains `1h`. Expected initial FAIL because the builder hardcodes
`1h`.

### Step 2: Implement PG event contract lookup

Add a typed internal value such as:

```python
@dataclass(frozen=True)
class RuntimeEventInputContract:
    event_spec_id: str
    event_id: str
    side: str
    primary_timeframe: str
```

Load it by joining active candidate scope, active binding, and current Event
Spec for runtime StrategyGroup + symbol + side. Fail closed on zero or multiple
rows.

Generalize `build_signal_input` to accept `primary_candles`,
`primary_timeframe`, and `context_candles_by_timeframe`. Preserve a `4h`
context window for evaluators that need it. Do not add a StrategyGroup-to-
timeframe constant.

### Step 3: Run input/watcher tests and commit

Run signal input, watcher, and comparative-strength tests. Expected: PASS.

## Task 4: Implement the canonical SOR 15m evaluator

### Step 1: Write failing pure-domain tests

Create `tests/unit/test_sor_session_range_evaluator.py` with independent cases:

- long close above opening high with follow-through;
- short close below opening low with follow-through;
- no-action inside the range;
- stale/unclosed input invalid;
- long protection ref is range low;
- short protection ref is range high;
- `WOULD_ENTER` alone emits trial grade/mode and exact fact observations;
- output side must equal the runtime/event side.

Expected assertions include:

```python
assert output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
assert output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
assert {fact.fact_key for fact in output.fact_observations} == {
    "opening_range_defined",
    "breakout_confirmed",
    "opening_range_low_reference",
}
```

Run and verify import failure.

### Step 2: Implement the evaluator

Create `src/domain/sor_session_range_evaluator.py`. It accepts only closed 15m
candles, uses the first four UTC-session 15m bars as the opening range, and
evaluates the latest closed bar. It does no I/O.

`WOULD_ENTER` outputs include three typed `StrategyFactObservation` rows with
validity ending one 15m freshness window after trigger close. No-action/invalid
outputs remain observe-only.

Register this evaluator for `("SOR-001", "SOR-001-v0")` in
`runtime_strategy_signal_evaluation_service.py`.

Update `build_sor_session_scope_detector.py` to translate its candle payloads
into the same evaluator instead of recomputing trigger rules.

### Step 3: Run SOR tests and commit

Run SOR evaluator, detector, signal service, and watcher tests. Expected: PASS.

## Task 5: Make BRF2 outputs satisfy the event contract

### Step 1: Write failing BRF2 wrapper tests

Extend `tests/unit/test_runtime_strategy_signal_evaluation_service.py` for:

- confirmed bear-rally failure produces trial-grade short;
- strong uptrend stays no-action observe-only;
- successful output includes `rally_failure_confirmed`,
  `short_side_not_disabled`, `rally_high_reference`, and explicit
  `strong_uptrend_disable=false`;
- no long output can be produced.

Expected initial FAIL because the wrapper preserves observe-only grade and no
fact observations.

### Step 2: Implement event-specific retargeting

Update `_BRF2LiveReferenceEvaluator.evaluate` so only an exact short
`WOULD_ENTER` retargets to trial grade/mode. Extract the rally high from
`price_action_structure.rally_high_reference` and attach the required and
disable fact observations. Missing evidence returns invalid observe-only.

### Step 3: Run BRF2 tests and commit

Run BRF evaluator, signal service, watcher, ticket disable-fact, and promotion
tests. Expected: PASS.

## Task 6: Add forward-only SOR and BRF2 v2 migrations

### Step 1: Write failing migration tests

Create SOR and BRF2 migration tests that seed the v1 state, apply migrations,
and assert:

```python
assert current_group_version == "sgv:SOR-001:v2"
assert active_sor_events == {
    "event_spec:SOR-001:SOR-LONG:v2",
    "event_spec:SOR-001:SOR-SHORT:v2",
}
assert all(row["execution_eligibility_enabled"] for row in active_events)
assert active_sor_binding_count == 8
assert active_brf2_binding_count == 3
assert brf2_sides == {"short"}
```

Assert downgrade rejects existing v2 signal lineage.

### Step 2: Implement migrations 110 and 111

Follow the transactional copy-then-switch pattern of migrations 108/109.
SOR migration creates one v2 group version with both events. BRF2 migration
creates one short event. Clone exact RequiredFacts, policies, and bindings;
retire v1 only after v2 inserts succeed.

Do not modify migrations 107-109.

### Step 3: Run migration tests and commit

Run migrations 104 and 107-111 tests. Expected: PASS.

## Task 7: Prove the unified non-executing chain

### Step 1: Add full-chain acceptance cases

Extend `tests/unit/test_action_time_full_chain_impact.py` with SOR-LONG,
SOR-SHORT, and BRF2-SHORT v2 cases. Each synthetic fixture must remain
`source_kind=synthetic` or test-only and must use disabled smoke. Assert:

```python
assert result["ticket_id"]
assert result["submit_mode"] == "disabled_smoke"
assert result["exchange_write_called"] is False
assert result["order_created"] is False
```

Add negative tests proving observe-only v1 cannot promote and replay/synthetic
cannot become a fresh live-market submit signal.

### Step 2: Run targeted acceptance

Run all P0-W3 touched test modules, then:

```bash
python3 scripts/audit_production_runtime_file_io.py --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Expected: targeted tests pass, `performance_risk.status=clear`, zero frequent
report writers, and no tracked output artifacts.

### Step 3: Run full regression

Run:

```bash
pytest -q
```

Record exact passed/failed/skipped counts. Fix only P0-W3 regressions. Any
unrelated pre-existing failure must be proven against `dev` before exclusion.

### Step 4: Self-review and final commit

Review the diff for:

- strategy identity shortcuts;
- unsupported side mirroring;
- replay/live authority leakage;
- migration mutation of 107-109;
- JSON/MD runtime reads or writes;
- changes to Owner policy, profile, notional, leverage, or credentials.

Commit the final acceptance/docs changes. Do not push, deploy, or place an
exchange order in this plan.
