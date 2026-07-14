"""Harden live signal event-time authority.

Revision ID: 087
Revises: 086
Create Date: 2026-07-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "087"
down_revision: Union[str, None] = "086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_live_signal_events"
UNIQUE_NAME = "uq_brc_live_signal_identity"
UNIQUE_COLUMNS = [
    "strategy_group_id",
    "symbol",
    "side",
    "detector_key",
    "signal_type",
    "event_time_ms",
]
CHECKS = {
    "ck_brc_live_signal_source_kind": (
        "source_kind IN ('live_market', 'replay', 'historical', 'synthetic', 'unit_test')"
    ),
    "ck_brc_live_signal_event_time": (
        "event_time_ms = trigger_candle_close_time_ms"
    ),
    "ck_brc_live_signal_no_generated_at_event_time": (
        "created_at_ms <> event_time_ms AND created_at_ms >= event_time_ms"
    ),
    "ck_brc_live_signal_fresh_source": (
        "NOT (source_kind <> 'live_market' AND status = 'facts_validated' "
        "AND freshness_state = 'fresh')"
    ),
}
NEW_COLUMNS = {
    "source_kind": sa.String(64),
    "event_time_ms": sa.BIGINT(),
    "trigger_candle_close_time_ms": sa.BIGINT(),
}


def _inspector() -> sa.engine.reflection.Inspector:
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table(TABLE_NAME)


def _is_sqlite() -> bool:
    return str(op.get_bind().dialect.name) == "sqlite"


def _columns() -> dict[str, dict[str, object]]:
    return {column["name"]: column for column in _inspector().get_columns(TABLE_NAME)}


def _checks() -> set[str]:
    return {
        constraint["name"]
        for constraint in _inspector().get_check_constraints(TABLE_NAME)
        if constraint.get("name")
    }


def _unique_constraints() -> dict[str, list[str]]:
    return {
        constraint["name"]: list(constraint.get("column_names") or [])
        for constraint in _inspector().get_unique_constraints(TABLE_NAME)
        if constraint.get("name")
    }


def _add_missing_columns() -> None:
    existing = _columns()
    for column_name, column_type in NEW_COLUMNS.items():
        if column_name in existing:
            continue
        op.add_column(TABLE_NAME, sa.Column(column_name, column_type, nullable=True))


def _backfill_existing_rows() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME}
            SET source_kind = 'historical'
            WHERE source_kind IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME}
            SET event_time_ms = CASE
                WHEN created_at_ms IS NOT NULL
                 AND observed_at_ms IS NOT NULL
                 AND created_at_ms > observed_at_ms
                THEN observed_at_ms
                WHEN created_at_ms IS NOT NULL
                THEN created_at_ms - 1
                ELSE observed_at_ms
            END
            WHERE event_time_ms IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME}
            SET trigger_candle_close_time_ms = event_time_ms
            WHERE trigger_candle_close_time_ms IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE {TABLE_NAME}
            SET status = 'stale',
                freshness_state = 'stale',
                expires_at_ms = NULL
            WHERE source_kind <> 'live_market'
              AND status = 'facts_validated'
              AND freshness_state = 'fresh'
            """
        )
    )


def _unique_columns_match() -> bool:
    return _unique_constraints().get(UNIQUE_NAME) == UNIQUE_COLUMNS


def _needs_rebuild_or_constraints() -> bool:
    columns = _columns()
    return (
        any(columns[column_name].get("nullable") for column_name in NEW_COLUMNS)
        or any(check_name not in _checks() for check_name in CHECKS)
        or not _unique_columns_match()
    )


def _apply_sqlite_constraints() -> None:
    existing_checks = _checks()
    existing_unique = _unique_constraints().get(UNIQUE_NAME)
    with op.batch_alter_table(TABLE_NAME, recreate="always") as batch_op:
        if existing_unique and existing_unique != UNIQUE_COLUMNS:
            batch_op.drop_constraint(UNIQUE_NAME, type_="unique")
        for column_name, column_type in NEW_COLUMNS.items():
            batch_op.alter_column(
                column_name,
                existing_type=column_type,
                existing_nullable=True,
                nullable=False,
            )
        if existing_unique != UNIQUE_COLUMNS:
            batch_op.create_unique_constraint(UNIQUE_NAME, UNIQUE_COLUMNS)
        for check_name, condition in CHECKS.items():
            if check_name not in existing_checks:
                batch_op.create_check_constraint(check_name, condition)


def _apply_postgres_constraints() -> None:
    columns = _columns()
    for column_name, column_type in NEW_COLUMNS.items():
        if columns[column_name].get("nullable"):
            op.alter_column(
                TABLE_NAME,
                column_name,
                existing_type=column_type,
                nullable=False,
            )
    checks = _checks()
    for check_name, condition in CHECKS.items():
        if check_name not in checks:
            op.create_check_constraint(check_name, TABLE_NAME, condition)
    existing_unique = _unique_constraints().get(UNIQUE_NAME)
    if existing_unique != UNIQUE_COLUMNS:
        if existing_unique:
            op.drop_constraint(UNIQUE_NAME, TABLE_NAME, type_="unique")
        op.create_unique_constraint(UNIQUE_NAME, TABLE_NAME, UNIQUE_COLUMNS)


def upgrade() -> None:
    if not _has_table():
        return
    _add_missing_columns()
    _backfill_existing_rows()
    if not _needs_rebuild_or_constraints():
        return
    if _is_sqlite():
        _apply_sqlite_constraints()
        return
    _apply_postgres_constraints()


def downgrade() -> None:
    # Revision 086 now defines the same live-signal authority shape. Downgrading
    # this follow-up revision must not delete the baseline safety columns.
    return
