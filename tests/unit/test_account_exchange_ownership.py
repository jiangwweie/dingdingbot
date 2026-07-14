from __future__ import annotations

import sqlalchemy as sa

from src.application.action_time.account_exchange_ownership import (
    classify_account_exchange_truth,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    ExchangeOpenOrderRow,
    ExchangePositionRow,
    FullAccountRiskSnapshot,
)


def _connection() -> sa.Connection:
    engine = sa.create_engine("sqlite://")
    conn = engine.connect()
    conn.execute(
        sa.text(
            """
            CREATE TABLE brc_ticket_bound_exchange_commands (
              exchange_command_id TEXT PRIMARY KEY,
              ticket_id TEXT NOT NULL,
              exchange_instrument_id TEXT NOT NULL,
              exchange_order_id TEXT,
              client_order_id TEXT,
              order_role TEXT NOT NULL,
              command_state TEXT NOT NULL
            )
            """
        )
    )
    return conn


def _snapshot(*, order: ExchangeOpenOrderRow | None = None, position_mode: str = "one_way") -> FullAccountRiskSnapshot:
    return FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance="600",
        available_balance="500",
        exchange_total_initial_margin="0",
        can_trade=True,
        position_mode=position_mode,
        positions=(
            ExchangePositionRow(
                exchange_symbol="ETHUSDT",
                position_qty="1",
                entry_price="100",
            ),
        ),
        regular_open_orders=(order,) if order else (),
        source_snapshot_id="snapshot-1",
        observed_at_ms=1_752_480_000_000,
        valid_until_ms=1_752_480_060_000,
    )


def _insert_command(
    conn: sa.Connection,
    *,
    command_id: str,
    ticket_id: str,
    exchange_order_id: str,
    client_order_id: str,
    role: str,
    instrument: str = "binance_usdm:ETHUSDT",
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO brc_ticket_bound_exchange_commands (
              exchange_command_id, ticket_id, exchange_instrument_id,
              exchange_order_id, client_order_id, order_role, command_state
            ) VALUES (:command_id, :ticket_id, :instrument, :exchange_order_id,
                      :client_order_id, :role, 'confirmed_submitted')
            """
        ),
        {
            "command_id": command_id,
            "ticket_id": ticket_id,
            "instrument": instrument,
            "exchange_order_id": exchange_order_id,
            "client_order_id": client_order_id,
            "role": role,
        },
    )


def test_owned_order_roles_have_explicit_purpose_not_reduce_only_heuristics() -> None:
    expected = {
        "ENTRY": "working_entry",
        "SL": "initial_stop",
        "TP1": "take_profit",
        "RUNNER_SL": "runner_stop",
        "FINAL_EXIT": "final_exit",
    }
    for role, purpose in expected.items():
        conn = _connection()
        _insert_command(
            conn,
            command_id=f"command-{role}",
            ticket_id="ticket-1",
            exchange_order_id="exchange-1",
            client_order_id="client-1",
            role=role,
        )
        result = classify_account_exchange_truth(
            conn,
            snapshot=_snapshot(
                order=ExchangeOpenOrderRow(
                    exchange_symbol="ETHUSDT",
                    exchange_order_id="exchange-1",
                    client_order_id="client-1",
                    reduce_only=True,
                )
            ),
        )
        assert result.orders[0].ownership_state == "owned_by_ticket"
        assert result.orders[0].purpose == purpose
        conn.close()


def test_unowned_and_conflicting_identities_fail_closed_for_new_entry() -> None:
    conn = _connection()
    external = classify_account_exchange_truth(
        conn,
        snapshot=_snapshot(
            order=ExchangeOpenOrderRow(
                exchange_symbol="ETHUSDT", exchange_order_id="external"
            )
        ),
    )
    assert external.orders[0].ownership_state == "external_unowned"
    assert external.new_entry_allowed is False

    _insert_command(
        conn,
        command_id="command-a",
        ticket_id="ticket-a",
        exchange_order_id="same-exchange",
        client_order_id="client-a",
        role="SL",
    )
    _insert_command(
        conn,
        command_id="command-b",
        ticket_id="ticket-b",
        exchange_order_id="other-exchange",
        client_order_id="same-client",
        role="TP1",
    )
    conflict = classify_account_exchange_truth(
        conn,
        snapshot=_snapshot(
            order=ExchangeOpenOrderRow(
                exchange_symbol="ETHUSDT",
                exchange_order_id="same-exchange",
                client_order_id="same-client",
            )
        ),
    )
    assert conflict.orders[0].ownership_state == "identity_conflict"
    assert conflict.new_entry_allowed is False
    conn.close()


def test_hedge_order_without_position_side_is_ambiguous_and_two_ticket_position_claims_conflict() -> None:
    conn = _connection()
    ambiguous = classify_account_exchange_truth(
        conn,
        snapshot=_snapshot(
            position_mode="hedge",
            order=ExchangeOpenOrderRow(exchange_symbol="ETHUSDT"),
        ),
    )
    assert ambiguous.orders[0].ownership_state == "mode_or_side_ambiguous"

    _insert_command(
        conn,
        command_id="command-a",
        ticket_id="ticket-a",
        exchange_order_id="a",
        client_order_id="a",
        role="ENTRY",
    )
    _insert_command(
        conn,
        command_id="command-b",
        ticket_id="ticket-b",
        exchange_order_id="b",
        client_order_id="b",
        role="ENTRY",
    )
    conflict = classify_account_exchange_truth(conn, snapshot=_snapshot())
    assert conflict.positions[0].ownership_state == "identity_conflict"
    assert conflict.new_entry_allowed is False
    conn.close()
