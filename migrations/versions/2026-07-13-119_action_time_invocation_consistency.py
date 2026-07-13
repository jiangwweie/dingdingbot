"""Bind Action-Time work to one exact signal and fact lineage.

Revision ID: 119
Revises: 118
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "119"
down_revision: Union[str, None] = "118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INVOCATION_TABLE = "brc_action_time_invocations"
FACT_TABLE = "brc_runtime_fact_snapshots"
OUTCOME_TABLE = "brc_runtime_process_outcomes"
COVERAGE_TABLE = "brc_watcher_runtime_coverage"
PROMOTION_TABLE = "brc_promotion_candidates"
LANE_TABLE = "brc_action_time_lane_inputs"
TICKET_TABLE = "brc_action_time_tickets"


RUNTIME_LANE_COLUMNS = (
    sa.Column("candidate_scope_id", sa.String(192), nullable=True),
    sa.Column("candidate_scope_event_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_scope_binding_id", sa.String(192), nullable=True),
    sa.Column("runtime_instance_id", sa.String(192), nullable=True),
    sa.Column("runtime_profile_id", sa.String(192), nullable=True),
    sa.Column("policy_current_id", sa.String(192), nullable=True),
    sa.Column("strategy_group_version_id", sa.String(192), nullable=True),
    sa.Column("asset_class", sa.String(96), nullable=True),
    sa.Column("event_spec_id", sa.String(192), nullable=True),
    sa.Column("event_spec_version", sa.String(96), nullable=True),
    sa.Column("event_id", sa.String(128), nullable=True),
    sa.Column("timeframe", sa.String(32), nullable=True),
    sa.Column("time_authority", sa.String(64), nullable=True),
    sa.Column("lane_identity_key", sa.String(192), nullable=True),
    sa.Column("source_watermark", sa.String(256), nullable=True),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(INVOCATION_TABLE):
        op.create_table(
            INVOCATION_TABLE,
            sa.Column("action_time_invocation_id", sa.String(192), primary_key=True),
            sa.Column("signal_event_id", sa.String(192), nullable=False),
            sa.Column("candidate_scope_id", sa.String(192), nullable=False),
            sa.Column(
                "candidate_scope_event_binding_id", sa.String(192), nullable=False
            ),
            sa.Column("runtime_scope_binding_id", sa.String(192), nullable=False),
            sa.Column("runtime_instance_id", sa.String(192), nullable=False),
            sa.Column("runtime_profile_id", sa.String(192), nullable=False),
            sa.Column("policy_current_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("strategy_group_version_id", sa.String(192), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("asset_class", sa.String(96), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("event_spec_id", sa.String(192), nullable=False),
            sa.Column("event_spec_version", sa.String(96), nullable=False),
            sa.Column("event_id", sa.String(128), nullable=False),
            sa.Column("timeframe", sa.String(32), nullable=False),
            sa.Column("time_authority", sa.String(64), nullable=False),
            sa.Column("lane_identity_key", sa.String(192), nullable=False),
            sa.Column("source_watermark", sa.String(256), nullable=False),
            sa.Column("opened_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("expires_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("account_safe_fact_snapshot_id", sa.String(256), nullable=True),
            sa.Column("account_mode_fact_snapshot_id", sa.String(256), nullable=True),
            sa.Column("action_time_fact_snapshot_id", sa.String(256), nullable=True),
            sa.Column("ticket_id", sa.String(192), nullable=True),
            sa.Column("closed_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.UniqueConstraint(
                "signal_event_id",
                name="uq_brc_action_time_invocation_signal",
            ),
            sa.UniqueConstraint(
                "lane_identity_key",
                "source_watermark",
                name="uq_brc_action_time_invocation_lane_source",
            ),
            sa.CheckConstraint(
                "expires_at_ms > opened_at_ms",
                name="ck_brc_action_time_invocation_deadline",
            ),
            sa.CheckConstraint(
                "closed_at_ms IS NULL OR closed_at_ms >= opened_at_ms",
                name="ck_brc_action_time_invocation_close_after_open",
            ),
        )
    _create_index_if_missing(
        INVOCATION_TABLE,
        "idx_brc_action_time_invocation_current",
        ["expires_at_ms", "closed_at_ms"],
    )

    inspector = sa.inspect(bind)
    if inspector.has_table(FACT_TABLE):
        _add_missing_columns(
            FACT_TABLE,
            (
                sa.Column(
                    "action_time_invocation_id", sa.String(192), nullable=True
                ),
            ),
        )
        _create_index_if_missing(
            FACT_TABLE,
            "idx_brc_runtime_fact_action_time_invocation",
            ["action_time_invocation_id", "fact_surface"],
        )
    if inspector.has_table(OUTCOME_TABLE):
        _add_missing_columns(
            OUTCOME_TABLE,
            RUNTIME_LANE_COLUMNS
            + (
                sa.Column(
                    "action_time_invocation_id", sa.String(192), nullable=True
                ),
            ),
        )
        _create_index_if_missing(
            OUTCOME_TABLE,
            "idx_brc_runtime_outcome_action_time_invocation",
            ["action_time_invocation_id", "updated_at_ms"],
        )
    if inspector.has_table(PROMOTION_TABLE):
        _add_missing_columns(
            PROMOTION_TABLE,
            (
                sa.Column(
                    "action_time_invocation_id", sa.String(192), nullable=True
                ),
            ),
        )
        _create_index_if_missing(
            PROMOTION_TABLE,
            "idx_brc_promotion_action_time_invocation",
            ["action_time_invocation_id", "created_at_ms"],
        )
    if inspector.has_table(LANE_TABLE):
        _add_missing_columns(
            LANE_TABLE,
            (
                sa.Column(
                    "action_time_invocation_id", sa.String(192), nullable=True
                ),
                sa.Column(
                    "account_safe_fact_snapshot_id", sa.String(256), nullable=True
                ),
                sa.Column(
                    "account_mode_fact_snapshot_id", sa.String(256), nullable=True
                ),
            ),
        )
        _create_index_if_missing(
            LANE_TABLE,
            "idx_brc_lane_action_time_invocation",
            ["action_time_invocation_id", "created_at_ms"],
        )
    if inspector.has_table(TICKET_TABLE):
        _add_missing_columns(
            TICKET_TABLE,
            (
                sa.Column(
                    "action_time_invocation_id", sa.String(192), nullable=True
                ),
            ),
        )
        _create_index_if_missing(
            TICKET_TABLE,
            "idx_brc_ticket_action_time_invocation",
            ["action_time_invocation_id", "created_at_ms"],
        )
    if inspector.has_table(COVERAGE_TABLE):
        _add_missing_columns(COVERAGE_TABLE, RUNTIME_LANE_COLUMNS)
        _invalidate_legacy_current_coverage(bind)
        _create_index_if_missing(
            COVERAGE_TABLE,
            "idx_brc_coverage_runtime_lane_lineage",
            ["lane_identity_key", "source_watermark", "is_current"],
        )


def downgrade() -> None:
    """Forward-only: dropping lineage columns would recreate ambiguous authority."""


def _add_missing_columns(table_name: str, columns: tuple[sa.Column, ...]) -> None:
    existing = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }
    for column in columns:
        if column.name not in existing:
            op.add_column(table_name, column)


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    existing = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def _invalidate_legacy_current_coverage(bind: sa.engine.Connection) -> None:
    bind.execute(
        sa.text(
            """
            UPDATE brc_watcher_runtime_coverage
            SET is_current = false
            WHERE is_current = true
              AND coverage_state = 'covered'
              AND (
                candidate_scope_id IS NULL
                OR candidate_scope_event_binding_id IS NULL
                OR runtime_scope_binding_id IS NULL
                OR runtime_instance_id IS NULL
                OR runtime_profile_id IS NULL
                OR policy_current_id IS NULL
                OR strategy_group_version_id IS NULL
                OR asset_class IS NULL
                OR event_spec_id IS NULL
                OR event_spec_version IS NULL
                OR event_id IS NULL
                OR timeframe IS NULL
                OR time_authority IS NULL
                OR lane_identity_key IS NULL
                OR source_watermark IS NULL
              )
            """
        )
    )
