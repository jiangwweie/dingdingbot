#!/usr/bin/env python3
"""Build a low-noise StrategyGroup runtime daily check from one L1 snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = REPO_ROOT / "scripts" / "probe_tokyo_runtime_snapshot.py"
DEFAULT_BASELINE_JSON = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    expected_heads = _resolve_expected_heads(args)
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
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.heartbeat:
        print(_heartbeat_xml(report))
    elif args.owner_progress:
        print(_owner_progress_text(report))
    elif args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"ready", "waiting_for_market"} else 2


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
    facts = snapshot.get("facts") if isinstance(snapshot.get("facts"), dict) else {}
    reports = facts.get("reports") if isinstance(facts.get("reports"), dict) else {}
    goal_status = (
        reports.get("goal_status") if isinstance(reports.get("goal_status"), dict) else {}
    )

    blockers = list(checks.get("blockers") or [])
    product_gaps = list(checks.get("product_gaps") or [])
    hard_failures = []
    warnings = []

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

    if product_gaps:
        warnings.extend(f"product_gap:{item}" for item in product_gaps)

    waiting_for_market = _is_waiting_for_market(owner_summary, goal_status)
    status = "ready"
    if blockers or hard_failures:
        status = "blocked"
    elif product_gaps:
        status = "degraded"
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
        "runtime_dry_run_missing_required_checks": list(
            checks.get("runtime_dry_run_missing_required_checks") or []
        ),
        "frontend_published": (
            checks.get("frontend_release_present") is True
            and checks.get("frontend_index_present") is True
        ),
    }

    return {
        "status": status,
        "scope": "strategygroup_runtime_daily_check",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": {
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
        },
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
                "frontend": owner_summary.get("frontend"),
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
        and checks.get("frontend_published") is True
    )
    if quiet_waiting:
        return {
            "decision": "DONT_NOTIFY",
            "reason": "healthy_waiting_for_market",
            "message": "自动化正常运行，当前没有 fresh signal",
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
    if checks.get("frontend_published") is not True:
        return "frontend_not_published"
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
        return "修复 Owner Console 产品发布缺口"
    if status == "waiting_for_market":
        return "继续等待市场机会"
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
        return {
            "category": "engineering_blocker",
            "label": "工程状态暂不可用",
            "detail": "Owner Console 首页或发布状态需要修复",
            "next_action": "修复 Owner Console 产品发布缺口",
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


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report.get("owner_summary")
    if not isinstance(owner, dict):
        owner = {}
    checks = report.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    interaction = report.get("interaction")
    if not isinstance(interaction, dict):
        interaction = {}
    notification = report.get("notification")
    if not isinstance(notification, dict):
        notification = {}
    progress = owner.get("progress")
    if not isinstance(progress, dict):
        progress = {}

    blockers = [str(item) for item in checks.get("blockers") or []]
    product_gaps = [str(item) for item in checks.get("product_gaps") or []]
    warnings = [str(item) for item in checks.get("warnings") or []]
    missing_dry_run_checks = [
        str(item) for item in checks.get("runtime_dry_run_missing_required_checks") or []
    ]

    lines = [
        "## StrategyGroup Runtime Progress",
        "",
        f"- 当前阶段: {owner.get('state') or report.get('status') or 'unknown'}",
        f"- 当前动作: {owner.get('current_action') or 'unknown'}",
        f"- 风险等级: {owner.get('risk_level') or 'unknown'}",
        (
            "- Owner 介入: "
            + _yes_no(bool(owner.get("owner_intervention_required")))
        ),
        f"- 通知决策: {notification.get('decision') or 'UNKNOWN'}",
        f"- 通知原因: {notification.get('reason') or 'unknown'}",
        f"- 交互等级: {interaction.get('level') or 'unknown'}",
        f"- 远端交互次数: {interaction.get('remote_interaction_count', 0)}",
        f"- 远端交互预算: {interaction.get('max_remote_interactions', 1)}",
        "- 服务器修改: " + _yes_no(bool(interaction.get("mutates_remote_files"))),
        "- 接近真实订单: " + _yes_no(bool(interaction.get("approaches_real_order"))),
        "- 交易所写入: " + _yes_no(bool(interaction.get("calls_exchange_write"))),
        "",
        "## Progress",
        "",
        f"- Runtime: {progress.get('runtime') or 'unknown'}",
        f"- Watcher: {progress.get('watcher') or 'unknown'}",
        f"- Source readiness: {progress.get('source_readiness') or 'unknown'}",
        f"- Dry-run audit: {progress.get('dry_run_audit') or 'unknown'}",
        f"- Frontend: {progress.get('frontend') or 'unknown'}",
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
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


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
    parser.add_argument("--output-json")
    parser.add_argument("--expected-runtime-head")
    parser.add_argument("--expected-frontend-head")
    parser.add_argument(
        "--max-remote-interactions",
        type=int,
        default=1,
        help="Fail the daily check if the source snapshot used more remote calls.",
    )
    parser.add_argument(
        "--baseline-json",
        default=str(DEFAULT_BASELINE_JSON),
        help=(
            "Read expected runtime/frontend heads from this JSON file. "
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
