"""Add exact protection recovery generation and source lineage.

Revision ID: 146
Revises: 145
Create Date: 2026-07-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "146"
down_revision: Union[str, None] = "145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ATTEMPT_TABLE = "brc_ticket_bound_protected_submit_attempts"
RECOVERY_TABLE = "brc_ticket_bound_protection_recovery_commands"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
TICKET_TABLE = "brc_action_time_tickets"
OLD_UNIQUE = "uq_brc_prot_rec_attempt"
NEW_UNIQUE = "uq_brc_prot_rec_attempt_generation"
LINEAGE_BLOCKER = "protection_recovery_lineage_backfill_unproven"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(ATTEMPT_TABLE):
        _add_attempt_generation(inspector)
    inspector = sa.inspect(bind)
    if not inspector.has_table(RECOVERY_TABLE):
        return
    _add_recovery_lineage(inspector)
    _backfill_recovery_lineage()
    _replace_constraints()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"ALTER TABLE {RECOVERY_TABLE} "
            "ALTER COLUMN protection_barrier_generation DROP DEFAULT"
        )
    op.create_index(
        "idx_brc_prot_rec_exact_current",
        RECOVERY_TABLE,
        (
            "netting_domain_key",
            "exposure_episode_id",
            "status",
            "protection_barrier_generation",
        ),
    )


def downgrade() -> None:
    # Forward-only: multiple recovery generations and their typed source lineage
    # cannot be collapsed into the old Attempt-only unique key without deleting
    # real-funds safety truth.
    return


def _add_attempt_generation(inspector: sa.Inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns(ATTEMPT_TABLE)}
    if "protection_barrier_generation" not in columns:
        op.add_column(
            ATTEMPT_TABLE,
            sa.Column(
                "protection_barrier_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(ATTEMPT_TABLE, recreate="always") as batch_op:
            batch_op.create_check_constraint(
                "ck_brc_ticket_submit_barrier_generation",
                "protection_barrier_generation > 0",
            )
        return
    op.execute(
        f"ALTER TABLE {ATTEMPT_TABLE} DROP CONSTRAINT IF EXISTS "
        "ck_brc_ticket_submit_barrier_generation"
    )
    op.create_check_constraint(
        "ck_brc_ticket_submit_barrier_generation",
        ATTEMPT_TABLE,
        "protection_barrier_generation > 0",
    )


def _add_recovery_lineage(inspector: sa.Inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns(RECOVERY_TABLE)}
    additions = (
        (
            "protection_barrier_generation",
            sa.Integer(),
            False,
            sa.text("1"),
        ),
        ("exposure_episode_id", sa.String(192), True, None),
        ("netting_domain_key", sa.String(640), True, None),
        ("source_entry_exchange_command_id", sa.String(192), True, None),
        ("protection_quantity", sa.Numeric(36, 18), True, None),
    )
    for name, column_type, nullable, default in additions:
        if name in columns:
            continue
        op.add_column(
            RECOVERY_TABLE,
            sa.Column(
                name,
                column_type,
                nullable=nullable,
                server_default=default,
            ),
        )


def _backfill_recovery_lineage() -> None:
    inspector = sa.inspect(op.get_bind())
    required = {ATTEMPT_TABLE, COMMAND_TABLE, TICKET_TABLE}
    if required <= set(inspector.get_table_names()):
        op.execute(
            f"""
            WITH proven AS (
              SELECT recovery.protection_recovery_command_id AS recovery_id,
                     MIN(command.exposure_episode_id) AS exposure_episode_id,
                     MIN(command.netting_domain_key) AS netting_domain_key,
                     MIN(command.exchange_command_id) AS entry_command_id,
                     MIN(attempt.protection_quantity) AS protection_quantity
              FROM {RECOVERY_TABLE} AS recovery
              JOIN {COMMAND_TABLE} AS command
                ON command.protected_submit_attempt_id =
                   recovery.protected_submit_attempt_id
               AND command.ticket_id = recovery.ticket_id
              JOIN {ATTEMPT_TABLE} AS attempt
                ON attempt.protected_submit_attempt_id =
                   command.protected_submit_attempt_id
              JOIN {TICKET_TABLE} AS ticket
                ON ticket.ticket_id = command.ticket_id
              WHERE command.order_role = 'ENTRY'
                AND command.command_source = 'protected_submit'
                AND command.command_state IN (
                  'confirmed_submitted', 'reconciled_submitted'
                )
                AND command.result_facts_complete = true
                AND command.executed_qty > 0
                AND attempt.entry_effect_state = 'accepted_filled'
                AND attempt.protection_quantity = command.executed_qty
                AND command.exposure_episode_id = ticket.exposure_episode_id
              GROUP BY recovery.protection_recovery_command_id
              HAVING COUNT(*) = 1
            )
            UPDATE {RECOVERY_TABLE} AS recovery
            SET exposure_episode_id = (
                  SELECT proven.exposure_episode_id
                  FROM proven
                  WHERE proven.recovery_id =
                        recovery.protection_recovery_command_id
                ),
                netting_domain_key = (
                  SELECT proven.netting_domain_key
                  FROM proven
                  WHERE proven.recovery_id =
                        recovery.protection_recovery_command_id
                ),
                source_entry_exchange_command_id = (
                  SELECT proven.entry_command_id
                  FROM proven
                  WHERE proven.recovery_id =
                        recovery.protection_recovery_command_id
                ),
                protection_quantity = (
                  SELECT proven.protection_quantity
                  FROM proven
                  WHERE proven.recovery_id =
                        recovery.protection_recovery_command_id
                )
            WHERE recovery.protection_recovery_command_id IN (
              SELECT proven.recovery_id FROM proven
            )
            """
        )
    blockers_type = (
        postgresql.JSONB()
        if op.get_bind().dialect.name == "postgresql"
        else sa.JSON()
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {RECOVERY_TABLE}
            SET status = 'blocked',
                first_blocker = :blocker,
                blockers = :blockers
            WHERE exposure_episode_id IS NULL
               OR trim(exposure_episode_id) = ''
               OR netting_domain_key IS NULL
               OR trim(netting_domain_key) = ''
               OR source_entry_exchange_command_id IS NULL
               OR trim(source_entry_exchange_command_id) = ''
               OR protection_quantity IS NULL
               OR protection_quantity <= 0
            """
        ).bindparams(
            sa.bindparam("blocker", value=LINEAGE_BLOCKER),
            sa.bindparam(
                "blockers",
                value=[LINEAGE_BLOCKER],
                type_=blockers_type,
            ),
        )
    )


