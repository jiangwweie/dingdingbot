from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_process_outcome import (
    classify_process_outcome,
    materialize_runtime_process_outcome,
    runtime_process_exit_code,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity


def test_action_time_stage_timeout_is_retryable_engineering_failure():
    outcome = classify_process_outcome(
        process_name="action_time_refresh_sequence",
        result_status="action_time_refresh_sequence_failed",
        blockers=["materialize_action_time_finalgate_preflight_timeout"],
    )

    assert outcome.process_state == "retryable_failure"
    assert outcome.business_state == "temporarily_unavailable"
    assert outcome.first_blocker == (
        "materialize_action_time_finalgate_preflight_timeout"
    )
from scripts.validate_current_projection_ownership import (
    _validate_runtime_process_outcomes,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION = REPO_ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
MIGRATION_104 = REPO_ROOT / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py"
MIGRATION_105 = REPO_ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py"
MIGRATION_106 = REPO_ROOT / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py"
MIGRATION_118 = REPO_ROOT / "migrations/versions/2026-07-13-118_conserve_runtime_lane_identity.py"


def test_valid_no_fresh_signal_is_business_noop_not_process_failure():
    outcome = classify_process_outcome(
        process_name="promotion_action_time_lane",
        result_status="no_fresh_signal",
        blockers=[],
    )

    assert outcome.process_state == "noop"
    assert outcome.business_state == "waiting_for_opportunity"
    assert outcome.first_blocker == ""


def test_runtime_dependency_error_is_retryable_process_failure():
    outcome = classify_process_outcome(
        process_name="promotion_action_time_lane",
        result_status="blocked",
        blockers=["runtime_control_state_invalid:connection_lost"],
    )

    assert outcome.process_state == "retryable_failure"
    assert outcome.business_state == "temporarily_unavailable"


def test_action_time_fact_business_block_is_temporarily_unavailable_not_intervention():
    outcome = classify_process_outcome(
        process_name="action_time_fact_snapshots",
        result_status="action_time_fact_snapshots_blocked",
        blockers=["required_fact_not_satisfied:leader_strength_confirmed"],
    )

    assert outcome.process_state == "business_blocked"
    assert outcome.business_state == "temporarily_unavailable"
    assert outcome.first_blocker == (
        "required_fact_not_satisfied:leader_strength_confirmed"
    )


def test_outer_action_time_business_block_preserves_safe_stop_semantics():
    outcome = classify_process_outcome(
        process_name="action_time_refresh_sequence",
        result_status="action_time_refresh_sequence_business_blocked",
        blockers=["runtime_lane_identity_mismatch:child_stage"],
    )

    assert outcome.process_state == "business_blocked"
    assert outcome.business_state == "temporarily_unavailable"
    assert outcome.first_blocker == "runtime_lane_identity_mismatch:child_stage"


def test_runtime_process_exit_code_treats_completed_process_states_as_success():
    for process_state in ("succeeded", "noop", "business_blocked"):
        assert runtime_process_exit_code({"process_state": process_state}) == 0


def test_runtime_process_exit_code_treats_process_failures_as_failure():
    for process_state in ("retryable_failure", "hard_failure"):
        assert runtime_process_exit_code({"process_state": process_state}) == 1


def test_runtime_process_exit_code_rejects_unknown_process_state():
    with pytest.raises(ValueError, match="unsupported runtime process state"):
        runtime_process_exit_code({"process_state": "unknown"})


def test_process_outcome_materializes_one_current_row_per_scope():
    modules = [
        _load(FOUNDATION, "migration_086_process_projection"),
        _load(MIGRATION_104, "migration_104_process_projection"),
        _load(MIGRATION_105, "migration_105_process_projection"),
        _load(MIGRATION_106, "migration_106_process_projection"),
    ]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        for module in modules:
            old_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = old_op
        materialize_runtime_process_outcome(
            conn,
            process_name="promotion_action_time_lane_batch",
            scope_key="global",
            run_id="run-1",
            result_status="no_fresh_signal",
            blockers=[],
            started_at_ms=100,
            completed_at_ms=120,
            runtime_head="head-1",
            source_watermark="signals:0",
        )
        materialize_runtime_process_outcome(
            conn,
            process_name="promotion_action_time_lane_batch",
            scope_key="global",
            run_id="run-2",
            result_status="promotion_action_time_lane_created",
            blockers=[],
            started_at_ms=200,
            completed_at_ms=230,
            runtime_head="head-1",
            source_watermark="signals:1",
        )
        rows = list(
            conn.execute(sa.text("SELECT * FROM brc_runtime_process_outcomes"))
            .mappings()
        )
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-2"
        assert rows[0]["process_state"] == "succeeded"
        assert _validate_runtime_process_outcomes(conn) == []
        conn.execute(
            sa.text(
                "UPDATE brc_runtime_process_outcomes "
                "SET projector_owner = 'wrong_projector'"
            )
        )
        assert _validate_runtime_process_outcomes(conn) == [
            "runtime process projector mismatch: promotion_action_time_lane_batch:global"
        ]
    engine.dispose()


def test_current_runtime_lane_process_rejects_legacy_unscoped_outcome():
    modules = [
        _load(FOUNDATION, "migration_086_reject_unscoped"),
        _load(MIGRATION_104, "migration_104_reject_unscoped"),
        _load(MIGRATION_105, "migration_105_reject_unscoped"),
        _load(MIGRATION_106, "migration_106_reject_unscoped"),
        _load(MIGRATION_118, "migration_118_reject_unscoped"),
    ]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        for module in modules:
            old_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = old_op

        for process_name in (
            "live_signal_materialization",
            "action_time_fact_snapshots",
            "promotion_action_time_lane",
            "action_time_ticket_sequence",
            "action_time_capability_certification",
        ):
            with pytest.raises(
                ValueError,
                match=f"runtime_lane_identity_required:{process_name}",
            ):
                materialize_runtime_process_outcome(
                    conn,
                    process_name=process_name,
                    scope_key="global",
                    run_id="unscoped-run",
                    result_status="no_fresh_signal",
                    blockers=[],
                    started_at_ms=100,
                    completed_at_ms=120,
                    runtime_head="head-1",
                    source_watermark="signals:0",
                )
    engine.dispose()


def test_migration_106_creates_supervision_semantics_and_allocation_tables():
    modules = [
        _load(FOUNDATION, "migration_086_p0_3"),
        _load(MIGRATION_104, "migration_104_p0_3"),
        _load(MIGRATION_105, "migration_105_p0_3"),
        _load(MIGRATION_106, "migration_106_p0_3"),
    ]
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        for module in modules:
            old_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = old_op

        inspector = sa.inspect(conn)
        assert {
            "brc_runtime_process_outcomes",
            "brc_strategy_semantic_admissions",
            "brc_allocation_decisions",
        } <= set(inspector.get_table_names())
        promotion_columns = {
            column["name"]
            for column in inspector.get_columns("brc_promotion_candidates")
        }
        assert {
            "allocation_decision_id",
            "allocation_rank",
            "requested_risk_at_stop",
            "allocated_risk_at_stop",
            "allocation_state",
        } <= promotion_columns
    engine.dispose()


def test_runtime_lane_process_outcome_uses_typed_identity_and_source_watermark():
    modules = [
        _load(FOUNDATION, "migration_086_lane_outcome"),
        _load(MIGRATION_104, "migration_104_lane_outcome"),
        _load(MIGRATION_105, "migration_105_lane_outcome"),
        _load(MIGRATION_106, "migration_106_lane_outcome"),
        _load(MIGRATION_118, "migration_118_lane_outcome"),
    ]
    identity = RuntimeLaneIdentity(
        candidate_scope_id="scope:CPM-RO-001:SOLUSDT:long",
        candidate_scope_event_binding_id="binding:CPM-RO-001:SOLUSDT:long:CPM-LONG",
        runtime_scope_binding_id="runtime_scope:CPM-RO-001:SOLUSDT:long",
        runtime_instance_id="runtime-cpm-sol-long",
        runtime_profile_id="runtime-profile:pilot",
        policy_current_id="policy:CPM-RO-001:SOLUSDT:long",
        strategy_group_id="CPM-RO-001",
        strategy_group_version_id="sgv:CPM-RO-001:v2",
        symbol="SOLUSDT",
        asset_class="crypto_perpetual",
        side="long",
        event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v2",
        event_spec_version="v2",
        event_id="CPM-LONG",
        timeframe="1h",
        time_authority="trigger_candle_close_time_ms",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        for module in modules:
            old_op = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = old_op

        first = materialize_runtime_process_outcome(
            conn,
            process_name="live_signal_materialization",
            scope_key=None,
            lane_identity=identity,
            run_id="lane-run-1",
            result_status="live_signal_materialization_completed",
            blockers=[],
            started_at_ms=100,
            completed_at_ms=120,
            runtime_head="head-1",
            source_watermark="runtime-cpm-sol-long:100",
        )
        duplicate = materialize_runtime_process_outcome(
            conn,
            process_name="live_signal_materialization",
            scope_key=None,
            lane_identity=identity,
            run_id="lane-run-2",
            result_status="live_signal_materialization_completed",
            blockers=[],
            started_at_ms=200,
            completed_at_ms=220,
            runtime_head="head-1",
            source_watermark="runtime-cpm-sol-long:100",
        )
        second_watermark = materialize_runtime_process_outcome(
            conn,
            process_name="live_signal_materialization",
            scope_key=None,
            lane_identity=identity,
            run_id="lane-run-3",
            result_status="live_signal_materialization_completed",
            blockers=[],
            started_at_ms=300,
            completed_at_ms=320,
            runtime_head="head-1",
            source_watermark="runtime-cpm-sol-long:200",
        )

        assert first["process_outcome_id"] == duplicate["process_outcome_id"]
        assert first["process_outcome_id"] != second_watermark["process_outcome_id"]
        rows = list(
            conn.execute(
                sa.text(
                    """
                    SELECT scope_kind, candidate_scope_id,
                           candidate_scope_event_binding_id, runtime_scope_binding_id,
                           runtime_instance_id, strategy_group_version_id,
                           event_spec_version, event_id, timeframe, lane_identity_key,
                           source_watermark, run_id
                    FROM brc_runtime_process_outcomes
                    ORDER BY source_watermark
                    """
                )
            ).mappings()
        )
        assert len(rows) == 2
        assert dict(rows[0]) == {
            "scope_kind": "runtime_lane",
            "candidate_scope_id": identity.candidate_scope_id,
            "candidate_scope_event_binding_id": identity.candidate_scope_event_binding_id,
            "runtime_scope_binding_id": identity.runtime_scope_binding_id,
            "runtime_instance_id": identity.runtime_instance_id,
            "strategy_group_version_id": identity.strategy_group_version_id,
            "event_spec_version": identity.event_spec_version,
            "event_id": identity.event_id,
            "timeframe": identity.timeframe,
            "lane_identity_key": identity.identity_key,
            "source_watermark": "runtime-cpm-sol-long:100",
            "run_id": "lane-run-2",
        }
    engine.dispose()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
