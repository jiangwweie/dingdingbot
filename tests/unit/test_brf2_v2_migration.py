from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import seed_runtime_control_state_foundation as seed


ROOT = Path(__file__).resolve().parents[2]
BASE = [
    ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    ROOT / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py",
    ROOT / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py",
    ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py",
    ROOT / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py",
    ROOT / "migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py",
    ROOT / "migrations/versions/2026-07-10-108_certify_mpg_long_trial_event.py",
    ROOT / "migrations/versions/2026-07-10-109_certify_mi_long_trial_event.py",
    ROOT / "migrations/versions/2026-07-10-110_certify_sor_dual_side_trial_events.py",
]
M111 = ROOT / "migrations/versions/2026-07-10-111_certify_brf2_short_trial_event.py"
M112 = ROOT / "migrations/versions/2026-07-10-112_version_live_signal_identity.py"


def _upgrade(conn, path: Path, name: str) -> None:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old_op


def test_fresh_seed_certifies_brf2_short_v2() -> None:
    event = next(
        row for row in seed.build_seed_rows()["brc_strategy_side_event_specs"]
        if row["strategy_group_id"] == "BRF2-001"
    )

    assert event["event_spec_id"] == "event_spec:BRF2-001:BRF2-SHORT:v2"
    assert event["declared_signal_grade"] == "trial_grade_signal"
    assert event["declared_required_execution_mode"] == "trial_live"
    assert event["execution_eligibility_enabled"] is True


def test_migration_111_switches_three_brf2_bindings_and_preserves_disable_fact() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(BASE[:5]):
                _upgrade(conn, path, f"brf2_base_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id in {"CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001"}
                else item
                for item in original
            )
            seed.seed_runtime_control_state_foundation(conn)
            for index, path in enumerate(BASE[5:], start=107):
                _upgrade(conn, path, f"brf2_{index}")
            _upgrade(conn, M111, "brf2_111")
            seed.ACTIVE_EVENT_SEEDS = original
            seed.seed_runtime_control_state_foundation(conn)

            disable_contract_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM brc_required_fact_contracts
                    WHERE strategy_group_version_id='sgv:BRF2-001:v2'
                      AND fact_key='strong_uptrend_disable'
                      AND required_surface='finalgate'
                    """
                )
            ).scalar_one()
            assert disable_contract_count == 1

            events = conn.execute(
                text(
                    """
                    SELECT event_spec_id, status, execution_eligibility_enabled
                    FROM brc_strategy_side_event_specs
                    WHERE strategy_group_id='BRF2-001'
                    ORDER BY event_spec_version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in events] == [
                {"event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v1", "status": "retired", "execution_eligibility_enabled": False},
                {"event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v2", "status": "current", "execution_eligibility_enabled": True},
            ]
            binding = conn.execute(
                text(
                    """
                    SELECT event_spec_id, COUNT(*) AS binding_count
                    FROM brc_candidate_scope_event_bindings
                    WHERE strategy_group_id='BRF2-001' AND status='active'
                    GROUP BY event_spec_id
                    """
                )
            ).mappings().one()
            assert dict(binding) == {
                "event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v2",
                "binding_count": 3,
            }
            disable = conn.execute(
                text(
                    """
                    SELECT fact_key, fact_role, operator, expected_value, disable_on_match
                    FROM brc_strategy_event_required_facts
                    WHERE event_spec_id='event_spec:BRF2-001:BRF2-SHORT:v2'
                      AND fact_key='strong_uptrend_disable'
                    """
                )
            ).mappings().one()
            disable = dict(disable)
            if isinstance(disable["expected_value"], str):
                disable["expected_value"] = json.loads(disable["expected_value"])
            assert disable == {
                "fact_key": "strong_uptrend_disable",
                "fact_role": "disable",
                "operator": "eq",
                "expected_value": True,
                "disable_on_match": True,
            }
    finally:
        seed.ACTIVE_EVENT_SEEDS = original
        engine.dispose()


