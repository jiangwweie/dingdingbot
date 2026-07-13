"""Conserve immutable runtime-lane identity across signal materialization.

Revision ID: 118
Revises: 117
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "118"
down_revision: Union[str, None] = "117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LIVE_SIGNAL_TABLE = "brc_live_signal_events"
OUTCOME_TABLE = "brc_runtime_process_outcomes"
PROMOTION_TABLE = "brc_promotion_candidates"
LANE_TABLE = "brc_action_time_lane_inputs"
TICKET_TABLE = "brc_action_time_tickets"
MIGRATION_AT_MS = 1783908000000

KNOWN_FALSE_OUTCOME = {
    "process_name": "live_signal_materialization",
    "scope_key": "lane:CPM-RO-001:SOLUSDT:short",
    "process_state": "retryable_failure",
    "source_watermark": "strategy-runtime-d3e7af7d4f6e:1783907999999",
    "first_blocker": (
        "pg_live_signal_event_materialization_failed:"
        "runtime_summary_blocked:waiting_for_signal"
    ),
}


LIVE_SIGNAL_COLUMNS = (
    sa.Column("candidate_scope_event_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_scope_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_instance_id", sa.String(192), nullable=True),
    sa.Column("runtime_profile_id", sa.String(192), nullable=True),
    sa.Column("policy_current_id", sa.String(192), nullable=True),
    sa.Column("strategy_group_version_id", sa.String(192), nullable=True),
    sa.Column("asset_class", sa.String(96), nullable=True),
    sa.Column("event_spec_version", sa.String(96), nullable=True),
    sa.Column("event_id", sa.String(128), nullable=True),
    sa.Column("timeframe", sa.String(32), nullable=True),
    sa.Column("time_authority", sa.String(64), nullable=True),
    sa.Column("lane_identity_key", sa.String(192), nullable=True),
    sa.Column("source_watermark", sa.String(256), nullable=True),
)

LINEAGE_COLUMNS = (
    sa.Column("lane_identity_key", sa.String(192), nullable=True),
    sa.Column("source_watermark", sa.String(256), nullable=True),
)

OUTCOME_COLUMNS = (
    sa.Column("scope_kind", sa.String(64), nullable=True),
    sa.Column("candidate_scope_id", sa.String(192), nullable=True),
    sa.Column("candidate_scope_event_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_scope_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_instance_id", sa.String(192), nullable=True),
    sa.Column("strategy_group_id", sa.String(128), nullable=True),
    sa.Column("strategy_group_version_id", sa.String(192), nullable=True),
    sa.Column("symbol", sa.String(128), nullable=True),
    sa.Column("asset_class", sa.String(96), nullable=True),
    sa.Column("side", sa.String(32), nullable=True),
    sa.Column("event_spec_id", sa.String(192), nullable=True),
    sa.Column("event_spec_version", sa.String(96), nullable=True),
    sa.Column("event_id", sa.String(128), nullable=True),
    sa.Column("timeframe", sa.String(32), nullable=True),
    sa.Column("lane_identity_key", sa.String(192), nullable=True),
    sa.Column("legacy_evidence", sa.Text(), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(LIVE_SIGNAL_TABLE):
        _add_missing_columns(LIVE_SIGNAL_TABLE, LIVE_SIGNAL_COLUMNS)
        _invalidate_untyped_current_live_signals(bind)
        _create_check(
            LIVE_SIGNAL_TABLE,
            "ck_brc_live_signal_fresh_runtime_lane_identity",
            """
            NOT (
              source_kind = 'live_market'
              AND status = 'facts_validated'
              AND freshness_state = 'fresh'
            )
            OR (
              candidate_scope_id IS NOT NULL
              AND candidate_scope_event_binding_id IS NOT NULL
              AND runtime_scope_binding_id IS NOT NULL
              AND runtime_instance_id IS NOT NULL
              AND runtime_profile_id IS NOT NULL
              AND policy_current_id IS NOT NULL
              AND strategy_group_id IS NOT NULL
              AND strategy_group_version_id IS NOT NULL
              AND symbol IS NOT NULL
              AND asset_class IS NOT NULL
              AND side IN ('long', 'short')
              AND event_spec_id IS NOT NULL
              AND event_spec_version IS NOT NULL
              AND event_id IS NOT NULL
              AND timeframe IS NOT NULL
              AND time_authority = 'trigger_candle_close_time_ms'
              AND lane_identity_key IS NOT NULL
              AND source_watermark IS NOT NULL
            )
            """,
        )
        _create_index_if_missing(
            LIVE_SIGNAL_TABLE,
            "idx_brc_live_signal_runtime_lane_identity_current",
            ["lane_identity_key", "freshness_state", "expires_at_ms"],
        )

    if inspector.has_table(PROMOTION_TABLE):
        _add_missing_columns(PROMOTION_TABLE, LINEAGE_COLUMNS)
        _invalidate_untyped_current_promotions(bind)
        _create_check(
            PROMOTION_TABLE,
            "ck_brc_promotion_current_runtime_lane_lineage",
            """
            NOT (
              status IN ('eligible', 'arbitration_pending', 'arbitration_won')
              AND closed_at_ms IS NULL
            )
            OR (
              lane_identity_key IS NOT NULL
              AND source_watermark IS NOT NULL
            )
            """,
        )
        _create_index_if_missing(
            PROMOTION_TABLE,
            "idx_brc_promotion_runtime_lane_lineage",
            ["lane_identity_key", "source_watermark"],
        )

    if inspector.has_table(LANE_TABLE):
        _add_missing_columns(LANE_TABLE, LINEAGE_COLUMNS)
        _invalidate_untyped_current_lanes(bind)
        _create_check(
            LANE_TABLE,
            "ck_brc_action_time_lane_current_runtime_lane_lineage",
            """
            NOT (
              status IN ('opened', 'facts_refreshing', 'ticket_pending', 'ticket_created')
              AND closed_at_ms IS NULL
            )
            OR (
              lane_identity_key IS NOT NULL
              AND source_watermark IS NOT NULL
            )
            """,
        )
        _create_index_if_missing(
            LANE_TABLE,
            "idx_brc_action_time_lane_runtime_lane_lineage",
            ["lane_identity_key", "source_watermark"],
        )

    if inspector.has_table(TICKET_TABLE):
        _add_missing_columns(TICKET_TABLE, LINEAGE_COLUMNS)
        _invalidate_untyped_current_tickets(bind)
        _create_check(
            TICKET_TABLE,
            "ck_brc_action_time_ticket_current_runtime_lane_lineage",
            """
            status NOT IN ('created', 'preflight_pending', 'finalgate_ready', 'submitted')
            OR (
              lane_identity_key IS NOT NULL
              AND source_watermark IS NOT NULL
            )
            """,
        )
        _create_index_if_missing(
            TICKET_TABLE,
            "idx_brc_action_time_ticket_runtime_lane_lineage",
            ["lane_identity_key", "source_watermark"],
        )

    if inspector.has_table(OUTCOME_TABLE):
        _add_missing_columns(OUTCOME_TABLE, OUTCOME_COLUMNS)
        _replace_legacy_outcome_scope_uniqueness()
        _reconcile_known_false_cpm_short_outcome(bind)
        _create_check(
            OUTCOME_TABLE,
            "ck_brc_runtime_outcome_runtime_lane_identity_complete",
            """
            scope_kind IS NULL
            OR scope_kind <> 'runtime_lane'
            OR (
              candidate_scope_id IS NOT NULL
              AND candidate_scope_event_binding_id IS NOT NULL
              AND runtime_scope_binding_id IS NOT NULL
              AND runtime_instance_id IS NOT NULL
              AND strategy_group_id IS NOT NULL
              AND strategy_group_version_id IS NOT NULL
              AND symbol IS NOT NULL
              AND asset_class IS NOT NULL
              AND side IN ('long', 'short')
              AND event_spec_id IS NOT NULL
              AND event_spec_version IS NOT NULL
              AND event_id IS NOT NULL
              AND timeframe IS NOT NULL
              AND lane_identity_key IS NOT NULL
            )
            """,
        )
        _create_check(
            OUTCOME_TABLE,
            "ck_brc_runtime_outcome_scope_kind",
            "scope_kind IS NULL OR scope_kind IN ('runtime_lane', 'legacy_unscoped', 'legacy_invalid_scope')",
        )
        _create_index_if_missing(
            OUTCOME_TABLE,
            "idx_brc_runtime_outcome_runtime_lane_current",
            ["lane_identity_key", "updated_at_ms"],
        )
        bind.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_brc_runtime_outcome_lane_source_watermark
                ON brc_runtime_process_outcomes (
                  process_name, lane_identity_key, source_watermark
                )
                WHERE scope_kind = 'runtime_lane'
                  AND lane_identity_key IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    """Intentionally preserve reconciled safety history on downgrade.

    Dropping identity columns or restoring the known false CPM-short retry row
    would recreate a current false lane. The migration is therefore forward-only
    for data safety; a code rollback remains possible against the expanded schema.
    """


def _add_missing_columns(table_name: str, columns: tuple[sa.Column, ...]) -> None:
    existing = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def _invalidate_untyped_current_live_signals(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE {LIVE_SIGNAL_TABLE}
            SET status = 'superseded',
                freshness_state = 'expired',
                invalidated_at_ms = COALESCE(invalidated_at_ms, :migration_at_ms),
                expires_at_ms = CASE
                  WHEN expires_at_ms IS NULL OR expires_at_ms > :migration_at_ms
                  THEN :migration_at_ms
                  ELSE expires_at_ms
                END
            WHERE source_kind = 'live_market'
              AND status = 'facts_validated'
              AND freshness_state = 'fresh'
              AND (
                candidate_scope_event_binding_id IS NULL
                OR runtime_scope_binding_id IS NULL
                OR runtime_instance_id IS NULL
                OR runtime_profile_id IS NULL
                OR policy_current_id IS NULL
                OR strategy_group_version_id IS NULL
                OR asset_class IS NULL
                OR event_spec_version IS NULL
                OR event_id IS NULL
                OR timeframe IS NULL
                OR time_authority IS NULL
                OR lane_identity_key IS NULL
                OR source_watermark IS NULL
              )
            """
        ),
        {"migration_at_ms": MIGRATION_AT_MS},
    )


