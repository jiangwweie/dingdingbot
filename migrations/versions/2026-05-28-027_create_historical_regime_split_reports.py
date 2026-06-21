"""Create BRC historical regime split comparison reports

Revision ID: 027
Revises: 026
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_historical_regime_split_reports"):
        op.create_table(
            "brc_historical_regime_split_reports",
            sa.Column("comparison_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("child_run_ids", _jsonb_type(), nullable=False),
            sa.Column("weighted_owner_verdict", sa.String(length=64), nullable=False),
            sa.Column("report_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "weighted_owner_verdict IN ('continue', 'park', 'needs_refinement', 'regime_dependent_continue')",
                name="ck_brc_hist_regime_split_reports_verdict",
            ),
            sa.PrimaryKeyConstraint("comparison_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_regime_split_reports_strategy",
        "brc_historical_regime_split_reports",
        ["strategy_family_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_regime_split_reports_verdict",
        "brc_historical_regime_split_reports",
        ["weighted_owner_verdict"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_hist_regime_split_reports_verdict",
        "idx_brc_hist_regime_split_reports_strategy",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_regime_split_reports")
    if _has_table("brc_historical_regime_split_reports"):
        op.drop_table("brc_historical_regime_split_reports")
