from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-22-146_add_protection_recovery_generation.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_146_protection_recovery_generation",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_146_is_the_single_successor_to_entry_effect_truth():
    migration = _load_migration()

    assert migration.revision == "146"
    assert migration.down_revision == "145"


def test_migration_146_backfills_only_proven_recovery_lineage_and_blocks_unknown():
    engine = _legacy_engine()
    with engine.begin() as conn:
        _seed_legacy_rows(conn)
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()

        attempts = {
            row["protected_submit_attempt_id"]: row
            for row in conn.execute(
                sa.text(
                    "SELECT protected_submit_attempt_id, "
                    "protection_barrier_generation "
                    "FROM brc_ticket_bound_protected_submit_attempts"
                )
            ).mappings()
        }
        recoveries = {
            row["protected_submit_attempt_id"]: row
            for row in conn.execute(
                sa.text(
                    "SELECT protected_submit_attempt_id, status, first_blocker, "
                    "protection_barrier_generation, exposure_episode_id, "
                    "netting_domain_key, source_entry_exchange_command_id, "
                    "protection_quantity "
                    "FROM brc_ticket_bound_protection_recovery_commands"
                )
            ).mappings()
        }

        assert attempts["attempt-proven"]["protection_barrier_generation"] == 1
        assert recoveries["attempt-proven"]["status"] == "prepared"
        assert recoveries["attempt-proven"]["exposure_episode_id"] == "episode-1"
        assert recoveries["attempt-proven"]["netting_domain_key"] == "domain-1"
        assert (
            recoveries["attempt-proven"]["source_entry_exchange_command_id"]
            == "entry-command-1"
        )
        assert Decimal(str(recoveries["attempt-proven"]["protection_quantity"])) == Decimal(
            "0.02"
        )

        assert recoveries["attempt-unproven"]["status"] == "blocked"
        assert (
            recoveries["attempt-unproven"]["first_blocker"]
            == "protection_recovery_lineage_backfill_unproven"
        )
        assert recoveries["attempt-unproven"]["source_entry_exchange_command_id"] is None
        assert recoveries["attempt-unproven"]["protection_quantity"] is None


def test_migration_146_enforces_exact_identity_for_executable_rows_and_multi_generation():
    engine = _legacy_engine()
    with engine.begin() as conn:
        _seed_legacy_rows(conn)
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()

        conn.execute(
            sa.text(
                "INSERT INTO brc_ticket_bound_protection_recovery_commands ("
                "protection_recovery_command_id, protected_submit_attempt_id, "
                "ticket_id, status, first_blocker, blockers, "
                "protection_barrier_generation, exposure_episode_id, "
                "netting_domain_key, source_entry_exchange_command_id, "
                "protection_quantity) VALUES ("
                "'recovery-proven-2', 'attempt-proven', 'ticket-1', "
                "'prepared', NULL, '[]', 2, 'episode-1', 'domain-1', "
                "'entry-command-1', 0.03)"
            )
        )
        generations = conn.execute(
            sa.text(
                "SELECT protection_barrier_generation "
                "FROM brc_ticket_bound_protection_recovery_commands "
                "WHERE protected_submit_attempt_id='attempt-proven' "
                "ORDER BY protection_barrier_generation"
            )
        ).scalars().all()
        assert generations == [1, 2]

        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protection_recovery_commands ("
                        "protection_recovery_command_id, protected_submit_attempt_id, "
                        "ticket_id, status, blockers, protection_barrier_generation, "
                        "exposure_episode_id, netting_domain_key, "
                        "source_entry_exchange_command_id, protection_quantity) VALUES ("
                        "'duplicate-generation', 'attempt-proven', 'ticket-1', "
                        "'prepared', '[]', 1, 'episode-1', 'domain-1', "
                        "'entry-command-1', 0.02)"
                    )
                )

        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO brc_ticket_bound_protection_recovery_commands ("
                        "protection_recovery_command_id, protected_submit_attempt_id, "
                        "ticket_id, status, blockers, protection_barrier_generation) "
                        "VALUES ('missing-identity', 'attempt-unproven', 'ticket-2', "
                        "'prepared', '[]', 2)"
                    )
                )

        with pytest.raises(sa.exc.IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "UPDATE brc_ticket_bound_protected_submit_attempts "
                        "SET protection_barrier_generation=0 "
                        "WHERE protected_submit_attempt_id='attempt-proven'"
                    )
                )


