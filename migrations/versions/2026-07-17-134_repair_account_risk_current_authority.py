"""Add physical capacity-fact references for account-risk authority.

Revision ID: 134
Revises: 133
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "134"
down_revision: Union[str, None] = "133"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    _make_ticket_legacy_account_fact_nullable(bind)
    _add_column_if_missing(
        bind,
        "brc_action_time_invocations",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    _add_column_if_missing(
        bind,
        "brc_action_time_lane_inputs",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    _add_column_if_missing(
        bind,
        "brc_action_time_tickets",
        "account_capacity_base_fact_snapshot_id",
        sa.String(256),
    )
    for column_name, column_type in (
        ("trusted_fact_refs_schema_version", sa.String(64)),
        ("account_capacity_fact_surface", sa.String(64)),
        ("account_capacity_fact_snapshot_id", sa.String(256)),
    ):
        _add_column_if_missing(
            bind,
            "brc_runtime_safety_state_snapshots",
            column_name,
            column_type,
        )
    if sa.inspect(bind).has_table("brc_runtime_safety_state_snapshots"):
        bind.execute(
            sa.text(
                "UPDATE brc_runtime_safety_state_snapshots "
                "SET trusted_fact_refs_schema_version = "
                "'runtime_safety_trusted_refs.v1' "
                "WHERE trusted_fact_refs_schema_version IS NULL"
            )
        )
    _create_index_if_missing(
        bind,
        "brc_action_time_invocations",
        "idx_brc_invocation_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_action_time_lane_inputs",
        "idx_brc_lane_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_action_time_tickets",
        "idx_brc_ticket_capacity_base_fact",
        ["account_capacity_base_fact_snapshot_id"],
    )
    _create_index_if_missing(
        bind,
        "brc_runtime_safety_state_snapshots",
        "idx_brc_runtime_safety_capacity_fact",
        ["account_capacity_fact_surface", "account_capacity_fact_snapshot_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_no_v2_history(bind)
    for table_name, index_name in (
        ("brc_action_time_invocations", "idx_brc_invocation_capacity_base_fact"),
        ("brc_action_time_lane_inputs", "idx_brc_lane_capacity_base_fact"),
        ("brc_action_time_tickets", "idx_brc_ticket_capacity_base_fact"),
        ("brc_runtime_safety_state_snapshots", "idx_brc_runtime_safety_capacity_fact"),
    ):
        if sa.inspect(bind).has_table(table_name):
            bind.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))


def _assert_no_v2_history(bind: sa.Connection) -> None:
    checks = (
        (
            "brc_action_time_tickets",
            "ticket_hash_schema_version",
            "action_time_ticket_hash.v2",
        ),
        (
            "brc_runtime_safety_state_snapshots",
            "trusted_fact_refs_schema_version",
            "runtime_safety_trusted_refs.v2",
        ),
    )
    for table_name, column_name, v2_value in checks:
        if not sa.inspect(bind).has_table(table_name):
            continue
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        if column_name not in columns:
            continue
        count = bind.execute(
            sa.text(
                f"SELECT count(*) FROM {table_name} "
                f"WHERE {column_name} = :v2_value"
            ),
            {"v2_value": v2_value},
        ).scalar_one()
        if int(count or 0):
            raise RuntimeError("capacity_fact_history_not_legacy_compatible")


def _add_column_if_missing(
    bind: sa.Connection,
    table_name: str,
    column_name: str,
    column_type: sa.types.TypeEngine[object],
) -> None:
    if not sa.inspect(bind).has_table(table_name):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
    if column_name not in columns:
        op.add_column(table_name, sa.Column(column_name, column_type, nullable=True))


def _make_ticket_legacy_account_fact_nullable(bind: sa.Connection) -> None:
    table_name = "brc_action_time_tickets"
    if not sa.inspect(bind).has_table(table_name):
        return
    columns = {
        column["name"]: column
        for column in sa.inspect(bind).get_columns(table_name)
    }
    column = columns.get("account_safe_fact_snapshot_id")
    if column is None or column.get("nullable") is True:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(
                "account_safe_fact_snapshot_id",
                existing_type=column["type"],
                nullable=True,
            )
    else:
        op.alter_column(
            table_name,
            "account_safe_fact_snapshot_id",
            existing_type=column["type"],
            nullable=True,
        )


def _create_index_if_missing(
    bind: sa.Connection,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    if not sa.inspect(bind).has_table(table_name):
        return
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)
