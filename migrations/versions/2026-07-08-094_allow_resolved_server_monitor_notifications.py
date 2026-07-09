"""Allow resolved server monitor notification state.

Revision ID: 094
Revises: 093
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "094"
down_revision: Union[str, None] = "093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        return
    op.drop_constraint(
        "ck_brc_monitor_notify_state",
        "brc_server_monitor_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_monitor_notify_state",
        "brc_server_monitor_notifications",
        "notification_state IN ('pending', 'sent', 'failed', 'suppressed', 'retrying', 'resolved')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        return
    op.execute(
        """
        UPDATE brc_server_monitor_notifications
        SET notification_state = 'suppressed'
        WHERE notification_state = 'resolved'
        """
    )
    op.drop_constraint(
        "ck_brc_monitor_notify_state",
        "brc_server_monitor_notifications",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_monitor_notify_state",
        "brc_server_monitor_notifications",
        "notification_state IN ('pending', 'sent', 'failed', 'suppressed', 'retrying')",
    )
