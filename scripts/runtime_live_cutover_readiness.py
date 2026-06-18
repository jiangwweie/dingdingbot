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
SCHEMA = "brc.runtime_live_cutover_readiness.v1"

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
        "allocated_subaccount_profile_boundary_checked",
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
    "live_closure_cutover_contract": [
        "live_closure_contract_defined",
        "live_closure_contract_rejects_synthetic_signal",
        "live_closure_contract_rejects_disabled_smoke",
        "live_closure_contract_requires_live_signal_chain_binding",
        "live_closure_contract_requires_pre_submit_authorization_chain_binding",
        "live_closure_contract_requires_exchange_acceptance",
        "live_closure_contract_requires_live_submit_truth",
        "live_closure_contract_requires_exchange_native_protection",
        "live_closure_contract_requires_exchange_native_protection_binding",
        "live_closure_contract_requires_post_submit_reconciliation",
        "live_closure_contract_requires_post_submit_result_binding",
        "live_closure_contract_has_no_owner_chat_confirmation_stage",
    ],
    "same_tick_product_state_visibility": [
        "product_state_refresh_status_ok",
        "product_state_live_closure_before_goal_status",
        "product_state_goal_status_before_source_readiness",
        "product_state_refresh_has_no_dangerous_effects",
    ],
    "dry_run_safety": [
        "dangerous_effects_absent",
        "disabled_smoke_not_real_execution_proof",
    ],
}

LIVE_CLOSURE_CUTOVER_STAGES = [
    {
        "name": "live_fresh_signal",
        "market_dependent": True,
        "required_evidence_keys": ["live_watcher_signal_packet_id"],
        "reject_if": ["synthetic_signal", "replay_signal", "stale_signal"],
        "next_action": "build_required_facts_readiness",
    },
    {
        "name": "required_facts_ready",
        "market_dependent": True,
        "required_evidence_keys": ["required_facts_readiness_packet_id"],
        "reject_if": [
            "missing_fact",
            "stale_fact",
            "live_signal_chain_proof_missing",
            "live_signal_chain_id_mismatch",
            "required_facts_signal_source_missing",
        ],
        "next_action": "prepare_candidate_authorization",
    },
    {
        "name": "candidate_authorization_bound",
        "market_dependent": True,
        "required_evidence_keys": [
            "candidate_id",
            "runtime_grant_id",
            "fresh_submit_authorization_id",
        ],
        "reject_if": [
            "strategy_scope_mismatch",
            "profile_boundary_mismatch",
            "pre_submit_authorization_chain_proof_missing",
            "pre_submit_authorization_chain_id_mismatch",
            "live_signal_chain_proof_missing",
            "live_signal_chain_id_mismatch",
            "candidate_signal_source_missing",
            "candidate_authorization_chain_source_missing",
        ],
        "next_action": "run_action_time_finalgate",
    },
    {
        "name": "action_time_finalgate_passed",
        "market_dependent": True,
        "required_evidence_keys": ["action_time_finalgate_packet_id"],
        "reject_if": [
            "active_position",
            "open_order",
            "budget_missing",
            "duplicate_submit_risk",
            "pre_submit_authorization_chain_proof_missing",
            "pre_submit_authorization_chain_id_mismatch",
            "finalgate_authorization_chain_source_missing",
        ],
        "next_action": "prepare_official_operation_layer_submit",
    },
    {
        "name": "official_operation_layer_ready",
        "market_dependent": True,
        "required_evidence_keys": ["operation_layer_submit_authorization_id"],
        "reject_if": [
            "operation_layer_not_ready",
            "disabled_smoke_only",
            "pre_submit_authorization_chain_proof_missing",
            "pre_submit_authorization_chain_id_mismatch",
            "operation_layer_authorization_chain_source_missing",
        ],
        "next_action": "submit_through_official_operation_layer",
    },
    {
        "name": "real_exchange_acceptance",
        "market_dependent": True,
        "required_evidence_keys": ["exchange_submit_execution_result_id"],
        "reject_if": [
            "exchange_submit_failed_before_acceptance",
            "live_submit_proof_missing",
            "live_submit_proof_result_id_mismatch",
            "live_submit_proof_result_source_missing",
            "live_exchange_not_called",
            "real_order_not_placed",
        ],
        "next_action": "attach_exchange_native_protection",
    },
    {
        "name": "exchange_native_protection",
        "market_dependent": True,
        "required_evidence_keys": ["exchange_native_hard_stop_order_id"],
        "reject_if": [
            "hard_stop_missing",
            "local_only_stop",
            "exchange_native_protection_proof_missing",
            "exchange_native_protection_result_id_mismatch",
            "exchange_native_protection_result_source_missing",
        ],
        "next_action": "run_post_submit_finalize",
    },
    {
        "name": "post_submit_finalize",
        "market_dependent": True,
        "required_evidence_keys": ["runtime_post_submit_finalize_packet_id"],
        "reject_if": [
            "finalize_missing",
            "next_attempt_gate_missing",
            "post_submit_close_loop_proof_missing",
            "post_submit_finalize_result_source_missing",
        ],
        "next_action": "reconcile_settle_and_review",
    },
    {
        "name": "reconciliation_settlement_review",
        "market_dependent": True,
        "required_evidence_keys": [
            "post_submit_reconciliation_evidence_id",
            "post_submit_budget_settlement_id",
            "submit_outcome_review_id",
        ],
        "reject_if": [
            "reconciliation_missing",
            "settlement_missing",
            "review_missing",
            "post_submit_close_loop_proof_missing",
            "post_submit_close_loop_result_source_missing",
        ],
        "next_action": "mark_first_bounded_live_order_closure_complete",
    },
]


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


