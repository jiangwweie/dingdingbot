from __future__ import annotations

import json

from sqlalchemy import text

from src.application.action_time.exchange_scope import (
    resolve_ticket_bound_exchange_scope,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runner_protection_adjuster import (
    _materialized_exit_protection_set,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_scope_resolves_canonical_identity_to_pg_exchange_instrument(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "resolved"
    assert result.blockers == []
    assert result.scope is not None
    assert result.scope.ticket_id == ticket_id
    assert result.scope.canonical_symbol == "ETHUSDT"
    assert result.scope.exchange_symbol == "ETH/USDT:USDT"
    assert result.scope.exchange_instrument_id.startswith("binance_usdm:")
    assert result.scope.exchange_id == "binance_usdm"
    assert result.scope.side == "long"
    assert result.scope.position_mode == "one_way"
    assert result.scope.position_side is None
    assert result.scope.position_bucket == "BOTH"
    assert result.scope.current_entry_eligible is True
    assert result.scope.account_id


def test_scope_uses_exact_pg_exchange_symbol_without_string_inference(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_exchange_instruments
            SET exchange_symbol = 'ETH-PERP-UNIT'
            WHERE exchange_instrument_id = (
              SELECT exchange_instrument_id
              FROM brc_action_time_tickets
              WHERE ticket_id = :ticket_id
            )
            """
        ),
        {"ticket_id": ticket_id},
    )

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "resolved"
    assert result.scope is not None
    assert result.scope.exchange_symbol == "ETH-PERP-UNIT"


def test_scope_derives_hedge_position_side_from_typed_account_fact(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)
    fact_id = pg_control_connection.execute(
        text(
            """
            SELECT account_mode_snapshot_id
            FROM brc_action_time_tickets
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = :fact_id
            """
        ),
        {
            "fact_id": fact_id,
            "fact_values": json.dumps({
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "account_mode": "hedge",
                "dual_side_position": True,
                "position_mode_safe": True,
            }),
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_exchange_account_modes_current
            SET position_mode = 'hedge',
                dual_side_position = true,
                position_mode_safe = true,
                status = 'current',
                fact_snapshot_id = :fact_id
            WHERE account_id = 'owner-subaccount-runtime-v0'
              AND exchange_id = 'binance_usdm'
            """
        ),
        {"fact_id": fact_id},
    )

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "resolved"
    assert result.scope is not None
    assert result.scope.position_mode == "hedge"
    assert result.scope.position_side == "LONG"
    assert result.scope.position_bucket == "LONG"


def test_scope_preserves_existing_ticket_identity_when_mapping_is_retired(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_symbol_instrument_mappings
            SET status = 'retired'
            WHERE symbol = 'ETHUSDT'
            """
        )
    )

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "resolved"
    assert result.scope is not None
    assert result.scope.exchange_symbol == "ETH/USDT:USDT"
    assert result.scope.current_entry_eligible is False
    assert result.scope.current_entry_blockers == [
        "ticket_exchange_instrument_mapping_not_current"
    ]


def test_scope_blocks_when_account_fact_belongs_to_another_account(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)
    fact_id = pg_control_connection.execute(
        text(
            """
            SELECT account_mode_snapshot_id
            FROM brc_action_time_tickets
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = :fact_id
            """
        ),
        {
            "fact_id": fact_id,
            "fact_values": json.dumps({
                "account_id": "different-account",
                "exchange_id": "binance_usdm",
                "account_mode": "one_way",
                "dual_side_position": False,
                "position_mode_safe": True,
            }),
        },
    )

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "blocked"
    assert result.scope is None
    assert result.blockers == [
        "ticket_exchange_scope_frozen_account_mode_invalid"
    ]


def test_scope_blocks_budget_identity_mismatch(pg_control_connection):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id_for_set(pg_control_connection, set_id)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET side = 'short'
            WHERE budget_reservation_id = (
              SELECT budget_reservation_id
              FROM brc_action_time_tickets
              WHERE ticket_id = :ticket_id
            )
            """
        ),
        {"ticket_id": ticket_id},
    )

    result = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    )

    assert result.status == "blocked"
    assert result.blockers == ["ticket_exchange_scope_budget_side_mismatch"]


def _ticket_id_for_set(conn, set_id: str) -> str:
    return str(
        conn.execute(
            text(
                """
                SELECT ticket_id
                FROM brc_ticket_bound_exit_protection_sets
                WHERE exit_protection_set_id = :set_id
                """
            ),
            {"set_id": set_id},
        ).scalar_one()
    )
