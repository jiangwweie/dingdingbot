from __future__ import annotations

# ruff: noqa: F401, F811

import pytest
from sqlalchemy import text

from src.application.action_time.ticket_bound_budget_settlement import (
    settle_ticket_bound_budget,
)
from src.application.runtime_incident_projector import (
    project_protection_barrier_failure,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_protected_submit_attempt import (
    _create_ready_protected_submit,
)
from tests.unit.test_ticket_bound_lifecycle_finalizer import (
    _prepare_reconciled_flat_exit,
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


def test_budget_settlement_releases_flat_terminal_ticket_without_residual_effect(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)

    result = settle_ticket_bound_budget(
        pg_control_connection,
        ticket_id=ticket_id,
        settlement_evidence_id="settlement-terminal-flat",
        now_ms=NOW_MS + 20_000,
    )

    assert result["status"] == "released"


def test_budget_settlement_rejects_effect_active_attempt(pg_control_connection):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET entry_effect_state = 'accepted_filled', "
            "protection_barrier_state = 'initial_stop_confirmed', "
            "protection_quantity = 0.01, "
            "entry_effect_observed_at_ms = :observed_at_ms, "
            "initial_stop_confirmed_at_ms = :confirmed_at_ms"
        ),
        {
            "observed_at_ms": NOW_MS + 5_000,
            "confirmed_at_ms": NOW_MS + 5_001,
        },
    )

    result = _settle(pg_control_connection, ticket_id, "effect-active")

    assert result["first_blocker"] == "ticket_budget_effect_active_attempt"


def test_budget_settlement_rejects_open_or_reconciling_entry_command(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_state = 'outcome_unknown', "
            "outcome_class = 'network_ambiguous', "
            "exchange_order_status = NULL, result_facts_complete = 0 "
            "WHERE order_role = 'ENTRY'"
        )
    )

    result = _settle(pg_control_connection, ticket_id, "entry-reconciling")

    assert result["first_blocker"] == "ticket_budget_entry_command_unresolved"


def test_budget_settlement_rejects_active_protection_incident(pg_control_connection):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    _open_initial_stop_incident(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_scope_freezes SET status = 'resolved', "
            "updated_at_ms = :now_ms WHERE source_kind = 'protection_barrier'"
        ),
        {"now_ms": NOW_MS + 19_000},
    )
    _reset_terminal_attempt_projection(pg_control_connection)

    result = _settle(pg_control_connection, ticket_id, "active-incident")

    assert result["first_blocker"] == "ticket_budget_protection_incident_active"


def test_budget_settlement_rejects_active_protection_barrier_hold(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    _open_initial_stop_incident(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_incidents SET status = 'closed', "
            "closed_at_ms = :now_ms "
            "WHERE incident_type = 'initial_stop_not_established'"
        ),
        {"now_ms": NOW_MS + 19_000},
    )
    _reset_terminal_attempt_projection(pg_control_connection)

    result = _settle(pg_control_connection, ticket_id, "active-hold")

    assert result["first_blocker"] == "ticket_budget_protection_barrier_hold_active"


def test_budget_settlement_rejects_nonterminal_exchange_command(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_state = 'prepared', outcome_class = 'pending' "
            "WHERE order_role = 'TP1'"
        )
    )

    result = _settle(pg_control_connection, ticket_id, "nonterminal-command")

    assert result["first_blocker"] == "ticket_budget_exchange_command_not_terminal"


def test_budget_settlement_rejects_open_protection_exchange_effect(
    pg_control_connection,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_state = 'confirmed_submitted', "
            "exchange_order_status = 'OPEN', result_facts_complete = 1 "
            "WHERE order_role = 'SL'"
        )
    )

    result = _settle(pg_control_connection, ticket_id, "open-protection-command")

    assert result["first_blocker"] == (
        "ticket_budget_exchange_command_effect_not_terminal"
    )


@pytest.mark.parametrize(
    ("field", "value", "blocker_field"),
    (
        ("source_command_id", "attempt:foreign", "source_attempt"),
        ("exposure_episode_id", "episode:foreign", "exposure_episode_id"),
        ("netting_domain_key", "domain:foreign", "netting_domain_key"),
    ),
)
def test_budget_settlement_rejects_entry_incident_identity_lineage_drift(
    pg_control_connection,
    field,
    value,
    blocker_field,
):
    ticket_id = _prepare_reconciled_flat_exit(pg_control_connection)
    pg_control_connection.execute(
        text(
            f"UPDATE brc_ticket_bound_exchange_commands SET {field} = :value "
            "WHERE order_role = 'ENTRY'"
        ),
        {"value": value},
    )

    result = _settle(pg_control_connection, ticket_id, f"lineage-{field}")

    assert result["first_blocker"] == (
        f"ticket_budget_entry_command_lineage_invalid:{blocker_field}"
    )


def _settle(conn, ticket_id: str, suffix: str) -> dict:
    return settle_ticket_bound_budget(
        conn,
        ticket_id=ticket_id,
        settlement_evidence_id=f"settlement-{suffix}",
        now_ms=NOW_MS + 20_000,
    )


def _open_initial_stop_incident(conn) -> None:
    attempt_id = conn.execute(
        text(
            "SELECT protected_submit_attempt_id "
            "FROM brc_ticket_bound_protected_submit_attempts"
        )
    ).scalar_one()
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET entry_effect_state = 'accepted_filled', "
            "protection_barrier_state = 'initial_stop_pending', "
            "protection_quantity = 0.01, "
            "entry_effect_observed_at_ms = :observed_at_ms"
        ),
        {"observed_at_ms": NOW_MS + 5_000},
    )
    project_protection_barrier_failure(
        conn,
        protected_submit_attempt_id=attempt_id,
        order_role="SL",
        blocker="initial_stop_deadline_exhausted",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="capacity-gate-test",
        now_ms=NOW_MS + 18_000,
    )


def _reset_terminal_attempt_projection(conn) -> None:
    conn.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET protection_barrier_state = 'closed'"
        )
    )
