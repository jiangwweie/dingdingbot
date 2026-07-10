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


REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_MIGRATIONS = [
    REPO_ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    REPO_ROOT / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py",
    REPO_ROOT / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py",
    REPO_ROOT / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py",
    REPO_ROOT / "migrations/versions/2026-07-10-106_create_runtime_supervision_and_allocation.py",
]
MIGRATION_107 = REPO_ROOT / "migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py"
MIGRATION_108 = REPO_ROOT / "migrations/versions/2026-07-10-108_certify_mpg_long_trial_event.py"


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


def test_fresh_seed_certifies_mpg_v2_with_pg_comparative_policy() -> None:
    rows = seed.build_seed_rows()
    mpg_event = next(
        row
        for row in rows["brc_strategy_side_event_specs"]
        if row["strategy_group_id"] == "MPG-001"
    )
    leader_contract = next(
        row
        for row in rows["brc_required_fact_contracts"]
        if row["strategy_group_version_id"] == "sgv:MPG-001:v2"
        and row["fact_key"] == "leader_strength_confirmed"
    )

    assert mpg_event["event_spec_id"] == "event_spec:MPG-001:MPG-LONG:v2"
    assert mpg_event["declared_signal_grade"] == "trial_grade_signal"
    assert mpg_event["declared_required_execution_mode"] == "trial_live"
    assert mpg_event["execution_eligibility_enabled"] is True
    assert leader_contract["definition_payload"]["comparative_strength"] == {
        "timeframe": "1h",
        "lookback_bars": 8,
        "max_rank": 1,
        "require_positive_return": True,
    }


def test_migration_108_preserves_mpg_v1_and_atomically_activates_v2() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original_seeds = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(BASE_MIGRATIONS, start=1):
                _upgrade(conn, path, f"migration_mpg_v2_base_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id in {"CPM-RO-001", "MPG-001"}
                else item
                for item in original_seeds
            )
            seed.seed_runtime_control_state_foundation(conn)
            _upgrade(conn, MIGRATION_107, "migration_mpg_v2_107")
            _upgrade(conn, MIGRATION_108, "migration_mpg_v2_108")

            versions = conn.execute(
                text(
                    """
                    SELECT strategy_group_version_id, status
                    FROM brc_strategy_group_versions
                    WHERE strategy_group_id='MPG-001'
                    ORDER BY version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in versions] == [
                {"strategy_group_version_id": "sgv:MPG-001:v1", "status": "superseded"},
                {"strategy_group_version_id": "sgv:MPG-001:v2", "status": "current"},
            ]

            events = conn.execute(
                text(
                    """
                    SELECT event_spec_id, status, declared_signal_grade,
                           declared_required_execution_mode,
                           execution_eligibility_enabled
                    FROM brc_strategy_side_event_specs
                    WHERE strategy_group_id='MPG-001'
                    ORDER BY event_spec_version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in events] == [
                {
                    "event_spec_id": "event_spec:MPG-001:MPG-LONG:v1",
                    "status": "retired",
                    "declared_signal_grade": "observe_only_signal",
                    "declared_required_execution_mode": "observe_only",
                    "execution_eligibility_enabled": False,
                },
                {
                    "event_spec_id": "event_spec:MPG-001:MPG-LONG:v2",
                    "status": "current",
                    "declared_signal_grade": "trial_grade_signal",
                    "declared_required_execution_mode": "trial_live",
                    "execution_eligibility_enabled": True,
                },
            ]

            active_bindings = conn.execute(
                text(
                    """
                    SELECT event_spec_id, COUNT(*) AS binding_count
                    FROM brc_candidate_scope_event_bindings
                    WHERE strategy_group_id='MPG-001' AND status='active'
                    GROUP BY event_spec_id
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in active_bindings] == [
                {
                    "event_spec_id": "event_spec:MPG-001:MPG-LONG:v2",
                    "binding_count": 4,
                }
            ]

            leader_payload = conn.execute(
                text(
                    """
                    SELECT definition_payload
                    FROM brc_required_fact_contracts
                    WHERE strategy_group_version_id='sgv:MPG-001:v2'
                      AND fact_key='leader_strength_confirmed'
                    """
                )
            ).scalar_one()
            if isinstance(leader_payload, str):
                leader_payload = json.loads(leader_payload)
            assert leader_payload["comparative_strength"] == {
                "timeframe": "1h",
                "lookback_bars": 8,
                "max_rank": 1,
                "require_positive_return": True,
            }
    finally:
        seed.ACTIVE_EVENT_SEEDS = original_seeds
        engine.dispose()
