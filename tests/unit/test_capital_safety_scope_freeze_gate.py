from __future__ import annotations

import json

from sqlalchemy import text

from src.application.action_time import action_time_ticket as ticket_materializer
from src.application.action_time import finalgate_preflight as finalgate
from src.application.action_time import operation_layer_handoff as handoff
from src.application.action_time import promotion_action_time_lane as lane_materializer
from src.application.action_time import protected_submit_attempt as submit
from src.application.action_time import runtime_safety_state as safety
from src.application.action_time.capital_safety_guard import current_scope_blockers
from tests.unit.test_action_time_ticket_materialization import (
    NOW_MS,
    _insert_action_time_lane_graph,
)
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    _insert_ready_fresh_signal,
)
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    _create_handoff_ready,
    pg_control_connection,
)


def test_scope_freeze_blocks_promotion_and_lane(pg_control_connection):
    _insert_ready_fresh_signal(pg_control_connection, "SOR-001", "ETHUSDT", "long")
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    payload = lane_materializer.materialize_pg_promotion_action_time_lane(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "promotion_candidates_blocked"
    assert payload["blockers"] == ["scope_frozen_for_lifecycle_recovery"]
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    promotion = pg_control_connection.execute(
        text("SELECT status, blockers FROM brc_promotion_candidates")
    ).mappings().one()
    assert promotion["status"] == "blocked"
    assert _json_value(promotion["blockers"]) == [
        "scope_frozen_for_lifecycle_recovery"
    ]


def test_unknown_exchange_command_freezes_exact_scope_only():
    control_state = {
        "ticket_bound_scope_freezes": [],
        "ticket_bound_exchange_commands": [
            {
                "command_state": "outcome_unknown",
                "account_id": "account-1",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "exchange_instrument_id": "binance_usdm:ETH/USDT:USDT",
                "side": "long",
            }
        ],
    }

    assert current_scope_blockers(
        control_state,
        account_id="account-1",
        strategy_group_id="SOR-001",
        symbol="ETHUSDT",
        exchange_instrument_id="binance_usdm:ETH/USDT:USDT",
        side="long",
    ) == ["exchange_command_outcome_unknown"]
    assert current_scope_blockers(
        control_state,
        account_id="account-1",
        strategy_group_id="MPG-001",
        symbol="OPUSDT",
        exchange_instrument_id="binance_usdm:OP/USDT:USDT",
        side="long",
    ) == []


def test_typed_one_way_domain_hold_blocks_other_strategy_and_direction():
    hold = {
        "status": "active",
        "account_id": "account-1",
        "exchange_instrument_id": "binance_usdm:ETH/USDT:USDT",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "position_mode": "one_way",
        "position_bucket": "BOTH",
        "netting_domain_key": (
            "account-1|binance_usdm:ETH/USDT:USDT|one_way|BOTH"
        ),
        "first_blocker": "exchange_command_outcome_unknown",
        "blockers": ["exchange_command_outcome_unknown"],
        "source_id": "command-1",
        "updated_at_ms": NOW_MS,
    }
    control_state = {"ticket_bound_scope_freezes": [hold]}

    assert current_scope_blockers(
        control_state,
        account_id="account-1",
        strategy_group_id="MPG-001",
        symbol="ETHUSDT",
        exchange_instrument_id="binance_usdm:ETH/USDT:USDT",
        side="short",
    ) == ["scope_frozen_for_exchange_unknown_risk"]
    assert current_scope_blockers(
        control_state,
        account_id="account-2",
        strategy_group_id="MPG-001",
        symbol="ETHUSDT",
        exchange_instrument_id="binance_usdm:ETH/USDT:USDT",
        side="short",
    ) == []


def test_scope_freeze_blocks_action_time_ticket(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection)
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["scope_frozen_for_lifecycle_recovery"]
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0


def test_cleanup_only_scope_freeze_does_not_block_ticket(pg_control_connection):
    lane_id = _insert_action_time_lane_graph(pg_control_connection)
    _insert_scope_freeze(
        pg_control_connection,
        first_blocker="scope_cleanup_pending_no_current_risk",
    )

    payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "action_time_ticket_created"
    assert payload["action_time_lane_input_id"] == lane_id
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1


def test_scope_freeze_blocks_finalgate_preflight(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["scope_frozen_for_lifecycle_recovery"]


def test_scope_freeze_blocks_operation_layer_handoff(pg_control_connection):
    _insert_action_time_lane_graph(pg_control_connection)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )
    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 1000,
    )
    assert finalgate_payload["status"] == "finalgate_ready"
    _insert_scope_freeze(pg_control_connection, first_blocker="exchange_only_unknown_order")

    payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id=str(finalgate_payload["finalgate_pass_id"]),
        now_ms=NOW_MS + 2000,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["scope_frozen_for_exchange_unknown_risk"]


def test_scope_freeze_blocks_runtime_safety_state(pg_control_connection):
    ids = _create_handoff_ready(pg_control_connection)
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert payload["blockers"] == ["scope_frozen_for_lifecycle_recovery"]


def test_scope_freeze_blocks_submit_mode_and_protected_submit(
    pg_control_connection,
    monkeypatch,
):
    _set_runtime_submit_env(monkeypatch)
    ids = _create_ready_protected_submit(pg_control_connection)
    _insert_scope_freeze(pg_control_connection, first_blocker="protection_missing")

    decision = submit.materialize_ticket_bound_submit_mode_decision(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        production_submit_execution_policy="armed",
        now_ms=NOW_MS + 3500,
    )
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS + 4000,
    )

    assert decision["status"] == "blocked"
    assert decision["blockers"] == ["scope_frozen_for_lifecycle_recovery"]
    assert prepared["status"] == "blocked"
    assert prepared["blockers"] == [
        "scope_frozen_for_lifecycle_recovery",
        "submit_mode_decision_not_real:blocked",
        "submit_mode_decision_has_blockers",
    ]
    assert _count(pg_control_connection, "brc_ticket_bound_protected_submit_attempts") == 1


def _insert_scope_freeze(
    conn,
    *,
    first_blocker: str,
    strategy_group_id: str = "SOR-001",
    symbol: str = "ETHUSDT",
    side: str = "long",
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_scope_freezes (
              scope_freeze_id, strategy_group_id, symbol, side, status,
              source_kind, source_id, first_blocker, blockers, freeze_scope,
              next_action, authority_boundary, created_at_ms, updated_at_ms
            ) VALUES (
              :scope_freeze_id, :strategy_group_id, :symbol, :side, 'active',
              'unit_test', :source_id, :first_blocker, :blockers, :freeze_scope,
              'repair_or_cleanup_scope', 'unit_test_scope_freeze', :now_ms, :now_ms
            )
            """
        ),
        {
            "scope_freeze_id": f"freeze:{strategy_group_id}:{symbol}:{side}",
            "strategy_group_id": strategy_group_id,
            "symbol": symbol,
            "side": side,
            "source_id": f"source:{first_blocker}",
            "first_blocker": first_blocker,
            "blockers": json.dumps([first_blocker], sort_keys=True),
            "freeze_scope": json.dumps(
                {
                    "strategy_group_id": strategy_group_id,
                    "symbol": symbol,
                    "side": side,
                },
                sort_keys=True,
            ),
            "now_ms": NOW_MS + 500,
        },
    )


def _count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one())


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value


def _set_runtime_submit_env(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED", "true")
