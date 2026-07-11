from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.lifecycle_mutation_capability import (
    lifecycle_mutation_capability_decision,
    set_lifecycle_mutation_capability,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_pg_capability_is_shared_fail_closed_current_truth(pg_control_connection):
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', certification_ref = 'unit:phase-one' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )

    disabled = lifecycle_mutation_capability_decision(pg_control_connection)
    enabled = set_lifecycle_mutation_capability(
        pg_control_connection,
        enabled=True,
        certification_ref="unit:all-certification-gates-passed",
        now_ms=NOW_MS,
    )

    assert disabled["enabled"] is False
    assert disabled["first_blocker"] == "lifecycle_mutation_capability_not_ready"
    assert enabled["enabled"] is True
    assert enabled["blockers"] == []
    assert enabled["capability"]["certification_ref"] == (
        "unit:all-certification-gates-passed"
    )