def test_migration_112_supersedes_old_event_signal_and_versions_identity() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(BASE[:5]):
                _upgrade(conn, path, f"signal_identity_base_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id in {"CPM-RO-001", "MPG-001", "MI-001", "SOR-001", "BRF2-001"}
                else item
                for item in original
            )
            seed.seed_runtime_control_state_foundation(conn)
            conn.execute(
                text(
                    """
                    INSERT INTO brc_live_signal_events (
                      signal_event_id, candidate_scope_id, event_spec_id,
                      strategy_group_id, symbol, side, detector_key, signal_type,
                      source_kind, status, freshness_state, confidence,
                      fact_snapshot_id, reason_codes, signal_payload,
                      event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
                      expires_at_ms, invalidated_at_ms, created_at_ms,
                      signal_grade, required_execution_mode, execution_eligible,
                      authority_source_ref
                    ) VALUES (
                      'signal:brf2-v1',
                      'candidate_scope:BRF2-001:ETHUSDT:short:BRF2-SHORT',
                      'event_spec:BRF2-001:BRF2-SHORT:v1',
                      'BRF2-001', 'ETHUSDT', 'short',
                      'runtime_active_observation_monitor', 'BRF2-SHORT',
                      'live_market', 'facts_validated', 'fresh', 0.9,
                      NULL, '[]', '{}', 1783691000000, 1783691000000,
                      1783691600000, 1783692200000, NULL, 1783691600000,
                      'observe_only_signal', 'observe_only', 0,
                      'event-spec:event_spec:BRF2-001:BRF2-SHORT:v1'
                    )
                    """
                )
            )
            for index, path in enumerate(BASE[5:], start=107):
                _upgrade(conn, path, f"signal_identity_{index}")
            _upgrade(conn, M111, "signal_identity_111")
            _upgrade(conn, M112, "signal_identity_112")

            retired = conn.execute(
                text(
                    """
                    SELECT status, freshness_state, invalidated_at_ms, expires_at_ms
                    FROM brc_live_signal_events
                    WHERE signal_event_id='signal:brf2-v1'
                    """
                )
            ).mappings().one()
            assert dict(retired) == {
                "status": "superseded",
                "freshness_state": "expired",
                "invalidated_at_ms": 1783691700000,
                "expires_at_ms": 1783691700000,
            }

            conn.execute(
                text(
                    """
                    INSERT INTO brc_live_signal_events (
                      signal_event_id, candidate_scope_id, event_spec_id,
                      strategy_group_id, symbol, side, detector_key, signal_type,
                      source_kind, status, freshness_state, confidence,
                      fact_snapshot_id, reason_codes, signal_payload,
                      event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
                      expires_at_ms, invalidated_at_ms, created_at_ms,
                      signal_grade, required_execution_mode, execution_eligible,
                      authority_source_ref
                    ) VALUES (
                      'signal:brf2-v2',
                      'candidate_scope:BRF2-001:ETHUSDT:short:BRF2-SHORT',
                      'event_spec:BRF2-001:BRF2-SHORT:v2',
                      'BRF2-001', 'ETHUSDT', 'short',
                      'runtime_active_observation_monitor', 'BRF2-SHORT',
                      'live_market', 'facts_validated', 'fresh', 0.9,
                      NULL, '[]', '{}', 1783691000000, 1783691000000,
                      1783691800000, 1783692200000, NULL, 1783691800000,
                      'trial_grade_signal', 'trial_live', 1,
                      'event-spec:event_spec:BRF2-001:BRF2-SHORT:v2'
                    )
                    """
                )
            )
            assert conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM brc_live_signal_events
                    WHERE strategy_group_id='BRF2-001'
                      AND symbol='ETHUSDT'
                      AND side='short'
                      AND event_time_ms=1783691000000
                    """
                )
            ).scalar_one() == 2
    finally:
        seed.ACTIVE_EVENT_SEEDS = original
        engine.dispose()