def _invalidate_untyped_current_promotions(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE {PROMOTION_TABLE}
            SET status = 'expired',
                closed_at_ms = COALESCE(closed_at_ms, :migration_at_ms),
                expires_at_ms = CASE
                  WHEN expires_at_ms > :migration_at_ms THEN :migration_at_ms
                  ELSE expires_at_ms
                END
            WHERE status IN ('eligible', 'arbitration_pending', 'arbitration_won')
              AND closed_at_ms IS NULL
              AND (lane_identity_key IS NULL OR source_watermark IS NULL)
            """
        ),
        {"migration_at_ms": MIGRATION_AT_MS},
    )


def _invalidate_untyped_current_lanes(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE {LANE_TABLE}
            SET status = 'invalidated',
                closed_at_ms = COALESCE(closed_at_ms, :migration_at_ms),
                expires_at_ms = CASE
                  WHEN expires_at_ms > :migration_at_ms THEN :migration_at_ms
                  ELSE expires_at_ms
                END
            WHERE status IN ('opened', 'facts_refreshing', 'ticket_pending', 'ticket_created')
              AND closed_at_ms IS NULL
              AND (lane_identity_key IS NULL OR source_watermark IS NULL)
            """
        ),
        {"migration_at_ms": MIGRATION_AT_MS},
    )


