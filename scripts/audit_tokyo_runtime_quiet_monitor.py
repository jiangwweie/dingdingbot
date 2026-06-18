#!/usr/bin/env python3
"""Audit the local Tokyo quiet-monitor automation against the repo baseline."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_JSON = REPO_ROOT / "docs/current/RUNTIME_MONITOR_BASELINE.json"
DEFAULT_AUTOMATION_TOML = (
    Path.home() / ".codex/automations/tokyo-runtime-quiet-monitor/automation.toml"
)
DEFAULT_QUIET_MONITOR_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-quiet-monitor-audit.json"
)
DEFAULT_QUIET_MONITOR_AUDIT_OWNER_PROGRESS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-quiet-monitor-audit.md"
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_quiet_monitor_audit(
        baseline=_read_json(Path(args.baseline_json)),
        automation_text=Path(args.automation_toml).read_text(encoding="utf-8"),
        automation_path=Path(args.automation_toml),
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
    return 0 if report["status"] == "ready" else 2


def build_quiet_monitor_audit(
    *,
    baseline: dict[str, Any],
    automation_text: str,
    automation_path: Path,
) -> dict[str, Any]:
    checks = _checks_from_text(baseline=baseline, automation_text=automation_text)
    checks.extend(_checks_from_baseline(baseline=baseline))
    blockers = [
        check["id"]
        for check in checks
        if check["status"] != "pass"
    ]
    status = "ready" if not blockers else "blocked"
    return {
        "status": status,
        "scope": "tokyo_runtime_quiet_monitor_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": {
            "level": "L0_local_automation_audit",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "自动化配置已对齐" if status == "ready" else "自动化配置需修正",
            "current_action": (
                "继续低噪音监控"
                if status == "ready"
                else "修正 quiet monitor 自动化提示词"
            ),
            "owner_intervention_required": False,
            "risk_level": "L0 local audit",
        },
        "checks": {
            "blockers": blockers,
            "all_required_prompt_terms_present": not blockers,
        },
        "required_checks": checks,
        "source_paths": {
            "baseline_json": str(DEFAULT_BASELINE_JSON),
            "automation_toml": str(automation_path),
            "quiet_monitor_audit_json": str(DEFAULT_QUIET_MONITOR_AUDIT_JSON),
            "quiet_monitor_audit_owner_progress_md": str(
                DEFAULT_QUIET_MONITOR_AUDIT_OWNER_PROGRESS_MD
            ),
        },
    }


def _checks_from_text(
    *,
    baseline: dict[str, Any],
    automation_text: str,
) -> list[dict[str, str]]:
    required_terms = {
        "local_monitor_sequence_check": str(
            baseline.get("local_monitor_sequence_check") or ""
        ),
        "latest_local_monitor_sequence_md": (
            "output/runtime-monitor/latest-local-monitor-sequence.md"
        ),
        "dont_notify": "DONT_NOTIFY",
        "waiting_for_market": "waiting_for_market",
        "not_complete_waiting_for_market": "not_complete_waiting_for_market",
        "blockers_none": "blockers none",
        "non_market_gaps_none": "non-market gaps none",
        "zero_remote_interaction": "remote interaction count 0",
        "fresh_signal_notify": "fresh/runtime-ready signal",
        "no_frontend_or_history_debt": (
            "Do not advance frontend or historical-debt cleanup"
        ),
    }
    checks = []
    for check_id, required in required_terms.items():
        present = bool(required) and required in automation_text
        checks.append({
            "id": check_id,
            "status": "pass" if present else "fail",
            "required_text": required,
        })
    return checks


def _checks_from_baseline(*, baseline: dict[str, Any]) -> list[dict[str, str]]:
    p0_completion_audit_check = str(baseline.get("p0_completion_audit_check") or "")
    p0_required_fragments = [
        "python3 scripts/runtime_first_bounded_live_order_completion_audit.py",
        "--output-json output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json",
        "--output-owner-progress output/runtime-monitor/latest-p0-live-order-closure-completion-audit.md",
    ]
    missing_p0_fragments = [
        fragment
        for fragment in p0_required_fragments
        if fragment not in p0_completion_audit_check
    ]
    forbidden_fragments = ["run_tokyo", "ssh ", "scp ", "rsync "]
    p0_forbidden_present = [
        fragment for fragment in forbidden_fragments if fragment in p0_completion_audit_check
    ]
    p0_status = (
        "pass"
        if p0_completion_audit_check and not missing_p0_fragments and not p0_forbidden_present
        else "fail"
    )
    local_sequence_check = str(baseline.get("local_monitor_sequence_check") or "")
    sequence_required_fragments = [
        "python3 scripts/run_strategygroup_runtime_local_monitor_sequence.py",
        "--daily-check-mode cache",
        "--output-json output/runtime-monitor/latest-local-monitor-sequence.json",
        "--output-owner-progress output/runtime-monitor/latest-local-monitor-sequence.md",
    ]
    missing_sequence_fragments = [
        fragment
        for fragment in sequence_required_fragments
        if fragment not in local_sequence_check
    ]
    sequence_forbidden_present = [
        fragment for fragment in forbidden_fragments if fragment in local_sequence_check
    ]
    sequence_status = (
        "pass"
        if local_sequence_check
        and not missing_sequence_fragments
        and not sequence_forbidden_present
        else "fail"
    )
    return [
        {
            "id": "p0_completion_audit_check_registered",
            "status": p0_status,
            "required_text": " | ".join(p0_required_fragments),
        },
        {
            "id": "local_monitor_sequence_check_registered",
            "status": sequence_status,
            "required_text": " | ".join(sequence_required_fragments),
        }
    ]


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    lines = [
        "## Tokyo Runtime Quiet Monitor Audit",
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
        "## Checks",
        "",
        "| Check | Status |",
        "| --- | --- |",
    ]
    for check in report["required_checks"]:
        lines.append(f"| {check['id']} | {check['status']} |")
    lines.extend(["", f"- Blockers: {_list_or_none(checks['blockers'])}"])
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
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit local Tokyo quiet-monitor automation prompt."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--owner-progress",
        action="store_true",
        help="Print an Owner-readable Markdown progress summary.",
    )
    parser.add_argument("--baseline-json", default=str(DEFAULT_BASELINE_JSON))
    parser.add_argument("--automation-toml", default=str(DEFAULT_AUTOMATION_TOML))
    parser.add_argument("--output-json", default=str(DEFAULT_QUIET_MONITOR_AUDIT_JSON))
    parser.add_argument(
        "--output-owner-progress",
        default=str(DEFAULT_QUIET_MONITOR_AUDIT_OWNER_PROGRESS_MD),
    )
    return parser.parse_args(argv)


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


if __name__ == "__main__":
    raise SystemExit(main())
