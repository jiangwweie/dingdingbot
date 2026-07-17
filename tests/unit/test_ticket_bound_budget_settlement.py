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


def test_budget_settlement_rejects_settlement_id_without_terminal_release_proof(
    pg_control_connection,
):
    ids = _create_ready_protected_submit(pg_control_connection)

    first = settle_ticket_bound_budget(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        settlement_evidence_id="settlement-1",
        now_ms=NOW_MS + 1_000,
    )
    assert first == {
        "status": "blocked",
        "first_blocker": "ticket_budget_terminal_lifecycle_not_matched",
        "blockers": ["ticket_budget_terminal_lifecycle_not_matched"],
        "runtime_budget_mutated": False,
    }
    assert pg_control_connection.execute(
        text(
            "SELECT status FROM brc_budget_reservations "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one() == "consumed"
    assert pg_control_connection.execute(
        text(
            "SELECT count(*) FROM brc_budget_reservation_events "
            "WHERE budget_reservation_id = ("
            "SELECT budget_reservation_id FROM brc_budget_reservations "
            "WHERE ticket_id = :ticket_id"
            ") AND to_status = 'released'"
        ),
        {"ticket_id": ids["ticket_id"]},
    ).scalar_one() == 0
