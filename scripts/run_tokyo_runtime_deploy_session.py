#!/usr/bin/env python3
"""Summarize a Tokyo deploy session with one Owner-readable interaction report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_interaction_levels import annotate_interaction, interaction_rank

DAILY_CHECK_SCRIPT = REPO_ROOT / "scripts" / "run_strategygroup_runtime_daily_check.py"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    reports = []
    if args.deploy_report_json:
        reports.append(("runtime_deploy", _read_json(Path(args.deploy_report_json))))
    if args.frontend_report_json:
        reports.append(("frontend_publish", _read_json(Path(args.frontend_report_json))))
    if args.daily_check_json:
        reports.append(("postdeploy_daily_check", _read_json(Path(args.daily_check_json))))
    elif args.run_daily_check:
        reports.append(
            (
                "postdeploy_daily_check",
                _run_daily_check(
                    expected_runtime_head=args.expected_runtime_head,
                    expected_frontend_head=args.expected_frontend_head,
                    mode=args.daily_check_mode,
                ),
            )
        )

    report = build_deploy_session_report(reports=reports)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"ready", "waiting_for_market"} else 2


def build_deploy_session_report(
    *,
    reports: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    steps = [_session_step(name=name, report=report) for name, report in reports]
    blockers = _dedupe(
        blocker
        for step in steps
        for blocker in step["blockers"]
        if blocker
    )
    warnings = _dedupe(
        warning
        for step in steps
        for warning in step["warnings"]
        if warning
    )
    product_gaps = _dedupe(
        gap
        for step in steps
        for gap in step["product_gaps"]
        if gap
    )

    interaction_levels = [str(step["interaction_level"]) for step in steps]
    highest_level = _highest_interaction_level(interaction_levels)
    remote_interactions = sum(int(step["remote_interaction_count"] or 0) for step in steps)
    mutates_remote = any(bool(step["mutates_remote_files"]) for step in steps)
    approaches_real_order = any(bool(step["approaches_real_order"]) for step in steps)
    calls_exchange_write = any(bool(step["calls_exchange_write"]) for step in steps)
    places_order = any(bool(step["places_order"]) for step in steps)
    waiting_for_market = any(step["status"] == "waiting_for_market" for step in steps)

    status = "ready"
    if blockers:
        status = "blocked"
    elif product_gaps:
        status = "degraded"
    elif waiting_for_market:
        status = "waiting_for_market"

    return {
        "status": status,
        "scope": "tokyo_runtime_deploy_session",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": annotate_interaction({
            "level": highest_level,
            "remote_interaction_count": remote_interactions,
            "mutates_remote_files": mutates_remote,
            "approaches_real_order": approaches_real_order,
            "calls_finalgate": any(bool(step["calls_finalgate"]) for step in steps),
            "calls_operation_layer": any(
                bool(step["calls_operation_layer"]) for step in steps
            ),
            "calls_exchange_write": calls_exchange_write,
            "places_order": places_order,
        }),
        "owner_summary": {
            "state": _owner_state_for_status(status=status, highest_level=highest_level),
            "current_action": _current_action_for_status(
                status=status,
                blockers=blockers,
                product_gaps=product_gaps,
            ),
            "owner_intervention_required": bool(blockers),
            "risk_level": highest_level,
            "server_mutation": "yes" if mutates_remote else "no",
            "real_order_approach": "yes" if approaches_real_order else "no",
            "step_count": len(steps),
        },
        "checks": {
            "blockers": blockers,
            "warnings": warnings,
            "product_gaps": product_gaps,
            "waiting_for_market": waiting_for_market,
            "all_steps_safe_for_deploy_session_summary": (
                not approaches_real_order
                and not calls_exchange_write
                and not places_order
            ),
        },
        "steps": steps,
        "safety_invariants": {
            "finalgate_bypassed": False,
            "operation_layer_bypassed": False,
            "secrets_read": False,
            "credentials_changed": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
            "exchange_write_called": calls_exchange_write,
            "order_created": places_order,
            "withdrawal_or_transfer_created": False,
        },
    }


def _session_step(*, name: str, report: dict[str, Any]) -> dict[str, Any]:
    interaction = report.get("interaction") if isinstance(report.get("interaction"), dict) else {}
    current_read_interaction = (
        report.get("current_read_interaction")
        if isinstance(report.get("current_read_interaction"), dict)
        else {}
    )
    effective_interaction = current_read_interaction or interaction
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    owner_summary = (
        report.get("owner_summary")
        if isinstance(report.get("owner_summary"), dict)
        else {}
    )
    effects = report.get("effects") if isinstance(report.get("effects"), dict) else {}
    safety = (
        report.get("safety_invariants")
        if isinstance(report.get("safety_invariants"), dict)
        else {}
    )
    blockers = _as_string_list(checks.get("blockers"))
    product_gaps = _as_string_list(checks.get("product_gaps"))
    warnings = _as_string_list(checks.get("warnings"))

    status = str(report.get("status") or "unknown")
    return {
        "name": name,
        "status": status,
        "scope": str(report.get("scope") or name),
        "interaction_level": str(effective_interaction.get("level") or "unknown"),
        "remote_interaction_count": int(
            effective_interaction.get("remote_interaction_count") or 0
        ),
        "collected_interaction_level": str(interaction.get("level") or "unknown"),
        "collected_remote_interaction_count": int(
            interaction.get("remote_interaction_count") or 0
        ),
        "mutates_remote_files": bool(
            effective_interaction.get("mutates_remote_files")
            or effects.get("remote_files_modified")
            or safety.get("remote_files_modified")
        ),
        "approaches_real_order": bool(
            effective_interaction.get("approaches_real_order")
        ),
        "calls_finalgate": bool(effective_interaction.get("calls_finalgate")),
        "calls_operation_layer": bool(
            effective_interaction.get("calls_operation_layer")
        ),
        "calls_exchange_write": bool(
            effective_interaction.get("calls_exchange_write")
            or effective_interaction.get("exchange_write_called")
            or effects.get("exchange_write_called")
            or effects.get("exchange_called")
            or safety.get("exchange_write_called")
        ),
        "places_order": bool(
            effective_interaction.get("places_order")
            or effects.get("order_created")
            or safety.get("order_created")
        ),
        "owner_state": str(owner_summary.get("state") or ""),
        "current_action": str(owner_summary.get("current_action") or ""),
        "blockers": blockers,
        "warnings": warnings,
        "product_gaps": product_gaps,
    }


def _highest_interaction_level(levels: list[str]) -> str:
    highest_rank = -1
    highest_label = "L0_local_session_summary"
    for level in levels:
        rank = interaction_rank(level)
        if rank > highest_rank:
            highest_rank = rank
            highest_label = level
    return highest_label


def _owner_state_for_status(*, status: str, highest_level: str) -> str:
    if status == "blocked":
        return "暂不可用"
    if status == "degraded":
        return "需要修复产品发布缺口"
    if status == "waiting_for_market":
        return "等待机会"
    if highest_level.startswith("L3"):
        return "部署会话完成"
    return "部署会话已核验"


def _current_action_for_status(
    *,
    status: str,
    blockers: list[str],
    product_gaps: list[str],
) -> str:
    if blockers:
        return "处理部署或运行阻断"
    if product_gaps:
        return "修复 Owner Console 首页发布缺口"
    if status == "waiting_for_market":
        return "继续等待市场机会"
    return "继续低噪音监控"


def _run_daily_check(
    *,
    expected_runtime_head: str | None,
    expected_frontend_head: str | None,
    mode: str,
) -> dict[str, Any]:
    command = [sys.executable, str(DAILY_CHECK_SCRIPT), "--json"]
    if mode == "auto-cache":
        command.append("--auto-cache")
    elif mode == "cache":
        command.extend(["--from-cache", "--require-fresh-cache"])
    elif mode != "fresh":
        return _daily_check_mode_error(mode)
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
        return _daily_check_error("daily_check_command_failed", completed)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return _daily_check_error("daily_check_output_not_json", completed)
    if not isinstance(payload, dict):
        return _daily_check_error("daily_check_output_not_object", completed)
    return payload


def _daily_check_mode_error(mode: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "scope": "strategygroup_runtime_daily_check",
        "interaction": {
            "level": "L0_local_cache_gate",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "暂不可用",
            "current_action": "修正部署会话日检模式",
        },
        "checks": {
            "blockers": [f"unknown_daily_check_mode:{mode}"],
            "warnings": [],
            "product_gaps": [],
        },
    }


def _daily_check_error(reason: str, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "scope": "strategygroup_runtime_daily_check",
        "interaction": {
            "level": "L1_daily_check_from_snapshot",
            "remote_interaction_count": 1,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": "暂不可用",
            "current_action": "检查日检命令",
        },
        "checks": {
            "blockers": [reason],
            "warnings": [],
            "product_gaps": [],
        },
        "error": completed.stderr[-2000:] or completed.stdout[-2000:],
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize a Tokyo runtime deploy session."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--deploy-report-json")
    parser.add_argument("--frontend-report-json")
    parser.add_argument("--daily-check-json")
    parser.add_argument("--run-daily-check", action="store_true")
    parser.add_argument(
        "--daily-check-mode",
        choices=("fresh", "auto-cache", "cache"),
        default="fresh",
        help=(
            "How --run-daily-check should collect status. Use fresh for "
            "postdeploy acceptance, auto-cache for routine low-noise status, "
            "or cache for strict no-server review."
        ),
    )
    parser.add_argument("--expected-runtime-head")
    parser.add_argument("--expected-frontend-head")
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _print_human_report(report: dict[str, Any]) -> None:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    print(f"status={report['status']}")
    print(f"interaction={interaction['level']}")
    print(f"remote_interaction_count={interaction['remote_interaction_count']}")
    print(f"mutates_remote_files={str(interaction['mutates_remote_files']).lower()}")
    print(f"approaches_real_order={str(interaction['approaches_real_order']).lower()}")
    print(f"owner_state={owner['state']}")
    print(f"current_action={owner['current_action']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["product_gaps"]:
        print("product_gaps=" + ",".join(checks["product_gaps"]))


if __name__ == "__main__":
    raise SystemExit(main())
