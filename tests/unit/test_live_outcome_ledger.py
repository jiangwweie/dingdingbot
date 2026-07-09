from __future__ import annotations

from sqlalchemy import text

from scripts import materialize_ticket_bound_exit_protection_set as exit_protection
from scripts import materialize_ticket_bound_protected_submit_attempt as submit
from src.application.action_time.live_outcome_ledger import (
    materialize_live_outcome_ledger,
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


def test_live_outcome_ledger_records_closed_real_ticket(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = _prepare_real_submit(pg_control_connection, ids)
    result = submit.record_ticket_bound_protected_submit_result(
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
            "submitted_orders": _submitted_orders(prepared),
        },
        now_ms=NOW_MS + 5000,
    )
    assert result["status"] == "submitted"
    proof = exit_protection.materialize_ticket_bound_exit_protection_set(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        now_ms=NOW_MS + 6000,
    )
    assert proof["status"] == "position_protected"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_ticket_bound_order_lifecycle_runs
            SET status = 'lifecycle_closed',
                updated_at_ms = :updated_at_ms
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"], "updated_at_ms": NOW_MS + 7000},
    )

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 8000,
    )

    assert payload["status"] == "recorded"
    assert payload["outcome_type"] == "lifecycle_closed"
    row = dict(
        pg_control_connection.execute(
            text("SELECT * FROM brc_live_outcome_ledger")
        ).mappings().one()
    )
    assert row["ticket_id"] == ids["ticket_id"]
    assert row["strategy_group_id"] == "SOR-001"
    assert row["symbol"] == "ETHUSDT"
    assert row["side"] == "long"
    assert row["stage_reached"] == "lifecycle_closed"
    assert row["risk_at_stop"] is not None
    assert row["authority_boundary"].startswith("ticket_bound_live_outcome_ledger")


def test_live_outcome_ledger_ignores_disabled_smoke(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)
    prepared = submit.prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="disabled_smoke",
        now_ms=NOW_MS + 4000,
    )
    assert prepared["status"] == "disabled_smoke_passed"

    payload = materialize_live_outcome_ledger(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        now_ms=NOW_MS + 5000,
    )

    assert payload["status"] == "not_applicable_no_real_submit"
    assert (
        pg_control_connection.execute(
            text("SELECT count(*) FROM brc_live_outcome_ledger")
        ).scalar_one()
        == 0
    )
