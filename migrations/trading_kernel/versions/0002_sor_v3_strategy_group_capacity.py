"""Add SOR v3 lineage, frozen lifecycle policy, and StrategyGroup capacity."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sor_v3_strategy_group_capacity"
down_revision: str | None = "0001_trading_kernel_baseline_v4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    """Upgrade an exact v4 database without rewriting historical lineage."""

    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    _upgrade_event_identity()
    _upgrade_signal_episode_and_fact_roles()
    _upgrade_owner_policy()
    _upgrade_capacity_claims()
    _upgrade_trade_tickets()


def _upgrade_event_identity() -> None:
    op.drop_constraint(
        "uq_brc_event_specs_event_id",
        "brc_event_specs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_brc_event_specs_strategy_version_id_event_id",
        "brc_event_specs",
        ("strategy_version_id", "event_id"),
    )


def _upgrade_signal_episode_and_fact_roles() -> None:
    op.add_column(
        "brc_signal_events",
        sa.Column("exposure_episode_id", ID, nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE brc_signal_events
               SET exposure_episode_id = 'legacy:signal:' || signal_event_id
            """
        )
    )
    op.alter_column(
        "brc_signal_events",
        "exposure_episode_id",
        existing_type=ID,
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_brc_signal_events_exposure_episode_id",
        "brc_signal_events",
        ("exposure_episode_id",),
    )
    op.drop_constraint(
        "ck_brc_signal_fact_snapshots_role_valid",
        "brc_signal_fact_snapshots",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_signal_fact_snapshots_role_valid",
        "brc_signal_fact_snapshots",
        "role IN ('condition', 'protection_reference', "
        "'identity_reference', 'lifecycle_reference', 'disable')",
    )


def _upgrade_owner_policy() -> None:
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "max_strategy_group_concurrent_tickets",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE brc_owner_policy_current
               SET max_strategy_group_concurrent_tickets = 2
            """
        )
    )
    op.alter_column(
        "brc_owner_policy_current",
        "max_strategy_group_concurrent_tickets",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_brc_owner_policy_current_max_strategy_group_concurre_b80b",
        "brc_owner_policy_current",
        "max_strategy_group_concurrent_tickets > 0",
    )


def _upgrade_capacity_claims() -> None:
    op.add_column(
        "brc_capacity_claims",
        sa.Column("exit_policy_id", ID, nullable=True),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column("exit_policy_semantic_hash", LONG_TEXT, nullable=True),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column(
            "active_strategy_group_ticket_count_at_claim",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column(
            "max_strategy_group_concurrent_tickets",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column(
            "remaining_strategy_group_slots_at_claim",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column("pre_tp1_reclaim_price", MONEY, nullable=True),
    )
    op.add_column(
        "brc_capacity_claims",
        sa.Column("exposure_session_end_ms", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE brc_capacity_claims AS claim
               SET exit_policy_id = event.exit_policy_id,
                   exit_policy_semantic_hash = policy.semantic_hash
              FROM brc_event_specs AS event
              JOIN brc_exit_policies AS policy
                ON policy.exit_policy_id = event.exit_policy_id
             WHERE event.event_spec_id = claim.event_spec_id
            """
        )
    )
    _backfill_strategy_group_counts()
    for column_name, column_type in (
        ("exit_policy_id", ID),
        ("exit_policy_semantic_hash", LONG_TEXT),
        ("active_strategy_group_ticket_count_at_claim", sa.Integer()),
        ("max_strategy_group_concurrent_tickets", sa.Integer()),
        ("remaining_strategy_group_slots_at_claim", sa.Integer()),
    ):
        op.alter_column(
            "brc_capacity_claims",
            column_name,
            existing_type=column_type,
            nullable=False,
        )


