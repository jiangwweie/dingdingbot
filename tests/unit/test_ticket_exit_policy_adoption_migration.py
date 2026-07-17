from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-16-125_add_active_ticket_exit_policy_adoption.py"
)
MIGRATION_135_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-17-135_repair_exit_policy_adoption_effective_uniqueness.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_125_active_ticket_exit_policy_adoption", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration_135():
    spec = importlib.util.spec_from_file_location(
        "migration_135_exit_policy_adoption_effective_uniqueness",
        MIGRATION_135_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_schema(engine) -> None:
    metadata = sa.MetaData()
    sa.Table(
        "brc_ticket_exit_policy_current",
        metadata,
        sa.Column("ticket_id", sa.String(192), primary_key=True),
        sa.Column("exit_policy_id", sa.String(192), nullable=False),
        sa.Column("exit_policy_version", sa.String(96), nullable=False),
        sa.Column("exit_policy_hash", sa.String(64), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
    )
    metadata.create_all(engine)


def _event(**overrides):
    values = {
        "adoption_event_id": "adoption:one",
        "ticket_id": "ticket:one",
        "from_exit_policy_hash": "a" * 64,
        "to_exit_policy_id": "policy:one",
        "to_exit_policy_version": "v1",
        "to_exit_policy_hash": "b" * 64,
        "owner_authorization_ref": "owner:approved",
        "eligibility_snapshot": {"schema": "eligibility.v1"},
        "eligibility_hash": "c" * 64,
        "decision": "accepted",
        "runtime_head": "d" * 40,
        "supersedes_adoption_event_id": None,
        "created_at_ms": 1,
    }
    values.update(overrides)
    return values


def test_migration_125_adds_append_only_adoption_authority_and_projection_fields():
    migration = _load_migration()
    assert migration.revision == "125"
    assert migration.down_revision == "124"

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    _base_schema(engine)
    with engine.begin() as conn:
        current = sa.Table(
            "brc_ticket_exit_policy_current", sa.MetaData(), autoload_with=conn
        )
        conn.execute(
            current.insert().values(
                ticket_id="ticket:existing",
                exit_policy_id="policy:existing",
                exit_policy_version="v1",
                exit_policy_hash="e" * 64,
                updated_at_ms=1,
            )
        )
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = previous_op

        inspector = sa.inspect(conn)
        event_columns = {
            item["name"]
            for item in inspector.get_columns(
                "brc_ticket_exit_policy_adoption_events"
            )
        }
        projection_columns = {
            item["name"]
            for item in inspector.get_columns("brc_ticket_exit_policy_current")
        }
        assert {
            "adoption_event_id",
            "ticket_id",
            "from_exit_policy_hash",
            "to_exit_policy_id",
            "to_exit_policy_version",
            "to_exit_policy_hash",
            "owner_authorization_ref",
            "eligibility_snapshot",
            "eligibility_hash",
            "decision",
            "runtime_head",
            "supersedes_adoption_event_id",
            "created_at_ms",
        } <= event_columns
        assert {"binding_source", "adoption_event_id"} <= projection_columns

        current = sa.Table(
            "brc_ticket_exit_policy_current", sa.MetaData(), autoload_with=conn
        )
        existing = conn.execute(
            sa.select(current).where(current.c.ticket_id == "ticket:existing")
        ).mappings().one()
        assert existing["binding_source"] == "ticket"
        assert existing["adoption_event_id"] is None

        events = sa.Table(
            "brc_ticket_exit_policy_adoption_events",
            sa.MetaData(),
            autoload_with=conn,
        )
        conn.execute(events.insert().values(**_event()))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                events.insert().values(
                    **_event(
                        adoption_event_id="adoption:two",
                        eligibility_hash="f" * 64,
                    )
                )
            )


def test_migration_125_rejects_invalid_decision_shape_and_downgrades():
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    _base_schema(engine)
    with engine.begin() as conn:
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
            events = sa.Table(
                "brc_ticket_exit_policy_adoption_events",
                sa.MetaData(),
                autoload_with=conn,
            )
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    events.insert().values(
                        **_event(
                            decision="revoked",
                            supersedes_adoption_event_id=None,
                        )
                    )
                )
            migration.downgrade()
        finally:
            migration.op = previous_op

        inspector = sa.inspect(conn)
        assert not inspector.has_table("brc_ticket_exit_policy_adoption_events")
        projection_columns = {
            item["name"]
            for item in inspector.get_columns("brc_ticket_exit_policy_current")
        }
        assert "binding_source" not in projection_columns
        assert "adoption_event_id" not in projection_columns


def test_migration_125_extends_command_source_and_blocks_unsafe_downgrade():
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    _base_schema(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE brc_ticket_bound_exchange_commands ("
            "exchange_command_id VARCHAR(192) PRIMARY KEY, "
            "command_source VARCHAR(64) NOT NULL, "
            "CONSTRAINT ck_brc_exchange_command_source CHECK ("
            "command_source IN ('protected_submit','protection_recovery',"
            "'runner_mutation','orphan_cleanup','exit_policy_runner',"
            "'exit_policy_close')))"
        )
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
            conn.execute(
                sa.text(
                    "INSERT INTO brc_ticket_bound_exchange_commands VALUES "
                    "('reprice-1','exit_policy_tp1_reprice')"
                )
            )
            with pytest.raises(RuntimeError, match="cannot_downgrade"):
                migration.downgrade()
            conn.execute(
                sa.text(
                    "DELETE FROM brc_ticket_bound_exchange_commands "
                    "WHERE exchange_command_id='reprice-1'"
                )
            )
            migration.downgrade()
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_exchange_commands VALUES "
                        "('reprice-2','exit_policy_tp1_reprice')"
                    )
                )
        finally:
            migration.op = previous_op


def test_migration_135_replaces_lifetime_acceptance_with_current_adoption_state():
    migration_125 = _load_migration()
    migration_135 = _load_migration_135()
    assert migration_135.revision == "135"
    assert migration_135.down_revision == "134"

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    _base_schema(engine)
    with engine.begin() as conn:
        context = Operations(MigrationContext.configure(conn))
        previous_125 = migration_125.op
        previous_135 = migration_135.op
        migration_125.op = context
        migration_135.op = context
        try:
            migration_125.upgrade()
            events = sa.Table(
                "brc_ticket_exit_policy_adoption_events", sa.MetaData(), autoload_with=conn
            )
            current = sa.Table(
                "brc_ticket_exit_policy_current", sa.MetaData(), autoload_with=conn
            )
            conn.execute(events.insert().values(**_event()))
            conn.execute(
                current.insert().values(
                    ticket_id="ticket:one",
                    exit_policy_id="policy:one",
                    exit_policy_version="v1",
                    exit_policy_hash="b" * 64,
                    updated_at_ms=1,
                    binding_source="adoption_event",
                    adoption_event_id="adoption:one",
                )
            )

            migration_135.upgrade()
            current = sa.Table(
                "brc_ticket_exit_policy_current", sa.MetaData(), autoload_with=conn
            )
            row = conn.execute(sa.select(current)).mappings().one()
            assert row["adoption_state"] == "accepted"
            assert row["mutation_allowed"] is True
            assert row["adoption_projection_version"] == 1

            conn.execute(
                events.insert().values(
                    **_event(
                        adoption_event_id="revoke:one",
                        decision="revoked",
                        supersedes_adoption_event_id="adoption:one",
                        eligibility_hash="e" * 64,
                    )
                )
            )
            conn.execute(
                events.insert().values(
                    **_event(
                        adoption_event_id="adoption:two",
                        eligibility_hash="f" * 64,
                    )
                )
            )
            with pytest.raises(RuntimeError, match="multiple_accepted"):
                migration_135.downgrade()
        finally:
            migration_125.op = previous_125
            migration_135.op = previous_135


def test_migration_135_round_trips_legacy_compatible_history():
    migration_125 = _load_migration()
    migration_135 = _load_migration_135()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    _base_schema(engine)
    with engine.begin() as conn:
        context = Operations(MigrationContext.configure(conn))
        previous_125 = migration_125.op
        previous_135 = migration_135.op
        migration_125.op = context
        migration_135.op = context
        try:
            migration_125.upgrade()
            migration_135.upgrade()
            migration_135.downgrade()
            events = sa.Table(
                "brc_ticket_exit_policy_adoption_events", sa.MetaData(), autoload_with=conn
            )
            conn.execute(events.insert().values(**_event()))
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    events.insert().values(
                        **_event(
                            adoption_event_id="adoption:two",
                            eligibility_hash="f" * 64,
                        )
                    )
                )
            migration_135.upgrade()
            current_columns = {
                item["name"]
                for item in sa.inspect(conn).get_columns(
                    "brc_ticket_exit_policy_current"
                )
            }
            assert {
                "adoption_state",
                "mutation_allowed",
                "adoption_projection_version",
            } <= current_columns
        finally:
            migration_125.op = previous_125
            migration_135.op = previous_135
