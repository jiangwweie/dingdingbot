"""Ticket-bound lifecycle safety classification helpers.

This module owns the post-submit state vocabulary. It does not call the
exchange, FinalGate, Operation Layer, or OrderLifecycle; callers pass already
observed facts and receive deterministic lifecycle states.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


LIFECYCLE_HARD_STOP_STATUSES = {
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
    "runner_mutation_failed",
    "runner_reconciliation_mismatch",
    "position_closed_protection_live",
    "final_exit_unknown",
    "settlement_blocked",
    "review_blocked",
}


class LifecyclePhase(str, Enum):
    UNKNOWN = "unknown"
    SUBMITTING = "submitting"
    OPEN = "open"
    REDUCING = "reducing"
    EXITING = "exiting"
    CLOSED = "closed"


class ProtectionState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    PROTECTED = "protected"
    DEGRADED = "degraded"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ReconciliationState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    MATCHED = "matched"
    MISMATCH = "mismatch"
    OUTCOME_UNKNOWN = "outcome_unknown"


class LifecycleControlState(str, Enum):
    AUTOMATED = "automated"
    RECOVERY_REQUIRED = "recovery_required"
    HARD_STOPPED = "hard_stopped"
    OWNER_REQUIRED = "owner_required"
    COMPLETED = "completed"


class OwnerLifecycleState(str, Enum):
    PROCESSING = "processing"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    NEEDS_INTERVENTION = "needs_intervention"
    COMPLETED = "completed"


@dataclass(frozen=True)
class LifecycleStatusSpecification:
    phase: LifecyclePhase
    protection_state: ProtectionState
    reconciliation_state: ReconciliationState
    control_state: LifecycleControlState
    event_type: str
    next_action: str
    failure_stage: str | None = None


def _spec(
    phase: LifecyclePhase,
    protection: ProtectionState,
    reconciliation: ReconciliationState,
    control: LifecycleControlState,
    event_type: str,
    next_action: str,
    failure_stage: str | None = None,
) -> LifecycleStatusSpecification:
    return LifecycleStatusSpecification(
        phase=phase,
        protection_state=protection,
        reconciliation_state=reconciliation,
        control_state=control,
        event_type=event_type,
        next_action=next_action,
        failure_stage=failure_stage,
    )


LIFECYCLE_STATUS_SPECIFICATIONS: dict[str, LifecycleStatusSpecification] = {
    "entry_submit_sent": _spec(
        LifecyclePhase.SUBMITTING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "entry_submitted",
        "wait_for_entry_fill_or_reconcile_order_status",
    ),
    "entry_fill_pending": _spec(
        LifecyclePhase.SUBMITTING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "hard_stopped",
        "wait_for_entry_fill_or_reconcile_order_status",
    ),
    "entry_filled": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "entry_filled",
        "materialize_ticket_bound_exit_protection_set",
    ),
    "exit_protection_submitted": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "exit_protection_materialization_started",
        "run_exchange_protection_reconciler",
    ),
    "position_protected": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.PROTECTED,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "exit_protection_reconciled",
        "continue_lifecycle_monitoring",
    ),
    "tp1_filled": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "tp1_filled",
        "run_official_runner_mutation_command",
    ),
    "sl_adjust_pending": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "sl_cancel_requested",
        "run_official_runner_mutation_command",
    ),
    "runner_protected": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.PROTECTED,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "runner_protected",
        "continue_runner_monitoring",
    ),
    "final_exit_detected": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "final_exit_detected",
        "run_final_exit_reconciliation",
    ),
    "reconciliation_matched": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.AUTOMATED,
        "reconciliation_matched",
        "settle_ticket_bound_budget",
    ),
    "budget_settled": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.AUTOMATED,
        "budget_settled",
        "record_ticket_bound_review",
    ),
    "review_recorded": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.AUTOMATED,
        "review_recorded",
        "finalize_ticket_bound_lifecycle",
    ),
    "lifecycle_closed": _spec(
        LifecyclePhase.CLOSED,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.COMPLETED,
        "lifecycle_closed",
        "lifecycle_closed",
    ),
    "blocked": _spec(
        LifecyclePhase.UNKNOWN,
        ProtectionState.UNKNOWN,
        ReconciliationState.OUTCOME_UNKNOWN,
        LifecycleControlState.HARD_STOPPED,
        "hard_stopped",
        "repair_ticket_bound_lifecycle_inputs",
        "unknown",
    ),
    "submit_failed": _spec(
        LifecyclePhase.SUBMITTING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.PENDING,
        LifecycleControlState.HARD_STOPPED,
        "submit_failed",
        "release_or_expire_ticket_scope_after_submit_failure",
        "submit",
    ),
    "presubmit_reconciled_absent": _spec(
        LifecyclePhase.CLOSED,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.COMPLETED,
        "presubmit_reconciled_absent",
        "lifecycle_closed",
        "submit",
    ),
    "entry_unknown": _spec(
        LifecyclePhase.SUBMITTING,
        ProtectionState.UNKNOWN,
        ReconciliationState.OUTCOME_UNKNOWN,
        LifecycleControlState.HARD_STOPPED,
        "entry_unknown",
        "run_exchange_order_reconciliation_before_retry",
        "entry",
    ),
    "entry_orphaned": _spec(
        LifecyclePhase.SUBMITTING,
        ProtectionState.UNKNOWN,
        ReconciliationState.OUTCOME_UNKNOWN,
        LifecycleControlState.HARD_STOPPED,
        "entry_orphaned",
        "reconcile_exchange_order_into_pg_before_new_submit",
        "entry",
    ),
    "entry_partial_fill_unhandled": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.MISSING,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "entry_partial_fill_detected",
        "reconcile_partial_fill_and_protect_actual_qty",
        "entry",
    ),
    "protection_missing": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.MISSING,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "protection_missing",
        "run_official_recovery_submit_sl_or_flatten",
        "protection",
    ),
    "protection_degraded": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.DEGRADED,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "protection_degraded",
        "run_official_recovery_submit_missing_tp1",
        "protection",
    ),
    "protection_submit_failed": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.UNKNOWN,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "protection_submit_failed",
        "run_official_recovery_submit_missing_protection_or_flatten",
        "protection",
    ),
    "protection_reconciliation_mismatch": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.UNKNOWN,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "protection_reconciliation_mismatch",
        "run_exchange_protection_reconciler",
        "reconciliation",
    ),
    "exchange_orphan_detected": _spec(
        LifecyclePhase.UNKNOWN,
        ProtectionState.UNKNOWN,
        ReconciliationState.OUTCOME_UNKNOWN,
        LifecycleControlState.HARD_STOPPED,
        "exchange_orphan_detected",
        "freeze_new_submits_for_scope",
        "reconciliation",
    ),
    "tp1_or_sl_orphaned": _spec(
        LifecyclePhase.OPEN,
        ProtectionState.UNKNOWN,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "tp1_or_sl_orphaned",
        "prove_or_cancel_orphan_protection_order",
        "protection",
    ),
    "runner_mutation_pending": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.PENDING,
        ReconciliationState.PENDING,
        LifecycleControlState.AUTOMATED,
        "runner_mutation_pending",
        "run_official_runner_mutation_command",
    ),
    "runner_mutation_failed": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.UNKNOWN,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "runner_mutation_failed",
        "repair_runner_mutation_or_flatten",
        "runner",
    ),
    "runner_reconciliation_mismatch": _spec(
        LifecyclePhase.REDUCING,
        ProtectionState.UNKNOWN,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "runner_reconciliation_mismatch",
        "run_exchange_runner_reconciler",
        "runner",
    ),
    "position_closed_protection_live": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.DEGRADED,
        ReconciliationState.MISMATCH,
        LifecycleControlState.RECOVERY_REQUIRED,
        "position_closed_protection_live",
        "run_official_orphan_protection_cancel",
        "protection",
    ),
    "final_exit_unknown": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.UNKNOWN,
        ReconciliationState.OUTCOME_UNKNOWN,
        LifecycleControlState.HARD_STOPPED,
        "final_exit_unknown",
        "run_final_exit_reconciliation",
        "exit",
    ),
    "settlement_blocked": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.RECOVERY_REQUIRED,
        "settlement_blocked",
        "repair_budget_settlement_evidence",
        "settlement",
    ),
    "review_blocked": _spec(
        LifecyclePhase.EXITING,
        ProtectionState.NOT_APPLICABLE,
        ReconciliationState.MATCHED,
        LifecycleControlState.RECOVERY_REQUIRED,
        "review_blocked",
        "repair_review_evidence",
        "review",
    ),
}


@dataclass(frozen=True)
class LifecycleDecision:
    status: str
    event_type: str
    next_action: str
    first_blocker: str | None
    blockers: tuple[str, ...]
    phase: LifecyclePhase
    protection_state: ProtectionState
    reconciliation_state: ReconciliationState
    control_state: LifecycleControlState
    owner_state: OwnerLifecycleState
    failure_code: str | None
    failure_stage: str | None
    owner_action_required: bool = False
    exchange_write_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "event_type": self.event_type,
            "next_action": self.next_action,
            "first_blocker": self.first_blocker,
            "blockers": list(self.blockers),
            "phase": self.phase.value,
            "protection_state": self.protection_state.value,
            "reconciliation_state": self.reconciliation_state.value,
            "control_state": self.control_state.value,
            "owner_state": self.owner_state.value,
            "failure_code": self.failure_code,
            "failure_stage": self.failure_stage,
            "owner_action_required": self.owner_action_required,
            "exchange_write_authorized": False,
        }


LifecycleSafetyClassification = LifecycleDecision


_UNKNOWN_SPECIFICATION = _spec(
    LifecyclePhase.UNKNOWN,
    ProtectionState.UNKNOWN,
    ReconciliationState.OUTCOME_UNKNOWN,
    LifecycleControlState.HARD_STOPPED,
    "hard_stopped",
    "repair_ticket_bound_lifecycle_inputs",
    "unknown",
)


def lifecycle_decision_for_status(
    status: str,
    *,
    event_type: str | None = None,
    blockers: list[str] | tuple[str, ...] = (),
    next_action: str | None = None,
    owner_action_required: bool = False,
) -> LifecycleDecision:
    normalized_status = str(status or "blocked")
    specification = LIFECYCLE_STATUS_SPECIFICATIONS.get(
        normalized_status,
        _UNKNOWN_SPECIFICATION,
    )
    normalized_blockers = _dedupe([str(item) for item in blockers])
    if (
        normalized_status in LIFECYCLE_HARD_STOP_STATUSES
        or specification.control_state is LifecycleControlState.HARD_STOPPED
    ) and not normalized_blockers:
        normalized_blockers = [normalized_status]
    control_state = specification.control_state
    if owner_action_required:
        control_state = LifecycleControlState.OWNER_REQUIRED
    owner_state = _owner_state_for_control(control_state)
    first_blocker = normalized_blockers[0] if normalized_blockers else None
    return LifecycleDecision(
        status=normalized_status,
        event_type=str(event_type or specification.event_type),
        next_action=str(next_action or specification.next_action),
        first_blocker=first_blocker,
        blockers=tuple(normalized_blockers),
        phase=specification.phase,
        protection_state=specification.protection_state,
        reconciliation_state=specification.reconciliation_state,
        control_state=control_state,
        owner_state=owner_state,
        failure_code=first_blocker,
        failure_stage=specification.failure_stage if first_blocker else None,
        owner_action_required=owner_action_required,
        exchange_write_authorized=False,
    )


def reduce_lifecycle_decision(
    *,
    current_status: str | None,
    target_status: str,
    event_type: str | None = None,
    blockers: list[str] | tuple[str, ...] = (),
    next_action: str | None = None,
    owner_action_required: bool = False,
) -> LifecycleDecision:
    current = str(current_status or "")
    target = str(target_status or "blocked")
    if current == "lifecycle_closed" and target != "lifecycle_closed":
        return lifecycle_decision_for_status(
            "lifecycle_closed",
            event_type="lifecycle_transition_rejected",
            blockers=["lifecycle_closed_is_terminal"],
            next_action="lifecycle_closed",
        )
    return lifecycle_decision_for_status(
        target,
        event_type=event_type,
        blockers=blockers,
        next_action=next_action,
        owner_action_required=owner_action_required,
    )


def _owner_state_for_control(
    control_state: LifecycleControlState,
) -> OwnerLifecycleState:
    if control_state is LifecycleControlState.COMPLETED:
        return OwnerLifecycleState.COMPLETED
    if control_state is LifecycleControlState.OWNER_REQUIRED:
        return OwnerLifecycleState.NEEDS_INTERVENTION
    if control_state is LifecycleControlState.HARD_STOPPED:
        return OwnerLifecycleState.TEMPORARILY_UNAVAILABLE
    return OwnerLifecycleState.PROCESSING


def classify_exit_protection_materialization(
    *,
    attempt: dict[str, Any],
    entry_order: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    blockers: list[str],
) -> LifecycleDecision:
    normalized = _dedupe(blockers)
    if not normalized:
        return lifecycle_decision_for_status(
            "position_protected",
            event_type="entry_filled",
            next_action="run_ticket_bound_post_submit_closure",
        )

    status = _exit_protection_status(
        attempt=attempt,
        entry_order=entry_order,
        sl_order=sl_order,
        tp1_order=tp1_order,
        blockers=normalized,
    )
    return lifecycle_decision_for_status(
        status,
        blockers=normalized,
    )


def classify_runner_protection_adjustment(
    *,
    blockers: list[str],
    tp1_waiting: bool,
    runner_ref_missing_only: bool,
) -> LifecycleDecision:
    normalized = _dedupe(blockers)
    if not normalized:
        return lifecycle_decision_for_status("runner_protected")
    if tp1_waiting:
        return lifecycle_decision_for_status(
            "position_protected",
            event_type="hard_stopped",
            next_action="wait_for_tp1_fill",
            blockers=normalized,
        )
    if runner_ref_missing_only:
        return lifecycle_decision_for_status(
            "runner_mutation_pending",
            blockers=normalized,
        )
    status = (
        "runner_mutation_failed"
        if any("runner" in blocker for blocker in normalized)
        else "protection_reconciliation_mismatch"
    )
    return lifecycle_decision_for_status(
        status,
        blockers=normalized,
    )


def classify_sequential_submit_result(
    *,
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
    blockers: list[str],
) -> LifecycleDecision:
    normalized = _dedupe(blockers)
    submitted_orders = [
        dict(order)
        for order in submit_result.get("submitted_orders", [])
        if isinstance(order, dict)
    ]
    entry_order = _order_by_role(submitted_orders, "ENTRY")
    sl_order = _order_by_role(submitted_orders, "SL")
    tp1_order = _order_by_role(submitted_orders, "TP1")
    request_orders = [
        dict(order)
        for order in _as_dict(attempt.get("submit_request")).get("orders", [])
        if isinstance(order, dict)
    ]
    entry_request = _order_by_role(request_orders, "ENTRY")

    status = _sequential_submit_status(
        submit_result=submit_result,
        entry_order=entry_order,
        sl_order=sl_order,
        tp1_order=tp1_order,
        entry_request=entry_request,
        blockers=normalized,
    )
    if not normalized:
        normalized = [status]
    return lifecycle_decision_for_status(
        status,
        blockers=normalized,
    )


def classify_protection_reconciliation(
    *,
    position_qty: Any,
    has_valid_sl: bool,
    has_valid_tp1: bool,
    has_runner_sl: bool,
    tp1_filled: bool,
    position_flat: bool,
    live_protection_orders: list[dict[str, Any]],
) -> LifecycleDecision:
    blockers: list[str] = []
    open_position = _decimal(position_qty) > 0 and not position_flat
    if position_flat and live_protection_orders:
        blockers.append("position_flat_with_live_protection_orders")
        status = "position_closed_protection_live"
    elif open_position and not has_valid_sl:
        blockers.append("open_position_without_valid_sl")
        status = "protection_missing"
    elif open_position and not has_valid_tp1 and not tp1_filled:
        blockers.append("open_position_without_valid_tp1")
        status = "protection_degraded"
    elif tp1_filled and not has_runner_sl:
        blockers.append("tp1_filled_without_runner_sl")
        status = "runner_mutation_pending"
    else:
        return lifecycle_decision_for_status("position_protected")
    return lifecycle_decision_for_status(status, blockers=blockers)


def _exit_protection_status(
    *,
    attempt: dict[str, Any],
    entry_order: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    blockers: list[str],
) -> str:
    if _has_prefix(blockers, "protected_submit_attempt_not_submitted"):
        return "submit_failed"
    if _has_prefix(blockers, "submit_result_not_submitted"):
        return "submit_failed"
    if "entry_order_missing" in blockers:
        return "entry_unknown"
    if "entry_exchange_order_id_missing" in blockers and entry_order:
        return "entry_orphaned"
    if _has_prefix(blockers, "entry_status_not_filled"):
        status = str(entry_order.get("status") or "").strip().lower()
        filled_qty = _decimal(entry_order.get("filled_qty"))
        if status in {"new", "open", "submitted", "accepted"} and filled_qty <= 0:
            return "entry_fill_pending"
        if status in {"canceled", "cancelled", "rejected", "failed", "expired"}:
            return "submit_failed"
        return "entry_unknown"
    if "entry_partial_fill_not_lifecycle_ready" in blockers:
        return "entry_partial_fill_unhandled"
    if "entry_filled_qty_missing" in blockers or "entry_average_exec_price_missing" in blockers:
        return "entry_unknown"
    sl_missing = any(blocker.startswith("sl_") for blocker in blockers) or not sl_order
    tp1_missing = any(blocker.startswith("tp1_") for blocker in blockers) or not tp1_order
    if sl_missing and tp1_missing:
        return "protection_missing"
    if sl_missing:
        return "protection_missing"
    if tp1_missing:
        return "protection_degraded"
    if attempt.get("status") == "submitted":
        return "protection_reconciliation_mismatch"
    return "blocked"


def _sequential_submit_status(
    *,
    submit_result: dict[str, Any],
    entry_order: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    entry_request: dict[str, Any],
    blockers: list[str],
) -> str:
    result_status = str(submit_result.get("status") or "").strip()
    if not submit_result.get("exchange_write_called"):
        return "submit_failed"
    if result_status in {"entry_submit_failed", "exchange_submit_failed"} and not entry_order:
        return "submit_failed"
    if entry_order and not str(entry_order.get("exchange_order_id") or "").strip():
        return "entry_orphaned"
    if entry_order and _entry_partial_fill(entry_order=entry_order, entry_request=entry_request):
        return "entry_partial_fill_unhandled"
    if entry_order and _entry_unknown(entry_order):
        return "entry_unknown"
    if result_status == "order_lifecycle_update_failed" and entry_order:
        return "entry_orphaned"
    if entry_order and not sl_order:
        return "protection_missing"
    if entry_order and sl_order and not tp1_order:
        return "protection_degraded"
    if result_status == "protection_submit_failed":
        return "protection_degraded" if sl_order else "protection_missing"
    if result_status.endswith("_failed"):
        return "submit_failed"
    if blockers:
        return "submit_failed"
    return "submit_failed"


def _event_type_for_status(status: str) -> str:
    return lifecycle_decision_for_status(status).event_type


def _next_action_for_status(status: str) -> str:
    return lifecycle_decision_for_status(status).next_action


def _has_prefix(blockers: list[str], prefix: str) -> bool:
    return any(blocker.startswith(prefix) for blocker in blockers)


def _order_by_role(orders: list[dict[str, Any]], role: str) -> dict[str, Any]:
    expected = role.upper()
    for order in orders:
        if str(order.get("order_role") or "").upper() == expected:
            return dict(order)
    return {}


def _entry_partial_fill(
    *,
    entry_order: dict[str, Any],
    entry_request: dict[str, Any],
) -> bool:
    filled_qty = _decimal(entry_order.get("filled_qty"))
    requested_qty = _decimal(
        entry_order.get("amount")
        if entry_order.get("amount") is not None
        else entry_request.get("amount")
    )
    return filled_qty > 0 and requested_qty > 0 and filled_qty < requested_qty


def _entry_unknown(entry_order: dict[str, Any]) -> bool:
    status = str(entry_order.get("status") or "").strip().lower()
    if status in {"filled", "closed"}:
        return False
    if _decimal(entry_order.get("filled_qty")) > 0:
        return False
    return status not in {"new", "open", "submitted", "accepted"}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
