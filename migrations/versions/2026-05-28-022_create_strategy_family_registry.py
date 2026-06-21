"""Create BRC strategy family registry metadata

Revision ID: 022
Revises: 021
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_strategy_family_registry"):
        op.create_table(
            "brc_strategy_family_registry",
            sa.Column("family_id", sa.String(length=128), nullable=False),
            sa.Column("version_id", sa.String(length=128), nullable=False),
            sa.Column("family_name", sa.String(length=256), nullable=False),
            sa.Column("family_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("hypothesis", sa.Text(), nullable=False),
            sa.Column("alpha_claim", sa.Boolean(), nullable=False),
            sa.Column("carrier_validation", sa.Boolean(), nullable=False),
            sa.Column("supported_symbols", _jsonb_type(), nullable=False),
            sa.Column("primary_timeframe", sa.String(length=32), nullable=False),
            sa.Column("context_timeframes", _jsonb_type(), nullable=False),
            sa.Column("input_requirements", _jsonb_type(), nullable=False),
            sa.Column("allowed_signal_types", _jsonb_type(), nullable=False),
            sa.Column("reason_code_taxonomy", _jsonb_type(), nullable=False),
            sa.Column("review_metrics", _jsonb_type(), nullable=False),
            sa.Column("known_failure_modes", _jsonb_type(), nullable=False),
            sa.Column("evidence_requirements", _jsonb_type(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('registered_hypothesis_only', 'active_observation_candidate', "
                "'live_readonly_observation', 'parked', 'retired')",
                name="ck_brc_strategy_family_registry_status",
            ),
            sa.CheckConstraint(
                "family_type IN ('trend_following', 'volatility_breakout', "
                "'mean_reversion', 'pullback_continuation', 'event_driven_discretionary', "
                "'funding_oi_dislocation', 'unknown')",
                name="ck_brc_strategy_family_registry_type",
            ),
            sa.PrimaryKeyConstraint("family_id", "version_id"),
        )
    _create_index_if_missing(
        "idx_brc_strategy_family_registry_family",
        "brc_strategy_family_registry",
        ["family_id"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_family_registry_status",
        "brc_strategy_family_registry",
        ["status", "updated_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_family_registry_type",
        "brc_strategy_family_registry",
        ["family_type"],
    )

    if not _has_table("brc_strategy_family_playbooks"):
        op.create_table(
            "brc_strategy_family_playbooks",
            sa.Column("playbook_id", sa.String(length=128), nullable=False),
            sa.Column("family_id", sa.String(length=128), nullable=False),
            sa.Column("version_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_name", sa.String(length=256), nullable=False),
            sa.Column("playbook_status", sa.String(length=64), nullable=False),
            sa.Column("symbol_universe", _jsonb_type(), nullable=False),
            sa.Column("primary_timeframe", sa.String(length=32), nullable=False),
            sa.Column("context_timeframes", _jsonb_type(), nullable=False),
            sa.Column("signal_contract_version", sa.String(length=128), nullable=False),
            sa.Column("allowed_signal_types", _jsonb_type(), nullable=False),
            sa.Column("review_windows", _jsonb_type(), nullable=False),
            sa.Column("review_metrics", _jsonb_type(), nullable=False),
            sa.Column("input_requirements", _jsonb_type(), nullable=False),
            sa.Column("evidence_requirements", _jsonb_type(), nullable=False),
            sa.Column("parameter_profile", _jsonb_type(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "playbook_status IN ('registered_hypothesis_only', 'active_observation_candidate', "
                "'live_readonly_observation', 'parked', 'retired')",
                name="ck_brc_strategy_family_playbooks_status",
            ),
            sa.PrimaryKeyConstraint("playbook_id"),
        )
    _create_index_if_missing(
        "idx_brc_strategy_family_playbooks_family",
        "brc_strategy_family_playbooks",
        ["family_id", "version_id"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_family_playbooks_status",
        "brc_strategy_family_playbooks",
        ["playbook_status", "updated_at_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_strategy_family_playbooks_status",
        "idx_brc_strategy_family_playbooks_family",
    ]:
        _drop_index_if_exists(index_name, "brc_strategy_family_playbooks")
    if _has_table("brc_strategy_family_playbooks"):
        op.drop_table("brc_strategy_family_playbooks")

    for index_name in [
        "idx_brc_strategy_family_registry_type",
        "idx_brc_strategy_family_registry_status",
        "idx_brc_strategy_family_registry_family",
    ]:
        _drop_index_if_exists(index_name, "brc_strategy_family_registry")
    if _has_table("brc_strategy_family_registry"):
        op.drop_table("brc_strategy_family_registry")
