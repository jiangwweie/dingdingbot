from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.ticket_bound_budget_settlement import (
    settle_ticket_bound_budget,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_budget_settlement_is_consumed_only_and_idempotent(pg_control_connection):
    ids = _create_ready_protected_submit(pg_control_connection)

    first = settle_ticket_bound_budget(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        settlement_evidence_id="settlement-1",
        now_ms=NOW_MS + 1_000,
    )
    second = settle_ticket_bound_budget(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        settlement_evidence_id="settlement-1",
        now_ms=NOW_MS + 2_000,
    )

    assert first["status"] == "released"
    assert first["runtime_budget_mutated"] is True
    assert second["status"] == "released"
    assert second["runtime_budget_mutated"] is False
    assert pg_control_connection.execute(
        text(
            "SELECT status FROM brc_budget_reservations "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one() == "released"
    event = pg_control_connection.execute(
        text(
            """
            SELECT from_status, to_status, reason, evidence_ref
            FROM brc_budget_reservation_events
            WHERE budget_reservation_id = :budget_reservation_id
              AND to_status = 'released'
            """
        ),
        {"budget_reservation_id": first["budget_reservation_id"]},
    ).mappings().one()
    assert dict(event) == {
        "from_status": "consumed",
        "to_status": "released",
        "reason": "lifecycle_closed:settlement-1",
        "evidence_ref": "settlement-1",
    }
