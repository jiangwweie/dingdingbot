"""Bind account-capacity claims to immutable policy events and margin state.

Revision ID: 130
Revises: 129
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "130"
down_revision: Union[str, None] = "129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESERVATIONS = "brc_budget_reservations"
POLICY_EVENTS = "brc_account_risk_policy_events"
OLD_POLICY_EVENT_UNIQUE = "uq_brc_account_risk_policy_event_identity"


def upgrade() -> None:
    _add_reservation_column("account_risk_policy_event_id", sa.String(192))
    _add_reservation_column("allowed_risk_budget", sa.Numeric(36, 18))
    _add_reservation_column("margin_accounting_state", sa.String(32))
    _drop_legacy_policy_event_unique_constraint()
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_brc_budget_res_capacity_event_scope "
            "ON brc_budget_reservations "
            "(account_id, account_risk_policy_event_id, status) "
            "WHERE status IN ('active', 'consumed')"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_brc_budget_res_capacity_event_scope")
    for column_name in (
        "margin_accounting_state",
        "allowed_risk_budget",
        "account_risk_policy_event_id",
    ):
        if _has_column(RESERVATIONS, column_name):
            op.drop_column(RESERVATIONS, column_name)


def _add_reservation_column(column_name: str, column_type: sa.types.TypeEngine) -> None:
    if not _has_column(RESERVATIONS, column_name):
        op.add_column(RESERVATIONS, sa.Column(column_name, column_type, nullable=True))


def _drop_legacy_policy_event_unique_constraint() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if POLICY_EVENTS not in inspector.get_table_names():
        return
    unique_names = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints(POLICY_EVENTS)
    }
    if OLD_POLICY_EVENT_UNIQUE not in unique_names:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(POLICY_EVENTS) as batch:
            batch.drop_constraint(OLD_POLICY_EVENT_UNIQUE, type_="unique")
    else:
        op.drop_constraint(OLD_POLICY_EVENT_UNIQUE, POLICY_EVENTS, type_="unique")


def _has_column(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )
