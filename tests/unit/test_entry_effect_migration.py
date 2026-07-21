from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-22-145_add_entry_effect_projection.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_145_entry_effect",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_145_adds_typed_entry_effect_constraints_and_fill_pending_event():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        sa.Column("protected_submit_attempt_id", sa.String, primary_key=True),
        sa.Column("exchange_write_called", sa.Boolean, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
    )
    sa.Table(
        "brc_ticket_bound_lifecycle_events",
        metadata,
        sa.Column("lifecycle_event_id", sa.String, primary_key=True),
        sa.Column("event_type", sa.String, nullable=False),
        sa.CheckConstraint(
            "event_type IN ('entry_filled')",
            name="ck_brc_lifecycle_event_type",
        ),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns(
                "brc_ticket_bound_protected_submit_attempts"
            )
        }
        conn.execute(
            sa.text(
                "INSERT INTO brc_ticket_bound_lifecycle_events "
                "(lifecycle_event_id, event_type) "
                "VALUES ('event-1', 'entry_fill_pending')"
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protected_submit_attempts ("
                        "protected_submit_attempt_id, exchange_write_called, "
                        "updated_at_ms, entry_effect_state, "
                        "entry_effect_observed_at_ms, protection_barrier_state, "
                        "protection_quantity) VALUES ("
                        "'bad-fill', true, 1, 'accepted_filled', 1, "
                        "'initial_stop_pending', 0)"
                    )
                )
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protected_submit_attempts ("
                        "protected_submit_attempt_id, exchange_write_called, "
                        "updated_at_ms, entry_effect_state, "
                        "entry_effect_observed_at_ms, protection_barrier_state, "
                        "initial_stop_confirmed_at_ms, protection_quantity) VALUES ("
                        "'zero-confirmed-stop', true, 1, 'accepted_zero_fill', 1, "
                        "'initial_stop_confirmed', 2, NULL)"
                    )
                )
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protected_submit_attempts ("
                        "protected_submit_attempt_id, exchange_write_called, "
                        "updated_at_ms, entry_effect_state, "
                        "entry_effect_observed_at_ms, protection_barrier_state, "
                        "initial_stop_confirmed_at_ms, protection_quantity) VALUES ("
                        "'confirmed-before-effect', true, 1, 'accepted_filled', 5, "
                        "'initial_stop_confirmed', 2, 1)"
                    )
                )
        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protected_submit_attempts ("
                        "protected_submit_attempt_id, exchange_write_called, "
                        "updated_at_ms, entry_effect_state, "
                        "entry_effect_observed_at_ms, protection_barrier_state, "
                        "protection_quantity) VALUES ("
                        "'unknown-guessed-qty', true, 1, 'outcome_unknown', 1, "
                        "'hard_stopped', 1)"
                    )
                )

    assert {
        "entry_effect_state",
        "entry_effect_observed_at_ms",
        "protection_barrier_state",
        "initial_stop_deadline_at_ms",
        "initial_stop_confirmed_at_ms",
        "protection_quantity",
    } <= columns
    assert migration.revision == "145"
    assert migration.down_revision == "144"
