from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import seed_runtime_control_state_foundation as seed


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = [
    REPO_ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    REPO_ROOT / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py",
    REPO_ROOT / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py",
    REPO_ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py",
    REPO_ROOT / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py",
]
MIGRATION_107 = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _upgrade(conn, path: Path, name: str) -> None:
    module = _load_module(path, name)
    old_op = module.op
    module.op = Operations(MigrationContext.configure(conn))
    try:
        module.upgrade()
    finally:
        module.op = old_op


def test_fresh_seed_certifies_only_cpm_long_v2() -> None:
    rows = seed.build_seed_rows()
    events = rows["brc_strategy_side_event_specs"]
    eligible = [
        row
        for row in events
        if row["execution_eligibility_enabled"] is True
    ]

    assert [
        (
            row["strategy_group_id"],
            row["event_id"],
            row["event_spec_version"],
            row["declared_signal_grade"],
            row["declared_required_execution_mode"],
        )
        for row in eligible
    ] == [
        (
            "CPM-RO-001",
            "CPM-LONG",
            "v2",
            "trial_grade_signal",
            "trial_live",
        )
    ]
    cpm_group = next(
        row
        for row in rows["brc_strategy_groups"]
        if row["strategy_group_id"] == "CPM-RO-001"
    )
    assert cpm_group["current_version_id"] == "sgv:CPM-RO-001:v2"


def test_non_cpm_event_specs_remain_observe_only() -> None:
    rows = seed.build_seed_rows()
    non_cpm = [
        row
        for row in rows["brc_strategy_side_event_specs"]
        if row["strategy_group_id"] != "CPM-RO-001"
    ]

    assert len(non_cpm) == 5
    assert {
        (
            row["event_spec_version"],
            row["declared_signal_grade"],
            row["declared_required_execution_mode"],
            row["execution_eligibility_enabled"],
        )
        for row in non_cpm
    } == {("v1", "observe_only_signal", "observe_only", False)}


def test_migration_107_preserves_cpm_v1_and_activates_v2() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_seeds = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(MIGRATIONS, start=1):
                _upgrade(conn, path, f"migration_cpm_v2_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id == "CPM-RO-001"
                else item
                for item in original_seeds
            )
            seed.seed_runtime_control_state_foundation(conn)

            _upgrade(conn, MIGRATION_107, "migration_cpm_v2_107")

            versions = conn.execute(
                text(
                    """
                    SELECT strategy_group_version_id, status
                    FROM brc_strategy_group_versions
                    WHERE strategy_group_id='CPM-RO-001'
                    ORDER BY version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in versions] == [
                {"strategy_group_version_id": "sgv:CPM-RO-001:v1", "status": "superseded"},
                {"strategy_group_version_id": "sgv:CPM-RO-001:v2", "status": "current"},
            ]
            events = conn.execute(
                text(
                    """
                    SELECT event_spec_id, status, declared_signal_grade,
                           declared_required_execution_mode,
                           execution_eligibility_enabled
                    FROM brc_strategy_side_event_specs
                    WHERE strategy_group_id='CPM-RO-001'
                    ORDER BY event_spec_version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in events] == [
                {
                    "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v1",
                    "status": "retired",
                    "declared_signal_grade": "observe_only_signal",
                    "declared_required_execution_mode": "observe_only",
                    "execution_eligibility_enabled": False,
                },
                {
                    "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
                    "status": "current",
                    "declared_signal_grade": "trial_grade_signal",
                    "declared_required_execution_mode": "trial_live",
                    "execution_eligibility_enabled": True,
                },
            ]
            binding_targets = conn.execute(
                text(
                    """
                    SELECT DISTINCT event_spec_id
                    FROM brc_candidate_scope_event_bindings
                    WHERE strategy_group_id='CPM-RO-001' AND status='active'
                    """
                )
            ).scalars().all()
            assert binding_targets == ["event_spec:CPM-RO-001:CPM-LONG:v2"]
    finally:
        seed.ACTIVE_EVENT_SEEDS = original_seeds
        engine.dispose()
