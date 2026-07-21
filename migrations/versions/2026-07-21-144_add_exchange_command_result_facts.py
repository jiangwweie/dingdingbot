"""Persist typed durable exchange-result facts for protection decisions.

Revision ID: 144
Revises: 143
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "144"
down_revision: Union[str, None] = "143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_ticket_bound_exchange_commands"


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE):
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns(TABLE)}
    additions = (
        ("exchange_order_status", sa.String(64), True),
        ("executed_qty", sa.Numeric(36, 18), True),
        ("average_exec_price", sa.Numeric(36, 18), True),
        ("exchange_observed_at_ms", sa.BIGINT(), True),
        (
            "result_facts_complete",
            sa.Boolean(),
            False,
        ),
    )
    for name, column_type, nullable in additions:
        if name in columns:
            continue
        op.add_column(
            TABLE,
            sa.Column(
                name,
                column_type,
                nullable=nullable,
                server_default=(sa.text("false") if name == "result_facts_complete" else None),
            ),
        )
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE brc_ticket_bound_exchange_commands "
        "ALTER COLUMN result_facts_complete SET DEFAULT false"
    )
    _replace_check(
        "ck_brc_exchange_command_executed_qty",
        "executed_qty IS NULL OR (executed_qty >= 0 AND executed_qty <= amount)",
    )
    _replace_check(
        "ck_brc_exchange_command_average_exec_price",
        "average_exec_price IS NULL OR average_exec_price > 0",
    )
    _replace_check(
        "ck_brc_exchange_command_result_facts_complete",
        "NOT result_facts_complete OR "
        "(exchange_order_status IS NOT NULL AND exchange_observed_at_ms IS NOT NULL)",
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brc_exchange_command_result_facts "
        "ON brc_ticket_bound_exchange_commands "
        "(protected_submit_attempt_id, order_role, result_facts_complete)"
    )


def downgrade() -> None:
    # Forward-only: typed exchange facts preserve future reconciliation lineage.
    return


def _replace_check(name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {name} CHECK ({expression})")
