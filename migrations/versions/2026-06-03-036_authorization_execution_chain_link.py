"""Link execution intents to bounded live trial authorizations

Revision ID: 036
Revises: 035
Create Date: 2026-06-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_check_constraints(table_name)
    constraints += inspector.get_foreign_keys(table_name)
    return any(constraint.get("name") == constraint_name for constraint in constraints)


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def upgrade() -> None:
    if _dialect_name() != "sqlite" and _has_table("brc_bounded_live_trial_authorizations") and _has_constraint(
        "brc_bounded_live_trial_authorizations",
        "ck_brc_trial_auths_not_consumed",
    ):
        op.drop_constraint(
            "ck_brc_trial_auths_not_consumed",
            "brc_bounded_live_trial_authorizations",
            type_="check",
        )

    if _has_table("execution_intents") and not _has_column("execution_intents", "authorization_id"):
        op.add_column(
            "execution_intents",
            sa.Column("authorization_id", sa.String(length=128), nullable=True),
        )
    if (
        _dialect_name() != "sqlite"
        and _has_table("execution_intents")
        and _has_table("brc_bounded_live_trial_authorizations")
    ):
        if not _has_constraint("execution_intents", "fk_execution_intents_authorization_id"):
            op.create_foreign_key(
                "fk_execution_intents_authorization_id",
                "execution_intents",
                "brc_bounded_live_trial_authorizations",
                ["authorization_id"],
                ["authorization_id"],
                deferrable=True,
                initially="DEFERRED",
            )
    if _has_table("execution_intents") and not _has_index(
        "execution_intents",
        "idx_execution_intents_authorization_id",
    ):
        op.create_index(
            "idx_execution_intents_authorization_id",
            "execution_intents",
            ["authorization_id"],
        )


def downgrade() -> None:
    if _has_table("execution_intents") and _has_index(
        "execution_intents",
        "idx_execution_intents_authorization_id",
    ):
        op.drop_index("idx_execution_intents_authorization_id", table_name="execution_intents")
    if _dialect_name() != "sqlite" and _has_table("execution_intents") and _has_constraint(
        "execution_intents",
        "fk_execution_intents_authorization_id",
    ):
        op.drop_constraint(
            "fk_execution_intents_authorization_id",
            "execution_intents",
            type_="foreignkey",
        )
    if _has_table("execution_intents") and _has_column("execution_intents", "authorization_id"):
        op.drop_column("execution_intents", "authorization_id")
    if _dialect_name() != "sqlite" and _has_table("brc_bounded_live_trial_authorizations") and not _has_constraint(
        "brc_bounded_live_trial_authorizations",
        "ck_brc_trial_auths_not_consumed",
    ):
        op.create_check_constraint(
            "ck_brc_trial_auths_not_consumed",
            "brc_bounded_live_trial_authorizations",
            "consumed IS FALSE",
        )
