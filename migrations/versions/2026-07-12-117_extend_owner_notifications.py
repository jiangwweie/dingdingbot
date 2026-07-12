"""Extend the monitor ledger for typed Owner notifications.

Revision ID: 117
Revises: 116
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "117"
down_revision: Union[str, None] = "116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "brc_server_monitor_notifications"
INDEX = "idx_brc_monitor_notify_correlation_kind"
STATE_INDEX = "idx_brc_monitor_notify_state"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    columns = {item["name"] for item in inspector.get_columns(TABLE)}
    additions = (
        sa.Column(
            "notification_kind",
            sa.String(64),
            nullable=False,
            server_default="legacy_monitor_event",
        ),
        sa.Column(
            "severity", sa.String(32), nullable=False, server_default="warning"
        ),
        sa.Column("correlation_id", sa.String(256), nullable=True),
        sa.Column(
            "template_version",
            sa.String(64),
            nullable=False,
            server_default="legacy-text-v0",
        ),
        sa.Column(
            "owner_action_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("resolved_at_ms", sa.BIGINT(), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column(TABLE, column)
    op.execute(
        sa.text(
            f"""
            UPDATE {TABLE}
            SET correlation_id = COALESCE(correlation_id, dedupe_key),
                occurred_at_ms = COALESCE(occurred_at_ms, first_seen_at_ms)
            WHERE correlation_id IS NULL OR occurred_at_ms IS NULL
            """
        )
    )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(
            INDEX,
            TABLE,
            ["correlation_id", "notification_kind"],
            unique=False,
        )
    if STATE_INDEX not in indexes:
        op.create_index(
            STATE_INDEX,
            TABLE,
            ["notification_state"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE):
        return
    indexes = {item["name"] for item in inspector.get_indexes(TABLE)}
    if STATE_INDEX in indexes:
        op.drop_index(STATE_INDEX, table_name=TABLE)
    if INDEX in indexes:
        op.drop_index(INDEX, table_name=TABLE)
    columns = {item["name"] for item in sa.inspect(bind).get_columns(TABLE)}
    for name in (
        "resolved_at_ms",
        "occurred_at_ms",
        "owner_action_required",
        "template_version",
        "correlation_id",
        "severity",
        "notification_kind",
    ):
        if name in columns:
            op.drop_column(TABLE, name)
