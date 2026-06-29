#!/usr/bin/env python3
"""Build the P0 Runtime Safety State snapshot.

The snapshot turns local pre-live rehearsal readiness into a runtime/monitor
consumable Runtime Safety standby state. It does not call FinalGate, Operation
Layer, exchange APIs, submit endpoints, or create real-order authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.domain.required_facts_readiness import (  # noqa: E402
    assess_required_fact,
    required_fact_status,
    required_fact_specs_from_rows,
)
from src.domain.runtime_readiness_state import (  # noqa: E402
    candidate_authorization_state_from_source,
    readiness_separation_from_runtime_safety_state,
)

from strategygroup_non_executing_projection import non_executing_interaction  # noqa: E402

DEFAULT_PRE_LIVE_READINESS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json"
)
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_LIVE_CUTOVER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-cutover-readiness.json"
)
DEFAULT_GOAL_PROGRESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
)
DEFAULT_COMPLETION_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-safety-state.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-safety-state.md"
)

ACTION_TIME_FACTS = [
    {
        "key": "trusted_submit_fact_snapshot",
        "question": "trusted submit fact snapshot",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "account_facts",
        "question": "account facts freshness",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "position_open_order_conflict",
        "question": "position and open-order conflict",
        "ready_status": "clear",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "budget_coverage",
        "question": "budget coverage",
        "ready_status": "sufficient",
        "stale_status": "stale",
        "missing_status": "insufficient",
    },
    {
        "key": "protection_template",
        "question": "protection template",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "submit_idempotency_policy",
        "question": "submit idempotency policy",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "duplicate_submit_guard",
        "question": "duplicate-submit guard",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "protection_failure_policy",
        "question": "protection failure policy",
        "ready_status": "ready",
        "stale_status": "stale",
        "missing_status": "missing",
    },
    {
        "key": "exchange_rules",
        "question": "exchange rule check",
        "ready_status": "pass",
        "stale_status": "stale",
        "missing_status": "fail",
    },
    {
        "key": "signal_freshness",
        "question": "signal freshness",
        "ready_status": "fresh",
        "stale_status": "expired",
        "missing_status": "waiting",
    },
]

FORBIDDEN_TRUE_PATHS = [
    ("interaction", "mutates_remote_files"),
    ("interaction", "approaches_real_order"),
    ("interaction", "calls_finalgate"),
    ("interaction", "calls_operation_layer"),
    ("interaction", "calls_exchange_write"),
    ("interaction", "places_order"),
    ("safety_invariants", "final_gate_called"),
    ("safety_invariants", "operation_layer_called"),
    ("safety_invariants", "exchange_write_called"),
    ("safety_invariants", "order_created"),
    ("safety_invariants", "live_profile_changed"),
    ("safety_invariants", "order_sizing_defaults_changed"),
    ("safety_invariants", "withdrawal_or_transfer_created"),
]


def build_runtime_safety_state(
    *,
    pre_live_readiness: dict[str, Any],
    daily_check: dict[str, Any],
    live_cutover: dict[str, Any],
    goal_progress: dict[str, Any],
    completion_audit: dict[str, Any],
    fact_sources: dict[str, Any] | None = None,
    candidate_authorization_state: dict[str, Any] | None = None,
    brf2_shadow_candidate_evidence: dict[str, Any] | None = None,
    signal_status_override: str | None = None,
) -> dict[str, Any]:
    fact_sources = fact_sources or {}
    candidate_authorization = _candidate_authorization_state(
        fact_sources=fact_sources,
        candidate_authorization_state=candidate_authorization_state,
        brf2_shadow_candidate_evidence=(
            brf2_shadow_candidate_evidence or {}
        ),
    )
    fresh_signal_state = _fresh_signal_state(
        daily_check=daily_check,
        live_cutover=live_cutover,
        goal_progress=goal_progress,
        signal_status_override=signal_status_override,
    )
    action_time_check_active = fresh_signal_state in {"fresh", "processing"}
    matrix = _action_time_required_facts_matrix(
        fact_sources=fact_sources,
        fresh_signal_state=fresh_signal_state,
        action_time_check_active=action_time_check_active,
    )
    hard_fact_blockers = [
        row["blocker"]
        for row in matrix
        if row["blocks_live_submit_now"] is True and row.get("blocker")
    ]
    pre_live_readiness_state = _as_dict(
        pre_live_readiness.get("runtime_readiness_state")
    )
    pre_live_ready = (
        pre_live_readiness.get("status") == "pre_live_rehearsal_ready"
        and pre_live_readiness_state.get("pre_live_rehearsal_ready") is True
    )
    status = _projection_status(
        pre_live_ready=pre_live_ready,
        fresh_signal_state=fresh_signal_state,
        hard_fact_blockers=hard_fact_blockers,
        completion_status=str(completion_audit.get("status") or ""),
    )
    owner_state = _owner_state_for_status(status, hard_fact_blockers)
    ready_for_finalgate_checkpoint = (
        status == "processing_ready_for_finalgate_checkpoint"
        and not hard_fact_blockers
    )
    live_submit_ready = False
    live_submit_ready_false_reason = _live_submit_ready_false_reason(
        fresh_signal_state=fresh_signal_state,
        hard_fact_blockers=hard_fact_blockers,
    )
    runtime_safety_state = _runtime_safety_state(
        status=status,
        pre_live_ready=pre_live_ready,
        fresh_signal_state=fresh_signal_state,
        hard_fact_blockers=hard_fact_blockers,
        ready_for_finalgate_checkpoint=ready_for_finalgate_checkpoint,
        candidate_authorization_state=candidate_authorization,
        owner_state=owner_state,
        live_submit_ready=live_submit_ready,
        live_submit_ready_false_reason=live_submit_ready_false_reason,
    )
    state_snapshot = {
        "schema": "brc.strategygroup_runtime_safety_state.v1",
        "scope": "p0_runtime_safety_state",
        "status": status,
        "runtime_safety_state": runtime_safety_state,
        "source_status": {
            "pre_live_rehearsal_readiness": pre_live_readiness.get("status"),
            "daily_check": daily_check.get("status"),
            "live_cutover": live_cutover.get("status"),
            "goal_progress": goal_progress.get("status"),
            "completion_audit": completion_audit.get("status"),
        },
        "fresh_signal_transition": {
            "current_checkpoint": _current_checkpoint(fresh_signal_state),
            "current_state": "waiting_for_market"
            if fresh_signal_state == "none"
            else "processing",
            "developer_audit_next_internal_gate_chain": [
                "RequiredFacts",
                "candidate/auth",
                "FinalGate",
                "Operation Layer",
            ],
            "signal_observation_grade_preempted_on_fresh_signal": (
                fresh_signal_state in {"fresh", "processing"}
            ),
            "owner_manual_internal_evidence_review_required": False,
        },
        "action_time_required_facts_matrix": matrix,
        "action_time_required_facts_behavior_evidence": (
            _action_time_required_facts_behavior_evidence(
                status=status,
                pre_live_ready=pre_live_ready,
                fresh_signal_state=fresh_signal_state,
                hard_fact_blockers=hard_fact_blockers,
                ready_for_finalgate_checkpoint=ready_for_finalgate_checkpoint,
            )
        ),
        "execution_attempt_rehearsal_preparation": (
            _execution_attempt_rehearsal_preparation(
                status=status,
                pre_live_ready=pre_live_ready,
                fresh_signal_state=fresh_signal_state,
                hard_fact_blockers=hard_fact_blockers,
            )
        ),
        "live_outcome_calibration_preparation": (
            _live_outcome_calibration_preparation()
        ),
        "strategygroup_advancement_preparation": (
            _strategygroup_advancement_preparation()
        ),
        "owner_state": owner_state,
        "interaction": non_executing_interaction("L0_runtime_safety_state"),
        "safety_invariants": {
            "local_runtime_safety_projection_only": True,
            "final_gate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    state_snapshot["validation_errors"] = validate_state_snapshot(state_snapshot)
    if state_snapshot["validation_errors"]:
        state_snapshot["status"] = "runtime_safety_state_failed"
    return state_snapshot


def validate_state_snapshot(state_snapshot: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if (
        state_snapshot.get("schema")
        != "brc.strategygroup_runtime_safety_state.v1"
    ):
        errors.append("schema_mismatch")
    for section, key in FORBIDDEN_TRUE_PATHS:
        if _as_dict(state_snapshot.get(section)).get(key) is True:
            errors.append(f"forbidden_true:{section}.{key}")
    matrix = _dict_rows(state_snapshot.get("action_time_required_facts_matrix"))
    matrix_keys = [str(row.get("key") or "") for row in matrix]
    expected_keys = [row["key"] for row in ACTION_TIME_FACTS]
    if matrix_keys != expected_keys:
        errors.append(f"required_facts_matrix_mismatch:{matrix_keys}")
    p2 = _as_dict(state_snapshot.get("execution_attempt_rehearsal_preparation"))
    operation_boundary = _as_dict(p2.get("operation_layer_input_shape_evidence"))
    for key in (
        "input_shape_ready",
        "protection_params_shape_ready",
        "budget_context_shape_ready",
        "idempotency_key_shape_ready",
        "recovery_path_shape_ready",
    ):
        if operation_boundary.get(key) is not True:
            errors.append(f"operation_layer_boundary_not_ready:{key}")
    for key in (
        "finalgate_pass_required_before_submit",
        "exchange_write_authority_gated",
        "operation_layer_submit_authority_required",
        "places_order",
        "calls_operation_layer",
    ):
        expected = False if key in {"places_order", "calls_operation_layer"} else True
        if operation_boundary.get(key) is not expected:
            errors.append(f"operation_layer_boundary_bad:{key}")
    owner_state = _as_dict(state_snapshot.get("owner_state"))
    if owner_state.get("owner_manual_internal_evidence_review_required") is not False:
        errors.append("owner_manual_internal_evidence_review_required")
    runtime_safety_state = _as_dict(state_snapshot.get("runtime_safety_state"))
    if runtime_safety_state.get("state_family") != "Runtime Safety State":
        errors.append("runtime_safety_state_family_missing")
    if runtime_safety_state.get("primary_judgment_source") is not True:
        errors.append("runtime_safety_state_not_primary_judgment_source")
    if runtime_safety_state.get("pre_live_rehearsal_ready") is not True:
        errors.append("pre_live_rehearsal_not_ready")
    if runtime_safety_state.get("live_submit_ready") is not False:
        errors.append("runtime_safety_state_live_submit_ready_requires_official_chain")
    for key in ("actionable_now", "real_order_authority"):
        if key in runtime_safety_state:
            errors.append(f"runtime_safety_state_legacy_authority_mirror_present:{key}")
    candidate_authorization_state = _as_dict(
        runtime_safety_state.get("candidate_authorization_state")
    )
    if candidate_authorization_state:
        if candidate_authorization_state.get("state_role") != "candidate_authorization":
            errors.append("candidate_authorization_state_role_mismatch")
        for key in (
            "live_submit_authority",
            "operation_layer_authority",
            "actionable_now",
            "real_order_authority",
        ):
            if key in candidate_authorization_state:
                errors.append(
                    f"candidate_authorization_state_legacy_authority_mirror_present:{key}"
                )
    p1 = _as_dict(state_snapshot.get("action_time_required_facts_behavior_evidence"))
    if p1.get("strategy_uncertainty_blocks_engineering_progress") is not False:
        errors.append("p1_strategy_uncertainty_blocks_engineering_progress")
    if "real_order_authority" in p2:
        errors.append("p2_legacy_authority_mirror_present:real_order_authority")
    p3 = _as_dict(state_snapshot.get("live_outcome_calibration_preparation"))
    if p3.get("live_outcome_calibrated") is not False:
        errors.append("p3_live_outcome_calibrated_requires_real_outcome")
    if p3.get("requires_real_live_outcome") is not True:
        errors.append("p3_requires_real_live_outcome_not_true")
    p4 = _as_dict(state_snapshot.get("strategygroup_advancement_preparation"))
    if p4.get("promotion_quality_final") is not False:
        errors.append("p4_promotion_quality_final_requires_evidence")
    if "actionable_now" in p4:
        errors.append("p4_legacy_authority_mirror_present:actionable_now")
    if state_snapshot.get("status") == "live_submit_standby_waiting_for_market":
        if runtime_safety_state.get("hard_fact_blockers") != []:
            errors.append("waiting_for_market_blockers_not_empty")
        if owner_state.get("owner_intervention_required") is not False:
            errors.append("waiting_for_market_owner_intervention")
        if (
            runtime_safety_state.get("live_submit_ready_false_reason")
            != "no_fresh_signal"
        ):
            errors.append("waiting_for_market_false_reason_not_no_fresh_signal")
    return errors


def _fresh_signal_state(
    *,
    daily_check: dict[str, Any],
    live_cutover: dict[str, Any],
    goal_progress: dict[str, Any],
    signal_status_override: str | None,
) -> str:
    if signal_status_override:
        return signal_status_override
    statuses = {
        str(daily_check.get("status") or ""),
        str(live_cutover.get("status") or ""),
        str(goal_progress.get("status") or ""),
    }
    if any("fresh_signal" in status and "waiting" not in status for status in statuses):
        return "fresh"
    if "processing" in statuses:
        return "processing"
    return "none"


def _action_time_required_facts_matrix(
    *,
    fact_sources: dict[str, Any],
    fresh_signal_state: str,
    action_time_check_active: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in required_fact_specs_from_rows(ACTION_TIME_FACTS):
        key = spec.key
        source = _as_dict(fact_sources.get(key))
        if key == "signal_freshness":
            raw_status = (
                "fresh"
                if fresh_signal_state in {"fresh", "processing"}
                else "expired"
                if fresh_signal_state == "expired"
                else "missing"
            )
        else:
            raw_status = str(
                source.get("status")
                or ("missing" if action_time_check_active else "pending_action_time")
            )
        assessment = assess_required_fact(
            spec=spec,
            raw_status=raw_status,
            action_time_check_active=action_time_check_active,
            check_surface="live_submit",
            owner_wording=_owner_wording_for_fact(
                key,
                required_fact_status(
                    spec=spec,
                    raw_status=raw_status,
                    action_time_check_active=action_time_check_active,
                ),
            ),
        )
        rows.append(assessment.as_runtime_safety_row())
    return rows


def _operation_layer_input_shape_evidence() -> dict[str, Any]:
    return {
        "input_shape_ready": True,
        "required_fields": [
            "strategy_group_id",
            "runtime_profile_id",
            "subaccount_boundary",
            "symbol",
            "side",
            "notional_or_quantity",
            "leverage",
            "protection_params",
            "budget_context",
            "submit_idempotency_key",
            "recovery_path",
            "authorization_evidence_ids",
        ],
        "protection_params_shape_ready": True,
        "budget_context_shape_ready": True,
        "idempotency_key_shape_ready": True,
        "recovery_path_shape_ready": True,
        "finalgate_pass_required_before_submit": True,
        "exchange_write_authority_gated": True,
        "operation_layer_submit_authority_required": True,
        "places_order": False,
        "calls_operation_layer": False,
    }


def _candidate_authorization_state(
    *,
    fact_sources: dict[str, Any],
    candidate_authorization_state: dict[str, Any] | None,
    brf2_shadow_candidate_evidence: dict[str, Any],
) -> dict[str, Any]:
    source = _as_dict(candidate_authorization_state) or _as_dict(
        fact_sources.get("candidate_authorization_state")
    )
    if not source:
        source = _candidate_authorization_state_from_brf2_evidence(
            brf2_shadow_candidate_evidence
        )
    if not source:
        return {}
    return candidate_authorization_state_from_source(source)


def _candidate_authorization_state_from_brf2_evidence(
    state_snapshot: dict[str, Any],
) -> dict[str, Any]:
    if state_snapshot.get("status") != "brf2_shadow_candidate_evidence_ready":
        return {}
    if state_snapshot.get("shadow_candidate_evidence_ready") is not True:
        return {}
    return {
        "state_source": "brf2_shadow_candidate_evidence",
        "strategy_group_id": str(state_snapshot.get("strategy_group_id") or "BRF2-001"),
        "status": "candidate_authorization_evidence_pending",
        "primary_judgment_source": False,
        "shadow_candidate_evidence_ready": True,
        "authorization_evidence_created": False,
        "ready_for_finalgate_checkpoint": False,
        "first_blocker_class": (
            "brf2_shadow_candidate_evidence_ready_authorization_evidence_not_created"
        ),
        "next_runtime_step": str(
            state_snapshot.get("next_runtime_step")
            or "prepare_fresh_candidate_authorization_evidence"
        ),
        "execution_attempt_required_for_lifecycle_entry": True,
    }


def _runtime_safety_state(
    *,
    status: str,
    pre_live_ready: bool,
    fresh_signal_state: str,
    hard_fact_blockers: list[str],
    ready_for_finalgate_checkpoint: bool,
    candidate_authorization_state: dict[str, Any],
    owner_state: dict[str, Any],
    live_submit_ready: bool,
    live_submit_ready_false_reason: str,
) -> dict[str, Any]:
    state = {
        "state_family": "Runtime Safety State",
        "status": status,
        "primary_judgment_source": True,
        "pre_live_rehearsal_ready": pre_live_ready,
        "fresh_signal_state": fresh_signal_state,
        "hard_fact_blockers": hard_fact_blockers,
        "ready_for_finalgate_checkpoint": ready_for_finalgate_checkpoint,
        "live_submit_ready": live_submit_ready,
        "live_submit_ready_false_reason": live_submit_ready_false_reason,
        "execution_attempt_required_for_lifecycle_entry": True,
        "source_sections": [
            "pre_live_rehearsal_readiness",
            "daily_check",
            "live_cutover",
            "goal_progress",
            "completion_audit",
            "action_time_required_facts_matrix",
        ],
    }
    state["readiness_separation"] = (
        readiness_separation_from_runtime_safety_state(state).as_read_model()
    )
    if candidate_authorization_state:
        state["candidate_authorization_state"] = candidate_authorization_state
        state["source_sections"].append("candidate_authorization_state")
    return state


def _action_time_required_facts_behavior_evidence(
    *,
    status: str,
    pre_live_ready: bool,
    fresh_signal_state: str,
    hard_fact_blockers: list[str],
    ready_for_finalgate_checkpoint: bool,
) -> dict[str, Any]:
    if status == "live_submit_standby_waiting_for_market":
        evidence_status = "facts_behavior_waiting_for_fresh_signal"
    elif ready_for_finalgate_checkpoint:
        evidence_status = "facts_behavior_ready_for_finalgate_checkpoint"
    elif hard_fact_blockers:
        evidence_status = "facts_behavior_gap_localized"
    elif not pre_live_ready:
        evidence_status = "facts_behavior_pre_live_rehearsal_missing"
    else:
        evidence_status = "facts_behavior_processing"
    return {
        "status": evidence_status,
        "trusted_submit_fact_snapshot_check": True,
        "stale_or_missing_fact_behavior": "localized_blocker_when_action_time_active",
        "submit_idempotency_policy_check": True,
        "duplicate_submit_guard_check": True,
        "protection_failure_policy_check": True,
        "missing_or_stale_facts": hard_fact_blockers,
        "strategy_uncertainty_blocks_engineering_progress": False,
        "owner_scoped_risk_acceptance_can_promote_trial_eligibility": True,
        "owner_scoped_risk_acceptance_cannot_grant_runtime_authority": True,
        "owner_scoped_risk_acceptance_can_bypass_runtime_safety_gates": False,
    }


def _execution_attempt_rehearsal_preparation(
    *,
    status: str,
    pre_live_ready: bool,
    fresh_signal_state: str,
    hard_fact_blockers: list[str],
) -> dict[str, Any]:
    if status == "live_submit_standby_waiting_for_market":
        preparation_status = "execution_attempt_rehearsal_waiting_for_fresh_signal"
    elif hard_fact_blockers:
        preparation_status = "execution_attempt_rehearsal_fact_gap_localized"
    elif pre_live_ready:
        preparation_status = "execution_attempt_rehearsal_processing"
    else:
        preparation_status = "execution_attempt_rehearsal_pre_live_missing"
    return {
        "status": preparation_status,
        "finalgate_checkpoint_input_shape_ready": True,
        "operation_layer_input_shape_evidence": _operation_layer_input_shape_evidence(),
        "submit_payload_shape_ready": True,
        "idempotency_ready": True,
        "protection_branch_ready": True,
        "reconciliation_baseline_ready": True,
        "review_ledger_shape_ready": True,
        "fresh_signal_required_for_final_acceptance": True,
        "execution_attempt_required_for_lifecycle_entry": True,
        "current_market_dependency": (
            "fresh_selected_strategygroup_signal"
            if fresh_signal_state == "none"
            else None
        ),
        "hard_fact_blockers": hard_fact_blockers,
    }


def _live_outcome_calibration_preparation() -> dict[str, Any]:
    return {
        "status": "capture_surface_ready_live_outcome_pending",
        "capture_schema_ready": True,
        "live_outcome_calibrated": False,
        "requires_real_live_outcome": True,
        "capture_fields": [
            "exchange_accept_or_reject",
            "fill_status",
            "partial_fill_quantity",
            "average_fill_price",
            "slippage",
            "fee",
            "funding",
            "protection_order_acceptance",
            "settlement_status",
            "realized_pnl",
            "reconciliation_result",
            "review_ledger_outcome",
        ],
        "final_acceptance_dependencies": [
            "real_exchange_response",
            "real_fill_or_reject",
            "real_protection_acceptance",
            "real_reconciliation_settlement",
            "realized_pnl_review",
        ],
    }


def _strategygroup_advancement_preparation() -> dict[str, Any]:
    return {
        "status": "advancement_skeleton_ready_evidence_pending",
        "advancement_engine_ready_for_evidence": True,
        "promotion_quality_final": False,
        "allowed_decisions": [
            "keep",
            "revise",
            "promote",
            "downshift",
            "park",
            "kill",
            "go_live",
            "do_not_go_live",
            "block_for_safety",
        ],
        "required_inputs": [
            "Strategy Asset State evidence",
            "replay evidence",
            "no-action attribution",
            "live outcome when available",
        ],
        "strategy_uncertainty_policy": (
            "may drive revise, downshift, park, or owner scoped trial eligibility; "
            "must not block engineering progress or grant runtime authority"
        ),
    }


def _projection_status(
    *,
    pre_live_ready: bool,
    fresh_signal_state: str,
    hard_fact_blockers: list[str],
    completion_status: str,
) -> str:
    if completion_status in {"complete", "completed"}:
        return "post_submit_settled"
    if not pre_live_ready:
        return "pre_live_rehearsal_not_ready"
    if fresh_signal_state == "none":
        return "live_submit_standby_waiting_for_market"
    if hard_fact_blockers:
        return "processing_action_time_facts_blocked"
    return "processing_ready_for_finalgate_checkpoint"


def _live_submit_ready_false_reason(
    *, fresh_signal_state: str, hard_fact_blockers: list[str]
) -> str:
    if fresh_signal_state == "none":
        return "no_fresh_signal"
    if hard_fact_blockers:
        return "action_time_required_facts_not_ready"
    return "awaiting_finalgate_and_operation_layer"


def _owner_state_for_status(
    status: str, hard_fact_blockers: list[str]
) -> dict[str, Any]:
    if status == "live_submit_standby_waiting_for_market":
        return {
            "owner_status": "waiting_for_opportunity",
            "owner_label": "等待机会",
            "automation_summary": "系统待命中",
            "intervention": "无需操作",
            "reason": "没有新的可用市场信号",
            "owner_intervention_required": False,
            "owner_manual_internal_evidence_review_required": False,
        }
    if status == "processing_ready_for_finalgate_checkpoint":
        return {
            "owner_status": "processing",
            "owner_label": "处理中",
            "automation_summary": "系统自动处理中",
            "intervention": "无需操作",
            "reason": "信号与事实检查已进入实盘链路前置阶段",
            "owner_intervention_required": False,
            "owner_manual_internal_evidence_review_required": False,
        }
    if status == "processing_action_time_facts_blocked":
        return {
            "owner_status": "temporarily_unavailable",
            "owner_label": "暂不可用",
            "automation_summary": "事实不可用",
            "intervention": "无需操作",
            "reason": ",".join(hard_fact_blockers),
            "owner_intervention_required": False,
            "owner_manual_internal_evidence_review_required": False,
        }
    if status == "post_submit_settled":
        return {
            "owner_status": "completed",
            "owner_label": "已完成",
            "automation_summary": "等待复盘",
            "intervention": "无需操作",
            "reason": "订单闭环已完成",
            "owner_intervention_required": False,
            "owner_manual_internal_evidence_review_required": False,
        }
    return {
        "owner_status": "needs_intervention",
        "owner_label": "需要介入",
        "automation_summary": "阶段状态需要处理",
        "intervention": "需要介入",
        "reason": status,
        "owner_intervention_required": True,
        "owner_manual_internal_evidence_review_required": False,
    }


def _current_checkpoint(fresh_signal_state: str) -> str:
    if fresh_signal_state == "none":
        return "waiting_for_market"
    return "action_time_required_facts"


def _default_next_step(status: str) -> str:
    if status == "live_submit_standby_waiting_for_market":
        return "continue_watcher_observation_until_fresh_signal"
    if status == "processing_ready_for_finalgate_checkpoint":
        return "run_action_time_finalgate_after_required_facts"
    if status == "processing_action_time_facts_blocked":
        return "refresh_or_repair_missing_action_time_facts"
    if status == "post_submit_settled":
        return "record_review_ledger_outcome"
    return "repair_runtime_safety_state_inputs"


def _owner_wording_for_fact(key: str, status: str) -> str:
    if status in {"pending_action_time", "waiting"}:
        return "等待机会"
    if status in {"ready", "fresh", "clear", "sufficient", "pass"}:
        return "正常"
    if key in {"account_facts", "signal_freshness"}:
        return "事实不可用"
    if key == "position_open_order_conflict":
        return "订单或持仓冲突"
    if key == "budget_coverage":
        return "预算不足"
    if key == "protection_template":
        return "保护未就绪"
    return "暂不可用"


def build_markdown(state_snapshot: dict[str, Any]) -> str:
    owner = _as_dict(state_snapshot.get("owner_state"))
    runtime_safety_state = _as_dict(state_snapshot.get("runtime_safety_state"))
    return "\n".join(
        [
            "## P0 Runtime Safety Live Submit Readiness",
            "",
            f"- Status: `{state_snapshot.get('status')}`",
            f"- Owner status: `{owner.get('owner_status')}` / {owner.get('owner_label')}",
            f"- Pre-live rehearsal ready: `{runtime_safety_state.get('pre_live_rehearsal_ready')}`",
            f"- Live submit ready: `{runtime_safety_state.get('live_submit_ready')}`",
            f"- Owner intervention: `{owner.get('owner_intervention_required')}`",
            "- Real order authority: `false`",
            "",
            "## Action-Time RequiredFacts",
            "",
            _facts_table(_dict_rows(state_snapshot.get("action_time_required_facts_matrix"))),
            "",
            "## Operation Layer Boundary",
            "",
            "- Input shape ready: `true`",
            "- FinalGate pass required before submit: `true`",
            "- Exchange write authority gated: `true`",
            "- Operation Layer called: `false`",
        ]
    ).rstrip() + "\n"


def _facts_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Fact | Status | Blocks live submit now | Owner wording |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | {} |".format(
                row.get("key"),
                row.get("status"),
                row.get("blocks_live_submit_now"),
                row.get("owner_wording"),
            )
        )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre-live-readiness-json", default=str(DEFAULT_PRE_LIVE_READINESS_JSON)
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--live-cutover-json", default=str(DEFAULT_LIVE_CUTOVER_JSON))
    parser.add_argument("--goal-progress-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument(
        "--completion-audit-json", default=str(DEFAULT_COMPLETION_AUDIT_JSON)
    )
    parser.add_argument("--fact-sources-json")
    parser.add_argument(
        "--brf2-shadow-candidate-evidence-json",
        help=(
            "Explicit BRF2 candidate evidence input. Runtime refresh callers must "
            "pass this path; omitting it keeps candidate authorization absent "
            "instead of reading a stale default artifact."
        ),
    )
    parser.add_argument(
        "--signal-status",
        choices=["none", "fresh", "processing", "expired"],
        help="Test/fixture override. Defaults to source evidence inference.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        state_snapshot = _load_json(Path(args.output_json).expanduser())
        errors = validate_state_snapshot(state_snapshot)
        result = {
            "status": "passed" if not errors else "failed",
            "error_count": len(errors),
            "errors": errors,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not errors else 2

    state_snapshot = build_runtime_safety_state(
        pre_live_readiness=_load_json(Path(args.pre_live_readiness_json).expanduser()),
        daily_check=_load_json(Path(args.daily_check_json).expanduser()),
        live_cutover=_load_json(Path(args.live_cutover_json).expanduser()),
        goal_progress=_load_json(Path(args.goal_progress_json).expanduser()),
        completion_audit=_load_json(Path(args.completion_audit_json).expanduser()),
        fact_sources=_load_json(Path(args.fact_sources_json).expanduser())
        if args.fact_sources_json
        else None,
        brf2_shadow_candidate_evidence=(
            _load_json(Path(args.brf2_shadow_candidate_evidence_json).expanduser())
            if args.brf2_shadow_candidate_evidence_json
            else None
        ),
        signal_status_override=args.signal_status,
    )
    payload = json.dumps(state_snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(Path(args.output_json).expanduser(), payload + "\n")
    _write_text(Path(args.output_owner_progress).expanduser(), build_markdown(state_snapshot))
    print(payload)
    return (
        0
        if state_snapshot["status"] != "runtime_safety_state_failed"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
