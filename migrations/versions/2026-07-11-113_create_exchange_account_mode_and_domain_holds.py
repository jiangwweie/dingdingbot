"""Create typed exchange-account mode current truth and domain holds.

Revision ID: 113
Revises: 112
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "113"
down_revision: Union[str, None] = "112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODE_TABLE = "brc_exchange_account_modes_current"
CAPABILITY_TABLE = "brc_runtime_capabilities_current"
HOLD_TABLE = "brc_ticket_bound_scope_freezes"
RUNTIME_SAFETY_TABLE = "brc_runtime_safety_state_snapshots"
LEGACY_UNIQUE = "uq_brc_scope_freeze_current"
ACTIVE_HOLD_INDEX = "uq_brc_domain_hold_active_source"


def upgrade() -> None:
    if not _has_table(CAPABILITY_TABLE):
        op.create_table(
            CAPABILITY_TABLE,
            sa.Column("capability_id", sa.String(128), primary_key=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("certification_ref", sa.String(256), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('disabled', 'enabled')",
                name="ck_brc_runtime_capability_status",
            ),
        )
        op.execute(
            sa.text(
                f"INSERT INTO {CAPABILITY_TABLE} "
                "(capability_id, status, certification_ref, updated_at_ms) "
                "VALUES ('ticket_lifecycle_durable_mutation', 'disabled', "
                "'migration-113:phase-one-fail-closed', 0)"
            )
        )
    if not _has_table(MODE_TABLE):
        op.create_table(
            MODE_TABLE,
            sa.Column("account_mode_current_id", sa.String(192), primary_key=True),
            sa.Column("account_id", sa.String(128), nullable=False),
            sa.Column("exchange_id", sa.String(128), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=True),
            sa.Column("position_mode", sa.String(32), nullable=True),
            sa.Column("dual_side_position", sa.Boolean(), nullable=True),
            sa.Column("position_mode_safe", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("fact_snapshot_id", sa.String(192), nullable=False),
            sa.Column("source_kind", sa.String(64), nullable=False),
            sa.Column("source_ref", sa.String(512), nullable=False),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("valid_until_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "position_mode IS NULL OR position_mode IN ('one_way', 'hedge')",
                name="ck_brc_exchange_account_mode_value",
            ),
            sa.CheckConstraint(
                "status IN ('current', 'stale', 'unknown')",
                name="ck_brc_exchange_account_mode_status",
            ),
            sa.CheckConstraint(
                "(position_mode_safe = false) OR "
                "(status = 'current' AND position_mode IS NOT NULL "
                "AND dual_side_position IS NOT NULL)",
                name="ck_brc_exchange_account_mode_safe_shape",
            ),
            sa.UniqueConstraint(
                "account_id",
                "exchange_id",
                name="uq_brc_exchange_account_mode_identity",
            ),
        )
        op.create_index(
            "idx_brc_exchange_account_mode_status",
            MODE_TABLE,
            ["status", "valid_until_ms"],
        )

    if _has_table(RUNTIME_SAFETY_TABLE):
        if not _has_column(
            RUNTIME_SAFETY_TABLE,
            "lifecycle_mutation_capability_ready",
        ):
            op.add_column(
                RUNTIME_SAFETY_TABLE,
                sa.Column(
                    "lifecycle_mutation_capability_ready",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                ),
            )
        if not _has_column(
            RUNTIME_SAFETY_TABLE,
            "lifecycle_mutation_capability_ref",
        ):
            op.add_column(
                RUNTIME_SAFETY_TABLE,
                sa.Column(
                    "lifecycle_mutation_capability_ref",
                    sa.String(256),
                    nullable=True,
                ),
            )
    if not _has_table(HOLD_TABLE):
        return
    additions = (
        ("account_id", sa.String(128), "legacy_unknown_account"),
        ("runtime_profile_id", sa.String(128), "legacy_unknown_profile"),
        ("exchange_id", sa.String(128), "legacy_unknown_exchange"),
        (
            "exchange_instrument_id",
            sa.String(192),
            "legacy_unknown_instrument",
        ),
        ("position_mode", sa.String(32), "unknown"),
        ("position_bucket", sa.String(16), "ANY"),
        ("netting_domain_key", sa.String(640), "legacy_unknown_domain"),
        ("source_ticket_id", sa.String(192), "legacy_unknown_ticket"),
    )
    for name, column_type, default in additions:
        if not _has_column(HOLD_TABLE, name):
            op.add_column(
                HOLD_TABLE,
                sa.Column(
                    name,
                    column_type,
                    nullable=False,
                    server_default=default,
                ),
            )

    _drop_legacy_hold_unique()
    if not _has_index(HOLD_TABLE, ACTIVE_HOLD_INDEX):
        where = sa.text("status = 'active'")
        op.create_index(
            ACTIVE_HOLD_INDEX,
            HOLD_TABLE,
            ["netting_domain_key", "source_kind", "source_id"],
            unique=True,
            postgresql_where=where,
            sqlite_where=where,
        )
    if not _has_index(HOLD_TABLE, "idx_brc_domain_hold_effective"):
        op.create_index(
            "idx_brc_domain_hold_effective",
            HOLD_TABLE,
            ["account_id", "exchange_instrument_id", "position_bucket", "status"],
        )


def downgrade() -> None:
    if _has_table(RUNTIME_SAFETY_TABLE):
        for name in (
            "lifecycle_mutation_capability_ref",
            "lifecycle_mutation_capability_ready",
        ):
            if _has_column(RUNTIME_SAFETY_TABLE, name):
                op.drop_column(RUNTIME_SAFETY_TABLE, name)
    if _has_table(HOLD_TABLE):
        for index_name in (
            "idx_brc_domain_hold_effective",
            ACTIVE_HOLD_INDEX,
        ):
            if _has_index(HOLD_TABLE, index_name):
                op.drop_index(index_name, table_name=HOLD_TABLE)
        _restore_legacy_hold_unique_if_possible()
        for name in (
            "source_ticket_id",
            "netting_domain_key",
            "position_bucket",
            "position_mode",
            "exchange_instrument_id",
            "exchange_id",
            "runtime_profile_id",
            "account_id",
        ):
            if _has_column(HOLD_TABLE, name):
                op.drop_column(HOLD_TABLE, name)
    if _has_table(MODE_TABLE):
        op.drop_table(MODE_TABLE)
    if _has_table(CAPABILITY_TABLE):
        op.drop_table(CAPABILITY_TABLE)


def _drop_legacy_hold_unique() -> None:
    uniques = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_unique_constraints(HOLD_TABLE)
    }
    if LEGACY_UNIQUE not in uniques:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(HOLD_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(LEGACY_UNIQUE, type_="unique")
        return
    op.drop_constraint(LEGACY_UNIQUE, HOLD_TABLE, type_="unique")


def _restore_legacy_hold_unique_if_possible() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            f"""
            SELECT 1
            FROM {HOLD_TABLE}
            GROUP BY strategy_group_id, symbol, side, status
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate:
        raise RuntimeError(
            "cannot downgrade migration 113 while multiple source-specific "
            "domain holds share one legacy StrategyGroup scope"
        )
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(HOLD_TABLE, recreate="always") as batch_op:
            batch_op.create_unique_constraint(
                LEGACY_UNIQUE,
                ["strategy_group_id", "symbol", "side", "status"],
            )
        return
    op.create_unique_constraint(
        LEGACY_UNIQUE,
        HOLD_TABLE,
        ["strategy_group_id", "symbol", "side", "status"],
    )


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _has_index(table_name: str, index_name: str) -> bool:
    return index_name in {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
