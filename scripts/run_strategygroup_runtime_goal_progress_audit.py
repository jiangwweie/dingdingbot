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
DEFAULT_LIVE_CUTOVER_READINESS_JSON = (
    REPO_ROOT
    / "output/strategygroup-runtime-pilot/live-cutover-readiness/runtime-live-cutover-readiness.json"
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
    report = build_goal_progress_report(
        daily_check=_read_json(Path(args.daily_check_json)),
        baseline=_read_json(Path(args.baseline_json)),
        tier_policy=_read_json(Path(args.tier_policy_json)),
        live_cutover_readiness=live_cutover_readiness,
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
    return 0 if report["status"] in {"ready", "waiting_for_market"} else 2


def build_goal_progress_report(
    *,
    daily_check: dict[str, Any],
    baseline: dict[str, Any],
    tier_policy: dict[str, Any] | None = None,
    live_cutover_readiness: dict[str, Any] | None = None,
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
    product_gaps = _dedupe([*product_gaps, *boundary_product_gaps])
    status = "ready"
    if hard_blockers:
        status = "blocked"
    elif product_gaps or not p05_ready:
        status = "degraded"
    elif waiting_for_market and p05_ready:
        status = "waiting_for_market"
    completion_boundary = _completion_boundary(
        checks=checks,
        waiting_for_market=waiting_for_market,
        p05_ready=p05_ready,
        engineering_rehearsal_ready=engineering_rehearsal_ready,
        hard_blockers=hard_blockers,
        product_gaps=product_gaps,
    )

    return {
        "status": status,
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
            "state": "等待机会" if status == "waiting_for_market" else _owner_state(status),
            "current_action": (
                "继续等待市场机会"
                if status == "waiting_for_market"
                else "处理非市场收口缺口"
                if status == "degraded"
                else "处理目标进度阻断"
            ),
            "owner_intervention_required": bool(hard_blockers),
            "risk_level": "L0 local audit",
            "p0": p0["status"],
            "p05": "ready" if p05_ready else "needs_work",
        },
        "completion_boundary": completion_boundary,
        "entry_fast_chain_boundary": entry_fast_chain_boundary,
        "exit_hardening_boundary": exit_hardening_boundary,
        "strategygroup_tier_boundary": strategygroup_tier_boundary,
        "live_cutover_readiness_boundary": live_cutover_readiness_boundary,
        "checks": {
            "blockers": hard_blockers,
            "product_gaps": product_gaps,
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
            "goal_progress_json": str(DEFAULT_GOAL_PROGRESS_JSON),
            "goal_progress_owner_progress_md": str(
                DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD
            ),
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
        ],
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
) -> dict[str, Any]:
    first_bounded_real_order_complete = (
        checks.get("first_bounded_real_order_complete") is True
    )
    real_order_closure_proven = (
        checks.get("real_order_closure_proven") is True
        or first_bounded_real_order_complete
    )
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
    }


def _p0_track(
    *,
    daily_check: dict[str, Any],
    checks: dict[str, Any],
    owner: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    blockers = [str(item) for item in checks.get("blockers") or []]
    waiting = checks.get("waiting_for_market") is True or daily_check.get("status") == "waiting_for_market"
    if blockers:
        status = "blocked"
        owner_state = "安全或工程阻断"
        next_action = "先处理阻断，不进入真实订单路径"
    elif waiting:
        status = "waiting_for_market"
        owner_state = "等待市场机会"
        next_action = "等待 fresh signal 后推进官方链路"
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
        "running",
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
    if status == "degraded":
        return "非市场收口待处理"
    return "运行中"


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    completion = report["completion_boundary"]
    entry_fast_chain = report["entry_fast_chain_boundary"]
    exit_hardening = report["exit_hardening_boundary"]
    tier_boundary = report["strategygroup_tier_boundary"]
    live_cutover = report["live_cutover_readiness_boundary"]
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
