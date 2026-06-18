#!/usr/bin/env python3
"""Build a local P0 live cutover readiness packet.

This packet compresses the existing non-executing runtime audit chain into an
Owner-readable answer: are non-market blockers cleared for the next fresh
selected StrategyGroup signal?

It never calls Tokyo, live FinalGate, live Operation Layer, OrderLifecycle, or
exchange write paths. It does not turn replay/synthetic signals into live
signals. It is a cutover-readiness projection, not submit authority.
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

from scripts import runtime_dry_run_audit_chain as dry_run_audit  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/live-cutover-readiness")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-live-cutover-readiness.json"
DEFAULT_OWNER_PROGRESS = DEFAULT_OUTPUT_DIR / "runtime-live-cutover-readiness.md"

MARKET_DEPENDENT_WAITING_KEYS = [
    "fresh_signal",
    "candidate_authorization",
    "action_time_finalgate",
    "official_operation_layer",
    "real_exchange_acceptance",
    "post_submit_real_reconciliation",
]

SECTION_CHECKS: dict[str, list[str]] = {
    "strategy_scope": [
        "runtime_tier_policy_checked",
        "only_mpg_tiny_real_order_eligible_checked",
        "common_execution_chain_reuse_checked",
        "strategygroup_adapter_boundary_checked",
        "strategy_handoff_no_execution_pipeline_fields_checked",
    ],
    "entry_fast_chain": [
        "fresh_signal_fast_auto_chain_checked",
        "required_facts_readiness_checked",
        "non_executing_prepare_auto_bridge_checked",
        "selected_strategygroup_dispatch_guard_checked",
        "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    ],
    "operation_layer_relay": [
        "operation_layer_evidence_relay_checked",
        "scoped_pipeline_operation_layer_handoff_checked",
        "operation_layer_authorization_chain_guard_checked",
    ],
    "hard_blocker_policy": [
        "operation_layer_hard_safety_blocker_matrix_checked",
        "operation_layer_blocker_review_policy_checked",
        "expanded_watcher_scope_execution_guard_checked",
    ],
    "exit_protection_recovery": [
        "post_submit_exit_outcome_matrix_checked",
        "reduce_only_recovery_standing_authorization_checked",
    ],
    "post_submit_close_loop": [
        "post_submit_closed_loop_evidence_guard_checked",
        "operation_layer_submit_result_identity_guard_checked",
        "post_submit_finalize_result_identity_guard_checked",
        "mock_operation_layer_closed_loop_checked",
    ],
    "legacy_confirmation_regression": [
        "disabled_smoke_not_real_execution_proof",
        "legacy_local_registration_probe_tolerated_without_blocking_cutover",
        "post_submit_outcomes_do_not_require_owner_chat_confirmation",
        "standing_reduce_only_recovery_does_not_require_owner_chat_confirmation",
    ],
    "dry_run_safety": [
        "dangerous_effects_absent",
        "disabled_smoke_not_real_execution_proof",
    ],
}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _section(name: str, checks: dict[str, Any]) -> dict[str, Any]:
    required = SECTION_CHECKS[name]
    missing = [check for check in required if checks.get(check) is not True]
    return {
        "name": name,
        "status": "ready" if not missing else "blocked",
        "required_checks": required,
        "missing_checks": missing,
    }


def _scenario_artifact(
    dry_run_packet: dict[str, Any],
    scenario_name: str,
    artifact_name: str,
) -> dict[str, Any]:
    scenarios = dry_run_packet.get("scenarios")
    if not isinstance(scenarios, list):
        return {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        if scenario.get("name") != scenario_name:
            continue
        artifacts = scenario.get("artifacts")
        if not isinstance(artifacts, dict):
            return {}
        value = artifacts.get(artifact_name)
        return value if isinstance(value, dict) else {}
    return {}


def _legacy_confirmation_regression_checks(
    dry_run_packet: dict[str, Any],
    checks: dict[str, Any],
) -> dict[str, bool]:
    guard = _scenario_artifact(
        dry_run_packet,
        "post_submit_closed_loop_evidence_guard",
        "post_submit_closed_loop_evidence_guard",
    )
    exit_matrix = guard.get("exit_outcome_matrix")
    if not isinstance(exit_matrix, dict):
        exit_matrix = {}
    exit_checks = exit_matrix.get("checks")
    if not isinstance(exit_checks, dict):
        exit_checks = {}
    return {
        "disabled_smoke_not_real_execution_proof": checks.get(
            "disabled_smoke_not_real_execution_proof"
        )
        is True,
        "legacy_local_registration_probe_tolerated_without_blocking_cutover": (
            checks.get("legacy_local_registration_probe_tolerance_checked") is True
        ),
        "post_submit_outcomes_do_not_require_owner_chat_confirmation": (
            exit_checks.get("no_post_submit_case_requires_owner_chat_confirmation")
            is True
        ),
        "standing_reduce_only_recovery_does_not_require_owner_chat_confirmation": (
            checks.get("reduce_only_recovery_standing_authorization_checked") is True
            and exit_checks.get(
                "protection_failure_recovery_uses_standing_authorization"
            )
            is True
        ),
    }


def _safety_invariants(dry_run_packet: dict[str, Any]) -> dict[str, bool]:
    safety = dry_run_packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    return {
        "calls_tokyo_api": bool(safety.get("calls_tokyo_api")),
        "mutates_server_files": False,
        "calls_live_finalgate": False,
        "calls_live_operation_layer": False,
        "exchange_write_called": bool(safety.get("exchange_write_called")),
        "order_lifecycle_called": bool(safety.get("order_lifecycle_called")),
        "real_order_created": bool(safety.get("real_order_created")),
        "withdrawal_or_transfer_created": bool(
            safety.get("withdrawal_or_transfer_created")
        ),
        "modifies_secret_or_credentials": bool(
            safety.get("modifies_secret_or_credentials")
        ),
        "modifies_live_profile": bool(safety.get("modifies_live_profile")),
        "modifies_order_sizing_defaults": bool(
            safety.get("modifies_order_sizing_defaults")
        ),
        "replay_or_synthetic_signal_used_as_live_signal": False,
    }


def _dangerous_effect_found(safety: dict[str, bool]) -> bool:
    return any(
        safety[key]
        for key in (
            "calls_tokyo_api",
            "mutates_server_files",
            "calls_live_finalgate",
            "calls_live_operation_layer",
            "exchange_write_called",
            "order_lifecycle_called",
            "real_order_created",
            "withdrawal_or_transfer_created",
            "modifies_secret_or_credentials",
            "modifies_live_profile",
            "modifies_order_sizing_defaults",
            "replay_or_synthetic_signal_used_as_live_signal",
        )
    )


def _owner_markdown(packet: dict[str, Any]) -> str:
    non_market = "无" if not packet["non_market_blockers"] else ", ".join(
        packet["non_market_blockers"]
    )
    sections = "\n".join(
        f"- {item['name']}: {item['status']}" for item in packet["sections"]
    )
    return "\n".join(
        [
            "## P0 Live Cutover Readiness",
            "",
            "- 当前状态: 等待真实 fresh signal"
            if packet["status"] == "live_cutover_waiting_for_fresh_signal"
            else "- 当前状态: 非市场阻断待修复",
            f"- Owner 状态: {packet['owner_state']}",
            f"- 非市场阻断: {non_market}",
            "- 服务器修改: 否",
            "- Live FinalGate: 否",
            "- Live Operation Layer: 否",
            "- Exchange write: 否",
            "- 接近真实订单: 否",
            "",
            "## Sections",
            "",
            sections,
            "",
            "## Boundary",
            "",
            "- 本包只读取本地 dry-run audit 语义。",
            "- 本包不把 replay / synthetic signal 伪造成真实市场信号。",
            "- 本包不是真实 submit authority。",
        ]
    )


def build_cutover_readiness_packet(
    output_dir: Path,
    *,
    dry_run_packet: dict[str, Any] | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dry_run_packet = dry_run_packet or dry_run_audit.build_audit_chain(
        output_dir / "dry-run-audit-chain"
    )
    checks = dry_run_packet.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    legacy_checks = _legacy_confirmation_regression_checks(dry_run_packet, checks)
    effective_checks = {**checks, **legacy_checks}
    sections = [_section(name, effective_checks) for name in SECTION_CHECKS]
    non_market_blockers = [
        f"{section['name']}:{check}"
        for section in sections
        for check in section["missing_checks"]
    ]
    safety = _safety_invariants(dry_run_packet)
    if _dangerous_effect_found(safety):
        non_market_blockers.append("dry_run_safety:dangerous_effect_found")
    if dry_run_packet.get("status") != "passed":
        for blocker in dry_run_packet.get("blockers") or []:
            non_market_blockers.append(f"dry_run_audit:{blocker}")

    ready = not non_market_blockers
    return {
        "scope": "runtime_live_cutover_readiness",
        "status": (
            "live_cutover_waiting_for_fresh_signal"
            if ready
            else "blocked_non_market_cutover_gap"
        ),
        "owner_state": "等待机会" if ready else "需要介入",
        "generated_at_ms": generated_at_ms or int(time.time() * 1000),
        "selected_strategy_group_id": "MPG-001",
        "first_live_lane": "selected_strategygroup_allocated_subaccount",
        "next_safe_action": (
            "continue_low_noise_watcher_until_fresh_selected_signal"
            if ready
            else "repair_non_market_cutover_blockers_before_next_signal"
        ),
        "next_fresh_signal_cutover_ready": ready,
        "current_real_submit_allowed": False,
        "current_real_submit_blocker": "no_live_fresh_signal_in_this_local_packet",
        "market_dependent_waiting_keys": MARKET_DEPENDENT_WAITING_KEYS,
        "non_market_blockers": non_market_blockers,
        "sections": sections,
        "source_packets": {
            "dry_run_audit_scope": dry_run_packet.get("scope"),
            "dry_run_audit_status": dry_run_packet.get("status"),
            "dry_run_scenario_count": dry_run_packet.get("scenario_count"),
        },
        "legacy_confirmation_regression_checks": legacy_checks,
        "safety_invariants": safety,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build local P0 live cutover readiness packet."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_cutover_readiness_packet(Path(args.output_dir).expanduser())
    output_json = Path(args.output_json).expanduser()
    owner_progress = Path(args.output_owner_progress).expanduser()
    _write_json(output_json, packet)
    _write_text(owner_progress, _owner_markdown(packet) + "\n")
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] == "live_cutover_waiting_for_fresh_signal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
