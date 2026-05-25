"""Add explicit EXIT order role

Revision ID: 009
Revises: 008
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_existing_order_role_constraint() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    names = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints("orders")
    }
    for name in ("ck_orders_order_role", "check_orders_order_role"):
        if name in names:
            op.drop_constraint(name, "orders", type_="check")
            return


def upgrade() -> None:
    _drop_existing_order_role_constraint()
    op.create_check_constraint(
        "ck_orders_order_role",
        "orders",
        "order_role IN ('ENTRY', 'EXIT', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )


def downgrade() -> None:
    _drop_existing_order_role_constraint()
    op.create_check_constraint(
        "ck_orders_order_role",
        "orders",
        "order_role IN ('ENTRY', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )
