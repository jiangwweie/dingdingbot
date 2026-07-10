# Execution Eligibility Authority Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make observe-only strategy signals structurally incapable of reaching a real-submit lane while preserving them as review evidence.

**Architecture:** A versioned Event Spec declares the maximum signal grade and execution mode. The watcher validates evaluator output against that declaration, persists an immutable authority envelope, and every later authority transition copies and independently rechecks the envelope. Deployment uses a short maintenance window; there is no online dual-write or compatibility path.

**Tech Stack:** Python 3.12, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL/SQLite migration tests, pytest.

## Global Constraints

- Existing Event Specs and signals backfill to `observe_only_signal`, `observe_only`, `execution_eligible=false`.
- No existing StrategyGroup receives trial-grade or production-grade authority.
- Owner policy and Runtime Safety may restrict eligibility but cannot upgrade it.
- No exchange calls, live-profile changes, sizing changes, JSON/Markdown runtime authority, or recurring artifact writer.
- Production deployment is stop timers, migrate, deploy matching code, verify read-only, restart timers.
- A no-signal production tick creates zero files and no additional PG rows beyond existing current projections.

---

### Task 1: Typed authority semantics and migration 104

**Files:**
- Modify: `src/domain/strategy_family_signal.py`
- Create: `src/domain/execution_eligibility.py`
- Create: `migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py`
- Modify: `tests/unit/test_strategy_family_signal_contract.py`
- Create: `tests/unit/test_execution_eligibility_migration.py`

**Interfaces:**
- Produces: `SignalGrade`, `RequiredExecutionMode`, `ExecutionEligibilityEnvelope`, and `resolve_execution_eligibility(...)`.
- Produces database columns named in the approved specification on all eight authority-transition tables.

- [ ] **Step 1: Write failing domain tests**

```python
def test_observe_only_signal_is_never_execution_eligible():
    envelope = resolve_execution_eligibility(
        declared_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
        declared_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
        execution_eligibility_enabled=False,
        evaluator_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
        evaluator_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
        authority_source_ref="event-spec:SOR-LONG-v1",
    )
    assert envelope.execution_eligible is False

def test_evaluator_cannot_upgrade_event_spec_authority():
    with pytest.raises(ValueError, match="exceeds declared event-spec authority"):
        resolve_execution_eligibility(
            declared_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
            declared_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
            execution_eligibility_enabled=False,
            evaluator_signal_grade=SignalGrade.TRIAL_GRADE_SIGNAL,
            evaluator_required_execution_mode=RequiredExecutionMode.TRIAL_LIVE,
            authority_source_ref="event-spec:SOR-LONG-v1",
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_strategy_family_signal_contract.py tests/unit/test_execution_eligibility_migration.py`

Expected: FAIL because the authority types and migration do not exist.

- [ ] **Step 3: Implement the pure domain resolver and migration**

The resolver must validate only these mappings:

```python
GRADE_TO_MODE = {
    SignalGrade.OBSERVE_ONLY_SIGNAL: RequiredExecutionMode.OBSERVE_ONLY,
    SignalGrade.TRIAL_GRADE_SIGNAL: RequiredExecutionMode.TRIAL_LIVE,
    SignalGrade.PRODUCTION_GRADE_SIGNAL: RequiredExecutionMode.PRODUCTION_LIVE,
    SignalGrade.INVALID_SIGNAL: RequiredExecutionMode.OBSERVE_ONLY,
}
```

Migration `104` adds non-null fail-closed columns, backfills every existing row to observe-only/ineligible, and adds CHECK constraints preventing eligible observe-only or invalid rows.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/unit/test_strategy_family_signal_contract.py tests/unit/test_execution_eligibility_migration.py`

Expected: PASS.

### Task 2: Watcher authority resolution and signal persistence

**Files:**
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `tests/unit/test_runtime_active_observation_monitor.py`

**Interfaces:**
- Consumes: `resolve_execution_eligibility(...)` and Event Spec declaration columns.
- Produces: live-signal rows carrying the complete authority envelope.

- [ ] **Step 1: Write failing watcher tests**

```python
def test_observe_only_would_enter_is_persisted_as_ineligible_evidence(connection):
    result = _write_live_signal_candidate(connection, candidate=observe_only_candidate(), observed_ms=NOW_MS)
    row = connection.execute(text("SELECT signal_grade, required_execution_mode, execution_eligible FROM brc_live_signal_events")).mappings().one()
    assert result["written"] is True
    assert row == {"signal_grade": "observe_only_signal", "required_execution_mode": "observe_only", "execution_eligible": False}
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/unit/test_runtime_active_observation_monitor.py -k execution_eligib`

Expected: FAIL because summaries and INSERT do not carry the envelope.

- [ ] **Step 3: Implement Event Spec lookup, resolution, and persistence**

`_live_signal_candidates_from_summaries` copies typed evaluator grade/mode. `_active_candidate_scope_event` loads declared authority. `_write_live_signal_candidate` rejects upgrades and persists all envelope fields without treating observe-only evidence as a process failure.

- [ ] **Step 4: Run and verify GREEN**

Run: `pytest -q tests/unit/test_runtime_active_observation_monitor.py -k 'live_signal or execution_eligib'`

Expected: PASS.

### Task 3: Promotion, lane, and ticket fail-closed propagation

**Files:**
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_action_time_ticket_materialization.py`

