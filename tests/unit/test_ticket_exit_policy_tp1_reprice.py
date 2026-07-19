from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from src.application.action_time.ticket_exit_policy_service import (
    maintain_ticket_exit_policy_in_transaction,
)
from src.application.action_time.exchange_command_worker import (
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.lifecycle_maintenance_service import (
    run_ticket_bound_lifecycle_maintenance,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_reconciliation_tick,
)
from src.domain.ticket_exit_policy import TicketExitExecutionSnapshot
from tests.unit.lifecycle_test_schema import (
    apply_active_ticket_exit_policy_adoption_schema,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_bound_exchange_command_worker import _WorkerGateway
from tests.unit.test_ticket_bound_protection_reconciler import _snapshot
from tests.unit.test_ticket_exit_policy_service import (
    _projection,
    _set_command_state,
    _versioned_exit_fixture,
)


ROOT = Path(__file__).resolve().parents[2]


def test_reprice_cancels_old_tp1_before_preparing_exact_limit_gtc_replacement(
    pg_control_connection,
):
    ticket_id, old_tp1, expected_price = _reprice_fixture(pg_control_connection)

    cancel_result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    commands = _reprice_commands(pg_control_connection, ticket_id)
    assert cancel_result["status"] == "tp1_reprice_cancel_prepared", cancel_result
    assert len(commands) == 1
    assert commands[0]["command_kind"] == "cancel_order"
    assert commands[0]["target_exchange_order_id"] == old_tp1["exchange_order_id"]

    _set_command_state(
        pg_control_connection,
        commands[0]["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=old_tp1["exchange_order_id"],
    )
    place_result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    commands = _reprice_commands(pg_control_connection, ticket_id)
    assert place_result["status"] == "tp1_reprice_place_prepared"
    assert len(commands) == 2
    place = next(item for item in commands if item["command_kind"] == "place_order")
    assert place["order_role"] == "TP1"
    assert place["order_type"] == "limit"
    assert place["execution_style"] == "limit_gtc"
    assert place["time_in_force"] == "GTC"
    assert place["post_only"] in {False, 0}
    assert place["market_fallback_allowed"] in {False, 0}
    assert place["reduce_only"] in {True, 1}
    assert Decimal(str(place["price"])) == expected_price


def test_reprice_unknown_cancel_never_prepares_replacement(pg_control_connection):
    ticket_id, _old_tp1, _expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    cancel = _reprice_commands(pg_control_connection, ticket_id)[0]
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="outcome_unknown",
        exchange_order_id=None,
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )

    assert result["status"] == "tp1_reprice_cancel_outcome_unknown"
    assert len(_reprice_commands(pg_control_connection, ticket_id)) == 1


def test_tp1_fill_race_after_cancel_supersedes_reprice_without_new_order(
    pg_control_connection,
):
    ticket_id, old_tp1, _expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    cancel = _reprice_commands(pg_control_connection, ticket_id)[0]
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=old_tp1["exchange_order_id"],
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_completion_state='complete', "
            "tp1_cumulative_filled_qty=resolved_tp1_target_qty "
            "WHERE ticket_id=:ticket_id"
        ),
        {"ticket_id": ticket_id},
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )

    assert result["status"] == "tp1_reprice_superseded_by_fill"
    assert len(_reprice_commands(pg_control_connection, ticket_id)) == 1


def test_tp1_partial_fill_after_cancel_places_only_frozen_target_residual(
    pg_control_connection,
):
    ticket_id, old_tp1, _expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    cancel = _reprice_commands(pg_control_connection, ticket_id)[0]
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=old_tp1["exchange_order_id"],
    )
    projection = _projection(pg_control_connection, ticket_id)
    target = Decimal(str(projection["resolved_tp1_target_qty"]))
    partial = target / Decimal("2")
    execution = TicketExitExecutionSnapshot.model_validate(
        _mapping(projection["exit_execution_snapshot"])
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "tp1_completion_state='partial', "
            "tp1_cumulative_filled_qty=:partial, "
            "remaining_position_qty=:remaining "
            "WHERE ticket_id=:ticket_id"
        ),
        {
            "partial": str(partial),
            "remaining": str(execution.runner_target_qty + target - partial),
            "ticket_id": ticket_id,
        },
    )

    result = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )

    assert result["status"] == "tp1_reprice_place_prepared"
    place = next(
        item
        for item in _reprice_commands(pg_control_connection, ticket_id)
        if item["command_kind"] == "place_order"
    )
    assert Decimal(str(place["amount"])) == target - partial


