"""Make live-signal identity event-spec-version aware.

Revision ID: 112
Revises: 111
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "112"
down_revision: Union[str, None] = "111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "brc_live_signal_events"
UNIQUE_NAME = "uq_brc_live_signal_identity"
OLD_UNIQUE_COLUMNS = [
    "strategy_group_id",
    "symbol",
    "side",
    "detector_key",
    "signal_type",
    "event_time_ms",
]
NEW_UNIQUE_COLUMNS = [
    "strategy_group_id",
    "symbol",
    "side",
    "detector_key",
    "event_spec_id",
    "signal_type",
    "event_time_ms",
]
MIGRATION_AT_MS = 1783691700000


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE_NAME):
        return

    # A semantic-version cutover revokes execution authority from signals that
    # still point at a retired event spec or a non-active candidate binding.
    # Preserve the row as provenance, but remove it from current readiness.
    conn.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME} AS signal
            SET status = 'superseded',
                freshness_state = 'expired',
                invalidated_at_ms = {MIGRATION_AT_MS},
                expires_at_ms = CASE
                    WHEN expires_at_ms IS NULL OR expires_at_ms > {MIGRATION_AT_MS}
                    THEN {MIGRATION_AT_MS}
                    ELSE expires_at_ms
                END
            WHERE signal.invalidated_at_ms IS NULL
              AND (
                NOT EXISTS (
                  SELECT 1
                  FROM brc_strategy_side_event_specs AS event_spec
                  WHERE event_spec.event_spec_id = signal.event_spec_id
                    AND event_spec.status = 'current'
                )
                OR NOT EXISTS (
                  SELECT 1
                  FROM brc_candidate_scope_event_bindings AS binding
                  WHERE binding.candidate_scope_id = signal.candidate_scope_id
                    AND binding.event_spec_id = signal.event_spec_id
                    AND binding.status = 'active'
                )
              )
            """
        )
    )
    _replace_unique_constraint(NEW_UNIQUE_COLUMNS)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(TABLE_NAME):
        return
    duplicate = conn.execute(
        sa.text(
            f"""
            SELECT 1
            FROM {TABLE_NAME}
            GROUP BY {', '.join(OLD_UNIQUE_COLUMNS)}
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "cannot downgrade migration 112 while multiple event-spec versions "
            "share one legacy live-signal identity"
        )
    _replace_unique_constraint(OLD_UNIQUE_COLUMNS)


def _replace_unique_constraint(columns: list[str]) -> None:
    conn = op.get_bind()
    existing = {
        constraint["name"]: list(constraint.get("column_names") or [])
        for constraint in sa.inspect(conn).get_unique_constraints(TABLE_NAME)
        if constraint.get("name")
    }.get(UNIQUE_NAME)
    if existing == columns:
        return
    if conn.dialect.name == "sqlite":
        with op.batch_alter_table(TABLE_NAME, recreate="always") as batch_op:
            if existing:
                batch_op.drop_constraint(UNIQUE_NAME, type_="unique")
            batch_op.create_unique_constraint(UNIQUE_NAME, columns)
        return
    if existing:
        op.drop_constraint(UNIQUE_NAME, TABLE_NAME, type_="unique")
    op.create_unique_constraint(UNIQUE_NAME, TABLE_NAME, columns)
