#!/usr/bin/env python3
"""Run local StrategyGroup runtime monitor artifacts in a strict sequence.

This helper is for goal-mode and manual status review. It prevents false
completion-audit gaps caused by running goal-progress and completion-audit
commands in parallel. The default mode is cache-only and does not contact Tokyo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_DAILY_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-owner-progress.md"
)
DEFAULT_GOAL_PROGRESS_JSON = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
DEFAULT_GOAL_PROGRESS_MD = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.md"
DEFAULT_COMPLETION_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_COMPLETION_AUDIT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.md"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.md"
)


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_local_monitor_sequence_report(
        daily_check_mode=args.daily_check_mode,
        daily_check_json=Path(args.daily_check_json),
        daily_owner_progress=Path(args.daily_owner_progress),
        goal_progress_json=Path(args.goal_progress_json),
        goal_progress_md=Path(args.goal_progress_md),
        completion_audit_json=Path(args.completion_audit_json),
        completion_audit_md=Path(args.completion_audit_md),
    )
    owner_progress_text = _owner_progress_text(report)
    if args.output_json:
        _write_json(Path(args.output_json), report)
    if args.output_owner_progress:
        _write_text(Path(args.output_owner_progress), owner_progress_text + "\n")
    if args.owner_progress:
        print(owner_progress_text)
    elif args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"waiting_for_market", "processing", "complete"} else 2


def build_local_monitor_sequence_report(
    *,
    daily_check_mode: str = "cache",
    daily_check_json: Path = DEFAULT_DAILY_CHECK_JSON,
    daily_owner_progress: Path = DEFAULT_DAILY_OWNER_PROGRESS,
    goal_progress_json: Path = DEFAULT_GOAL_PROGRESS_JSON,
    goal_progress_md: Path = DEFAULT_GOAL_PROGRESS_MD,
    completion_audit_json: Path = DEFAULT_COMPLETION_AUDIT_JSON,
    completion_audit_md: Path = DEFAULT_COMPLETION_AUDIT_MD,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = command_runner or _run_command
    steps: list[dict[str, Any]] = []

    daily_command = _daily_check_command(
        mode=daily_check_mode,
        output_json=daily_check_json,
        output_owner_progress=daily_owner_progress,
    )
    steps.append(_run_step("daily_check", daily_command, daily_check_json, runner))

    goal_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_goal_progress_audit.py"),
        "--owner-progress",
        "--output-json",
        str(goal_progress_json),
        "--output-owner-progress",
        str(goal_progress_md),
    ]
    steps.append(_run_step("goal_progress", goal_command, goal_progress_json, runner))

    completion_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/runtime_first_bounded_live_order_completion_audit.py"),
        "--owner-progress",
        "--output-json",
        str(completion_audit_json),
        "--output-owner-progress",
        str(completion_audit_md),
    ]
    steps.append(
        _run_step("completion_audit", completion_command, completion_audit_json, runner)
    )

    packets = {
        step["name"]: step.get("packet") if isinstance(step.get("packet"), dict) else {}
        for step in steps
    }
    status = _sequence_status(steps=steps, packets=packets)
    interaction = _sequence_interaction(steps)
    blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not (
            step["name"] == "completion_audit"
            and _status(packets["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    non_market_gaps = list(packets["completion_audit"].get("non_market_gaps") or [])
    if non_market_gaps:
        blockers.append("completion_audit:non_market_gaps")

    return {
        "schema": "brc.strategygroup_runtime_local_monitor_sequence.v1",
        "scope": "strategygroup_runtime_local_monitor_sequence",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_check_mode": daily_check_mode,
        "owner_summary": {
            "state": _owner_state(status),
            "current_action": _owner_action(status),
            "owner_intervention_required": status == "needs_non_market_repair",
            "risk_level": interaction["level"],
        },
        "interaction": interaction,
        "checks": {
            "blockers": blockers,
            "non_market_gaps": non_market_gaps,
            "waiting_for_market": status == "waiting_for_market",
            "goal_complete": status == "complete",
        },
        "steps": [
            {
                "name": step["name"],
                "returncode": step["returncode"],
                "status": _status(step.get("packet")),
                "output_json": step["output_json"],
                "interaction": _interaction(step.get("packet")),
            }
            for step in steps
        ],
        "source_paths": {
            "daily_check_json": str(daily_check_json),
            "goal_progress_json": str(goal_progress_json),
            "completion_audit_json": str(completion_audit_json),
        },
    }


def _daily_check_command(
    *,
    mode: str,
    output_json: Path,
    output_owner_progress: Path,
) -> list[str]:
    if mode not in {"cache", "auto-cache"}:
        raise ValueError(f"unsupported daily_check_mode: {mode}")
    mode_args = (
        ["--from-cache", "--require-fresh-cache"]
        if mode == "cache"
        else ["--auto-cache"]
    )
    return [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_daily_check.py"),
        *mode_args,
        "--json",
        "--output-json",
        str(output_json),
        "--output-owner-progress",
        str(output_owner_progress),
    ]


def _run_step(
    name: str,
    command: list[str],
    output_json: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    completed = runner(command)
    packet = _read_json_if_exists(output_json)
    return {
        "name": name,
        "command": _display_command(command),
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_json": str(output_json),
        "packet": packet,
    }


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _sequence_status(
    *,
    steps: list[dict[str, Any]],
    packets: dict[str, dict[str, Any]],
) -> str:
    failed_steps = [
        step
        for step in steps
        if int(step.get("returncode") or 0) != 0
        and not (
            step["name"] == "completion_audit"
            and _status(packets["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    if failed_steps:
        return "needs_non_market_repair"

    completion_status = _status(packets["completion_audit"])
    if completion_status in {"complete", "completed"}:
        return "complete"
    if completion_status == "needs_non_market_repair":
        return "needs_non_market_repair"
    if completion_status == "not_complete_runtime_processing":
        return "processing"
    if (
        _status(packets["daily_check"]) == "waiting_for_market"
        and _status(packets["goal_progress"]) == "waiting_for_market"
        and completion_status == "not_complete_waiting_for_market"
    ):
        return "waiting_for_market"
    if _status(packets["daily_check"]) == "processing" or _status(
        packets["goal_progress"]
    ) == "processing":
        return "processing"
    return "needs_non_market_repair"


def _sequence_interaction(steps: list[dict[str, Any]]) -> dict[str, Any]:
    remote_count = 0
    mutates_remote = False
    approaches_real_order = False
    calls_finalgate = False
    calls_operation_layer = False
    calls_exchange_write = False
    places_order = False
    for step in steps:
        interaction = _interaction(step.get("packet"))
        remote_count += _int(interaction.get("remote_interaction_count"))
        mutates_remote = mutates_remote or interaction.get("mutates_remote_files") is True
        approaches_real_order = (
            approaches_real_order or interaction.get("approaches_real_order") is True
        )
        calls_finalgate = calls_finalgate or interaction.get("calls_finalgate") is True
        calls_operation_layer = (
            calls_operation_layer or interaction.get("calls_operation_layer") is True
        )
        calls_exchange_write = (
            calls_exchange_write or interaction.get("calls_exchange_write") is True
        )
        places_order = places_order or interaction.get("places_order") is True
    return {
        "level": "L1_local_monitor_sequence_with_auto_cache"
        if remote_count
        else "L0_local_monitor_sequence",
        "remote_interaction_count": remote_count,
        "mutates_remote_files": mutates_remote,
        "approaches_real_order": approaches_real_order,
        "calls_finalgate": calls_finalgate,
        "calls_operation_layer": calls_operation_layer,
        "calls_exchange_write": calls_exchange_write,
        "places_order": places_order,
    }


def _owner_state(status: str) -> str:
    if status == "waiting_for_market":
        return "等待机会"
    if status == "processing":
        return "处理中"
    if status == "complete":
        return "已完成"
    return "需要修复"


def _owner_action(status: str) -> str:
    if status == "waiting_for_market":
        return "继续等待市场机会"
    if status == "processing":
        return "等待系统完成当前链路"
    if status == "complete":
        return "归档第一笔边界内真实订单闭环"
    return "修复本地监控或非市场证据缺口"


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    lines = [
        "## StrategyGroup Runtime Local Monitor Sequence",
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
        "## Steps",
        "",
        "| Step | Status | Returncode |",
        "| --- | --- | ---: |",
    ]
    for step in report["steps"]:
        lines.append(
            f"| {step['name']} | {step.get('status') or 'unknown'} | {step['returncode']} |"
        )
    lines.extend([
        "",
        "## Checks",
        "",
        f"- Blockers: {_list_or_none([str(item) for item in checks['blockers']])}",
        f"- Non-market gaps: {_list_or_none([str(item) for item in checks['non_market_gaps']])}",
    ])
    return "\n".join(lines)


def _print_human_report(report: dict[str, Any]) -> None:
    print(f"status={report['status']}")
    print(f"owner_state={report['owner_summary']['state']}")
    print(f"current_action={report['owner_summary']['current_action']}")
    print(f"interaction={report['interaction']['level']}")
    print(f"remote_interaction_count={report['interaction']['remote_interaction_count']}")
    blockers = [str(item) for item in report["checks"]["blockers"]]
    if blockers:
        print("blockers=" + ",".join(blockers))


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _status(packet: Any) -> str:
    return str(packet.get("status") or "") if isinstance(packet, dict) else ""


def _interaction(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    interaction = packet.get("interaction")
    return interaction if isinstance(interaction, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _display_command(command: list[str]) -> str:
    return " ".join(command).replace(str(REPO_ROOT) + "/", "")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local StrategyGroup runtime monitor artifacts sequentially."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--owner-progress", action="store_true")
    parser.add_argument(
        "--daily-check-mode",
        choices=["cache", "auto-cache"],
        default="cache",
        help="cache is local-only; auto-cache may perform one L1 readonly refresh.",
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--daily-owner-progress", default=str(DEFAULT_DAILY_OWNER_PROGRESS))
    parser.add_argument("--goal-progress-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument("--goal-progress-md", default=str(DEFAULT_GOAL_PROGRESS_MD))
    parser.add_argument("--completion-audit-json", default=str(DEFAULT_COMPLETION_AUDIT_JSON))
    parser.add_argument("--completion-audit-md", default=str(DEFAULT_COMPLETION_AUDIT_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
