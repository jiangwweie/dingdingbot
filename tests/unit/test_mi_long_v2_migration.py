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
]
M107 = ROOT / "migrations/versions/2026-07-10-107_certify_cpm_long_trial_event.py"
M108 = ROOT / "migrations/versions/2026-07-10-108_certify_mpg_long_trial_event.py"
M109 = ROOT / "migrations/versions/2026-07-10-109_certify_mi_long_trial_event.py"


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


def test_fresh_seed_certifies_mi_v2_with_pg_comparative_policy() -> None:
    rows = seed.build_seed_rows()
    event = next(
        row for row in rows["brc_strategy_side_event_specs"]
        if row["strategy_group_id"] == "MI-001"
    )
    contract = next(
        row for row in rows["brc_required_fact_contracts"]
        if row["strategy_group_version_id"] == "sgv:MI-001:v2"
        and row["fact_key"] == "relative_strength_confirmed"
    )

    assert event["event_spec_id"] == "event_spec:MI-001:MI-LONG:v2"
    assert event["declared_signal_grade"] == "trial_grade_signal"
    assert event["declared_required_execution_mode"] == "trial_live"
    assert event["execution_eligibility_enabled"] is True
    assert contract["definition_payload"]["comparative_strength"] == {
        "timeframe": "1h",
        "lookback_bars": 12,
        "max_rank": 1,
        "require_positive_return": True,
    }


def test_migration_109_preserves_mi_v1_and_switches_three_bindings() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = seed.ACTIVE_EVENT_SEEDS
    try:
        with engine.begin() as conn:
            for index, path in enumerate(BASE):
                _upgrade(conn, path, f"mi_base_{index}")
            seed.ACTIVE_EVENT_SEEDS = tuple(
                replace(
                    item,
                    strategy_group_version=1,
                    event_spec_version="v1",
                    declared_signal_grade="observe_only_signal",
                    declared_required_execution_mode="observe_only",
                    execution_eligibility_enabled=False,
                )
                if item.strategy_group_id in {"CPM-RO-001", "MPG-001", "MI-001"}
                else item
                for item in original
            )
            seed.seed_runtime_control_state_foundation(conn)
            _upgrade(conn, M107, "mi_107")
            _upgrade(conn, M108, "mi_108")
            _upgrade(conn, M109, "mi_109")

            events = conn.execute(
                text(
                    """
                    SELECT event_spec_id, status, declared_signal_grade,
                           declared_required_execution_mode,
                           execution_eligibility_enabled
                    FROM brc_strategy_side_event_specs
                    WHERE strategy_group_id='MI-001'
                    ORDER BY event_spec_version
                    """
                )
            ).mappings().all()
            assert [dict(row) for row in events] == [
                {
                    "event_spec_id": "event_spec:MI-001:MI-LONG:v1",
                    "status": "retired",
                    "declared_signal_grade": "observe_only_signal",
                    "declared_required_execution_mode": "observe_only",
                    "execution_eligibility_enabled": False,
                },
                {
                    "event_spec_id": "event_spec:MI-001:MI-LONG:v2",
                    "status": "current",
                    "declared_signal_grade": "trial_grade_signal",
                    "declared_required_execution_mode": "trial_live",
                    "execution_eligibility_enabled": True,
                },
            ]
            binding = conn.execute(
                text(
                    """
                    SELECT event_spec_id, COUNT(*) AS binding_count
                    FROM brc_candidate_scope_event_bindings
                    WHERE strategy_group_id='MI-001' AND status='active'
                    GROUP BY event_spec_id
                    """
                )
            ).mappings().one()
            assert dict(binding) == {
                "event_spec_id": "event_spec:MI-001:MI-LONG:v2",
                "binding_count": 3,
            }
            payload = conn.execute(
                text(
                    """
                    SELECT definition_payload FROM brc_required_fact_contracts
                    WHERE strategy_group_version_id='sgv:MI-001:v2'
                      AND fact_key='relative_strength_confirmed'
                    """
                )
            ).scalar_one()
            if isinstance(payload, str):
                payload = json.loads(payload)
            assert payload["comparative_strength"]["lookback_bars"] == 12
    finally:
        seed.ACTIVE_EVENT_SEEDS = original
        engine.dispose()
