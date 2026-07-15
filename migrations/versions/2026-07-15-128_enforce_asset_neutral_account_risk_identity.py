"""Enforce asset-neutral identity only after historical backfill is complete.

Revision ID: 128
Revises: 127
Create Date: 2026-07-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "128"
down_revision: Union[str, None] = "127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTIVE_CLAIM_REQUIRED_COLUMNS = (
    "ticket_id",
    "exchange_instrument_id",
    "exposure_episode_id",
    "action_time_invocation_id",
    "asset_class",
    "instrument_type",
    "settlement_asset",
    "margin_asset",
    "instrument_rule_snapshot_id",
    "instrument_rule_schema_version",
    "pricing_source_fact_snapshot_id",
    "account_source_fact_snapshot_id",
    "account_fact_schema_version",
    "primary_risk_cluster_id",
    "cluster_membership_snapshot_id",
    "capacity_claim_schema_version",
    "capacity_claim_hash",
    "reservation_idempotency_key",
    "account_risk_policy_version",
    "account_risk_policy_event_id",
    "allowed_risk_budget",
    "margin_accounting_state",
    "account_capacity_projection_version",
)


def upgrade() -> None:
    bind = op.get_bind()
    _assert_current_rows_are_complete(bind)
    _replace_candidate_scope_active_identity_index(bind)
    _create_hot_path_indexes(bind)
    _add_lineage_constraints(bind)
    _add_postgresql_current_row_checks(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for index_name in (
        "idx_brc_exchange_command_nonterminal_evidence",
        "idx_brc_account_exposure_current_hot_path",
        "idx_brc_budget_reservation_effective_hot_path",
        "uq_brc_budget_reservation_invocation",
        "uq_brc_budget_reservation_idempotency",
        "uq_brc_risk_cluster_membership_primary_current",
        "uq_brc_instrument_rule_snapshot_current",
        "uq_brc_candidate_scope_active_instrument_timeframe",
    ):
        bind.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
    if _has_table(bind, "brc_strategy_group_candidate_scope"):
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_candidate_scope_active
                ON brc_strategy_group_candidate_scope (strategy_group_id, symbol, side)
                WHERE status = 'active'
                """
            )
        )


def _assert_current_rows_are_complete(bind: sa.Connection) -> None:
    _assert_no_incomplete_active_claim(bind)
    _assert_active_claim_ticket_lineage(bind)
    _assert_no_incomplete_active_candidate_scope(bind)
    _assert_no_incomplete_current_exposure(bind)


def _assert_no_incomplete_active_claim(bind: sa.Connection) -> None:
    if "brc_budget_reservations" not in _tables(bind):
        return
    columns = _columns(bind, "brc_budget_reservations")
    if not set(_ACTIVE_CLAIM_REQUIRED_COLUMNS) <= columns:
        raise RuntimeError("asset_neutral_active_claim_unresolved:schema_columns_missing")
    missing_predicate = " OR ".join(
        f"{column_name} IS NULL OR trim(CAST({column_name} AS TEXT)) = ''"
        for column_name in _ACTIVE_CLAIM_REQUIRED_COLUMNS
        if column_name
        not in {
            "capacity_claim_hash",
        }
    )
    missing_predicate += " OR capacity_claim_hash IS NULL OR trim(capacity_claim_hash) = ''"
    count = bind.execute(
        sa.text(
            f"""
            SELECT count(*)
            FROM brc_budget_reservations
            WHERE status IN ('active', 'consumed')
              AND ({missing_predicate})
            """
        )
    ).scalar_one()
    if int(count):
        raise RuntimeError("asset_neutral_active_claim_unresolved")


def _assert_active_claim_ticket_lineage(bind: sa.Connection) -> None:
    if not {
        "brc_budget_reservations",
        "brc_action_time_tickets",
    } <= _tables(bind):
        return
    count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM brc_budget_reservations AS reservation
            LEFT JOIN brc_action_time_tickets AS ticket
              ON ticket.ticket_id = reservation.ticket_id
            WHERE reservation.status IN ('active', 'consumed')
              AND (
                ticket.ticket_id IS NULL
                OR ticket.budget_reservation_id <> reservation.budget_reservation_id
                OR ticket.exposure_episode_id IS NULL
                OR ticket.exposure_episode_id <> reservation.exposure_episode_id
                OR ticket.exchange_instrument_id <> reservation.exchange_instrument_id
                OR ticket.capacity_claim_hash IS NULL
                OR ticket.capacity_claim_hash <> reservation.capacity_claim_hash
              )
            """
        )
    ).scalar_one()
    if int(count):
        raise RuntimeError("asset_neutral_active_claim_ticket_lineage_unresolved")


def _assert_no_incomplete_active_candidate_scope(bind: sa.Connection) -> None:
    if "brc_strategy_group_candidate_scope" not in _tables(bind):
        return
    count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM brc_strategy_group_candidate_scope
            WHERE status = 'active'
              AND (
                exchange_instrument_id IS NULL
                OR trim(exchange_instrument_id) = ''
                OR timeframe IS NULL
                OR trim(timeframe) = ''
              )
            """
        )
    ).scalar_one()
    if int(count):
        raise RuntimeError("asset_neutral_active_candidate_scope_unresolved")


