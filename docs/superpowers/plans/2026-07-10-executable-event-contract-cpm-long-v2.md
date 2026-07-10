# Executable Event Contract And CPM-LONG v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make observed strategy facts truthful and certify `CPM-LONG v2` as the only trial-grade Event Spec without deploying or calling the exchange.

**Architecture:** Extend the existing pure signal output with typed fact observations, remove expected-as-observed fact synthesis, and create versioned CPM StrategyGroup/Event Spec/RequiredFacts/execution-policy rows through migration 107 and the foundation seed. Reuse the existing execution-eligibility envelope and `authority_source_ref` through promotion, ticket, Runtime Safety, and protected submit.

**Tech Stack:** Python 3.14 local runtime, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL/SQLite migration tests, pytest.

## Global Constraints

- Do not modify SOR, MPG, MI, or BRF2 signal grade or execution mode.
- Do not change CPM thresholds, symbol set, notional, leverage, loss unit, attempt cap, runtime profile, protection policy, FinalGate, Operation Layer, or exchange gateway.
- Preserve CPM v1 historical rows as observe-only and ineligible.
- `expected_value` is never an observed fact.
- No replay, synthetic, audit, or disabled-smoke input gains exchange-write authority.
- No production deploy, runtime restart, PG production mutation, FinalGate call, Operation Layer call, or exchange write.
- One no-signal tick creates `0` JSON/MD files.

---

### Task 1: Typed Strategy Fact Observations And CPM Grade

**Files:**
- Modify: `src/domain/strategy_family_signal.py`
- Modify: `src/domain/cpm_historical_evaluator.py`
- Modify: `tests/unit/test_strategy_family_signal_contract.py`

**Interfaces:**
- Produces: `StrategyFactObservation(fact_key, observed_value, observed_at_ms, valid_until_ms, source_ref)`.
- Produces: `StrategyFamilySignalOutput.fact_observations`.
- CPM long `WOULD_ENTER` produces `trial_grade_signal` / `trial_live`; all other CPM outputs remain observe-only or invalid.

- [ ] **Step 1: Write failing typed-fact and CPM authority tests**

```python
def test_cpm_long_would_enter_emits_trial_grade_observed_facts():
    output = CPMRO001HistoricalEvaluator().evaluate(cpm_long_signal_input())
    assert output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    facts = {item.fact_key: item.observed_value for item in output.fact_observations}
    assert facts == {
        "htf_trend_intact": True,
        "reclaim_confirmed": True,
        "pullback_low_reference": Decimal("95"),
    }

def test_cpm_short_would_enter_remains_observe_only():
    output = CPMRO001HistoricalEvaluator().evaluate(cpm_short_signal_input())
    assert output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL
    assert output.required_execution_mode == RequiredExecutionMode.OBSERVE_ONLY
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest -q tests/unit/test_strategy_family_signal_contract.py -k 'cpm and (trial_grade or observed_facts or short_would_enter)'
```

Expected: FAIL because `StrategyFactObservation`/`fact_observations` and CPM trial-grade output do not exist.

- [ ] **Step 3: Add the pure model and minimal CPM output logic**

Add to `strategy_family_signal.py`:

```python
class StrategyFactObservation(StrategyFamilySignalModel):
    fact_key: str = Field(min_length=1, max_length=128)
    observed_value: bool | Decimal | int | str
    observed_at_ms: int = Field(ge=0)
    valid_until_ms: int = Field(gt=0)
    source_ref: str = Field(min_length=1, max_length=256)

# Add this field to the existing StrategyFamilySignalOutput model.
fact_observations: list[StrategyFactObservation] = Field(default_factory=list)
```

In CPM `_would_enter`, emit trial grade and the three facts only for `LONG`.
Use `trigger_candle_close_time_ms` as observation time and one hour as validity.
Reject a missing/non-positive `lookback_low` from trial-grade output.

- [ ] **Step 4: Run Task 1 tests and verify GREEN**

Run:

```bash
pytest -q tests/unit/test_strategy_family_signal_contract.py
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/domain/strategy_family_signal.py src/domain/cpm_historical_evaluator.py tests/unit/test_strategy_family_signal_contract.py
git commit -m "feat(strategy): emit typed CPM trial facts"
```

### Task 2: Remove Fabricated Action-Time Facts

**Files:**
- Modify: `src/application/action_time/fact_snapshots.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`

**Interfaces:**
- Consumes: `signal_payload.signal_summary.fact_observations`.
- Produces: fact values only from typed observations, trusted public values, or explicit reference aliases.

- [ ] **Step 1: Write failing missing-fact tests**

