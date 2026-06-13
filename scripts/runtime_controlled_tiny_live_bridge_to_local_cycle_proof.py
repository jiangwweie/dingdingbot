#!/usr/bin/env python3
"""Controlled tiny-live bridge to local runtime cycle proof.

RTF-102 composes:

RTF-101 bridge-ready official preflight proof
-> RTF-091 official fresh-candidate runtime cycle handoff proof

It proves the ready bridge can be followed by the local official route through
controlled in-memory submit, durable execution result, post-submit finalize,
budget / attempt settlement, and next-attempt gate.

This proof never calls a live exchange, writes PG, withdraws, transfers, or
places a real order.  The gateway and OrderLifecycle calls are the controlled
in-memory simulation expected inside RTF-091.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_controlled_tiny_live_bridge_to_preflight_proof as rtf101  # noqa: E402
from scripts import runtime_official_fresh_candidate_runtime_cycle_handoff_proof as rtf091  # noqa: E402
from scripts.runtime_official_scoped_local_registration_proof import _write_json  # noqa: E402


BridgePreflightBuilder = Callable[[Path], dict[str, Any]]
RuntimeCycleBuilder = Callable[[Path], dict[str, Any]]


def build_proof_report(
    output_dir: Path,
    *,
    bridge_preflight_builder: BridgePreflightBuilder | None = None,
    runtime_cycle_builder: RuntimeCycleBuilder | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    bridge_builder = bridge_preflight_builder or rtf101.build_proof_report
    cycle_builder = runtime_cycle_builder or rtf091.build_proof_report

    bridge_preflight = bridge_builder(output_dir / "rtf101-bridge-preflight")
    runtime_cycle = cycle_builder(output_dir / "rtf091-runtime-cycle")
    packet = _proof_packet(
        bridge_preflight=bridge_preflight,
        runtime_cycle=runtime_cycle,
    )
    artifacts = {
        "rtf101-bridge-preflight-report.json": bridge_preflight,
        "rtf091-runtime-cycle-report.json": runtime_cycle,
        "bridge-to-local-runtime-cycle-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    checks = dict(packet["checks"])
    report = {
        "scope": "runtime_controlled_tiny_live_bridge_to_local_cycle_proof",
        "status": (
            "controlled_tiny_live_bridge_to_local_cycle_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": runtime_cycle.get("runtime_instance_id"),
        "signal_evaluation_id": runtime_cycle.get("signal_evaluation_id"),
        "order_candidate_id": runtime_cycle.get("order_candidate_id"),
        "preflight_authorization_id": runtime_cycle.get(
            "preflight_authorization_id"
        ),
        "post_submit_authorization_id": runtime_cycle.get(
            "post_submit_authorization_id"
        ),
        "exchange_submit_execution_result_id": runtime_cycle.get(
            "exchange_submit_execution_result_id"
        ),
        "submit_outcome_review_id": runtime_cycle.get("submit_outcome_review_id"),
        "post_submit_budget_settlement_id": runtime_cycle.get(
            "post_submit_budget_settlement_id"
        ),
        "bridge_to_local_runtime_cycle_packet": packet,
        "checks": checks,
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "tokyo_integration_probe_for_bridge_to_runtime_cycle"
                if _contract_passed(checks)
                else "resolve_bridge_to_runtime_cycle_blockers"
            ),
            "uses_official_fastapi_routes": True,
            "uses_fake_console_api": False,
            "controlled_execution_mode": "in_memory_simulation",
            "calls_live_exchange": False,
            "executes_real_submit": False,
            "post_submit_finalize_completed": True,
            "next_attempt_requires_fresh_signal": True,
            "next_attempt_requires_fresh_authorization": True,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "post_submit_finalize_is_primary_after_submit": True,
            "old_authorization_is_replay_only": True,
            "right_tail_runner_preserved": checks["right_tail_runner_preserved"],
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


def _proof_packet(
    *,
    bridge_preflight: dict[str, Any],
    runtime_cycle: dict[str, Any],
) -> dict[str, Any]:
    bridge_packet = bridge_preflight.get("bridge_to_official_preflight_packet") or {}
    cycle_packet = runtime_cycle.get("fresh_candidate_runtime_cycle_packet") or {}
    checks = _checks(
        bridge_preflight=bridge_preflight,
        bridge_packet=bridge_packet,
        runtime_cycle=runtime_cycle,
        cycle_packet=cycle_packet,
    )
    return {
        "scope": "runtime_controlled_tiny_live_bridge_to_local_cycle_packet",
        "status": (
            "bridge_ready_local_runtime_cycle_completed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "bridge_side": {
            "status": bridge_preflight.get("status"),
            "waiting_bridge_status": (bridge_packet.get("waiting_path") or {}).get(
                "bridge_status"
            ),
            "ready_bridge_status": (bridge_packet.get("ready_path") or {}).get(
                "bridge_status"
            ),
            "official_preflight_status": (
                bridge_packet.get("official_preflight") or {}
            ).get("status"),
            "preflight_status": (
                (bridge_packet.get("official_preflight") or {}).get(
                    "controlled_submit_preflight"
                )
                or {}
            ).get("status"),
        },
        "runtime_cycle_side": {
            "status": runtime_cycle.get("status"),
            "runtime_instance_id": runtime_cycle.get("runtime_instance_id"),
            "signal_evaluation_id": runtime_cycle.get("signal_evaluation_id"),
            "order_candidate_id": runtime_cycle.get("order_candidate_id"),
            "exchange_submit_execution_result_id": runtime_cycle.get(
                "exchange_submit_execution_result_id"
            ),
            "submit_outcome_review_id": runtime_cycle.get(
                "submit_outcome_review_id"
            ),
            "post_submit_budget_settlement_id": runtime_cycle.get(
                "post_submit_budget_settlement_id"
            ),
            "cycle_status": cycle_packet.get("status"),
            "controlled_action_side": cycle_packet.get("controlled_action_side") or {},
            "post_submit_side": cycle_packet.get("post_submit_side") or {},
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            bridge_preflight=bridge_preflight,
            runtime_cycle=runtime_cycle,
            cycle_packet=cycle_packet,
        ),
    }


def _checks(
    *,
    bridge_preflight: dict[str, Any],
    bridge_packet: dict[str, Any],
    runtime_cycle: dict[str, Any],
    cycle_packet: dict[str, Any],
) -> dict[str, bool]:
    bridge_checks = bridge_preflight.get("checks") or {}
    cycle_checks = runtime_cycle.get("checks") or {}
    post_submit = cycle_packet.get("post_submit_side") or {}
    controlled_action = cycle_packet.get("controlled_action_side") or {}
    safety = _safety_invariants(
        bridge_preflight=bridge_preflight,
        runtime_cycle=runtime_cycle,
        cycle_packet=cycle_packet,
    )
    return {
        "rtf101_bridge_preflight_passed": (
            bridge_preflight.get("status")
            == "controlled_tiny_live_bridge_to_official_preflight_passed"
        ),
        "waiting_bridge_blocks_official_route": bool(
            bridge_checks.get("waiting_bridge_blocks_official_route")
        ),
        "ready_bridge_enters_official_prepare": bool(
            bridge_checks.get("ready_bridge_enters_official_prepare")
        ),
        "bridge_uses_legacy_pre_attempt_as_primary_gate": bool(
            bridge_checks.get("bridge_uses_legacy_pre_attempt_as_primary_gate")
        ),
        "rtf091_runtime_cycle_passed": (
            runtime_cycle.get("status")
            == "official_fresh_candidate_runtime_cycle_handoff_passed"
        ),
        "runtime_ids_match": bool(cycle_checks.get("runtime_ids_match")),
        "candidate_ids_match": (
            bool(cycle_checks.get("candidate_ids_match"))
            and bridge_preflight.get("order_candidate_id")
            == runtime_cycle.get("order_candidate_id")
            == "order-candidate-rtf075-contract"
        ),
        "final_gate_passed": bool(cycle_checks.get("final_gate_passed")),
        "controlled_submit_preflight_ready": bool(
            cycle_checks.get("controlled_submit_preflight_ready")
        ),
        "controlled_gateway_action_passed": bool(
            cycle_checks.get("controlled_gateway_action_passed")
        ),
        "controlled_in_memory_execution_result_recorded": (
            controlled_action.get("exchange_submit_execution_result_status")
            == "exchange_submit_orders_submitted"
        ),
        "durable_execution_result_reused": bool(
            cycle_checks.get("durable_execution_result_reused")
        ),
        "post_submit_finalize_completed": bool(
            cycle_checks.get("post_submit_finalize_completed")
        ),
        "post_submit_finalize_status_recorded": (
            post_submit.get("finalize_status") == "finalized_next_attempt_blocked"
        ),
        "next_attempt_gate_blocked_by_active_position": bool(
            cycle_checks.get("next_attempt_gate_blocked_by_active_position")
        ),
        "next_attempt_requires_fresh_signal": bool(
            cycle_checks.get("next_attempt_requires_fresh_signal")
        ),
        "next_attempt_requires_fresh_authorization": bool(
            cycle_checks.get("next_attempt_requires_fresh_authorization")
        ),
        "old_authorization_retry_disallowed": bool(
            cycle_checks.get("old_authorization_retry_disallowed")
        ),
        "pre_submit_rehearsal_retry_disallowed": bool(
            cycle_checks.get("pre_submit_rehearsal_retry_disallowed")
        ),
        "local_created_order_requirement_retired": bool(
            cycle_checks.get("local_created_order_requirement_retired")
        ),
        "submit_outcome_review_created": bool(
            cycle_checks.get("submit_outcome_review_created")
        ),
        "post_submit_budget_settlement_created": bool(
            cycle_checks.get("post_submit_budget_settlement_created")
        ),
        "right_tail_runner_preserved": (
            bool(bridge_checks.get("right_tail_runner_preserved"))
            and bool(cycle_checks.get("right_tail_runner_preserved"))
        ),
        "uses_official_fastapi_routes": (
            bool(bridge_checks.get("official_preflight_passed"))
            and bool(cycle_checks.get("uses_official_fastapi_routes"))
        ),
        "uses_fake_console_api": (
            bool(bridge_checks.get("uses_fake_console_api"))
            or bool(cycle_checks.get("uses_fake_console_api"))
        ),
        "controlled_fake_gateway_called": safety["controlled_fake_gateway_called"],
        "controlled_order_lifecycle_submit_called": safety[
            "controlled_order_lifecycle_submit_called"
        ],
        "live_exchange_called": safety["live_exchange_called"],
        "pg_written": safety["pg_written"],
        "withdrawal_or_transfer_created": safety[
            "withdrawal_or_transfer_created"
        ],
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "rtf101_bridge_preflight_passed",
        "waiting_bridge_blocks_official_route",
        "ready_bridge_enters_official_prepare",
        "rtf091_runtime_cycle_passed",
        "runtime_ids_match",
        "candidate_ids_match",
        "final_gate_passed",
        "controlled_submit_preflight_ready",
        "controlled_gateway_action_passed",
        "controlled_in_memory_execution_result_recorded",
        "durable_execution_result_reused",
        "post_submit_finalize_completed",
        "post_submit_finalize_status_recorded",
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
        "controlled_fake_gateway_called",
        "controlled_order_lifecycle_submit_called",
    )
    required_false = (
        "bridge_uses_legacy_pre_attempt_as_primary_gate",
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
    bridge_preflight: dict[str, Any],
    runtime_cycle: dict[str, Any],
    cycle_packet: dict[str, Any],
) -> dict[str, bool]:
    bridge_safety = bridge_preflight.get("safety_invariants") or {}
    cycle_safety = runtime_cycle.get("safety_invariants") or {}
    return {
        "bridge_no_forbidden_live_side_effects": bool(
            bridge_safety.get("bridge_no_forbidden_live_side_effects")
        ),
        "uses_official_fastapi_routes": bool(
            cycle_safety.get("uses_official_fastapi_routes")
        ),
        "uses_fake_console_api": bool(cycle_safety.get("uses_fake_console_api")),
        "controlled_in_memory_execution_result_recorded": bool(
            cycle_safety.get("controlled_in_memory_execution_result_recorded")
        ),
        "controlled_fake_gateway_called": bool(
            cycle_safety.get("controlled_fake_gateway_called")
        ),
        "controlled_order_lifecycle_submit_called": bool(
            cycle_safety.get("controlled_order_lifecycle_submit_called")
        ),
        "post_submit_created_order": bool(
            cycle_safety.get("post_submit_created_order")
        ),
        "post_submit_order_lifecycle_called": bool(
            cycle_safety.get("post_submit_order_lifecycle_called")
        ),
        "live_exchange_called": bool(cycle_safety.get("live_exchange_called")),
        "pg_written": bool(cycle_safety.get("pg_written")),
        "withdrawal_or_transfer_created": bool(
            cycle_safety.get("withdrawal_or_transfer_created")
        ),
        "real_order_placed": False,
        "real_funds_transfer_created": False,
        "runtime_cycle_status_completed": (
            cycle_packet.get("status") == "fresh_candidate_cycle_handoff_completed"
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a controlled tiny-live bridge to local runtime cycle proof."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf102-controlled-tiny-live-bridge-to-local-cycle",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"] == "controlled_tiny_live_bridge_to_local_cycle_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