def test_migration_146_blocks_ambiguous_multi_entry_lineage():
    engine = _legacy_engine()
    with engine.begin() as conn:
        _seed_legacy_rows(conn)
        conn.execute(
            sa.text(
                "INSERT INTO brc_ticket_bound_exchange_commands VALUES ("
                "'entry-command-duplicate', 'attempt-proven', 'ticket-1', "
                "'ENTRY', 'protected_submit', 'confirmed_submitted', true, "
                "0.02, 'episode-1', 'domain-1')"
            )
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))

        migration.upgrade()

        recovery = conn.execute(
            sa.text(
                "SELECT status, first_blocker, source_entry_exchange_command_id "
                "FROM brc_ticket_bound_protection_recovery_commands "
                "WHERE protected_submit_attempt_id='attempt-proven'"
            )
        ).mappings().one()
        assert recovery["status"] == "blocked"
        assert recovery["first_blocker"] == (
            "protection_recovery_lineage_backfill_unproven"
        )
        assert recovery["source_entry_exchange_command_id"] is None


def _legacy_engine() -> sa.Engine:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        sa.Column("protected_submit_attempt_id", sa.String, primary_key=True),
        sa.Column("entry_effect_state", sa.String, nullable=False),
        sa.Column("protection_barrier_state", sa.String, nullable=False),
        sa.Column("protection_quantity", sa.Numeric(36, 18), nullable=True),
    )
    sa.Table(
        "brc_action_time_tickets",
        metadata,
        sa.Column("ticket_id", sa.String, primary_key=True),
        sa.Column("exposure_episode_id", sa.String, nullable=True),
    )
    sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        sa.Column("exchange_command_id", sa.String, primary_key=True),
        sa.Column("protected_submit_attempt_id", sa.String, nullable=False),
        sa.Column("ticket_id", sa.String, nullable=False),
        sa.Column("order_role", sa.String, nullable=False),
        sa.Column("command_source", sa.String, nullable=False),
        sa.Column("command_state", sa.String, nullable=False),
        sa.Column("result_facts_complete", sa.Boolean, nullable=False),
        sa.Column("executed_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("exposure_episode_id", sa.String, nullable=True),
        sa.Column("netting_domain_key", sa.String, nullable=True),
    )
    sa.Table(
        "brc_ticket_bound_protection_recovery_commands",
        metadata,
        sa.Column("protection_recovery_command_id", sa.String, primary_key=True),
        sa.Column("protected_submit_attempt_id", sa.String, nullable=False),
        sa.Column("ticket_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("first_blocker", sa.String, nullable=True),
        sa.Column("blockers", sa.JSON, nullable=False, server_default="[]"),
        sa.UniqueConstraint(
            "protected_submit_attempt_id",
            name="uq_brc_prot_rec_attempt",
        ),
    )
    metadata.create_all(engine)
    return engine


def _seed_legacy_rows(conn: sa.engine.Connection) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO brc_ticket_bound_protected_submit_attempts VALUES "
            "('attempt-proven', 'accepted_filled', 'initial_stop_pending', 0.02), "
            "('attempt-unproven', 'accepted_filled', 'initial_stop_pending', 0.03)"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_action_time_tickets VALUES "
            "('ticket-1', 'episode-1'), ('ticket-2', 'episode-2')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_ticket_bound_exchange_commands VALUES ("
            "'entry-command-1', 'attempt-proven', 'ticket-1', 'ENTRY', "
            "'protected_submit', 'confirmed_submitted', true, 0.02, "
            "'episode-1', 'domain-1')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brc_ticket_bound_protection_recovery_commands VALUES "
            "('recovery-proven', 'attempt-proven', 'ticket-1', 'prepared', NULL, '[]'), "
            "('recovery-unproven', 'attempt-unproven', 'ticket-2', 'prepared', NULL, '[]')"
        )
    )
