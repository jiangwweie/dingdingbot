"""Create LLM advisory plane ledgers

Revision ID: 081
Revises: 080
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "081"
down_revision: Union[str, None] = "080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EVENT_TABLE = "llm_consumable_events"
RECOMMENDATION_TABLE = "llm_advisory_recommendations"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(EVENT_TABLE):
        op.create_table(
            EVENT_TABLE,
            sa.Column("event_id", sa.String(length=128), primary_key=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=128), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
            sa.Column("symbol", sa.String(length=64), nullable=True),
            sa.Column("timeframe", sa.String(length=32), nullable=True),
            sa.Column("strategy_family_ids", _json_type(), nullable=False, server_default="[]"),
            sa.Column("dedupe_key", sa.String(length=256), nullable=True),
            sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("context_packet", _json_type(), nullable=False, server_default="{}"),
            sa.Column("allowed_llm_actions", _json_type(), nullable=False, server_default="[]"),
            sa.Column("delivery_policy", _json_type(), nullable=False, server_default="[]"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("not_execution_authority", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("owner_action_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("execution_intent_created", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "withdrawal_instruction_created",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "transfer_instruction_created",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("live_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.CheckConstraint(
                "event_type IN ('market_regime_changed', 'strategy_candidate_observed', "
                "'runtime_budget_changed', 'final_gate_blocked', 'order_candidate_created', "
                "'protection_anomaly_detected', 'reconciliation_mismatch', 'trade_closed', "
                "'review_due', 'daily_audit_digest', 'owner_requested_analysis')",
                name="ck_llm_consumable_events_type",
            ),
            sa.CheckConstraint(
                "not_execution_authority = true",
                name="ck_llm_consumable_events_not_authority",
            ),
            sa.CheckConstraint(
                "owner_action_enabled = false",
                name="ck_llm_consumable_events_no_owner_action",
            ),
            sa.CheckConstraint(
                "execution_intent_created = false",
                name="ck_llm_consumable_events_no_intent",
            ),
            sa.CheckConstraint(
                "order_created = false",
                name="ck_llm_consumable_events_no_order",
            ),
            sa.CheckConstraint(
                "exchange_called = false",
                name="ck_llm_consumable_events_no_exchange",
            ),
            sa.CheckConstraint(
                "withdrawal_instruction_created = false",
                name="ck_llm_consumable_events_no_withdrawal",
            ),
            sa.CheckConstraint(
                "transfer_instruction_created = false",
                name="ck_llm_consumable_events_no_transfer",
            ),
            sa.CheckConstraint(
                "live_ready = false",
                name="ck_llm_consumable_events_no_live",
            ),
        )
        op.create_index(
            "idx_llm_consumable_events_type_time",
            EVENT_TABLE,
            ["event_type", "created_at_ms"],
        )
        op.create_index(
            "idx_llm_consumable_events_source",
            EVENT_TABLE,
            ["source_type", "source_id"],
        )
        op.create_index("idx_llm_consumable_events_dedupe", EVENT_TABLE, ["dedupe_key"])

    if not _has_table(RECOMMENDATION_TABLE):
        op.create_table(
            RECOMMENDATION_TABLE,
            sa.Column("recommendation_id", sa.String(length=128), primary_key=True),
            sa.Column("event_id", sa.String(length=128), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=128), nullable=False),
            sa.Column("recommendation_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Numeric(8, 6), nullable=False),
            sa.Column(
                "recommended_strategy_family_ids",
                _json_type(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "observe_only_strategy_family_ids",
                _json_type(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("reason_codes", _json_type(), nullable=False, server_default="[]"),
            sa.Column("risk_notes", _json_type(), nullable=False, server_default="[]"),
            sa.Column("missing_facts", _json_type(), nullable=False, server_default="[]"),
            sa.Column(
                "research_idea_notes",
                _json_type(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("review_notes", _json_type(), nullable=False, server_default="[]"),
            sa.Column(
                "feishu_card_type",
                sa.String(length=64),
                nullable=False,
                server_default="generic_advisory",
            ),
            sa.Column("provider_name", sa.String(length=128), nullable=False),
            sa.Column("model_name", sa.String(length=128), nullable=True),
            sa.Column("prompt_version", sa.String(length=64), nullable=False),
            sa.Column("raw_response_summary", _json_type(), nullable=False, server_default="{}"),
            sa.Column("delivery_channels", _json_type(), nullable=False, server_default="[]"),
            sa.Column(
                "owner_action_route",
                sa.String(length=256),
                nullable=False,
                server_default="/console",
            ),
            sa.Column("owner_action_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pushed_to_feishu_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("push_error", sa.Text(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("not_execution_authority", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column(
                "strategy_execution_authorized",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("execution_intent_created", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "withdrawal_instruction_created",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "transfer_instruction_created",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("live_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.CheckConstraint(
                "recommendation_type IN ('strategy_family_candidate', 'audit_digest', "
                "'blocker_explanation', 'trade_review', 'market_context', 'unknown')",
                name="ck_llm_advisory_recommendations_type",
            ),
            sa.CheckConstraint(
                "status IN ('generated', 'blocked', 'pushed', 'push_failed')",
                name="ck_llm_advisory_recommendations_status",
            ),
            sa.CheckConstraint(
                "confidence >= 0 AND confidence <= 1",
                name="ck_llm_advisory_recommendations_confidence",
            ),
            sa.CheckConstraint(
                "feishu_card_type IN ('candidate_review', 'final_gate_blocked', "
                "'daily_audit_digest', 'trade_closed_review', 'market_context', "
                "'generic_advisory')",
                name="ck_llm_advisory_recommendations_card_type",
            ),
            sa.CheckConstraint(
                "not_execution_authority = true",
                name="ck_llm_advisory_recommendations_not_authority",
            ),
            sa.CheckConstraint(
                "owner_action_enabled = false",
                name="ck_llm_advisory_recommendations_push_only",
            ),
            sa.CheckConstraint(
                "strategy_execution_authorized = false",
                name="ck_llm_advisory_recommendations_no_strategy_auth",
            ),
            sa.CheckConstraint(
                "execution_intent_created = false",
                name="ck_llm_advisory_recommendations_no_intent",
            ),
            sa.CheckConstraint(
                "order_created = false",
                name="ck_llm_advisory_recommendations_no_order",
            ),
            sa.CheckConstraint(
                "exchange_called = false",
                name="ck_llm_advisory_recommendations_no_exchange",
            ),
            sa.CheckConstraint(
                "withdrawal_instruction_created = false",
                name="ck_llm_advisory_recommendations_no_withdrawal",
            ),
            sa.CheckConstraint(
                "transfer_instruction_created = false",
                name="ck_llm_advisory_recommendations_no_transfer",
            ),
            sa.CheckConstraint(
                "live_ready = false",
                name="ck_llm_advisory_recommendations_no_live",
            ),
        )
        op.create_index(
            "idx_llm_advisory_recommendations_event",
            RECOMMENDATION_TABLE,
            ["event_id"],
        )
        op.create_index(
            "idx_llm_advisory_recommendations_type_time",
            RECOMMENDATION_TABLE,
            ["event_type", "created_at_ms"],
        )
        op.create_index(
            "idx_llm_advisory_recommendations_status_time",
            RECOMMENDATION_TABLE,
            ["status", "created_at_ms"],
        )


def downgrade() -> None:
    if _has_table(RECOMMENDATION_TABLE):
        op.drop_index(
            "idx_llm_advisory_recommendations_status_time",
            table_name=RECOMMENDATION_TABLE,
        )
        op.drop_index(
            "idx_llm_advisory_recommendations_type_time",
            table_name=RECOMMENDATION_TABLE,
        )
        op.drop_index(
            "idx_llm_advisory_recommendations_event",
            table_name=RECOMMENDATION_TABLE,
        )
        op.drop_table(RECOMMENDATION_TABLE)
    if _has_table(EVENT_TABLE):
        op.drop_index("idx_llm_consumable_events_dedupe", table_name=EVENT_TABLE)
        op.drop_index("idx_llm_consumable_events_source", table_name=EVENT_TABLE)
        op.drop_index("idx_llm_consumable_events_type_time", table_name=EVENT_TABLE)
        op.drop_table(EVENT_TABLE)
