"""Extend the one exchange-command authority across lifecycle mutations.

Revision ID: 114
Revises: 113
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "114"
down_revision: Union[str, None] = "113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_ticket_bound_exchange_commands"
OLD_UNIQUE = "uq_brc_exchange_command_ticket_role_generation"
NEW_UNIQUE = "uq_brc_exchange_command_source_generation"


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    additions = (
        ("exchange_id", sa.String(128), "legacy_unknown_exchange"),
        ("position_mode", sa.String(32), "unknown"),
        ("position_side", sa.String(16), None),
        ("position_bucket", sa.String(16), "ANY"),
        ("netting_domain_key", sa.String(640), "legacy_unknown_domain"),
        ("reduce_intent", sa.String(32), "open_position"),
        ("command_kind", sa.String(32), "place_order"),
        ("command_source", sa.String(64), "protected_submit"),
        ("source_command_id", sa.String(192), "legacy_unknown_source"),
        ("target_exchange_order_id", sa.String(192), None),
        ("claim_owner", sa.String(128), None),
        ("claim_token", sa.String(192), None),
        ("claim_started_at_ms", sa.BIGINT(), None),
        ("claim_expires_at_ms", sa.BIGINT(), None),
        ("execution_attempt_count", sa.Integer(), 0),
        ("last_reconciled_at_ms", sa.BIGINT(), None),
        ("exchange_result", sa.JSON(), "{}"),
    )
    for name, column_type, default in additions:
        if _has_column(name):
            continue
        nullable = default is None
        kwargs = {"nullable": nullable}
        if default is not None:
            kwargs["server_default"] = str(default)
        op.add_column(TABLE, sa.Column(name, column_type, **kwargs))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            UPDATE {TABLE}
            SET exchange_id = CASE
                  WHEN exchange_instrument_id LIKE 'binance_usdm:%'
                  THEN 'binance_usdm'
                  ELSE exchange_id
                END,
                reduce_intent = CASE
                  WHEN reduce_only THEN 'reduce_position'
                  ELSE 'open_position'
                END,
                source_command_id = protected_submit_attempt_id
            """
        )
    )
    _drop_old_unique()
    if not _has_index(NEW_UNIQUE):
        op.create_index(
            NEW_UNIQUE,
            TABLE,
            [
                "command_source",
                "source_command_id",
                "command_kind",
                "order_role",
                "command_generation",
            ],
            unique=True,
        )
    if not _has_index("idx_brc_exchange_command_claim"):
        op.create_index(
            "idx_brc_exchange_command_claim",
            TABLE,
            ["command_state", "claim_expires_at_ms", "prepared_at_ms"],
        )
    if not _has_index("idx_brc_exchange_command_domain_state"):
        op.create_index(
            "idx_brc_exchange_command_domain_state",
            TABLE,
            ["netting_domain_key", "command_state", "updated_at_ms"],
        )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    for index_name in (
        "idx_brc_exchange_command_domain_state",
        "idx_brc_exchange_command_claim",
        NEW_UNIQUE,
    ):
        if _has_index(index_name):
            op.drop_index(index_name, table_name=TABLE)
    _restore_old_unique_if_possible()
    for name in (
        "exchange_result",
        "last_reconciled_at_ms",
        "execution_attempt_count",
        "claim_expires_at_ms",
        "claim_started_at_ms",
        "claim_token",
        "claim_owner",
        "target_exchange_order_id",
        "source_command_id",
        "command_source",
        "command_kind",
        "reduce_intent",
        "netting_domain_key",
        "position_bucket",
        "position_side",
        "position_mode",
        "exchange_id",
    ):
        if _has_column(name):
            op.drop_column(TABLE, name)


def _drop_old_unique() -> None:
    names = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_unique_constraints(TABLE)
    }
    if OLD_UNIQUE not in names:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        return
    op.drop_constraint(OLD_UNIQUE, TABLE, type_="unique")


def _restore_old_unique_if_possible() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            f"""
            SELECT 1 FROM {TABLE}
            GROUP BY ticket_id, order_role, command_generation
            HAVING COUNT(*) > 1 LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "cannot downgrade migration 114 with lifecycle place/cancel "
            "commands sharing one legacy role generation"
        )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.create_unique_constraint(
                OLD_UNIQUE,
                ["ticket_id", "order_role", "command_generation"],
            )
        return
    op.create_unique_constraint(
        OLD_UNIQUE,
        TABLE,
        ["ticket_id", "order_role", "command_generation"],
    )


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(column_name: str) -> bool:
    return column_name in {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(TABLE)
    }


def _has_index(index_name: str) -> bool:
    return index_name in {
        item.get("name") for item in sa.inspect(op.get_bind()).get_indexes(TABLE)
    }
