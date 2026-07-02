"""Create BRC admission trial binding reservations

Revision ID: 019
Revises: 018
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
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
    if not _has_table("brc_admission_trial_bindings"):
        op.create_table(
            "brc_admission_trial_bindings",
            sa.Column("binding_id", sa.String(length=128), nullable=False),
            sa.Column("admission_decision_id", sa.String(length=128), nullable=False),
            sa.Column("owner_risk_acceptance_id", sa.String(length=128), nullable=True),
            sa.Column("trial_constraint_snapshot_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_catalog_snapshot_json", _jsonb_type(), nullable=False),
            sa.Column("trial_env", sa.String(length=16), nullable=False),
            sa.Column("trial_stage", sa.String(length=64), nullable=False),
            sa.Column("execution_mode", sa.String(length=64), nullable=False),
            sa.Column("binding_status", sa.String(length=64), nullable=False),
            sa.Column("campaign_id", sa.String(length=128), nullable=True),
            sa.Column("runtime_carrier_id", sa.String(length=128), nullable=True),
            sa.Column("created_by_operation_id", sa.String(length=128), nullable=False),
            sa.Column("created_by_preflight_id", sa.String(length=128), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("invalidated_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("invalidation_reason", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "trial_env IN ('testnet', 'live')",
                name="ck_brc_admission_trial_bindings_trial_env",
            ),
            sa.CheckConstraint(
                "trial_stage IN ('development_validation', 'funded_validation')",
                name="ck_brc_admission_trial_bindings_trial_stage",
            ),
            sa.CheckConstraint(
                "execution_mode IN ('auto_within_budget', 'owner_confirm_each_entry', "
                "'observe_only', 'no_entry')",
                name="ck_brc_admission_trial_bindings_execution_mode",
            ),
            sa.CheckConstraint(
                "binding_status IN ('planned', 'binding_reserved', 'cancelled', 'expired', "
                "'invalidated', 'campaign_created', 'runtime_constraints_installed', "
                "'runtime_installed')",
                name="ck_brc_admission_trial_bindings_status",
            ),
            sa.CheckConstraint(
                "(binding_status NOT IN ('planned', 'binding_reserved')) "
                "OR (campaign_id IS NULL AND runtime_carrier_id IS NULL)",
                name="ck_brc_admission_trial_bindings_reserved_no_runtime",
            ),
            sa.PrimaryKeyConstraint("binding_id"),
        )
    _create_index_if_missing(
        "idx_brc_admission_trial_bindings_decision_status",
        "brc_admission_trial_bindings",
        ["admission_decision_id", "binding_status"],
    )
    _create_index_if_missing(
        "idx_brc_admission_trial_bindings_operation",
        "brc_admission_trial_bindings",
        ["created_by_operation_id"],
    )
    _create_index_if_missing(
        "idx_brc_admission_trial_bindings_status_time",
        "brc_admission_trial_bindings",
        ["binding_status", "created_at_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_admission_trial_bindings_status_time",
        "idx_brc_admission_trial_bindings_operation",
        "idx_brc_admission_trial_bindings_decision_status",
    ]:
        _drop_index_if_exists(index_name, "brc_admission_trial_bindings")
    if _has_table("brc_admission_trial_bindings"):
        op.drop_table("brc_admission_trial_bindings")
