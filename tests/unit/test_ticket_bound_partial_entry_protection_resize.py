from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

from src.application.action_time.exchange_command import (
    mark_exchange_command_dispatching,
    record_exchange_command_outcome,
    resize_prepared_protection_command_to_entry_fill,
)
from src.application.action_time.exit_protection_materializer import (
    materialize_ticket_bound_exit_protection_set,
)
from src.application.action_time.protected_submit_attempt import (
    record_ticket_bound_protected_submit_result,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
    _prepare_real_submit,
    _submitted_orders,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_partial_entry_resizes_sl_and_tp1_to_actual_filled_quantity(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text(
            "UPDATE brc_exchange_instruments SET quantity_step = 0.001"
        )
    )
    commands = {
        row["order_role"]: dict(row)
        for row in pg_control_connection.execute(
            text("SELECT * FROM brc_ticket_bound_exchange_commands")
        ).mappings()
    }
    requested = Decimal(str(commands["ENTRY"]["amount"]))
    filled = requested / Decimal("2")
    mark_exchange_command_dispatching(
        pg_control_connection,
        exchange_command_id=commands["ENTRY"]["exchange_command_id"],
        now_ms=NOW_MS + 5_000,
    )
    record_exchange_command_outcome(
        pg_control_connection,
        exchange_command_id=commands["ENTRY"]["exchange_command_id"],
        target_state=ExchangeCommandState.CONFIRMED_SUBMITTED,
        outcome_class=ExchangeCommandOutcomeClass.EXCHANGE_ACCEPTED,
        exchange_result={
            "exchange_order_id": "exchange-entry-partial",
            "filled_qty": str(filled),
            "average_exec_price": "2000",
        },
        now_ms=NOW_MS + 5_100,
    )

    sl = resize_prepared_protection_command_to_entry_fill(
        pg_control_connection,
        exchange_command_id=commands["SL"]["exchange_command_id"],
        now_ms=NOW_MS + 5_200,
    )
    tp1 = resize_prepared_protection_command_to_entry_fill(
        pg_control_connection,
        exchange_command_id=commands["TP1"]["exchange_command_id"],
        now_ms=NOW_MS + 5_300,
    )

    assert Decimal(str(sl["amount"])) == filled
    assert Decimal(str(tp1["amount"])) <= filled / Decimal("2")
    assert Decimal(str(tp1["amount"])) > 0
    assert "actual-entry-fill" in sl["authority_source_ref"]
    assert "actual-entry-fill" in tp1["authority_source_ref"]


def test_protection_dispatch_blocks_until_entry_fill_quantity_is_confirmed(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    sl_id = pg_control_connection.execute(
        text(
            "SELECT exchange_command_id FROM brc_ticket_bound_exchange_commands "
            "WHERE order_role = 'SL'"
        )
    ).scalar_one()

    try:
        resize_prepared_protection_command_to_entry_fill(
            pg_control_connection,
            exchange_command_id=sl_id,
            now_ms=NOW_MS + 5_000,
        )
    except ValueError as exc:
        assert str(exc) == "entry_fill_not_confirmed_before_protection"
    else:
        raise AssertionError("SL dispatch must remain blocked before ENTRY fill truth")


def test_partial_entry_materializes_protection_for_actual_fill_not_requested_qty(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    orders = _submitted_orders(prepared)
    entry = next(row for row in orders if row["order_role"] == "ENTRY")
    sl = next(row for row in orders if row["order_role"] == "SL")
    tp1 = next(row for row in orders if row["order_role"] == "TP1")
    actual = Decimal(str(entry["filled_qty"])) / Decimal("2")
    entry["status"] = "PARTIALLY_FILLED"
    entry["filled_qty"] = str(actual)
    sl["amount"] = str(actual)
    tp1["amount"] = str(actual / Decimal("2"))
    recorded = record_ticket_bound_protected_submit_result(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        submit_result={
            "status": "exchange_submit_orders_submitted",
            "ticket_id": ids["ticket_id"],
            "operation_submit_command_id": ids["operation_submit_command_id"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
            "exchange_write_called": True,
            "order_created": True,
            "order_lifecycle_called": True,
            "withdrawal_or_transfer_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
            "submitted_orders": orders,
        },
        now_ms=NOW_MS + 5_000,
    )

    protection = materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6_000,
    )

    assert recorded["status"] == "submitted"
    assert protection["status"] == "position_protected"
    lifecycle_qty = pg_control_connection.execute(
        text(
            "SELECT entry_filled_qty FROM brc_ticket_bound_order_lifecycle_runs "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one()
    sl_qty = pg_control_connection.execute(
        text(
            "SELECT qty FROM brc_ticket_bound_exit_protection_orders "
            "WHERE ticket_id = :ticket_id AND role = 'SL'"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one()
    assert Decimal(str(lifecycle_qty)) == actual
    assert Decimal(str(sl_qty)) == actual