@pytest.mark.asyncio
async def test_existing_worker_dispatches_cancel_then_exact_reduce_only_limit(
    pg_control_connection,
):
    ticket_id, _old_tp1, expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    pg_control_connection.commit()
    gateway = _WorkerGateway()
    engine = pg_control_connection.engine

    cancelled = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id="tp1-reprice-cancel",
        now_ms=NOW_MS + 20_010,
        command_sources=("exit_policy_tp1_reprice",),
    )
    with engine.begin() as conn:
        prepared = maintain_ticket_exit_policy_in_transaction(
            conn,
            ticket_id=ticket_id,
            now_ms=NOW_MS + 20_020,
        )
    placed = await run_one_ticket_bound_exchange_command(
        engine,
        gateway=gateway,
        worker_id="tp1-reprice-place",
        now_ms=NOW_MS + 20_030,
        command_sources=("exit_policy_tp1_reprice",),
    )
    with engine.begin() as conn:
        completed = maintain_ticket_exit_policy_in_transaction(
            conn,
            ticket_id=ticket_id,
            now_ms=NOW_MS + 20_040,
        )

    assert cancelled["status"] == "command_confirmed"
    assert prepared["status"] == "tp1_reprice_place_prepared"
    assert placed["status"] == "command_confirmed"
    assert completed["status"] == "tp1_reprice_completed"
    assert len(gateway.calls) == 2
    assert "exchange_order_id" in gateway.calls[0]
    assert gateway.calls[1]["order_type"] == "limit"
    assert gateway.calls[1]["time_in_force"] == "GTC"
    assert gateway.calls[1]["reduce_only"] is True
    assert gateway.calls[1]["price"].quantize(Decimal("0.001")) == expected_price


@pytest.mark.asyncio
async def test_completed_reprice_is_idempotent_and_does_not_prepare_recovery(
    pg_control_connection,
):
    ticket_id, old_tp1, expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    cancel = _reprice_commands(pg_control_connection, ticket_id)[0]
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=cancel["target_exchange_order_id"],
    )
    protection_set_id = str(
        pg_control_connection.execute(
            text(
                "SELECT exit_protection_set_id FROM "
                "brc_ticket_bound_exit_protection_sets WHERE ticket_id=:ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).scalar_one()
    )
    cancellation_window_snapshot = _snapshot(
        pg_control_connection,
        protection_set_id,
    )
    cancellation_window_snapshot["open_orders"] = [
        item
        for item in cancellation_window_snapshot["open_orders"]
        if str(item.get("exchange_order_id") or "")
        != str(cancel["target_exchange_order_id"])
    ]
    maintenance = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=cancellation_window_snapshot,
        now_ms=NOW_MS + 20_050,
    )
    assert all(
        action["action_type"] != "protection_recovery_prepared"
        for action in maintenance["actions"]
    )
    assert not list(
        pg_control_connection.execute(
            text(
                "SELECT * FROM brc_ticket_bound_protection_recovery_commands "
                "WHERE protected_submit_attempt_id=(SELECT protected_submit_attempt_id "
                "FROM brc_ticket_bound_exit_protection_sets WHERE ticket_id=:ticket_id)"
            ),
            {"ticket_id": ticket_id},
        ).mappings()
    )
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    place = next(
        item
        for item in _reprice_commands(pg_control_connection, ticket_id)
        if item["command_kind"] == "place_order"
    )
    _set_command_state(
        pg_control_connection,
        place["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id="repriced-tp1",
    )
    completed = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_200,
    )
    repeated = maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_300,
    )

    assert completed["status"] == "tp1_reprice_completed"
    assert repeated["status"] == "tp1_reprice_already_completed"
    assert repeated["ticket_id"] == ticket_id
    assert repeated["blockers"] == []
    assert repeated["exchange_write_called"] is False
    assert repeated["exchange_order_id"] == "repriced-tp1"
    orders = list(
        pg_control_connection.execute(
            text(
                "SELECT status, price, exchange_order_id FROM "
                "brc_ticket_bound_exit_protection_orders "
                "WHERE ticket_id=:ticket_id AND role='TP1' ORDER BY generation"
            ),
            {"ticket_id": ticket_id},
        ).mappings()
    )
    assert [(item["status"], Decimal(str(item["price"]))) for item in orders] == [
        ("replaced", Decimal(str(old_tp1["price"]))),
        ("submitted", expected_price),
    ]

    propagation_window_snapshot = _snapshot(
        pg_control_connection,
        protection_set_id,
    )
    propagation_window_snapshot["open_orders"] = [
        item
        for item in propagation_window_snapshot["open_orders"]
        if str(item.get("exchange_order_id") or "") != "repriced-tp1"
    ]
    propagation_window_maintenance = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=propagation_window_snapshot,
        now_ms=NOW_MS + 20_250,
    )
    assert all(
        action["action_type"] != "protection_recovery_prepared"
        for action in propagation_window_maintenance["actions"]
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands SET updated_at_ms=0 "
            "WHERE ticket_id=:ticket_id AND command_source='exit_policy_tp1_reprice' "
            "AND command_kind='place_order'"
        ),
        {"ticket_id": ticket_id},
    )
    expired_window_maintenance = await run_ticket_bound_lifecycle_maintenance(
        pg_control_connection,
        ticket_id=ticket_id,
        exchange_snapshot=propagation_window_snapshot,
        now_ms=NOW_MS + 20_300,
    )
    assert any(
        action["action_type"] == "protection_recovery_prepared"
        for action in expired_window_maintenance["actions"]
    )


