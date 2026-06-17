#!/usr/bin/env python3
"""Build a low-noise StrategyGroup runtime daily check from one L1 snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCRIPT = REPO_ROOT / "scripts" / "probe_tokyo_runtime_snapshot.py"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot = (
        _read_json(Path(args.snapshot_json_path))
        if args.snapshot_json_path
        else _run_snapshot(
            expected_runtime_head=args.expected_runtime_head,
            expected_frontend_head=args.expected_frontend_head,
        )
    )
    report = build_daily_check_report(snapshot=snapshot)
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


def build_daily_check_report(*, snapshot: dict[str, Any]) -> dict[str, Any]:
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

    return {
        "status": status,
        "scope": "strategygroup_runtime_daily_check",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": {
            "level": "L1_daily_check_from_snapshot",
            "uses_snapshot_level": interaction.get("level"),
            "remote_interaction_count": interaction.get("remote_interaction_count", 0),
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "owner_summary": {
            "state": owner_summary.get("state") or "状态待刷新",
            "current_action": _daily_next_action(
                status=status,
                owner_summary=owner_summary,
                blockers=blockers,
                product_gaps=product_gaps,
            ),
            "owner_intervention_required": status == "blocked",
            "risk_level": "L1 read-only",
            "progress": {
                "runtime": owner_summary.get("runtime"),
                "watcher": owner_summary.get("watcher"),
                "source_readiness": owner_summary.get("source_readiness"),
                "dry_run_audit": owner_summary.get("dry_run_audit"),
                "frontend": owner_summary.get("frontend"),
            },
        },
        "checks": {
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
            "frontend_published": (
                checks.get("frontend_release_present") is True
                and checks.get("frontend_index_present") is True
            ),
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


def _daily_next_action(
    *,
    status: str,
    owner_summary: dict[str, Any],
    blockers: list[str],
    product_gaps: list[str],
) -> str:
    if blockers:
        return "处理工程或安全阻断"
    if product_gaps:
        return "修复 Owner Console 产品发布缺口"
    if status == "waiting_for_market":
        return "继续等待市场机会"
    return str(owner_summary.get("current_action") or "继续保持监控")


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


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a low-noise StrategyGroup runtime daily check."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--snapshot-json-path")
    parser.add_argument("--output-json")
    parser.add_argument("--expected-runtime-head")
    parser.add_argument("--expected-frontend-head")
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
