#!/usr/bin/env python3
"""Build read-only watch evidence for runtime and strategy-group signals.

The evidence combines the ACTIVE runtime observation status artifact with a
strategy-group read-only preview. It is designed for operator handoff while the
runtime loop is waiting for a real signal: no PG writes, no shadow candidates,
no ExecutionIntent, no orders, and no runtime mutation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def build_watch_evidence(
    *,
    active_status_artifact: dict[str, Any],
    strategy_preview_artifact: dict[str, Any],
) -> dict[str, Any]:
    runtime_summaries = [
        _runtime_summary(row)
        for row in active_status_artifact.get("runtime_signal_summaries") or []
        if isinstance(row, dict)
    ]
    runtime_ready = [
        row
        for row in runtime_summaries
        if row.get("signal_type") == "would_enter"
        or row.get("status") in {"ready_for_prepare", "ready_for_final_gate_preflight"}
    ]
    runtime_ready_for_prepare = [
        row for row in runtime_ready if row.get("status") == "ready_for_prepare"
    ]
    runtime_ready_for_preflight = [
        row
        for row in runtime_ready
        if row.get("status") == "ready_for_final_gate_preflight"
    ]
    strategy_would_enter = [
        _strategy_summary(row)
        for row in strategy_preview_artifact.get("would_enter_signals") or []
        if isinstance(row, dict)
    ]
    strategy_no_action = [
        _strategy_summary(row)
        for row in strategy_preview_artifact.get("no_action_signals") or []
        if isinstance(row, dict)
    ]
    forbidden_effects = _forbidden_effects(
        ("active_status_artifact", active_status_artifact),
        ("strategy_preview_artifact", strategy_preview_artifact),
    )
    status = "blocked_forbidden_effect"
    next_step = "resolve_signal_watch_forbidden_effects"
    if not forbidden_effects:
        if runtime_ready_for_preflight:
            status = "runtime_prepare_records_ready_for_preview"
            next_step = "run_final_gate_arm_preview_and_disabled_smoke_only"
        elif runtime_ready:
            status = "runtime_signal_ready"
            next_step = "review_runtime_ready_signal_prepare_path"
        elif strategy_would_enter:
            status = "strategy_group_signal_review_available"
            next_step = "review_would_enter_strategy_group_without_execution"
        elif active_status_artifact.get("status") == "observation_window_complete_no_signal":
            status = "watch_window_complete_no_signal"
            next_step = "review_no_signal_window_or_start_new_observation"
        elif active_status_artifact.get("status") == "waiting_for_signal":
            status = "watching_no_signal"
            next_step = "continue_active_runtime_observation"
        else:
            status = "watch_attention"
            next_step = "review_active_runtime_observation_status"

    return {
        "scope": "runtime_strategy_signal_watch_evidence",
        "status": status,
        "active_runtime_observation": {
            "status": active_status_artifact.get("status"),
            "latest_status": active_status_artifact.get("latest_status"),
            "latest_iteration": active_status_artifact.get("latest_iteration"),
            "iterations_completed": active_status_artifact.get("iterations_completed"),
            "iterations_requested": active_status_artifact.get("iterations_requested"),
            "iterations_remaining": active_status_artifact.get("iterations_remaining"),
            "artifact_stale": active_status_artifact.get("artifact_stale"),
            "stop_reason": active_status_artifact.get("stop_reason"),
            "active_runtime_count": active_status_artifact.get("active_runtime_count"),
            "monitored_runtime_count": active_status_artifact.get(
                "monitored_runtime_count"
            ),
            "selected_runtime_instance_ids": active_status_artifact.get(
                "selected_runtime_instance_ids"
            )
            or [],
            "prepared_authorization_id": active_status_artifact.get(
                "prepared_authorization_id"
            ),
        },
        "runtime_signals": runtime_summaries,
        "runtime_ready_signals": runtime_ready,
        "runtime_prepare_context": {
            "ready_for_prepare_count": len(runtime_ready_for_prepare),
            "ready_for_final_gate_preflight_count": len(runtime_ready_for_preflight),
            "prepared_authorization_id": active_status_artifact.get(
                "prepared_authorization_id"
            ),
            "shadow_candidate_id": active_status_artifact.get("shadow_candidate_id"),
            "allowed_non_executing_followups": [
                "create_shadow_signal_evaluation",
                "create_shadow_order_candidate",
                "create_prepare_authorization_record",
                "run_final_gate_preview",
                "run_arm_preview",
                "run_disabled_first_real_submit_smoke",
            ],
            "forbidden_followups": [
                "create_executable_execution_intent",
                "submit_order_lifecycle",
                "execute_first_real_submit",
                "place_exchange_order",
                "withdrawal_or_transfer",
            ],
        },
        "strategy_group_preview": {
            "status": strategy_preview_artifact.get("status"),
            "source_requested": strategy_preview_artifact.get("source_requested"),
            "market_source": strategy_preview_artifact.get("market_source"),
            "checks": strategy_preview_artifact.get("checks") or {},
        },
        "strategy_group_would_enter_signals": strategy_would_enter,
        "strategy_group_no_action_signals": strategy_no_action,
        "checks": {
            "runtime_ready_signal_count": len(runtime_ready),
            "strategy_group_would_enter_signal_count": len(strategy_would_enter),
            "strategy_group_no_action_signal_count": len(strategy_no_action),
            "forbidden_effects": forbidden_effects,
        },
        "watch_evidence_plan": {
            "not_executed": True,
            "next_step": next_step,
            "allowed_review_checkpoints": _allowed_review_checkpoints(status),
            "records_observation": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "read_artifacts_only": True,
            "strategy_preview_only": True,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_started": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": forbidden_effects,
        },
    }


def _runtime_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_instance_id": row.get("runtime_instance_id"),
        "strategy_family_id": row.get("strategy_family_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "status": row.get("status"),
        "evaluation_status": row.get("evaluation_status"),
        "signal_type": row.get("signal_type"),
        "signal_side": row.get("signal_side"),
        "confidence": row.get("confidence"),
        "reason_codes": row.get("reason_codes") or [],
        "human_summary": row.get("human_summary"),
    }


def _strategy_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "strategy_group_id": row.get("strategy_group_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "signal_type": row.get("signal_type"),
        "confidence": row.get("confidence"),
        "reason_codes": row.get("reason_codes") or [],
        "human_summary": row.get("human_summary"),
        "not_order": row.get("not_order"),
        "not_execution_intent": row.get("not_execution_intent"),
        "no_execution_permission": row.get("no_execution_permission"),
        "no_order_permission": row.get("no_order_permission"),
        "no_runtime_start": row.get("no_runtime_start"),
    }


def _allowed_review_checkpoints(status: str) -> list[str]:
    if status == "runtime_signal_ready":
        return [
            "review_runtime_ready_signal",
            "create_shadow_prepare_records_if_authorized",
        ]
    if status == "runtime_prepare_records_ready_for_preview":
        return [
            "run_final_gate_preview",
            "run_arm_preview",
            "run_disabled_first_real_submit_smoke",
        ]
    if status == "strategy_group_signal_review_available":
        return ["review_strategy_group_would_enter_signal_without_execution"]
    if status == "watching_no_signal":
        return ["continue_active_runtime_observation"]
    if status == "watch_window_complete_no_signal":
        return ["review_no_signal_window", "start_new_observation_window"]
    return ["review_signal_watch_evidence"]


def _forbidden_effects(*sources: tuple[str, dict[str, Any]]) -> list[str]:
    effects: list[str] = []
    for source_name, artifact in sources:
        safety = artifact.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        for key in (
            "exchange_write_called",
            "order_created",
            "order_lifecycle_called",
            "execution_intent_created",
            "creates_execution_intent",
            "places_order",
            "calls_order_lifecycle",
            "shadow_candidate_created",
            "runtime_budget_mutated",
            "attempt_counter_mutated",
            "withdrawal_or_transfer_created",
            "withdrawal_or_transfer_requested",
        ):
            if safety.get(key) is True:
                effects.append(f"{source_name}.{key}")
        for item in safety.get("forbidden_effects") or []:
            effects.append(f"{source_name}.{item}")
    return sorted(set(effects))
