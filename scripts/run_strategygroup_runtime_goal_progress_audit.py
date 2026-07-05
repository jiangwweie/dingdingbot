#!/usr/bin/env python3
"""Summarize StrategyGroup Runtime Pilot goal progress from local evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import runtime_live_closure_evidence_verifier  # noqa: E402
from scripts import runtime_first_bounded_live_order_completion_audit  # noqa: E402
from scripts import runtime_live_cutover_readiness  # noqa: E402
from scripts.strategygroup_non_executing_projection import (  # noqa: E402
    LEGACY_AUTHORITY_MIRROR_KEYS,
    legacy_authority_mirror_present_errors,
)
try:
    from scripts.runtime_monitor_refresh import (
        DEPLOYMENT_ISSUE_STATUS,
        MONITOR_REFRESH_STATUS,
        monitor_owner_action_label_for,
        monitor_owner_state_label_for,
        monitor_notification_projection,
        owner_runtime_issues_projection,
        monitor_status_projection,
        monitor_runtime_status_for,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from runtime_monitor_refresh import (
        DEPLOYMENT_ISSUE_STATUS,
        MONITOR_REFRESH_STATUS,
        monitor_owner_action_label_for,
        monitor_owner_state_label_for,
        monitor_notification_projection,
        owner_runtime_issues_projection,
        monitor_status_projection,
        monitor_runtime_status_for,
    )

DEFAULT_BASELINE_JSON = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_GOAL_PROGRESS_JSON = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-goal-progress.md"
)
DEFAULT_P0_COMPLETION_AUDIT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_LIVE_CUTOVER_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-cutover-readiness.json"
)
DEFAULT_LIVE_CLOSURE_EVIDENCE_VERIFICATION_JSON = (
    REPO_ROOT
    / "output/strategygroup-runtime-pilot/live-closure-evidence/"
    "runtime-live-closure-evidence-verification.json"
)
DEFAULT_LIVE_CLOSURE_EVIDENCE_JSON = (
    REPO_ROOT
    / "output/strategygroup-runtime-pilot/live-closure-evidence/"
    "runtime-live-closure-evidence.json"
)
OWNER_PROGRESS_STATE_LABELS = {
    "blocked": "暂不可用",
    "complete": "已完成",
    "degraded": "非市场收口待处理",
    "processing": "处理中",
}
OWNER_PROGRESS_ACTION_LABELS = {
    "blocked": "处理目标进度阻断",
    "complete": "归档当前目标进度",
    "degraded": "处理非市场收口缺口",
    "processing": "等待系统完成收口",
}
REVIEW_PROJECTION_FORBIDDEN_EFFECT_KEYS = (
    "exchange_write_called",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "mpg_member_live_scope_expanded",
)
PORTFOLIO_PROJECTION_FORBIDDEN_EFFECT_KEYS = (
    "exchange_write_called",
    "calls_exchange_write",
    "final_gate_called",
    "calls_finalgate",
    "operation_layer_called",
    "calls_operation_layer",
    "order_created",
    "places_order",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "preview_or_replay_treated_as_live_signal",
)
TRIAL_ENVELOPE_PROJECTION_FORBIDDEN_EFFECT_KEYS = (
    *PORTFOLIO_PROJECTION_FORBIDDEN_EFFECT_KEYS,
)
DEFAULT_STRATEGYGROUP_REVIEW_ONLY_EVIDENCE_CLOSURE_WAVE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.json"
)
DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.json"
)
DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.json"
)
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.json"
)
SCHEMA = "brc.strategygroup_runtime_goal_progress_audit.v1"

P0_COMPLETION_AUDIT_REQUIRED_CHECKS = (
    "allocated_subaccount_profile_boundary_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "disabled_smoke_not_real_execution_proof",
    "expanded_watcher_scope_execution_guard_checked",
    "fresh_signal_fast_auto_chain_checked",
    "execution_attempt_rehearsal_prepare_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "operation_layer_authorization_chain_guard_checked",
    "operation_layer_blocker_review_policy_checked",
    "ticket_bound_operation_layer_handoff_checked",
    "ticket_bound_protected_submit_boundary_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "post_submit_exit_outcome_matrix_checked",
    "post_submit_finalize_result_identity_guard_checked",
    "reduce_only_recovery_standing_authorization_checked",
    "required_facts_readiness_checked",
    "scoped_pipeline_operation_layer_submit_projection_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "strategygroup_adapter_boundary_checked",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    live_cutover_readiness = _read_optional_json(
        Path(args.live_cutover_readiness_json)
    )
    if live_cutover_readiness is None and not args.no_auto_live_cutover_readiness:
        live_cutover_readiness = _build_live_cutover_readiness(
            Path(args.live_cutover_readiness_json)
        )
    live_closure_evidence_verification = _live_closure_evidence_verification(
        verification_json=Path(args.live_closure_evidence_verification_json),
        evidence_json=Path(args.live_closure_evidence_json),
    )
    report = build_goal_progress_report(
        daily_check=_read_json(Path(args.daily_check_json)),
        baseline=_read_json(Path(args.baseline_json)),
        tier_policy=_read_json(Path(args.tier_policy_json)),
        live_cutover_readiness=live_cutover_readiness,
        live_closure_evidence_verification=live_closure_evidence_verification,
        strategy_review_evidence_closure_wave=_read_optional_json(
            Path(args.strategy_review_evidence_closure_wave_json)
        ),
        strategy_review_deep_dive_wave=_read_optional_json(
            Path(args.strategy_review_deep_dive_wave_json)
        ),
        strategygroup_portfolio_board=_read_optional_json(
            Path(args.strategygroup_portfolio_board_json)
        ),
        strategygroup_capital_trial_envelope_projection=_read_optional_json(
            Path(args.strategygroup_capital_trial_envelope_projection_json)
        ),
    )
    owner_progress_text = _owner_progress_text(report)
    if args.output_json:
        output_path = Path(args.output_json)
        _write_text_atomic(
            output_path,
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    if args.output_owner_progress:
        output_path = Path(args.output_owner_progress)
        _write_text_atomic(output_path, owner_progress_text + "\n")
    if args.owner_progress:
        print(owner_progress_text)
    elif args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return (
        0
        if report["status"]
        in {"ready", "waiting_for_market", "processing", MONITOR_REFRESH_STATUS}
        else 2
    )


def _daily_check_waiting_for_market(
    *,
    daily_check: dict[str, Any],
) -> bool:
    typed_state = daily_check.get("owner_runtime_state")
    if isinstance(typed_state, dict) and typed_state:
        return typed_state.get("waiting_for_market") is True
    runtime_status = str(daily_check.get("runtime_status") or "")
    return runtime_status == "waiting_for_market"


def build_goal_progress_report(
    *,
    daily_check: dict[str, Any],
    baseline: dict[str, Any],
    tier_policy: dict[str, Any] | None = None,
    live_cutover_readiness: dict[str, Any] | None = None,
    live_closure_evidence_verification: dict[str, Any] | None = None,
    strategy_review_evidence_closure_wave: dict[str, Any] | None = None,
    strategy_review_deep_dive_wave: dict[str, Any] | None = None,
    strategygroup_portfolio_board: dict[str, Any] | None = None,
    strategygroup_capital_trial_envelope_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks = daily_check.get("checks") if isinstance(daily_check.get("checks"), dict) else {}
    owner = (
        daily_check.get("owner_summary")
        if isinstance(daily_check.get("owner_summary"), dict)
        else {}
    )
    visibility = (
        owner.get("visibility") if isinstance(owner.get("visibility"), dict) else {}
    )
    collected_interaction = (
        daily_check.get("interaction")
        if isinstance(daily_check.get("interaction"), dict)
        else {}
    )
    current_read_interaction = (
        daily_check.get("current_read_interaction")
        if isinstance(daily_check.get("current_read_interaction"), dict)
        else {}
    )
    interaction = current_read_interaction or {
        "level": "L0_local_cache_read",
        "remote_interaction_count": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_exchange_write": False,
        "places_order": False,
    }
    notification = (
        daily_check.get("notification")
        if isinstance(daily_check.get("notification"), dict)
        else {}
    )
    safety = (
        daily_check.get("safety_invariants")
        if isinstance(daily_check.get("safety_invariants"), dict)
        else {}
    )
    p0 = _p0_track(
        daily_check=daily_check,
        checks=checks,
        owner=owner,
        visibility=visibility,
    )
    signal_observation_tracks = [
        _runtime_interaction_track(
            baseline=baseline,
            interaction=interaction,
            collected_interaction=collected_interaction,
            checks=checks,
        ),
        _engineering_rehearsal_track(checks=checks, owner=owner),
        _owner_visibility_track(
            owner=owner,
            visibility=visibility,
            notification=notification,
        ),
        *(
            [
                _strategy_review_evidence_closure_track(
                    strategy_review_evidence_closure_wave
                )
            ]
            if strategy_review_evidence_closure_wave
            else []
        ),
        *(
            [_strategy_review_deep_dive_track(strategy_review_deep_dive_wave)]
            if strategy_review_deep_dive_wave
            else []
        ),
        *(
            [_strategygroup_portfolio_board_track(strategygroup_portfolio_board)]
            if strategygroup_portfolio_board
            else []
        ),
        *(
            [
                _strategygroup_capital_trial_envelope_projection_track(
                    strategygroup_capital_trial_envelope_projection
                )
            ]
            if strategygroup_capital_trial_envelope_projection
            else []
        ),
        _safety_invariants_track(safety=safety),
    ]
    issues = _dedupe(
        blocker
        for item in [p0, *signal_observation_tracks]
        for blocker in item.get("blockers", [])
    )
    hard_blockers = _dedupe(
        blocker
        for item in [p0, *signal_observation_tracks]
        if item["id"] in {"p0_live_closure", "safety_invariants_projection"}
        for blocker in item.get("blockers", [])
    )
    waiting_for_market = p0["status"] == "waiting_for_market"
    signal_observation_ready = all(item["status"] == "ready" for item in signal_observation_tracks)
    product_gaps = [item for item in issues if item not in hard_blockers]
    engineering_rehearsal_ready = next(
        (
            item["status"] == "ready"
            for item in signal_observation_tracks
            if item["id"] == "engineering_rehearsal_projection"
        ),
        False,
    )
    entry_fast_chain_boundary = _entry_fast_chain_boundary(checks=checks)
    exit_hardening_boundary = _exit_hardening_boundary(checks=checks)
    strategygroup_tier_boundary = _strategygroup_tier_boundary(
        checks=checks,
        tier_policy=tier_policy or {},
    )
    live_cutover_readiness_boundary = _live_cutover_readiness_boundary(
        live_cutover_readiness=live_cutover_readiness,
        entry_fast_chain_boundary=entry_fast_chain_boundary,
        exit_hardening_boundary=exit_hardening_boundary,
        strategygroup_tier_boundary=strategygroup_tier_boundary,
    )
    live_closure_evidence_boundary = _live_closure_evidence_boundary(
        live_closure_evidence_verification=live_closure_evidence_verification,
        checks=checks,
        waiting_for_market=waiting_for_market,
        live_cutover_readiness_boundary=live_cutover_readiness_boundary,
    )
    boundary_product_gaps = []
    if entry_fast_chain_boundary["status"] != "ready":
        boundary_product_gaps.append("entry_fast_chain_boundary_not_ready")
    if exit_hardening_boundary["status"] != "ready":
        boundary_product_gaps.append("exit_hardening_boundary_not_ready")
    if strategygroup_tier_boundary["status"] != "ready":
        boundary_product_gaps.append("strategygroup_tier_boundary_not_ready")
    if live_cutover_readiness_boundary["status"] == "blocked":
        boundary_product_gaps.extend(
            f"live_cutover_readiness:{item}"
            for item in live_cutover_readiness_boundary["non_market_blockers"]
        )
    if live_closure_evidence_boundary["status"] == "rejected":
        boundary_product_gaps.extend(
            f"live_closure_evidence:{item}"
            for item in live_closure_evidence_boundary["reject_reasons"]
        )
    if (
        checks.get("first_bounded_real_order_complete") is True
        or checks.get("real_order_closure_proven") is True
    ) and live_closure_evidence_boundary["status"] != "complete":
        boundary_product_gaps.append(
            "live_closure_completion_claim_without_verified_evidence"
        )
    product_gaps = _dedupe([*product_gaps, *boundary_product_gaps])
    preliminary_monitor_projection = monitor_status_projection(
        status=str(daily_check.get("status") or ""),
        artifacts=[daily_check],
        default_runtime_status="temporarily_unavailable",
        default_monitor_status="unknown",
    )
    monitor_status = preliminary_monitor_projection.monitor_status
    monitor_refresh_needed = preliminary_monitor_projection.monitor_refresh_needed
    status = "ready"
    processing = visibility.get("category") == "processing"
    if hard_blockers:
        status = "blocked"
    elif monitor_status == "deployment_issue":
        status = DEPLOYMENT_ISSUE_STATUS
    elif monitor_refresh_needed and waiting_for_market and signal_observation_ready:
        status = MONITOR_REFRESH_STATUS
    elif product_gaps or not signal_observation_ready:
        status = "degraded"
    elif processing and signal_observation_ready:
        status = "processing"
    elif waiting_for_market and signal_observation_ready:
        status = "waiting_for_market"
    completion_boundary = _completion_boundary(
        checks=checks,
        waiting_for_market=waiting_for_market,
        signal_observation_ready=signal_observation_ready,
        engineering_rehearsal_ready=engineering_rehearsal_ready,
        hard_blockers=hard_blockers,
        product_gaps=product_gaps,
        live_closure_evidence_boundary=live_closure_evidence_boundary,
    )
    p0_completion_audit_boundary = _p0_completion_audit_boundary(
        daily_check=daily_check,
        checks=checks,
        live_cutover_readiness=live_cutover_readiness,
        completion_boundary=completion_boundary,
        live_closure_evidence_boundary=live_closure_evidence_boundary,
    )
    if p0_completion_audit_boundary["status"] == "needs_non_market_repair":
        product_gaps = _dedupe(
            [
                *product_gaps,
                *[
                    f"p0_completion_audit:{item}"
                    for item in p0_completion_audit_boundary["non_market_gap_keys"]
                ],
            ]
        )
        completion_boundary = _completion_boundary(
            checks=checks,
            waiting_for_market=waiting_for_market,
            signal_observation_ready=signal_observation_ready,
            engineering_rehearsal_ready=engineering_rehearsal_ready,
            hard_blockers=hard_blockers,
            product_gaps=product_gaps,
            live_closure_evidence_boundary=live_closure_evidence_boundary,
        )
        p0_completion_audit_boundary = _p0_completion_audit_boundary(
            daily_check=daily_check,
            checks=checks,
            live_cutover_readiness=live_cutover_readiness,
            completion_boundary=completion_boundary,
            live_closure_evidence_boundary=live_closure_evidence_boundary,
        )
        if not hard_blockers and (product_gaps or not signal_observation_ready):
            status = "degraded"

    runtime_status = monitor_runtime_status_for(
        status=status,
        waiting_for_market=waiting_for_market,
    )
    monitor_projection = monitor_status_projection(
        status=status,
        artifacts=[daily_check],
        runtime_status=runtime_status,
        owner_intervention_required=bool(hard_blockers),
        waiting_for_market=waiting_for_market,
    )
    monitor_status = monitor_projection.monitor_status
    owner_status = monitor_projection.owner_status
    owner_runtime_state = monitor_projection.owner_runtime_state
    monitor_refresh_needed = monitor_projection.monitor_refresh_needed
    monitor_refresh_reasons = monitor_projection.monitor_refresh_reasons
    owner_runtime_issues = owner_runtime_issues_projection(
        blockers=hard_blockers,
        non_market_gaps=product_gaps,
        include_counts=True,
        gap_key="product_gaps",
        gap_count_key="product_gap_count",
    )
    signal_observation = {
        "grade_code": "signal-observation-grade-review",
        "ready": signal_observation_ready,
        "state": "ready" if signal_observation_ready else "needs_work",
    }
    notification_projection = monitor_notification_projection(
        monitor_refresh_needed=monitor_refresh_needed,
        owner_notify=bool(hard_blockers),
        owner_intervention_required=bool(
            notification.get("owner_intervention_required")
        ),
        source_notification=notification,
        source_prefix="daily_check",
    )
    capital_trial_boundary = _strategygroup_capital_trial_envelope_projection_boundary(
        strategygroup_capital_trial_envelope_projection
    )

    return {
        "schema": SCHEMA,
        "status": status,
        "runtime_status": runtime_status,
        "monitor_status": monitor_status,
        "owner_status": owner_status,
        "owner_runtime_state": owner_runtime_state,
        "owner_runtime_issues": owner_runtime_issues,
        "signal_observation": signal_observation,
        "notification": notification_projection,
        "scope": "strategygroup_runtime_goal_progress_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": {
            "level": "L0_local_goal_progress_audit",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": monitor_owner_state_label_for(
                status,
                local_labels=OWNER_PROGRESS_STATE_LABELS,
                default_label="暂不可用",
            ),
            "non_authority_checkpoint": monitor_owner_action_label_for(
                status,
                local_labels=OWNER_PROGRESS_ACTION_LABELS,
                default_label="刷新或修复 runtime monitor 权威状态",
            ),
            "checkpoint_source": "goal_progress_status_projection",
            "owner_intervention_required": bool(hard_blockers),
            "risk_level": "L0 local audit",
            "p0": p0["status"],
            "signal_observation_state": (
                "ready" if signal_observation_ready else "needs_work"
            ),
            "strategy_portfolio": (
                "portfolio_screening_active"
                if strategygroup_portfolio_board
                and _strategygroup_portfolio_board_boundary(
                    strategygroup_portfolio_board
                )["status"]
                == "portfolio_board_ready"
                else "not_generated"
            ),
            "capital_trial": (
                capital_trial_boundary["selected_candidate_status"]
                if capital_trial_boundary["projection_status"]
                == "trial_envelope_projection_ready"
                else "not_generated"
            ),
        },
        "completion_boundary": completion_boundary,
        "entry_fast_chain_boundary": entry_fast_chain_boundary,
        "exit_hardening_boundary": exit_hardening_boundary,
        "strategygroup_tier_boundary": strategygroup_tier_boundary,
        "live_cutover_readiness_boundary": live_cutover_readiness_boundary,
        "live_closure_evidence_boundary": live_closure_evidence_boundary,
        "strategy_review_evidence_closure_boundary": (
            _strategy_review_evidence_closure_boundary(
                strategy_review_evidence_closure_wave
            )
        ),
        "strategy_review_deep_dive_boundary": (
            _strategy_review_deep_dive_boundary(strategy_review_deep_dive_wave)
        ),
        "strategygroup_portfolio_board_boundary": (
            _strategygroup_portfolio_board_boundary(strategygroup_portfolio_board)
        ),
        "strategygroup_capital_trial_envelope_projection_boundary": capital_trial_boundary,
        "p0_completion_audit_boundary": p0_completion_audit_boundary,
        "tracks": [p0, *signal_observation_tracks],
        "source_paths": {
            "daily_check_json": str(DEFAULT_DAILY_CHECK_JSON),
            "baseline_json": str(DEFAULT_BASELINE_JSON),
            "tier_policy_json": str(DEFAULT_TIER_POLICY_JSON),
            "live_cutover_readiness_json": str(DEFAULT_LIVE_CUTOVER_READINESS_JSON),
            "live_closure_evidence_verification_json": str(
                DEFAULT_LIVE_CLOSURE_EVIDENCE_VERIFICATION_JSON
            ),
            "live_closure_evidence_json": str(DEFAULT_LIVE_CLOSURE_EVIDENCE_JSON),
            "strategy_review_evidence_closure_wave_json": str(
                DEFAULT_STRATEGYGROUP_REVIEW_ONLY_EVIDENCE_CLOSURE_WAVE_JSON
            ),
            "strategy_review_deep_dive_wave_json": str(
                DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON
            ),
            "strategygroup_portfolio_board_json": str(
                DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON
            ),
            "strategygroup_capital_trial_envelope_projection_json": str(
                DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON
            ),
            "goal_progress_json": str(DEFAULT_GOAL_PROGRESS_JSON),
            "goal_progress_owner_progress_md": str(
                DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD
            ),
            "p0_completion_audit_json": str(DEFAULT_P0_COMPLETION_AUDIT_JSON),
        },
    }


def _entry_fast_chain_boundary(*, checks: dict[str, Any]) -> dict[str, Any]:
    fast_chain_checks = {
        "fresh_signal_fast_auto_chain_checked": _dry_run_required_check_present(
            checks,
            "fresh_signal_fast_auto_chain_checked",
        ),
        "required_facts_readiness_checked": _dry_run_required_check_present(
            checks,
            "required_facts_readiness_checked",
        ),
        "selected_strategygroup_dispatch_guard_checked": (
            _dry_run_required_check_present(
                checks,
                "selected_strategygroup_dispatch_guard_checked",
            )
        ),
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": (
            _dry_run_required_check_present(
                checks,
                "all_selected_strategygroups_reach_finalgate_dispatch_checked",
            )
        ),
        "ticket_bound_operation_layer_handoff_checked": _dry_run_required_check_present(
            checks,
            "ticket_bound_operation_layer_handoff_checked",
        ),
        "scoped_pipeline_operation_layer_submit_projection_checked": (
            _dry_run_required_check_present(
                checks,
                "scoped_pipeline_operation_layer_submit_projection_checked",
            )
        ),
        "operation_layer_authorization_chain_guard_checked": (
            _dry_run_required_check_present(
                checks,
                "operation_layer_authorization_chain_guard_checked",
            )
        ),
        "ticket_bound_protected_submit_boundary_checked": (
            _dry_run_required_check_present(
                checks,
                "ticket_bound_protected_submit_boundary_checked",
            )
        ),
        "operation_layer_blocker_review_policy_checked": (
            _dry_run_required_check_present(
                checks,
                "operation_layer_blocker_review_policy_checked",
            )
        ),
    }
    status = "ready" if all(fast_chain_checks.values()) else "needs_work"
    return {
        "status": status,
        "checks": fast_chain_checks,
        "fresh_signal_to_candidate_authorization_covered": fast_chain_checks[
            "fresh_signal_fast_auto_chain_checked"
        ],
        "required_facts_gate_covered": fast_chain_checks[
            "required_facts_readiness_checked"
        ],
        "candidate_authorization_to_finalgate_covered": (
            fast_chain_checks[
                "all_selected_strategygroups_reach_finalgate_dispatch_checked"
            ]
            and fast_chain_checks["selected_strategygroup_dispatch_guard_checked"]
        ),
        "finalgate_to_ticket_bound_operation_layer_handoff_covered": (
            fast_chain_checks["ticket_bound_operation_layer_handoff_checked"]
            and fast_chain_checks["scoped_pipeline_operation_layer_submit_projection_checked"]
        ),
        "operation_layer_authorization_guard_covered": fast_chain_checks[
            "operation_layer_authorization_chain_guard_checked"
        ]
        and fast_chain_checks["ticket_bound_protected_submit_boundary_checked"],
        "operation_layer_blocker_review_policy_covered": fast_chain_checks[
            "operation_layer_blocker_review_policy_checked"
        ],
        "real_action_time_finalgate_proven": (
            checks.get("real_action_time_finalgate_proven") is True
        ),
        "real_operation_layer_submit_proven": (
            checks.get("real_operation_layer_submit_proven") is True
        ),
        "real_order_dependent_remaining": not (
            checks.get("real_action_time_finalgate_proven") is True
            and checks.get("real_operation_layer_submit_proven") is True
        ),
    }


def _strategygroup_tier_boundary(
    *,
    checks: dict[str, Any],
    tier_policy: dict[str, Any],
) -> dict[str, Any]:
    tier_policy_checked = _dry_run_required_check_present(
        checks,
        "runtime_tier_policy_checked",
    )
    only_mpg_l4_checked = _dry_run_required_check_present(
        checks,
        "only_mpg_tiny_real_order_eligible_checked",
    )
    new_defaults_checked = _dry_run_required_check_present(
        checks,
        "new_strategygroups_default_observe_only_checked",
    )
    adapter_boundary_checked = _dry_run_required_check_present(
        checks,
        "strategygroup_adapter_boundary_checked",
    )
    allocated_subaccount_boundary_checked = _dry_run_required_check_present(
        checks,
        "allocated_subaccount_profile_boundary_checked",
    )
    selected_dispatch_checked = _dry_run_required_check_present(
        checks,
        "selected_strategygroup_dispatch_guard_checked",
    )
    all_selected_finalgate_checked = _dry_run_required_check_present(
        checks,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    )
    current_strategy_group_tiers = _current_strategy_group_tiers(tier_policy)
    new_strategy_group_default_tiers = _new_strategy_group_default_tiers(tier_policy)
    l4_strategy_groups = [
        strategy_group_id
        for strategy_group_id, tier in current_strategy_group_tiers.items()
        if tier == "L4"
    ]
    checks_passed = {
        "runtime_tier_policy_checked": tier_policy_checked,
        "only_mpg_tiny_real_order_eligible_checked": only_mpg_l4_checked,
        "new_strategygroups_default_observe_only_checked": new_defaults_checked,
        "strategygroup_adapter_boundary_checked": adapter_boundary_checked,
        "allocated_subaccount_profile_boundary_checked": (
            allocated_subaccount_boundary_checked
        ),
        "selected_strategygroup_dispatch_guard_checked": selected_dispatch_checked,
        "all_selected_strategygroups_reach_finalgate_dispatch_checked": (
            all_selected_finalgate_checked
        ),
        "tier_policy_source_readable": bool(current_strategy_group_tiers),
    }
    return {
        "status": "ready" if all(checks_passed.values()) else "needs_work",
        "checks": checks_passed,
        "current_strategy_group_tiers": current_strategy_group_tiers,
        "l4_strategy_groups": l4_strategy_groups if only_mpg_l4_checked else [],
        "first_live_lane_strategy_group": (
            l4_strategy_groups[0]
            if only_mpg_l4_checked and len(l4_strategy_groups) == 1
            else None
        ),
        "non_l4_strategy_groups": [
            strategy_group_id
            for strategy_group_id, tier in current_strategy_group_tiers.items()
            if tier != "L4"
        ],
        "new_strategy_group_default_tiers": new_strategy_group_default_tiers,
        "new_strategy_groups_default_non_l4": new_defaults_checked,
        "tier_policy_is_execution_authority": not bool(
            tier_policy.get("not_execution_authority")
        ),
        "tier_policy_bypasses_finalgate": not bool(
            tier_policy.get("not_finalgate_input")
        ),
        "tier_policy_bypasses_operation_layer": not bool(
            tier_policy.get("not_operation_layer_input")
        ),
        "strategygroups_define_custom_execution_pipeline": not bool(
            (tier_policy.get("safety_invariants") or {}).get(
                "no_strategy_group_directly_defines_candidate_pipeline"
            )
            and (tier_policy.get("safety_invariants") or {}).get(
                "no_strategy_group_directly_defines_finalgate"
            )
            and (tier_policy.get("safety_invariants") or {}).get(
                "no_strategy_group_directly_defines_operation_layer"
            )
        ),
    }


def _current_strategy_group_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    current = tier_policy.get("current_strategy_groups")
    if not isinstance(current, dict):
        return {}
    tiers: dict[str, str] = {}
    for strategy_group_id, payload in current.items():
        if not isinstance(payload, dict):
            continue
        tier = payload.get("tier")
        if isinstance(tier, str) and tier:
            tiers[str(strategy_group_id)] = tier
    return tiers


def _new_strategy_group_default_tiers(tier_policy: dict[str, Any]) -> dict[str, str]:
    defaults = tier_policy.get("new_strategy_group_defaults")
    if not isinstance(defaults, dict):
        return {}
    known = defaults.get("known_new_groups")
    if not isinstance(known, dict):
        return {}
    return {
        str(strategy_group_id): str(tier)
        for strategy_group_id, tier in known.items()
        if str(strategy_group_id) and str(tier)
    }


def _exit_hardening_boundary(*, checks: dict[str, Any]) -> dict[str, Any]:
    matrix_checked = _dry_run_required_check_present(
        checks,
        "post_submit_exit_outcome_matrix_checked",
    )
    standing_recovery_checked = _dry_run_required_check_present(
        checks,
        "reduce_only_recovery_standing_authorization_checked",
    )
    ready = matrix_checked and standing_recovery_checked
    return {
        "status": "ready" if ready else "needs_work",
        "post_submit_exit_outcome_matrix_checked": matrix_checked,
        "reduce_only_recovery_standing_authorization_checked": (
            standing_recovery_checked
        ),
        "exchange_native_hard_stop_required_after_entry": matrix_checked,
        "entry_filled_protection_ok_covered": matrix_checked,
        "entry_filled_protection_failed_reduce_only_recovery_covered": ready,
        "partial_fill_policy_covered": matrix_checked,
        "exchange_submit_failed_before_acceptance_policy_covered": matrix_checked,
        "active_position_remains_open_policy_covered": matrix_checked,
        "position_closed_by_sl_tp_or_reduce_only_recovery_covered": matrix_checked,
        "real_post_submit_close_reconcile_settle_proven": (
            checks.get("real_post_submit_close_reconcile_settle_proven") is True
        ),
        "real_order_dependent_remaining": (
            checks.get("real_post_submit_close_reconcile_settle_proven") is not True
        ),
    }


def _live_cutover_readiness_boundary(
    *,
    live_cutover_readiness: dict[str, Any] | None,
    entry_fast_chain_boundary: dict[str, Any],
    exit_hardening_boundary: dict[str, Any],
    strategygroup_tier_boundary: dict[str, Any],
) -> dict[str, Any]:
    if not live_cutover_readiness:
        return {
            "status": "not_generated",
            "owner_state": "未生成",
            "next_fresh_signal_cutover_ready": False,
            "current_real_submit_allowed": False,
            "non_market_blockers": [],
            "market_dependent_waiting_keys": [],
            "source_status": None,
            "entry_fast_chain_ready": entry_fast_chain_boundary["status"] == "ready",
            "exit_hardening_ready": exit_hardening_boundary["status"] == "ready",
            "strategygroup_tier_ready": strategygroup_tier_boundary["status"]
            == "ready",
            "live_closure_cutover_contract_ready": False,
            "live_closure_required_stage_count": 0,
            "live_closure_required_evidence_keys": [],
        }
    blockers = [str(item) for item in live_cutover_readiness.get("non_market_blockers") or []]
    source_status = str(live_cutover_readiness.get("status") or "")
    contract = live_cutover_readiness.get("live_closure_cutover_contract")
    if not isinstance(contract, dict):
        contract = {}
    contract_checks = contract.get("checks")
    if not isinstance(contract_checks, dict):
        contract_checks = {}
    contract_ready = (
        contract.get("status") == "ready"
        and bool(contract_checks)
        and all(value is True for value in contract_checks.values())
    )
    if not contract_ready:
        blockers.append("live_closure_cutover_contract:missing_or_not_ready")
    ready = (
        source_status == "live_cutover_waiting_for_fresh_signal"
        and not blockers
        and live_cutover_readiness.get("next_fresh_signal_cutover_ready") is True
        and live_cutover_readiness.get("current_real_submit_allowed") is False
    )
    return {
        "status": "ready" if ready else "blocked",
        "owner_state": str(live_cutover_readiness.get("owner_state") or ""),
        "next_fresh_signal_cutover_ready": bool(
            live_cutover_readiness.get("next_fresh_signal_cutover_ready")
        ),
        "current_real_submit_allowed": bool(
            live_cutover_readiness.get("current_real_submit_allowed")
        ),
        "non_market_blockers": blockers,
        "market_dependent_waiting_keys": [
            str(item)
            for item in live_cutover_readiness.get("market_dependent_waiting_keys")
            or []
        ],
        "source_status": source_status,
        "entry_fast_chain_ready": entry_fast_chain_boundary["status"] == "ready",
        "exit_hardening_ready": exit_hardening_boundary["status"] == "ready",
        "strategygroup_tier_ready": strategygroup_tier_boundary["status"] == "ready",
        "live_closure_cutover_contract_ready": contract_ready,
        "live_closure_required_stage_count": int(contract.get("stage_count") or 0),
        "live_closure_required_evidence_keys": [
            str(item) for item in contract.get("required_evidence_keys") or []
        ],
    }


def _live_closure_evidence_verification(
    *,
    verification_json: Path,
    evidence_json: Path,
) -> dict[str, Any] | None:
    verification = _read_optional_json(verification_json)
    if verification is not None:
        return verification
    evidence = _read_optional_json(evidence_json)
    if evidence is None:
        return None
    return runtime_live_closure_evidence_verifier.build_live_closure_evidence_verification(
        evidence
    )


def _live_closure_evidence_boundary(
    *,
    live_closure_evidence_verification: dict[str, Any] | None,
    checks: dict[str, Any],
    waiting_for_market: bool,
    live_cutover_readiness_boundary: dict[str, Any],
) -> dict[str, Any]:
    expected_stage_count = int(
        live_cutover_readiness_boundary.get("live_closure_required_stage_count") or 0
    )
    expected_evidence_keys = [
        str(item)
        for item in live_cutover_readiness_boundary.get(
            "live_closure_required_evidence_keys"
        )
        or []
    ]
    market_waiting_keys = [
        str(item)
        for item in live_cutover_readiness_boundary.get(
            "market_dependent_waiting_keys"
        )
        or []
    ]
    if not live_closure_evidence_verification:
        source_status = str(
            checks.get("runtime_live_closure_evidence_status") or "not_generated"
        )
        reject_reasons = [
            str(item)
            for item in checks.get("runtime_live_closure_evidence_reject_reasons")
            or []
        ]
        real_order_readiness = checks.get("real_order_readiness_summary")
        if not isinstance(real_order_readiness, dict):
            real_order_readiness = {}
        real_order_waiting_keys = {
            str(item) for item in real_order_readiness.get("waiting_keys") or []
        }
        no_signal_waiting = (
            waiting_for_market
            and "fresh_signal" in real_order_waiting_keys
        )
        if source_status in {"live_closure_in_progress", "in_progress"}:
            if no_signal_waiting:
                return {
                    "status": "not_generated",
                    "source_status": "no_live_closure_evidence",
                    "raw_source_status": source_status,
                    "normalization_reason": "waiting_for_market_no_fresh_signal",
                    "owner_state": "未生成",
                    "first_bounded_real_order_complete": False,
                    "real_order_closure_proven": False,
                    "completed_stage_count": 0,
                    "stage_count": expected_stage_count,
                    "expected_stage_count": expected_stage_count,
                    "first_incomplete_stage": (
                        market_waiting_keys[0]
                        if market_waiting_keys
                        else "fresh_signal"
                    ),
                    "expected_evidence_keys": expected_evidence_keys,
                    "market_dependent_waiting_keys": market_waiting_keys,
                    "missing_evidence_keys": [],
                    "reject_reasons": [],
                }
            return {
                "status": "in_progress",
                "source_status": source_status,
                "raw_source_status": source_status,
                "normalization_reason": None,
                "owner_state": "处理中",
                "first_bounded_real_order_complete": False,
                "real_order_closure_proven": False,
                "completed_stage_count": 0,
                "stage_count": expected_stage_count,
                "expected_stage_count": expected_stage_count,
                "first_incomplete_stage": None,
                "expected_evidence_keys": expected_evidence_keys,
                "market_dependent_waiting_keys": market_waiting_keys,
                "missing_evidence_keys": [],
                "reject_reasons": [],
            }
        if source_status in {"blocked_live_closure_rejected", "rejected"}:
            return {
                "status": "rejected",
                "source_status": source_status,
                "raw_source_status": source_status,
                "normalization_reason": None,
                "owner_state": "工程状态暂不可用",
                "first_bounded_real_order_complete": False,
                "real_order_closure_proven": False,
                "completed_stage_count": 0,
                "stage_count": expected_stage_count,
                "expected_stage_count": expected_stage_count,
                "first_incomplete_stage": None,
                "expected_evidence_keys": expected_evidence_keys,
                "market_dependent_waiting_keys": market_waiting_keys,
                "missing_evidence_keys": [],
                "reject_reasons": reject_reasons or ["rejected"],
            }
        return {
            "status": "not_generated",
            "source_status": source_status,
            "raw_source_status": source_status,
            "normalization_reason": None,
            "owner_state": "未生成",
            "first_bounded_real_order_complete": False,
            "real_order_closure_proven": False,
            "completed_stage_count": 0,
            "stage_count": expected_stage_count,
            "expected_stage_count": expected_stage_count,
            "first_incomplete_stage": None,
            "expected_evidence_keys": expected_evidence_keys,
            "market_dependent_waiting_keys": market_waiting_keys,
            "missing_evidence_keys": [],
            "reject_reasons": [],
        }
    source_status = str(live_closure_evidence_verification.get("status") or "")
    completion = live_closure_evidence_verification.get("completion")
    if not isinstance(completion, dict):
        completion = {}
    if source_status == "blocked_live_closure_rejected":
        status = "rejected"
    elif source_status == "live_closure_complete":
        status = "complete"
    elif source_status in {"live_closure_in_progress", "live_closure_not_started"}:
        status = "in_progress"
    else:
        status = "needs_work"
    return {
        "status": status,
        "source_status": source_status,
        "raw_source_status": source_status,
        "normalization_reason": None,
        "owner_state": str(live_closure_evidence_verification.get("owner_state") or ""),
        "first_bounded_real_order_complete": (
            completion.get("first_bounded_real_order_complete") is True
        ),
        "real_order_closure_proven": (
            completion.get("real_order_closure_proven") is True
        ),
        "completed_stage_count": int(
            live_closure_evidence_verification.get("completed_stage_count") or 0
        ),
        "stage_count": int(live_closure_evidence_verification.get("stage_count") or 0),
        "expected_stage_count": expected_stage_count,
        "first_incomplete_stage": live_closure_evidence_verification.get(
            "first_incomplete_stage"
        ),
        "expected_evidence_keys": expected_evidence_keys,
        "market_dependent_waiting_keys": market_waiting_keys,
        "missing_evidence_keys": [
            str(item)
            for item in live_closure_evidence_verification.get("missing_evidence_keys")
            or []
        ],
        "reject_reasons": [
            str(item)
            for item in live_closure_evidence_verification.get("reject_reasons") or []
        ],
    }


def _p0_completion_audit_boundary(
    *,
    daily_check: dict[str, Any],
    checks: dict[str, Any],
    live_cutover_readiness: dict[str, Any] | None,
    completion_boundary: dict[str, Any],
    live_closure_evidence_boundary: dict[str, Any],
) -> dict[str, Any]:
    if not live_cutover_readiness:
        return {
            "status": "not_generated",
            "goal_complete": bool(completion_boundary.get("goal_complete")),
            "non_market_gap_count": 0,
            "non_market_gap_keys": [],
            "market_dependent_remaining": [],
            "market_dependent_remaining_count": 0,
            "source_status": None,
        }
    has_full_audit_inputs = (
        bool(live_cutover_readiness.get("selected_strategy_group_id"))
        and bool(live_cutover_readiness.get("first_live_lane"))
        and isinstance(live_cutover_readiness.get("check_groups"), list)
    )
    if not has_full_audit_inputs:
        return {
            "status": "not_generated_legacy_cutover_artifact",
            "goal_complete": bool(completion_boundary.get("goal_complete")),
            "non_market_gap_count": 0,
            "non_market_gap_keys": [],
            "market_dependent_remaining": [],
            "market_dependent_remaining_count": 0,
            "source_status": str(live_cutover_readiness.get("status") or ""),
        }
    audit_checks = dict(checks)
    for check_name in P0_COMPLETION_AUDIT_REQUIRED_CHECKS:
        audit_checks.setdefault(
            check_name,
            _dry_run_required_check_present(checks, check_name),
        )
    audit = runtime_first_bounded_live_order_completion_audit.build_completion_audit_report(
        daily_check=daily_check,
        goal_progress={
            "interaction": {
                "level": "L0_local_goal_progress_audit",
                "remote_interaction_count": 0,
            },
            "completion_boundary": completion_boundary,
            "live_closure_evidence_boundary": live_closure_evidence_boundary,
        },
        dry_run_audit={
            "checks": audit_checks,
            "summary": audit_checks,
        },
        live_cutover=live_cutover_readiness,
    )
    non_market_gaps = [
        item for item in audit.get("non_market_gaps") or [] if isinstance(item, dict)
    ]
    non_market_gap_keys = [
        f"{gap.get('requirement')}:{item}"
        for gap in non_market_gaps
        for item in gap.get("missing_or_false") or []
    ]
    market_dependent_remaining = [
        str(item) for item in audit.get("market_dependent_remaining") or []
    ]
    return {
        "status": str(audit.get("status") or "unknown"),
        "goal_complete": bool(audit.get("goal_complete")),
        "non_market_gap_count": len(non_market_gaps),
        "non_market_gap_keys": non_market_gap_keys,
        "market_dependent_remaining": market_dependent_remaining,
        "market_dependent_remaining_count": len(market_dependent_remaining),
        "source_status": str(live_cutover_readiness.get("status") or ""),
    }


def _dry_run_required_check_present(checks: dict[str, Any], name: str) -> bool:
    if checks.get(name) is not None:
        return checks.get(name) is True
    if checks.get("runtime_dry_run_audit_passed") is not True:
        return False
    missing = [str(item) for item in checks.get("runtime_dry_run_missing_required_checks") or []]
    if checks.get("runtime_dry_run_required_checks_present") is False:
        return False
    return name not in missing


def _completion_boundary(
    *,
    checks: dict[str, Any],
    waiting_for_market: bool,
    signal_observation_ready: bool,
    engineering_rehearsal_ready: bool,
    hard_blockers: list[str],
    product_gaps: list[str],
    live_closure_evidence_boundary: dict[str, Any],
) -> dict[str, Any]:
    first_bounded_real_order_complete = (
        live_closure_evidence_boundary["status"] == "complete"
        and live_closure_evidence_boundary["first_bounded_real_order_complete"]
    )
    real_order_closure_proven = (
        live_closure_evidence_boundary["status"] == "complete"
        and live_closure_evidence_boundary["real_order_closure_proven"]
    )
    live_closure_in_progress = live_closure_evidence_boundary["status"] == "in_progress"
    goal_complete = (
        first_bounded_real_order_complete
        and real_order_closure_proven
        and not hard_blockers
        and not product_gaps
    )
    waiting_for_real_fresh_signal = (
        waiting_for_market and signal_observation_ready and not hard_blockers and not product_gaps
    )
    if goal_complete:
        status = "complete"
        blocker_class = "none"
        reason = "first_bounded_real_order_closed"
    elif waiting_for_real_fresh_signal:
        status = "not_complete_waiting_for_market"
        blocker_class = "waiting_for_market"
        reason = "waiting_for_real_fresh_selected_strategygroup_signal"
    elif hard_blockers:
        status = "not_complete_hard_safety_stop"
        blocker_class = "hard_safety_stop"
        reason = "hard_safety_blocker_present"
    elif product_gaps:
        status = "not_complete_product_gap"
        blocker_class = "missing_fact"
        reason = "non_market_product_gap_present"
    elif live_closure_in_progress:
        status = "not_complete_runtime_processing"
        blocker_class = "runtime_processing"
        reason = "first_bounded_live_order_closure_in_progress"
    else:
        status = "not_complete_runtime_processing"
        blocker_class = "runtime_processing"
        reason = "runtime_chain_not_settled"
    return {
        "goal_complete": goal_complete,
        "status": status,
        "reason": reason,
        "completion_blocker_class": blocker_class,
        "first_bounded_real_order_complete": first_bounded_real_order_complete,
        "real_order_closure_proven": real_order_closure_proven,
        "waiting_for_real_fresh_signal": waiting_for_real_fresh_signal,
        "dry_run_readiness_proven": engineering_rehearsal_ready,
        "mock_signal_treated_as_real_signal": False,
        "disabled_smoke_treated_as_real_execution_proof": False,
        "live_closure_evidence_status": live_closure_evidence_boundary["status"],
    }


def _p0_track(
    *,
    daily_check: dict[str, Any],
    checks: dict[str, Any],
    owner: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    blockers = _p0_action_blockers(checks)
    waiting = _daily_check_waiting_for_market(
        daily_check=daily_check,
    )
    processing = visibility.get("category") == "processing"
    if blockers:
        status = "blocked"
        owner_state = "安全或工程阻断"
        progress_checkpoint = "先处理阻断，不进入真实订单路径"
    elif waiting:
        status = "waiting_for_market"
        owner_state = "等待市场机会"
        progress_checkpoint = "等待 fresh signal 后推进官方链路"
    elif processing:
        status = "processing"
        owner_state = str(owner.get("state") or visibility.get("label") or "处理中")
        progress_checkpoint = "等待系统完成收口"
    else:
        status = "ready"
        source_owner_state = str(owner.get("state") or visibility.get("label") or "")
        owner_state = source_owner_state or "暂不可用"
        progress_checkpoint = (
            "fresh signal 已出现时推进官方链路"
            if source_owner_state
            else "刷新或修复 runtime monitor 权威状态"
        )
    return {
        "id": "p0_live_closure",
        "label": "P0 第一笔边界内真实订单闭环",
        "status": status,
        "owner_state": owner_state,
        "progress_checkpoint": progress_checkpoint,
        "evidence": [
            f"daily_check_status={daily_check.get('status')}",
            f"derived_waiting_for_market={waiting}",
        ],
        "blockers": blockers,
    }


def _p0_action_blockers(checks: dict[str, Any]) -> list[str]:
    blockers = [str(item) for item in checks.get("blockers") or []]
    if checks.get("deployment_issue") is not True:
        return blockers
    deployment_tokens = {
        "runtime_head_mismatch",
        "runtime_goal_status_deployment_not_aligned",
    }
    return [
        blocker
        for blocker in blockers
        if blocker not in deployment_tokens and blocker != "l1_snapshot_blocked"
    ]


def _runtime_interaction_track(
    *,
    baseline: dict[str, Any],
    interaction: dict[str, Any],
    collected_interaction: dict[str, Any],
    checks: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    required_keys = [
        "server_side_runtime_monitor_check",
        "server_side_runtime_monitor_service",
        "server_side_runtime_monitor_timer",
    ]
    missing = [key for key in required_keys if not baseline.get(key)]
    if missing:
        blockers.append("runtime_monitor_baseline_missing:" + ",".join(missing))
    if int(interaction.get("remote_interaction_count") or 0) != 0:
        blockers.append("local_goal_progress_expected_zero_remote_interaction")
    if interaction.get("mutates_remote_files") is True:
        blockers.append("local_goal_progress_mutated_remote")
    if checks.get("blockers"):
        blockers.append("daily_check_has_blockers")
    return _track(
        track_id="runtime_interaction_projection",
        label="Runtime Interaction Projection",
        blockers=blockers,
        evidence=[
            f"interaction={interaction.get('level')}",
            f"remote_interaction_count={interaction.get('remote_interaction_count', 0)}",
            f"collected_interaction={collected_interaction.get('level')}",
            f"collected_remote_interaction_count={collected_interaction.get('remote_interaction_count', 0)}",
            "server_side_monitor_baseline=present"
            if not missing
            else "server_side_monitor_baseline=missing",
        ],
        progress_checkpoint="生产监控由 Tokyo server-side readonly timer 负责",
    )


def _engineering_rehearsal_track(
    *,
    checks: dict[str, Any],
    owner: dict[str, Any],
) -> dict[str, Any]:
    progress = owner.get("progress") if isinstance(owner.get("progress"), dict) else {}
    blockers: list[str] = []
    if checks.get("runtime_dry_run_audit_passed") is not True:
        blockers.append("runtime_dry_run_audit_not_passed")
    if checks.get("runtime_dry_run_required_checks_present") is not True:
        blockers.append("runtime_dry_run_required_checks_missing")
    missing = [
        str(item) for item in checks.get("runtime_dry_run_missing_required_checks") or []
    ]
    missing_chain_segments = [
        str(item)
        for item in checks.get(
            "runtime_execution_chain_missing_or_failed_segments"
        )
        or []
    ]
    missing_goal_chain_segments = [
        str(item)
        for item in checks.get(
            "runtime_execution_goal_chain_missing_or_failed_segments"
        )
        or []
    ]
    blockers.extend(f"missing_dry_run_check:{item}" for item in missing)
    blockers.extend(f"missing_chain_segment:{item}" for item in missing_chain_segments)
    blockers.extend(
        f"missing_goal_chain_segment:{item}"
        for item in missing_goal_chain_segments
    )
    ready_segment_count = checks.get("runtime_execution_chain_ready_segment_count")
    ready_segment_text = (
        str(ready_segment_count) if ready_segment_count is not None else "unknown"
    )
    ready_goal_segment_count = checks.get(
        "runtime_execution_goal_chain_ready_segment_count"
    )
    ready_goal_segment_text = (
        str(ready_goal_segment_count)
        if ready_goal_segment_count is not None
        else "unknown"
    )
    return _track(
        track_id="engineering_rehearsal_projection",
        label="Engineering Rehearsal Projection",
        blockers=blockers,
        evidence=[
            f"dry_run_audit={progress.get('dry_run_audit')}",
            f"scenario_count={checks.get('runtime_dry_run_scenario_count')}",
            f"chain_ready_segments={ready_segment_text}",
            f"missing_chain_segments={len(missing_chain_segments)}",
            f"goal_chain_ready_segments={ready_goal_segment_text}",
            f"missing_goal_chain_segments={len(missing_goal_chain_segments)}",
        ],
        progress_checkpoint="保持 dry-run / mock signal / source readiness 日检",
    )


def _owner_visibility_track(
    *,
    owner: dict[str, Any],
    visibility: dict[str, Any],
    notification: dict[str, Any],
) -> dict[str, Any]:
    category = str(visibility.get("category") or "")
    blockers: list[str] = []
    allowed_categories = {
        "waiting_for_market",
        "processing",
        "running",
        "monitor_refresh",
        "engineering_blocker",
        "safety_blocker",
    }
    if category and category not in allowed_categories:
        blockers.append(f"unknown_owner_visibility_category:{category}")
    if owner.get("owner_intervention_required") is True and category != "safety_blocker":
        blockers.append("owner_intervention_required_without_safety_blocker")
    return _track(
        track_id="owner_visibility_projection",
        label="Owner Visibility Projection",
        blockers=blockers,
        evidence=[
            f"category={category or 'unknown'}",
            f"notification={notification.get('decision')}",
            f"owner_intervention_required={owner.get('owner_intervention_required')}",
        ],
        progress_checkpoint="保持 Owner 进度层输出，不要求阅读原始证据包",
    )


def _projection_status(artifact: dict[str, Any]) -> str:
    return str(artifact.get("status") or "unknown")


def _projection_mapping(artifact: dict[str, Any], key: str) -> dict[str, Any]:
    value = artifact.get(key)
    return value if isinstance(value, dict) else {}


def _projection_mapping_first(
    artifact: dict[str, Any],
    *keys: str,
) -> dict[str, Any]:
    for key in keys:
        value = _projection_mapping(artifact, key)
        if value:
            return value
    return {}


def _projection_int(mapping: dict[str, Any], key: str) -> int:
    return int(mapping.get(key) or 0)


def _projection_int_first(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return int(value)
    return 0


def _projection_list_count(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    return len(value) if isinstance(value, list) else 0


def _projection_list_count_first(mapping: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _projection_true(mapping: dict[str, Any], key: str) -> bool:
    return mapping.get(key) is True


def _projection_false(mapping: dict[str, Any], key: str) -> bool:
    return mapping.get(key) is False


def _projection_text(mapping: dict[str, Any], key: str, default: str) -> str:
    return str(mapping.get(key) or default)


def _projection_text_first(
    mapping: dict[str, Any],
    keys: tuple[str, ...],
    default: str,
) -> str:
    for key in keys:
        value = mapping.get(key)
        if value:
            return str(value)
    return default


def _append_unexpected_projection_status(
    reject_reasons: list[str],
    *,
    actual_status: str,
    expected_status: str,
) -> None:
    if actual_status != expected_status:
        reject_reasons.append("projection_not_ready")


def _append_forbidden_projection_effects(
    reject_reasons: list[str],
    *,
    safety: dict[str, Any],
    keys: tuple[str, ...],
    legacy_authority_mirror_keys: tuple[str, ...] = (),
) -> None:
    for key in keys:
        if _projection_true(safety, key):
            reject_reasons.append(f"forbidden_effect:{key}")
    reject_reasons.extend(
        legacy_authority_mirror_present_errors(
            safety,
            label_prefix="",
            keys=legacy_authority_mirror_keys,
        )
    )


def _append_projection_remote_interaction_blocker(
    reject_reasons: list[str],
    *,
    interaction: dict[str, Any],
) -> None:
    if interaction.get("remote_interaction_count", 0) not in {0, "0", None}:
        reject_reasons.append("remote_interaction_not_zero")


def _append_projection_promote_authority_boundary_rejections(
    reject_reasons: list[str],
    *,
    trial_envelope: dict[str, Any],
) -> None:
    if _projection_text(trial_envelope, "policy_outcome", "") != "promote":
        return
    if _projection_text(trial_envelope, "promotion_scope", "") != "intake_only":
        reject_reasons.append("unscoped_promote_forbidden")
    authority_boundary = _projection_mapping(
        trial_envelope, "authority_boundary"
    )
    if _projection_text(authority_boundary, "promotion_scope", "") != "intake_only":
        reject_reasons.append("authority_boundary_promotion_scope_missing")
    if not _projection_false(authority_boundary, "unscoped_promote"):
        reject_reasons.append("authority_boundary_unscoped_promote_not_false")
    if not _projection_false(trial_envelope, "tiny_live_ready"):
        reject_reasons.append("trial_envelope_tiny_live_ready_not_false")


def _append_projection_basic_safety_rejections(
    reject_reasons: list[str],
    *,
    summary: dict[str, Any],
    trial_envelope: dict[str, Any],
) -> None:
    if _projection_int(summary, "live_permission_change_count") != 0:
        reject_reasons.append("live_permission_change_count_not_zero")
    reject_reasons.extend(
        legacy_authority_mirror_present_errors(
            trial_envelope,
            label_prefix="trial_envelope.",
        )
    )
    if not _projection_false(trial_envelope, "live_permission_change"):
        reject_reasons.append("trial_envelope_live_permission_change_not_false")


def _append_projection_admission_selection_rejections(
    reject_reasons: list[str],
    *,
    artifact: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    projection_status = _projection_text(artifact, "projection_status", "unknown")
    if projection_status != "trial_envelope_projection_ready":
        reject_reasons.append("projection_status_not_ready")
    if _projection_int(summary, "eligibility_row_count") < 5:
        reject_reasons.append("eligibility_row_count_below_5")
    if _projection_int(summary, "non_mpg_trial_candidate_count") < 1:
        reject_reasons.append("non_mpg_trial_candidate_missing")
    selected = _projection_text(summary, "selected_non_mpg_strategy_group_id", "")
    if not selected or selected == "MPG-001":
        reject_reasons.append("selected_non_mpg_candidate_invalid")
    if not _projection_true(summary, "trial_envelope_generated"):
        reject_reasons.append("trial_envelope_not_generated")


def _append_projection_authority_claim_rejections(
    reject_reasons: list[str],
    *,
    policy: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    if _projection_true(policy, "runtime_owner_intervention_required"):
        reject_reasons.append("owner_policy_checkpoint_became_runtime_intervention")
    if _projection_true(metadata, "strategygroup_lifecycle_owner"):
        reject_reasons.append("projection_claimed_lifecycle_owner")
    if _projection_true(metadata, "tradeability_decision_source"):
        reject_reasons.append("projection_claimed_tradeability_decision_source")
    if _projection_true(metadata, "runtime_truth_source"):
        reject_reasons.append("projection_claimed_runtime_truth_source")


def _strategy_review_evidence_closure_track(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    boundary = _strategy_review_evidence_closure_boundary(artifact)
    blockers = [
        f"strategy_review_evidence_closure:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"phase_1={boundary['phase_1_status']}",
        f"phase_2={boundary['phase_2_status']}",
        f"phase_3={boundary['phase_3_status']}",
        f"evidence_artifact_count={boundary['evidence_artifact_count']}",
        f"next_owner_policy_item_count={boundary['next_owner_policy_item_count']}",
        "owner_policy_confirmation_required_now="
        + str(boundary["owner_policy_confirmation_required_now"]),
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "strategy_review_evidence_closure_projection",
        "label": "Strategy Review Evidence Projection",
        "status": "blocked" if blockers else "ready",
        "owner_state": "策略政策待确认" if not blockers else "需处理",
        "progress_checkpoint": (
            "等待 Owner 策略政策确认，不改变实盘权限"
            if not blockers
            else "修复策略复核证据闭合包"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategy_review_evidence_closure_boundary(
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if not artifact:
        return {
            "status": "not_generated",
            "phase_1_status": "not_generated",
            "phase_2_status": "not_generated",
            "phase_3_status": "not_generated",
            "evidence_artifact_count": 0,
            "next_owner_policy_item_count": 0,
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "reject_reasons": [],
        }
    phase_status = _projection_mapping(artifact, "phase_status")
    next_package = _projection_mapping(artifact, "next_owner_policy_package")
    safety = _projection_mapping(artifact, "safety_invariants")
    interaction = _projection_mapping(artifact, "interaction")
    status = _projection_status(artifact)
    reject_reasons: list[str] = []
    _append_unexpected_projection_status(
        reject_reasons,
        actual_status=status,
        expected_status="review_only_evidence_closure_wave_ready",
    )
    _append_forbidden_projection_effects(
        reject_reasons,
        safety=safety,
        keys=REVIEW_PROJECTION_FORBIDDEN_EFFECT_KEYS,
        legacy_authority_mirror_keys=LEGACY_AUTHORITY_MIRROR_KEYS,
    )
    _append_projection_remote_interaction_blocker(
        reject_reasons,
        interaction=interaction,
    )
    return {
        "status": status,
        "phase_1_status": _projection_text(
            phase_status, "phase_1_owner_perception_projection", "unknown"
        ),
        "phase_2_status": _projection_text(
            phase_status, "phase_2_evidence_closure_queue", "unknown"
        ),
        "phase_3_status": _projection_text_first(
            phase_status,
            (
                "phase_3_next_owner_policy_package",
            ),
            "unknown",
        ),
        "evidence_artifact_count": _projection_list_count_first(
            artifact,
            "evidence_closure_artifacts",
        ),
        "next_owner_policy_item_count": _projection_int_first(
            next_package,
            "owner_policy_item_count",
            "decision_count",
        ),
        "owner_policy_confirmation_required_now": (
            _projection_true(next_package, "owner_policy_confirmation_required_now")
        ),
        "runtime_owner_intervention_required": (
            _projection_true(next_package, "runtime_owner_intervention_required")
        ),
        "reject_reasons": reject_reasons,
    }


def _strategy_review_deep_dive_track(artifact: dict[str, Any]) -> dict[str, Any]:
    boundary = _strategy_review_deep_dive_boundary(artifact)
    blockers = [
        f"strategy_review_deep_dive:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"phase_1={boundary['phase_1_status']}",
        f"phase_2={boundary['phase_2_status']}",
        f"phase_3={boundary['phase_3_status']}",
        f"deep_dive_artifact_count={boundary['deep_dive_artifact_count']}",
        f"next_owner_policy_item_count={boundary['next_owner_policy_item_count']}",
        "owner_policy_confirmation_required_now="
        + str(boundary["owner_policy_confirmation_required_now"]),
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "strategy_review_deep_dive_projection",
        "label": "Strategy Review Deep Dive Projection",
        "status": "blocked" if blockers else "ready",
        "owner_state": "六条线等待政策决策" if not blockers else "需处理",
        "progress_checkpoint": (
            "等待 Owner 确认六条策略线下一步政策，不改变实盘权限"
            if not blockers
            else "修复策略深挖决策包"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategy_review_deep_dive_boundary(
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if not artifact:
        return {
            "status": "not_generated",
            "phase_1_status": "not_generated",
            "phase_2_status": "not_generated",
            "phase_3_status": "not_generated",
            "deep_dive_artifact_count": 0,
            "next_owner_policy_item_count": 0,
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "reject_reasons": [],
        }
    phase_status = _projection_mapping(artifact, "phase_status")
    next_package = _projection_mapping(artifact, "owner_policy_package")
    safety = _projection_mapping(artifact, "safety_invariants")
    interaction = _projection_mapping(artifact, "interaction")
    status = _projection_status(artifact)
    reject_reasons: list[str] = []
    _append_unexpected_projection_status(
        reject_reasons,
        actual_status=status,
        expected_status="review_only_deep_dive_ready_for_owner_policy",
    )
    _append_forbidden_projection_effects(
        reject_reasons,
        safety=safety,
        keys=REVIEW_PROJECTION_FORBIDDEN_EFFECT_KEYS,
        legacy_authority_mirror_keys=LEGACY_AUTHORITY_MIRROR_KEYS,
    )
    _append_projection_remote_interaction_blocker(
        reject_reasons,
        interaction=interaction,
    )
    return {
        "status": status,
        "phase_1_status": _projection_text(
            phase_status, "phase_1_owner_perception_projection", "unknown"
        ),
        "phase_2_status": _projection_text(
            phase_status, "phase_2_six_line_deep_dive", "unknown"
        ),
        "phase_3_status": _projection_text_first(
            phase_status,
            (
                "phase_3_owner_policy_package",
            ),
            "unknown",
        ),
        "deep_dive_artifact_count": _projection_list_count_first(
            artifact,
            "deep_dive_artifacts",
        ),
        "next_owner_policy_item_count": _projection_int_first(
            next_package,
            "owner_policy_item_count",
            "decision_count",
        ),
        "owner_policy_confirmation_required_now": (
            _projection_true(next_package, "owner_policy_confirmation_required_now")
        ),
        "runtime_owner_intervention_required": (
            _projection_true(next_package, "runtime_owner_intervention_required")
        ),
        "reject_reasons": reject_reasons,
    }


def _strategygroup_portfolio_board_track(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    boundary = _strategygroup_portfolio_board_boundary(artifact)
    blockers = [
        f"strategygroup_portfolio_board:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"portfolio_row_count={boundary['portfolio_row_count']}",
        f"trial_candidate_count={boundary['trial_candidate_count']}",
        f"engineering_continuation_count={boundary['engineering_continuation_count']}",
        f"owner_policy_queue_count={boundary['owner_policy_queue_count']}",
        f"live_permission_change_count={boundary['live_permission_change_count']}",
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "strategygroup_portfolio_projection",
        "label": "StrategyGroup Portfolio Projection",
        "status": "blocked" if blockers else "ready",
        "owner_state": "策略组合筛选中" if not blockers else "需处理",
        "progress_checkpoint": (
            "继续工程补证队列和 受控实盘候选池治理，不改变实盘权限"
            if not blockers
            else "修复 StrategyGroup Portfolio Board 证据或安全边界"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategygroup_portfolio_board_boundary(
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if not artifact:
        return {
            "status": "not_generated",
            "portfolio_row_count": 0,
            "trial_candidate_count": 0,
            "engineering_continuation_count": 0,
            "owner_policy_queue_count": 0,
            "live_permission_change_count": 0,
            "runtime_owner_intervention_required": False,
            "reject_reasons": [],
        }
    summary = _projection_mapping(artifact, "portfolio_summary")
    trial_pool = _projection_mapping(artifact, "trial_candidate_pool")
    safety = _projection_mapping(artifact, "safety_invariants")
    interaction = _projection_mapping(artifact, "interaction")
    owner_projection = _projection_mapping(artifact, "owner_progress_projection")
    status = _projection_status(artifact)
    reject_reasons: list[str] = []
    _append_unexpected_projection_status(
        reject_reasons,
        actual_status=status,
        expected_status="portfolio_board_ready",
    )
    if _projection_int(summary, "portfolio_row_count") < 10:
        reject_reasons.append("portfolio_row_count_below_10")
    if _projection_int(trial_pool, "live_permission_change_count") != 0:
        reject_reasons.append("trial_pool_live_permission_change_not_zero")
    _append_forbidden_projection_effects(
        reject_reasons,
        safety=safety,
        keys=PORTFOLIO_PROJECTION_FORBIDDEN_EFFECT_KEYS,
        legacy_authority_mirror_keys=LEGACY_AUTHORITY_MIRROR_KEYS,
    )
    _append_projection_remote_interaction_blocker(
        reject_reasons,
        interaction=interaction,
    )
    return {
        "status": status,
        "portfolio_row_count": _projection_int(summary, "portfolio_row_count"),
        "trial_candidate_count": _projection_int(trial_pool, "candidate_count"),
        "engineering_continuation_count": _projection_int(
            summary, "engineering_continuation_count"
        ),
        "owner_policy_queue_count": _projection_int_first(
            summary,
            "owner_policy_queue_count",
        ),
        "live_permission_change_count": _projection_int(
            trial_pool, "live_permission_change_count"
        ),
        "runtime_owner_intervention_required": (
            _projection_true(owner_projection, "owner_intervention_required")
        ),
        "reject_reasons": reject_reasons,
    }


def _strategygroup_capital_trial_envelope_projection_track(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    boundary = _strategygroup_capital_trial_envelope_projection_boundary(artifact)
    blockers = [
        f"strategygroup_capital_trial_envelope_projection:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"projection_status={boundary['projection_status']}",
        f"eligibility_row_count={boundary['eligibility_row_count']}",
        f"non_mpg_trial_candidate_count={boundary['non_mpg_trial_candidate_count']}",
        f"selected_non_mpg_strategy_group_id={boundary['selected_non_mpg_strategy_group_id']}",
        f"selected_candidate_status={boundary['selected_candidate_status']}",
        f"trial_envelope_generated={boundary['trial_envelope_generated']}",
        f"live_permission_change_count={boundary['live_permission_change_count']}",
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "capital_trial_readiness_projection",
        "label": "Capital Trial Envelope Projection",
        "status": "blocked" if blockers else "ready",
        "owner_state": "资金试验候选准备中" if not blockers else "需处理",
        "progress_checkpoint": (
            "保留 "
            + str(boundary["selected_non_mpg_strategy_group_id"] or "候选策略组")
            + " 为首个非 MPG 预注册试验候选，继续工程补证和后续政策检查点"
            if not blockers
            else "修复 Capital Trial Envelope Projection 证据或安全边界"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategygroup_capital_trial_envelope_projection_boundary(
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if not artifact:
        return {
            "status": "not_generated",
            "projection_status": "not_generated",
            "projection_schema": "",
            "projection_role": "trial_envelope_projection",
            "strategygroup_lifecycle_owner": False,
            "tradeability_decision_source": False,
            "runtime_truth_source": False,
            "eligibility_row_count": 0,
            "non_mpg_trial_candidate_count": 0,
            "selected_non_mpg_strategy_group_id": None,
            "selected_candidate_status": "not_generated",
            "policy_outcome": "not_generated",
            "reason": "",
            "promotion_scope": "not_applicable",
            "promotion_target": "not_applicable",
            "tiny_live_ready": False,
            "next_checkpoint": "",
            "trial_envelope_generated": False,
            "live_permission_change_count": 0,
            "owner_policy_checkpoint_count": 0,
            "runtime_owner_intervention_required": False,
            "reject_reasons": [],
        }
    summary = _projection_mapping(artifact, "capital_trial_summary")
    trial_envelope = _projection_mapping(artifact, "trial_envelope_v0")
    safety = _projection_mapping(artifact, "safety_invariants")
    interaction = _projection_mapping(artifact, "interaction")
    policy = _projection_mapping(artifact, "owner_policy_checkpoint")
    metadata = _projection_mapping(artifact, "projection_metadata")
    status = _projection_status(artifact)
    reject_reasons: list[str] = []
    _append_projection_admission_selection_rejections(
        reject_reasons,
        artifact=artifact,
        summary=summary,
    )
    _append_projection_basic_safety_rejections(
        reject_reasons,
        summary=summary,
        trial_envelope=trial_envelope,
    )
    _append_projection_promote_authority_boundary_rejections(
        reject_reasons,
        trial_envelope=trial_envelope,
    )
    _append_forbidden_projection_effects(
        reject_reasons,
        safety=safety,
        keys=TRIAL_ENVELOPE_PROJECTION_FORBIDDEN_EFFECT_KEYS,
        legacy_authority_mirror_keys=LEGACY_AUTHORITY_MIRROR_KEYS,
    )
    _append_projection_remote_interaction_blocker(
        reject_reasons,
        interaction=interaction,
    )
    _append_projection_authority_claim_rejections(
        reject_reasons,
        policy=policy,
        metadata=metadata,
    )
    return {
        "status": status,
        "projection_status": _projection_text(
            artifact, "projection_status", "unknown"
        ),
        "projection_schema": _projection_text(artifact, "projection_schema", ""),
        "projection_role": _projection_text(
            metadata, "artifact_role", "trial_envelope_projection"
        ),
        "strategygroup_lifecycle_owner": (
            _projection_true(metadata, "strategygroup_lifecycle_owner")
        ),
        "tradeability_decision_source": (
            _projection_true(metadata, "tradeability_decision_source")
        ),
        "runtime_truth_source": _projection_true(metadata, "runtime_truth_source"),
        "eligibility_row_count": _projection_int(summary, "eligibility_row_count"),
        "non_mpg_trial_candidate_count": _projection_int(
            summary, "non_mpg_trial_candidate_count"
        ),
        "selected_non_mpg_strategy_group_id": (
            summary.get("selected_non_mpg_strategy_group_id")
        ),
        "selected_candidate_status": _projection_text(
            summary, "selected_candidate_status", "unknown"
        ),
        "policy_outcome": _projection_text(
            trial_envelope, "policy_outcome", "pending"
        ),
        "reason": _projection_text(trial_envelope, "reason", ""),
        "promotion_scope": _projection_text(
            trial_envelope, "promotion_scope", "not_applicable"
        ),
        "promotion_target": _projection_text(
            trial_envelope, "promotion_target", "not_applicable"
        ),
        "next_checkpoint": _projection_text(trial_envelope, "next_checkpoint", ""),
        "trial_envelope_generated": _projection_true(
            summary, "trial_envelope_generated"
        ),
        "live_permission_change_count": _projection_int(
            summary, "live_permission_change_count"
        ),
        "owner_policy_checkpoint_count": _projection_int(
            summary, "owner_policy_checkpoint_count"
        ),
        "runtime_owner_intervention_required": (
            _projection_true(policy, "runtime_owner_intervention_required")
        ),
        "reject_reasons": reject_reasons,
    }


def _safety_invariants_track(*, safety: dict[str, Any]) -> dict[str, Any]:
    forbidden_true = [
        key for key, value in safety.items()
        if key in {
            "remote_files_modified",
            "env_files_read",
            "secrets_read",
            "migrations_run",
            "services_restarted",
            "execution_intent_created",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "withdrawal_or_transfer_created",
        }
        and value is True
    ]
    return _track(
        track_id="safety_invariants_projection",
        label="Safety Invariants Projection",
        blockers=[f"forbidden_effect:{item}" for item in forbidden_true],
        evidence=[f"forbidden_effect_count={len(forbidden_true)}"],
        progress_checkpoint="保持不触发 FinalGate、Operation Layer、exchange write 或订单动作",
    )


def _track(
    *,
    track_id: str,
    label: str,
    blockers: list[str],
    evidence: list[str],
    progress_checkpoint: str,
) -> dict[str, Any]:
    return {
        "id": track_id,
        "label": label,
        "status": "blocked" if blockers else "ready",
        "owner_state": "需处理" if blockers else "已就绪",
        "progress_checkpoint": (
            progress_checkpoint if not blockers else "处理该轨道阻断"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    issues = report["owner_runtime_issues"]
    signal_observation = report["signal_observation"]
    owner_runtime_state = report["owner_runtime_state"]
    completion = report["completion_boundary"]
    p0_completion = report["p0_completion_audit_boundary"]
    entry_fast_chain = report["entry_fast_chain_boundary"]
    exit_hardening = report["exit_hardening_boundary"]
    tier_boundary = report["strategygroup_tier_boundary"]
    live_cutover = report["live_cutover_readiness_boundary"]
    live_closure = report["live_closure_evidence_boundary"]
    strategy_review = report["strategy_review_evidence_closure_boundary"]
    strategy_deep_dive = report["strategy_review_deep_dive_boundary"]
    portfolio_board = report["strategygroup_portfolio_board_boundary"]
    capital_trial = report["strategygroup_capital_trial_envelope_projection_boundary"]
    lines = [
        "## StrategyGroup Runtime Goal Progress",
        "",
        f"- 报告时间: {report['generated_at_utc']}",
        f"- 当前阶段: {owner['state']}",
        f"- 当前检查点: {owner['non_authority_checkpoint']}",
        f"- 风险等级: {owner['risk_level']}",
        f"- Owner 介入: {_yes_no(bool(owner['owner_intervention_required']))}",
        f"- 交互等级: {interaction['level']}",
        f"- 远端交互次数: {interaction['remote_interaction_count']}",
        f"- 服务器修改: {_yes_no(bool(interaction['mutates_remote_files']))}",
        f"- 接近真实订单: {_yes_no(bool(interaction['approaches_real_order']))}",
        "",
        "## Completion Boundary",
        "",
        f"- Goal complete: {_yes_no(bool(completion['goal_complete']))}",
        f"- Status: {completion['status']}",
        f"- Reason: {completion['reason']}",
        f"- Completion blocker class: {completion['completion_blocker_class']}",
        "- First bounded real order complete: "
        + _yes_no(bool(completion["first_bounded_real_order_complete"])),
        "- Real order closure proven: "
        + _yes_no(bool(completion["real_order_closure_proven"])),
        "- Waiting for real fresh signal: "
        + _yes_no(bool(completion["waiting_for_real_fresh_signal"])),
        "- Dry-run readiness proven: "
        + _yes_no(bool(completion["dry_run_readiness_proven"])),
        "",
        "## P0 Completion Audit Boundary",
        "",
        f"- Status: {p0_completion['status']}",
        "- Non-market gaps: "
        + str(p0_completion["non_market_gap_count"]),
        "- Market-dependent remaining: "
        + str(p0_completion["market_dependent_remaining_count"]),
        "- Market-dependent remaining items: "
        + _list_or_none(
            [str(item) for item in p0_completion["market_dependent_remaining"]]
        ),
        "- Goal complete by audit: "
        + _yes_no(bool(p0_completion["goal_complete"])),
        "",
        "## Entry Fast Chain Boundary",
        "",
        f"- Status: {entry_fast_chain['status']}",
        "- Fresh signal to candidate/auth covered: "
        + _yes_no(
            bool(entry_fast_chain["fresh_signal_to_candidate_authorization_covered"])
        ),
        "- RequiredFacts gate covered: "
        + _yes_no(bool(entry_fast_chain["required_facts_gate_covered"])),
        "- Candidate/auth to FinalGate covered: "
        + _yes_no(
            bool(entry_fast_chain["candidate_authorization_to_finalgate_covered"])
        ),
        "- FinalGate to ticket-bound Operation Layer handoff covered: "
        + _yes_no(
            bool(
                entry_fast_chain[
                    "finalgate_to_ticket_bound_operation_layer_handoff_covered"
                ]
            )
        ),
        "- Operation Layer authorization guard covered: "
        + _yes_no(
            bool(entry_fast_chain["operation_layer_authorization_guard_covered"])
        ),
        "- Real action-time FinalGate proven: "
        + _yes_no(bool(entry_fast_chain["real_action_time_finalgate_proven"])),
        "- Real Operation Layer submit proven: "
        + _yes_no(bool(entry_fast_chain["real_operation_layer_submit_proven"])),
        "- Real order dependent remaining: "
        + _yes_no(bool(entry_fast_chain["real_order_dependent_remaining"])),
        "",
        "## Exit Hardening Boundary",
        "",
        f"- Status: {exit_hardening['status']}",
        "- Post-submit exit outcome matrix checked: "
        + _yes_no(bool(exit_hardening["post_submit_exit_outcome_matrix_checked"])),
        "- Exchange-native hard stop required after entry: "
        + _yes_no(
            bool(exit_hardening["exchange_native_hard_stop_required_after_entry"])
        ),
        "- Protection failure reduce-only recovery covered: "
        + _yes_no(
            bool(
                exit_hardening[
                    "entry_filled_protection_failed_reduce_only_recovery_covered"
                ]
            )
        ),
        "- Real post-submit close/reconcile/settle proven: "
        + _yes_no(
            bool(exit_hardening["real_post_submit_close_reconcile_settle_proven"])
        ),
        "- Real order dependent remaining: "
        + _yes_no(bool(exit_hardening["real_order_dependent_remaining"])),
        "",
        "## StrategyGroup Tier Boundary",
        "",
        f"- Status: {tier_boundary['status']}",
        "- First live lane StrategyGroup: "
        + str(tier_boundary["first_live_lane_strategy_group"] or "none"),
        "- L4 StrategyGroups: "
        + _list_or_none([str(item) for item in tier_boundary["l4_strategy_groups"]]),
        "- New StrategyGroups default non-L4: "
        + _yes_no(bool(tier_boundary["new_strategy_groups_default_non_l4"])),
        "- Tier policy is execution authority: "
        + _yes_no(bool(tier_boundary["tier_policy_is_execution_authority"])),
        "- Tier policy bypasses FinalGate: "
        + _yes_no(bool(tier_boundary["tier_policy_bypasses_finalgate"])),
        "- Tier policy bypasses Operation Layer: "
        + _yes_no(bool(tier_boundary["tier_policy_bypasses_operation_layer"])),
        "",
        "## Live Cutover Readiness Boundary",
        "",
        f"- Status: {live_cutover['status']}",
        f"- Source status: {live_cutover['source_status'] or 'none'}",
        "- Next fresh signal cutover ready: "
        + _yes_no(bool(live_cutover["next_fresh_signal_cutover_ready"])),
        "- Current real submit allowed: "
        + _yes_no(bool(live_cutover["current_real_submit_allowed"])),
        "- Non-market blockers: "
        + _list_or_none(
            [str(item) for item in live_cutover["non_market_blockers"]]
        ),
        "- Market-dependent waiting keys: "
        + _list_or_none(
            [str(item) for item in live_cutover["market_dependent_waiting_keys"]]
        ),
        "",
        "## Live Closure Evidence Boundary",
        "",
        f"- Status: {live_closure['status']}",
        f"- Source status: {live_closure.get('source_status') or 'none'}",
        f"- Raw source status: {live_closure.get('raw_source_status') or 'none'}",
        f"- Normalization reason: {live_closure.get('normalization_reason') or 'none'}",
        "- Completed stages: "
        + f"{live_closure['completed_stage_count']}/{live_closure['stage_count']}",
        "- Expected stages: "
        + str(live_closure.get("expected_stage_count") or 0),
        "- First incomplete stage: "
        + str(live_closure["first_incomplete_stage"] or "none"),
        "- Market-dependent waiting keys: "
        + _list_or_none(
            [
                str(item)
                for item in live_closure.get("market_dependent_waiting_keys") or []
            ]
        ),
        "- Missing evidence keys: "
        + _list_or_none(
            [str(item) for item in live_closure["missing_evidence_keys"]]
        ),
        "- Reject reasons: "
        + _list_or_none([str(item) for item in live_closure["reject_reasons"]]),
        "",
        "## Strategy Review Evidence Closure Boundary",
        "",
        f"- Status: {strategy_review['status']}",
        f"- Phase 1 Owner perception: {strategy_review['phase_1_status']}",
        f"- Phase 2 evidence closure: {strategy_review['phase_2_status']}",
        f"- Phase 3 next Owner policy package: {strategy_review['phase_3_status']}",
        "- Evidence artifact count: "
        + str(strategy_review["evidence_artifact_count"]),
        "- Next Owner policy policy_item count: "
        + str(strategy_review["next_owner_policy_item_count"]),
        "- Owner policy confirmation required now: "
        + _yes_no(bool(strategy_review["owner_policy_confirmation_required_now"])),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(strategy_review["runtime_owner_intervention_required"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in strategy_review["reject_reasons"]]
        ),
        "",
        "## Strategy Review Deep Dive Boundary",
        "",
        f"- Status: {strategy_deep_dive['status']}",
        f"- Phase 1 Owner perception: {strategy_deep_dive['phase_1_status']}",
        f"- Phase 2 six-line deep dive: {strategy_deep_dive['phase_2_status']}",
        f"- Phase 3 next Owner policy package: {strategy_deep_dive['phase_3_status']}",
        "- Deep-dive artifact count: "
        + str(strategy_deep_dive["deep_dive_artifact_count"]),
        "- Next Owner policy policy_item count: "
        + str(strategy_deep_dive["next_owner_policy_item_count"]),
        "- Owner policy confirmation required now: "
        + _yes_no(bool(strategy_deep_dive["owner_policy_confirmation_required_now"])),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(strategy_deep_dive["runtime_owner_intervention_required"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in strategy_deep_dive["reject_reasons"]]
        ),
        "",
        "## StrategyGroup Portfolio Board Boundary",
        "",
        f"- Status: {portfolio_board['status']}",
        "- Portfolio row count: "
        + str(portfolio_board["portfolio_row_count"]),
        "- Trial candidate count: "
        + str(portfolio_board["trial_candidate_count"]),
        "- Engineering continuation count: "
        + str(portfolio_board["engineering_continuation_count"]),
        "- Owner policy queue count: "
        + str(portfolio_board["owner_policy_queue_count"]),
        "- Live permission change count: "
        + str(portfolio_board["live_permission_change_count"]),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(portfolio_board["runtime_owner_intervention_required"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in portfolio_board["reject_reasons"]]
        ),
        "",
        "## StrategyGroup Capital Trial Envelope Projection Boundary",
        "",
        f"- Status: {capital_trial['status']}",
        f"- Projection status: {capital_trial['projection_status']}",
        f"- Projection role: {capital_trial['projection_role']}",
        "- Eligibility row count: "
        + str(capital_trial["eligibility_row_count"]),
        "- Non-MPG trial candidate count: "
        + str(capital_trial["non_mpg_trial_candidate_count"]),
        "- Selected non-MPG StrategyGroup: "
        + str(capital_trial["selected_non_mpg_strategy_group_id"] or "none"),
        "- Selected candidate status: "
        + str(capital_trial["selected_candidate_status"]),
        "- Policy outcome: "
        + str(capital_trial["policy_outcome"]),
        "- Reason: "
        + str(capital_trial["reason"]),
        "- Promotion scope: "
        + str(capital_trial["promotion_scope"]),
        "- Promotion target: "
        + str(capital_trial["promotion_target"]),
        "- Next checkpoint: "
        + str(capital_trial["next_checkpoint"] or "none"),
        "- Trial envelope generated: "
        + _yes_no(bool(capital_trial["trial_envelope_generated"])),
        "- Live permission change count: "
        + str(capital_trial["live_permission_change_count"]),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(capital_trial["runtime_owner_intervention_required"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in capital_trial["reject_reasons"]]
        ),
        "",
        "## Tracks",
        "",
        "| Track | Status | Owner state | Progress checkpoint | Blockers |",
        "| --- | --- | --- | --- | --- |",
    ]
    for track in report["tracks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(track["label"]),
                    str(track["status"]),
                    str(track["owner_state"]),
                    str(track["progress_checkpoint"]),
                    _list_or_none([str(item) for item in track.get("blockers", [])]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Evidence", ""])
    lines.append("| Track | Evidence |")
    lines.append("| --- | --- |")
    for track in report["tracks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(track["label"]),
                    _list_or_none([str(item) for item in track.get("evidence", [])]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Owner Runtime State", ""])
    lines.append(
        "- Waiting for market: "
        + _yes_no(bool(owner_runtime_state["waiting_for_market"]))
    )
    lines.append(
        "- Signal Observation grade: "
        f"{signal_observation['grade_code']} / {signal_observation['state']}"
    )
    lines.append(
        "- Signal Observation ready: "
        + _yes_no(bool(signal_observation["ready"]))
    )
    lines.extend(["", "## Owner Runtime Issues", ""])
    lines.append(
        f"- Blockers: {_list_or_none([str(item) for item in issues['blockers']])}"
    )
    lines.append(
        f"- Product gaps: {_list_or_none([str(item) for item in issues['product_gaps']])}"
    )
    return "\n".join(lines)


def _print_human_report(report: dict[str, Any]) -> None:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    issues = report["owner_runtime_issues"]
    signal_observation = report["signal_observation"]
    print(f"status={report['status']}")
    print(f"owner_state={owner['state']}")
    print(f"non_authority_checkpoint={owner['non_authority_checkpoint']}")
    print(f"interaction={interaction['level']}")
    print(f"remote_interaction_count={interaction['remote_interaction_count']}")
    print(f"signal_observation_ready={str(signal_observation['ready']).lower()}")
    if issues["blockers"]:
        print("blockers=" + ",".join(issues["blockers"]))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _build_live_cutover_readiness(path: Path) -> dict[str, Any]:
    artifact = runtime_live_cutover_readiness.build_cutover_readiness_artifact(
        path.parent / "artifacts"
    )
    _write_text_atomic(
        path,
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return artifact


def _write_text_atomic(path: Path, text: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize StrategyGroup Runtime Pilot goal progress."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--owner-progress",
        action="store_true",
        help="Print an Owner-readable Markdown progress summary.",
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--baseline-json", default=str(DEFAULT_BASELINE_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--live-cutover-readiness-json",
        default=str(DEFAULT_LIVE_CUTOVER_READINESS_JSON),
    )
    parser.add_argument(
        "--live-closure-evidence-verification-json",
        default=str(DEFAULT_LIVE_CLOSURE_EVIDENCE_VERIFICATION_JSON),
    )
    parser.add_argument(
        "--live-closure-evidence-json",
        default=str(DEFAULT_LIVE_CLOSURE_EVIDENCE_JSON),
    )
    parser.add_argument(
        "--strategy-review-evidence-closure-wave-json",
        default=str(DEFAULT_STRATEGYGROUP_REVIEW_ONLY_EVIDENCE_CLOSURE_WAVE_JSON),
    )
    parser.add_argument(
        "--strategy-review-deep-dive-wave-json",
        default=str(DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON),
    )
    parser.add_argument(
        "--strategygroup-portfolio-board-json",
        default=str(DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON),
    )
    parser.add_argument(
        "--strategygroup-capital-trial-envelope-projection-json",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON),
    )
    parser.add_argument(
        "--no-auto-live-cutover-readiness",
        action="store_true",
        help="Do not build a local live-cutover readiness artifact when missing.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument(
        "--output-owner-progress",
        default=str(DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD),
    )
    return parser.parse_args(argv)


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


if __name__ == "__main__":
    raise SystemExit(main())
