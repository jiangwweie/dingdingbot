"""Add nullable strategy runtime audit IDs

Revision ID: 046
Revises: 045
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUDIT_ID_COLUMNS = [
    "runtime_instance_id",
    "trial_binding_id",
    "strategy_family_id",
    "strategy_family_version_id",
    "signal_evaluation_id",
    "order_candidate_id",
]

TABLES = [
    "execution_intents",
    "orders",
    "brc_live_lifecycle_reviews",
    "reconciliation_read_model_reports",
    "reconciliation_read_model_mismatches",
]

INDEXES = {
    "execution_intents": [
        ("idx_execution_intents_runtime_instance_id", ["runtime_instance_id"]),
        ("idx_execution_intents_trial_binding_id", ["trial_binding_id"]),
        (
            "idx_execution_intents_strategy_family_version_id",
            ["strategy_family_version_id"],
        ),
        ("idx_execution_intents_order_candidate_id", ["order_candidate_id"]),
    ],
    "orders": [
        ("idx_orders_runtime_instance_id", ["runtime_instance_id"]),
        ("idx_orders_trial_binding_id", ["trial_binding_id"]),
        ("idx_orders_strategy_family_version_id", ["strategy_family_version_id"]),
        ("idx_orders_order_candidate_id", ["order_candidate_id"]),
    ],
    "brc_live_lifecycle_reviews": [
        ("idx_brc_live_lifecycle_reviews_runtime", ["runtime_instance_id"]),
        ("idx_brc_live_lifecycle_reviews_trial_binding", ["trial_binding_id"]),
        (
            "idx_brc_live_lifecycle_reviews_strategy_version",
            ["strategy_family_version_id"],
        ),
    ],
    "reconciliation_read_model_reports": [
        ("idx_reconciliation_read_model_reports_runtime", ["runtime_instance_id"]),
        ("idx_reconciliation_read_model_reports_trial_binding", ["trial_binding_id"]),
    ],
    "reconciliation_read_model_mismatches": [
        ("idx_reconciliation_read_model_mismatches_runtime", ["runtime_instance_id"]),
        (
            "idx_reconciliation_read_model_mismatches_trial_binding",
            ["trial_binding_id"],
        ),
    ],
}


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    for table_name in TABLES:
        if not _has_table(table_name):
            continue
        for column_name in AUDIT_ID_COLUMNS:
            if not _has_column(table_name, column_name):
                op.add_column(
                    table_name,
                    sa.Column(column_name, sa.String(length=128), nullable=True),
                )
        for index_name, columns in INDEXES.get(table_name, []):
            if not _has_index(table_name, index_name):
                op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    for table_name in reversed(TABLES):
        if not _has_table(table_name):
            continue
        for index_name, _columns in reversed(INDEXES.get(table_name, [])):
            if _has_index(table_name, index_name):
                op.drop_index(index_name, table_name=table_name)
        for column_name in reversed(AUDIT_ID_COLUMNS):
            if _has_column(table_name, column_name):
                op.drop_column(table_name, column_name)
