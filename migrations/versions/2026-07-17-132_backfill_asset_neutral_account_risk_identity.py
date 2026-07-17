"""Backfill asset-neutral account-risk identity from historical facts.

Revision ID: 132
Revises: 131
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "132"
down_revision: Union[str, None] = "131"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TERMINAL_RESERVATION_STATUSES = ("released", "expired", "invalidated")
_TERMINAL_PRE_SUBMIT_TICKET_STATUSES = (
    "expired",
    "finalgate_rejected",
    "invalidated",
    "superseded",
)
_TERMINAL_PRE_SUBMIT_RELEASE_REASON = "terminal_presubmit_ticket_capacity_reclaimed"
_TERMINAL_PRE_SUBMIT_EVIDENCE_REF = "migration:132"
_LEGACY_AUDIT_ONLY_BLOCKER = "legacy_audit_only_identity_unresolved"


def upgrade() -> None:
    bind = op.get_bind()
    _set_session_timeouts(bind)
    _preflight_history_bounds(bind)
    _release_terminal_presubmit_capacity(bind)
    _backfill_candidate_scope_instruments(bind)
    _backfill_reservation_instruments(bind)
    _backfill_exposure_episode_lineage(bind)
    _backfill_asset_neutral_dimensions(bind)
    _mark_unresolved_terminal_history_audit_only(bind)


def downgrade() -> None:
    # Historical-time fact backfill is intentionally immutable and non-destructive.
    return None


def _set_session_timeouts(bind: sa.Connection) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        bind.execute(sa.text("SET LOCAL statement_timeout = '60s'"))


def _preflight_history_bounds(bind: sa.Connection) -> None:
    """Force a cheap DB-side preflight without transferring historical payloads."""

    if not _has_table(bind, "brc_budget_reservations"):
        return
    bind.execute(
        sa.text(
            """
            SELECT count(*) AS history_count,
                   min(budget_reservation_id) AS min_reservation_id,
                   max(budget_reservation_id) AS max_reservation_id
            FROM brc_budget_reservations
            """
        )
    ).first()


def _release_terminal_presubmit_capacity(bind: sa.Connection) -> None:
    """Conservatively reclaim capacity without materializing candidate rows."""

    required_tables = {
        "brc_budget_reservations",
        "brc_action_time_tickets",
        "brc_budget_reservation_events",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_ticket_bound_exchange_commands",
        "brc_account_exposure_current",
    }
    if not required_tables <= _tables(bind):
        return
    required_columns = {
        "brc_budget_reservations": {
            "budget_reservation_id",
            "ticket_id",
            "status",
            "release_reason",
            "released_at_ms",
            "reserved_at_ms",
        },
        "brc_action_time_tickets": {"ticket_id", "status"},
        "brc_budget_reservation_events": {
            "budget_reservation_event_id",
            "budget_reservation_id",
            "from_status",
            "to_status",
            "reason",
            "evidence_ref",
            "created_at_ms",
        },
        "brc_ticket_bound_protected_submit_attempts": {
            "ticket_id",
            "exchange_write_called",
        },
        "brc_ticket_bound_exchange_commands": {
            "ticket_id",
            "command_state",
            "dispatch_started_at_ms",
            "exchange_order_id",
        },
        "brc_account_exposure_current": {
            "owner_ticket_id",
            "position_slot_claimed",
        },
    }
    if any(
        not columns <= _columns(bind, table_name)
        for table_name, columns in required_columns.items()
    ):
        # Missing safety evidence must fail closed: leave capacity consumed.
        return

    eligible_predicate = _terminal_presubmit_eligible_predicate()
    event_id_expression = (
        "'budget_reservation_event:migration-132:' || "
        "brc_budget_reservations.budget_reservation_id"
    )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO brc_budget_reservation_events (
              budget_reservation_event_id, budget_reservation_id,
              from_status, to_status, reason, evidence_ref, created_at_ms
            )
            SELECT {event_id_expression}, budget_reservation_id,
                   'consumed', 'released', :reason, :evidence_ref,
                   COALESCE(reserved_at_ms, 0)
            FROM brc_budget_reservations
            WHERE {eligible_predicate}
              AND NOT EXISTS (
                SELECT 1
                FROM brc_budget_reservation_events AS existing_event
                WHERE existing_event.budget_reservation_event_id = {event_id_expression}
              )
            """
        ),
        {
            "reason": _TERMINAL_PRE_SUBMIT_RELEASE_REASON,
            "evidence_ref": _TERMINAL_PRE_SUBMIT_EVIDENCE_REF,
        },
    )
    bind.execute(
        sa.text(
            f"""
            UPDATE brc_budget_reservations
            SET status = 'released',
                release_reason = :reason,
                released_at_ms = COALESCE(released_at_ms, reserved_at_ms, 0)
            WHERE {eligible_predicate}
            """
        ),
        {"reason": _TERMINAL_PRE_SUBMIT_RELEASE_REASON},
    )


