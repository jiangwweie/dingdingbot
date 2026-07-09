"""Ticket-bound lifecycle safety classification helpers.

This module owns the post-submit state vocabulary. It does not call the
exchange, FinalGate, Operation Layer, or OrderLifecycle; callers pass already
observed facts and receive deterministic lifecycle states.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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


@dataclass(frozen=True)
class LifecycleSafetyClassification:
    status: str
    event_type: str
    next_action: str
    first_blocker: str | None
    blockers: tuple[str, ...]


def classify_exit_protection_materialization(
    *,
    attempt: dict[str, Any],
    entry_order: dict[str, Any],
    sl_order: dict[str, Any],
    tp1_order: dict[str, Any],
    blockers: list[str],
) -> LifecycleSafetyClassification:
    normalized = _dedupe(blockers)
    if not normalized:
        return LifecycleSafetyClassification(
            status="position_protected",
            event_type="entry_filled",
            next_action="run_ticket_bound_post_submit_closure",
            first_blocker=None,
            blockers=(),
        )

    status = _exit_protection_status(
        attempt=attempt,
        entry_order=entry_order,
        sl_order=sl_order,
        tp1_order=tp1_order,
        blockers=normalized,
    )
    return LifecycleSafetyClassification(
        status=status,
        event_type=_event_type_for_status(status),
        next_action=_next_action_for_status(status),
        first_blocker=normalized[0],
        blockers=tuple(normalized),
    )


def classify_runner_protection_adjustment(
    *,
    blockers: list[str],
    tp1_waiting: bool,
    runner_ref_missing_only: bool,
) -> LifecycleSafetyClassification:
    normalized = _dedupe(blockers)
    if not normalized:
        return LifecycleSafetyClassification(
            status="runner_protected",
            event_type="runner_protected",
            next_action="continue_runner_monitoring",
            first_blocker=None,
            blockers=(),
        )
    if tp1_waiting:
        return LifecycleSafetyClassification(
            status="position_protected",
            event_type="hard_stopped",
            next_action="wait_for_tp1_fill",
            first_blocker=normalized[0],
            blockers=tuple(normalized),
        )
    if runner_ref_missing_only:
        return LifecycleSafetyClassification(
            status="runner_mutation_pending",
            event_type="runner_mutation_pending",
            next_action="run_official_runner_mutation_command",
            first_blocker=normalized[0],
            blockers=tuple(normalized),
        )
    status = (
        "runner_mutation_failed"
        if any("runner" in blocker for blocker in normalized)
        else "protection_reconciliation_mismatch"
    )
    return LifecycleSafetyClassification(
        status=status,
        event_type=_event_type_for_status(status),
        next_action=_next_action_for_status(status),
        first_blocker=normalized[0],
        blockers=tuple(normalized),
    )


def classify_sequential_submit_result(
    *,
    attempt: dict[str, Any],
    submit_result: dict[str, Any],
    blockers: list[str],
) -> LifecycleSafetyClassification:
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
    return LifecycleSafetyClassification(
        status=status,
        event_type=_event_type_for_status(status),
        next_action=_next_action_for_status(status),
        first_blocker=normalized[0],
        blockers=tuple(normalized),
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
) -> LifecycleSafetyClassification:
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
        return LifecycleSafetyClassification(
            status="position_protected",
            event_type="exit_protection_reconciled",
            next_action="continue_lifecycle_monitoring",
            first_blocker=None,
            blockers=(),
        )
    return LifecycleSafetyClassification(
        status=status,
        event_type=_event_type_for_status(status),
        next_action=_next_action_for_status(status),
        first_blocker=blockers[0],
        blockers=tuple(blockers),
    )


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
    if status == "entry_partial_fill_unhandled":
        return "entry_partial_fill_detected"
    if status in {
        "submit_failed",
        "entry_unknown",
        "entry_orphaned",
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
    }:
        return status
    return "hard_stopped"


def _next_action_for_status(status: str) -> str:
    return {
        "submit_failed": "release_or_expire_ticket_scope_after_submit_failure",
        "entry_unknown": "run_exchange_order_reconciliation_before_retry",
        "entry_orphaned": "reconcile_exchange_order_into_pg_before_new_submit",
        "entry_fill_pending": "wait_for_entry_fill_or_reconcile_order_status",
        "entry_partial_fill_unhandled": "reconcile_partial_fill_and_protect_actual_qty",
        "protection_missing": "run_official_recovery_submit_sl_or_flatten",
        "protection_degraded": "run_official_recovery_submit_missing_tp1",
        "protection_submit_failed": "run_official_recovery_submit_missing_protection_or_flatten",
        "protection_reconciliation_mismatch": "run_exchange_protection_reconciler",
        "exchange_orphan_detected": "freeze_new_submits_for_scope",
        "tp1_or_sl_orphaned": "prove_or_cancel_orphan_protection_order",
        "runner_mutation_pending": "run_official_runner_mutation_command",
        "runner_mutation_failed": "repair_runner_mutation_or_flatten",
        "runner_reconciliation_mismatch": "run_exchange_runner_reconciler",
        "position_closed_protection_live": "run_official_orphan_protection_cancel",
        "final_exit_unknown": "run_final_exit_reconciliation",
        "settlement_blocked": "repair_budget_settlement_evidence",
        "review_blocked": "repair_review_evidence",
        "blocked": "repair_ticket_bound_lifecycle_inputs",
    }.get(status, "repair_ticket_bound_lifecycle_inputs")


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
