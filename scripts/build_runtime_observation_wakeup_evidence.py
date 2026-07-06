#!/usr/bin/env python3
"""Build Owner wake-up evidence from runtime observation evidence.

This evidence consumes existing runtime observation operator evidence. It does
not call APIs, connect to PG, resolve runtimes, create candidates, create
ExecutionIntents, call OrderLifecycle, place exchange orders, or mutate runtime
state.
"""

from __future__ import annotations

from typing import Any


def build_wakeup_evidence(operator_evidence: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(operator_evidence.get("safety_invariants"))
    review_plan = _as_dict(operator_evidence.get("operator_review_plan"))
    prepare_context = _as_dict(operator_evidence.get("runtime_prepare_context"))
    active = _as_dict(operator_evidence.get("active_runtime_observation"))
    signal_counts = _as_dict(operator_evidence.get("signal_counts"))
    forbidden_effects = _forbidden_effects(operator_evidence)

    ready_count = _int(signal_counts.get("runtime_ready_signal_count"))
    prepared_authorization_id = _text_or_none(
        prepare_context.get("prepared_authorization_id")
        or active.get("prepared_authorization_id")
    )
    shadow_candidate_id = _text_or_none(
        prepare_context.get("shadow_candidate_id")
        or active.get("shadow_candidate_id")
    )
    prepared_evidence_exists = bool(prepared_authorization_id or shadow_candidate_id)

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        owner_attention = "immediate_review_required"
        next_step = "stop_and_review_forbidden_observation_effects"
    elif prepared_evidence_exists:
        status = "prepared_shadow_evidence_ready_for_owner_review"
        owner_attention = "review_when_available"
        next_step = "review_prepared_shadow_evidence_before_first_real_submit_decision"
    elif ready_count > 0:
        status = "runtime_signal_ready_for_non_executing_prepare"
        owner_attention = "review_when_available"
        next_step = "allow_existing_supervisor_to_create_prepare_records_then_review"
    elif operator_evidence.get("status") == "observation_running_no_signal":
        status = "owner_sleep_safe_observation_running"
        owner_attention = "no_owner_action_needed_now"
        next_step = "continue_active_runtime_observation"
    elif operator_evidence.get("status") == "no_signal_window_complete":
        status = "observation_window_complete_no_signal"
        owner_attention = "review_when_available"
        next_step = "review_no_signal_window_before_new_window"
    else:
        status = "operator_evidence_needs_review"
        owner_attention = "review_when_available"
        next_step = "review_operator_evidence_status"

    return {
        "scope": "runtime_observation_wakeup_evidence",
        "status": status,
        "source_operator_status": operator_evidence.get("status"),
        "owner_attention": owner_attention,
        "summary": {
            "active_runtime_count": active.get("active_runtime_count"),
            "monitored_runtime_count": active.get("monitored_runtime_count"),
            "selected_runtime_instance_ids": active.get(
                "selected_runtime_instance_ids"
            )
            or [],
            "latest_iteration": active.get("latest_iteration"),
            "iterations_completed": active.get("iterations_completed"),
            "iterations_remaining": active.get("iterations_remaining"),
            "stop_reason": active.get("stop_reason"),
            "runtime_ready_signal_count": ready_count,
            "strategy_group_would_enter_signal_count": _int(
                signal_counts.get("strategy_group_would_enter_signal_count")
            ),
            "strategy_group_no_action_signal_count": _int(
                signal_counts.get("strategy_group_no_action_signal_count")
            ),
            "prepared_authorization_id": prepared_authorization_id,
            "shadow_candidate_id": shadow_candidate_id,
            "next_step": next_step,
        },
        "allowed_while_owner_asleep": _allowed_while_owner_asleep(
            status=status,
            review_plan=review_plan,
            prepare_context=prepare_context,
        ),
        "requires_owner_before": [
            "executable_first_real_submit",
            "exchange_order_placement",
            "OrderLifecycle_submit",
            "withdrawal_or_transfer",
        ],
        "right_tail_objective_context": {
            "no_signal_is_not_failure": True,
            "small_bounded_losses_allowed_when_runtime_ready": True,
            "force_entry_without_signal": False,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "safety_invariants": {
            "wakeup_evidence_only": True,
            "source_operator_evidence_read_only": (
                safety.get("operator_evidence_only") is True
            ),
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created_by_wakeup_evidence": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def _allowed_while_owner_asleep(
    *,
    status: str,
    review_plan: dict[str, Any],
    prepare_context: dict[str, Any],
) -> list[str]:
    if status == "blocked_forbidden_effect":
        return []
    if status == "owner_sleep_safe_observation_running":
        return ["continue_active_runtime_observation"]
    if status == "runtime_signal_ready_for_non_executing_prepare":
        allowed = list(prepare_context.get("allowed_non_executing_followups") or [])
        return [
            item
            for item in allowed
            if item
            in {
                "create_shadow_signal_evaluation",
                "create_shadow_order_candidate",
                "create_prepare_authorization_record",
                "run_final_gate_preview",
                "run_arm_preview",
                "run_disabled_first_real_submit_smoke",
            }
        ]
    if status == "prepared_shadow_evidence_ready_for_owner_review":
        return [
            "run_final_gate_preview",
            "run_arm_preview",
            "run_disabled_first_real_submit_smoke",
        ]
    return list(review_plan.get("allowed_review_checkpoints") or [])


def _forbidden_effects(source_evidence: dict[str, Any]) -> list[str]:
    safety = _as_dict(source_evidence.get("safety_invariants"))
    effects = [str(item) for item in safety.get("forbidden_effects") or [] if item]
    for key in (
        "execution_intent_created",
        "order_created",
        "order_lifecycle_called",
        "exchange_write_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is True:
            effects.append(key)
    plan = _as_dict(source_evidence.get("operator_review_plan"))
    for key in (
        "creates_execution_intent",
        "places_order",
        "calls_order_lifecycle",
        "withdrawal_or_transfer_requested",
    ):
        if plan.get(key) is True:
            effects.append(f"operator_review_plan.{key}")
    return sorted(set(effects))


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
