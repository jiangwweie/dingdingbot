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
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_READINESS_BRIDGE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-readiness-bridge.json"
)
SCHEMA = "brc.strategygroup_runtime_goal_progress_audit.v1"
MONITOR_REFRESH_STATUS = "waiting_for_market_monitor_refresh_needed"
DEPLOYMENT_ISSUE_STATUS = "temporarily_unavailable_deployment_issue"

P0_COMPLETION_AUDIT_REQUIRED_CHECKS = (
    "allocated_subaccount_profile_boundary_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "disabled_smoke_not_real_execution_proof",
    "expanded_watcher_scope_execution_guard_checked",
    "fresh_signal_fast_auto_chain_checked",
    "non_executing_prepare_auto_bridge_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "operation_layer_authorization_chain_guard_checked",
    "operation_layer_blocker_review_policy_checked",
    "operation_layer_evidence_relay_checked",
    "operation_layer_standing_authorization_relay_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "post_submit_exit_outcome_matrix_checked",
    "post_submit_finalize_result_identity_guard_checked",
    "reduce_only_recovery_standing_authorization_checked",
    "required_facts_readiness_checked",
    "scoped_pipeline_operation_layer_handoff_checked",
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
        strategygroup_capital_trial_readiness_bridge=_read_optional_json(
            Path(args.strategygroup_capital_trial_readiness_bridge_json)
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
    strategygroup_capital_trial_readiness_bridge: dict[str, Any] | None = None,
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
    monitor_refresh_needed = checks.get("monitor_refresh_needed") is True
    monitor_refresh_reasons = [
        str(item) for item in checks.get("monitor_refresh_reasons") or []
    ]
    monitor_status = str(
        daily_check.get("monitor_status")
        or (
            "deployment_issue"
            if checks.get("deployment_issue") is True
            else "needs_refresh"
            if monitor_refresh_needed
            else "fresh"
        )
    )

    p0 = _p0_track(
        daily_check=daily_check,
        checks=checks,
        owner=owner,
        visibility=visibility,
    )
    p05_tracks = [
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
                _strategygroup_capital_trial_readiness_bridge_track(
                    strategygroup_capital_trial_readiness_bridge
                )
            ]
            if strategygroup_capital_trial_readiness_bridge
            else []
        ),
        _safety_invariants_track(safety=safety),
    ]
    issues = _dedupe(
        blocker
        for item in [p0, *p05_tracks]
        for blocker in item.get("blockers", [])
    )
    hard_blockers = _dedupe(
        blocker
        for item in [p0, *p05_tracks]
        if item["id"] in {"p0_live_closure", "p05_safety_invariants"}
        for blocker in item.get("blockers", [])
    )
    waiting_for_market = p0["status"] == "waiting_for_market"
    p05_ready = all(item["status"] == "ready" for item in p05_tracks)
    product_gaps = [item for item in issues if item not in hard_blockers]
    engineering_rehearsal_ready = next(
        (
            item["status"] == "ready"
            for item in p05_tracks
            if item["id"] == "p05_engineering_rehearsal_loop"
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
    status = "ready"
    processing = daily_check.get("status") == "processing" or (
        visibility.get("category") == "processing"
    )
    if hard_blockers:
        status = "blocked"
    elif monitor_status == "deployment_issue":
        status = DEPLOYMENT_ISSUE_STATUS
    elif monitor_refresh_needed and waiting_for_market and p05_ready:
        status = MONITOR_REFRESH_STATUS
    elif product_gaps or not p05_ready:
        status = "degraded"
    elif processing and p05_ready:
        status = "processing"
    elif waiting_for_market and p05_ready:
        status = "waiting_for_market"
    completion_boundary = _completion_boundary(
        checks=checks,
        waiting_for_market=waiting_for_market,
        p05_ready=p05_ready,
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
            p05_ready=p05_ready,
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
        if not hard_blockers and (product_gaps or not p05_ready):
            status = "degraded"

    runtime_status = _runtime_status_for(
        status=status,
        waiting_for_market=waiting_for_market,
    )
    if status == MONITOR_REFRESH_STATUS:
        runtime_status = "waiting_for_market"
    elif status == DEPLOYMENT_ISSUE_STATUS:
        runtime_status = "temporarily_unavailable"
    owner_status = _owner_status_for(
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_intervention_required=bool(hard_blockers),
    )

    return {
        "schema": SCHEMA,
        "status": status,
        "runtime_status": runtime_status,
        "monitor_status": monitor_status,
        "owner_status": owner_status,
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
            "state": (
                "等待机会"
                if status in {"waiting_for_market", MONITOR_REFRESH_STATUS}
                else _owner_state(status)
            ),
            "current_action": (
                "继续等待市场机会"
                if status == "waiting_for_market"
                else "刷新本地 runtime monitor 缓存"
                if status in {"needs_refresh", MONITOR_REFRESH_STATUS}
                else "等待系统完成收口"
                if status == "processing"
                else "处理非市场收口缺口"
                if status == "degraded"
                else "处理目标进度阻断"
            ),
            "owner_intervention_required": bool(hard_blockers),
            "risk_level": "L0 local audit",
            "p0": p0["status"],
            "p05": "ready" if p05_ready else "needs_work",
            "p05_strategy_portfolio": (
                "portfolio_screening_active"
                if strategygroup_portfolio_board
                and _strategygroup_portfolio_board_boundary(
                    strategygroup_portfolio_board
                )["status"]
                == "portfolio_board_ready"
                else "not_generated"
            ),
            "p05_capital_trial": (
                _strategygroup_capital_trial_readiness_bridge_boundary(
                    strategygroup_capital_trial_readiness_bridge
                )["selected_candidate_status"]
                if strategygroup_capital_trial_readiness_bridge
                and _strategygroup_capital_trial_readiness_bridge_boundary(
                    strategygroup_capital_trial_readiness_bridge
                )["status"]
                == "capital_trial_readiness_bridge_ready"
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
        "strategygroup_capital_trial_readiness_bridge_boundary": (
            _strategygroup_capital_trial_readiness_bridge_boundary(
                strategygroup_capital_trial_readiness_bridge
            )
        ),
        "p0_completion_audit_boundary": p0_completion_audit_boundary,
        "checks": {
            "blockers": hard_blockers,
            "product_gaps": product_gaps,
            "runtime_status": runtime_status,
            "monitor_status": monitor_status,
            "owner_status": owner_status,
            "monitor_refresh_needed": monitor_refresh_needed,
            "monitor_refresh_reasons": monitor_refresh_reasons,
            "refresh_required": monitor_refresh_needed,
            "automation_notify": monitor_refresh_needed,
            "owner_notify": bool(hard_blockers),
            "waiting_for_market": waiting_for_market,
            "p05_ready": p05_ready,
            "daily_check_status": daily_check.get("status"),
            "daily_check_notification": notification.get("decision"),
        },
        "tracks": [p0, *p05_tracks],
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
            "strategygroup_capital_trial_readiness_bridge_json": str(
                DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_READINESS_BRIDGE_JSON
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
        "operation_layer_evidence_relay_checked": _dry_run_required_check_present(
            checks,
            "operation_layer_evidence_relay_checked",
        ),
        "scoped_pipeline_operation_layer_handoff_checked": (
            _dry_run_required_check_present(
                checks,
                "scoped_pipeline_operation_layer_handoff_checked",
            )
        ),
        "operation_layer_authorization_chain_guard_checked": (
            _dry_run_required_check_present(
                checks,
                "operation_layer_authorization_chain_guard_checked",
            )
        ),
        "operation_layer_standing_authorization_relay_checked": (
            _dry_run_required_check_present(
                checks,
                "operation_layer_standing_authorization_relay_checked",
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
        "finalgate_to_operation_layer_evidence_covered": (
            fast_chain_checks["operation_layer_evidence_relay_checked"]
            and fast_chain_checks["scoped_pipeline_operation_layer_handoff_checked"]
        ),
        "operation_layer_authorization_guard_covered": fast_chain_checks[
            "operation_layer_authorization_chain_guard_checked"
        ]
        and fast_chain_checks["operation_layer_standing_authorization_relay_checked"],
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
            checks.get("waiting_for_market") is True
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
        and isinstance(live_cutover_readiness.get("sections"), list)
    )
    if not has_full_audit_inputs:
        return {
            "status": "not_generated_legacy_cutover_packet",
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
    p05_ready: bool,
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
        waiting_for_market and p05_ready and not hard_blockers and not product_gaps
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
    waiting = checks.get("waiting_for_market") is True or daily_check.get("status") == "waiting_for_market"
    processing = daily_check.get("status") == "processing" or (
        visibility.get("category") == "processing"
    )
    if blockers:
        status = "blocked"
        owner_state = "安全或工程阻断"
        next_action = "先处理阻断，不进入真实订单路径"
    elif waiting:
        status = "waiting_for_market"
        owner_state = "等待市场机会"
        next_action = "等待 fresh signal 后推进官方链路"
    elif processing:
        status = "processing"
        owner_state = str(owner.get("state") or visibility.get("label") or "处理中")
        next_action = "等待系统完成收口"
    else:
        status = "ready"
        owner_state = str(owner.get("state") or visibility.get("label") or "运行中")
        next_action = "fresh signal 已出现时推进官方链路"
    return {
        "id": "p0_live_closure",
        "label": "P0 第一笔边界内真实订单闭环",
        "status": status,
        "owner_state": owner_state,
        "next_action": next_action,
        "evidence": [
            f"daily_check_status={daily_check.get('status')}",
            f"waiting_for_market={checks.get('waiting_for_market')}",
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
        "default_check",
        "heartbeat_check",
        "routine_status_check",
        "strict_no_server_check",
        "deploy_session_owner_progress_check",
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
        track_id="p05_runtime_interaction_optimization",
        label="P0.5 Runtime Interaction Optimization",
        blockers=blockers,
        evidence=[
            f"interaction={interaction.get('level')}",
            f"remote_interaction_count={interaction.get('remote_interaction_count', 0)}",
            f"collected_interaction={collected_interaction.get('level')}",
            f"collected_remote_interaction_count={collected_interaction.get('remote_interaction_count', 0)}",
            "baseline_low_noise_commands=present" if not missing else "baseline_low_noise_commands=missing",
        ],
        next_action="使用 L0 本地缓存进度，必要时才刷新一次 L1 快照",
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
        track_id="p05_engineering_rehearsal_loop",
        label="P0.5 Engineering Rehearsal Loop",
        blockers=blockers,
        evidence=[
            f"dry_run_audit={progress.get('dry_run_audit')}",
            f"scenario_count={checks.get('runtime_dry_run_scenario_count')}",
            f"chain_ready_segments={ready_segment_text}",
            f"missing_chain_segments={len(missing_chain_segments)}",
            f"goal_chain_ready_segments={ready_goal_segment_text}",
            f"missing_goal_chain_segments={len(missing_goal_chain_segments)}",
        ],
        next_action="保持 dry-run / mock signal / source readiness 日检",
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
        track_id="p05_owner_visibility_loop",
        label="P0.5 Owner Visibility Loop",
        blockers=blockers,
        evidence=[
            f"category={category or 'unknown'}",
            f"notification={notification.get('decision')}",
            f"owner_intervention_required={owner.get('owner_intervention_required')}",
        ],
        next_action="保持 Owner 进度层输出，不要求阅读原始证据包",
    )


def _strategy_review_evidence_closure_track(packet: dict[str, Any]) -> dict[str, Any]:
    boundary = _strategy_review_evidence_closure_boundary(packet)
    blockers = [
        f"strategy_review_evidence_closure:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"phase_1={boundary['phase_1_status']}",
        f"phase_2={boundary['phase_2_status']}",
        f"phase_3={boundary['phase_3_status']}",
        f"evidence_packet_count={boundary['evidence_packet_count']}",
        f"next_owner_decision_count={boundary['next_owner_decision_count']}",
        "owner_policy_confirmation_required_now="
        + str(boundary["owner_policy_confirmation_required_now"]),
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "p05_strategy_review_evidence_closure",
        "label": "P0.5 Strategy Review Evidence Closure",
        "status": "blocked" if blockers else "ready",
        "owner_state": "策略政策待确认" if not blockers else "需处理",
        "next_action": (
            "等待 Owner 策略政策确认，不改变实盘权限"
            if not blockers
            else "修复策略复核证据闭合包"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategy_review_evidence_closure_boundary(
    packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if not packet:
        return {
            "status": "not_generated",
            "phase_1_status": "not_generated",
            "phase_2_status": "not_generated",
            "phase_3_status": "not_generated",
            "evidence_packet_count": 0,
            "next_owner_decision_count": 0,
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "real_order_authority": False,
            "reject_reasons": [],
        }
    phase_status = packet.get("phase_status")
    if not isinstance(phase_status, dict):
        phase_status = {}
    next_package = packet.get("next_owner_decision_package")
    if not isinstance(next_package, dict):
        next_package = {}
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    interaction = packet.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    reject_reasons: list[str] = []
    if packet.get("status") != "review_only_evidence_closure_wave_ready":
        reject_reasons.append("packet_not_ready")
    for key in (
        "real_order_authority",
        "exchange_write_called",
        "final_gate_called",
        "operation_layer_called",
        "order_created",
        "registry_authority_changed",
        "tier_policy_changed",
        "live_profile_changed",
        "mpg_member_live_scope_expanded",
    ):
        if safety.get(key) is True:
            reject_reasons.append(f"forbidden_effect:{key}")
    if interaction.get("remote_interaction_count", 0) not in {0, "0", None}:
        reject_reasons.append("remote_interaction_not_zero")
    return {
        "status": str(packet.get("status") or "unknown"),
        "phase_1_status": str(
            phase_status.get("phase_1_owner_perception_projection") or "unknown"
        ),
        "phase_2_status": str(
            phase_status.get("phase_2_evidence_closure_queue") or "unknown"
        ),
        "phase_3_status": str(
            phase_status.get("phase_3_next_owner_decision_package") or "unknown"
        ),
        "evidence_packet_count": len(
            packet.get("evidence_closure_packets")
            if isinstance(packet.get("evidence_closure_packets"), list)
            else []
        ),
        "next_owner_decision_count": int(next_package.get("decision_count") or 0),
        "owner_policy_confirmation_required_now": (
            next_package.get("owner_policy_confirmation_required_now") is True
        ),
        "runtime_owner_intervention_required": (
            next_package.get("runtime_owner_intervention_required") is True
        ),
        "real_order_authority": safety.get("real_order_authority") is True,
        "reject_reasons": reject_reasons,
    }


def _strategy_review_deep_dive_track(packet: dict[str, Any]) -> dict[str, Any]:
    boundary = _strategy_review_deep_dive_boundary(packet)
    blockers = [
        f"strategy_review_deep_dive:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"phase_1={boundary['phase_1_status']}",
        f"phase_2={boundary['phase_2_status']}",
        f"phase_3={boundary['phase_3_status']}",
        f"deep_dive_packet_count={boundary['deep_dive_packet_count']}",
        f"next_owner_decision_count={boundary['next_owner_decision_count']}",
        "owner_policy_confirmation_required_now="
        + str(boundary["owner_policy_confirmation_required_now"]),
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "p05_strategy_review_deep_dive",
        "label": "P0.5 Strategy Review Deep Dive",
        "status": "blocked" if blockers else "ready",
        "owner_state": "六条线等待政策决策" if not blockers else "需处理",
        "next_action": (
            "等待 Owner 确认六条策略线下一步政策，不改变实盘权限"
            if not blockers
            else "修复策略深挖决策包"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategy_review_deep_dive_boundary(
    packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if not packet:
        return {
            "status": "not_generated",
            "phase_1_status": "not_generated",
            "phase_2_status": "not_generated",
            "phase_3_status": "not_generated",
            "deep_dive_packet_count": 0,
            "next_owner_decision_count": 0,
            "owner_policy_confirmation_required_now": False,
            "runtime_owner_intervention_required": False,
            "real_order_authority": False,
            "reject_reasons": [],
        }
    phase_status = packet.get("phase_status")
    if not isinstance(phase_status, dict):
        phase_status = {}
    next_package = packet.get("owner_decision_package")
    if not isinstance(next_package, dict):
        next_package = {}
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    interaction = packet.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    reject_reasons: list[str] = []
    if packet.get("status") != "review_only_deep_dive_ready_for_owner_decision":
        reject_reasons.append("packet_not_ready")
    for key in (
        "real_order_authority",
        "exchange_write_called",
        "final_gate_called",
        "operation_layer_called",
        "order_created",
        "registry_authority_changed",
        "tier_policy_changed",
        "live_profile_changed",
        "mpg_member_live_scope_expanded",
    ):
        if safety.get(key) is True:
            reject_reasons.append(f"forbidden_effect:{key}")
    if interaction.get("remote_interaction_count", 0) not in {0, "0", None}:
        reject_reasons.append("remote_interaction_not_zero")
    return {
        "status": str(packet.get("status") or "unknown"),
        "phase_1_status": str(
            phase_status.get("phase_1_owner_perception_projection") or "unknown"
        ),
        "phase_2_status": str(
            phase_status.get("phase_2_six_line_deep_dive") or "unknown"
        ),
        "phase_3_status": str(
            phase_status.get("phase_3_owner_policy_decision_package")
            or "unknown"
        ),
        "deep_dive_packet_count": len(
            packet.get("deep_dive_packets")
            if isinstance(packet.get("deep_dive_packets"), list)
            else []
        ),
        "next_owner_decision_count": int(next_package.get("decision_count") or 0),
        "owner_policy_confirmation_required_now": (
            next_package.get("owner_policy_confirmation_required_now") is True
        ),
        "runtime_owner_intervention_required": (
            next_package.get("runtime_owner_intervention_required") is True
        ),
        "real_order_authority": safety.get("real_order_authority") is True,
        "reject_reasons": reject_reasons,
    }


def _strategygroup_portfolio_board_track(packet: dict[str, Any]) -> dict[str, Any]:
    boundary = _strategygroup_portfolio_board_boundary(packet)
    blockers = [
        f"strategygroup_portfolio_board:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"portfolio_row_count={boundary['portfolio_row_count']}",
        f"trial_candidate_count={boundary['trial_candidate_count']}",
        f"engineering_continuation_count={boundary['engineering_continuation_count']}",
        f"owner_policy_decision_count={boundary['owner_policy_decision_count']}",
        f"actionable_now_count={boundary['actionable_now_count']}",
        f"live_permission_change_count={boundary['live_permission_change_count']}",
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "p05_strategygroup_portfolio_board",
        "label": "P0.5 StrategyGroup Portfolio Board",
        "status": "blocked" if blockers else "ready",
        "owner_state": "策略组合筛选中" if not blockers else "需处理",
        "next_action": (
            "继续工程补证队列和 review-only 小资金候选池治理，不改变实盘权限"
            if not blockers
            else "修复 StrategyGroup Portfolio Board 证据或安全边界"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategygroup_portfolio_board_boundary(
    packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if not packet:
        return {
            "status": "not_generated",
            "portfolio_row_count": 0,
            "trial_candidate_count": 0,
            "engineering_continuation_count": 0,
            "owner_policy_decision_count": 0,
            "actionable_now_count": 0,
            "live_permission_change_count": 0,
            "runtime_owner_intervention_required": False,
            "real_order_authority": False,
            "reject_reasons": [],
        }
    summary = packet.get("portfolio_summary")
    if not isinstance(summary, dict):
        summary = {}
    trial_pool = packet.get("trial_candidate_pool")
    if not isinstance(trial_pool, dict):
        trial_pool = {}
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    interaction = packet.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    owner_projection = packet.get("owner_progress_projection")
    if not isinstance(owner_projection, dict):
        owner_projection = {}
    reject_reasons: list[str] = []
    if packet.get("status") != "portfolio_board_ready":
        reject_reasons.append("packet_not_ready")
    if int(summary.get("portfolio_row_count") or 0) < 10:
        reject_reasons.append("portfolio_row_count_below_10")
    if int(trial_pool.get("actionable_now_count") or 0) != 0:
        reject_reasons.append("trial_pool_actionable_now_not_zero")
    if int(trial_pool.get("live_permission_change_count") or 0) != 0:
        reject_reasons.append("trial_pool_live_permission_change_not_zero")
    for key in (
        "real_order_authority",
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
    ):
        if safety.get(key) is True:
            reject_reasons.append(f"forbidden_effect:{key}")
    if interaction.get("remote_interaction_count", 0) not in {0, "0", None}:
        reject_reasons.append("remote_interaction_not_zero")
    return {
        "status": str(packet.get("status") or "unknown"),
        "portfolio_row_count": int(summary.get("portfolio_row_count") or 0),
        "trial_candidate_count": int(trial_pool.get("candidate_count") or 0),
        "engineering_continuation_count": int(
            summary.get("engineering_continuation_count") or 0
        ),
        "owner_policy_decision_count": int(
            summary.get("owner_policy_decision_count") or 0
        ),
        "actionable_now_count": int(trial_pool.get("actionable_now_count") or 0),
        "live_permission_change_count": int(
            trial_pool.get("live_permission_change_count") or 0
        ),
        "runtime_owner_intervention_required": (
            owner_projection.get("owner_intervention_required") is True
        ),
        "real_order_authority": safety.get("real_order_authority") is True,
        "reject_reasons": reject_reasons,
    }


def _strategygroup_capital_trial_readiness_bridge_track(
    packet: dict[str, Any],
) -> dict[str, Any]:
    boundary = _strategygroup_capital_trial_readiness_bridge_boundary(packet)
    blockers = [
        f"strategygroup_capital_trial_readiness_bridge:{item}"
        for item in boundary["reject_reasons"]
    ]
    evidence = [
        f"status={boundary['status']}",
        f"eligibility_row_count={boundary['eligibility_row_count']}",
        f"non_mpg_trial_candidate_count={boundary['non_mpg_trial_candidate_count']}",
        f"selected_non_mpg_strategy_group_id={boundary['selected_non_mpg_strategy_group_id']}",
        f"selected_candidate_status={boundary['selected_candidate_status']}",
        f"trial_packet_generated={boundary['trial_packet_generated']}",
        f"actionable_now_count={boundary['actionable_now_count']}",
        f"live_permission_change_count={boundary['live_permission_change_count']}",
        f"real_order_authority_count={boundary['real_order_authority_count']}",
        "runtime_owner_intervention_required="
        + str(boundary["runtime_owner_intervention_required"]),
    ]
    return {
        "id": "p05_strategygroup_capital_trial_readiness_bridge",
        "label": "P0.5 Capital Trial Readiness Bridge",
        "status": "blocked" if blockers else "ready",
        "owner_state": "资金试验候选准备中" if not blockers else "需处理",
        "next_action": (
            "保留 MI-001 为首个非 MPG 预注册试验候选，继续工程补证和后续政策检查点"
            if not blockers
            else "修复 Capital Trial Readiness Bridge 证据或安全边界"
        ),
        "evidence": evidence,
        "blockers": blockers,
    }


def _strategygroup_capital_trial_readiness_bridge_boundary(
    packet: dict[str, Any] | None,
) -> dict[str, Any]:
    if not packet:
        return {
            "status": "not_generated",
            "eligibility_row_count": 0,
            "non_mpg_trial_candidate_count": 0,
            "selected_non_mpg_strategy_group_id": None,
            "selected_candidate_status": "not_generated",
            "trial_packet_generated": False,
            "actionable_now_count": 0,
            "live_permission_change_count": 0,
            "real_order_authority_count": 0,
            "owner_policy_checkpoint_count": 0,
            "runtime_owner_intervention_required": False,
            "real_order_authority": False,
            "reject_reasons": [],
        }
    summary = packet.get("capital_trial_summary")
    if not isinstance(summary, dict):
        summary = {}
    trial_packet = packet.get("trial_packet_v0")
    if not isinstance(trial_packet, dict):
        trial_packet = {}
    safety = packet.get("safety_invariants")
    if not isinstance(safety, dict):
        safety = {}
    interaction = packet.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    policy = packet.get("owner_policy_checkpoint")
    if not isinstance(policy, dict):
        policy = {}
    reject_reasons: list[str] = []
    if packet.get("status") != "capital_trial_readiness_bridge_ready":
        reject_reasons.append("packet_not_ready")
    if int(summary.get("eligibility_row_count") or 0) < 5:
        reject_reasons.append("eligibility_row_count_below_5")
    if int(summary.get("non_mpg_trial_candidate_count") or 0) < 1:
        reject_reasons.append("non_mpg_trial_candidate_missing")
    selected = str(summary.get("selected_non_mpg_strategy_group_id") or "")
    if not selected or selected == "MPG-001":
        reject_reasons.append("selected_non_mpg_candidate_invalid")
    if summary.get("trial_packet_generated") is not True:
        reject_reasons.append("trial_packet_not_generated")
    if int(summary.get("actionable_now_count") or 0) != 0:
        reject_reasons.append("actionable_now_count_not_zero")
    if int(summary.get("live_permission_change_count") or 0) != 0:
        reject_reasons.append("live_permission_change_count_not_zero")
    if int(summary.get("real_order_authority_count") or 0) != 0:
        reject_reasons.append("real_order_authority_count_not_zero")
    if trial_packet.get("actionable_now") is not False:
        reject_reasons.append("trial_packet_actionable_now_not_false")
    if trial_packet.get("live_permission_change") is not False:
        reject_reasons.append("trial_packet_live_permission_change_not_false")
    if trial_packet.get("real_order_authority") is not False:
        reject_reasons.append("trial_packet_real_order_authority_not_false")
    for key in (
        "actionable_now",
        "real_order_authority",
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
    ):
        if safety.get(key) is True:
            reject_reasons.append(f"forbidden_effect:{key}")
    if interaction.get("remote_interaction_count", 0) not in {0, "0", None}:
        reject_reasons.append("remote_interaction_not_zero")
    if policy.get("runtime_owner_intervention_required") is True:
        reject_reasons.append("owner_policy_checkpoint_became_runtime_intervention")
    return {
        "status": str(packet.get("status") or "unknown"),
        "eligibility_row_count": int(summary.get("eligibility_row_count") or 0),
        "non_mpg_trial_candidate_count": int(
            summary.get("non_mpg_trial_candidate_count") or 0
        ),
        "selected_non_mpg_strategy_group_id": (
            summary.get("selected_non_mpg_strategy_group_id")
        ),
        "selected_candidate_status": str(
            summary.get("selected_candidate_status") or "unknown"
        ),
        "trial_packet_generated": summary.get("trial_packet_generated") is True,
        "actionable_now_count": int(summary.get("actionable_now_count") or 0),
        "live_permission_change_count": int(
            summary.get("live_permission_change_count") or 0
        ),
        "real_order_authority_count": int(
            summary.get("real_order_authority_count") or 0
        ),
        "owner_policy_checkpoint_count": int(
            summary.get("owner_policy_checkpoint_count") or 0
        ),
        "runtime_owner_intervention_required": (
            policy.get("runtime_owner_intervention_required") is True
        ),
        "real_order_authority": safety.get("real_order_authority") is True,
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
        track_id="p05_safety_invariants",
        label="P0.5 Safety Invariants",
        blockers=[f"forbidden_effect:{item}" for item in forbidden_true],
        evidence=[f"forbidden_effect_count={len(forbidden_true)}"],
        next_action="保持不触发 FinalGate、Operation Layer、exchange write 或订单动作",
    )


def _track(
    *,
    track_id: str,
    label: str,
    blockers: list[str],
    evidence: list[str],
    next_action: str,
) -> dict[str, Any]:
    return {
        "id": track_id,
        "label": label,
        "status": "blocked" if blockers else "ready",
        "owner_state": "需处理" if blockers else "已就绪",
        "next_action": next_action if not blockers else "处理该轨道阻断",
        "evidence": evidence,
        "blockers": blockers,
    }


def _owner_state(status: str) -> str:
    if status == "blocked":
        return "暂不可用"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "暂不可用"
    if status == MONITOR_REFRESH_STATUS:
        return "等待机会"
    if status == "needs_refresh":
        return "监控状态需刷新"
    if status == "degraded":
        return "非市场收口待处理"
    if status == "processing":
        return "处理中"
    return "运行中"


def _runtime_status_for(*, status: str, waiting_for_market: bool) -> str:
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "temporarily_unavailable"
    if waiting_for_market or status in {"waiting_for_market", MONITOR_REFRESH_STATUS}:
        return "waiting_for_market"
    if status == "processing":
        return "processing"
    if status in {"blocked", "degraded"}:
        return "temporarily_unavailable"
    return "running"


def _owner_status_for(
    *,
    runtime_status: str,
    monitor_status: str,
    owner_intervention_required: bool,
) -> str:
    if owner_intervention_required:
        return "needs_intervention"
    if runtime_status == "waiting_for_market":
        return "waiting_for_opportunity"
    if runtime_status == "processing":
        return "processing"
    if runtime_status == "temporarily_unavailable":
        return "temporarily_unavailable"
    if monitor_status == "deployment_issue":
        return "temporarily_unavailable"
    return "running"


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
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
    capital_trial = report["strategygroup_capital_trial_readiness_bridge_boundary"]
    lines = [
        "## StrategyGroup Runtime Goal Progress",
        "",
        f"- 报告时间: {report['generated_at_utc']}",
        f"- 当前阶段: {owner['state']}",
        f"- 当前动作: {owner['current_action']}",
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
        "- FinalGate to Operation Layer evidence covered: "
        + _yes_no(
            bool(entry_fast_chain["finalgate_to_operation_layer_evidence_covered"])
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
        f"- Phase 3 next Owner decision package: {strategy_review['phase_3_status']}",
        "- Evidence packet count: "
        + str(strategy_review["evidence_packet_count"]),
        "- Next Owner decision count: "
        + str(strategy_review["next_owner_decision_count"]),
        "- Owner policy confirmation required now: "
        + _yes_no(bool(strategy_review["owner_policy_confirmation_required_now"])),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(strategy_review["runtime_owner_intervention_required"])),
        "- Real order authority: "
        + _yes_no(bool(strategy_review["real_order_authority"])),
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
        f"- Phase 3 next Owner decision package: {strategy_deep_dive['phase_3_status']}",
        "- Deep-dive packet count: "
        + str(strategy_deep_dive["deep_dive_packet_count"]),
        "- Next Owner decision count: "
        + str(strategy_deep_dive["next_owner_decision_count"]),
        "- Owner policy confirmation required now: "
        + _yes_no(bool(strategy_deep_dive["owner_policy_confirmation_required_now"])),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(strategy_deep_dive["runtime_owner_intervention_required"])),
        "- Real order authority: "
        + _yes_no(bool(strategy_deep_dive["real_order_authority"])),
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
        "- Owner policy decision count: "
        + str(portfolio_board["owner_policy_decision_count"]),
        "- Actionable now count: "
        + str(portfolio_board["actionable_now_count"]),
        "- Live permission change count: "
        + str(portfolio_board["live_permission_change_count"]),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(portfolio_board["runtime_owner_intervention_required"])),
        "- Real order authority: "
        + _yes_no(bool(portfolio_board["real_order_authority"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in portfolio_board["reject_reasons"]]
        ),
        "",
        "## StrategyGroup Capital Trial Readiness Bridge Boundary",
        "",
        f"- Status: {capital_trial['status']}",
        "- Eligibility row count: "
        + str(capital_trial["eligibility_row_count"]),
        "- Non-MPG trial candidate count: "
        + str(capital_trial["non_mpg_trial_candidate_count"]),
        "- Selected non-MPG StrategyGroup: "
        + str(capital_trial["selected_non_mpg_strategy_group_id"] or "none"),
        "- Selected candidate status: "
        + str(capital_trial["selected_candidate_status"]),
        "- Trial packet generated: "
        + _yes_no(bool(capital_trial["trial_packet_generated"])),
        "- Actionable now count: "
        + str(capital_trial["actionable_now_count"]),
        "- Live permission change count: "
        + str(capital_trial["live_permission_change_count"]),
        "- Real order authority count: "
        + str(capital_trial["real_order_authority_count"]),
        "- Runtime Owner intervention required: "
        + _yes_no(bool(capital_trial["runtime_owner_intervention_required"])),
        "- Real order authority: "
        + _yes_no(bool(capital_trial["real_order_authority"])),
        "- Reject reasons: "
        + _list_or_none(
            [str(item) for item in capital_trial["reject_reasons"]]
        ),
        "",
        "## Tracks",
        "",
        "| Track | Status | Owner state | Next action | Blockers |",
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
                    str(track["next_action"]),
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
    lines.extend(["", "## Checks", ""])
    lines.append(f"- Waiting for market: {_yes_no(bool(checks['waiting_for_market']))}")
    lines.append(f"- P0.5 ready: {_yes_no(bool(checks['p05_ready']))}")
    lines.append(f"- Blockers: {_list_or_none([str(item) for item in checks['blockers']])}")
    lines.append(
        f"- Product gaps: {_list_or_none([str(item) for item in checks['product_gaps']])}"
    )
    return "\n".join(lines)


def _print_human_report(report: dict[str, Any]) -> None:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    print(f"status={report['status']}")
    print(f"owner_state={owner['state']}")
    print(f"current_action={owner['current_action']}")
    print(f"interaction={interaction['level']}")
    print(f"remote_interaction_count={interaction['remote_interaction_count']}")
    print(f"p05_ready={str(checks['p05_ready']).lower()}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))


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
    packet = runtime_live_cutover_readiness.build_cutover_readiness_packet(
        path.parent / "artifacts"
    )
    _write_text_atomic(
        path,
        json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    return packet


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
        "--strategygroup-capital-trial-readiness-bridge-json",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_READINESS_BRIDGE_JSON),
    )
    parser.add_argument(
        "--no-auto-live-cutover-readiness",
        action="store_true",
        help="Do not build a local live-cutover readiness packet when missing.",
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
