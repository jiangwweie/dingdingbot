"""Enforce current identity and immutable detector-decision schema capability.

Revision ID: 141
Revises: 140
Create Date: 2026-07-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "141"
down_revision: Union[str, None] = "140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUDGET_TABLE = "brc_account_budget_current"
FACT_TABLE = "brc_runtime_fact_snapshots"
EXPOSURE_TABLE = "brc_account_exposure_current"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
HOLD_TABLE = "brc_ticket_bound_scope_freezes"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _enforce_single_budget_current()
    _add_detector_decision_identity()
    _converge_netting_domain_keys()


def downgrade() -> None:
    # Production schema is forward-only.  Added identity and uniqueness are
    # retained so a future forward migration can preserve audit lineage.
    return


def _enforce_single_budget_current() -> None:
    if not _has_table(BUDGET_TABLE):
        return
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT 1 FROM brc_account_budget_current
            GROUP BY account_id, runtime_profile_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate:
        raise RuntimeError(
            "schema_capability_blocked:account_budget_current_duplicate_scope"
        )
    op.execute(
        "ALTER TABLE brc_account_budget_current "
        "DROP CONSTRAINT IF EXISTS uq_brc_account_budget_current_scope"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_brc_account_budget_current_account_profile "
        "ON brc_account_budget_current (account_id, runtime_profile_id)"
    )


def _add_detector_decision_identity() -> None:
    if not _has_table(FACT_TABLE):
        return
    columns = _columns(FACT_TABLE)
    additions = (
        ("lane_identity_key", sa.String(192)),
        ("event_spec_id", sa.String(192)),
        ("event_spec_version", sa.String(96)),
        ("detector_key", sa.String(128)),
        ("decision_identity", sa.BIGINT()),
        ("source_watermark", sa.String(256)),
        ("producer_runtime_head", sa.String(128)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column(FACT_TABLE, sa.Column(name, column_type, nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_brc_runtime_fact_pretrade_detector_identity "
        "ON brc_runtime_fact_snapshots "
        "(lane_identity_key, event_spec_id, event_spec_version, detector_key, decision_identity) "
        "WHERE fact_surface = 'pretrade_strategy' "
        "AND lane_identity_key IS NOT NULL "
        "AND event_spec_id IS NOT NULL "
        "AND event_spec_version IS NOT NULL "
        "AND detector_key IS NOT NULL "
        "AND decision_identity IS NOT NULL"
    )


def _converge_netting_domain_keys() -> None:
    """Backfill only rows whose typed identity makes the target unambiguous."""

    for table_name in (EXPOSURE_TABLE, COMMAND_TABLE, HOLD_TABLE):
        if not _has_table(table_name) or not _has_netting_identity(table_name):
            continue
        op.execute(
            f"ALTER TABLE {table_name} "
            "ALTER COLUMN netting_domain_key TYPE VARCHAR(640)"
        )
        _assert_no_active_netting_identity_collision(table_name)
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET netting_domain_key = account_id || '|' || exchange_instrument_id
                    || '|' || position_mode || '|' || position_bucket
                WHERE { _valid_netting_identity_predicate() }
                  AND netting_domain_key IS DISTINCT FROM
                    account_id || '|' || exchange_instrument_id
                    || '|' || position_mode || '|' || position_bucket
                """
            )
        )


def _has_netting_identity(table_name: str) -> bool:
    required = {
        "account_id",
        "exchange_instrument_id",
        "position_mode",
        "position_bucket",
        "netting_domain_key",
    }
    return required <= _columns(table_name)


def _valid_netting_identity_predicate() -> str:
    return """
        account_id IS NOT NULL AND btrim(account_id) <> ''
        AND exchange_instrument_id IS NOT NULL
        AND btrim(exchange_instrument_id) <> ''
        AND exchange_instrument_id <> 'legacy_unknown_instrument'
        AND position_mode IN ('one_way', 'hedge')
        AND position_bucket IN ('BOTH', 'LONG', 'SHORT')
    """


def _assert_no_active_netting_identity_collision(table_name: str) -> None:
    """Never merge two active safety facts merely because their old key drifted."""

    columns = _columns(table_name)
    if not {"status", "source_kind", "source_id"} <= columns:
        return
    duplicate = op.get_bind().execute(
        sa.text(
            f"""
            SELECT 1 FROM {table_name}
            WHERE status IN ('active', 'prepared', 'dispatching', 'outcome_unknown')
              AND { _valid_netting_identity_predicate() }
            GROUP BY account_id, exchange_instrument_id, position_mode, position_bucket,
                     source_kind, source_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate:
        raise RuntimeError(
            "schema_capability_blocked:netting_domain_active_identity_collision"
        )


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table_name)}
