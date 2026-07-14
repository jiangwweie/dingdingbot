from __future__ import annotations

from copy import deepcopy

import pytest
from sqlalchemy import text

from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.exchange_command import (
    materialize_ticket_bound_exchange_commands,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_real_submit_prepare_commits_entry_sl_tp1_commands(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)

    prepared = _prepare_real_submit(pg_control_connection, ids)
    commands = _exchange_command_rows(pg_control_connection)

    assert prepared["status"] == "submit_prepared"
    assert [row["order_role"] for row in commands] == ["ENTRY", "SL", "TP1"]
    assert {row["command_state"] for row in commands} == {"prepared"}
    assert len({row["client_order_id"] for row in commands}) == 3
    assert all(len(row["client_order_id"]) <= 36 for row in commands)
    assert all(
        row["account_id"] == "owner-subaccount-runtime-v0"
        for row in commands
    )
    assert all(
        row["exchange_instrument_id"] == "binance_usdm:ETH/USDT:USDT"
        for row in commands
    )
    assert all(row["gateway_symbol"] == "ETH/USDT:USDT" for row in commands)


def test_repeated_materialization_reuses_identity_and_rejects_request_mutation(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    first = _exchange_command_rows(pg_control_connection)

    materialize_ticket_bound_exchange_commands(
        pg_control_connection,
        attempt=prepared,
        now_ms=NOW_MS + 4100,
    )
    assert _exchange_command_rows(pg_control_connection) == first

    mutated = deepcopy(prepared)
    mutated["submit_request"]["orders"][0]["amount"] = "999"
    with pytest.raises(
        ValueError,
        match="exchange_command_request_fingerprint_mismatch",
    ):
        materialize_ticket_bound_exchange_commands(
            pg_control_connection,
            attempt=mutated,
            now_ms=NOW_MS + 4200,
        )


def _exchange_command_rows(conn) -> list[dict]:
    return [
        dict(row)
        for row in conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "ORDER BY CASE order_role "
                "WHEN 'ENTRY' THEN 1 WHEN 'SL' THEN 2 WHEN 'TP1' THEN 3 ELSE 4 END"
            )
        ).mappings()
    ]
