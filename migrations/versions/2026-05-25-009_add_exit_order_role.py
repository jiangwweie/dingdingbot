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


def _existing_order_role_constraint_name() -> str | None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    names = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints("orders")
    }
    for name in ("ck_orders_order_role", "check_orders_order_role"):
        if name in names:
            return name
    return None


def _replace_order_role_constraint(expression: str) -> None:
    existing_name = _existing_order_role_constraint_name()
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("orders", recreate="always") as batch_op:
            if existing_name is not None:
                batch_op.drop_constraint(existing_name, type_="check")
            batch_op.create_check_constraint("ck_orders_order_role", expression)
        return

    if existing_name is not None:
        op.drop_constraint(existing_name, "orders", type_="check")
    op.create_check_constraint("ck_orders_order_role", "orders", expression)


def upgrade() -> None:
    _replace_order_role_constraint(
        "order_role IN ('ENTRY', 'EXIT', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )


def downgrade() -> None:
    _replace_order_role_constraint(
        "order_role IN ('ENTRY', 'SL', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')",
    )
