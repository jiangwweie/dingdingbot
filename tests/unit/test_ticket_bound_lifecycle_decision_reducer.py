from __future__ import annotations

import pytest

from src.application.action_time.lifecycle_safety_core import (
    LIFECYCLE_HARD_STOP_STATUSES,
    LIFECYCLE_STATUS_SPECIFICATIONS,
    LifecycleControlState,
    LifecyclePhase,
    OwnerLifecycleState,
    ProtectionState,
    ReconciliationState,
    lifecycle_decision_for_status,
    reduce_lifecycle_decision,
)


MIGRATION_114_LIFECYCLE_STATUSES = {
    "entry_submit_sent",
    "entry_fill_pending",
    "entry_filled",
    "exit_protection_submitted",
    "position_protected",
    "tp1_filled",
    "sl_adjust_pending",
    "runner_protected",
    "final_exit_detected",
    "reconciliation_matched",
    "budget_settled",
    "review_recorded",
    "lifecycle_closed",
    "blocked",
    "submit_failed",
    "entry_unknown",
    "entry_orphaned",
    "entry_partial_fill_unhandled",
    "protection_missing",
    "protection_degraded",
    "protection_submit_failed",
    "protection_reconciliation_mismatch",
    "exchange_orphan_detected",
    "tp1_or_sl_orphaned",
    "runner_mutation_pending",
    "runner_mutation_failed",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
    "final_exit_unknown",
    "settlement_blocked",
    "review_blocked",
}


def test_every_migration_114_status_has_one_typed_specification():
    assert set(LIFECYCLE_STATUS_SPECIFICATIONS) == MIGRATION_114_LIFECYCLE_STATUSES


@pytest.mark.parametrize(
    (
        "status",
        "phase",
        "protection",
        "reconciliation",
        "control",
        "owner_state",
        "next_action",
    ),
    [
        (
            "entry_fill_pending",
            LifecyclePhase.SUBMITTING,
            ProtectionState.PENDING,
            ReconciliationState.PENDING,
            LifecycleControlState.AUTOMATED,
            OwnerLifecycleState.PROCESSING,
            "wait_for_entry_fill_or_reconcile_order_status",
        ),
        (
            "position_protected",
            LifecyclePhase.OPEN,
            ProtectionState.PROTECTED,
            ReconciliationState.PENDING,
            LifecycleControlState.AUTOMATED,
            OwnerLifecycleState.PROCESSING,
            "continue_lifecycle_monitoring",
        ),
        (
            "runner_mutation_pending",
            LifecyclePhase.REDUCING,
            ProtectionState.PENDING,
            ReconciliationState.PENDING,
            LifecycleControlState.AUTOMATED,
            OwnerLifecycleState.PROCESSING,
            "run_official_runner_mutation_command",
        ),
        (
            "protection_missing",
            LifecyclePhase.OPEN,
            ProtectionState.MISSING,
            ReconciliationState.MISMATCH,
            LifecycleControlState.RECOVERY_REQUIRED,
            OwnerLifecycleState.PROCESSING,
            "run_official_recovery_submit_sl_or_flatten",
        ),
        (
            "entry_unknown",
            LifecyclePhase.SUBMITTING,
            ProtectionState.UNKNOWN,
            ReconciliationState.OUTCOME_UNKNOWN,
            LifecycleControlState.HARD_STOPPED,
            OwnerLifecycleState.TEMPORARILY_UNAVAILABLE,
            "run_exchange_order_reconciliation_before_retry",
        ),
        (
            "lifecycle_closed",
            LifecyclePhase.CLOSED,
            ProtectionState.NOT_APPLICABLE,
            ReconciliationState.MATCHED,
            LifecycleControlState.COMPLETED,
            OwnerLifecycleState.COMPLETED,
            "lifecycle_closed",
        ),
    ],
)
def test_lifecycle_status_projects_one_typed_decision(
    status,
    phase,
    protection,
    reconciliation,
    control,
    owner_state,
    next_action,
):
    blockers = ["exchange_outcome_unknown"] if status in LIFECYCLE_HARD_STOP_STATUSES else []
    decision = lifecycle_decision_for_status(status, blockers=blockers)

    assert decision.status == status
    assert decision.phase is phase
    assert decision.protection_state is protection
    assert decision.reconciliation_state is reconciliation
    assert decision.control_state is control
    assert decision.owner_state is owner_state
    assert decision.next_action == next_action


