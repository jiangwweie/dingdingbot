#!/usr/bin/env python3
"""Summarize StrategyGroup runtime execution-chain closure status.

This script compresses the local dry-run audit chain into a small status artifact
for automation and human progress reports. It is intentionally non-executing:
it does not call Tokyo, does not call exchange write paths, and does not turn
disabled smoke into real execution proof.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_dry_run_audit_chain as audit_chain  # noqa: E402
from scripts import runtime_live_cutover_readiness as live_cutover  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/chain-closure-status")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-execution-chain-closure-status.json"
DEFAULT_DRY_RUN_OUTPUT_DIR = DEFAULT_OUTPUT_DIR / "dry-run-audit-chain"
PROJECTED_DRY_RUN_CHECKS = [
    "fresh_signal_fast_auto_chain_checked",
    "required_facts_readiness_checked",
    "execution_attempt_rehearsal_prepare_checked",
    "disabled_smoke_not_real_execution_proof",
    "ticket_bound_operation_layer_handoff_checked",
    "scoped_pipeline_operation_layer_submit_projection_checked",
    "legacy_authorization_finalgate_ready_retirement_checked",
    "legacy_authorization_submit_retirement_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "operation_layer_blocker_review_policy_checked",
    "operation_layer_authorization_chain_guard_checked",
    "ticket_bound_protected_submit_boundary_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "shared_runtime_pipeline_checked",
    "common_execution_chain_reuse_checked",
    "strategygroup_adapter_boundary_checked",
    "strategy_intake_no_execution_pipeline_fields_checked",
    "runtime_tier_policy_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "new_strategygroups_default_observe_only_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "post_submit_exit_outcome_matrix_checked",
    "reduce_only_recovery_standing_authorization_checked",
    "operation_layer_submit_result_identity_guard_checked",
    "post_submit_finalize_result_identity_guard_checked",
]
GOAL_CHAIN_SEGMENTS = {
    "fresh_or_mock_signal": [
        "fresh_signal_fast_auto_chain_checked",
    ],
    "required_facts_readiness": [
        "required_facts_readiness_checked",
    ],
    "candidate_authorization_evidence": [
        "fresh_signal_fast_auto_chain_checked",
        "execution_attempt_rehearsal_prepare_checked",
    ],
    "action_time_finalgate": [
        "fresh_signal_fast_auto_chain_checked",
        "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    ],
    "ticket_bound_operation_layer_handoff_projection": [
        "ticket_bound_operation_layer_handoff_checked",
        "scoped_pipeline_operation_layer_submit_projection_checked",
        "ticket_bound_protected_submit_boundary_checked",
    ],
    "disabled_dry_run_proof": [
        "disabled_smoke_not_real_execution_proof",
        "legacy_authorization_finalgate_ready_retirement_checked",
        "legacy_authorization_submit_retirement_checked",
    ],
    "post_submit_exit_outcome_matrix": [
        "post_submit_closed_loop_evidence_guard_checked",
        "post_submit_exit_outcome_matrix_checked",
        "reduce_only_recovery_standing_authorization_checked",
    ],
}
GOAL_CHAIN_SEGMENT_SCENARIOS = {
    "fresh_or_mock_signal": [
        "mock_fresh_signal_dry_run_pass",
    ],
    "required_facts_readiness": [
        "mock_fresh_signal_dry_run_pass",
        "required_facts_missing",
    ],
    "candidate_authorization_evidence": [
        "mock_fresh_signal_dry_run_pass",
        "execution_attempt_rehearsal_prepare",
    ],
    "action_time_finalgate": [
        "mock_fresh_signal_dry_run_pass",
        "execution_attempt_rehearsal_prepare",
    ],
    "ticket_bound_operation_layer_handoff_projection": [
        "mock_fresh_signal_dry_run_pass",
        "scoped_pipeline_operation_layer_submit_projection",
    ],
    "disabled_dry_run_proof": [
        "mock_fresh_signal_dry_run_pass",
        "scoped_pipeline_operation_layer_submit_projection",
        "legacy_authorization_submit_retired",
    ],
    "post_submit_exit_outcome_matrix": [
        "post_submit_closed_loop_evidence_guard",
    ],
}
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
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


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


def _scenario_statuses(audit_artifact: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    scenarios = audit_artifact.get("scenarios")
    if not isinstance(scenarios, list):
        return statuses
    for item in scenarios:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        statuses[name] = str(item.get("status") or "").strip()
    return statuses


def _goal_chain_segment_evidence(
    *,
    projected_checks: dict[str, bool],
    scenario_statuses: dict[str, str],
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for segment, required_checks in GOAL_CHAIN_SEGMENTS.items():
        scenario_names = GOAL_CHAIN_SEGMENT_SCENARIOS.get(segment, [])
        scenario_states = {
            name: scenario_statuses.get(name, "missing")
            for name in scenario_names
        }
        checks_passed = all(
            projected_checks.get(check) is True for check in required_checks
        )
        scenarios_passed = all(
            scenario_states.get(name) == "passed" for name in scenario_names
        )
        evidence[segment] = {
            "required_checks": list(required_checks),
            "scenario_names": list(scenario_names),
            "scenario_statuses": scenario_states,
            "checks_passed": checks_passed,
            "scenarios_passed": scenarios_passed,
            "ready": checks_passed and scenarios_passed,
        }
    return evidence


def _live_closure_contract() -> dict[str, Any]:
    return live_cutover.build_live_closure_cutover_contract()


def build_status_artifact(*, audit_artifact: dict[str, Any]) -> dict[str, Any]:
    required_checks = _dict(audit_artifact.get("required_checks"))
    safety = _dict(audit_artifact.get("safety_invariants"))
    failed_checks = _failed_required_checks(required_checks)
    dangerous_effects = _dangerous_effects(safety)
    projected_checks = _projected_dry_run_checks(required_checks)
    scenario_statuses = _scenario_statuses(audit_artifact)
    live_closure_contract = _live_closure_contract()
    live_closure_stages = [
        str(item)
        for item in live_closure_contract.get("stage_order") or []
    ]
    live_closure_required_evidence_keys = [
        str(item)
        for item in live_closure_contract.get("required_evidence_keys") or []
    ]
    goal_chain_segment_evidence = _goal_chain_segment_evidence(
        projected_checks=projected_checks,
        scenario_statuses=scenario_statuses,
    )
    goal_chain_segments = {
        segment: bool(item.get("ready"))
        for segment, item in goal_chain_segment_evidence.items()
    }
    audit_passed = (
        audit_artifact.get("status") == "passed"
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
            "source_scope": audit_artifact.get("scope"),
            "scenario_count": audit_artifact.get("scenario_count"),
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
            "goal_chain_segments": goal_chain_segments,
            "goal_chain_segment_evidence": goal_chain_segment_evidence,
            "ready_goal_chain_segments": [
                name for name, passed in goal_chain_segments.items() if passed
            ],
            "missing_or_failed_goal_chain_segments": [
                name for name, passed in goal_chain_segments.items() if not passed
            ],
            "common_execution_chain_reuse_checked": bool(
                _dict(audit_artifact.get("summary")).get(
                    "common_execution_chain_reuse_checked"
                )
            ),
            "scoped_pipeline_operation_layer_submit_projection_checked": bool(
                _dict(audit_artifact.get("summary")).get(
                    "scoped_pipeline_operation_layer_submit_projection_checked"
                )
            ),
            "post_submit_closed_loop_evidence_guard_checked": bool(
                _dict(audit_artifact.get("summary")).get(
                    "post_submit_closed_loop_evidence_guard_checked"
                )
            ),
            "operation_layer_submit_result_identity_guard_checked": bool(
                _dict(audit_artifact.get("summary")).get(
                    "operation_layer_submit_result_identity_guard_checked"
                )
            ),
            "post_submit_finalize_result_identity_guard_checked": bool(
                _dict(audit_artifact.get("summary")).get(
                    "post_submit_finalize_result_identity_guard_checked"
                )
            ),
        },
        "real_execution": {
            "status": "waiting_for_live_action_time_proof",
            "real_order_allowed": False,
            "disabled_smoke_is_real_execution_proof": False,
            "live_closure_cutover_contract_status": live_closure_contract.get("status"),
            "live_closure_stage_count": int(
                live_closure_contract.get("stage_count") or 0
            ),
            "missing_live_proof_stages": live_closure_stages,
            "missing_live_proofs": live_closure_required_evidence_keys,
            "missing_live_evidence_keys": live_closure_required_evidence_keys,
            "reason": (
                "local dry-run proof cannot replace live same-run FinalGate, "
                "official Operation Layer, exchange acceptance, exchange-native "
                "protection, and post-submit settlement evidence"
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
        description="Build the runtime execution-chain closure status artifact."
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
        audit_artifact = _read_json(Path(args.audit_json).expanduser())
    else:
        audit_artifact = audit_chain.build_audit_artifact(
            Path(args.audit_output_dir).expanduser()
        )
    artifact = build_status_artifact(audit_artifact=audit_artifact)
    output_json = Path(args.output_json).expanduser()
    _write_json(output_json, artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if artifact["status"] == "non_market_execution_chain_ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