def _terminal_presubmit_eligible_predicate() -> str:
    statuses = ", ".join(
        repr(status) for status in _TERMINAL_PRE_SUBMIT_TICKET_STATUSES
    )
    return f"""
      brc_budget_reservations.status = 'consumed'
      AND brc_budget_reservations.ticket_id IS NOT NULL
      AND EXISTS (
        SELECT 1
        FROM brc_action_time_tickets AS terminal_ticket
        WHERE terminal_ticket.ticket_id = brc_budget_reservations.ticket_id
          AND terminal_ticket.status IN ({statuses})
      )
      AND NOT EXISTS (
        SELECT 1
        FROM brc_ticket_bound_protected_submit_attempts AS submit_attempt
        WHERE submit_attempt.ticket_id = brc_budget_reservations.ticket_id
          AND submit_attempt.exchange_write_called = true
      )
      AND NOT EXISTS (
        SELECT 1
        FROM brc_ticket_bound_exchange_commands AS exchange_command
        WHERE exchange_command.ticket_id = brc_budget_reservations.ticket_id
          AND (
            exchange_command.dispatch_started_at_ms IS NOT NULL
            OR exchange_command.exchange_order_id IS NOT NULL
            OR exchange_command.command_state IS NULL
            OR exchange_command.command_state NOT IN ('prepared', 'reconciled_absent')
          )
      )
      AND NOT EXISTS (
        SELECT 1
        FROM brc_account_exposure_current AS account_exposure
        WHERE account_exposure.owner_ticket_id = brc_budget_reservations.ticket_id
          AND account_exposure.position_slot_claimed = true
      )
    """


def _backfill_candidate_scope_instruments(bind: sa.Connection) -> None:
    if not {
        "brc_strategy_group_candidate_scope",
        "brc_symbol_instrument_mappings",
    } <= _tables(bind):
        return
    bind.execute(
        sa.text(
            """
            UPDATE brc_strategy_group_candidate_scope
            SET exchange_instrument_id = (
              SELECT mapping.exchange_instrument_id
              FROM brc_symbol_instrument_mappings AS mapping
              WHERE mapping.symbol = brc_strategy_group_candidate_scope.symbol
                AND mapping.valid_from_ms <= brc_strategy_group_candidate_scope.valid_from_ms
                AND (
                  mapping.valid_until_ms IS NULL
                  OR brc_strategy_group_candidate_scope.valid_from_ms < mapping.valid_until_ms
                )
              ORDER BY mapping.valid_from_ms DESC, mapping.mapping_id DESC
              LIMIT 1
            )
            WHERE exchange_instrument_id IS NULL OR trim(exchange_instrument_id) = ''
            """
        )
    )


def _backfill_reservation_instruments(bind: sa.Connection) -> None:
    if "brc_budget_reservations" not in _tables(bind):
        return
    tables = _tables(bind)
    if "brc_action_time_tickets" in tables:
        bind.execute(
            sa.text(
                """
                UPDATE brc_budget_reservations
                SET exchange_instrument_id = (
                  SELECT ticket.exchange_instrument_id
                  FROM brc_action_time_tickets AS ticket
                  WHERE ticket.ticket_id = brc_budget_reservations.ticket_id
                  LIMIT 1
                )
                WHERE (exchange_instrument_id IS NULL OR trim(exchange_instrument_id) = '')
                  AND ticket_id IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM brc_action_time_tickets AS ticket
                    WHERE ticket.ticket_id = brc_budget_reservations.ticket_id
                      AND ticket.exchange_instrument_id IS NOT NULL
                      AND trim(ticket.exchange_instrument_id) <> ''
                  )
                """
            )
        )
    if "brc_symbol_instrument_mappings" not in tables:
        return
    bind.execute(
        sa.text(
            """
            UPDATE brc_budget_reservations
            SET exchange_instrument_id = (
              SELECT mapping.exchange_instrument_id
              FROM brc_symbol_instrument_mappings AS mapping
              WHERE mapping.symbol = brc_budget_reservations.symbol
                AND mapping.valid_from_ms <= brc_budget_reservations.reserved_at_ms
                AND (
                  mapping.valid_until_ms IS NULL
                  OR brc_budget_reservations.reserved_at_ms < mapping.valid_until_ms
                )
              ORDER BY mapping.valid_from_ms DESC, mapping.mapping_id DESC
              LIMIT 1
            )
            WHERE exchange_instrument_id IS NULL OR trim(exchange_instrument_id) = ''
            """
        )
    )


def _backfill_asset_neutral_dimensions(bind: sa.Connection) -> None:
    if "brc_exchange_instruments" not in _tables(bind):
        return
    _backfill_table_instrument_dimensions(
        bind,
        table_name="brc_action_time_tickets",
        id_column="ticket_id",
        instrument_column="exchange_instrument_id",
        asset_class_column="asset_class",
        instrument_type_column="instrument_type",
    )
    _backfill_table_instrument_dimensions(
        bind,
        table_name="brc_budget_reservations",
        id_column="budget_reservation_id",
        instrument_column="exchange_instrument_id",
        asset_class_column="asset_class",
        instrument_type_column="instrument_type",
    )
    _backfill_table_instrument_dimensions(
        bind,
        table_name="brc_account_exposure_current",
        id_column="account_exposure_current_id",
        instrument_column="exchange_instrument_id",
        asset_class_column="asset_class",
        instrument_type_column="instrument_type",
    )


def _backfill_exposure_episode_lineage(bind: sa.Connection) -> None:
    tables = _tables(bind)
    if "brc_budget_reservations" in tables and {
        "ticket_id",
        "exposure_episode_id",
    } <= _columns(bind, "brc_budget_reservations"):
        bind.execute(sa.text("""
          UPDATE brc_budget_reservations
          SET exposure_episode_id = 'exposure_episode:migration-132:' || ticket_id
          WHERE ticket_id IS NOT NULL AND trim(ticket_id) <> ''
            AND (exposure_episode_id IS NULL OR trim(exposure_episode_id) = '')
        """))
    if "brc_action_time_tickets" in tables and {
        "ticket_id",
        "exposure_episode_id",
    } <= _columns(bind, "brc_action_time_tickets"):
        bind.execute(sa.text("""
          UPDATE brc_action_time_tickets
          SET exposure_episode_id = COALESCE(
            (SELECT reservation.exposure_episode_id
             FROM brc_budget_reservations AS reservation
             WHERE reservation.ticket_id = brc_action_time_tickets.ticket_id
             LIMIT 1),
            'exposure_episode:migration-132:' || ticket_id
          )
          WHERE exposure_episode_id IS NULL OR trim(exposure_episode_id) = ''
        """))
    for table_name in (
        "brc_ticket_bound_exchange_commands",
        "brc_ticket_bound_reconciliation_ticks",
        "brc_live_outcome_ledger",
    ):
        if table_name not in tables or not {
            "ticket_id",
            "exposure_episode_id",
        } <= _columns(bind, table_name):
            continue
        bind.execute(sa.text(f"""
          UPDATE {table_name}
          SET exposure_episode_id = (
            SELECT ticket.exposure_episode_id
            FROM brc_action_time_tickets AS ticket
            WHERE ticket.ticket_id = {table_name}.ticket_id
            LIMIT 1
          )
          WHERE (exposure_episode_id IS NULL OR trim(exposure_episode_id) = '')
            AND EXISTS (
              SELECT 1 FROM brc_action_time_tickets AS ticket
              WHERE ticket.ticket_id = {table_name}.ticket_id
                AND ticket.exposure_episode_id IS NOT NULL
                AND trim(ticket.exposure_episode_id) <> ''
            )
        """))
    if "brc_account_exposure_current" in tables and {
        "owner_ticket_id",
        "current_exposure_episode_id",
        "ownership_state",
    } <= _columns(bind, "brc_account_exposure_current"):
        bind.execute(sa.text("""
          UPDATE brc_account_exposure_current
          SET current_exposure_episode_id = (
            SELECT ticket.exposure_episode_id
            FROM brc_action_time_tickets AS ticket
            WHERE ticket.ticket_id = brc_account_exposure_current.owner_ticket_id
            LIMIT 1
          )
          WHERE ownership_state IN
              ('owned_by_ticket', 'owned_by_other_known_ticket')
            AND (current_exposure_episode_id IS NULL
                 OR trim(current_exposure_episode_id) = '')
        """))