def _backfill_strategy_group_counts() -> None:
    op.execute(
        sa.text(
            """
            WITH historical_counts AS (
                SELECT claim.capacity_claim_id,
                       count(ticket.ticket_id)::integer AS active_count
                  FROM brc_capacity_claims AS claim
             LEFT JOIN brc_trade_tickets AS ticket
                    ON ticket.venue_id = claim.venue_id
                   AND ticket.account_id = claim.account_id
                   AND ticket.strategy_group_id = claim.strategy_group_id
                   AND (
                        ticket.created_at_ms < claim.created_at_ms
                        OR (
                            ticket.created_at_ms = claim.created_at_ms
                            AND ticket.ticket_id < claim.ticket_id
                        )
                   )
                   AND (
                        ticket.terminal_at_ms IS NULL
                        OR ticket.terminal_at_ms > claim.created_at_ms
                   )
              GROUP BY claim.capacity_claim_id
            )
            UPDATE brc_capacity_claims AS claim
               SET active_strategy_group_ticket_count_at_claim = counts.active_count,
                   max_strategy_group_concurrent_tickets = 2,
                   remaining_strategy_group_slots_at_claim = 2 - counts.active_count
              FROM historical_counts AS counts
             WHERE counts.capacity_claim_id = claim.capacity_claim_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM brc_capacity_claims
                     WHERE active_strategy_group_ticket_count_at_claim > 2
                        OR remaining_strategy_group_slots_at_claim < 0
                ) THEN
                    RAISE EXCEPTION
                        'v4 history exceeds approved StrategyGroup capacity backfill';
                END IF;
            END
            $$;
            """
        )
    )


def _upgrade_trade_tickets() -> None:
    op.add_column(
        "brc_trade_tickets",
        sa.Column("exit_policy_id", ID, nullable=True),
    )
    op.add_column(
        "brc_trade_tickets",
        sa.Column("exit_policy_semantic_hash", LONG_TEXT, nullable=True),
    )
    op.add_column(
        "brc_trade_tickets",
        sa.Column("pre_tp1_reclaim_price", MONEY, nullable=True),
    )
    op.add_column(
        "brc_trade_tickets",
        sa.Column("exposure_session_end_ms", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE brc_trade_tickets AS ticket
               SET exit_policy_id = event.exit_policy_id,
                   exit_policy_semantic_hash = policy.semantic_hash
              FROM brc_event_specs AS event
              JOIN brc_exit_policies AS policy
                ON policy.exit_policy_id = event.exit_policy_id
             WHERE event.event_spec_id = ticket.event_spec_id
            """
        )
    )
    op.alter_column(
        "brc_trade_tickets",
        "exit_policy_id",
        existing_type=ID,
        nullable=False,
    )
    op.alter_column(
        "brc_trade_tickets",
        "exit_policy_semantic_hash",
        existing_type=LONG_TEXT,
        nullable=False,
    )
    op.create_index(
        "ix_brc_trade_tickets_active_strategy_group",
        "brc_trade_tickets",
        ("venue_id", "account_id", "strategy_group_id", "terminal_at_ms"),
        unique=False,
    )


def downgrade() -> None:
    """Return to v4 only before any v3 Strategy Registry row exists."""

    bind = op.get_bind()
    has_v3_rows = bool(
        bind.execute(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM brc_strategy_versions
                     WHERE version >= 3
                )
                """
            )
        ).scalar_one()
    )
    if has_v3_rows:
        raise RuntimeError(
            "0002 downgrade refused after v3 runtime rows; use fix-forward"
        )

    op.drop_index(
        "ix_brc_trade_tickets_active_strategy_group",
        table_name="brc_trade_tickets",
    )
    for column_name in (
        "exposure_session_end_ms",
        "pre_tp1_reclaim_price",
        "exit_policy_semantic_hash",
        "exit_policy_id",
    ):
        op.drop_column("brc_trade_tickets", column_name)

    for column_name in (
        "exposure_session_end_ms",
        "pre_tp1_reclaim_price",
        "remaining_strategy_group_slots_at_claim",
        "max_strategy_group_concurrent_tickets",
        "active_strategy_group_ticket_count_at_claim",
        "exit_policy_semantic_hash",
        "exit_policy_id",
    ):
        op.drop_column("brc_capacity_claims", column_name)

    op.drop_constraint(
        "ck_brc_owner_policy_current_max_strategy_group_concurre_b80b",
        "brc_owner_policy_current",
        type_="check",
    )
    op.drop_column(
        "brc_owner_policy_current",
        "max_strategy_group_concurrent_tickets",
    )

    op.drop_constraint(
        "ck_brc_signal_fact_snapshots_role_valid",
        "brc_signal_fact_snapshots",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_signal_fact_snapshots_role_valid",
        "brc_signal_fact_snapshots",
        "role IN ('condition', 'protection_reference', 'disable')",
    )
    op.drop_constraint(
        "uq_brc_signal_events_exposure_episode_id",
        "brc_signal_events",
        type_="unique",
    )
    op.drop_column("brc_signal_events", "exposure_episode_id")

    op.drop_constraint(
        "uq_brc_event_specs_strategy_version_id_event_id",
        "brc_event_specs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_brc_event_specs_event_id",
        "brc_event_specs",
        ("event_id",),
    )
