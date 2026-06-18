#!/usr/bin/env python3
"""Build a low-noise StrategyGroup runtime daily check from one L1 snapshot."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_interaction_levels import (
    annotate_interaction,
    interaction_policy as policy_for_interaction_level,
)

SNAPSHOT_SCRIPT = REPO_ROOT / "scripts" / "probe_tokyo_runtime_snapshot.py"
DEFAULT_BASELINE_JSON = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"
DEFAULT_DAILY_CHECK_CACHE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
)
DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-owner-progress.md"
)
DEFAULT_MAX_CACHE_AGE_MINUTES = 35
DAILY_CHECK_REPORT_SCHEMA_VERSION = 12

ACTIVE_GOAL_STATUSES = {
    "fresh_signal_detected",
    "fresh_signal_processing",
    "action_time_finalgate_ready",
    "operation_layer_ready",
}

ENTRY_FAST_CHAIN_REQUIRED_SEGMENTS = (
    "fresh_signal_fast_auto_chain_checked",
    "required_facts_readiness_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "operation_layer_evidence_relay_checked",
    "scoped_pipeline_operation_layer_handoff_checked",
    "operation_layer_authorization_chain_guard_checked",
)
EXIT_HARDENING_REQUIRED_SEGMENTS = (
    "post_submit_exit_outcome_matrix_checked",
    "reduce_only_recovery_standing_authorization_checked",
)
STRATEGYGROUP_TIER_REQUIRED_SEGMENTS = (
    "strategygroup_adapter_boundary_checked",
    "runtime_tier_policy_checked",
    "new_strategygroups_default_observe_only_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    expected_heads = _resolve_expected_heads(args)
    report = _build_or_read_daily_check_report(args)
    report = _apply_cache_freshness_gate(
        report,
        require_fresh_cache=args.require_fresh_cache,
        max_cache_age_minutes=args.max_cache_age_minutes,
        expected_runtime_head=expected_heads["expected_runtime_head"],
    )
    if args.from_cache:
        report = _annotate_current_read_interaction(report)
    if args.output_json:
        output_path = Path(args.output_json)
        _write_text_atomic(
            output_path,
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    owner_progress_text = _owner_progress_text(
        report,
        max_cache_age_minutes=args.max_cache_age_minutes,
    )
    if args.output_owner_progress:
        output_path = Path(args.output_owner_progress)
        _write_text_atomic(output_path, owner_progress_text + "\n")
    if args.heartbeat:
        print(_heartbeat_xml(report))
    elif args.owner_progress:
        print(owner_progress_text)
    elif args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"ready", "waiting_for_market", "processing"} else 2


def _build_or_read_daily_check_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.auto_cache:
        return _build_auto_cache_daily_check_report(args)
    if args.report_json_path:
        return _read_json(Path(args.report_json_path))
    if args.from_cache:
        if not DEFAULT_DAILY_CHECK_CACHE_JSON.exists():
            return _cache_unavailable_report(
                reason="runtime_progress_cache_missing",
                detail=f"cache not found: {DEFAULT_DAILY_CHECK_CACHE_JSON}",
            )
        return _read_json(DEFAULT_DAILY_CHECK_CACHE_JSON)
    expected_heads = _resolve_expected_heads(args)
    snapshot = (
        _read_json(Path(args.snapshot_json_path))
        if args.snapshot_json_path
        else _run_snapshot(
            expected_runtime_head=expected_heads["expected_runtime_head"],
            expected_frontend_head=expected_heads["expected_frontend_head"],
        )
    )
    return build_daily_check_report(
        snapshot=snapshot,
        max_remote_interactions=args.max_remote_interactions,
    )


def _build_auto_cache_daily_check_report(args: argparse.Namespace) -> dict[str, Any]:
    expected_heads = _resolve_expected_heads(args)
    if DEFAULT_DAILY_CHECK_CACHE_JSON.exists():
        cached = _read_json(DEFAULT_DAILY_CHECK_CACHE_JSON)
        if _is_fresh_cache_report(
            cached,
            max_cache_age_minutes=args.max_cache_age_minutes,
            expected_runtime_head=expected_heads["expected_runtime_head"],
        ):
            return _annotate_current_read_interaction(cached)

    snapshot = (
        _read_json(Path(args.snapshot_json_path))
        if args.snapshot_json_path
        else _run_snapshot(
            expected_runtime_head=expected_heads["expected_runtime_head"],
            expected_frontend_head=expected_heads["expected_frontend_head"],
        )
    )
    report = build_daily_check_report(
        snapshot=snapshot,
        max_remote_interactions=args.max_remote_interactions,
    )
    _write_text_atomic(
        DEFAULT_DAILY_CHECK_CACHE_JSON,
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _write_text_atomic(
        DEFAULT_DAILY_CHECK_OWNER_PROGRESS_MD,
        _owner_progress_text(
            report,
            max_cache_age_minutes=args.max_cache_age_minutes,
        )
        + "\n",
    )
    return report


def build_daily_check_report(
    *,
    snapshot: dict[str, Any],
    max_remote_interactions: int = 1,
) -> dict[str, Any]:
    checks = snapshot.get("checks") if isinstance(snapshot.get("checks"), dict) else {}
    owner_summary = (
        snapshot.get("owner_summary")
        if isinstance(snapshot.get("owner_summary"), dict)
        else {}
    )
    interaction = (
        snapshot.get("interaction") if isinstance(snapshot.get("interaction"), dict) else {}
    )
    inputs = snapshot.get("inputs") if isinstance(snapshot.get("inputs"), dict) else {}
    facts = snapshot.get("facts") if isinstance(snapshot.get("facts"), dict) else {}
    release = facts.get("release") if isinstance(facts.get("release"), dict) else {}
    reports = facts.get("reports") if isinstance(facts.get("reports"), dict) else {}
    goal_status = (
        reports.get("goal_status") if isinstance(reports.get("goal_status"), dict) else {}
    )
    dry_run_summary = (
        reports.get("runtime_dry_run_audit")
        if isinstance(reports.get("runtime_dry_run_audit"), dict)
        else {}
    )
    real_order_readiness_summary = (
        goal_status.get("real_order_readiness_summary")
        if isinstance(goal_status.get("real_order_readiness_summary"), dict)
        else {}
    )
    chain_closure_summary = (
        reports.get("runtime_execution_chain_closure_status")
        if isinstance(reports.get("runtime_execution_chain_closure_status"), dict)
        else {}
    )
    dry_run_scenario_count = _int_or_none(dry_run_summary.get("scenario_count"))
    chain_segments_available = (
        isinstance(chain_closure_summary.get("ready_segments"), list)
        or isinstance(
            chain_closure_summary.get("missing_or_failed_segments"),
            list,
        )
    )
    chain_ready_segments = (
        [str(item) for item in chain_closure_summary.get("ready_segments") or []]
        if chain_segments_available
        else None
    )
    chain_missing_or_failed_segments = (
        [
            str(item)
            for item in chain_closure_summary.get("missing_or_failed_segments") or []
        ]
        if chain_segments_available
        else None
    )
    goal_chain_segments_available = (
        isinstance(chain_closure_summary.get("ready_goal_chain_segments"), list)
        or isinstance(
            chain_closure_summary.get("missing_or_failed_goal_chain_segments"),
            list,
        )
    )
    goal_chain_ready_segments = (
        [
            str(item)
            for item in chain_closure_summary.get("ready_goal_chain_segments") or []
        ]
        if goal_chain_segments_available
        else None
    )
    goal_chain_missing_or_failed_segments = (
        [
            str(item)
            for item in chain_closure_summary.get(
                "missing_or_failed_goal_chain_segments"
            )
            or []
        ]
        if goal_chain_segments_available
        else None
    )
    entry_fast_chain_boundary_ready = _required_segments_ready(
        ready_segments=chain_ready_segments,
        missing_or_failed_segments=chain_missing_or_failed_segments,
        required_segments=ENTRY_FAST_CHAIN_REQUIRED_SEGMENTS,
    )
    exit_hardening_boundary_ready = _required_segments_ready(
        ready_segments=chain_ready_segments,
        missing_or_failed_segments=chain_missing_or_failed_segments,
        required_segments=EXIT_HARDENING_REQUIRED_SEGMENTS,
    )
    strategygroup_tier_boundary_ready = _required_segments_ready(
        ready_segments=chain_ready_segments,
        missing_or_failed_segments=chain_missing_or_failed_segments,
        required_segments=STRATEGYGROUP_TIER_REQUIRED_SEGMENTS,
    )

    blockers = list(checks.get("blockers") or [])
    product_gaps = list(checks.get("product_gaps") or [])
    hard_failures = []
    warnings = []
    live_closure_status = str(
        checks.get("runtime_live_closure_evidence_status") or "not_generated"
    )
    live_closure_reject_reasons = [
        str(item)
        for item in checks.get("runtime_live_closure_evidence_reject_reasons") or []
    ]
    live_closure_processing_claimed = live_closure_status in {
        "in_progress",
        "live_closure_in_progress",
    }
    live_closure_rejected = live_closure_status in {
        "rejected",
        "blocked_live_closure_rejected",
    }

    if snapshot.get("status") == "blocked":
        hard_failures.append("l1_snapshot_blocked")
    remote_interaction_count = _int_or_zero(
        interaction.get("remote_interaction_count")
    )
    if remote_interaction_count > max_remote_interactions:
        hard_failures.append(
            "daily_check_remote_interaction_budget_exceeded:"
            f"{remote_interaction_count}>{max_remote_interactions}"
        )
    if interaction.get("mutates_remote_files") is True:
        hard_failures.append("daily_check_snapshot_mutated_remote")
    if interaction.get("approaches_real_order") is True:
        hard_failures.append("daily_check_snapshot_approached_real_order")
    if interaction.get("calls_exchange_write") is True:
        hard_failures.append("daily_check_snapshot_called_exchange_write")

    if live_closure_rejected:
        product_gaps.extend(
            f"live_closure_evidence:{item}"
            for item in (live_closure_reject_reasons or ["rejected"])
        )
    product_gaps = _dedupe([str(item) for item in product_gaps])

    if product_gaps:
        warnings.extend(f"product_gap:{item}" for item in product_gaps)

    first_bounded_real_order_complete = (
        checks.get("first_bounded_real_order_complete") is True
    )
    real_order_closure_proven = checks.get("real_order_closure_proven") is True
    real_order_waiting_keys = {
        str(item)
        for item in real_order_readiness_summary.get("waiting_keys") or []
    }
    goal_status_value = str(goal_status.get("status") or "")
    goal_processing = (
        goal_status_value in ACTIVE_GOAL_STATUSES
        or goal_status.get("fresh_signal_present") is True
    )
    waiting_for_market = _is_waiting_for_market(owner_summary, goal_status)
    if goal_processing:
        waiting_for_market = False
    live_closure_processing = live_closure_processing_claimed and not (
        waiting_for_market and "fresh_signal" in real_order_waiting_keys
    )
    if (
        (first_bounded_real_order_complete and real_order_closure_proven)
        or live_closure_processing
        or live_closure_rejected
    ):
        waiting_for_market = False
    status = "ready"
    if blockers or hard_failures:
        status = "blocked"
    elif product_gaps:
        status = "degraded"
    elif goal_processing and not waiting_for_market:
        status = "processing"
    elif live_closure_processing:
        status = "processing"
    elif waiting_for_market:
        status = "waiting_for_market"
    visibility = _owner_visibility(
        status=status,
        blockers=[*blockers, *hard_failures],
        product_gaps=product_gaps,
        waiting_for_market=waiting_for_market,
    )
    checks_report = {
        "blockers": _dedupe([*blockers, *hard_failures]),
        "warnings": _dedupe(warnings),
        "product_gaps": product_gaps,
        "waiting_for_market": waiting_for_market,
        "runtime_ready": checks.get("backend_active") is True,
        "watcher_ready": checks.get("watcher_timer_active") is True,
        "source_readiness_ready": checks.get("source_readiness_ready") is True,
        "runtime_dry_run_audit_passed": (
            checks.get("runtime_dry_run_audit_passed") is True
        ),
        "runtime_dry_run_required_checks_present": (
            checks.get("runtime_dry_run_required_checks_present") is True
        ),
        "fresh_signal_notification_policy_checked": True,
        "runtime_dry_run_missing_required_checks": list(
            checks.get("runtime_dry_run_missing_required_checks") or []
        ),
        "runtime_dry_run_scenario_count": dry_run_scenario_count,
        "runtime_execution_chain_closure_status_ready": (
            checks.get("runtime_execution_chain_closure_status_ready") is True
        ),
        "runtime_live_closure_evidence_status": live_closure_status,
        "runtime_live_closure_evidence_reject_reasons": live_closure_reject_reasons,
        "first_bounded_real_order_complete": first_bounded_real_order_complete,
        "real_order_closure_proven": real_order_closure_proven,
        "runtime_execution_chain_ready_segment_count": (
            len(chain_ready_segments)
            if chain_ready_segments is not None
            else None
        ),
        "runtime_execution_chain_ready_segments": chain_ready_segments or [],
        "runtime_execution_chain_missing_or_failed_segments": (
            chain_missing_or_failed_segments or []
        ),
        "runtime_execution_goal_chain_ready_segment_count": (
            len(goal_chain_ready_segments)
            if goal_chain_ready_segments is not None
            else None
        ),
        "runtime_execution_goal_chain_ready_segments": goal_chain_ready_segments or [],
        "runtime_execution_goal_chain_missing_or_failed_segments": (
            goal_chain_missing_or_failed_segments or []
        ),
        "entry_fast_chain_boundary_ready": entry_fast_chain_boundary_ready,
        "exit_hardening_boundary_ready": exit_hardening_boundary_ready,
        "strategygroup_tier_boundary_ready": strategygroup_tier_boundary_ready,
        "real_order_readiness_summary": dict(real_order_readiness_summary),
        "frontend_scope": checks.get("frontend_scope") or "externalized",
    }

    return {
        "schema_version": DAILY_CHECK_REPORT_SCHEMA_VERSION,
        "status": status,
        "scope": "strategygroup_runtime_daily_check",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "expected_runtime_head": _optional_text(
                inputs.get("expected_runtime_head")
            ),
            "runtime_head": _optional_text(release.get("head")),
            "runtime_release_path": _optional_text(release.get("current_realpath")),
        },
        "interaction": annotate_interaction({
            "level": "L1_daily_check_from_snapshot",
            "uses_snapshot_level": interaction.get("level"),
            "remote_interaction_count": remote_interaction_count,
            "max_remote_interactions": max_remote_interactions,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        }),
        "owner_summary": {
            "state": visibility["label"],
            "current_action": _daily_next_action(
                status=status,
                owner_summary=owner_summary,
                blockers=blockers,
                product_gaps=product_gaps,
            ),
            "owner_intervention_required": visibility["owner_intervention_required"],
            "risk_level": "L1 read-only",
            "visibility": visibility,
            "progress": {
                "runtime": owner_summary.get("runtime"),
                "watcher": owner_summary.get("watcher"),
                "source_readiness": owner_summary.get("source_readiness"),
                "dry_run_audit": owner_summary.get("dry_run_audit"),
                "dry_run_audit_scenarios": dry_run_scenario_count,
                "chain_closure": owner_summary.get("chain_closure")
                or chain_closure_summary.get("status"),
                "chain_closure_ready_segments": (
                    len(chain_ready_segments)
                    if chain_ready_segments is not None
                    else None
                ),
                "chain_closure_missing_or_failed_segments": (
                    chain_missing_or_failed_segments or []
                ),
                "goal_chain_ready_segments": (
                    len(goal_chain_ready_segments)
                    if goal_chain_ready_segments is not None
                    else None
                ),
                "goal_chain_missing_or_failed_segments": (
                    goal_chain_missing_or_failed_segments or []
                ),
                "entry_fast_chain_boundary": _boundary_progress_label(
                    entry_fast_chain_boundary_ready
                ),
                "exit_hardening_boundary": _boundary_progress_label(
                    exit_hardening_boundary_ready
                ),
                "strategygroup_tier_boundary": _boundary_progress_label(
                    strategygroup_tier_boundary_ready
                ),
                "real_order_readiness": dict(real_order_readiness_summary),
                "live_closure": (
                    checks.get("runtime_live_closure_evidence_status")
                    or "not_generated"
                ),
                "frontend": owner_summary.get("frontend") or "外部项目",
            },
        },
        "checks": checks_report,
        "notification": _notification_decision(
            status=status,
            checks=checks_report,
            visibility=visibility,
        ),
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _notification_decision(
    *,
    status: str,
    checks: dict[str, Any],
    visibility: dict[str, Any],
) -> dict[str, Any]:
    quiet_waiting = (
        status == "waiting_for_market"
        and checks.get("waiting_for_market") is True
        and checks.get("blockers") == []
        and checks.get("warnings") == []
        and checks.get("product_gaps") == []
        and checks.get("runtime_ready") is True
        and checks.get("watcher_ready") is True
        and checks.get("source_readiness_ready") is True
        and checks.get("runtime_dry_run_audit_passed") is True
        and checks.get("runtime_dry_run_required_checks_present") is True
        and checks.get("runtime_execution_chain_closure_status_ready") is True
        and checks.get("entry_fast_chain_boundary_ready") is True
        and checks.get("exit_hardening_boundary_ready") is True
        and checks.get("strategygroup_tier_boundary_ready") is True
    )
    if quiet_waiting:
        return {
            "decision": "DONT_NOTIFY",
            "reason": "healthy_waiting_for_market",
            "message": "自动化正常运行，当前没有可用市场机会",
            "owner_intervention_required": False,
        }
    return {
        "decision": "NOTIFY",
        "reason": _notification_reason(status=status, checks=checks, visibility=visibility),
        "message": str(visibility.get("detail") or "运行状态需要处理"),
        "owner_intervention_required": bool(
            visibility.get("owner_intervention_required")
        ),
    }


def _notification_reason(
    *,
    status: str,
    checks: dict[str, Any],
    visibility: dict[str, Any],
) -> str:
    if checks.get("blockers"):
        return "blocker_present"
    if checks.get("product_gaps"):
        return "product_gap_present"
    if checks.get("warnings"):
        return "warning_present"
    if checks.get("runtime_dry_run_audit_passed") is not True:
        return "dry_run_audit_not_passed"
    if checks.get("runtime_dry_run_required_checks_present") is not True:
        return "dry_run_required_checks_missing"
    if checks.get("runtime_execution_chain_closure_status_ready") is not True:
        return "runtime_execution_chain_closure_status_not_ready"
    if checks.get("entry_fast_chain_boundary_ready") is not True:
        return "entry_fast_chain_boundary_not_ready"
    if checks.get("exit_hardening_boundary_ready") is not True:
        return "exit_hardening_boundary_not_ready"
    if checks.get("strategygroup_tier_boundary_ready") is not True:
        return "strategygroup_tier_boundary_not_ready"
    category = str(visibility.get("category") or "")
    if category and category != "waiting_for_market":
        return category
    if status != "waiting_for_market":
        return f"status_{status}"
    return "not_quiet_waiting_for_market"


def _daily_next_action(
    *,
    status: str,
    owner_summary: dict[str, Any],
    blockers: list[str],
    product_gaps: list[str],
) -> str:
    if blockers:
        visibility = _owner_visibility(
            status=status,
            blockers=blockers,
            product_gaps=product_gaps,
            waiting_for_market=False,
        )
        return str(visibility["next_action"])
    if product_gaps:
        if any(str(item).startswith("live_closure_evidence:") for item in product_gaps):
            return "处理真实闭环证据异常"
        return "处理产品状态缺口"
    if status == "waiting_for_market":
        return "继续等待市场机会"
    if status == "processing":
        return "等待系统完成收口"
    return str(owner_summary.get("current_action") or "继续保持监控")


def _owner_visibility(
    *,
    status: str,
    blockers: list[str],
    product_gaps: list[str],
    waiting_for_market: bool,
) -> dict[str, Any]:
    if blockers:
        category = (
            "safety_blocker"
            if any(_is_safety_blocker(blocker) for blocker in blockers)
            else "engineering_blocker"
        )
        return {
            "category": category,
            "label": "安全边界阻断" if category == "safety_blocker" else "工程状态暂不可用",
            "detail": _owner_blocker_detail(blockers),
            "next_action": (
                "等待系统处理安全状态"
                if category == "safety_blocker"
                else "处理工程状态阻断"
            ),
            "owner_intervention_required": category == "safety_blocker",
        }
    if product_gaps:
        if any(str(item).startswith("live_closure_evidence:") for item in product_gaps):
            return {
                "category": "engineering_blocker",
                "label": "工程状态暂不可用",
                "detail": "真实闭环证据不可用，等待系统处理",
                "next_action": "处理真实闭环证据异常",
                "owner_intervention_required": False,
            }
        return {
            "category": "engineering_blocker",
            "label": "工程状态暂不可用",
            "detail": "产品状态需要修复",
            "next_action": "处理产品状态缺口",
            "owner_intervention_required": False,
        }
    if waiting_for_market or status == "waiting_for_market":
        return {
            "category": "waiting_for_market",
            "label": "等待机会",
            "detail": "自动化正常运行，当前没有 fresh signal",
            "next_action": "继续等待市场机会",
            "owner_intervention_required": False,
        }
    if status == "processing":
        return {
            "category": "processing",
            "label": "处理中",
            "detail": "系统正在处理真实订单闭环证据",
            "next_action": "等待系统完成收口",
            "owner_intervention_required": False,
        }
    return {
        "category": "running",
        "label": "运行中",
        "detail": "自动化正常运行",
        "next_action": "继续保持监控",
        "owner_intervention_required": False,
    }


def _is_safety_blocker(blocker: str) -> bool:
    tokens = (
        "active_position",
        "open_order",
        "protection",
        "missing_budget",
        "budget_missing",
        "budget_exhausted",
        "insufficient_budget",
        "duplicate",
        "hard_safety",
        "finalgate",
        "operation_layer",
        "exchange_write",
        "real_order",
        "scope_mismatch",
        "stale_fact",
        "missing_fact",
    )
    lowered = blocker.lower()
    return any(token in lowered for token in tokens)


def _owner_blocker_detail(blockers: list[str]) -> str:
    if any(_is_safety_blocker(blocker) for blocker in blockers):
        return "真实订单保持关闭，等待安全状态恢复"
    return "运行、观察、部署或状态源需要恢复"


def _is_waiting_for_market(
    owner_summary: dict[str, Any],
    goal_status: dict[str, Any],
) -> bool:
    owner_state = str(owner_summary.get("state") or "")
    goal_state = str(goal_status.get("status") or "")
    return (
        owner_state == "等待机会"
        or goal_state in {"waiting_for_signal", "waiting_for_market"}
        or goal_status.get("fresh_signal_present") is False
    )


def _run_snapshot(
    *,
    expected_runtime_head: str | None,
    expected_frontend_head: str | None,
) -> dict[str, Any]:
    command = [sys.executable, str(SNAPSHOT_SCRIPT), "--json"]
    if expected_runtime_head:
        command.extend(["--expected-runtime-head", expected_runtime_head])
    if expected_frontend_head:
        command.extend(["--expected-frontend-head", expected_frontend_head])
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode not in {0, 2}:
        return {
            "status": "blocked",
            "checks": {"blockers": ["l1_snapshot_command_failed"]},
            "owner_summary": {
                "state": "暂不可用",
                "current_action": "检查 L1 快照命令",
            },
            "interaction": {
                "level": "L1_readonly_snapshot",
                "remote_interaction_count": 1,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_exchange_write": False,
            },
            "error": completed.stderr[-2000:] or completed.stdout[-2000:],
        }
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "blocked",
            "checks": {"blockers": ["l1_snapshot_output_not_json"]},
            "owner_summary": {
                "state": "暂不可用",
                "current_action": "检查 L1 快照输出",
            },
            "interaction": {
                "level": "L1_readonly_snapshot",
                "remote_interaction_count": 1,
                "mutates_remote_files": False,
                "approaches_real_order": False,
                "calls_exchange_write": False,
            },
            "error": str(exc),
        }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _write_text_atomic(path: Path, text: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _cache_unavailable_report(*, reason: str, detail: str) -> dict[str, Any]:
    return {
        "schema_version": DAILY_CHECK_REPORT_SCHEMA_VERSION,
        "status": "blocked",
        "scope": "strategygroup_runtime_daily_check",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": annotate_interaction({
            "level": "L0_local_cache_read",
            "uses_snapshot_level": None,
            "remote_interaction_count": 0,
            "max_remote_interactions": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        }),
        "owner_summary": {
            "state": "工程状态暂不可用",
            "current_action": "等待自动化刷新本地 runtime monitor 缓存",
            "owner_intervention_required": False,
            "risk_level": "L0 local cache only",
            "visibility": {
                "category": "engineering_blocker",
                "label": "工程状态暂不可用",
                "detail": detail,
                "next_action": "等待自动化刷新本地 runtime monitor 缓存",
                "owner_intervention_required": False,
            },
            "progress": {
                "runtime": "unknown",
                "watcher": "unknown",
            "source_readiness": "unknown",
            "dry_run_audit": "unknown",
            "frontend": "外部项目",
            },
        },
        "checks": {
            "blockers": [reason],
            "warnings": [],
            "product_gaps": [],
            "waiting_for_market": False,
            "runtime_ready": False,
            "watcher_ready": False,
            "source_readiness_ready": False,
            "runtime_dry_run_audit_passed": False,
            "runtime_dry_run_required_checks_present": False,
            "fresh_signal_notification_policy_checked": False,
            "runtime_dry_run_missing_required_checks": [],
            "frontend_scope": "externalized",
        },
        "notification": {
            "decision": "NOTIFY",
            "reason": reason,
            "message": detail,
            "owner_intervention_required": False,
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _apply_cache_freshness_gate(
    report: dict[str, Any],
    *,
    require_fresh_cache: bool,
    max_cache_age_minutes: int,
    expected_runtime_head: str | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    if not require_fresh_cache:
        return report
    if report.get("schema_version") != DAILY_CHECK_REPORT_SCHEMA_VERSION:
        return _gated_cache_report(
            report,
            reason="runtime_progress_cache_schema_stale",
            detail="本地 runtime monitor 缓存结构已过期，等待自动化刷新",
        )
    cache_status = _cache_status_text(
        generated_at=str(report.get("generated_at_utc") or "unknown"),
        now_utc=now_utc,
        max_cache_age_minutes=max_cache_age_minutes,
    )
    if cache_status == "fresh":
        if _cache_runtime_head_matches(
            report,
            expected_runtime_head=expected_runtime_head,
        ):
            return report
        return _gated_cache_report(
            report,
            reason="runtime_progress_cache_runtime_head_stale",
            detail="本地 runtime monitor 缓存对应的部署 head 已过期，等待自动化刷新",
        )
    reason = (
        "runtime_progress_cache_timestamp_unknown"
        if cache_status == "unknown"
        else "runtime_progress_cache_stale"
    )
    detail = (
        "本地 runtime monitor 缓存时间不可用，等待自动化刷新"
        if cache_status == "unknown"
        else "本地 runtime monitor 缓存已过期，等待自动化刷新"
    )
    return _gated_cache_report(report, reason=reason, detail=detail)


def _is_fresh_cache_report(
    report: dict[str, Any],
    *,
    max_cache_age_minutes: int,
    expected_runtime_head: str | None = None,
) -> bool:
    if report.get("schema_version") != DAILY_CHECK_REPORT_SCHEMA_VERSION:
        return False
    if (
        _cache_status_text(
            generated_at=str(report.get("generated_at_utc") or "unknown"),
            max_cache_age_minutes=max_cache_age_minutes,
        )
        != "fresh"
    ):
        return False
    return _cache_runtime_head_matches(
        report,
        expected_runtime_head=expected_runtime_head,
    )


def _cache_runtime_head_matches(
    report: dict[str, Any],
    *,
    expected_runtime_head: str | None,
) -> bool:
    if not expected_runtime_head:
        return True
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    cached_runtime_head = _optional_text(source.get("runtime_head"))
    cached_expected_head = _optional_text(source.get("expected_runtime_head"))
    return (
        cached_runtime_head == expected_runtime_head
        and cached_expected_head == expected_runtime_head
    )


def _gated_cache_report(
    report: dict[str, Any],
    *,
    reason: str,
    detail: str,
) -> dict[str, Any]:
    gated = dict(report)
    cached_interaction = (
        dict(gated.get("interaction"))
        if isinstance(gated.get("interaction"), dict)
        else {}
    )
    gated["cached_report_interaction"] = cached_interaction
    gated["interaction"] = annotate_interaction({
        "level": "L0_local_cache_gate",
        "uses_snapshot_level": cached_interaction.get("uses_snapshot_level")
        or cached_interaction.get("level"),
        "remote_interaction_count": 0,
        "max_remote_interactions": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    })
    checks = dict(gated.get("checks") if isinstance(gated.get("checks"), dict) else {})
    blockers = _dedupe([*[str(item) for item in checks.get("blockers") or []], reason])
    checks["blockers"] = blockers
    gated["checks"] = checks
    gated["status"] = "blocked"

    visibility = _owner_visibility(
        status="blocked",
        blockers=blockers,
        product_gaps=[str(item) for item in checks.get("product_gaps") or []],
        waiting_for_market=False,
    )
    visibility["detail"] = detail
    visibility["next_action"] = "等待自动化刷新本地 runtime monitor 缓存"

    owner = dict(gated.get("owner_summary") if isinstance(gated.get("owner_summary"), dict) else {})
    owner["state"] = visibility["label"]
    owner["current_action"] = visibility["next_action"]
    owner["owner_intervention_required"] = False
    owner["risk_level"] = "L0 local cache only"
    owner["visibility"] = visibility
    gated["owner_summary"] = owner
    gated["notification"] = {
        "decision": "NOTIFY",
        "reason": reason,
        "message": detail,
        "owner_intervention_required": False,
    }
    return gated


def _annotate_current_read_interaction(report: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(report)
    cached_interaction = (
        dict(annotated.get("interaction"))
        if isinstance(annotated.get("interaction"), dict)
        else {}
    )
    current_read_interaction = annotate_interaction({
        "level": "L0_local_cache_read",
        "uses_snapshot_level": cached_interaction.get("uses_snapshot_level")
        or cached_interaction.get("level"),
        "remote_interaction_count": 0,
        "max_remote_interactions": 0,
        "mutates_remote_files": False,
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    })
    annotated["cached_report_interaction"] = cached_interaction
    annotated["current_read_interaction"] = current_read_interaction
    annotated["interaction"] = current_read_interaction
    owner = (
        dict(annotated.get("owner_summary"))
        if isinstance(annotated.get("owner_summary"), dict)
        else {}
    )
    owner["risk_level"] = "L0 local cache only"
    annotated["owner_summary"] = owner
    return annotated


def _resolve_expected_heads(args: argparse.Namespace) -> dict[str, str | None]:
    baseline = _read_monitor_baseline(Path(args.baseline_json)) if args.baseline_json else {}
    return {
        "expected_runtime_head": args.expected_runtime_head
        or _optional_text(baseline.get("expected_runtime_head")),
        "expected_frontend_head": args.expected_frontend_head
        or _optional_text(baseline.get("expected_frontend_head")),
    }


def _read_monitor_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_segments_ready(
    *,
    ready_segments: list[str] | None,
    missing_or_failed_segments: list[str] | None,
    required_segments: tuple[str, ...],
) -> bool | None:
    if ready_segments is None or missing_or_failed_segments is None:
        return None
    ready = set(ready_segments)
    missing_or_failed = set(missing_or_failed_segments)
    return all(
        segment in ready and segment not in missing_or_failed
        for segment in required_segments
    )


def _boundary_progress_label(value: bool | None) -> str:
    if value is True:
        return "ready"
    if value is False:
        return "needs_work"
    return "unknown"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _heartbeat_xml(report: dict[str, Any]) -> str:
    notification = report.get("notification")
    if not isinstance(notification, dict):
        notification = {}
    decision = str(notification.get("decision") or "NOTIFY")
    if decision not in {"DONT_NOTIFY", "NOTIFY"}:
        decision = "NOTIFY"
    message = str(notification.get("message") or "运行状态需要处理")
    automation_id = "tokyo-runtime-quiet-monitor"
    return "\n".join(
        [
            "<heartbeat>",
            f"  <automation_id>{escape(automation_id)}</automation_id>",
            f"  <decision>{escape(decision)}</decision>",
            f"  <message>{escape(message)}</message>",
            "</heartbeat>",
        ]
    )


def _owner_progress_text(
    report: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    max_cache_age_minutes: int = DEFAULT_MAX_CACHE_AGE_MINUTES,
) -> str:
    owner = report.get("owner_summary")
    if not isinstance(owner, dict):
        owner = {}
    checks = report.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    interaction = report.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    current_read_interaction = report.get("current_read_interaction")
    if not isinstance(current_read_interaction, dict):
        current_read_interaction = {}
    cached_report_interaction = report.get("cached_report_interaction")
    if not isinstance(cached_report_interaction, dict):
        cached_report_interaction = {}
    report_collection_interaction = cached_report_interaction or interaction
    notification = report.get("notification")
    if not isinstance(notification, dict):
        notification = {}
    progress = owner.get("progress")
    if not isinstance(progress, dict):
        progress = {}
    interaction_policy = report_collection_interaction.get("policy")
    if not isinstance(interaction_policy, dict):
        interaction_policy = policy_for_interaction_level(
            str(report_collection_interaction.get("level") or "unknown")
        )
    current_read_policy = current_read_interaction.get("policy")
    if not isinstance(current_read_policy, dict):
        current_read_policy = policy_for_interaction_level(
            str(current_read_interaction.get("level") or "unknown")
        )

    blockers = [str(item) for item in checks.get("blockers") or []]
    product_gaps = [str(item) for item in checks.get("product_gaps") or []]
    warnings = [str(item) for item in checks.get("warnings") or []]
    missing_dry_run_checks = [
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
    generated_at = str(report.get("generated_at_utc") or "unknown")
    cache_age = _cache_age_text(generated_at=generated_at, now_utc=now_utc)
    cache_status = _cache_status_text(
        generated_at=generated_at,
        now_utc=now_utc,
        max_cache_age_minutes=max_cache_age_minutes,
    )

    lines = [
        "## StrategyGroup Runtime Progress",
        "",
        f"- 报告时间: {generated_at}",
        f"- 缓存年龄: {cache_age}",
        f"- 缓存状态: {cache_status}",
        f"- 当前阶段: {owner.get('state') or report.get('status') or 'unknown'}",
        f"- 当前动作: {owner.get('current_action') or 'unknown'}",
        f"- 风险等级: {owner.get('risk_level') or 'unknown'}",
        (
            "- Owner 介入: "
            + _yes_no(bool(owner.get("owner_intervention_required")))
        ),
        f"- 通知决策: {notification.get('decision') or 'UNKNOWN'}",
        f"- 通知原因: {notification.get('reason') or 'unknown'}",
        (
            f"- 本次读取等级: {current_read_interaction.get('level')}"
            if current_read_interaction
            else f"- 交互等级: {interaction.get('level') or 'unknown'}"
        ),
        *(
            [f"- 本次读取口径: {current_read_policy.get('owner_label') or 'unknown'}"]
            if current_read_interaction
            else [f"- 交互口径: {interaction_policy.get('owner_label') or 'unknown'}"]
        ),
        (
            f"- 本次远端交互次数: {current_read_interaction.get('remote_interaction_count', 0)}"
            if current_read_interaction
            else f"- 远端交互次数: {interaction.get('remote_interaction_count', 0)}"
        ),
        (
            f"- 报告采集等级: {report_collection_interaction.get('level') or 'unknown'}"
            if current_read_interaction
            else f"- 远端交互预算: {interaction.get('max_remote_interactions', 1)}"
        ),
        *(
            [f"- 报告采集口径: {interaction_policy.get('owner_label') or 'unknown'}"]
            if current_read_interaction
            else []
        ),
        (
            f"- 报告采集远端交互次数: {report_collection_interaction.get('remote_interaction_count', 0)}"
            if current_read_interaction
            else "- 服务器修改: " + _yes_no(bool(interaction.get("mutates_remote_files")))
        ),
        *(
            [
                f"- 报告采集远端交互预算: {report_collection_interaction.get('max_remote_interactions', 1)}",
                "- 服务器修改: "
                + _yes_no(bool(current_read_interaction.get("mutates_remote_files"))),
            ]
            if current_read_interaction
            else []
        ),
        "- 接近真实订单: "
        + _yes_no(
            bool(
                (
                    current_read_interaction
                    or interaction
                ).get("approaches_real_order")
            )
        ),
        "- 交易所写入: "
        + _yes_no(
            bool(
                (
                    current_read_interaction
                    or interaction
                ).get("calls_exchange_write")
            )
        ),
        "",
        "## Progress",
        "",
        f"- Runtime: {progress.get('runtime') or 'unknown'}",
        f"- Watcher: {progress.get('watcher') or 'unknown'}",
        f"- Source readiness: {progress.get('source_readiness') or 'unknown'}",
        f"- Dry-run audit: {progress.get('dry_run_audit') or 'unknown'}",
        f"- 演练场景: {progress.get('dry_run_audit_scenarios') or 'unknown'}",
        f"- Execution chain: {progress.get('chain_closure') or 'unknown'}",
        _chain_segment_progress_line(progress),
        _goal_chain_segment_progress_line(progress),
        f"- 入场快链: {progress.get('entry_fast_chain_boundary') or 'unknown'}",
        f"- 出场硬化: {progress.get('exit_hardening_boundary') or 'unknown'}",
        f"- 策略组分层: {progress.get('strategygroup_tier_boundary') or 'unknown'}",
        _real_order_readiness_progress_line(progress),
        f"- Frontend: {progress.get('frontend') or '外部项目'}",
    ]
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
    if product_gaps:
        lines.extend(["", "## Product Gaps", ""])
        lines.extend(f"- {item}" for item in product_gaps)
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
    if missing_dry_run_checks:
        lines.extend(["", "## Missing Dry-Run Checks", ""])
        lines.extend(f"- {item}" for item in missing_dry_run_checks)
    if missing_chain_segments:
        lines.extend(["", "## Missing Chain Segments", ""])
        lines.extend(f"- {item}" for item in missing_chain_segments)
    if missing_goal_chain_segments:
        lines.extend(["", "## Missing Goal Chain Segments", ""])
        lines.extend(f"- {item}" for item in missing_goal_chain_segments)
    return "\n".join(lines)


def _chain_segment_progress_line(progress: dict[str, Any]) -> str:
    ready_count = progress.get("chain_closure_ready_segments")
    missing_segments = progress.get("chain_closure_missing_or_failed_segments")
    if isinstance(ready_count, int) and isinstance(missing_segments, list):
        return f"- 链路段: {ready_count} ready / {len(missing_segments)} missing"
    return "- 链路段: unknown"


def _goal_chain_segment_progress_line(progress: dict[str, Any]) -> str:
    ready_count = progress.get("goal_chain_ready_segments")
    missing_segments = progress.get("goal_chain_missing_or_failed_segments")
    if isinstance(ready_count, int) and isinstance(missing_segments, list):
        return f"- 目标链路段: {ready_count} ready / {len(missing_segments)} missing"
    return "- 目标链路段: unknown"


def _real_order_readiness_progress_line(progress: dict[str, Any]) -> str:
    summary = progress.get("real_order_readiness")
    if not isinstance(summary, dict) or not summary:
        return "- 实盘矩阵: unknown"
    pass_count = _int_or_zero(summary.get("pass"))
    waiting_count = _int_or_zero(summary.get("waiting"))
    blocked_count = _int_or_zero(summary.get("blocked"))
    return (
        "- 实盘矩阵: "
        f"{pass_count} pass / {waiting_count} waiting / {blocked_count} blocked"
    )


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _cache_age_text(*, generated_at: str, now_utc: datetime | None = None) -> str:
    generated_at_dt = _parse_iso_datetime(generated_at)
    if generated_at_dt is None:
        return "unknown"
    now = now_utc or datetime.now(timezone.utc)
    age_seconds = max(0, int((now - generated_at_dt).total_seconds()))
    age_minutes = age_seconds // 60
    if age_minutes < 1:
        return "<1m"
    if age_minutes < 60:
        return f"{age_minutes}m"
    age_hours = age_minutes // 60
    remaining_minutes = age_minutes % 60
    if remaining_minutes == 0:
        return f"{age_hours}h"
    return f"{age_hours}h{remaining_minutes}m"


def _cache_status_text(
    *,
    generated_at: str,
    now_utc: datetime | None = None,
    max_cache_age_minutes: int = DEFAULT_MAX_CACHE_AGE_MINUTES,
) -> str:
    generated_at_dt = _parse_iso_datetime(generated_at)
    if generated_at_dt is None:
        return "unknown"
    now = now_utc or datetime.now(timezone.utc)
    age_seconds = max(0, int((now - generated_at_dt).total_seconds()))
    max_age_seconds = max(0, max_cache_age_minutes) * 60
    return "stale" if age_seconds > max_age_seconds else "fresh"


def _parse_iso_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text or text == "unknown":
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a low-noise StrategyGroup runtime daily check."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--owner-progress",
        action="store_true",
        help="Print a concise Owner-readable progress summary.",
    )
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="Print Codex heartbeat XML using notification.decision.",
    )
    parser.add_argument("--snapshot-json-path")
    parser.add_argument(
        "--report-json-path",
        help="Read a prebuilt daily-check report JSON without probing Tokyo.",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Read the default local daily-check cache without probing Tokyo.",
    )
    parser.add_argument(
        "--auto-cache",
        action="store_true",
        help=(
            "Use the default local cache when it is fresh; otherwise run one L1 "
            "snapshot and refresh the cache."
        ),
    )
    parser.add_argument("--output-json")
    parser.add_argument(
        "--output-owner-progress",
        help="Write the Owner-readable progress summary to this path.",
    )
    parser.add_argument("--expected-runtime-head")
    parser.add_argument("--expected-frontend-head")
    parser.add_argument(
        "--max-remote-interactions",
        type=int,
        default=1,
        help="Fail the daily check if the source snapshot used more remote calls.",
    )
    parser.add_argument(
        "--max-cache-age-minutes",
        type=int,
        default=DEFAULT_MAX_CACHE_AGE_MINUTES,
        help="Mark cached Owner progress as stale when older than this.",
    )
    parser.add_argument(
        "--require-fresh-cache",
        action="store_true",
        help="Treat stale or timestamp-missing cached reports as an engineering blocker.",
    )
    parser.add_argument(
        "--baseline-json",
        default=str(DEFAULT_BASELINE_JSON),
        help=(
            "Read expected runtime heads from this JSON file. "
            "Explicit --expected-* arguments override it."
        ),
    )
    return parser.parse_args(argv)


def _print_human_report(report: dict[str, Any]) -> None:
    owner = report["owner_summary"]
    checks = report["checks"]
    print(f"status={report['status']}")
    print(f"interaction={report['interaction']['level']}")
    print(f"owner_state={owner['state']}")
    print(f"current_action={owner['current_action']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["product_gaps"]:
        print("product_gaps=" + ",".join(checks["product_gaps"]))


if __name__ == "__main__":
    raise SystemExit(main())
