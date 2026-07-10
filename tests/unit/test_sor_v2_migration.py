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
]
M110 = ROOT / "migrations/versions/2026-07-10-110_certify_sor_dual_side_trial_events.py"


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


def test_fresh_seed_certifies_both_sor_v2_events() -> None:
    events = [
        row for row in seed.build_seed_rows()["brc_strategy_side_event_specs"]
        if row["strategy_group_id"] == "SOR-001"
    ]

    assert {
        (
            row["event_spec_id"],
            row["declared_signal_grade"],
            row["declared_required_execution_mode"],
            row["execution_eligibility_enabled"],
        )
        for row in events
    } == {
        ("event_spec:SOR-001:SOR-LONG:v2", "trial_grade_signal", "trial_live", True),
        ("event_spec:SOR-001:SOR-SHORT:v2", "trial_grade_signal", "trial_live", True),
    }


def test_migration_110_atomically_switches_eight_sor_bindings() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(BASE[:5]):
                _upgrade(conn, path, f"sor_base_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id in {"CPM-RO-001", "MPG-001", "MI-001", "SOR-001"}
                else item
                for item in original
            )
            seed.seed_runtime_control_state_foundation(conn)
            for index, path in enumerate(BASE[5:], start=107):
                _upgrade(conn, path, f"sor_{index}")
            _upgrade(conn, M110, "sor_110")

            events = conn.execute(
                text(
                    """
                    SELECT event_spec_id, status, execution_eligibility_enabled
                    FROM brc_strategy_side_event_specs
                    WHERE strategy_group_id='SOR-001'
                    ORDER BY event_spec_id
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in events] == [
                {"event_spec_id": "event_spec:SOR-001:SOR-LONG:v1", "status": "retired", "execution_eligibility_enabled": False},
                {"event_spec_id": "event_spec:SOR-001:SOR-LONG:v2", "status": "current", "execution_eligibility_enabled": True},
                {"event_spec_id": "event_spec:SOR-001:SOR-SHORT:v1", "status": "retired", "execution_eligibility_enabled": False},
                {"event_spec_id": "event_spec:SOR-001:SOR-SHORT:v2", "status": "current", "execution_eligibility_enabled": True},
            ]
            active = conn.execute(
                text(
                    """
                    SELECT event_spec_id, COUNT(*) AS binding_count
                    FROM brc_candidate_scope_event_bindings
                    WHERE strategy_group_id='SOR-001' AND status='active'
                    GROUP BY event_spec_id ORDER BY event_spec_id
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in active] == [
                {"event_spec_id": "event_spec:SOR-001:SOR-LONG:v2", "binding_count": 4},
                {"event_spec_id": "event_spec:SOR-001:SOR-SHORT:v2", "binding_count": 4},
            ]
    finally:
        seed.ACTIVE_EVENT_SEEDS = original
        engine.dispose()
