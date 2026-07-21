from __future__ import annotations

# ruff: noqa: F401, F811

from decimal import Decimal

import pytest
from sqlalchemy import text

from src.application import runtime_incident_projector as incidents
from src.application.action_time.entry_effect_projection import (
    project_protection_result,
    project_reconciled_entry_execution,
)
from src.application.action_time.exchange_command import (
    mark_exchange_command_dispatching,
    record_exchange_command_outcome,
)
from src.application.action_time.lifecycle_exchange_command_materializer import (
    materialize_lifecycle_exchange_commands,
)
from src.application.action_time.netting_domain_hold import upsert_netting_domain_hold
from src.application.action_time.protection_recovery_command import (
    prepare_ticket_bound_protection_recovery_command,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
)
from src.application.action_time.post_submit_reconciliation_tick import (
    materialize_ticket_bound_reconciliation_tick,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_post_submit_reconciliation_tick import (
    _cumulative_entry_fill_snapshot,
    _entry_accepted_local_lifecycle_failed_attempt,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


@pytest.mark.parametrize(
    ("blocker", "outcome_ambiguous"),
    [
        ("initial_stop_deadline_exhausted", False),
        ("initial_stop_exchange_rejected", False),
        ("initial_stop_exchange_outcome_unknown", True),
    ],
)
def test_initial_stop_failure_opens_one_stable_incident_and_exact_hold(
    pg_control_connection,
    blocker,
    outcome_ambiguous,
):
    prepared = _effect_active_attempt(pg_control_connection)
    first = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="SL",
        blocker=blocker,
        outcome_ambiguous=outcome_ambiguous,
        protection_barrier_generation=1,
        trigger_ref=f"test:{blocker}",
        now_ms=NOW_MS + 7000,
    )
    second = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="SL",
        blocker=blocker,
        outcome_ambiguous=outcome_ambiguous,
        protection_barrier_generation=1,
        trigger_ref=f"test:{blocker}",
        now_ms=NOW_MS + 7100,
    )

    incident = _one(pg_control_connection, "brc_runtime_incidents")
    hold = _incident_hold(pg_control_connection)
    assert first["incident_id"] == second["incident_id"] == incident["incident_id"]
    assert incident["incident_type"] == "initial_stop_not_established"
    assert incident["status"] == "open"
    assert incident["severity"] == "critical"
    assert incident["opened_at_ms"] == NOW_MS + 7000
    assert hold["status"] == "active"
    assert hold["source_kind"] == "protection_barrier"
    assert hold["source_id"].startswith("protection_barrier:")
    assert _count(pg_control_connection, "brc_runtime_incidents") == 1
    assert _count_incident_holds(pg_control_connection) == 1


def test_initial_stop_quantity_mismatch_is_current_p0_incident(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)

    result = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="SL",
        blocker="sl_protection_quantity_mismatch",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="reconciliation:quantity-mismatch",
        now_ms=NOW_MS + 7000,
    )
    assert result["status"] == "open"
    assert _one(pg_control_connection, "brc_runtime_incidents")["blocker_class"] == (
        "sl_protection_quantity_mismatch"
    )
    assert _incident_hold(pg_control_connection)["first_blocker"] == (
        "sl_protection_quantity_mismatch"
    )


def test_positive_entry_effect_immediately_opens_stable_barrier_hold_and_deadline(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    first_attempt = _attempt(
        pg_control_connection,
        prepared["protected_submit_attempt_id"],
    )
    first_hold = _incident_hold(pg_control_connection)

    project_reconciled_entry_execution(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_order_id="exchange-entry-1",
        executed_qty=Decimal("0.010"),
        average_exec_price=Decimal("2000"),
        exchange_observed_at_ms=NOW_MS + 9000,
        now_ms=NOW_MS + 9000,
    )
    replayed_attempt = _attempt(
        pg_control_connection,
        prepared["protected_submit_attempt_id"],
    )
    replayed_hold = _incident_hold(pg_control_connection)

    assert first_attempt["initial_stop_deadline_at_ms"] == NOW_MS + 21_000
    assert replayed_attempt["initial_stop_deadline_at_ms"] == (
        first_attempt["initial_stop_deadline_at_ms"]
    )
    assert first_hold["scope_freeze_id"] == replayed_hold["scope_freeze_id"]
    assert first_hold["status"] == "active"
    assert first_hold["first_blocker"] == "initial_stop_pending"
    assert _count(pg_control_connection, "brc_runtime_incidents") == 0


@pytest.mark.parametrize(
    ("deadline_offset_ms", "incident_expected"),
    [(-1, False), (0, True), (1, True)],
)
def test_missing_initial_stop_critical_incident_starts_at_exact_sla_boundary(
    pg_control_connection,
    deadline_offset_ms,
    incident_expected,
):
    prepared = _effect_active_attempt(pg_control_connection)
    attempt = _attempt(pg_control_connection, prepared["protected_submit_attempt_id"])
    deadline_at_ms = int(attempt["initial_stop_deadline_at_ms"])

    payload = materialize_ticket_bound_reconciliation_tick(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        tick_kind="scheduled",
        exchange_snapshot=_cumulative_entry_fill_snapshot(prepared, qty="0.010"),
        now_ms=deadline_at_ms + deadline_offset_ms,
    )

    assert payload["status"] == "recovery_required"
    assert _count(pg_control_connection, "brc_runtime_incidents") == int(
        incident_expected
    )
    hold = _incident_hold(pg_control_connection)
    assert hold["status"] == "active"
    assert hold["first_blocker"] == (
        "initial_stop_deadline_exhausted"
        if incident_expected
        else "initial_stop_pending"
    )

def test_tp1_failure_after_confirmed_stop_is_degraded_without_p0_hold(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET protection_barrier_state = 'initial_stop_confirmed', "
            "initial_stop_confirmed_at_ms = :now_ms "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {
            "attempt_id": prepared["protected_submit_attempt_id"],
            "now_ms": NOW_MS + 6500,
        },
    )
    incidents.resolve_initial_stop_incident(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        protection_barrier_generation=1,
        resolution_source="unit_test_initial_stop_confirmed",
        now_ms=NOW_MS + 6500,
    )

    result = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="TP1",
        blocker="tp1_exchange_outcome_unknown",
        outcome_ambiguous=True,
        protection_barrier_generation=1,
        trigger_ref="exchange-command:tp1",
        now_ms=NOW_MS + 7000,
    )

    attempt = _attempt(pg_control_connection, prepared["protected_submit_attempt_id"])
    lifecycle = _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs")
    assert result["status"] == "protection_degraded"
    assert attempt["protection_barrier_state"] == "degraded"
    assert lifecycle["status"] == "protection_degraded"
    assert _count(pg_control_connection, "brc_runtime_incidents") == 0
    assert _count_incident_holds(pg_control_connection) == 1
    assert _incident_hold(pg_control_connection)["status"] == "resolved"