def _live_closure_cutover_contract() -> dict[str, Any]:
    evidence_keys = [
        evidence_key
        for stage in LIVE_CLOSURE_CUTOVER_STAGES
        for evidence_key in stage["required_evidence_keys"]
    ]
    stage_names = [stage["name"] for stage in LIVE_CLOSURE_CUTOVER_STAGES]
    reject_reasons = [
        reason
        for stage in LIVE_CLOSURE_CUTOVER_STAGES
        for reason in stage["reject_if"]
    ]
    checks = {
        "live_closure_contract_defined": bool(LIVE_CLOSURE_CUTOVER_STAGES),
        "live_closure_contract_rejects_synthetic_signal": (
            "synthetic_signal" in reject_reasons
            and "replay_signal" in reject_reasons
            and "stale_signal" in reject_reasons
        ),
        "live_closure_contract_rejects_disabled_smoke": (
            "disabled_smoke_only" in reject_reasons
        ),
        "live_closure_contract_requires_live_signal_chain_binding": (
            "live_signal_chain_proof_missing" in reject_reasons
            and "live_signal_chain_id_mismatch" in reject_reasons
            and "required_facts_signal_source_missing" in reject_reasons
            and "candidate_signal_source_missing" in reject_reasons
        ),
        "live_closure_contract_requires_pre_submit_authorization_chain_binding": (
            "pre_submit_authorization_chain_proof_missing" in reject_reasons
            and "pre_submit_authorization_chain_id_mismatch" in reject_reasons
            and "candidate_authorization_chain_source_missing" in reject_reasons
            and "finalgate_authorization_chain_source_missing" in reject_reasons
            and "operation_layer_authorization_chain_source_missing"
            in reject_reasons
        ),
        "live_closure_contract_requires_exchange_acceptance": (
            "exchange_submit_execution_result_id" in evidence_keys
        ),
        "live_closure_contract_requires_live_submit_truth": (
            "live_submit_proof_missing" in reject_reasons
            and "live_submit_proof_result_id_mismatch" in reject_reasons
            and "live_submit_proof_result_source_missing" in reject_reasons
            and "live_exchange_not_called" in reject_reasons
            and "real_order_not_placed" in reject_reasons
        ),
        "live_closure_contract_requires_exchange_native_protection": (
            "exchange_native_hard_stop_order_id" in evidence_keys
        ),
        "live_closure_contract_requires_exchange_native_protection_binding": (
            "exchange_native_protection_proof_missing" in reject_reasons
            and "exchange_native_protection_result_id_mismatch" in reject_reasons
            and "exchange_native_protection_result_source_missing" in reject_reasons
        ),
        "live_closure_contract_requires_post_submit_reconciliation": (
            "post_submit_reconciliation_evidence_id" in evidence_keys
            and "post_submit_budget_settlement_id" in evidence_keys
            and "submit_outcome_review_id" in evidence_keys
        ),
        "live_closure_contract_requires_post_submit_result_binding": (
            "post_submit_close_loop_proof_missing" in reject_reasons
            and "post_submit_finalize_result_source_missing" in reject_reasons
            and "post_submit_close_loop_result_source_missing" in reject_reasons
        ),
        "live_closure_contract_has_no_owner_chat_confirmation_stage": all(
            "owner_chat_confirmation" not in stage["name"]
            and "owner_chat_confirmation" not in stage["next_action"]
            and "owner_chat_confirmation" not in stage["required_evidence_keys"]
            for stage in LIVE_CLOSURE_CUTOVER_STAGES
        ),
    }
    return {
        "scope": "first_bounded_live_order_closure_cutover_contract",
        "status": "ready" if all(checks.values()) else "blocked",
        "stage_count": len(LIVE_CLOSURE_CUTOVER_STAGES),
        "stage_order": stage_names,
        "required_evidence_keys": evidence_keys,
        "stages": LIVE_CLOSURE_CUTOVER_STAGES,
        "checks": checks,
    }