def test_unknown_status_fails_closed_without_inventing_pg_status():
    decision = lifecycle_decision_for_status(
        "venue_new_state",
        blockers=["unsupported_lifecycle_status:venue_new_state"],
    )

    assert decision.status == "venue_new_state"
    assert decision.phase is LifecyclePhase.UNKNOWN
    assert decision.protection_state is ProtectionState.UNKNOWN
    assert decision.reconciliation_state is ReconciliationState.OUTCOME_UNKNOWN
    assert decision.control_state is LifecycleControlState.HARD_STOPPED
    assert decision.owner_state is OwnerLifecycleState.TEMPORARILY_UNAVAILABLE
    assert decision.next_action == "repair_ticket_bound_lifecycle_inputs"


def test_hard_stop_gets_a_deterministic_blocker_when_caller_omits_one():
    decision = lifecycle_decision_for_status("entry_unknown")

    assert decision.first_blocker == "entry_unknown"
    assert decision.blockers == ("entry_unknown",)
    assert decision.failure_code == "entry_unknown"
    assert decision.failure_stage == "entry"


def test_generic_blocked_control_state_also_gets_a_deterministic_blocker():
    decision = lifecycle_decision_for_status("blocked")

    assert decision.control_state is LifecycleControlState.HARD_STOPPED
    assert decision.first_blocker == "blocked"
    assert decision.blockers == ("blocked",)


def test_explicit_evidence_driven_event_and_action_override_are_preserved():
    decision = lifecycle_decision_for_status(
        "protection_reconciliation_mismatch",
        event_type="exchange_snapshot_missing",
        blockers=["exchange_position_snapshot_missing"],
        next_action="refresh_exchange_position_snapshot",
    )

    assert decision.event_type == "exchange_snapshot_missing"
    assert decision.next_action == "refresh_exchange_position_snapshot"
    assert decision.first_blocker == "exchange_position_snapshot_missing"


def test_owner_required_is_explicit_and_never_grants_action_authority():
    decision = lifecycle_decision_for_status(
        "runner_mutation_failed",
        blockers=["runner_mutation_retry_limit_exhausted"],
        owner_action_required=True,
    )

    assert decision.control_state is LifecycleControlState.OWNER_REQUIRED
    assert decision.owner_state is OwnerLifecycleState.NEEDS_INTERVENTION
    assert decision.owner_action_required is True
    assert decision.exchange_write_authorized is False


def test_closed_lifecycle_cannot_regress_to_an_open_state():
    decision = reduce_lifecycle_decision(
        current_status="lifecycle_closed",
        target_status="position_protected",
        event_type="exit_protection_reconciled",
    )

    assert decision.status == "lifecycle_closed"
    assert decision.phase is LifecyclePhase.CLOSED
    assert decision.first_blocker == "lifecycle_closed_is_terminal"
    assert decision.event_type == "lifecycle_transition_rejected"


def test_normal_transition_uses_target_spec_and_observed_event():
    decision = reduce_lifecycle_decision(
        current_status="tp1_filled",
        target_status="runner_mutation_pending",
        event_type="runner_mutation_pending",
        blockers=["runner_sl_exchange_order_id_required"],
    )

    assert decision.status == "runner_mutation_pending"
    assert decision.phase is LifecyclePhase.REDUCING
    assert decision.event_type == "runner_mutation_pending"
    assert decision.next_action == "run_official_runner_mutation_command"
    assert decision.first_blocker == "runner_sl_exchange_order_id_required"