def test_recovery_confirmation_closes_only_exact_incident_hold_source(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    opened = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="SL",
        blocker="initial_stop_exchange_rejected",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="exchange-command:sl-rejected",
        now_ms=NOW_MS + 7000,
    )
    entry = _entry_command(pg_control_connection, prepared["protected_submit_attempt_id"])
    unrelated = upsert_netting_domain_hold(
        pg_control_connection,
        account_id=entry["account_id"],
        runtime_profile_id=entry["runtime_profile_id"],
        exchange_id=entry["exchange_id"],
        exchange_instrument_id=entry["exchange_instrument_id"],
        position_mode=entry["position_mode"],
        position_bucket=entry["position_bucket"],
        netting_domain_key=entry["netting_domain_key"],
        source_ticket_id=entry["ticket_id"],
        strategy_group_id=entry["strategy_group_id"],
        symbol=entry["symbol"],
        side=entry["side"],
        source_kind="unit_test_other_hold",
        source_id="other-source",
        blockers=["other_blocker"],
        next_action="repair_other_source",
        authority_boundary="unit_test",
        now_ms=NOW_MS + 7050,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET protection_barrier_state = 'initial_stop_confirmed', "
            "initial_stop_confirmed_at_ms = :now_ms "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {
            "attempt_id": prepared["protected_submit_attempt_id"],
            "now_ms": NOW_MS + 7900,
        },
    )

    first = incidents.resolve_initial_stop_incident(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        protection_barrier_generation=1,
        resolution_source="recovery_sl_confirmed",
        now_ms=NOW_MS + 8000,
    )
    second = incidents.resolve_initial_stop_incident(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        protection_barrier_generation=1,
        resolution_source="recovery_sl_confirmed",
        now_ms=NOW_MS + 8100,
    )

    incident = _one(pg_control_connection, "brc_runtime_incidents")
    incident_hold = _incident_hold(pg_control_connection)
    other_hold = _hold_by_id(pg_control_connection, unrelated["scope_freeze_id"])
    assert first["incident_id"] == second["incident_id"] == opened["incident_id"]
    assert incident["status"] == "closed"
    assert incident["closed_at_ms"] == NOW_MS + 8000
    assert incident_hold["status"] == "resolved"
    assert other_hold["status"] == "active"


def test_stale_generation_failure_cannot_regress_current_confirmed_barrier(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET protection_barrier_generation = 2, "
            "protection_barrier_state = 'initial_stop_confirmed', "
            "initial_stop_confirmed_at_ms = :now_ms "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {
            "attempt_id": prepared["protected_submit_attempt_id"],
            "now_ms": NOW_MS + 7000,
        },
    )

    result = incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        order_role="SL",
        blocker="initial_stop_exchange_outcome_unknown",
        outcome_ambiguous=True,
        protection_barrier_generation=1,
        trigger_ref="exchange-command:stale-generation-1",
        now_ms=NOW_MS + 8000,
    )

    attempt = _attempt(pg_control_connection, prepared["protected_submit_attempt_id"])
    assert result["status"] == "stale_generation_ignored"
    assert attempt["protection_barrier_generation"] == 2
    assert attempt["protection_barrier_state"] == "initial_stop_confirmed"
    assert _count(pg_control_connection, "brc_runtime_incidents") == 0
    assert _count_incident_holds(pg_control_connection) == 1


