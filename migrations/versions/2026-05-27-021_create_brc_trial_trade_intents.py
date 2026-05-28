"""Create BRC non-executable trial trade intent ledger

Revision ID: 021
Revises: 020
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "021"
down_revision: Union[str, None] = "020"
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
    if not _has_table("brc_trial_trade_intents"):
        op.create_table(
            "brc_trial_trade_intents",
            sa.Column("intent_id", sa.String(length=128), nullable=False),
            sa.Column("campaign_id", sa.String(length=128), nullable=False),
            sa.Column("binding_id", sa.String(length=128), nullable=True),
            sa.Column("admission_decision_id", sa.String(length=128), nullable=True),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
            sa.Column("execution_mode", sa.String(length=64), nullable=False),
            sa.Column("intended_action", sa.String(length=64), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=True),
            sa.Column("signal_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("market_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("risk_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("decision", sa.String(length=32), nullable=False),
            sa.Column("not_executed_reason", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("created_by_operation_id", sa.String(length=128), nullable=True),
            sa.Column("audit_refs_json", _jsonb_type(), nullable=False),
            sa.CheckConstraint(
                "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', "
                "'observe_only', 'no_entry')",
                name="ck_brc_trial_trade_intents_execution_mode",
            ),
            sa.CheckConstraint(
                "intended_action IN ('entry', 'increase', 'exit', 'reduce', 'hold', 'unknown')",
                name="ck_brc_trial_trade_intents_intended_action",
            ),
            sa.CheckConstraint(
                "decision IN ('recorded', 'blocked', 'unavailable')",
                name="ck_brc_trial_trade_intents_decision",
            ),
            sa.PrimaryKeyConstraint("intent_id"),
        )
    _create_index_if_missing(
        "idx_brc_trial_trade_intents_campaign_time",
        "brc_trial_trade_intents",
        ["campaign_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_trial_trade_intents_binding_time",
        "brc_trial_trade_intents",
        ["binding_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_trial_trade_intents_decision_time",
        "brc_trial_trade_intents",
        ["decision", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_trial_trade_intents_operation",
        "brc_trial_trade_intents",
        ["created_by_operation_id"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_trial_trade_intents_operation",
        "idx_brc_trial_trade_intents_decision_time",
        "idx_brc_trial_trade_intents_binding_time",
        "idx_brc_trial_trade_intents_campaign_time",
    ]:
        _drop_index_if_exists(index_name, "brc_trial_trade_intents")
    if _has_table("brc_trial_trade_intents"):
        op.drop_table("brc_trial_trade_intents")
