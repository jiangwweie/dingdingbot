"""Allow temporary tiny-live protected submit mode.

Revision ID: 094
Revises: 093
Create Date: 2026-07-08

This migration is intentionally narrow and temporary. It only admits the
ticket-bound ENTRY + SL + TP1 live aperture used to validate exchange behavior;
it does not relax forbidden profile, sizing, withdrawal, or transfer effects.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "094"
down_revision: Union[str, None] = "093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UP_SUBMIT_MODE = (
    "submit_mode IN ('disabled_smoke', 'real_gateway_action', "
    "'temp_tiny_live_protected_submit')"
)
DOWN_SUBMIT_MODE = "submit_mode IN ('disabled_smoke', 'real_gateway_action')"
UP_SUBMITTED_EFFECTS = (
    "status <> 'submitted' OR "
    "(submit_mode IN ('real_gateway_action', 'temp_tiny_live_protected_submit') "
    "AND submit_allowed = true "
    "AND official_operation_layer_submit_called = true "
    "AND exchange_write_called = true "
    "AND order_lifecycle_called = true)"
)
DOWN_SUBMITTED_EFFECTS = (
    "status <> 'submitted' OR "
    "(submit_mode = 'real_gateway_action' "
    "AND submit_allowed = true "
    "AND official_operation_layer_submit_called = true "
    "AND exchange_write_called = true "
    "AND order_lifecycle_called = true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(submit_mode=UP_SUBMIT_MODE, submitted_effects=UP_SUBMITTED_EFFECTS)
        return
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_protected_submit_attempts
        DROP CONSTRAINT IF EXISTS ck_brc_ticket_submit_mode
        """
    )
    op.create_check_constraint(
        "ck_brc_ticket_submit_mode",
        "brc_ticket_bound_protected_submit_attempts",
        UP_SUBMIT_MODE,
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_protected_submit_attempts
        DROP CONSTRAINT IF EXISTS ck_brc_ticket_submit_submitted_effects
        """
    )
    op.create_check_constraint(
        "ck_brc_ticket_submit_submitted_effects",
        "brc_ticket_bound_protected_submit_attempts",
        UP_SUBMITTED_EFFECTS,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(
            submit_mode=DOWN_SUBMIT_MODE,
            submitted_effects=DOWN_SUBMITTED_EFFECTS,
        )
        return
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_protected_submit_attempts
        DROP CONSTRAINT IF EXISTS ck_brc_ticket_submit_submitted_effects
        """
    )
    op.create_check_constraint(
        "ck_brc_ticket_submit_submitted_effects",
        "brc_ticket_bound_protected_submit_attempts",
        DOWN_SUBMITTED_EFFECTS,
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_protected_submit_attempts
        DROP CONSTRAINT IF EXISTS ck_brc_ticket_submit_mode
        """
    )
    op.create_check_constraint(
        "ck_brc_ticket_submit_mode",
        "brc_ticket_bound_protected_submit_attempts",
        DOWN_SUBMIT_MODE,
    )


def _sqlite_rebuild(*, submit_mode: str, submitted_effects: str) -> None:
    with op.batch_alter_table("brc_ticket_bound_protected_submit_attempts") as batch:
        batch.drop_constraint("ck_brc_ticket_submit_submitted_effects", type_="check")
        batch.drop_constraint("ck_brc_ticket_submit_mode", type_="check")
        batch.create_check_constraint("ck_brc_ticket_submit_mode", submit_mode)
        batch.create_check_constraint(
            "ck_brc_ticket_submit_submitted_effects",
            submitted_effects,
        )
