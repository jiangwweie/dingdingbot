from __future__ import annotations

import json

from sqlalchemy import text

from src.application.action_time.exchange_order_ownership import (
    classify_exchange_order_ownership,
)
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


def test_global_ownership_distinguishes_current_ticket_and_unowned_order(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id(pg_control_connection, set_id)
    scope = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    ).scope
    assert scope is not None
    sl_exchange_id = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id FROM brc_ticket_bound_exit_protection_orders "
            "WHERE role = 'SL'"
        )
    ).scalar_one()

    results = classify_exchange_order_ownership(
        pg_control_connection,
        current_scope=scope,
        open_orders=[
            {
                "exchange_order_id": sl_exchange_id,
                "client_order_id": "",
                "position_side": "",
            },
            {
                "exchange_order_id": "unowned-order",
                "client_order_id": "unowned-client",
                "position_side": "",
            },
        ],
        now_ms=NOW_MS + 10_000,
    )

    assert [item.ownership_class for item in results] == [
        "owned_by_current_ticket",
        "unowned_same_domain",
    ]
    assert results[0].blocks_current_domain is False
    assert results[1].blocker == "exchange_only_unknown_order"


def test_exchange_and_client_identity_disagreement_is_hard_conflict(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id(pg_control_connection, set_id)
    scope = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    ).scope
    assert scope is not None
    rows = list(
        pg_control_connection.execute(
            text(
                "SELECT exchange_command_id, client_order_id "
                "FROM brc_ticket_bound_exchange_commands "
                "ORDER BY order_role"
            )
        ).mappings()
    )
    assert rows
    sl_exchange_id = pg_control_connection.execute(
        text(
            "SELECT exchange_order_id FROM brc_ticket_bound_exit_protection_orders "
            "WHERE role = 'SL'"
        )
    ).scalar_one()
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET ticket_id = 'other-ticket' "
            "WHERE exchange_command_id = :command_id"
        ),
        {"command_id": rows[0]["exchange_command_id"]},
    )

    result = classify_exchange_order_ownership(
        pg_control_connection,
        current_scope=scope,
        open_orders=[
            {
                "exchange_order_id": sl_exchange_id,
                "client_order_id": rows[0]["client_order_id"],
            }
        ],
        now_ms=NOW_MS + 10_000,
    )[0]

    assert result.ownership_class == "identity_conflict"
    assert result.blocks_current_domain is True


def test_hedge_unowned_order_without_position_side_is_ambiguous(
    pg_control_connection,
):
    set_id = _materialized_exit_protection_set(pg_control_connection)
    ticket_id = _ticket_id(pg_control_connection, set_id)
    fact_id = pg_control_connection.execute(
        text(
            "SELECT account_mode_snapshot_id FROM brc_action_time_tickets "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    ).scalar_one()
    values = json.dumps(
        {
            "account_id": "owner-subaccount-runtime-v0",
            "exchange_id": "binance_usdm",
            "account_mode": "hedge",
            "dual_side_position": True,
            "position_mode_safe": True,
        }
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_fact_snapshots SET fact_values = :values "
            "WHERE fact_snapshot_id = :fact_id"
        ),
        {"values": values, "fact_id": fact_id},
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_exchange_account_modes_current "
            "SET position_mode = 'hedge', dual_side_position = true "
            "WHERE account_id = 'owner-subaccount-runtime-v0'"
        )
    )
    scope = resolve_ticket_bound_exchange_scope(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 10_000,
    ).scope
    assert scope is not None

    result = classify_exchange_order_ownership(
        pg_control_connection,
        current_scope=scope,
        open_orders=[{"exchange_order_id": "unknown", "position_side": ""}],
        now_ms=NOW_MS + 10_000,
    )[0]

    assert result.ownership_class == "mode_or_side_ambiguous"
    assert result.blocker == "exchange_order_position_side_ambiguous"


def _ticket_id(conn, set_id: str) -> str:
    return str(
        conn.execute(
            text(
                "SELECT ticket_id FROM brc_ticket_bound_exit_protection_sets "
                "WHERE exit_protection_set_id = :set_id"
            ),
            {"set_id": set_id},
        ).scalar_one()
    )
