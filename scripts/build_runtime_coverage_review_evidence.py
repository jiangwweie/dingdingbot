#!/usr/bin/env python3
"""Build read-only ACTIVE runtime coverage review evidence.

The evidence consumes an existing runtime observation operator evidence artifact.
It is a posture review aid for no-signal windows: it compares ACTIVE runtime
coverage with the broader strategy preview shelf and summarizes no-action
reasons.

It does not call APIs, connect to PG, start runtimes, create candidates, create
ExecutionIntents, call OrderLifecycle, place exchange orders, or mutate runtime
state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_coverage_review_evidence(operator_evidence: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(operator_evidence.get("safety_invariants"))
    coverage = _as_dict(operator_evidence.get("coverage"))
    active = _as_dict(operator_evidence.get("active_runtime_observation"))
    counts = _as_dict(operator_evidence.get("signal_counts"))
    diagnostics = _as_dict(operator_evidence.get("no_action_diagnostics"))
    forbidden_effects = _forbidden_effects(operator_evidence)

    active_families = _text_list(coverage.get("active_runtime_strategy_families"))
    preview_families = _text_list(coverage.get("strategy_group_preview_families"))
    active_symbols = _text_list(coverage.get("active_runtime_symbols"))
    preview_symbols = _text_list(coverage.get("strategy_group_preview_symbols"))
    uncovered_families = sorted(set(preview_families) - set(active_families))
    uncovered_symbols = sorted(set(preview_symbols) - set(active_symbols))
    ready_count = _int(counts.get("runtime_ready_signal_count"))
    would_enter_count = _int(counts.get("strategy_group_would_enter_signal_count"))

    window_running = active.get("stop_reason") == "running"
    window_complete = active.get("stop_reason") not in {None, "running"}
    narrow_coverage = bool(
        coverage.get("active_runtime_count_less_than_preview_family_count")
        or uncovered_families
    )

    if forbidden_effects:
        status = "blocked_forbidden_effect"
        next_step = "stop_and_review_forbidden_coverage_source_effects"
    elif ready_count > 0:
        status = "runtime_signal_ready_not_coverage_review"
        next_step = "review_runtime_ready_signal_prepare_path"
    elif would_enter_count > 0:
        status = "strategy_group_signal_available_not_runtime_active"
        next_step = "review_strategy_group_signal_without_execution"
    elif window_complete and narrow_coverage:
        status = "coverage_review_needed_after_no_signal_window"
        next_step = "review_active_runtime_coverage_before_next_window"
    elif window_running and narrow_coverage:
        status = "coverage_review_observation_running"
        next_step = "continue_observation_then_review_coverage_if_no_signal_persists"
    elif window_complete:
        status = "coverage_review_window_complete_no_gap"
        next_step = "review_no_signal_reasons_before_new_window"
    else:
        status = "coverage_review_no_gap_running"
        next_step = "continue_active_runtime_observation"

    active_family_count = len(active_families)
    preview_family_count = len(preview_families)
    return {
        "scope": "runtime_coverage_review_evidence",
        "status": status,
        "source_operator_status": operator_evidence.get("status"),
        "summary": {
            "active_runtime_count": active.get("active_runtime_count"),
            "latest_iteration": active.get("latest_iteration"),
            "iterations_completed": active.get("iterations_completed"),
            "iterations_remaining": active.get("iterations_remaining"),
            "stop_reason": active.get("stop_reason"),
            "runtime_ready_signal_count": ready_count,
            "strategy_group_would_enter_signal_count": would_enter_count,
            "strategy_group_no_action_signal_count": _int(
                counts.get("strategy_group_no_action_signal_count")
            ),
            "active_family_count": active_family_count,
            "preview_family_count": preview_family_count,
            "coverage_ratio": (
                str(active_family_count) + "/" + str(preview_family_count)
                if preview_family_count
                else "0/0"
            ),
            "narrow_coverage": narrow_coverage,
            "next_step": next_step,
        },
        "coverage": {
            "active_runtime_strategy_families": active_families,
            "strategy_group_preview_families": preview_families,
            "uncovered_preview_families": uncovered_families,
            "active_runtime_symbols": active_symbols,
            "strategy_group_preview_symbols": preview_symbols,
            "uncovered_preview_symbols": uncovered_symbols,
        },
        "no_action_review": {
            "dominant_runtime_reasons": list(
                diagnostics.get("dominant_runtime_reasons") or []
            ),
            "dominant_strategy_group_reasons": list(
                diagnostics.get("dominant_strategy_group_reasons") or []
            ),
            "runtime_reason_counts": _as_dict(
                diagnostics.get("runtime_reason_counts")
            ),
            "strategy_group_reason_counts": _as_dict(
                diagnostics.get("strategy_group_reason_counts")
            ),
        },
        "review_plan": {
            "not_execution_authority": True,
            "next_step": next_step,
            "allowed_review_checkpoints": _allowed_review_checkpoints(status),
        },
        "owner_gate": {
            "coverage_review_only": True,
            "does_not_authorize": [
                "new runtime activation",
                "strategy parameter changes",
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle submit",
                "executable ExecutionIntent",
                "withdrawal or transfer",
            ],
        },
        "right_tail_objective_context": {
            "no_signal_is_not_failure": True,
            "coverage_review_can_expand_future_opportunity_search": True,
            "small_bounded_losses_allowed_when_runtime_ready": True,
            "forcing_entry_without_signal_forbidden": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "safety_invariants": {
            "coverage_evidence_only": True,
            "source_operator_evidence_read_only": (
                safety.get("operator_evidence_only") is True
            ),
            "api_called": False,
            "database_connected": False,
            "pg_observation_written": False,
            "runtime_started": False,
            "runtime_resolver_called": False,
            "strategy_parameters_changed": False,
            "shadow_candidate_created": False,
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


def build_coverage_review_evidence_from_path(operator_evidence_json: str | Path) -> dict[str, Any]:
    return build_coverage_review_evidence(
        _load_json_object(Path(operator_evidence_json).expanduser())
    )


def _allowed_review_checkpoints(status: str) -> list[str]:
    if status == "blocked_forbidden_effect":
        return []
    if status == "runtime_signal_ready_not_coverage_review":
        return ["review_runtime_ready_signal_prepare_path"]
    if status == "strategy_group_signal_available_not_runtime_active":
        return ["review_strategy_group_signal_without_execution"]
    if status == "coverage_review_needed_after_no_signal_window":
        return [
            "review_active_runtime_coverage",
            "review_no_action_reason_codes",
            "decide_future_runtime_profile_changes_with_owner",
        ]
    if status == "coverage_review_observation_running":
        return [
            "continue_active_runtime_observation",
            "review_coverage_if_no_signal_persists",
        ]
    return ["continue_active_runtime_observation"]


def _forbidden_effects(evidence: dict[str, Any]) -> list[str]:
    safety = _as_dict(evidence.get("safety_invariants"))
    effects = [str(item) for item in safety.get("forbidden_effects") or [] if item]
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
            effects.append(key)
    plan = _as_dict(evidence.get("operator_review_plan"))
    for key in (
        "creates_shadow_candidate",
        "creates_execution_intent",
        "places_order",
        "calls_order_lifecycle",
        "withdrawal_or_transfer_requested",
    ):
        if plan.get(key) is True:
            effects.append(f"operator_review_plan.{key}")
    return sorted(set(effects))


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item or "").strip()})


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-evidence-json", required=True)
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    artifact = build_coverage_review_evidence_from_path(args.operator_evidence_json)
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
