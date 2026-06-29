#!/usr/bin/env python3
"""Official fresh-candidate runtime cycle handoff proof.

RTF-091 combines the fresh-candidate FinalGate preflight proof with the
controlled gateway action / post-submit finalize proof.  It proves the runtime
chain can move from a fresh strategy-driven shadow candidate into official
preflight, through the controlled in-memory submit path, then back into
post-submit finalize and the next-attempt gate.

This is a local official-route proof only: gateway execution is in-memory, not
live exchange; no PG write, withdrawal, transfer, or live exchange order occurs.
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

from scripts import runtime_official_fresh_candidate_final_gate_preflight_proof as rtf090  # noqa: E402
from scripts import runtime_official_post_submit_finalize_proof as rtf088  # noqa: E402
from scripts.runtime_official_scoped_local_registration_proof import _write_json  # noqa: E402


def build_proof_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    fresh_preflight_report = rtf090.build_proof_report(
        output_dir / "rtf090-prerequisite"
    )
    _write_json(
        output_dir / "rtf090-prerequisite-report.json",
        fresh_preflight_report,
    )

    post_submit_report = rtf088.build_proof_report(
        output_dir / "rtf088-post-submit-finalize"
    )
    _write_json(
        output_dir / "rtf088-post-submit-finalize-report.json",
        post_submit_report,
    )

    proof_artifact = _proof_artifact(
        fresh_preflight_report=fresh_preflight_report,
        post_submit_report=post_submit_report,
    )
    _write_json(
        output_dir / "fresh-candidate-runtime-cycle-artifact.json",
        proof_artifact,
    )

    checks = dict(proof_artifact["checks"])
    report = {
        "scope": "runtime_official_fresh_candidate_runtime_cycle_handoff_proof",
        "status": (
            "official_fresh_candidate_runtime_cycle_handoff_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": fresh_preflight_report.get("runtime_instance_id"),
        "signal_evaluation_id": fresh_preflight_report.get("signal_evaluation_id"),
        "order_candidate_id": fresh_preflight_report.get("order_candidate_id"),
        "preflight_authorization_id": fresh_preflight_report.get(
            "authorization_id"
        ),
        "post_submit_authorization_id": post_submit_report.get("authorization_id"),
        "exchange_submit_execution_result_id": post_submit_report.get(
            "exchange_submit_execution_result_id"
        ),
        "submit_outcome_review_id": post_submit_report.get(
            "submit_outcome_review_id"
        ),
        "post_submit_budget_settlement_id": post_submit_report.get(
            "post_submit_budget_settlement_id"
        ),
        "fresh_candidate_runtime_cycle_artifact": proof_artifact,
        "rtf090_prerequisite": fresh_preflight_report,
        "rtf088_post_submit_finalize": post_submit_report,
        "checks": checks,
        "safety_invariants": proof_artifact["safety_invariants"],
        "fresh_candidate_runtime_cycle_handoff_plan": {
            "next_step": (
                "prove_repeatable_runtime_cycle_with_flat_next_attempt_gate"
                if _contract_passed(checks)
                else "resolve_fresh_candidate_runtime_cycle_handoff_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "controlled_execution_mode": "in_memory_simulation",
            "calls_live_exchange": False,
            "next_attempt_requires_fresh_signal": True,
            "next_attempt_requires_fresh_authorization": True,
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
    fresh_preflight_report: dict[str, Any],
    post_submit_report: dict[str, Any],
) -> dict[str, Any]:
    fresh_preflight_artifact = fresh_preflight_report.get(
        "fresh_candidate_final_gate_preflight_artifact"
    ) or {}
    post_submit_artifact = (
        post_submit_report.get("post_submit_finalize_proof_artifact") or {}
    )
    checks = _checks(
        fresh_preflight_report=fresh_preflight_report,
        fresh_preflight_artifact=fresh_preflight_artifact,
        post_submit_report=post_submit_report,
        post_submit_artifact=post_submit_artifact,
    )
    return {
        "scope": "runtime_official_fresh_candidate_runtime_cycle_artifact",
        "status": (
            "fresh_candidate_cycle_handoff_completed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "candidate_handoff": {
            "fresh_preflight_candidate_id": fresh_preflight_report.get(
                "order_candidate_id"
            ),
            "post_submit_candidate_id": post_submit_report.get("order_candidate_id"),
            "candidate_ids_match": checks["candidate_ids_match"],
            "signal_evaluation_id": fresh_preflight_report.get(
                "signal_evaluation_id"
            ),
        },
        "pre_submit_side": {
            "fresh_preflight_status": fresh_preflight_artifact.get("status"),
            "final_gate_verdict": (
                fresh_preflight_artifact.get("final_gate") or {}
            ).get("verdict"),
            "controlled_submit_preflight_status": (
                fresh_preflight_artifact.get("controlled_submit_preflight") or {}
            ).get("status"),
            "fresh_authorization_required_before_submit": (
                fresh_preflight_artifact.get("authorization") or {}
            ).get("fresh_authorization_required_before_submit"),
        },
        "controlled_action_side": {
            "exchange_submit_execution_result_id": post_submit_report.get(
                "exchange_submit_execution_result_id"
            ),
            "exchange_submit_execution_result_status": (
                (post_submit_artifact.get("statuses") or {}).get(
                    "exchange_submit_execution_result"
                )
            ),
            "controlled_gateway_action_status": (
                post_submit_artifact.get("statuses") or {}
            ).get("exchange_submit_adapter_result"),
            "execution_mode": "in_memory_simulation",
        },
        "post_submit_side": {
            "finalize_status": (
                post_submit_artifact.get("post_submit_finalize") or {}
            ).get("status"),
            "next_attempt_gate_status": (
                post_submit_artifact.get("next_attempt_gate") or {}
            ).get("status"),
            "next_attempt_gate_blockers": list(
                (post_submit_artifact.get("next_attempt_gate") or {}).get(
                    "blockers"
                )
                or []
            ),
            "old_authorization_submit_retry_allowed": (
                post_submit_artifact.get("post_submit_finalize") or {}
            ).get("old_authorization_submit_retry_allowed"),
            "pre_submit_rehearsal_retry_allowed": (
                post_submit_artifact.get("post_submit_finalize") or {}
            ).get("pre_submit_rehearsal_retry_allowed"),
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            fresh_preflight_report=fresh_preflight_report,
            fresh_preflight_artifact=fresh_preflight_artifact,
            post_submit_report=post_submit_report,
            post_submit_artifact=post_submit_artifact,
        ),
    }


def _checks(
    *,
    fresh_preflight_report: dict[str, Any],
    fresh_preflight_artifact: dict[str, Any],
    post_submit_report: dict[str, Any],
    post_submit_artifact: dict[str, Any],
) -> dict[str, bool]:
    fresh_checks = fresh_preflight_report.get("checks") or {}
    post_checks = post_submit_report.get("checks") or {}
    post_finalize = post_submit_artifact.get("post_submit_finalize") or {}
    next_gate = post_submit_artifact.get("next_attempt_gate") or {}
    statuses = post_submit_artifact.get("statuses") or {}
    review = post_submit_artifact.get("review") or {}
    settlement = post_submit_artifact.get("settlement") or {}
    safety = _safety_invariants(
        fresh_preflight_report=fresh_preflight_report,
        fresh_preflight_artifact=fresh_preflight_artifact,
        post_submit_report=post_submit_report,
        post_submit_artifact=post_submit_artifact,
    )
    return {
        "rtf090_prerequisite_passed": (
            fresh_preflight_report.get("status")
            == "official_fresh_candidate_final_gate_preflight_passed"
        ),
        "rtf088_post_submit_finalize_passed": (
            post_submit_report.get("status")
            == "official_post_submit_finalize_passed"
        ),
        "candidate_ids_match": (
            fresh_preflight_report.get("order_candidate_id")
            == post_submit_report.get("order_candidate_id")
            == "order-candidate-rtf075-contract"
        ),
        "runtime_ids_match": (
            fresh_preflight_report.get("runtime_instance_id")
            == post_submit_report.get("runtime_instance_id")
            == "runtime-rtf075-cpm-long"
        ),
        "fresh_preflight_ready": (
            fresh_preflight_artifact.get("status")
            == "fresh_candidate_ready_for_controlled_submit_adapter"
        ),
        "final_gate_passed": bool(fresh_checks.get("final_gate_verdict_pass")),
        "controlled_submit_preflight_ready": bool(
            fresh_checks.get("controlled_submit_preflight_ready")
        ),
        "fresh_authorization_required_before_submit": bool(
            fresh_checks.get("fresh_authorization_required_before_submit")
        ),
        "controlled_gateway_action_passed": bool(
            post_checks.get("controlled_gateway_action_passed")
        ),
        "exchange_execution_result_submitted": (
            statuses.get("exchange_submit_execution_result")
            == "exchange_submit_orders_submitted"
        ),
        "durable_execution_result_reused": bool(
            post_checks.get("durable_execution_result_reused")
        ),
        "post_submit_finalize_completed": (
            post_finalize.get("status") == "finalized_next_attempt_blocked"
        ),
        "next_attempt_gate_blocked_by_active_position": (
            next_gate.get("status") == "blocked"
            and "runtime_active_position_slot_in_use"
            in list(next_gate.get("blockers") or [])
        ),
        "next_attempt_requires_fresh_signal": (
            next_gate.get("requires_fresh_strategy_signal") is True
        ),
        "next_attempt_requires_fresh_authorization": (
            next_gate.get("requires_fresh_authorization") is True
        ),
        "old_authorization_retry_disallowed": (
            post_finalize.get("old_authorization_submit_retry_allowed") is False
        ),
        "pre_submit_rehearsal_retry_disallowed": (
            post_finalize.get("pre_submit_rehearsal_retry_allowed") is False
        ),
        "local_created_order_requirement_retired": (
            post_finalize.get("local_created_order_requirement_retired") is True
        ),
        "submit_outcome_review_created": review.get("created_count") == 1,
        "post_submit_budget_settlement_created": (
            settlement.get("created_count") == 1
        ),
        "right_tail_runner_preserved": bool(
            fresh_checks.get("right_tail_runner_preserved")
        ),
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "live_exchange_called": safety["live_exchange_called"],
        "pg_written": safety["pg_written"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "rtf090_prerequisite_passed",
        "rtf088_post_submit_finalize_passed",
        "candidate_ids_match",
        "runtime_ids_match",
        "fresh_preflight_ready",
        "final_gate_passed",
        "controlled_submit_preflight_ready",
        "fresh_authorization_required_before_submit",
        "controlled_gateway_action_passed",
        "exchange_execution_result_submitted",
        "durable_execution_result_reused",
        "post_submit_finalize_completed",
        "next_attempt_gate_blocked_by_active_position",
        "next_attempt_requires_fresh_signal",
        "next_attempt_requires_fresh_authorization",
        "old_authorization_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "local_created_order_requirement_retired",
        "submit_outcome_review_created",
        "post_submit_budget_settlement_created",
        "right_tail_runner_preserved",
        "uses_official_fastapi_routes",
    )
    required_false = (
        "uses_fake_console_api",
        "live_exchange_called",
        "pg_written",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    fresh_preflight_report: dict[str, Any],
    fresh_preflight_artifact: dict[str, Any],
    post_submit_report: dict[str, Any],
    post_submit_artifact: dict[str, Any],
) -> dict[str, bool]:
    fresh_safety = fresh_preflight_report.get("safety_invariants") or {}
    post_safety = post_submit_report.get("safety_invariants") or {}
    post_checks = post_submit_report.get("checks") or {}
    return {
        "uses_official_fastapi_routes": True,
        "uses_fake_console_api": False,
        "fresh_candidate_preflight_ready": (
            fresh_preflight_artifact.get("status")
            == "fresh_candidate_ready_for_controlled_submit_adapter"
        ),
        "controlled_in_memory_execution_result_recorded": (
            (post_submit_artifact.get("statuses") or {}).get(
                "exchange_submit_execution_result"
            )
            == "exchange_submit_orders_submitted"
        ),
        "controlled_order_lifecycle_submit_called": bool(
            post_checks.get("controlled_gateway_action_passed")
        ),
        "controlled_fake_gateway_called": bool(
            post_checks.get("controlled_gateway_action_passed")
        ),
        "live_exchange_called": bool(post_checks.get("live_exchange_called")),
        "pg_written": (
            bool(fresh_safety.get("pg_written"))
            or bool(post_safety.get("pg_written"))
        ),
        "post_submit_created_order": bool(
            post_safety.get("post_submit_created_order")
        ),
        "post_submit_order_lifecycle_called": bool(
            post_safety.get("post_submit_order_lifecycle_called")
        ),
        "execution_intent_status_changed": bool(
            post_checks.get("execution_intent_status_changed")
        ),
        "withdrawal_or_transfer_created": (
            bool(fresh_safety.get("withdrawal_or_transfer_created"))
            or bool(post_safety.get("withdrawal_or_transfer_created"))
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an official fresh-candidate runtime cycle handoff proof."
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf091-official-fresh-candidate-runtime-cycle-handoff",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"]
        == "official_fresh_candidate_runtime_cycle_handoff_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
