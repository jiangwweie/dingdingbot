"""Add explicit Owner dynamic execution-risk policy.

Revision ID: 115
Revises: 114
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "115"
down_revision: Union[str, None] = "114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_owner_policy_current"
BUDGET_TABLE = "brc_budget_reservations"
TICKET_TABLE = "brc_action_time_tickets"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
LIVE_OUTCOME_TABLE = "brc_live_outcome_ledger"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        _add_columns(
            TABLE,
            (
                ("planned_stop_risk_fraction", sa.Numeric(8, 6), False, "0.03"),
                ("max_initial_margin_utilization", sa.Numeric(8, 6), False, "0.90"),
                ("max_leverage", sa.Integer(), False, "10"),
            ),
        )

    for current_table in (BUDGET_TABLE, TICKET_TABLE):
        if sa.inspect(op.get_bind()).has_table(current_table):
            _add_columns(
                current_table,
                (
                    ("effective_notional", sa.Numeric(36, 18), True, None),
                    ("selected_leverage", sa.Integer(), True, None),
                    ("planned_stop_risk_budget", sa.Numeric(36, 18), True, None),
                    ("planned_stop_risk", sa.Numeric(36, 18), True, None),
                ),
            )
    if sa.inspect(op.get_bind()).has_table(COMMAND_TABLE):
        _add_columns(
            COMMAND_TABLE,
            (("desired_leverage", sa.Integer(), True, None),),
        )
    if sa.inspect(op.get_bind()).has_table(LIVE_OUTCOME_TABLE):
        _add_columns(
            LIVE_OUTCOME_TABLE,
            (("entry_slippage", sa.Numeric(36, 18), True, None),),
        )

    if sa.inspect(op.get_bind()).has_table(TABLE) and op.get_bind().dialect.name != "sqlite":
        op.create_check_constraint(
            "ck_brc_owner_policy_current_stop_risk_fraction",
            TABLE,
            "planned_stop_risk_fraction > 0 AND planned_stop_risk_fraction <= 1",
        )
        op.create_check_constraint(
            "ck_brc_owner_policy_current_margin_utilization",
            TABLE,
            "max_initial_margin_utilization > 0 AND max_initial_margin_utilization <= 1",
        )
        op.create_check_constraint(
            "ck_brc_owner_policy_current_max_leverage",
            TABLE,
            "max_leverage >= 1 AND max_leverage <= 125",
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(LIVE_OUTCOME_TABLE):
        _drop_columns(LIVE_OUTCOME_TABLE, ("entry_slippage",))
    if sa.inspect(op.get_bind()).has_table(COMMAND_TABLE):
        _drop_columns(COMMAND_TABLE, ("desired_leverage",))
    for current_table in (TICKET_TABLE, BUDGET_TABLE):
        if sa.inspect(op.get_bind()).has_table(current_table):
            _drop_columns(
                current_table,
                (
                    "planned_stop_risk",
                    "planned_stop_risk_budget",
                    "selected_leverage",
                    "effective_notional",
                ),
            )
    if not sa.inspect(op.get_bind()).has_table(TABLE):
        return
    if op.get_bind().dialect.name != "sqlite":
        for name in (
            "ck_brc_owner_policy_current_max_leverage",
            "ck_brc_owner_policy_current_margin_utilization",
            "ck_brc_owner_policy_current_stop_risk_fraction",
        ):
            op.drop_constraint(name, TABLE, type_="check")
    _drop_columns(
        TABLE,
        (
            "max_leverage",
            "max_initial_margin_utilization",
            "planned_stop_risk_fraction",
        ),
    )


def _add_columns(
    table: str,
    additions: tuple[tuple[str, sa.types.TypeEngine, bool, str | None], ...],
) -> None:
    columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)
    }
    for name, column_type, nullable, default in additions:
        if name in columns:
            continue
        kwargs: dict[str, object] = {"nullable": nullable}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column(table, sa.Column(name, column_type, **kwargs))


def _drop_columns(table: str, names: tuple[str, ...]) -> None:
    columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)
    }
    for name in names:
        if name not in columns:
            continue
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.drop_column(name)
        else:
            op.drop_column(table, name)
