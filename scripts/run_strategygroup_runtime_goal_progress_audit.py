#!/usr/bin/env python3
"""Summarize StrategyGroup Runtime Pilot goal progress from local evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_JSON = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_GOAL_PROGRESS_JSON = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-goal-progress.md"
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_goal_progress_report(
        daily_check=_read_json(Path(args.daily_check_json)),
        baseline=_read_json(Path(args.baseline_json)),
    )
    owner_progress_text = _owner_progress_text(report)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.output_owner_progress:
        output_path = Path(args.output_owner_progress)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(owner_progress_text + "\n", encoding="utf-8")
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
    status = "ready"
    if hard_blockers:
        status = "blocked"
    elif waiting_for_market and p05_ready:
        status = "waiting_for_market"
    elif not p05_ready:
        status = "degraded"

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
        "checks": {
            "blockers": hard_blockers,
            "product_gaps": [item for item in issues if item not in hard_blockers],
            "waiting_for_market": waiting_for_market,
            "p05_ready": p05_ready,
            "daily_check_status": daily_check.get("status"),
            "daily_check_notification": notification.get("decision"),
        },
        "tracks": [p0, *p05_tracks],
        "source_paths": {
            "daily_check_json": str(DEFAULT_DAILY_CHECK_JSON),
            "baseline_json": str(DEFAULT_BASELINE_JSON),
            "goal_progress_json": str(DEFAULT_GOAL_PROGRESS_JSON),
            "goal_progress_owner_progress_md": str(
                DEFAULT_GOAL_PROGRESS_OWNER_PROGRESS_MD
            ),
        },
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
    blockers.extend(f"missing_dry_run_check:{item}" for item in missing)
    return _track(
        track_id="p05_engineering_rehearsal_loop",
        label="P0.5 Engineering Rehearsal Loop",
        blockers=blockers,
        evidence=[
            f"dry_run_audit={progress.get('dry_run_audit')}",
            f"scenario_count={checks.get('runtime_dry_run_scenario_count')}",
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
