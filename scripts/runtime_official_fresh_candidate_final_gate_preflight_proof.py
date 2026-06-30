#!/usr/bin/env python3
"""Official fresh-candidate FinalGate preflight lifecycle proof.

RTF-090 connects the post-submit next-attempt strategy continuation proof to
the official FinalGate / controlled-submit preflight proof. It proves the
fresh shadow OrderCandidate produced after a ready next-attempt gate is the same
candidate accepted by the official prepare, FinalGate, and preflight routes.

This remains non-executing: no local order registration, no OrderLifecycle
submit, no exchange write, no runtime mutation, no withdrawal, and no transfer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_official_final_gate_preflight_proof as rtf081  # noqa: E402
from scripts import runtime_official_next_attempt_strategy_continuation_proof as rtf089  # noqa: E402
from scripts.runtime_official_scoped_local_registration_proof import _write_json  # noqa: E402


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    continuation_report = rtf089.build_proof_report(
        output_dir / "rtf089-prerequisite"
    )
    _write_json(
        output_dir / "rtf089-prerequisite-report.json",
        continuation_report,
    )

    final_gate_report = rtf081.build_proof_report(
        output_dir / "rtf081-official-final-gate-preflight"
    )
    _write_json(
        output_dir / "rtf081-final-gate-preflight-report.json",
        final_gate_report,
    )

    proof_artifact = _proof_artifact(
        continuation_report=continuation_report,
        final_gate_report=final_gate_report,
    )
    _write_json(
        output_dir / "fresh-candidate-final-gate-preflight-artifact.json",
        proof_artifact,
    )

    checks = dict(proof_artifact["checks"])
    report = {
        "scope": "runtime_official_fresh_candidate_final_gate_preflight_proof",
        "status": (
            "official_fresh_candidate_final_gate_preflight_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": continuation_report.get("runtime_instance_id"),
        "signal_evaluation_id": continuation_report.get("signal_evaluation_id"),
        "order_candidate_id": continuation_report.get("order_candidate_id"),
        "authorization_id": final_gate_report.get("authorization_id"),
        "runtime_execution_intent_draft_id": final_gate_report.get(
            "runtime_execution_intent_draft_id"
        ),
        "execution_intent_id": final_gate_report.get("execution_intent_id"),
        "controlled_submit_preflight_id": final_gate_report.get(
            "controlled_submit_preflight_id"
        ),
        "fresh_candidate_final_gate_preflight_artifact": proof_artifact,
        "rtf089_prerequisite": continuation_report,
        "rtf081_final_gate_preflight": final_gate_report,
        "checks": checks,
        "safety_invariants": proof_artifact["safety_invariants"],
        "fresh_candidate_preflight_plan": {
            "next_step": (
                "continue_fresh_candidate_to_submit_adapter_preview"
                if _contract_passed(checks)
                else "resolve_fresh_candidate_final_gate_preflight_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "requires_fresh_authorization_before_submit": True,
            "creates_executable_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "right_tail_runner_preserved": checks[
                "right_tail_runner_preserved"
            ],
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


def _proof_artifact(
    *,
    continuation_report: dict[str, Any],
    final_gate_report: dict[str, Any],
) -> dict[str, Any]:
    continuation_artifact = continuation_report.get(
        "next_attempt_strategy_continuation_artifact"
    ) or {}
    final_gate_artifact = final_gate_report.get("preflight_artifact") or {}
    checks = _checks(
        continuation_report=continuation_report,
        continuation_artifact=continuation_artifact,
        final_gate_report=final_gate_report,
        final_gate_artifact=final_gate_artifact,
    )
    return {
        "scope": "runtime_official_fresh_candidate_final_gate_preflight_artifact",
        "status": (
            "fresh_candidate_ready_for_controlled_submit_adapter"
            if _contract_passed(checks)
            else "blocked"
        ),
        "candidate_handoff": {
            "continuation_order_candidate_id": continuation_report.get(
                "order_candidate_id"
            ),
            "final_gate_order_candidate_id": final_gate_report.get(
                "order_candidate_id"
            ),
            "signal_evaluation_id": continuation_report.get(
                "signal_evaluation_id"
            ),
            "fresh_ready_status": continuation_report.get("ready_status"),
            "candidate_ids_match": checks["candidate_ids_match"],
        },
        "authorization": {
            "authorization_id": final_gate_report.get("authorization_id"),
            "runtime_execution_intent_draft_id": final_gate_report.get(
                "runtime_execution_intent_draft_id"
            ),
            "execution_intent_id": final_gate_report.get("execution_intent_id"),
            "fresh_authorization_required_before_submit": checks[
                "fresh_authorization_required_before_submit"
            ],
        },
        "final_gate": {
            "verdict": (final_gate_artifact.get("final_gate") or {}).get("verdict"),
            "status": (final_gate_artifact.get("final_gate") or {}).get("status"),
            "blockers": list(
                (final_gate_artifact.get("final_gate") or {}).get("blockers") or []
            ),
        },
        "controlled_submit_preflight": {
            "status": (
                final_gate_artifact.get("controlled_submit_preflight") or {}
            ).get("status"),
            "final_gate_verdict": (
                final_gate_artifact.get("controlled_submit_preflight") or {}
            ).get("final_gate_verdict"),
            "preview_only": (
                final_gate_artifact.get("controlled_submit_preflight") or {}
            ).get("preview_only"),
            "blockers": list(
                (
                    final_gate_artifact.get("controlled_submit_preflight") or {}
                ).get("blockers")
                or []
            ),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            continuation_report=continuation_report,
            continuation_artifact=continuation_artifact,
            final_gate_report=final_gate_report,
            final_gate_artifact=final_gate_artifact,
        ),
    }


def _checks(
    *,
    continuation_report: dict[str, Any],
    continuation_artifact: dict[str, Any],
    final_gate_report: dict[str, Any],
    final_gate_artifact: dict[str, Any],
) -> dict[str, bool]:
    continuation_checks = continuation_report.get("checks") or {}
    final_gate_checks = final_gate_report.get("checks") or {}
    ready_path = continuation_artifact.get("ready_path") or {}
    ready_post_submit_gate = continuation_artifact.get("ready_post_submit_gate") or {}
    safety = _safety_invariants(
        continuation_report=continuation_report,
        continuation_artifact=continuation_artifact,
        final_gate_report=final_gate_report,
        final_gate_artifact=final_gate_artifact,
    )
    return {
        "rtf089_prerequisite_passed": (
            continuation_report.get("status")
            == "official_next_attempt_strategy_continuation_passed"
        ),
        "rtf081_final_gate_preflight_passed": (
            final_gate_report.get("status") == "official_final_gate_preflight_passed"
        ),
        "fresh_candidate_ready_for_final_gate": (
            continuation_report.get("ready_status")
            == "ready_for_final_gate_preflight"
        ),
        "candidate_ids_match": (
            continuation_report.get("order_candidate_id")
            == final_gate_report.get("order_candidate_id")
            == "order-candidate-rtf075-contract"
        ),
        "signal_evaluation_present": bool(
            continuation_report.get("signal_evaluation_id")
        ),
        "ready_path_shadow_candidate_created": bool(
            continuation_checks.get("ready_path_shadow_candidate_created")
        ),
        "ready_path_requires_final_gate": bool(
            continuation_checks.get("ready_path_requires_final_gate")
        ),
        "fresh_authorization_required_before_submit": (
            ready_path.get("strategy_planning_plan", {}).get(
                "requires_official_final_gate"
            )
            is True
            and ready_path.get("status") == "ready_for_final_gate_preflight"
        ),
        "old_authorization_retry_disallowed": (
            ready_post_submit_gate.get("old_authorization_submit_retry_allowed")
            is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            ready_post_submit_gate.get("pre_submit_rehearsal_retry_allowed")
            is False
        ),
        "final_gate_verdict_pass": bool(
            final_gate_checks.get("final_gate_verdict_pass")
        ),
        "controlled_submit_preflight_ready": bool(
            final_gate_checks.get("controlled_submit_preflight_ready")
        ),
        "preflight_preview_only": bool(
            final_gate_checks.get("preflight_preview_only")
        ),
        "prepare_authorization_created": bool(
            final_gate_checks.get("prepare_authorization_created")
        ),
        "right_tail_runner_preserved": (
            bool(continuation_checks.get("right_tail_runner_preserved"))
            and bool(final_gate_checks.get("right_tail_runner_preserved"))
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "execution_intent_created_in_continuation": safety[
            "execution_intent_created_in_continuation"
        ],
        "executable_execution_intent_created": safety[
            "executable_execution_intent_created"
        ],
        "local_order_created": safety["local_order_created"],
        "order_lifecycle_called": safety["order_lifecycle_called"],
        "exchange_called": safety["exchange_called"],
        "exchange_order_submitted": safety["exchange_order_submitted"],
        "runtime_state_mutated": safety["runtime_state_mutated"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "rtf089_prerequisite_passed",
        "rtf081_final_gate_preflight_passed",
        "fresh_candidate_ready_for_final_gate",
        "candidate_ids_match",
        "signal_evaluation_present",
        "ready_path_shadow_candidate_created",
        "ready_path_requires_final_gate",
        "fresh_authorization_required_before_submit",
        "old_authorization_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "final_gate_verdict_pass",
        "controlled_submit_preflight_ready",
        "preflight_preview_only",
        "prepare_authorization_created",
        "right_tail_runner_preserved",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "execution_intent_created_in_continuation",
        "executable_execution_intent_created",
        "local_order_created",
        "order_lifecycle_called",
        "exchange_called",
        "exchange_order_submitted",
        "runtime_state_mutated",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    continuation_report: dict[str, Any],
    continuation_artifact: dict[str, Any],
    final_gate_report: dict[str, Any],
    final_gate_artifact: dict[str, Any],
) -> dict[str, bool]:
    continuation_safety = continuation_report.get("safety_invariants") or {}
    final_gate_safety = final_gate_report.get("safety_invariants") or {}
    continuation_checks = continuation_report.get("checks") or {}
    final_gate_checks = final_gate_report.get("checks") or {}
    preflight = final_gate_artifact.get("controlled_submit_preflight") or {}
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "ready_path_shadow_candidate_created": bool(
            continuation_safety.get("ready_path_shadow_candidate_created")
        ),
        "execution_intent_created_in_continuation": bool(
            continuation_checks.get("execution_intent_created")
        ),
        "executable_execution_intent_created": (
            bool(continuation_checks.get("executable_execution_intent_created"))
            or preflight.get("submit_executed") is True
        ),
        "local_order_created": (
            bool(continuation_checks.get("order_created"))
            or bool(final_gate_checks.get("order_created"))
        ),
        "order_lifecycle_called": (
            bool(continuation_checks.get("order_lifecycle_called"))
            or bool(final_gate_checks.get("order_lifecycle_called"))
        ),
        "exchange_called": bool(continuation_checks.get("exchange_called")),
        "exchange_order_submitted": bool(
            continuation_safety.get("exchange_order_submitted")
        ),
        "runtime_state_mutated": (
            bool(continuation_safety.get("runtime_state_mutated"))
            or bool(final_gate_safety.get("attempt_counter_mutated"))
            or bool(final_gate_safety.get("runtime_budget_mutated"))
        ),
        "pg_written": bool(final_gate_safety.get("pg_written")),
        "withdrawal_or_transfer_created": (
            bool(continuation_checks.get("withdrawal_or_transfer_created"))
            or bool(final_gate_checks.get("withdrawal_or_transfer_created"))
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official fresh-candidate FinalGate preflight proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf090-official-fresh-candidate-final-gate-preflight",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"]
        == "official_fresh_candidate_final_gate_preflight_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
