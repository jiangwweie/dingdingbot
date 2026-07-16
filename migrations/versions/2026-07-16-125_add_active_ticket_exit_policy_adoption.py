"""Add append-only active-Ticket exit-policy adoption authority.

Revision ID: 125
Revises: 124
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "125"
down_revision: Union[str, None] = "124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADOPTION_TABLE = "brc_ticket_exit_policy_adoption_events"
CURRENT_TABLE = "brc_ticket_exit_policy_current"
CURRENT_BINDING_CHECK = "ck_brc_ticket_exit_policy_binding_source"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
COMMAND_SOURCE_CHECK = "ck_brc_exchange_command_source"
PREVIOUS_COMMAND_SOURCES = (
    "protected_submit",
    "protection_recovery",
    "runner_mutation",
    "orphan_cleanup",
    "exit_policy_runner",
    "exit_policy_close",
)
COMMAND_SOURCES = PREVIOUS_COMMAND_SOURCES + ("exit_policy_tp1_reprice",)


def upgrade() -> None:
    _create_adoption_table()
    _extend_current_projection()
    _replace_command_source_constraint(COMMAND_SOURCES)


def downgrade() -> None:
    _assert_no_tp1_reprice_commands()
    _replace_command_source_constraint(PREVIOUS_COMMAND_SOURCES)
    _contract_current_projection()
    if _has_table(ADOPTION_TABLE):
        op.drop_table(ADOPTION_TABLE)


def _create_adoption_table() -> None:
    if _has_table(ADOPTION_TABLE):
        return
    op.create_table(
        ADOPTION_TABLE,
        sa.Column("adoption_event_id", sa.String(192), primary_key=True),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("from_exit_policy_hash", sa.String(64), nullable=False),
        sa.Column("to_exit_policy_id", sa.String(192), nullable=False),
        sa.Column("to_exit_policy_version", sa.String(96), nullable=False),
        sa.Column("to_exit_policy_hash", sa.String(64), nullable=False),
        sa.Column("owner_authorization_ref", sa.String(256), nullable=False),
        sa.Column(
            "eligibility_snapshot",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("eligibility_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("runtime_head", sa.String(40), nullable=False),
        sa.Column("supersedes_adoption_event_id", sa.String(192), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted', 'rejected', 'revoked')",
            name="ck_brc_ticket_exit_policy_adoption_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'revoked' AND supersedes_adoption_event_id IS NOT NULL) "
            "OR (decision <> 'revoked' AND supersedes_adoption_event_id IS NULL)",
            name="ck_brc_ticket_exit_policy_adoption_supersedes",
        ),
        sa.CheckConstraint(
            "length(from_exit_policy_hash) = 64 "
            "AND length(to_exit_policy_hash) = 64 "
            "AND length(eligibility_hash) = 64",
            name="ck_brc_ticket_exit_policy_adoption_hash_lengths",
        ),
        sa.CheckConstraint(
            "length(runtime_head) = 40",
            name="ck_brc_ticket_exit_policy_adoption_runtime_head",
        ),
        sa.CheckConstraint(
            "length(owner_authorization_ref) > 0",
            name="ck_brc_ticket_exit_policy_adoption_owner_ref",
        ),
        sa.CheckConstraint(
            "length(CAST(eligibility_snapshot AS TEXT)) <= 65536",
            name="ck_brc_ticket_exit_policy_adoption_snapshot_size",
        ),
    )
    op.create_index(
        "uq_brc_ticket_exit_policy_one_accepted_adoption",
        ADOPTION_TABLE,
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("decision = 'accepted'"),
        sqlite_where=sa.text("decision = 'accepted'"),
    )
    op.create_index(
        "idx_brc_ticket_exit_policy_adoption_ticket_time",
        ADOPTION_TABLE,
        ["ticket_id", sa.text("created_at_ms DESC")],
        unique=False,
    )


def _extend_current_projection() -> None:
    if not _has_table(CURRENT_TABLE):
        raise RuntimeError("ticket_exit_policy_current_missing_before_adoption")
    binding_source = sa.Column(
        "binding_source",
        sa.String(32),
        nullable=False,
        server_default="ticket",
    )
    adoption_event_id = sa.Column(
        "adoption_event_id",
        sa.String(192),
        nullable=True,
    )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(CURRENT_TABLE, recreate="always") as batch_op:
            if not _has_column(CURRENT_TABLE, "binding_source"):
                batch_op.add_column(binding_source)
            if not _has_column(CURRENT_TABLE, "adoption_event_id"):
                batch_op.add_column(adoption_event_id)
            batch_op.create_check_constraint(
                CURRENT_BINDING_CHECK,
                "(binding_source = 'ticket' AND adoption_event_id IS NULL) OR "
                "(binding_source = 'adoption_event' AND adoption_event_id IS NOT NULL)",
            )
    else:
        if not _has_column(CURRENT_TABLE, "binding_source"):
            op.add_column(CURRENT_TABLE, binding_source)
        if not _has_column(CURRENT_TABLE, "adoption_event_id"):
            op.add_column(CURRENT_TABLE, adoption_event_id)
        op.create_check_constraint(
            CURRENT_BINDING_CHECK,
            CURRENT_TABLE,
            "(binding_source = 'ticket' AND adoption_event_id IS NULL) OR "
            "(binding_source = 'adoption_event' AND adoption_event_id IS NOT NULL)",
        )
    op.create_index(
        "idx_brc_ticket_exit_policy_current_adoption",
        CURRENT_TABLE,
        ["adoption_event_id"],
        unique=True,
        postgresql_where=sa.text("adoption_event_id IS NOT NULL"),
        sqlite_where=sa.text("adoption_event_id IS NOT NULL"),
    )


def _contract_current_projection() -> None:
    if not _has_table(CURRENT_TABLE):
        return
    index_names = {
        str(item.get("name") or "")
        for item in sa.inspect(op.get_bind()).get_indexes(CURRENT_TABLE)
    }
    if "idx_brc_ticket_exit_policy_current_adoption" in index_names:
        op.drop_index(
            "idx_brc_ticket_exit_policy_current_adoption",
            table_name=CURRENT_TABLE,
        )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(CURRENT_TABLE, recreate="always") as batch_op:
            if CURRENT_BINDING_CHECK in _check_constraint_names(CURRENT_TABLE):
                batch_op.drop_constraint(CURRENT_BINDING_CHECK, type_="check")
            if _has_column(CURRENT_TABLE, "adoption_event_id"):
                batch_op.drop_column("adoption_event_id")
            if _has_column(CURRENT_TABLE, "binding_source"):
                batch_op.drop_column("binding_source")
    else:
        if CURRENT_BINDING_CHECK in _check_constraint_names(CURRENT_TABLE):
            op.drop_constraint(
                CURRENT_BINDING_CHECK,
                CURRENT_TABLE,
                type_="check",
            )
        if _has_column(CURRENT_TABLE, "adoption_event_id"):
            op.drop_column(CURRENT_TABLE, "adoption_event_id")
        if _has_column(CURRENT_TABLE, "binding_source"):
            op.drop_column(CURRENT_TABLE, "binding_source")


def _assert_no_tp1_reprice_commands() -> None:
    if not _has_table(COMMAND_TABLE):
        return
    table = sa.Table(COMMAND_TABLE, sa.MetaData(), autoload_with=op.get_bind())
    count = op.get_bind().execute(
        sa.select(sa.func.count())
        .select_from(table)
        .where(table.c.command_source == "exit_policy_tp1_reprice")
    ).scalar_one()
    if count:
        raise RuntimeError("cannot_downgrade_active_tp1_reprice_commands")


def _replace_command_source_constraint(sources: tuple[str, ...]) -> None:
    if not _has_table(COMMAND_TABLE) or not _has_column(
        COMMAND_TABLE, "command_source"
    ):
        return
    condition = "command_source IN (" + ", ".join(repr(item) for item in sources) + ")"
    existing = COMMAND_SOURCE_CHECK in _check_constraint_names(COMMAND_TABLE)
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(COMMAND_TABLE, recreate="always") as batch_op:
            if existing:
                batch_op.drop_constraint(COMMAND_SOURCE_CHECK, type_="check")
            batch_op.create_check_constraint(COMMAND_SOURCE_CHECK, condition)
    else:
        if existing:
            op.drop_constraint(
                COMMAND_SOURCE_CHECK,
                COMMAND_TABLE,
                type_="check",
            )
        op.create_check_constraint(
            COMMAND_SOURCE_CHECK,
            COMMAND_TABLE,
            condition,
        )


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _check_constraint_names(table_name: str) -> set[str]:
    return {
        str(item.get("name") or "")
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    }