```python
def test_missing_required_boolean_is_not_filled_from_expected_value():
    value = fact_materializer._derive_fact_value(
        key="htf_trend_intact",
        fact={"operator": "eq", "expected_value": True, "disable_on_match": False},
        event_id="CPM-LONG",
        protection_ref_type="pullback_low_reference",
        source_values={},
        reason_codes=[],
    )
    assert value is None

def test_expr_ref_without_observation_is_missing():
    value = fact_materializer._derive_fact_value(
        key="custom_expr_fact",
        fact={"operator": "expr_ref", "expected_value": None, "disable_on_match": False},
        event_id="CPM-LONG",
        protection_ref_type="pullback_low_reference",
        source_values={},
        reason_codes=[],
    )
    assert value is None
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py -k 'expected_value or expr_ref_without or typed_fact_observation'
```

Expected: FAIL because the current materializer synthesizes expected values.

- [ ] **Step 3: Implement truthful fact resolution**

Add a helper that converts typed observations into a fact map:

```python
def _typed_fact_observation_values(signal_summary: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in _as_list(signal_summary.get("fact_observations")):
        row = _as_dict(item)
        key = str(row.get("fact_key") or "")
        if key and row.get("observed_value") is not None:
            values[key] = row["observed_value"]
    return values
```

Merge this source before generic evidence. Delete:

```python
expected = fact.get("expected_value")
if expected is not None:
    return expected
if str(fact.get("operator") or "") == "expr_ref":
    return True
```

Keep only exact supported derivations and protection-reference aliases.

- [ ] **Step 4: Add the positive CPM fact test**

```python
def test_cpm_typed_fact_observations_are_first_class_source_values():
    signal_summary = {
        "fact_observations": [
            {"fact_key": "htf_trend_intact", "observed_value": True},
            {"fact_key": "reclaim_confirmed", "observed_value": True},
            {"fact_key": "pullback_low_reference", "observed_value": "95"},
        ]
    }
    values = fact_materializer._typed_fact_observation_values(signal_summary)
    assert values == {
        "htf_trend_intact": True,
        "reclaim_confirmed": True,
        "pullback_low_reference": "95",
    }
```

- [ ] **Step 5: Run Task 2 tests and verify GREEN**

Run:

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py
```

Expected: all tests pass after fixtures explicitly provide facts they previously synthesized.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/application/action_time/fact_snapshots.py tests/unit/test_pg_promotion_action_time_lane_materialization.py
git commit -m "fix(runtime): require observed strategy facts"
```

### Task 3: Versioned CPM-LONG v2 Seed And Migration 107

**Files:**
- Create: `migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py`
- Modify: `scripts/seed_runtime_control_state_foundation.py`
- Create: `tests/unit/test_cpm_long_v2_migration.py`
- Modify: `tests/unit/test_pg_runtime_control_state_foundation_migration.py`
- Modify: `tests/unit/test_pg_migration_identifier_names.py`

**Interfaces:**
- Produces: `sgv:CPM-RO-001:v2` as current CPM version.
- Produces: `event_spec:CPM-RO-001:CPM-LONG:v2` as the current trial-grade event.
- Produces: active CPM candidate bindings and execution policy referencing v2.

- [ ] **Step 1: Write failing seed and migration tests**

```python
def test_fresh_seed_certifies_only_cpm_long_v2():
    rows = build_seed_rows()
    events = rows["brc_strategy_side_event_specs"]
    eligible = [row for row in events if row["execution_eligibility_enabled"]]
    assert [(row["strategy_group_id"], row["event_id"], row["event_spec_version"])
            for row in eligible] == [("CPM-RO-001", "CPM-LONG", "v2")]

def test_migration_107_preserves_cpm_v1_and_activates_v2(connection):
    upgrade_to_106(connection)
    migration_107.upgrade()
    assert current_cpm_event(connection)["event_spec_version"] == "v2"
    assert historical_cpm_v1(connection)["status"] == "retired"
```

- [ ] **Step 2: Run migration tests and verify RED**

Run:

```bash
pytest -q tests/unit/test_cpm_long_v2_migration.py tests/unit/test_pg_runtime_control_state_foundation_migration.py tests/unit/test_pg_migration_identifier_names.py
```

Expected: FAIL because migration 107 and version-aware seed do not exist.

- [ ] **Step 3: Make the seed version-aware**

Extend `EventSeed` with explicit version and authority fields:

```python
strategy_group_version: int = 1
event_spec_version: str = "v1"
declared_signal_grade: str = "observe_only_signal"
declared_required_execution_mode: str = "observe_only"
execution_eligibility_enabled: bool = False
```

Set CPM to version 2/trial-grade/trial-live/enabled. Derive IDs from these
fields. All other seeds retain version 1 and observe-only authority.

- [ ] **Step 4: Implement migration 107**

The migration must copy stable CPM v1 version/policy fields, create v2 rows,
retire/supersede v1, replace CPM active event bindings, and update
`brc_strategy_groups.current_version_id`. It must not change Owner policy,
runtime scope, candidate symbols, capital, profile, leverage, or notional.

The migration must be idempotent under the project's migration test harness and
must perform no runtime/exchange call.

- [ ] **Step 5: Run Task 3 tests and verify GREEN**