def test_scheduled_tick_uses_current_exit_protection_tp1_after_reprice(
    pg_control_connection,
):
    ticket_id, old_tp1, _expected_price = _reprice_fixture(pg_control_connection)
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_000,
    )
    cancel = _reprice_commands(pg_control_connection, ticket_id)[0]
    _set_command_state(
        pg_control_connection,
        cancel["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id=old_tp1["exchange_order_id"],
    )
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_100,
    )
    place = next(
        item
        for item in _reprice_commands(pg_control_connection, ticket_id)
        if item["command_kind"] == "place_order"
    )
    _set_command_state(
        pg_control_connection,
        place["exchange_command_id"],
        state="confirmed_submitted",
        exchange_order_id="repriced-tp1",
    )
    maintain_ticket_exit_policy_in_transaction(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 20_200,
    )
    attempt_id = str(
        pg_control_connection.execute(
            text(
                "SELECT protected_submit_attempt_id FROM "
                "brc_ticket_bound_exit_protection_sets WHERE ticket_id=:ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).scalar_one()
    )
    protection_set_id = str(
        pg_control_connection.execute(
            text(
                "SELECT exit_protection_set_id FROM "
                "brc_ticket_bound_exit_protection_sets WHERE ticket_id=:ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).scalar_one()
    )
    raw_submit_result = pg_control_connection.execute(
        text(
            "SELECT submit_result FROM brc_ticket_bound_protected_submit_attempts "
            "WHERE protected_submit_attempt_id=:attempt_id"
        ),
        {"attempt_id": attempt_id},
    ).scalar_one()
    submit_result = _mapping(raw_submit_result)
    current_tp1 = next(
        order
        for order in submit_result["submitted_orders"]
        if order["order_role"] == "TP1"
    )
    submit_result["submitted_orders"].append(
        {
            **current_tp1,
            "exchange_order_id": "stale-recovery-tp1",
            "client_order_id": "stale-recovery-tp1",
            "price": "9999",
        }
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET submit_result=:submit_result "
            "WHERE protected_submit_attempt_id=:attempt_id"
        ),
        {
            "attempt_id": attempt_id,
            "submit_result": json.dumps(submit_result, sort_keys=True),
        },
    )

    payload = materialize_ticket_bound_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        tick_kind="scheduled",
        exchange_snapshot=_snapshot(pg_control_connection, protection_set_id),
        now_ms=NOW_MS + 20_300,
    )

    assert payload["status"] == "matched"
    assert payload["tick"]["sl_state"] == "open"
    assert payload["tick"]["tp1_state"] == "open"

def _reprice_fixture(conn):
    ticket_id = _versioned_exit_fixture(conn)
    apply_active_ticket_exit_policy_adoption_schema(
        conn,
        repo_root=ROOT,
        module_prefix="tp1_reprice",
    )
    old_tp1 = dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exit_protection_orders "
                "WHERE ticket_id=:ticket_id AND role='TP1'"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    )
    old_price = Decimal(str(old_tp1["price"]))
    expected_price = old_price - Decimal("0.006")
    projection = _projection(conn, ticket_id)
    execution = TicketExitExecutionSnapshot.model_validate(
        _mapping(projection["exit_execution_snapshot"])
    )
    revised = TicketExitExecutionSnapshot.with_canonical_hash(
        {
            **execution.model_dump(mode="python"),
            "resolved_tp1_price": expected_price,
        }
    )
    conn.execute(
        text(
            "UPDATE brc_exchange_instruments SET price_tick=0.001 "
            "WHERE exchange_instrument_id=(SELECT exchange_instrument_id "
            "FROM brc_action_time_tickets WHERE ticket_id=:ticket_id)"
        ),
        {"ticket_id": ticket_id},
    )
    conn.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET "
            "exit_execution_snapshot=:snapshot, exit_execution_hash=:hash, "
            "resolved_tp1_price=:price, state='blocked_tp1_reprice_required', "
            "first_blocker='tp1_reprice_required' WHERE ticket_id=:ticket_id"
        ),
        {
            "snapshot": json.dumps(revised.model_dump(mode="json")),
            "hash": revised.payload_hash,
            "price": str(expected_price),
            "ticket_id": ticket_id,
        },
    )
    return ticket_id, old_tp1, expected_price


def _reprice_commands(conn, ticket_id):
    return [
        dict(row)
        for row in conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "WHERE ticket_id=:ticket_id "
                "AND command_source='exit_policy_tp1_reprice' "
                "ORDER BY prepared_at_ms, command_kind"
            ),
            {"ticket_id": ticket_id},
        ).mappings()
    ]


def _mapping(value):
    return value if isinstance(value, dict) else json.loads(value)
