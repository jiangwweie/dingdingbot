"""Create protection price plans table

Revision ID: 037
Revises: 036
Create Date: 2026-06-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb() -> sa.types.TypeEngine:
    return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("brc_protection_price_plans"):
        return
    op.create_table(
        "brc_protection_price_plans",
        sa.Column("plan_id", sa.String(length=128), primary_key=True),
        sa.Column("authorization_id", sa.String(length=128), nullable=False),
        sa.Column("carrier_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("planner_version", sa.String(length=128), nullable=False),
        sa.Column("price_source_type", sa.String(length=128), nullable=False),
        sa.Column("reference_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("fill_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("quantity", sa.Numeric(36, 18), nullable=False),
        sa.Column("tp_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("sl_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("tp_quantity", sa.Numeric(36, 18), nullable=True),
        sa.Column("sl_quantity", sa.Numeric(36, 18), nullable=True),
        sa.Column("tick_size", sa.Numeric(36, 18), nullable=True),
        sa.Column("amount_step", sa.Numeric(36, 18), nullable=True),
        sa.Column("min_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("min_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("rounding", _jsonb(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("filters", _jsonb(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("blockers", _jsonb(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("computed_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["brc_bounded_live_trial_authorizations.authorization_id"],
            name="fk_brc_protection_price_plans_authorization_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_protection_price_plans_side"),
        sa.CheckConstraint(
            "phase IN ('pre_entry_reference', 'post_entry_fill')",
            name="ck_brc_protection_price_plans_phase",
        ),
        sa.CheckConstraint(
            "status IN ('valid', 'blocked')",
            name="ck_brc_protection_price_plans_status",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_brc_protection_price_plans_quantity_positive"),
    )
    op.create_index(
        "idx_brc_protection_price_plans_auth_phase_time",
        "brc_protection_price_plans",
        ["authorization_id", "phase", "computed_at_ms"],
    )
    op.create_index(
        "idx_brc_protection_price_plans_carrier_time",
        "brc_protection_price_plans",
        ["carrier_id", "computed_at_ms"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("brc_protection_price_plans"):
        return
    op.drop_index(
        "idx_brc_protection_price_plans_carrier_time",
        table_name="brc_protection_price_plans",
    )
    op.drop_index(
        "idx_brc_protection_price_plans_auth_phase_time",
        table_name="brc_protection_price_plans",
    )
    op.drop_table("brc_protection_price_plans")