def test_recovery_generation_sl_acceptance_closes_exact_current_incident_and_hold(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    attempt_id = prepared["protected_submit_attempt_id"]
    incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        order_role="SL",
        blocker="initial_stop_exchange_rejected",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="original-sl-rejected",
        now_ms=NOW_MS + 7000,
    )
    incidents.supersede_protection_barrier_generation(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        protection_barrier_generation=1,
        now_ms=NOW_MS + 7100,
    )
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_protected_submit_attempts "
            "SET protection_barrier_generation = 2, "
            "protection_barrier_state = 'initial_stop_pending', "
            "initial_stop_deadline_at_ms = :deadline, updated_at_ms = :now_ms "
            "WHERE protected_submit_attempt_id = :attempt_id"
        ),
        {
            "attempt_id": attempt_id,
            "deadline": NOW_MS + 22_100,
            "now_ms": NOW_MS + 7100,
        },
    )
    incidents.ensure_protection_barrier_hold(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        protection_barrier_generation=2,
        blocker="initial_stop_pending",
        next_action="establish_exact_initial_stop_within_sla",
        now_ms=NOW_MS + 7100,
    )
    incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        order_role="SL",
        blocker="initial_stop_deadline_exhausted",
        outcome_ambiguous=False,
        protection_barrier_generation=2,
        trigger_ref="recovery-generation-2-deadline",
        now_ms=NOW_MS + 22_100,
    )
    recovery = prepare_ticket_bound_protection_recovery_command(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        now_ms=NOW_MS + 22_200,
    )
    assert recovery["status"] == "prepared", (
        recovery,
        _one(pg_control_connection, "brc_ticket_bound_order_lifecycle_runs"),
    )
    commands = materialize_lifecycle_exchange_commands(
        pg_control_connection,
        command_source="protection_recovery",
        source_command_id=recovery["command"]["protection_recovery_command_id"],
        now_ms=NOW_MS + 22_300,
    )
    recovery_sl = next(row for row in commands if row["order_role"] == "SL")
    mark_exchange_command_dispatching(
        pg_control_connection,
        exchange_command_id=recovery_sl["exchange_command_id"],
        now_ms=NOW_MS + 22_400,
    )
    confirmed = record_exchange_command_outcome(
        pg_control_connection,
        exchange_command_id=recovery_sl["exchange_command_id"],
        target_state=ExchangeCommandState.CONFIRMED_SUBMITTED,
        outcome_class=ExchangeCommandOutcomeClass.EXCHANGE_ACCEPTED,
        exchange_result={
            "exchange_order_id": "exchange-recovery-sl-generation-2",
            "exchange_order_status": "OPEN",
        },
        now_ms=NOW_MS + 22_500,
    )

    project_protection_result(
        pg_control_connection,
        command=confirmed,
        now_ms=NOW_MS + 22_500,
    )

    attempt = _attempt(pg_control_connection, attempt_id)
    incidents_by_generation = list(
        pg_control_connection.execute(
            text(
                "SELECT status, details FROM brc_runtime_incidents "
                "WHERE incident_type = 'initial_stop_not_established' "
                "ORDER BY opened_at_ms"
            )
        ).mappings()
    )
    active_holds = pg_control_connection.execute(
        text(
            "SELECT count(*) FROM brc_ticket_bound_scope_freezes "
            "WHERE source_kind = 'protection_barrier' AND status = 'active'"
        )
    ).scalar_one()
    assert attempt["protection_barrier_generation"] == 2
    assert attempt["protection_barrier_state"] == "initial_stop_confirmed"
    assert [row["status"] for row in incidents_by_generation] == ["closed", "closed"]
    assert active_holds == 0


def test_exact_flat_proof_closes_current_generation_incident_and_hold(
    pg_control_connection,
):
    prepared = _effect_active_attempt(pg_control_connection)
    attempt_id = prepared["protected_submit_attempt_id"]
    entry = _entry_command(pg_control_connection, attempt_id)
    incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        order_role="SL",
        blocker="initial_stop_deadline_exhausted",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="flat-proof-current",
        now_ms=NOW_MS + 7000,
    )

    result = incidents.resolve_protection_barrier_from_flat_proof(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        ticket_id=str(entry["ticket_id"]),
        exposure_episode_id=str(entry["exposure_episode_id"]),
        netting_domain_key=str(entry["netting_domain_key"]),
        source_entry_exchange_command_id=str(entry["exchange_command_id"]),
        protection_barrier_generation=1,
        authoritative_position_flat=True,
        exact_live_residual_absent=True,
        resolution_source="matched_flat_reconciliation_tick",
        now_ms=NOW_MS + 8000,
    )

    assert result["status"] == "closed_from_flat_proof"
    assert _attempt(pg_control_connection, attempt_id)[
        "protection_barrier_state"
    ] == "closed"
    assert _one(pg_control_connection, "brc_runtime_incidents")["status"] == "closed"
    assert _incident_hold(pg_control_connection)["status"] == "resolved"