def _assert_no_incomplete_current_exposure(bind: sa.Connection) -> None:
    if "brc_account_exposure_current" not in _tables(bind):
        return
    count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM brc_account_exposure_current
            WHERE exposure_state NOT IN ('flat', 'closed')
              AND (
                asset_class IS NULL OR trim(asset_class) = ''
                OR instrument_type IS NULL OR trim(instrument_type) = ''
                OR current_exposure_episode_id IS NULL
                OR trim(current_exposure_episode_id) = ''
                OR primary_risk_cluster_id IS NULL
                OR trim(primary_risk_cluster_id) = ''
                OR cluster_membership_snapshot_id IS NULL
                OR trim(cluster_membership_snapshot_id) = ''
                OR account_source_fact_snapshot_id IS NULL
                OR trim(account_source_fact_snapshot_id) = ''
                OR account_fact_schema_version IS NULL
                OR trim(account_fact_schema_version) = ''
              )
            """
        )
    ).scalar_one()
    if int(count):
        raise RuntimeError("asset_neutral_current_exposure_unresolved")


def _replace_candidate_scope_active_identity_index(bind: sa.Connection) -> None:
    if "brc_strategy_group_candidate_scope" not in _tables(bind):
        return
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_brc_candidate_scope_active"))
    bind.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_candidate_scope_active_instrument_timeframe
            ON brc_strategy_group_candidate_scope (
              strategy_group_id, exchange_instrument_id, side, timeframe
            )
            WHERE status = 'active'
            """
        )
    )


def _create_hot_path_indexes(bind: sa.Connection) -> None:
    if "brc_instrument_rule_snapshots" in _tables(bind):
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_instrument_rule_snapshot_current
                ON brc_instrument_rule_snapshots (exchange_instrument_id)
                WHERE status = 'current'
                """
            )
        )
    if "brc_risk_cluster_memberships" in _tables(bind):
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_risk_cluster_membership_primary_current
                ON brc_risk_cluster_memberships (cluster_membership_snapshot_id)
                WHERE membership_role = 'primary' AND status = 'active'
                """
            )
        )
    if "brc_budget_reservations" in _tables(bind):
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_budget_reservation_idempotency
                ON brc_budget_reservations (reservation_idempotency_key)
                WHERE reservation_idempotency_key IS NOT NULL
                """
            )
        )
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_budget_reservation_invocation
                ON brc_budget_reservations (action_time_invocation_id)
                WHERE action_time_invocation_id IS NOT NULL
                """
            )
        )
        bind.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS idx_brc_budget_reservation_effective_hot_path
                ON brc_budget_reservations (account_id, runtime_profile_id, status)
                WHERE status IN ('active', 'consumed')
                """
            )
        )
    if "brc_account_exposure_current" in _tables(bind):
        bind.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS idx_brc_account_exposure_current_hot_path
                ON brc_account_exposure_current (account_id, exposure_state)
                WHERE exposure_state NOT IN ('flat', 'closed') OR first_blocker IS NOT NULL
                """
            )
        )
    if "brc_ticket_bound_exchange_commands" in _tables(bind):
        bind.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS idx_brc_exchange_command_nonterminal_evidence
                ON brc_ticket_bound_exchange_commands (ticket_id, command_state)
                WHERE command_state NOT IN ('confirmed_rejected', 'reconciled_absent')
                """
            )
        )


def _add_lineage_constraints(bind: sa.Connection) -> None:
    if not {
        "brc_budget_reservations",
        "brc_action_time_tickets",
    } <= _tables(bind):
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("brc_budget_reservations") as batch:
            batch.create_unique_constraint(
                "uq_brc_budget_reservation_ticket_episode",
                ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
            )
        with op.batch_alter_table("brc_action_time_tickets") as batch:
            batch.create_foreign_key(
                "fk_brc_ticket_reservation_ticket_episode",
                "brc_budget_reservations",
                ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
                ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
            )
        return
    op.create_unique_constraint(
        "uq_brc_budget_reservation_ticket_episode",
        "brc_budget_reservations",
        ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
    )
    op.create_foreign_key(
        "fk_brc_ticket_reservation_ticket_episode",
        "brc_action_time_tickets",
        "brc_budget_reservations",
        ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
        ["budget_reservation_id", "ticket_id", "exposure_episode_id"],
    )


def _add_postgresql_current_row_checks(bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql" or "brc_budget_reservations" not in _tables(bind):
        return
    required = " AND ".join(f"{column_name} IS NOT NULL" for column_name in _ACTIVE_CLAIM_REQUIRED_COLUMNS)
    op.execute(
        f"""
        ALTER TABLE brc_budget_reservations
        ADD CONSTRAINT ck_brc_budget_reservation_active_asset_neutral_identity
        CHECK (status NOT IN ('active', 'consumed') OR ({required}))
        """
    )


def _tables(bind: sa.Connection) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind: sa.Connection, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns(table_name)
    }
