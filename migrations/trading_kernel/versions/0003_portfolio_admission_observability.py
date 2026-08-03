"""Add portfolio-admission observability projections."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_portfolio_admission_observability"
down_revision: str | None = "0002_sor_v3_strategy_group_capacity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)


def upgrade() -> None:
    """Add the rising-edge Episode current projection."""

    op.create_table(
        "brc_exposure_episode_current",
        sa.Column("episode_domain_key", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("episode_policy", SHORT_TEXT, nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("exposure_episode_id", ID, nullable=True),
        sa.Column("triggered_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("rearmed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "episode_domain_key",
            name="pk_brc_exposure_episode_current",
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
            name="fk_brc_episode_event_spec",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instruments.exchange_instrument_id"],
            name="fk_brc_episode_instrument",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_episode_position_side",
        ),
        sa.CheckConstraint(
            "episode_policy = 'rising_edge'",
            name="ck_brc_episode_policy",
        ),
        sa.CheckConstraint(
            "state IN ('armed', 'triggered')",
            name="ck_brc_episode_state",
        ),
        sa.CheckConstraint(
            "projection_version > 0 AND last_observed_at_ms > 0",
            name="ck_brc_episode_version_time",
        ),
        sa.CheckConstraint(
            "rearmed_at_ms IS NULL OR rearmed_at_ms > 0",
            name="ck_brc_episode_rearmed_time",
        ),
        sa.CheckConstraint(
            "(state = 'triggered' AND exposure_episode_id IS NOT NULL "
            "AND triggered_at_ms IS NOT NULL AND triggered_at_ms > 0) OR "
            "(state = 'armed' AND exposure_episode_id IS NULL "
            "AND triggered_at_ms IS NULL)",
            name="ck_brc_episode_state_shape",
        ),
    )


def downgrade() -> None:
    raise RuntimeError("0003 downgrade is forbidden; use fix-forward")
