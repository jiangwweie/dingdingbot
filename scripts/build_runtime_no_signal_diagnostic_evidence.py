#!/usr/bin/env python3
"""Build read-only diagnostic evidence for no-signal runtime watch windows.

This script consumes runtime strategy-signal watch evidence as source evidence.
It does not call APIs, resolve runtimes, write PG rows, create
shadow candidates, create ExecutionIntents, place orders, or mutate runtime
state.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def build_no_signal_diagnostic_evidence(watch_evidence: dict[str, Any]) -> dict[str, Any]:
    checks = _as_dict(watch_evidence.get("checks"))
    active = _as_dict(watch_evidence.get("active_runtime_observation"))
    safety = _as_dict(watch_evidence.get("safety_invariants"))
    runtime_signals = _dict_rows(watch_evidence.get("runtime_signals"))
    strategy_no_action = _dict_rows(watch_evidence.get("strategy_group_no_action_signals"))
    strategy_would_enter = _dict_rows(
        watch_evidence.get("strategy_group_would_enter_signals")
    )
    runtime_ready = _dict_rows(watch_evidence.get("runtime_ready_signals"))

    forbidden_effects = _forbidden_effects(watch_evidence)
    runtime_ready_count = int(checks.get("runtime_ready_signal_count") or 0)
    strategy_would_enter_count = int(
        checks.get("strategy_group_would_enter_signal_count") or 0
    )
    no_signal = (
        runtime_ready_count == 0
        and strategy_would_enter_count == 0
        and watch_evidence.get("status")
        in {"watching_no_signal", "watch_window_complete_no_signal"}
    )

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        next_step = "resolve_no_signal_diagnostic_forbidden_effects"
    elif runtime_ready or runtime_ready_count:
        status = "runtime_signal_ready_not_no_signal"
        next_step = "review_runtime_ready_signal_prepare_path"
    elif strategy_would_enter or strategy_would_enter_count:
        status = "strategy_group_signal_available_not_no_signal"
        next_step = "review_strategy_group_would_enter_without_execution"
    elif no_signal and watch_evidence.get("status") == "watch_window_complete_no_signal":
        status = "no_signal_window_complete"
        next_step = "review_strategy_coverage_before_starting_new_window"
    elif no_signal:
        status = "no_signal_observation_running"
        next_step = "continue_active_runtime_observation"
    else:
        status = "watch_evidence_needs_review"
        next_step = "review_watch_evidence_status"

    runtime_reason_counts = _reason_counts(runtime_signals)
    strategy_reason_counts = _reason_counts(strategy_no_action)
    active_families = _unique_text(row.get("strategy_family_id") for row in runtime_signals)
    preview_families = _unique_text(
        row.get("strategy_group_id") or row.get("strategy_family_id")
        for row in strategy_no_action + strategy_would_enter
    )

    return {
        "scope": "runtime_no_signal_diagnostic_evidence",
        "status": status,
        "source_watch_status": watch_evidence.get("status"),
        "observation": {
            "active_runtime_count": active.get("active_runtime_count"),
            "monitored_runtime_count": active.get("monitored_runtime_count"),
            "selected_runtime_instance_ids": active.get(
                "selected_runtime_instance_ids"
            )
            or [],
            "latest_iteration": active.get("latest_iteration"),
            "iterations_completed": active.get("iterations_completed"),
            "iterations_remaining": active.get("iterations_remaining"),
            "iterations_requested": active.get("iterations_requested"),
            "stop_reason": active.get("stop_reason"),
            "artifact_stale": active.get("artifact_stale"),
        },
        "signal_counts": {
            "runtime_ready_signal_count": runtime_ready_count,
            "strategy_group_would_enter_signal_count": strategy_would_enter_count,
            "strategy_group_no_action_signal_count": int(
                checks.get("strategy_group_no_action_signal_count") or 0
            ),
        },
        "coverage": {
            "active_runtime_strategy_families": active_families,
            "strategy_group_preview_families": preview_families,
            "active_runtime_symbols": _unique_text(row.get("symbol") for row in runtime_signals),
            "strategy_group_preview_symbols": _unique_text(
                row.get("symbol") for row in strategy_no_action + strategy_would_enter
            ),
            "active_runtime_count_less_than_preview_family_count": (
                len(active_families) < len(preview_families)
            ),
        },
        "no_action_diagnostics": {
            "runtime_reason_counts": runtime_reason_counts,
            "strategy_group_reason_counts": strategy_reason_counts,
            "dominant_runtime_reasons": _top_reason_counts(runtime_reason_counts),
            "dominant_strategy_group_reasons": _top_reason_counts(strategy_reason_counts),
        },
        "review_plan": {
            "not_execution_authority": True,
            "next_step": next_step,
            "allowed_review_checkpoints": _allowed_review_checkpoints(status),
        },
        "owner_gate": {
            "diagnostic_only": True,
            "does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle submit",
                "executable ExecutionIntent",
                "withdrawal or transfer",
            ],
        },
        "right_tail_objective_context": {
            "no_signal_is_not_failure": True,
            "small_bounded_losses_allowed_when_runtime_ready": True,
            "forcing_entry_without_signal_forbidden": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "safety_invariants": {
            "diagnostic_evidence_only": True,
            "api_called": False,
            "database_connected": False,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": forbidden_effects,
            "source_watch_safety_flags": safety,
        },
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for reason in row.get("reason_codes") or []:
            text = str(reason or "").strip()
            if text:
                counter[text] += 1
    return dict(sorted(counter.items()))


def _top_reason_counts(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"reason_code": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            :5
        ]
    ]


def _unique_text(values: Any) -> list[str]:
    return sorted({str(value) for value in values if value})


def _forbidden_effects(watch_evidence: dict[str, Any]) -> list[str]:
    effects = list(_as_dict(watch_evidence.get("checks")).get("forbidden_effects") or [])
    safety = _as_dict(watch_evidence.get("safety_invariants"))
    for key in (
        "shadow_candidate_created",
        "execution_intent_created",
        "order_created",
        "order_lifecycle_called",
        "exchange_write_called",
        "attempt_counter_mutated",
        "runtime_budget_mutated",
        "withdrawal_or_transfer_created",
    ):
        if safety.get(key) is True:
            effects.append(f"safety.{key}")
    effects.extend(str(item) for item in safety.get("forbidden_effects") or [])
    return sorted(set(str(item) for item in effects if item))


def _allowed_review_checkpoints(status: str) -> list[str]:
    if status == "no_signal_observation_running":
        return ["continue_active_runtime_observation"]
    if status == "no_signal_window_complete":
        return [
            "review_no_action_reason_codes",
            "review_strategy_runtime_coverage",
            "start_new_observation_window_if_still_desired",
        ]
    if status == "runtime_signal_ready_not_no_signal":
        return ["review_runtime_ready_signal_prepare_path"]
    if status == "strategy_group_signal_available_not_no_signal":
        return ["review_strategy_group_signal_without_execution"]
    return ["review_no_signal_diagnostic_evidence"]