def _invalidate_untyped_current_tickets(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE {TICKET_TABLE}
            SET status = 'invalidated',
                expires_at_ms = CASE
                  WHEN expires_at_ms > :migration_at_ms THEN :migration_at_ms
                  ELSE expires_at_ms
                END
            WHERE status IN ('created', 'preflight_pending', 'finalgate_ready', 'submitted')
              AND (lane_identity_key IS NULL OR source_watermark IS NULL)
            """
        ),
        {"migration_at_ms": MIGRATION_AT_MS},
    )


def _reconcile_known_false_cpm_short_outcome(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            f"""
            UPDATE {OUTCOME_TABLE}
            SET process_state = 'noop',
                business_state = 'completed',
                scope_kind = 'legacy_invalid_scope',
                legacy_evidence = first_blocker,
                first_blocker = 'legacy_invalid_runtime_lane_identity_reconciled',
                updated_at_ms = :migration_at_ms
            WHERE process_name = :process_name
              AND scope_key = :scope_key
              AND process_state = :process_state
              AND source_watermark = :source_watermark
              AND first_blocker = :first_blocker
            """
        ),
        {**KNOWN_FALSE_OUTCOME, "migration_at_ms": MIGRATION_AT_MS},
    )


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    existing = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def _replace_legacy_outcome_scope_uniqueness() -> None:
    """Replace scope-only idempotency with lane identity plus watermark."""

    name = "uq_brc_process_outcome_scope"
    constraints = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_unique_constraints(OUTCOME_TABLE)
    }
    if name not in constraints:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(OUTCOME_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(name, type_="unique")
        return
    op.drop_constraint(name, OUTCOME_TABLE, type_="unique")


def _create_check(table_name: str, name: str, condition: str) -> None:
    existing = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    }
    if name in existing:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.create_check_constraint(name, condition)
        return
    op.create_check_constraint(name, table_name, condition)
