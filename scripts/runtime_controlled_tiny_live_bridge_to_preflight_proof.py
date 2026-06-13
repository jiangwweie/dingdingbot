#!/usr/bin/env python3
"""Controlled tiny-live bridge to official preflight proof.

RTF-101 proves the RTF-100 bridge can hand a ready selector state into the
existing official prepare / FinalGate / controlled-submit preflight proof,
while the current waiting selector state stays non-executing.

This is a local proof only.  It does not call live exchange, create local
orders, call OrderLifecycle submit, execute controlled submit, close positions,
withdraw, or transfer funds.
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

from scripts import runtime_controlled_tiny_live_bridge_readiness_packet as bridge  # noqa: E402
from scripts import runtime_official_flat_next_attempt_end_to_end_proof as rtf092  # noqa: E402
from scripts.runtime_official_scoped_local_registration_proof import _write_json  # noqa: E402


OfficialPreflightBuilder = Callable[[Path], dict[str, Any]]


def build_proof_report(
    output_dir: Path,
    *,
    official_preflight_builder: OfficialPreflightBuilder | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    official_builder = official_preflight_builder or rtf092.build_proof_report

    waiting_refresh = _waiting_refresh_packet()
    ready_refresh = _ready_prepare_refresh_packet()
    waiting_bridge = bridge.build_bridge_readiness_packet(
        refresh_packet=waiting_refresh,
        deployed_head="local-rtf101",
        release_name="local-rtf101-bridge-proof",
    )
    ready_bridge = bridge.build_bridge_readiness_packet(
        refresh_packet=ready_refresh,
        deployed_head="local-rtf101",
        release_name="local-rtf101-bridge-proof",
    )
    official_preflight = official_builder(output_dir / "rtf092-official-preflight")

    packet = _proof_packet(
        waiting_bridge=waiting_bridge,
        ready_bridge=ready_bridge,
        official_preflight=official_preflight,
    )
    artifacts = {
        "waiting-refresh.json": waiting_refresh,
        "ready-refresh.json": ready_refresh,
        "waiting-bridge-readiness.json": waiting_bridge,
        "ready-bridge-readiness.json": ready_bridge,
        "rtf092-official-preflight-report.json": official_preflight,
        "bridge-to-official-preflight-packet.json": packet,
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    checks = dict(packet["checks"])
    report = {
        "scope": "runtime_controlled_tiny_live_bridge_to_preflight_proof",
        "status": (
            "controlled_tiny_live_bridge_to_official_preflight_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "runtime_instance_id": official_preflight.get("runtime_instance_id"),
        "signal_evaluation_id": official_preflight.get("signal_evaluation_id"),
        "order_candidate_id": official_preflight.get("order_candidate_id"),
        "authorization_id": official_preflight.get("authorization_id"),
        "controlled_submit_preflight_id": official_preflight.get(
            "controlled_submit_preflight_id"
        ),
        "bridge_to_official_preflight_packet": packet,
        "checks": checks,
        "safety_invariants": packet["safety_invariants"],
        "operator_command_plan": {
            "next_step": (
                "run_local_fake_submit_then_post_submit_finalize_cycle"
                if _contract_passed(checks)
                else "resolve_bridge_to_official_preflight_blockers"
            ),
            "waiting_bridge_does_not_enter_official_route": True,
            "ready_bridge_enters_official_prepare_route": True,
            "requires_fresh_final_gate_before_submit": True,
            "requires_controlled_submit_preflight_before_exchange": True,
            "executes_submit": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "real_strategy_signal_required_before_new_attempt": True,
            "right_tail_runner_preserved": checks["right_tail_runner_preserved"],
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
            "not_proven_alpha": True,
        },
    }
    _write_json(output_dir / "contract-report.json", report)
    return report


def _waiting_refresh_packet() -> dict[str, Any]:
    return {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": "continuation_refresh_monitor_position_or_owner_close",
        "readiness_status": "live_attempt_blocked_by_runtime_or_signal_gate",
        "selector_status": "continuation_monitor_position_or_owner_close",
        "active_runtime_count": 3,
        "selected_continuation": {
            "runtime_instance_id": "strategy-runtime-e6138ad7c88f",
            "selected_action": "monitor_position_or_owner_authorize_reduce_only_close",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "strategy_family_id": "CPM-001",
            "strategy_family_version_id": "CPM-001-v0",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
        },
        "blockers": ["strategy-runtime-e6138ad7c88f:next_attempt_gate_blocked"],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "safety_invariants": _refresh_safety(),
        "operator_command_plan": {
            "ready_for_controlled_tiny_live_path": False,
            "execute_tiny_live_attempt_now": False,
            "execute_reduce_only_close_now": False,
        },
    }


def _ready_prepare_refresh_packet() -> dict[str, Any]:
    return {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": "continuation_refresh_ready_for_prepare",
        "readiness_status": "live_attempt_ready_for_prepare_review",
        "selector_status": "continuation_ready_for_prepare",
        "active_runtime_count": 1,
        "selected_continuation": {
            "runtime_instance_id": "runtime-rtf075-cpm-long",
            "selected_action": "prepare_shadow_candidate",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "strategy_family_id": "CPM-001",
            "strategy_family_version_id": "CPM-001-v0",
            "ready_for_prepare": True,
            "ready_for_final_gate_preflight": False,
            "signal_summary": {
                "evaluation_status": "ready_for_semantic_binding",
                "signal_type": "price_action_cpm_long",
                "required_execution_mode": "shadow_candidate",
                "confidence": "0.71",
                "reason_codes": ["rtf101_ready_signal_fixture"],
            },
        },
        "blockers": [],
        "warnings": [],
        "safety_invariants": _refresh_safety(),
        "operator_command_plan": {
            "ready_for_controlled_tiny_live_path": True,
            "execute_tiny_live_attempt_now": False,
            "execute_reduce_only_close_now": False,
        },
    }


def _refresh_safety() -> dict[str, Any]:
    return {
        "packet_only": True,
        "forbidden_effects": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_state_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "position_closed": False,
            "execute_real_submit": False,
            "exchange_submit_armed": False,
            "local_registration_armed": False,
            "executable_execution_intent_created": False,
        },
    }


def _proof_packet(
    *,
    waiting_bridge: dict[str, Any],
    ready_bridge: dict[str, Any],
    official_preflight: dict[str, Any],
) -> dict[str, Any]:
    official_packet = official_preflight.get("flat_next_attempt_end_to_end_packet") or {}
    official_checks = official_preflight.get("checks") or {}
    official_safety = official_preflight.get("safety_invariants") or {}
    checks = _checks(
        waiting_bridge=waiting_bridge,
        ready_bridge=ready_bridge,
        official_preflight=official_preflight,
        official_checks=official_checks,
        official_safety=official_safety,
    )
    return {
        "scope": "runtime_controlled_tiny_live_bridge_to_official_preflight_packet",
        "status": (
            "bridge_ready_for_official_controlled_submit_preflight"
            if _contract_passed(checks)
            else "blocked"
        ),
        "waiting_path": {
            "bridge_status": waiting_bridge.get("status"),
            "next_step": (waiting_bridge.get("operator_command_plan") or {}).get(
                "next_step"
            ),
            "selected_action": (
                waiting_bridge.get("selected_continuation") or {}
            ).get("selected_action"),
            "execute_tiny_live_attempt_now": (
                waiting_bridge.get("operator_command_plan") or {}
            ).get("execute_tiny_live_attempt_now"),
        },
        "ready_path": {
            "bridge_status": ready_bridge.get("status"),
            "next_step": (ready_bridge.get("operator_command_plan") or {}).get(
                "next_step"
            ),
            "selected_runtime_instance_id": (
                ready_bridge.get("operator_command_plan") or {}
            ).get("selected_runtime_instance_id"),
            "selected_action": (
                ready_bridge.get("operator_command_plan") or {}
            ).get("selected_action"),
        },
        "official_preflight": {
            "status": official_preflight.get("status"),
            "runtime_instance_id": official_preflight.get("runtime_instance_id"),
            "signal_evaluation_id": official_preflight.get("signal_evaluation_id"),
            "order_candidate_id": official_preflight.get("order_candidate_id"),
            "authorization_id": official_preflight.get("authorization_id"),
            "controlled_submit_preflight_id": official_preflight.get(
                "controlled_submit_preflight_id"
            ),
            "packet_status": official_packet.get("status"),
            "final_gate": official_packet.get("final_gate") or {},
            "controlled_submit_preflight": official_packet.get(
                "controlled_submit_preflight"
            )
            or {},
        },
        "checks": checks,
        "safety_invariants": _safety_invariants(
            waiting_bridge=waiting_bridge,
            ready_bridge=ready_bridge,
            official_safety=official_safety,
        ),
    }


def _checks(
    *,
    waiting_bridge: dict[str, Any],
    ready_bridge: dict[str, Any],
    official_preflight: dict[str, Any],
    official_checks: dict[str, Any],
    official_safety: dict[str, Any],
) -> dict[str, bool]:
    waiting_plan = waiting_bridge.get("operator_command_plan") or {}
    ready_plan = ready_bridge.get("operator_command_plan") or {}
    return {
        "waiting_bridge_blocks_official_route": (
            waiting_bridge.get("status")
            == "controlled_tiny_live_bridge_waiting_for_ready_selector"
            and waiting_plan.get("next_step") == "continue_selector_refresh_until_ready"
            and waiting_plan.get("execute_tiny_live_attempt_now") is False
            and waiting_plan.get("execute_reduce_only_close_now") is False
        ),
        "ready_bridge_enters_official_prepare": (
            ready_bridge.get("status")
            == "controlled_tiny_live_bridge_ready_for_official_prepare"
            and ready_plan.get("next_step")
            == "run_official_prepare_then_final_gate_preflight"
            and ready_plan.get("requires_fresh_final_gate_before_submit") is True
            and ready_plan.get("requires_controlled_submit_preflight_before_exchange")
            is True
        ),
        "bridge_uses_legacy_pre_attempt_as_primary_gate": bool(
            ready_plan.get("uses_legacy_pre_attempt_rehearsal_as_primary_gate")
        ),
        "official_preflight_passed": (
            official_preflight.get("status")
            == "official_flat_next_attempt_end_to_end_passed"
        ),
        "official_strategy_signal_created_shadow_evaluation": bool(
            official_checks.get("shadow_signal_created")
        ),
        "official_strategy_signal_created_shadow_candidate": bool(
            official_checks.get("shadow_candidate_created")
        ),
        "official_fresh_authorization_required": bool(
            official_checks.get("fresh_authorization_required_before_submit")
        ),
        "official_final_gate_passed": bool(
            official_checks.get("final_gate_verdict_pass")
        ),
        "official_controlled_submit_preflight_ready": bool(
            official_checks.get("controlled_submit_preflight_ready")
        ),
        "official_preflight_preview_only": bool(
            official_checks.get("preflight_preview_only")
        ),
        "old_authorization_retry_disallowed": bool(
            official_checks.get("old_authorization_retry_disallowed")
        ),
        "pre_submit_rehearsal_retry_disallowed": bool(
            official_checks.get("pre_submit_rehearsal_retry_disallowed")
        ),
        "right_tail_runner_preserved": bool(
            official_checks.get("right_tail_runner_preserved")
        ),
        "execution_intent_created_for_audit": bool(
            official_safety.get("execution_intent_created_for_audit")
        ),
        "executable_submit_executed": bool(
            official_safety.get("executable_submit_executed")
        ),
        "local_order_created": bool(official_safety.get("local_order_created")),
        "order_lifecycle_called": bool(
            official_safety.get("order_lifecycle_called")
        ),
        "exchange_called": bool(official_safety.get("exchange_called")),
        "runtime_state_mutated": bool(official_safety.get("runtime_state_mutated")),
        "withdrawal_or_transfer_created": bool(
            official_safety.get("withdrawal_or_transfer_created")
        ),
    }


def _contract_passed(checks: dict[str, bool]) -> bool:
    required_true = (
        "waiting_bridge_blocks_official_route",
        "ready_bridge_enters_official_prepare",
        "official_preflight_passed",
        "official_strategy_signal_created_shadow_evaluation",
        "official_strategy_signal_created_shadow_candidate",
        "official_fresh_authorization_required",
        "official_final_gate_passed",
        "official_controlled_submit_preflight_ready",
        "official_preflight_preview_only",
        "old_authorization_retry_disallowed",
        "pre_submit_rehearsal_retry_disallowed",
        "right_tail_runner_preserved",
        "execution_intent_created_for_audit",
    )
    required_false = (
        "bridge_uses_legacy_pre_attempt_as_primary_gate",
        "executable_submit_executed",
        "local_order_created",
        "order_lifecycle_called",
        "exchange_called",
        "runtime_state_mutated",
        "withdrawal_or_transfer_created",
    )
    return all(checks.get(key) is True for key in required_true) and all(
        checks.get(key) is False for key in required_false
    )


def _safety_invariants(
    *,
    waiting_bridge: dict[str, Any],
    ready_bridge: dict[str, Any],
    official_safety: dict[str, Any],
) -> dict[str, bool]:
    waiting_safety = waiting_bridge.get("safety_invariants") or {}
    ready_safety = ready_bridge.get("safety_invariants") or {}
    return {
        "waiting_bridge_packet_only": waiting_safety.get("packet_only") is True,
        "ready_bridge_packet_only": ready_safety.get("packet_only") is True,
        "bridge_no_forbidden_live_side_effects": (
            waiting_safety.get("no_forbidden_live_side_effects") is True
            and ready_safety.get("no_forbidden_live_side_effects") is True
        ),
        "uses_official_fastapi_routes": bool(
            official_safety.get("uses_official_fastapi_routes")
        ),
        "uses_fake_console_api": bool(official_safety.get("uses_fake_console_api")),
        "execution_intent_created_for_audit": bool(
            official_safety.get("execution_intent_created_for_audit")
        ),
        "executable_submit_executed": bool(
            official_safety.get("executable_submit_executed")
        ),
        "local_order_created": bool(official_safety.get("local_order_created")),
        "order_lifecycle_called": bool(
            official_safety.get("order_lifecycle_called")
        ),
        "exchange_called": bool(official_safety.get("exchange_called")),
        "runtime_state_mutated": bool(official_safety.get("runtime_state_mutated")),
        "withdrawal_or_transfer_created": bool(
            official_safety.get("withdrawal_or_transfer_created")
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a controlled tiny-live bridge to official preflight proof."
        )
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf101-controlled-tiny-live-bridge-to-preflight",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_proof_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"]
        == "controlled_tiny_live_bridge_to_official_preflight_passed"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
