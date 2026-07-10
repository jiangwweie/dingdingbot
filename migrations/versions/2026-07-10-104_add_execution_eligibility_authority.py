"""Add execution-eligibility authority to the pre-trade chain.

Revision ID: 104
Revises: 103
Create Date: 2026-07-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "104"
down_revision: Union[str, None] = "103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EVENT_SPEC_TABLE = "brc_strategy_side_event_specs"
AUTHORITY_TRANSITION_TABLES = (
    "brc_live_signal_events",
    "brc_promotion_candidates",
    "brc_action_time_lane_inputs",
    "brc_action_time_tickets",
    "brc_runtime_safety_state_snapshots",
    "brc_ticket_bound_submit_mode_decisions",
    "brc_ticket_bound_protected_submit_attempts",
)

SIGNAL_GRADES = (
    "observe_only_signal",
    "trial_grade_signal",
    "production_grade_signal",
    "invalid_signal",
)
EXECUTION_MODES = ("observe_only", "trial_live", "production_live")


def upgrade() -> None:
    _add_column(
        EVENT_SPEC_TABLE,
        sa.Column(
            "declared_signal_grade",
            sa.String(64),
            nullable=False,
            server_default="observe_only_signal",
        ),
    )
    _add_column(
        EVENT_SPEC_TABLE,
        sa.Column(
            "declared_required_execution_mode",
            sa.String(64),
            nullable=False,
            server_default="observe_only",
        ),
    )
    _add_column(
        EVENT_SPEC_TABLE,
        sa.Column(
            "execution_eligibility_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    _add_authority_checks(
        EVENT_SPEC_TABLE,
        grade_column="declared_signal_grade",
        mode_column="declared_required_execution_mode",
        eligible_column="execution_eligibility_enabled",
        prefix="event_auth",
    )

    for table_name in AUTHORITY_TRANSITION_TABLES:
        _add_column(
            table_name,
            sa.Column(
                "signal_grade",
                sa.String(64),
                nullable=False,
                server_default="observe_only_signal",
            ),
        )
        _add_column(
            table_name,
            sa.Column(
                "required_execution_mode",
                sa.String(64),
                nullable=False,
                server_default="observe_only",
            ),
        )
        _add_column(
            table_name,
            sa.Column(
                "execution_eligible",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        _add_column(
            table_name,
            sa.Column(
                "authority_source_ref",
                sa.String(256),
                nullable=False,
                server_default="migration-104:legacy-observe-only",
            ),
        )
        _add_authority_checks(
            table_name,
            grade_column="signal_grade",
            mode_column="required_execution_mode",
            eligible_column="execution_eligible",
            prefix=_constraint_prefix(table_name),
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(AUTHORITY_TRANSITION_TABLES):
        _drop_authority_checks(table_name, _constraint_prefix(table_name), bind)
        for column_name in (
            "authority_source_ref",
            "execution_eligible",
            "required_execution_mode",
            "signal_grade",
        ):
            if _has_column(table_name, column_name):
                op.drop_column(table_name, column_name)

    _drop_authority_checks(EVENT_SPEC_TABLE, "event_auth", bind)
    for column_name in (
        "execution_eligibility_enabled",
        "declared_required_execution_mode",
        "declared_signal_grade",
    ):
        if _has_column(EVENT_SPEC_TABLE, column_name):
            op.drop_column(EVENT_SPEC_TABLE, column_name)


def _add_column(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, str(column.name)):
        op.add_column(table_name, column)


def _add_authority_checks(
    table_name: str,
    *,
    grade_column: str,
    mode_column: str,
    eligible_column: str,
    prefix: str,
) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    grade_values = ", ".join(repr(value) for value in SIGNAL_GRADES)
    mode_values = ", ".join(repr(value) for value in EXECUTION_MODES)
    checks = {
        f"ck_brc_{prefix}_grade": f"{grade_column} IN ({grade_values})",
        f"ck_brc_{prefix}_mode": f"{mode_column} IN ({mode_values})",
        f"ck_brc_{prefix}_mapping": (
            f"({grade_column} = 'observe_only_signal' AND {mode_column} = 'observe_only') OR "
            f"({grade_column} = 'trial_grade_signal' AND {mode_column} = 'trial_live') OR "
            f"({grade_column} = 'production_grade_signal' AND {mode_column} = 'production_live') OR "
            f"({grade_column} = 'invalid_signal' AND {mode_column} = 'observe_only')"
        ),
        f"ck_brc_{prefix}_eligible": (
            f"{eligible_column} = false OR "
            f"({grade_column} IN ('trial_grade_signal', 'production_grade_signal') "
            f"AND {mode_column} IN ('trial_live', 'production_live'))"
        ),
    }
    for name, condition in checks.items():
        op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {name}")
        op.create_check_constraint(name, table_name, condition)


def _drop_authority_checks(table_name: str, prefix: str, bind: sa.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    for suffix in ("eligible", "mapping", "mode", "grade"):
        op.execute(
            f"ALTER TABLE {table_name} "
            f"DROP CONSTRAINT IF EXISTS ck_brc_{prefix}_{suffix}"
        )


def _constraint_prefix(table_name: str) -> str:
    prefixes = {
        "brc_live_signal_events": "live_sig_auth",
        "brc_promotion_candidates": "promo_auth",
        "brc_action_time_lane_inputs": "lane_auth",
        "brc_action_time_tickets": "ticket_auth",
        "brc_runtime_safety_state_snapshots": "safety_auth",
        "brc_ticket_bound_submit_mode_decisions": "submit_mode_auth",
        "brc_ticket_bound_protected_submit_attempts": "submit_attempt_auth",
    }
    return prefixes[table_name]


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )
