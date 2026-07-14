#!/usr/bin/env python3
"""Build read-only operator evidence for active runtime observation.

The evidence joins:

1. An active runtime observation status artifact.
2. Runtime + strategy signal watch evidence.
3. No-signal diagnostic evidence when applicable.

It does not write PG rows, resolve runtimes, create non-ticket trade records,
create ExecutionIntents, place orders, call OrderLifecycle, or mutate runtime
state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_runtime_no_signal_diagnostic_evidence import (  # noqa: E402
    build_no_signal_diagnostic_evidence,
)
from scripts.build_runtime_strategy_signal_watch_evidence import (  # noqa: E402
    build_watch_evidence,
)


def build_operator_evidence(
    *,
    active_status_artifact: dict[str, Any],
    strategy_preview_artifact: dict[str, Any],
) -> dict[str, Any]:
    watch_evidence = build_watch_evidence(
        active_status_artifact=active_status_artifact,
        strategy_preview_artifact=strategy_preview_artifact,
    )
    diagnostic_evidence = build_no_signal_diagnostic_evidence(watch_evidence)
    forbidden_effects = _forbidden_effects(
        ("watch_evidence", watch_evidence),
        ("diagnostic_evidence", diagnostic_evidence),
    )
    watch_status = str(watch_evidence.get("status") or "unknown")
    diagnostic_status = str(diagnostic_evidence.get("status") or "unknown")

    status = "blocked_forbidden_effect"
    next_step = "resolve_operator_evidence_forbidden_effects"
    if not forbidden_effects:
        if watch_status == "runtime_signal_identity_gap":
            status = "runtime_signal_identity_gap"
            next_step = "repair_pg_live_signal_identity_handoff"
        elif watch_status in {
            "runtime_signal_ready",
            "runtime_signal_ready_for_action_time_ticket",
        }:
            status = "runtime_signal_attention"
            next_step = "materialize_pg_action_time_ticket"
        elif watch_status == "strategy_group_signal_review_available":
            status = "strategy_group_signal_review_available"
            next_step = "review_strategy_group_would_enter_without_execution"
        elif diagnostic_status == "no_signal_window_complete":
            status = "no_signal_window_complete"
            next_step = "review_no_signal_diagnostic_before_new_window"
        elif diagnostic_status == "no_signal_observation_running":
            status = "observation_running_no_signal"
            next_step = "continue_active_runtime_observation"
        else:
            status = "operator_review"
            next_step = "review_observation_operator_evidence"

    return {
        "scope": "runtime_observation_operator_evidence",
        "status": status,
        "watch_status": watch_status,
        "diagnostic_status": diagnostic_status,
        "active_runtime_observation": watch_evidence.get("active_runtime_observation"),
        "signal_counts": (diagnostic_evidence.get("signal_counts") or {}),
        "coverage": (diagnostic_evidence.get("coverage") or {}),
        "no_action_diagnostics": (
            diagnostic_evidence.get("no_action_diagnostics") or {}
        ),
        "runtime_action_time_context": (
            watch_evidence.get("runtime_action_time_context") or {}
        ),
        "operator_review_plan": {
            "not_execution_authority": True,
            "next_step": next_step,
            "allowed_review_checkpoints": _allowed_review_checkpoints(
                status=status,
                watch_evidence=watch_evidence,
                diagnostic_evidence=diagnostic_evidence,
            ),
        },
        "owner_gate": {
            "operator_review_only": True,
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
        "watch_evidence": watch_evidence,
        "no_signal_diagnostic_evidence": diagnostic_evidence,
        "safety_invariants": {
            "operator_evidence_only": True,
            "status_artifact_read_only": True,
            "strategy_preview_only": True,
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
            "forbidden_effects": forbidden_effects,
        },
    }


def _allowed_review_checkpoints(
    *,
    status: str,
    watch_evidence: dict[str, Any],
    diagnostic_evidence: dict[str, Any],
) -> list[str]:
    if status == "runtime_signal_identity_gap":
        return []
    if status == "runtime_signal_attention":
        watch_plan = watch_evidence.get("watch_evidence_plan")
        return list(
            (watch_plan or {}).get("allowed_review_checkpoints")
            or ["materialize_pg_action_time_ticket"]
        )
    if status == "strategy_group_signal_review_available":
        return ["review_strategy_group_would_enter_without_execution"]
    if status in {"observation_running_no_signal", "no_signal_window_complete"}:
        return list(
            (diagnostic_evidence.get("review_plan") or {}).get("allowed_review_checkpoints")
            or ["continue_active_runtime_observation"]
        )
    return ["review_observation_operator_evidence"]


def _forbidden_effects(*sources: tuple[str, dict[str, Any]]) -> list[str]:
    effects: list[str] = []
    for source_name, artifact in sources:
        checks = (
            artifact.get("checks") if isinstance(artifact.get("checks"), dict) else {}
        )
        effects.extend(
            f"{source_name}.checks.{item}"
            for item in checks.get("forbidden_effects") or []
        )
        safety = (
            artifact.get("safety_invariants")
            if isinstance(artifact.get("safety_invariants"), dict)
            else {}
        )
        for item in safety.get("forbidden_effects") or []:
            effects.append(f"{source_name}.{item}")
        for item in safety.get("source_forbidden_effects") or []:
            effects.append(f"{source_name}.source.{item}")
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
                effects.append(f"{source_name}.{key}")
    return sorted(set(str(item) for item in effects if item))