def _replace_constraints() -> None:
    bind = op.get_bind()
    exact_identity = (
        "status = 'blocked' OR ("
        "exposure_episode_id IS NOT NULL AND trim(exposure_episode_id) <> '' AND "
        "netting_domain_key IS NOT NULL AND trim(netting_domain_key) <> '' AND "
        "source_entry_exchange_command_id IS NOT NULL AND "
        "trim(source_entry_exchange_command_id) <> '' AND "
        "protection_quantity IS NOT NULL AND protection_quantity > 0)"
    )
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(RECOVERY_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
            batch_op.alter_column(
                "protection_barrier_generation",
                existing_type=sa.Integer(),
                nullable=False,
                server_default=None,
            )
            batch_op.create_unique_constraint(
                NEW_UNIQUE,
                ("protected_submit_attempt_id", "protection_barrier_generation"),
            )
            batch_op.create_check_constraint(
                "ck_brc_prot_rec_generation",
                "protection_barrier_generation > 0",
            )
            batch_op.create_check_constraint(
                "ck_brc_prot_rec_quantity",
                "protection_quantity IS NULL OR protection_quantity > 0",
            )
            batch_op.create_check_constraint(
                "ck_brc_prot_rec_executable_lineage",
                exact_identity,
            )
        return
    op.drop_constraint(OLD_UNIQUE, RECOVERY_TABLE, type_="unique")
    op.create_unique_constraint(
        NEW_UNIQUE,
        RECOVERY_TABLE,
        ("protected_submit_attempt_id", "protection_barrier_generation"),
    )
    op.create_check_constraint(
        "ck_brc_prot_rec_generation",
        RECOVERY_TABLE,
        "protection_barrier_generation > 0",
    )
    op.create_check_constraint(
        "ck_brc_prot_rec_quantity",
        RECOVERY_TABLE,
        "protection_quantity IS NULL OR protection_quantity > 0",
    )
    op.create_check_constraint(
        "ck_brc_prot_rec_executable_lineage",
        RECOVERY_TABLE,
        exact_identity,
    )
