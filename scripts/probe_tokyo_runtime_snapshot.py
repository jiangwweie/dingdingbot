#!/usr/bin/env python3
"""Collect one read-only Tokyo runtime snapshot with a single SSH interaction."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import runtime_live_closure_evidence_verifier  # noqa: E402

DEFAULT_HOST = "tokyo"
DEFAULT_DEPLOY_ROOT = "/home/ubuntu/brc-deploy"
DEFAULT_REPORT_DIR = (
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher"
)
DEFAULT_SERVICES = (
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-signal-watcher.service",
    "brc-owner-console-backend.service",
)
DEFAULT_REPORT_FILES = (
    "watcher-tick.json",
    "latest-summary.json",
    "strategygroup-runtime-goal-status.json",
    "owner-console-source-readiness.json",
    "runtime-dry-run-audit-chain.json",
    "runtime-execution-chain-closure-status.json",
    "runtime-live-closure-evidence.json",
    "runtime-live-closure-evidence-verification.json",
)

REQUIRED_DRY_RUN_CHECKS = (
    "required_scenarios_present",
    "all_scenarios_passed",
    "dangerous_effects_absent",
    "disabled_smoke_not_real_execution_proof",
    "operation_layer_evidence_relay_checked",
    "scoped_pipeline_operation_layer_submit_projection_checked",
    "fresh_signal_fast_auto_chain_checked",
    "required_facts_readiness_checked",
    "mock_operation_layer_closed_loop_checked",
    "operation_layer_blocker_review_policy_checked",
    "operation_layer_hard_safety_blocker_matrix_checked",
    "operation_layer_authorization_chain_guard_checked",
    "post_submit_closed_loop_evidence_guard_checked",
    "post_submit_exit_outcome_matrix_checked",
    "reduce_only_recovery_standing_authorization_checked",
    "operation_layer_submit_result_identity_guard_checked",
    "post_submit_finalize_result_identity_guard_checked",
    "shared_runtime_pipeline_checked",
    "common_execution_chain_reuse_checked",
    "strategygroup_adapter_boundary_checked",
    "runtime_tier_policy_checked",
    "only_mpg_tiny_real_order_eligible_checked",
    "new_strategygroups_default_observe_only_checked",
    "selected_strategygroup_dispatch_guard_checked",
    "all_selected_strategygroups_reach_finalgate_dispatch_checked",
    "execution_attempt_rehearsal_prepare_checked",
)

ACTIVE_GOAL_STATUSES = {
    "fresh_signal_detected",
    "fresh_signal_processing",
    "action_time_finalgate_ready",
    "operation_layer_ready",
}


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


Runner = Callable[[tuple[str, ...]], CommandResult]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_tokyo_runtime_snapshot(
        host=args.host,
        deploy_root=args.deploy_root,
        report_dir=args.report_dir,
        expected_runtime_head=args.expected_runtime_head,
        connect_timeout_seconds=args.connect_timeout_seconds,
    )
    if args.output_json:
        _write_text_atomic(
            Path(args.output_json),
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"ready", "product_gap"} else 2


def build_tokyo_runtime_snapshot(
    *,
    host: str,
    deploy_root: str,
    report_dir: str,
    expected_runtime_head: str | None,
    connect_timeout_seconds: int = 8,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Collect and evaluate a Tokyo snapshot without remote mutation."""

    remote_facts = collect_remote_snapshot(
        host=host,
        deploy_root=deploy_root,
        report_dir=report_dir,
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    return evaluate_runtime_snapshot(
        remote_facts=remote_facts,
        host=host,
        deploy_root=deploy_root,
        report_dir=report_dir,
        expected_runtime_head=expected_runtime_head,
    )


def collect_remote_snapshot(
    *,
    host: str,
    deploy_root: str,
    report_dir: str,
    connect_timeout_seconds: int,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Run one remote read-only Python collector over SSH."""

    command_runner = runner or _run
    remote_command = _remote_snapshot_command(
        deploy_root=deploy_root,
        report_dir=report_dir,
    )
    command = (
        ("sh", "-lc", remote_command)
        if _is_local_host(host)
        else (
            "ssh",
            "-o",
            f"ConnectTimeout={int(connect_timeout_seconds)}",
            host,
            remote_command,
        )
    )
    result = command_runner(command)
    if result.returncode != 0:
        return {
            "collector_status": "failed",
            "collector_error": result.stderr.strip() or result.stdout.strip(),
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "collector_status": "failed",
            "collector_error": f"collector_output_not_json:{exc}",
            "stdout_tail": result.stdout[-2000:],
        }
    if not isinstance(payload, dict):
        return {
            "collector_status": "failed",
            "collector_error": "collector_output_not_object",
        }
    return payload


def evaluate_runtime_snapshot(
    *,
    remote_facts: dict[str, Any],
    host: str,
    deploy_root: str,
    report_dir: str,
    expected_runtime_head: str | None,
) -> dict[str, Any]:
    """Project raw facts into a compact Owner/Codex interaction report."""

    services = _as_dict(remote_facts.get("systemd"))
    reports = _as_dict(remote_facts.get("reports"))
    release = _as_dict(remote_facts.get("release"))

    blockers: list[str] = []
    product_gaps: list[str] = []
    warnings: list[str] = []

    collector_ok = remote_facts.get("collector_status") == "ok"
    if not collector_ok:
        blockers.append("tokyo_snapshot_collector_failed")

    runtime_head = _first_text(
        release.get("head"),
        _as_dict(release.get("manifest")).get("head"),
        _as_dict(release.get("manifest")).get("commit"),
        _as_dict(_as_dict(release.get("manifest")).get("local_git")).get("head"),
    )
    if expected_runtime_head and runtime_head != expected_runtime_head:
        blockers.append("runtime_head_mismatch")

    timer = _as_dict(services.get("brc-runtime-signal-watcher.timer"))
    backend = _as_dict(services.get("brc-owner-console-backend.service"))
    if timer.get("active") != "active":
        blockers.append("watcher_timer_inactive")
    if backend.get("active") != "active":
        blockers.append("owner_console_backend_inactive")

    source_readiness = _report_payload(reports, "owner-console-source-readiness.json")
    goal_status = _report_payload(reports, "strategygroup-runtime-goal-status.json")
    dry_run = _report_payload(reports, "runtime-dry-run-audit-chain.json")
    chain_closure = _report_payload(
        reports,
        "runtime-execution-chain-closure-status.json",
    )
    live_closure_evidence = _report_payload(
        reports,
        "runtime-live-closure-evidence.json",
    )
    live_closure_verification = _live_closure_verification_from_reports(
        reports=reports,
        live_closure_evidence=live_closure_evidence,
    )
    latest_summary = _report_payload(reports, "latest-summary.json")

    if source_readiness.get("status") not in {"ready", "ok"}:
        blockers.append("source_readiness_not_ready")
    dry_run_checks = _as_dict(dry_run.get("checks"))
    missing_dry_run_checks = _missing_dry_run_required_checks(dry_run_checks)
    if dry_run.get("status") != "passed":
        blockers.append("runtime_dry_run_audit_not_passed")
    blockers.extend(
        f"runtime_dry_run_missing_required_check:{name}"
        for name in missing_dry_run_checks
    )
    if chain_closure.get("status") != "non_market_execution_chain_ready":
        blockers.append("runtime_execution_chain_closure_status_not_ready")
    if _artifact_check(goal_status, "deployment_aligned") is False:
        blockers.append("runtime_goal_status_deployment_not_aligned")
    if _artifact_check(goal_status, "watcher_liveness_healthy") is False:
        blockers.append("watcher_liveness_not_healthy")
    goal_status_submit_blockers = _goal_status_submit_blocker_keys(goal_status)
    goal_status_real_order_readiness_summary = (
        _goal_status_real_order_readiness_summary(goal_status)
    )
    blockers.extend(
        f"runtime_goal_status_submit_blocker:{key}"
        for key in goal_status_submit_blockers
    )
    live_closure_completion = _as_dict(live_closure_verification.get("completion"))
    first_bounded_real_order_complete = (
        live_closure_completion.get("first_bounded_real_order_complete") is True
    )
    real_order_closure_proven = (
        live_closure_completion.get("real_order_closure_proven") is True
    )
    if live_closure_verification.get("status") == "blocked_live_closure_rejected":
        product_gaps.extend(
            f"live_closure_evidence:{item}"
            for item in live_closure_verification.get("reject_reasons") or []
        )

    goal_status_value = str(goal_status.get("status") or "")
    fresh_signal_present = _artifact_check(goal_status, "fresh_signal_present") is True
    goal_processing = fresh_signal_present or goal_status_value in ACTIVE_GOAL_STATUSES
    waiting_for_market = (not goal_processing) and (
        _artifact_check(goal_status, "fresh_signal_present") is False
        or latest_summary.get("status") in {"waiting_for_signal", "waiting_for_market"}
        or source_readiness.get("owner_state") in {"等待机会", "waiting_for_opportunity"}
    )
    if first_bounded_real_order_complete and real_order_closure_proven:
        waiting_for_market = False
    ready_for_real_order = bool(goal_status.get("ready_for_real_order_action"))
    owner_stage = "等待机会" if waiting_for_market else "处理中"
    if blockers:
        owner_stage = "暂不可用"
    if ready_for_real_order:
        owner_stage = "处理中"
    owner_checkpoint = (
        "继续等待市场机会"
        if waiting_for_market
        else "等待系统完成收口"
    )

    checks = {
        "blockers": _dedupe(blockers),
        "product_gaps": _dedupe(product_gaps),
        "warnings": _dedupe(warnings),
        "runtime_head_matches_expected": (
            True if not expected_runtime_head else runtime_head == expected_runtime_head
        ),
        "watcher_timer_active": timer.get("active") == "active",
        "backend_active": backend.get("active") == "active",
        "source_readiness_ready": source_readiness.get("status") in {"ready", "ok"},
        "runtime_dry_run_audit_passed": (
            dry_run.get("status") == "passed" and not missing_dry_run_checks
        ),
        "runtime_dry_run_required_checks_present": not missing_dry_run_checks,
        "runtime_dry_run_missing_required_checks": missing_dry_run_checks,
        "runtime_execution_chain_closure_status_ready": (
            chain_closure.get("status") == "non_market_execution_chain_ready"
        ),
        "runtime_execution_chain_real_order_allowed": (
            _as_dict(chain_closure.get("real_execution")).get("real_order_allowed")
            is True
        ),
        "runtime_live_closure_evidence_status": (
            live_closure_verification.get("status") or "not_generated"
        ),
        "runtime_live_closure_evidence_reject_reasons": list(
            live_closure_verification.get("reject_reasons") or []
        ),
        "first_bounded_real_order_complete": first_bounded_real_order_complete,
        "real_order_closure_proven": real_order_closure_proven,
        "waiting_for_market": waiting_for_market,
        "runtime_goal_status_submit_blocker_keys": goal_status_submit_blockers,
        "runtime_goal_status_real_order_readiness_summary": (
            goal_status_real_order_readiness_summary
        ),
    }
    status = "ready"
    if checks["blockers"]:
        status = "blocked"
    elif checks["product_gaps"]:
        status = "product_gap"

    return {
        "status": status,
        "scope": "tokyo_runtime_snapshot",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interaction": {
            "level": (
                "L0_tokyo_local_snapshot"
                if _is_local_host(host)
                else "L1_readonly_snapshot"
            ),
            "remote_interaction_count": 0 if _is_local_host(host) else 1,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "report_dir": report_dir,
            "expected_runtime_head": expected_runtime_head,
        },
        "owner_summary": {
            "state": owner_stage,
            "non_authority_checkpoint": owner_checkpoint,
            "checkpoint_source": "tokyo_runtime_snapshot_projection",
            "owner_intervention_required": False if not checks["blockers"] else True,
            "runtime": "正常" if not checks["blockers"] else "暂不可用",
            "watcher": "运行中" if checks["watcher_timer_active"] else "暂不可用",
            "source_readiness": (
                "正常" if checks["source_readiness_ready"] else "暂不可用"
            ),
            "dry_run_audit": (
                "审计演练正常"
                if checks["runtime_dry_run_audit_passed"]
                else "审计演练暂不可用"
            ),
            "chain_closure": (
                "非市场链路已收口"
                if checks["runtime_execution_chain_closure_status_ready"]
                else "非市场链路待修复"
            ),
        },
        "facts": {
            "release": {
                "current_realpath": release.get("current_realpath"),
                "head": runtime_head,
                "manifest": release.get("manifest"),
            },
            "systemd": services,
            "reports": {
                "latest_summary": _summary_from_artifact(latest_summary),
                "goal_status": _summary_from_artifact(goal_status),
                "source_readiness": _summary_from_artifact(source_readiness),
                "runtime_dry_run_audit": _summary_from_artifact(dry_run),
                "runtime_execution_chain_closure_status": (
                    _summary_from_artifact(chain_closure)
                ),
                "runtime_live_closure_evidence": (
                    _summary_from_artifact(live_closure_evidence)
                ),
                "runtime_live_closure_evidence_verification": (
                    _summary_from_artifact(live_closure_verification)
                ),
            },
        },
        "checks": checks,
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


def _remote_snapshot_command(
    *,
    deploy_root: str,
    report_dir: str,
) -> str:
    remote_python = r'''
import json
import os
import re
import subprocess
import sys
from pathlib import Path

deploy_root = sys.argv[1]
report_dir = sys.argv[2]
services = [
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-signal-watcher.service",
    "brc-owner-console-backend.service",
]
report_files = [
    "watcher-tick.json",
    "latest-summary.json",
    "strategygroup-runtime-goal-status.json",
    "owner-console-source-readiness.json",
    "runtime-dry-run-audit-chain.json",
    "runtime-execution-chain-closure-status.json",
    "runtime-live-closure-evidence.json",
    "runtime-live-closure-evidence-verification.json",
]

def run(args):
    completed = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }

def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return {"exists": True, "payload": json.load(handle)}
    except FileNotFoundError:
        return {"exists": False, "payload": None}
    except json.JSONDecodeError as exc:
        return {"exists": True, "payload": None, "error": f"json_decode:{exc}"}
    except OSError as exc:
        return {"exists": False, "payload": None, "error": f"os_error:{exc}"}

current_path = os.path.join(deploy_root, "app", "current")
manifest_path = os.path.join(current_path, ".brc-release-manifest.json")
release_manifest = read_json(manifest_path)
release_payload = release_manifest.get("payload") if release_manifest.get("exists") else {}
if not isinstance(release_payload, dict):
    release_payload = {}

systemd = {}
for service in services:
    systemd[service] = {
        "active": run(["systemctl", "is-active", service])["stdout"],
        "enabled": run(["systemctl", "is-enabled", service])["stdout"],
    }

reports = {}
for filename in report_files:
    reports[filename] = read_json(os.path.join(report_dir, filename))

payload = {
    "collector_status": "ok",
    "hostname": run(["hostname"])["stdout"],
    "release": {
        "current_path": current_path,
        "current_realpath": os.path.realpath(current_path) if os.path.exists(current_path) else None,
        "manifest": release_payload,
        "head": (
            release_payload.get("head")
            or release_payload.get("commit")
            or (release_payload.get("local_git") or {}).get("head")
        ),
    },
    "systemd": systemd,
    "reports": reports,
    "collector_safety": {
        "remote_files_modified": False,
        "env_files_read": False,
        "secrets_read": False,
        "services_restarted": False,
        "exchange_write_called": False,
        "order_created": False,
    },
}
print(json.dumps(payload, sort_keys=True))
'''
    return (
        "python3 - "
        f"{shlex.quote(deploy_root)} "
        f"{shlex.quote(report_dir)} "
        "<<'PY'\n"
        f"{remote_python}\n"
        "PY"
    )


def _run(command: tuple[str, ...]) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _is_local_host(host: str) -> bool:
    return host in {"local", "localhost", "127.0.0.1", "::1"}


def _report_payload(reports: dict[str, Any], filename: str) -> dict[str, Any]:
    item = _as_dict(reports.get(filename))
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else {}


def _live_closure_verification_from_reports(
    *,
    reports: dict[str, Any],
    live_closure_evidence: dict[str, Any],
) -> dict[str, Any]:
    verification = _report_payload(
        reports,
        "runtime-live-closure-evidence-verification.json",
    )
    if verification:
        return verification
    if live_closure_evidence:
        return (
            runtime_live_closure_evidence_verifier
            .build_live_closure_evidence_verification(live_closure_evidence)
        )
    return {}


def _missing_dry_run_required_checks(checks: dict[str, Any]) -> list[str]:
    return sorted(name for name in REQUIRED_DRY_RUN_CHECKS if checks.get(name) is not True)


def _summary_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    dry_run_chain = _as_dict(artifact.get("dry_run_chain"))
    return {
        "status": artifact.get("status"),
        "owner_state": artifact.get("owner_state"),
        "blockers": artifact.get("blockers"),
        "scenario_count": artifact.get("scenario_count")
        or _as_dict(artifact.get("checks")).get("scenario_count"),
        "fresh_signal_present": _artifact_check(artifact, "fresh_signal_present"),
        "ready_for_real_order_action": artifact.get("ready_for_real_order_action"),
        "projected_checks": dry_run_chain.get("projected_checks"),
        "ready_segments": dry_run_chain.get("ready_segments"),
        "missing_or_failed_segments": dry_run_chain.get(
            "missing_or_failed_segments"
        ),
        "goal_chain_segments": dry_run_chain.get("goal_chain_segments"),
        "goal_chain_segment_evidence": dry_run_chain.get(
            "goal_chain_segment_evidence"
        ),
        "ready_goal_chain_segments": dry_run_chain.get(
            "ready_goal_chain_segments"
        ),
        "missing_or_failed_goal_chain_segments": dry_run_chain.get(
            "missing_or_failed_goal_chain_segments"
        ),
        "submit_blocker_keys": _goal_status_submit_blocker_keys(artifact),
        "real_order_readiness_summary": _goal_status_real_order_readiness_summary(
            artifact
        ),
    }


def _artifact_check(artifact: dict[str, Any], key: str) -> Any:
    if key in artifact:
        return artifact.get(key)
    checks = _as_dict(artifact.get("checks"))
    return checks.get(key)


def _goal_status_submit_blocker_keys(artifact: dict[str, Any]) -> list[str]:
    matrix = artifact.get("real_order_readiness_matrix")
    if not isinstance(matrix, list):
        return []
    keys: list[str] = []
    for item in matrix:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "blocked":
            continue
        if item.get("blocks_real_submit") is not True:
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            keys.append(key)
    return _dedupe(keys)


def _goal_status_real_order_readiness_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    matrix = artifact.get("real_order_readiness_matrix")
    if not isinstance(matrix, list):
        return {
            "total": 0,
            "pass": 0,
            "waiting": 0,
            "blocked": 0,
            "submit_blocker_keys": [],
            "waiting_keys": [],
        }
    summary = {
        "total": 0,
        "pass": 0,
        "waiting": 0,
        "blocked": 0,
        "submit_blocker_keys": [],
        "waiting_keys": [],
    }
    submit_blockers: list[str] = []
    waiting_keys: list[str] = []
    for item in matrix:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        status = str(item.get("status") or "")
        if not isinstance(key, str) or not key:
            key = "unknown"
        summary["total"] += 1
        if status == "pass":
            summary["pass"] += 1
        elif status == "blocked":
            summary["blocked"] += 1
            if item.get("blocks_real_submit") is True:
                submit_blockers.append(key)
        elif status.startswith("waiting"):
            summary["waiting"] += 1
            waiting_keys.append(key)
        else:
            summary["blocked"] += 1
            if item.get("blocks_real_submit") is True:
                submit_blockers.append(key)
    summary["submit_blocker_keys"] = _dedupe(submit_blockers)
    summary["waiting_keys"] = _dedupe(waiting_keys)
    return summary


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect one read-only Tokyo runtime snapshot."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--expected-runtime-head", default=None)
    parser.add_argument("--connect-timeout-seconds", type=int, default=8)
    parser.add_argument(
        "--output-json",
        default=None,
        help="Atomically write the snapshot JSON to this path.",
    )
    return parser.parse_args(argv)


def _write_text_atomic(path: Path, text: str) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _print_human_report(report: dict[str, Any]) -> None:
    owner = report["owner_summary"]
    checks = report["checks"]
    print(f"status={report['status']}")
    print(f"interaction={report['interaction']['level']}")
    print(f"owner_state={owner['state']}")
    print(f"non_authority_checkpoint={owner['non_authority_checkpoint']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["product_gaps"]:
        print("product_gaps=" + ",".join(checks["product_gaps"]))


if __name__ == "__main__":
    raise SystemExit(main())