Run:

```bash
pytest -q tests/unit/test_cpm_long_v2_migration.py tests/unit/test_pg_runtime_control_state_foundation_migration.py tests/unit/test_pg_migration_identifier_names.py
```

Expected: all tests pass; exactly one Event Spec is execution-eligible.

- [ ] **Step 6: Commit Task 3**

```bash
git add migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py scripts/seed_runtime_control_state_foundation.py tests/unit/test_cpm_long_v2_migration.py tests/unit/test_pg_runtime_control_state_foundation_migration.py tests/unit/test_pg_migration_identifier_names.py
git commit -m "feat(runtime): certify CPM-LONG v2 event"
```

### Task 4: Watcher And Authority-Lineage Integration

**Files:**
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_strategy_semantic_admission.py`

**Interfaces:**
- Consumes CPM evaluator grade/mode/fact observations and current CPM Event Spec v2.
- Produces eligible CPM live-signal rows with exact `authority_source_ref`.

- [ ] **Step 1: Write failing watcher integration tests**

```python
def test_cpm_v2_trial_signal_is_written_execution_eligible(connection):
    candidate = cpm_long_candidate_with_typed_facts()
    result = _write_live_signal_candidate(connection, candidate=candidate, observed_ms=NOW_MS)
    assert result["execution_eligible"] is True
    row = latest_signal(connection)
    assert row["authority_source_ref"] == "event-spec:event_spec:CPM-RO-001:CPM-LONG:v2"

def test_cpm_trial_evaluator_against_v1_observe_event_is_rejected(connection):
    connection.execute(text("""
        UPDATE brc_strategy_side_event_specs
        SET declared_signal_grade='observe_only_signal',
            declared_required_execution_mode='observe_only',
            execution_eligibility_enabled=false
        WHERE event_spec_id='event_spec:CPM-RO-001:CPM-LONG:v2'
    """))
    candidate = cpm_long_candidate_with_typed_facts()
    result = _write_live_signal_candidate(connection, candidate=candidate, observed_ms=NOW_MS)
    assert result["blocker"] == "execution_eligibility_authority_invalid"
```

- [ ] **Step 2: Run watcher tests and verify RED**

Run:

```bash
pytest -q tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_strategy_semantic_admission.py -k 'cpm or execution_eligibility'
```

Expected: FAIL until seed/migration fixtures and candidate summaries preserve typed facts and v2 authority.

- [ ] **Step 3: Preserve typed facts in the watcher summary and PG payload**

Ensure `_live_signal_candidates_from_summaries` copies `fact_observations` as
part of `signal_summary`; do not create another authority field or file.
Continue to use `resolve_execution_eligibility` as the grade/mode upper
bound.

- [ ] **Step 4: Verify semantic admission**

Assert CPM candidates become `trial_grade_capable` while all other candidate
admissions remain `observe_only_by_design`.

- [ ] **Step 5: Run Task 4 tests and verify GREEN**

Run:

```bash
pytest -q tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_strategy_semantic_admission.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 4**

```bash
git add scripts/runtime_active_observation_monitor.py tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_strategy_semantic_admission.py
git commit -m "feat(watcher): admit CPM trial signals"
```

### Task 5: Vertical Regression And Completion Evidence

**Files:**
- Modify only if a RED test proves a real regression in the approved scope.
- Test: current action-time, safety, protected-submit, candidate-pool, monitor, migration, and file-authority suites.

**Interfaces:**
- Consumes all earlier tasks.
- Produces verified local capability; no deploy or production mutation.

- [ ] **Step 1: Run the focused vertical regression**

```bash
pytest -q \
  tests/unit/test_strategy_family_signal_contract.py \
  tests/unit/test_cpm_long_v2_migration.py \
  tests/unit/test_execution_eligibility_migration.py \
  tests/unit/test_runtime_active_observation_monitor.py \
  tests/unit/test_strategy_semantic_admission.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_ticket_bound_runtime_safety_state_materialization.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_tokyo_runtime_server_monitor.py
```

Expected: all tests pass; no exchange call occurs.

- [ ] **Step 2: Run governance and performance validators**

```bash
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
python3 scripts/validate_no_runtime_file_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
```

Expected:

```text
suspicious_runtime_file_authority=0
frequent_report_write=0
no_runtime_file_authority_valid
output_artifact_scope_valid
```

- [ ] **Step 3: Verify scope and chain position**

Confirm from tests/fixtures:

```text
CPM Event Specs: v1 historical observe-only, v2 current trial-grade
Other Event Specs: observe-only
CPM candidate count: 4
Maximum real-submit lane: 1
Replay/synthetic exchange writes: 0
Profile/sizing changes: 0
```

- [ ] **Step 4: Commit any test-only acceptance updates**

```bash
git add tests
git commit -m "test(runtime): verify CPM executable event contract"
```

Skip this commit if Task 5 creates no file changes.