def _backfill_table_instrument_dimensions(
    bind: sa.Connection,
    *,
    table_name: str,
    id_column: str,
    instrument_column: str,
    asset_class_column: str,
    instrument_type_column: str,
) -> None:
    if table_name not in _tables(bind):
        return
    columns = _columns(bind, table_name)
    required = {
        id_column,
        instrument_column,
        asset_class_column,
        instrument_type_column,
    }
    if not required <= columns:
        return
    bind.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET {asset_class_column} = CASE
                  WHEN (
                    SELECT instrument.asset_class
                    FROM brc_exchange_instruments AS instrument
                    WHERE instrument.exchange_instrument_id = {table_name}.{instrument_column}
                    LIMIT 1
                  ) = 'crypto_perpetual' THEN 'crypto'
                  ELSE (
                    SELECT instrument.asset_class
                    FROM brc_exchange_instruments AS instrument
                    WHERE instrument.exchange_instrument_id = {table_name}.{instrument_column}
                    LIMIT 1
                  )
                END,
                {instrument_type_column} = COALESCE(
                  (
                    SELECT instrument.instrument_type
                    FROM brc_exchange_instruments AS instrument
                    WHERE instrument.exchange_instrument_id = {table_name}.{instrument_column}
                    LIMIT 1
                  ),
                  CASE
                    WHEN (
                      SELECT instrument.asset_class
                      FROM brc_exchange_instruments AS instrument
                      WHERE instrument.exchange_instrument_id = {table_name}.{instrument_column}
                      LIMIT 1
                    ) = 'crypto_perpetual' THEN 'perpetual'
                  END
                )
            WHERE ({asset_class_column} IS NULL OR trim({asset_class_column}) = '')
              AND {instrument_column} IS NOT NULL
              AND trim({instrument_column}) <> ''
            """
        )
    )


def _mark_unresolved_terminal_history_audit_only(bind: sa.Connection) -> None:
    if "brc_budget_reservations" not in _tables(bind):
        return
    statuses = ", ".join(repr(status) for status in _TERMINAL_RESERVATION_STATUSES)
    bind.execute(
        sa.text(
            f"""
            UPDATE brc_budget_reservations
            SET reconciliation_state = COALESCE(reconciliation_state, 'legacy_audit_only'),
                current_first_blocker = COALESCE(
                  current_first_blocker, :legacy_audit_only_blocker
                )
            WHERE status IN ({statuses})
              AND (exchange_instrument_id IS NULL OR trim(exchange_instrument_id) = '')
            """
        ),
        {"legacy_audit_only_blocker": _LEGACY_AUDIT_ONLY_BLOCKER},
    )


def _tables(bind: sa.Connection) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _has_table(bind: sa.Connection, table_name: str) -> bool:
    return table_name in _tables(bind)


def _columns(bind: sa.Connection, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns(table_name)
    }
