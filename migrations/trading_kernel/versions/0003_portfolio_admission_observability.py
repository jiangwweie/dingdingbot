"""Add portfolio-admission observability projections."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_portfolio_admission_observability"
down_revision: str | None = "0002_sor_v3_strategy_group_capacity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)


def upgrade() -> None:
    """Add the rising-edge Episode current projection."""

    _upgrade_portfolio_admission_policy_v4()

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
    _create_admission_decisions()


def _upgrade_portfolio_admission_policy_v4() -> None:
    """Extend the un-deployed 0003 head with current Policy v4 lineage."""

    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "family_ticket_limits",
            JSONB(),
            nullable=False,
            server_default=sa.text(
                "'{\"long_continuation\": 1, \"opening_range\": 2, \"rally_failure_short\": 1}'::jsonb"
            ),
        ),
    )
    op.alter_column(
        "brc_owner_policy_current",
        "max_strategy_group_concurrent_tickets",
        nullable=True,
        server_default=None,
    )
    for column_name in (
        "active_strategy_group_ticket_count_at_claim",
        "max_strategy_group_concurrent_tickets",
        "remaining_strategy_group_slots_at_claim",
    ):
        op.alter_column(
            "brc_capacity_claims",
            column_name,
            nullable=True,
            server_default=None,
        )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "directional_stop_risk_limit_fraction",
            sa.Numeric(36, 18),
            nullable=False,
            server_default="0.04",
        ),
    )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "min_materialization_ratio",
            sa.Numeric(36, 18),
            nullable=False,
            server_default="0.50",
        ),
    )
    for table_name in ("brc_capacity_claims", "brc_trade_tickets"):
        op.add_column(
            table_name,
            sa.Column("exposure_family", SHORT_TEXT, nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("active_family_ticket_count_at_claim", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("family_ticket_limit", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("directional_risk_at_stop_at_claim", sa.Numeric(36, 18), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("directional_stop_risk_limit_fraction", sa.Numeric(36, 18), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("min_materialization_ratio", sa.Numeric(36, 18), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("minimum_stop_risk_budget", sa.Numeric(36, 18), nullable=True),
        )
    op.create_index(
        "ix_brc_trade_tickets_active_family",
        "brc_trade_tickets",
        ["venue_id", "account_id", "exposure_family", "terminal_at_ms"],
    )
    op.create_index(
        "ix_brc_trade_tickets_active_directional_risk",
        "brc_trade_tickets",
        ["venue_id", "account_id", "position_side", "terminal_at_ms"],
    )


def _create_admission_decisions() -> None:
    op.create_table(
        "brc_admission_decisions",
        sa.Column("admission_decision_id", ID, nullable=False),
        sa.Column("signal_event_id", ID, nullable=False),
        sa.Column("exposure_episode_id", ID, nullable=False),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("universe_version_id", ID, nullable=False),
        sa.Column("universe_semantic_digest", sa.String(512), nullable=False),
        sa.Column("runtime_profile_id", ID, nullable=False),
        sa.Column("runtime_scope_id", ID, nullable=False),
        sa.Column("runtime_scope_version", sa.BigInteger(), nullable=False),
        sa.Column("owner_policy_id", ID, nullable=False),
        sa.Column("owner_policy_version", sa.BigInteger(), nullable=False),
        sa.Column("venue_id", ID, nullable=False),
        sa.Column("account_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("exposure_family", SHORT_TEXT, nullable=False),
        sa.Column("candidate_rank", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("candidate_set_digest", sa.String(512), nullable=False),
        sa.Column("candidate_set_summary", JSONB(), nullable=False),
        sa.Column("portfolio_usage", JSONB(), nullable=False),
        sa.Column("decision_status", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", sa.String(512), nullable=True),
        sa.Column("binding_constraint", sa.String(512), nullable=True),
        sa.Column("capacity_claim_id", ID, nullable=True),
        sa.Column("ticket_id", ID, nullable=True),
        sa.Column(
            "entry_admission_snapshot_digest",
            sa.String(512),
            nullable=True,
        ),
        sa.Column("decision_digest", sa.String(512), nullable=False),
        sa.Column("decided_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "admission_decision_id",
            name="pk_brc_admission_decisions",
        ),
        sa.UniqueConstraint(
            "signal_event_id",
            name="uq_brc_admission_decisions_signal",
        ),
        sa.ForeignKeyConstraint(
            ["signal_event_id"],
            ["brc_signal_events.signal_event_id"],
            name="fk_brc_admission_signal",
        ),
        sa.ForeignKeyConstraint(
            ["capacity_claim_id"],
            ["brc_capacity_claims.capacity_claim_id"],
            name="fk_brc_admission_claim",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["brc_trade_tickets.ticket_id"],
            name="fk_brc_admission_ticket",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_admission_side",
        ),
        sa.CheckConstraint(
            "exposure_family IN ('long_continuation', 'opening_range', "
            "'rally_failure_short')",
            name="ck_brc_admission_family",
        ),
        sa.CheckConstraint(
            "candidate_rank > 0 AND candidate_count BETWEEN 1 AND 64 "
            "AND candidate_rank <= candidate_count",
            name="ck_brc_admission_candidate",
        ),
        sa.CheckConstraint(
            "decision_status IN ('admitted', 'rejected')",
            name="ck_brc_admission_status",
        ),
        sa.CheckConstraint(
            "(decision_status = 'admitted' AND first_blocker IS NULL "
            "AND capacity_claim_id IS NOT NULL AND ticket_id IS NOT NULL "
            "AND entry_admission_snapshot_digest IS NOT NULL) OR "
            "(decision_status = 'rejected' AND first_blocker IS NOT NULL "
            "AND capacity_claim_id IS NULL AND ticket_id IS NULL)",
            name="ck_brc_admission_shape",
        ),
        sa.CheckConstraint(
            "candidate_set_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND decision_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND (entry_admission_snapshot_digest IS NULL OR "
            "entry_admission_snapshot_digest ~ '^sha256:[0-9a-f]{64}$')",
            name="ck_brc_admission_digest",
        ),
    )
    op.create_index(
        "ix_brc_admission_decisions_decided_at_ms",
        "brc_admission_decisions",
        ["decided_at_ms"],
    )
    op.create_index(
        "ix_brc_admission_decisions_first_blocker_decided_at_ms",
        "brc_admission_decisions",
        ["first_blocker", "decided_at_ms"],
    )
    op.create_index(
        "ix_brc_admission_decisions_strategy_event_decided",
        "brc_admission_decisions",
        ["strategy_group_id", "event_spec_id", "decided_at_ms"],
    )


def downgrade() -> None:
    raise RuntimeError("0003 downgrade is forbidden; use fix-forward")
