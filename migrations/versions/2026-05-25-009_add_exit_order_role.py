"""Add explicit EXIT order role

Revision ID: 009
Revises: 008
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_orders_order_role", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_order_role",
        "orders",
        "order_role IN ('ENTRY', 'EXIT', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_order_role", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders_order_role",
        "orders",
        "order_role IN ('ENTRY', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )
