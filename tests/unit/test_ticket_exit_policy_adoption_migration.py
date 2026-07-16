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


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_125_active_ticket_exit_policy_adoption", MIGRATION_PATH
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
