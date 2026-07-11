#!/usr/bin/env python3
"""Read-only post-deploy verification for Tokyo runtime governance.

This verifier runs SSH/curl read-only checks against the Tokyo backend after a
controlled deployment. It does not write remote files, source env files, read
secrets, connect to a database directly, run migrations, restart services,
create execution records, create orders, call OrderLifecycle, or call exchange
APIs. Trading Console checks use `include_exchange=false`.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


DEFAULT_HOST = "tokyo"
DEFAULT_DEPLOY_ROOT = "~/brc-deploy"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_EXPECTED_MIGRATION_COUNT = 114
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-07-11-114_extend_exchange_commands_for_lifecycle.py"
)
DEFAULT_COMMAND_TIMEOUT_SECONDS = 20


class PostDeployVerifyError(RuntimeError):
    """Raised when post-deploy verification cannot collect required facts."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


Runner = Callable[[tuple[str, ...]], CommandResult]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_postdeploy_report(
        host=args.host,
        deploy_root=args.deploy_root,
        api_base=args.api_base,
        expected_current_head=args.expected_current_head,
        expected_migration_count=args.expected_migration_count,
        expected_latest_migration=args.expected_latest_migration,
        connect_timeout_seconds=args.connect_timeout_seconds,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["checks"]["postdeploy_acceptance_passed"] else 2


def build_postdeploy_report(
    *,
    host: str,
    deploy_root: str,
    api_base: str,
    expected_current_head: str,
    expected_migration_count: int,
    expected_latest_migration: str,
    connect_timeout_seconds: int,
    runner: Runner | None = None,
) -> dict[str, Any]:
    command_runner = runner or _run
    root = _remote_path(deploy_root)
    current_path = f"{root}/app/current"
    quoted_current_path = _quote_remote_path(current_path)

    release_identity = _remote_release_identity(
        host,
        quoted_current_path=quoted_current_path,
        connect_timeout_seconds=connect_timeout_seconds,
        runner=command_runner,
    )
    facts = {
        "host": _ssh_text(
            host,
            "hostname",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "current_realpath": _ssh_text(
            host,
            f"readlink -f {quoted_current_path}",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "release_identity": release_identity,
        "release_identity_source": release_identity["source"],
        "current_head": release_identity["head"],
        "migration_count": _ssh_text(
            host,
            (
                f"cd {quoted_current_path} && "
                "find migrations/versions -type f -name '*.py' | wc -l | tr -d ' '"
            ),
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "latest_migration": _ssh_text(
            host,
            (
                f"cd {quoted_current_path} && "
                "find migrations/versions -type f -name '*.py' -printf '%f\\n' "
                "| sort | tail -1"
            ),
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "lifecycle_timer_enabled": _ssh_text(
            host,
            "systemctl is-enabled brc-ticket-lifecycle-maintenance.timer",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "lifecycle_timer_active": _ssh_text(
            host,
            "systemctl is-active brc-ticket-lifecycle-maintenance.timer",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "lifecycle_service_result": _ssh_text(
            host,
            "systemctl show brc-ticket-lifecycle-maintenance.service "
            "--property=Result --property=ExecMainStatus --value",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "lifecycle_units_match_release": _ssh_text(
            host,
            "cmp -s /etc/systemd/system/brc-ticket-lifecycle-maintenance.service "
            f"{quoted_current_path}/deploy/systemd/brc-ticket-lifecycle-maintenance.service "
            "&& cmp -s /etc/systemd/system/brc-ticket-lifecycle-maintenance.timer "
            f"{quoted_current_path}/deploy/systemd/brc-ticket-lifecycle-maintenance.timer "
            "&& echo match",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "http_checks": _http_checks(
            host,
            api_base=api_base,
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
    }

    checks = evaluate_postdeploy_checks(
        facts=facts,
        expected_current_head=expected_current_head,
        expected_migration_count=expected_migration_count,
        expected_latest_migration=expected_latest_migration,
    )
    report = {
        "status": "postdeploy_acceptance_passed" if not checks["blockers"] else "blocked",
        "scope": "tokyo_runtime_governance_postdeploy_readonly_verification",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "api_base": api_base,
            "expected_current_head": expected_current_head,
            "expected_migration_count": expected_migration_count,
            "expected_latest_migration": expected_latest_migration,
        },
        "facts": facts,
        "checks": checks,
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "database_connected_directly": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "trading_console_include_exchange": False,
        },
    }
    return report


def evaluate_postdeploy_checks(
    *,
    facts: dict[str, Any],
    expected_current_head: str,
    expected_migration_count: int,
    expected_latest_migration: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    release_identity = facts.get("release_identity")
    current_head = (
        release_identity.get("head")
        if isinstance(release_identity, dict)
        else None
    )
    if current_head != expected_current_head:
        blockers.append("postdeploy_release_head_mismatch")
    if (
        isinstance(release_identity, dict)
        and release_identity.get("source") == "release_manifest"
    ):
        warnings.append("release_identity_from_manifest_without_git_status")

    migration_count = _int_or_none(facts.get("migration_count"))
    if migration_count != expected_migration_count:
        blockers.append("postdeploy_migration_count_mismatch")
    latest_migration = str(facts.get("latest_migration") or "").strip()
    if latest_migration != expected_latest_migration:
        blockers.append("postdeploy_latest_migration_mismatch")
    if str(facts.get("lifecycle_timer_enabled") or "").strip() != "enabled":
        blockers.append("postdeploy_lifecycle_timer_not_enabled")
    if str(facts.get("lifecycle_timer_active") or "").strip() != "active":
        blockers.append("postdeploy_lifecycle_timer_not_active")
    lifecycle_result = str(facts.get("lifecycle_service_result") or "").splitlines()
    if lifecycle_result != ["success", "0"]:
        blockers.append("postdeploy_lifecycle_service_last_run_failed")
    if str(facts.get("lifecycle_units_match_release") or "").strip() != "match":
        blockers.append("postdeploy_lifecycle_units_release_mismatch")

    http_checks = facts.get("http_checks")
    if not isinstance(http_checks, list):
        blockers.append("postdeploy_http_checks_missing")
        http_checks = []

    for item in http_checks:
        if not isinstance(item, dict):
            blockers.append("postdeploy_http_check_invalid")
            continue
        name = str(item.get("name") or "unknown")
        expected_status = item.get("expected_status")
        actual_status = item.get("http_status")
        if actual_status != expected_status:
            blockers.append(f"http_status_mismatch:{name}")
        if item.get("expect_json") and not isinstance(item.get("body_json"), dict):
            blockers.append(f"http_json_missing:{name}")

    health = _http_check_by_name(http_checks, "health")
    health_body = health.get("body_json") if isinstance(health, dict) else {}
    if isinstance(health_body, dict):
        if health_body.get("status") != "ok":
            blockers.append("health_status_not_ok")
        if health_body.get("runtime_bound") is not True:
            warnings.append("health_runtime_bound_not_true")
        if health_body.get("live_ready") is True:
            blockers.append("health_live_ready_true_after_deploy")
    else:
        blockers.append("health_body_json_missing")

    return {
        "postdeploy_acceptance_passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }


def _http_checks(
    host: str,
    *,
    api_base: str,
    connect_timeout_seconds: int,
    runner: Runner,
) -> list[dict[str, Any]]:
    base = api_base.rstrip("/")
    endpoints = [
        {
            "name": "health",
            "method": "GET",
            "path": "/api/health",
            "expected_status": 200,
            "expect_json": True,
        },
        {
            "name": "trading_console_strategy_runtimes",
            "method": "GET",
            "path": "/api/trading-console/strategy-runtimes?limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_runtime_profile_proposal",
            "method": "GET",
            "path": (
                "/api/trading-console/strategy-runtime-profile-proposals"
                "?strategy_family_id=CPM-RO-001"
                "&strategy_family_version_id=CPM-RO-001-v0"
                "&symbol=BNB/USDT:USDT"
                "&side=long"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_strategy_family_admission_state",
            "method": "GET",
            "path": "/api/trading-console/strategy-family-admission-state",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_strategy_runtime_promotion_gate",
            "method": "GET",
            "path": (
                "/api/trading-console/strategy-runtime-promotion-gate"
                "?strategy_family_id=CPM-RO-001"
                "&strategy_family_version_id=CPM-RO-001-v0"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_owner_capital_review",
            "method": "GET",
            "path": "/api/trading-console/owner-capital-review?include_exchange=false&limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_right_tail_review",
            "method": "GET",
            "path": "/api/trading-console/right-tail-review?include_exchange=false&limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "brc_strategy_runtime_promotion_confirmations",
            "method": "GET",
            "path": "/api/brc/strategy-runtime-promotion-confirmations?limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "brc_owner_capital_adjustments",
            "method": "GET",
            "path": "/api/brc/owner-capital-adjustments?limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "brc_owner_capital_baseline_snapshots",
            "method": "GET",
            "path": "/api/brc/owner-capital-baseline-snapshots?limit=1",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_scheduled_observation_run_requires_auth",
            "method": "POST",
            "path": "/api/trading-console/strategy-observations/scheduled-runs",
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "runtime_execution_submit_rehearsal_requires_auth",
            "method": "GET",
            "path": (
                "/api/trading-console/runtime-execution-submit-rehearsals"
                "/authorizations/postdeploy-probe-authorization"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "runtime_execution_order_registration_draft_requires_auth",
            "method": "GET",
            "path": (
                "/api/trading-console/runtime-execution-order-registration-draft-previews"
                "/authorizations/postdeploy-probe-authorization"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "runtime_execution_recorded_intent_write_requires_auth",
            "method": "POST",
            "path": (
                "/api/trading-console/runtime-execution-intents"
                "/drafts/postdeploy-probe-draft"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "runtime_execution_attempt_mutation_write_requires_auth",
            "method": "POST",
            "path": (
                "/api/trading-console/runtime-execution-attempt-mutations"
                "/reservations/postdeploy-probe-reservation"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "runtime_execution_controlled_submit_write_requires_auth",
            "method": "POST",
            "path": (
                "/api/trading-console/runtime-execution-controlled-submit"
                "/authorizations/postdeploy-probe-authorization?submit_enabled=true"
            ),
            "expected_status": 401,
            "expect_json": True,
        },
        {
            "name": "trading_console_generic_post_blocked",
            "method": "POST",
            "path": "/api/trading-console/operations-cockpit",
            "expected_status": 405,
            "expect_json": False,
        },
    ]
    checks: list[dict[str, Any]] = []
    for endpoint in endpoints:
        checks.append(
            _remote_http(
                host,
                method=endpoint["method"],
                url=base + endpoint["path"],
                expected_status=int(endpoint["expected_status"]),
                expect_json=bool(endpoint["expect_json"]),
                name=endpoint["name"],
                connect_timeout_seconds=connect_timeout_seconds,
                runner=runner,
            )
        )
    return checks


def _remote_http(
    host: str,
    *,
    method: str,
    url: str,
    expected_status: int,
    expect_json: bool,
    name: str,
    connect_timeout_seconds: int,
    runner: Runner,
) -> dict[str, Any]:
    command = (
        f"curl -sS -m 8 -X {shlex.quote(method)} "
        f"-w '\\nHTTP_STATUS:%{{http_code}}' {shlex.quote(url)}"
    )
    raw = _ssh_text(
        host,
        command,
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    lines = raw.splitlines()
    status = None
    body_lines: list[str] = []
    for line in lines:
        if line.startswith("HTTP_STATUS:"):
            status = _int_or_none(line.removeprefix("HTTP_STATUS:"))
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    body_json = None
    if body:
        try:
            body_json = json.loads(body)
        except json.JSONDecodeError:
            body_json = None
    return {
        "name": name,
        "method": method,
        "url": url,
        "http_status": status,
        "expected_status": expected_status,
        "expect_json": expect_json,
        "body_json": body_json,
        "body_excerpt": body[:240],
    }


def _remote_release_identity(
    host: str,
    *,
    quoted_current_path: str,
    connect_timeout_seconds: int,
    runner: Runner,
) -> dict[str, Any]:
    head_result = _ssh_result(
        host,
        f"cd {quoted_current_path} && git rev-parse HEAD",
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    if head_result.returncode == 0 and head_result.stdout.strip():
        return {"source": "git", "head": head_result.stdout.strip(), "manifest": None}

    manifest_result = _ssh_result(
        host,
        f"cd {quoted_current_path} && cat .brc-release-manifest.json",
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    if manifest_result.returncode != 0 or not manifest_result.stdout.strip():
        raise PostDeployVerifyError(
            "remote release identity unavailable: git rev-parse failed and "
            ".brc-release-manifest.json was not readable"
        )
    try:
        manifest = json.loads(manifest_result.stdout)
    except json.JSONDecodeError as exc:
        raise PostDeployVerifyError("remote release manifest is not valid JSON") from exc
    local_git = manifest.get("local_git") if isinstance(manifest, dict) else None
    head = local_git.get("head") if isinstance(local_git, dict) else None
    if not head:
        raise PostDeployVerifyError("remote release manifest missing local_git.head")
    return {
        "source": "release_manifest",
        "head": str(head).strip(),
        "manifest": {
            "scope": manifest.get("scope"),
            "generated_at_utc": manifest.get("generated_at_utc"),
            "short_head": local_git.get("short_head") if isinstance(local_git, dict) else None,
        },
    }


def _http_check_by_name(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in items:
        if item.get("name") == name:
            return item
    return {}


def _remote_path(value: str) -> str:
    if value.startswith("~/"):
        return "$HOME/" + value[2:]
    return value


def _quote_remote_path(value: str) -> str:
    if value == "$HOME":
        return '"$HOME"'
    if value.startswith("$HOME/"):
        suffix = value.removeprefix("$HOME/")
        return '"$HOME"/' + shlex.quote(suffix)
    return shlex.quote(value)


def _ssh_text(
    host: str,
    remote_command: str,
    *,
    connect_timeout_seconds: int,
    runner: Runner,
    allow_empty: bool = False,
) -> str:
    result = _ssh_result(
        host,
        remote_command,
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    if result.returncode != 0:
        raise PostDeployVerifyError(
            f"remote command failed ({remote_command}): "
            f"{result.stderr or result.stdout}"
        )
    stdout = result.stdout.strip()
    if not stdout and not allow_empty:
        raise PostDeployVerifyError(f"remote command returned empty output: {remote_command}")
    return stdout


def _ssh_result(
    host: str,
    remote_command: str,
    *,
    connect_timeout_seconds: int,
    runner: Runner,
) -> CommandResult:
    return runner(
        (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={connect_timeout_seconds}",
            host,
            f"set -eu; {remote_command}",
        )
    )


def _run(command: tuple[str, ...]) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            stdout=exc.stdout or "",
            stderr=(
                (exc.stderr or "")
                + f"\ncommand timed out after {DEFAULT_COMMAND_TIMEOUT_SECONDS}s"
            ).strip(),
            returncode=124,
        )
    return CommandResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Tokyo runtime-governance deployment read-only."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument(
        "--expected-current-head",
        required=True,
        help="Expected deployed release commit after controlled deployment.",
    )
    parser.add_argument(
        "--expected-migration-count",
        type=int,
        default=DEFAULT_EXPECTED_MIGRATION_COUNT,
    )
    parser.add_argument(
        "--expected-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
    )
    parser.add_argument("--connect-timeout-seconds", type=int, default=8)
    return parser.parse_args(argv)


def _print_human_report(report: dict[str, Any]) -> None:
    checks = report["checks"]
    facts = report["facts"]
    release_identity = facts["release_identity"]
    print(f"status={report['status']}")
    print(f"host={facts['host']}")
    print(f"current_realpath={facts['current_realpath']}")
    print(f"release_identity_source={release_identity['source']}")
    print(f"current_head={release_identity['head']}")
    print(f"migration_count={facts['migration_count']}")
    print(f"latest_migration={facts['latest_migration']}")
    print(
        "postdeploy_acceptance_passed="
        + str(checks["postdeploy_acceptance_passed"]).lower()
    )
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PostDeployVerifyError as exc:
        print(f"postdeploy_verify_error={exc}", file=sys.stderr)
        raise SystemExit(2)