@pytest.mark.parametrize(
    ("mutation", "expected_status"),
    (
        ({"protection_barrier_generation": 2}, "stale_generation_ignored"),
        ({"netting_domain_key": "netting-domain:foreign"}, "identity_mismatch"),
        (
            {"exact_live_residual_absent": False},
            "flat_proof_incomplete",
        ),
    ),
)
def test_flat_proof_does_not_clear_stale_identity_or_unknown_residual(
    pg_control_connection,
    mutation,
    expected_status,
):
    prepared = _effect_active_attempt(pg_control_connection)
    attempt_id = prepared["protected_submit_attempt_id"]
    entry = _entry_command(pg_control_connection, attempt_id)
    incidents.project_protection_barrier_failure(
        pg_control_connection,
        protected_submit_attempt_id=attempt_id,
        order_role="SL",
        blocker="initial_stop_deadline_exhausted",
        outcome_ambiguous=False,
        protection_barrier_generation=1,
        trigger_ref="flat-proof-negative",
        now_ms=NOW_MS + 7000,
    )
    kwargs = {
        "protected_submit_attempt_id": attempt_id,
        "ticket_id": str(entry["ticket_id"]),
        "exposure_episode_id": str(entry["exposure_episode_id"]),
        "netting_domain_key": str(entry["netting_domain_key"]),
        "source_entry_exchange_command_id": str(entry["exchange_command_id"]),
        "protection_barrier_generation": 1,
        "authoritative_position_flat": True,
        "exact_live_residual_absent": True,
        "resolution_source": "matched_flat_reconciliation_tick",
        "now_ms": NOW_MS + 8000,
        **mutation,
    }

    result = incidents.resolve_protection_barrier_from_flat_proof(
        pg_control_connection,
        **kwargs,
    )

    assert result["status"] == expected_status
    assert _attempt(pg_control_connection, attempt_id)[
        "protection_barrier_state"
    ] == "hard_stopped"
    assert _one(pg_control_connection, "brc_runtime_incidents")["status"] == "open"
    assert _incident_hold(pg_control_connection)["status"] == "active"


def _effect_active_attempt(conn) -> dict:
    prepared = _entry_accepted_local_lifecycle_failed_attempt(conn)
    project_reconciled_entry_execution(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        exchange_order_id="exchange-entry-1",
        executed_qty=Decimal("0.010"),
        average_exec_price=Decimal("2000"),
        exchange_observed_at_ms=NOW_MS + 6000,
        now_ms=NOW_MS + 6000,
    )
    materialize_ticket_bound_reconciliation_tick(
        conn,
        protected_submit_attempt_id=prepared["protected_submit_attempt_id"],
        tick_kind="scheduled",
        exchange_snapshot=_cumulative_entry_fill_snapshot(prepared, qty="0.010"),
        now_ms=NOW_MS + 6001,
    )
    return prepared


def _entry_command(conn, attempt_id: str) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_exchange_commands "
                "WHERE protected_submit_attempt_id = :attempt_id AND order_role = 'ENTRY'"
            ),
            {"attempt_id": attempt_id},
        ).mappings().one()
    )


def _attempt(conn, attempt_id: str) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_protected_submit_attempts "
                "WHERE protected_submit_attempt_id = :attempt_id"
            ),
            {"attempt_id": attempt_id},
        ).mappings().one()
    )


def _incident_hold(conn) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_scope_freezes "
                "WHERE source_kind = 'protection_barrier'"
            )
        ).mappings().one()
    )


def _hold_by_id(conn, hold_id: str) -> dict:
    return dict(
        conn.execute(
            text(
                "SELECT * FROM brc_ticket_bound_scope_freezes "
                "WHERE scope_freeze_id = :hold_id"
            ),
            {"hold_id": hold_id},
        ).mappings().one()
    )


def _count(conn, table: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def _count_incident_holds(conn) -> int:
    return int(
        conn.execute(
            text(
                "SELECT count(*) FROM brc_ticket_bound_scope_freezes "
                "WHERE source_kind = 'protection_barrier'"
            )
        ).scalar_one()
    )


def _one(conn, table: str) -> dict:
    return dict(conn.execute(text(f"SELECT * FROM {table}")).mappings().one())
