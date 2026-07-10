from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_PATH = REPO_ROOT / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
MIGRATION_PATH = REPO_ROOT / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_every_authority_transition_fail_closed():
    foundation = _load_module(FOUNDATION_PATH, "migration_086_execution_eligibility")
    migration = _load_module(MIGRATION_PATH, "migration_104_execution_eligibility")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        old_op = foundation.op
        foundation.op = operations
        try:
            foundation.upgrade()
        finally:
            foundation.op = old_op

        conn.execute(
            text(
                """
                INSERT INTO brc_strategy_side_event_specs (
                    event_spec_id, strategy_group_id, strategy_group_version_id,
                    event_id, side, timeframe, event_spec_version, status,
                    freshness_window_ms, time_authority, protection_ref_type,
                    created_at_ms, created_by
                ) VALUES (
                    'event-spec-1', 'SOR-001', 'SOR-001-v1', 'SOR-LONG', 'long',
                    '15m', 'v1', 'current', 900000,
                    'trigger_candle_close_time_ms', 'opening_range_low_reference',
                    1770000000000, 'unit-test'
                )
                """
            )
        )

        old_migration_op = migration.op
        migration.op = operations
        try:
            migration.upgrade()
        finally:
            migration.op = old_migration_op

        row = conn.execute(
            text(
                """
                SELECT declared_signal_grade,
                       declared_required_execution_mode,
                       execution_eligibility_enabled
                FROM brc_strategy_side_event_specs
                WHERE event_spec_id = 'event-spec-1'
                """
            )
        ).mappings().one()
        assert row["declared_signal_grade"] == "observe_only_signal"
        assert row["declared_required_execution_mode"] == "observe_only"
        assert row["execution_eligibility_enabled"] in {False, 0}

        inspector = sa.inspect(conn)
        for table_name in migration.AUTHORITY_TRANSITION_TABLES:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert {"signal_grade", "required_execution_mode", "execution_eligible", "authority_source_ref"} <= columns

    engine.dispose()