**Interfaces:**
- Consumes: persisted signal authority envelope.
- Produces: copied promotion/lane/ticket envelopes included in ticket identity.

- [ ] **Step 1: Write failing progression tests**

```python
def test_observe_only_signal_cannot_materialize_real_submit_promotion(connection):
    insert_signal(connection, signal_grade="observe_only_signal", required_execution_mode="observe_only", execution_eligible=False)
    payload = materialize_pg_promotion_action_time_lane(connection, now_ms=NOW_MS)
    assert payload["status"] == "no_execution_eligible_fresh_signal"
    assert count(connection, "brc_action_time_lane_inputs") == 0

def test_ticket_rejects_ineligible_lane(connection):
    lane_id = insert_lane(connection, execution_eligible=False)
    payload = materialize_action_time_ticket(connection, now_ms=NOW_MS)
    assert payload["status"] == "blocked"
    assert "execution_eligibility_missing_or_false" in payload["blockers"]
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_action_time_ticket_materialization.py -k execution_eligib`

Expected: FAIL because the current materializers ignore execution eligibility.

- [ ] **Step 3: Implement copied envelopes and ticket hash binding**

Only `execution_eligible=true` signals may enter `live_submit_candidate` promotion or `real_submit_candidate` lane. Ticket lineage rechecks exact grade/mode/eligibility equality and includes the three values plus `authority_source_ref` in `ticket_hash`.

- [ ] **Step 4: Run and verify GREEN**

Run: `pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_action_time_ticket_materialization.py -k 'execution_eligib or ticket_hash'`

Expected: PASS.

### Task 4: Runtime Safety and protected-submit redundant rejection

**Files:**
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `src/application/action_time/protected_submit_attempt.py`
- Modify: `tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`
- Modify: `tests/unit/test_ticket_bound_protected_submit_attempt.py`

**Interfaces:**
- Consumes: ticket, signal, lane, Runtime Safety, and submit-decision authority envelopes.
- Produces: fail-closed safety snapshot, submit-mode decision, and protected attempt.

- [ ] **Step 1: Write failing final-boundary tests**

```python
def test_runtime_safety_blocks_ineligible_ticket_graph(connection):
    ids = create_ready_graph(connection)
    connection.execute(text("UPDATE brc_action_time_tickets SET execution_eligible=false WHERE ticket_id=:id"), {"id": ids["ticket_id"]})
    payload = materialize_ticket_bound_runtime_safety_state(connection, ticket_id=ids["ticket_id"], operation_layer_handoff_id=ids["operation_layer_handoff_id"], now_ms=NOW_MS)
    assert payload["submit_allowed"] is False
    assert "execution_eligibility_missing_or_false" in payload["blockers"]
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/unit/test_ticket_bound_runtime_safety_state_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py -k execution_eligib`

Expected: FAIL because current final boundaries trust upstream readiness only.

- [ ] **Step 3: Implement independent envelope equality checks**

Runtime Safety sets `submit_allowed=true` only for an eligible, consistent graph. A real submit-mode decision and `submit_prepared`/`submitted` attempt require the same invariant; disabled-smoke remains non-writing but also records the envelope.

- [ ] **Step 4: Run and verify GREEN**

Run: `pytest -q tests/unit/test_ticket_bound_runtime_safety_state_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py -k 'execution_eligib or submit_allowed'`

Expected: PASS.

### Task 5: Projection semantics and bounded verification

**Files:**
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `tests/unit/test_strategy_live_candidate_pool.py`
- Modify: `tests/unit/test_pg_migration_identifier_names.py`

**Interfaces:**
- Consumes: current PG signal and lane authority fields.
- Produces: `action_time_boundary_not_reproduced` for observe-only signal evidence, never `waiting_for_market` or process failure.

- [ ] **Step 1: Write failing projection test**

```python
def test_observe_only_fresh_signal_reports_action_time_boundary_gap():
    row = build_candidate(signal_grade="observe_only_signal", execution_eligible=False)
    assert row["first_blocker"] == "action_time_boundary_not_reproduced"
    assert row["owner_action_required"] is False
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/unit/test_strategy_live_candidate_pool.py -k observe_only`

Expected: FAIL because observe-only evidence is currently indistinguishable from an executable fresh signal.

- [ ] **Step 3: Implement projection classification and run bounded verification**

Run:

```bash
pytest -q tests/unit/test_strategy_family_signal_contract.py tests/unit/test_execution_eligibility_migration.py tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_action_time_ticket_materialization.py tests/unit/test_ticket_bound_runtime_safety_state_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py tests/unit/test_strategy_live_candidate_pool.py
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

Expected: all selected tests pass, `performance_risk.status=clear`, and no tracked/generated output regression appears.

- [ ] **Step 4: Stop condition**

Stop P0-1 when an observe-only `would_enter` remains queryable as evidence but cannot create a promotion, real-submit lane, ticket, submit-allowed Runtime Safety snapshot, real submit-mode decision, or prepared protected-submit attempt. Do not begin P0-2 in the same batch.