def build_live_closure_cutover_contract() -> dict[str, Any]:
    return _live_closure_cutover_contract()


class _FakeReadModelResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeReadModelResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _same_tick_product_state_visibility_contract(output_dir: Path) -> dict[str, Any]:
    from scripts.refresh_strategygroup_runtime_product_state_packets import (
        refresh_packets,
    )

    contract_dir = output_dir / "same-tick-product-state-refresh"
    events: list[str] = []
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "strategy_group_live_facts_ready_for_armed_observation"},
        },
        "/api/trading-console/owner-console-source-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "ready"},
        },
        "/api/trading-console/strategygroup-runtime-pilot-status": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [],
            "data": {"status": "waiting_for_market"},
        },
    }

    def opener(request: Any, timeout: int) -> _FakeReadModelResponse:
        path = str(request.full_url).replace("http://cutover.local", "")
        events.append(f"api:{path}")
        return _FakeReadModelResponse(payloads[path])

    def dry_run_builder(_output_dir: Path) -> dict[str, Any]:
        events.append("dry_run")
        return {
            "scope": "runtime_dry_run_audit_chain",
            "status": "passed",
            "scenario_count": 14,
            "checks": {"dangerous_effects_absent": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    def chain_closure_status_builder(**kwargs: Any) -> dict[str, Any]:
        events.append("chain_closure")
        return {
            "scope": "runtime_execution_chain_closure_status",
            "status": "non_market_execution_chain_ready",
            "real_execution": {
                "real_order_allowed": False,
                "missing_live_proofs": ["live_fresh_signal"],
            },
        }

    def live_closure_evidence_refresher(**kwargs: Any) -> dict[str, Any]:
        events.append("live_closure")
        return {
            "scope": "runtime_live_closure_evidence_refresh",
            "status": "live_closure_refresh_not_started",
            "verification": {
                "status": "live_closure_not_started",
                "first_bounded_real_order_complete": False,
                "real_order_closure_proven": False,
                "reject_reasons": [],
            },
        }

    def goal_status_builder(**kwargs: Any) -> dict[str, Any]:
        events.append("goal_status")
        return {
            "scope": "strategygroup_runtime_goal_status",
            "status": "waiting_for_market",
            "ready_for_real_order_action": False,
            "checks": {
                "runtime_dry_run_audit_passed": True,
                "ready_for_real_order_action": False,
            },
            "owner_state": {
                "status": "waiting_for_opportunity",
                "next_safe_checkpoint": "continue_watcher_observation",
            },
            "real_order_boundary": {"ready_for_real_order_action": False},
        }

    refresh = refresh_packets(
        api_base="http://cutover.local",
        output_dir=contract_dir,
        label="local-cutover-contract",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
        refresh_dry_run_audit_chain=True,
        dry_run_output_dir=contract_dir / "dry-run-audit-chain",
        dry_run_output_json=contract_dir / "runtime-dry-run-audit-chain.json",
        dry_run_builder=dry_run_builder,
        refresh_chain_closure_status=True,
        chain_closure_output_json=(
            contract_dir / "runtime-execution-chain-closure-status.json"
        ),
        chain_closure_status_builder=chain_closure_status_builder,
        refresh_live_closure_evidence=True,
        live_closure_evidence_refresher=live_closure_evidence_refresher,
        refresh_goal_status=True,
        goal_status_output_json=contract_dir / "strategygroup-runtime-goal-status.json",
        release_manifest=contract_dir / "manifest.json",
        expected_head="local-cutover-contract",
        goal_status_builder=goal_status_builder,
    )
    safety = refresh.get("safety_invariants") if isinstance(refresh, dict) else {}
    checks = {
        "product_state_refresh_status_ok": refresh.get("status") == "refreshed",
        "product_state_live_closure_before_goal_status": (
            "live_closure" in events
            and "goal_status" in events
            and events.index("live_closure") < events.index("goal_status")
        ),
        "product_state_goal_status_before_source_readiness": (
            "goal_status" in events
            and "api:/api/trading-console/owner-console-source-readiness" in events
            and events.index("goal_status")
            < events.index("api:/api/trading-console/owner-console-source-readiness")
        ),
        "product_state_refresh_has_no_dangerous_effects": (
            isinstance(safety, dict)
            and safety.get("exchange_write_called") is False
            and safety.get("order_created") is False
            and safety.get("order_lifecycle_called") is False
            and safety.get("withdrawal_or_transfer_created") is False
            and safety.get("places_order") is False
            and safety.get("mutates_pg") is False
        ),
    }
    return {
        "scope": "same_tick_product_state_visibility_contract",
        "status": "ready" if all(checks.values()) else "blocked",
        "events": events,
        "checks": checks,
        "refresh_status": refresh.get("status"),
        "refresh_blockers": list(refresh.get("blockers") or []),
        "refresh_output_dir": str(contract_dir),
        "safety_invariants": {
            "calls_tokyo_api": False,
            "mutates_server_files": False,
            "calls_live_finalgate": False,
            "calls_live_operation_layer": False,
            "exchange_write_called": bool(
                isinstance(safety, dict) and safety.get("exchange_write_called")
            ),
            "order_lifecycle_called": bool(
                isinstance(safety, dict) and safety.get("order_lifecycle_called")
            ),
            "real_order_created": bool(
                isinstance(safety, dict) and safety.get("order_created")
            ),
            "withdrawal_or_transfer_created": bool(
                isinstance(safety, dict)
                and safety.get("withdrawal_or_transfer_created")
            ),
        },
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
    live_closure_contract = _live_closure_cutover_contract()
    contract_checks = live_closure_contract.get("checks")
    if not isinstance(contract_checks, dict):
        contract_checks = {}
    same_tick_visibility = _same_tick_product_state_visibility_contract(output_dir)
    same_tick_checks = same_tick_visibility.get("checks")
    if not isinstance(same_tick_checks, dict):
        same_tick_checks = {}
    effective_checks = {
        **checks,
        **legacy_checks,
        **contract_checks,
        **same_tick_checks,
    }
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
        "schema": SCHEMA,
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
        "live_closure_cutover_contract": live_closure_contract,
        "same_tick_product_state_visibility_contract": same_tick_visibility,
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
