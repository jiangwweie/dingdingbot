#!/usr/bin/env python3
"""Summarize StrategyGroup runtime execution-chain closure status.

This script compresses the local dry-run audit chain into a small status packet
for automation and human progress reports. It is intentionally non-executing:
it does not call Tokyo, does not call exchange write paths, and does not turn
disabled smoke into real execution proof.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_dry_run_audit_chain as audit_chain  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/chain-closure-status")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-execution-chain-closure-status.json"
DEFAULT_DRY_RUN_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "dry-run-audit-chain"
REQUIRED_LIVE_PROOFS = [
    "live_fresh_signal",
    "same_run_action_time_finalgate_pass",
    "official_operation_layer_real_gateway_action",
    "post_submit_finalize_reconciliation_budget_settlement",
]
PROJECTED_DRY_RUN_CHECKS = [
    "fresh_signal_fast_auto_chain_checked",
    "non_executing_prepare_auto_bridge_checked",
    "operation_layer_evidence_relay_checked",
    "scoped_pipeline_operation_layer_handoff_checked",
    "mock_operation_layer_closed_loop_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "operation_layer_blocker_review_policy_checked",
    "operation_layer_authorization_chain_guard_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "shared_runtime_pipeline_checked",
    "common_execution_chain_reuse_checked",
    "strategygroup_adapter_boundary_checked",
    "strategy_handoff_no_execution_pipeline_fields_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "operation_layer_submit_result_identity_guard_checked",
    "post_submit_finalize_result_identity_guard_checked",
]
SAFETY_INVARIANT_KEYS = [
    "calls_tokyo_api",
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "withdrawal_or_transfer_created",
    "modifies_secret_or_credentials",
    "modifies_live_profile",
    "modifies_order_sizing_defaults",
    "finalgate_bypassed",
    "operation_layer_bypassed",
]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _failed_required_checks(required_checks: dict[str, Any]) -> list[str]:
    return sorted(
        str(name)
        for name, value in required_checks.items()
        if value is not True
    )


def _dangerous_effects(safety: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for name in SAFETY_INVARIANT_KEYS:
        if safety.get(name) is not False:
            effects.append(name)
    for item in safety.get("dangerous_effects") or []:
        text = str(item or "").strip()
        if text:
            effects.append(text)
    return sorted(set(effects))


def _projected_dry_run_checks(required_checks: dict[str, Any]) -> dict[str, bool]:
    return {
        name: required_checks.get(name) is True
        for name in PROJECTED_DRY_RUN_CHECKS
    }


def build_status_packet(*, audit_packet: dict[str, Any]) -> dict[str, Any]:
    required_checks = _dict(audit_packet.get("required_checks"))
    safety = _dict(audit_packet.get("safety_invariants"))
    failed_checks = _failed_required_checks(required_checks)
    dangerous_effects = _dangerous_effects(safety)
    projected_checks = _projected_dry_run_checks(required_checks)
    audit_passed = (
        audit_packet.get("status") == "passed"
        and not failed_checks
        and not dangerous_effects
        and safety.get("disabled_smoke_is_real_execution_proof") is False
    )
    status = (
        "non_market_execution_chain_ready"
        if audit_passed
        else "non_market_execution_chain_blocked"
    )
    if audit_passed:
        next_safe_actions = [
            "keep_watcher_running",
            "run_dry_run_audit_chain_after_runtime_changes",
            "on_fresh_signal_run_same_run_finalgate_then_official_operation_layer",
        ]
    else:
        next_safe_actions = [
            "repair_failed_dry_run_checks_before_waiting_for_market",
            "do_not_call_real_operation_layer",
        ]

    return {
        "scope": "runtime_execution_chain_closure_status",
        "status": status,
        "generated_at_ms": int(time.time() * 1000),
        "dry_run_chain": {
            "status": "passed" if audit_passed else "blocked",
            "source_scope": audit_packet.get("scope"),
            "scenario_count": audit_packet.get("scenario_count"),
            "required_checks_passed": not failed_checks,
            "failed_required_checks": failed_checks,
            "dangerous_effects_absent": not dangerous_effects,
            "dangerous_effects": dangerous_effects,
            "projected_checks": projected_checks,
            "ready_segments": [
                name for name, passed in projected_checks.items() if passed
            ],
            "missing_or_failed_segments": [
                name for name, passed in projected_checks.items() if not passed
            ],
            "common_execution_chain_reuse_checked": bool(
                _dict(audit_packet.get("summary")).get(
                    "common_execution_chain_reuse_checked"
                )
            ),
            "scoped_pipeline_operation_layer_handoff_checked": bool(
                _dict(audit_packet.get("summary")).get(
                    "scoped_pipeline_operation_layer_handoff_checked"
                )
            ),
            "post_submit_closed_loop_evidence_guard_checked": bool(
                _dict(audit_packet.get("summary")).get(
                    "post_submit_closed_loop_evidence_guard_checked"
                )
            ),
            "operation_layer_submit_result_identity_guard_checked": bool(
                _dict(audit_packet.get("summary")).get(
                    "operation_layer_submit_result_identity_guard_checked"
                )
            ),
            "post_submit_finalize_result_identity_guard_checked": bool(
                _dict(audit_packet.get("summary")).get(
                    "post_submit_finalize_result_identity_guard_checked"
                )
            ),
        },
        "real_execution": {
            "status": "waiting_for_live_action_time_proof",
            "real_order_allowed": False,
            "disabled_smoke_is_real_execution_proof": False,
            "missing_live_proofs": list(REQUIRED_LIVE_PROOFS),
            "reason": (
                "local dry-run proof cannot replace live same-run FinalGate, "
                "official Operation Layer, and post-submit settlement evidence"
            ),
        },
        "next_safe_actions": next_safe_actions,
        "safety_invariants": {
            name: False
            for name in SAFETY_INVARIANT_KEYS
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the runtime execution-chain closure status packet."
    )
    parser.add_argument(
        "--audit-json",
        help=(
            "Existing runtime-dry-run-audit-chain.json. If omitted, the audit "
            "chain is generated locally first."
        ),
    )
    parser.add_argument("--audit-output-dir", default=str(DEFAULT_DRY_RUN_OUTPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.audit_json:
        audit_packet = _read_json(Path(args.audit_json).expanduser())
    else:
        audit_packet = audit_chain.build_audit_chain(
            Path(args.audit_output_dir).expanduser()
        )
    packet = build_status_packet(audit_packet=audit_packet)
    output_json = Path(args.output_json).expanduser()
    _write_json(output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == "non_market_execution_chain_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
