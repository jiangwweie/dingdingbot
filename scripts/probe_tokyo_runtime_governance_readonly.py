#!/usr/bin/env python3
"""Read-only Tokyo runtime-governance deployment probe.

This probe gathers remote deployment facts needed before a controlled release.
It performs SSH read-only commands only. It does not source env files, read
secret values, write remote files, run migrations, restart services, create
execution records, create orders, call OrderLifecycle, or call exchange APIs.
"""

from __future__ import annotations

import argparse
import json
import shlex
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


DEFAULT_HOST = "tokyo"
DEFAULT_DEPLOY_ROOT = "~/brc-deploy"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_EXPECTED_HEAD = "ae9b209e33cd287273491f2e93dfdff3b6a814fd"
DEFAULT_EXPECTED_MIGRATION_COUNT = 119
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-07-13-119_action_time_invocation_consistency.py"
)
BACKEND_PROCESS_MARKER = "python -m " + "src.main"


class TokyoProbeError(RuntimeError):
    """Raised when the read-only probe cannot collect required facts."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


Runner = Callable[[tuple[str, ...]], CommandResult]
SocketConnector = Callable[[str, int, float], None]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report = build_tokyo_probe_report(
            host=args.host,
            deploy_root=args.deploy_root,
            api_base=args.api_base,
            expected_current_head=args.expected_current_head,
            expected_migration_count=args.expected_migration_count,
            expected_latest_migration=args.expected_latest_migration,
            connect_timeout_seconds=args.connect_timeout_seconds,
        )
    except TokyoProbeError as exc:
        report = build_tokyo_probe_error_report(
            host=args.host,
            deploy_root=args.deploy_root,
            api_base=args.api_base,
            expected_current_head=args.expected_current_head,
            expected_migration_count=args.expected_migration_count,
            expected_latest_migration=args.expected_latest_migration,
            connect_timeout_seconds=args.connect_timeout_seconds,
            error=exc,
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["checks"]["ready_for_controlled_deploy_preflight"] else 2


def build_tokyo_probe_report(
    *,
    host: str,
    deploy_root: str,
    api_base: str,
    expected_current_head: str | None,
    expected_migration_count: int | None,
    expected_latest_migration: str | None,
    connect_timeout_seconds: int,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Collect and evaluate Tokyo deployment facts without remote mutation."""

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
        "user": _ssh_text(
            host,
            "whoami",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "current_realpath": _ssh_text(
            host,
            f"readlink -f {quoted_current_path}",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "release_identity_source": release_identity["source"],
        "release_manifest": release_identity["manifest"],
        "current_head": release_identity["head"],
        "current_status": release_identity["status"],
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
        "health": _remote_health(
            host,
            api_base=api_base,
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
        ),
        "process_snapshot": _ssh_text(
            host,
            (
                "ps -eo pid,ppid,user,comm,args "
                f"| egrep '({BACKEND_PROCESS_MARKER}|postgres|docker)' "
                "| grep -v -E '(grep|egrep)' | sed -n '1,80p'"
            ),
            connect_timeout_seconds=connect_timeout_seconds,
            runner=command_runner,
            allow_empty=True,
        ),
    }

    report = {
        "status": "ready_for_controlled_deploy_preflight",
        "scope": "tokyo_runtime_governance_readonly_probe",
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
        "checks": {},
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }
    checks = evaluate_probe_checks(
        facts=facts,
        expected_current_head=expected_current_head,
        expected_migration_count=expected_migration_count,
        expected_latest_migration=expected_latest_migration,
    )
    report["checks"] = checks
    if checks["blockers"]:
        report["status"] = "blocked"
    return report


def build_tokyo_connectivity_probe(
    *,
    host: str,
    ports: tuple[int, ...] = (22,),
    connect_timeout_seconds: int = 6,
    connector: SocketConnector | None = None,
) -> dict[str, Any]:
    """Classify local-to-Tokyo network reachability without remote mutation."""

    connect = connector or _socket_connect
    dns_error: str | None = None
    resolved_addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(host, None)
        resolved_addresses = sorted(
            {
                str(item[4][0])
                for item in infos
                if len(item) >= 5 and item[4] and item[4][0]
            }
        )
    except OSError as exc:
        dns_error = f"{type(exc).__name__}:{exc}"

    port_results: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    if dns_error:
        blockers.append("tokyo_dns_resolution_failed")

    for port in ports:
        key = str(port)
        started_at = datetime.now(timezone.utc)
        try:
            connect(host, port, float(connect_timeout_seconds))
        except OSError as exc:
            port_results[key] = {
                "reachable": False,
                "error": f"{type(exc).__name__}:{exc}",
                "started_at_utc": started_at.isoformat(),
            }
            blockers.append(f"tokyo_tcp_{port}_unreachable")
        else:
            port_results[key] = {
                "reachable": True,
                "error": None,
                "started_at_utc": started_at.isoformat(),
            }

    checks = {
        "dns_resolved": dns_error is None,
        "tcp_ports_reachable": all(
            item.get("reachable") is True for item in port_results.values()
        ),
        "blockers": _dedupe(blockers),
    }
    return {
        "status": "ready" if not checks["blockers"] else "blocked",
        "scope": "tokyo_runtime_governance_connectivity_probe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "host": host,
            "ports": list(ports),
            "connect_timeout_seconds": connect_timeout_seconds,
        },
        "facts": {
            "resolved_addresses": resolved_addresses,
            "dns_error": dns_error,
            "ports": port_results,
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
            "exchange_called": False,
        },
    }


def build_tokyo_probe_error_report(
    *,
    host: str,
    deploy_root: str,
    api_base: str,
    expected_current_head: str | None,
    expected_migration_count: int | None,
    expected_latest_migration: str | None,
    connect_timeout_seconds: int,
    error: Exception,
) -> dict[str, Any]:
    error_text = str(error)
    blockers = [_classify_probe_error(error_text)]
    return {
        "status": "blocked",
        "scope": "tokyo_runtime_governance_readonly_probe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "api_base": api_base,
            "expected_current_head": expected_current_head,
            "expected_migration_count": expected_migration_count,
            "expected_latest_migration": expected_latest_migration,
            "connect_timeout_seconds": connect_timeout_seconds,
        },
        "facts": {
            "host": None,
            "user": None,
            "current_realpath": None,
            "release_identity_source": None,
            "release_manifest": None,
            "current_head": None,
            "current_status": None,
            "migration_count": None,
            "latest_migration": None,
            "health": {"http_status": None, "body": "", "body_json": None},
            "process_snapshot": "",
            "probe_error": error_text,
        },
        "checks": {
            "ready_for_controlled_deploy_preflight": False,
            "blockers": blockers,
            "warnings": [],
            "dirty_status_lines": [],
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
            "exchange_called": False,
        },
    }


def evaluate_probe_checks(
    *,
    facts: dict[str, Any],
    expected_current_head: str | None,
    expected_migration_count: int | None,
    expected_latest_migration: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    current_head = str(facts.get("current_head") or "").strip()
    if not current_head:
        blockers.append("remote_current_head_missing")
    elif expected_current_head and current_head != expected_current_head:
        blockers.append("remote_current_head_mismatch")

    current_status = str(facts.get("current_status") or "")
    release_identity_source = str(facts.get("release_identity_source") or "")
    dirty_lines = [
        line
        for line in current_status.splitlines()
        if (
            line
            and not line.startswith("## ")
            and line != "release_manifest_without_git_status"
        )
    ]
    if dirty_lines:
        blockers.append("remote_current_release_worktree_dirty")
    if release_identity_source == "release_manifest":
        warnings.append("remote_release_identity_from_manifest_without_git_status")

    migration_count = _int_or_none(facts.get("migration_count"))
    if migration_count is None:
        blockers.append("remote_migration_count_unreadable")
    elif expected_migration_count is not None and migration_count != expected_migration_count:
        blockers.append("remote_migration_count_mismatch")

    latest_migration = str(facts.get("latest_migration") or "").strip()
    if not latest_migration:
        blockers.append("remote_latest_migration_missing")
    elif expected_latest_migration and latest_migration != expected_latest_migration:
        blockers.append("remote_latest_migration_mismatch")

    health = facts.get("health") if isinstance(facts.get("health"), dict) else {}
    if health.get("http_status") != 200:
        blockers.append("remote_health_http_not_ok")
    body = health.get("body_json") if isinstance(health.get("body_json"), dict) else {}
    if body.get("status") != "ok":
        blockers.append("remote_health_status_not_ok")
    if body.get("live_ready") is True:
        blockers.append("remote_health_live_ready_true_before_controlled_deploy")
    if body.get("runtime_bound") is not True:
        warnings.append("remote_health_runtime_bound_not_true")

    process_snapshot = str(facts.get("process_snapshot") or "")
    if BACKEND_PROCESS_MARKER not in process_snapshot:
        blockers.append("remote_backend_process_not_found")
    if "postgres" not in process_snapshot:
        warnings.append("remote_postgres_process_not_visible")

    return {
        "ready_for_controlled_deploy_preflight": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "dirty_status_lines": dirty_lines,
    }


def _classify_probe_error(error_text: str) -> str:
    normalized = error_text.lower()
    if "permission denied" in normalized and "publickey" in normalized:
        return "tokyo_ssh_publickey_denied"
    if "could not resolve hostname" in normalized or "name or service not known" in normalized:
        return "tokyo_dns_resolution_failed"
    if "timed out" in normalized or "operation timed out" in normalized:
        return "tokyo_ssh_timeout"
    if "connection refused" in normalized:
        return "tokyo_ssh_connection_refused"
    return "tokyo_readonly_probe_failed"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only Tokyo deployment facts for runtime governance."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host alias.")
    parser.add_argument(
        "--deploy-root",
        default=DEFAULT_DEPLOY_ROOT,
        help="Remote deployment root.",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="Remote local API base used for health check.",
    )
    parser.add_argument(
        "--expected-current-head",
        default=DEFAULT_EXPECTED_HEAD,
        help="Expected current remote release commit before controlled deploy.",
    )
    parser.add_argument(
        "--expected-migration-count",
        type=int,
        default=DEFAULT_EXPECTED_MIGRATION_COUNT,
        help="Expected current remote migration-file count before controlled deploy.",
    )
    parser.add_argument(
        "--expected-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
        help="Expected current remote latest migration filename before controlled deploy.",
    )
    parser.add_argument(
        "--connect-timeout-seconds",
        type=int,
        default=8,
        help="SSH connection timeout.",
    )
    return parser.parse_args(argv)


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


def _remote_health(
    host: str,
    *,
    api_base: str,
    connect_timeout_seconds: int,
    runner: Runner,
) -> dict[str, Any]:
    command = (
        f"curl -fsS -m 5 -w '\\nHTTP_STATUS:%{{http_code}}' "
        f"{shlex.quote(api_base.rstrip('/') + '/api/health')}"
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
    try:
        body_json = json.loads(body) if body else None
    except json.JSONDecodeError:
        body_json = None
    return {
        "http_status": status,
        "body": body,
        "body_json": body_json,
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
        status = _ssh_text(
            host,
            f"cd {quoted_current_path} && git status --short --branch",
            connect_timeout_seconds=connect_timeout_seconds,
            runner=runner,
        )
        return {
            "source": "git",
            "head": head_result.stdout.strip(),
            "status": status,
            "manifest": None,
        }

    manifest_result = _ssh_result(
        host,
        f"cd {quoted_current_path} && cat .brc-release-manifest.json",
        connect_timeout_seconds=connect_timeout_seconds,
        runner=runner,
    )
    if manifest_result.returncode != 0 or not manifest_result.stdout.strip():
        detail = "; ".join(
            item
            for item in [
                f"git_error={head_result.stderr or head_result.stdout}".strip(),
                (
                    "manifest_error="
                    f"{manifest_result.stderr or manifest_result.stdout}"
                ).strip(),
            ]
            if item and not item.endswith("=")
        )
        raise TokyoProbeError(
            "remote release identity unavailable: git rev-parse failed and "
            ".brc-release-manifest.json was not readable"
            + (f"; {detail}" if detail else "")
        )
    try:
        manifest = json.loads(manifest_result.stdout)
    except json.JSONDecodeError as exc:
        raise TokyoProbeError("remote release manifest is not valid JSON") from exc
    head = (
        manifest.get("local_git", {}).get("head")
        if isinstance(manifest.get("local_git"), dict)
        else None
    )
    if not head:
        raise TokyoProbeError("remote release manifest missing local_git.head")
    return {
        "source": "release_manifest",
        "head": str(head).strip(),
        "status": "release_manifest_without_git_status",
        "manifest": {
            "scope": manifest.get("scope"),
            "generated_at_utc": manifest.get("generated_at_utc"),
            "short_head": manifest.get("local_git", {}).get("short_head")
            if isinstance(manifest.get("local_git"), dict)
            else None,
        },
    }


def _ssh_text(
    host: str,
    remote_command: str,
    *,
    connect_timeout_seconds: int,
    runner: Runner,
    allow_empty: bool = False,
) -> str:
    result = runner(
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
    if result.returncode != 0:
        raise TokyoProbeError(
            f"remote command failed ({remote_command}): "
            f"{result.stderr or result.stdout}"
        )
    stdout = result.stdout.strip()
    if not stdout and not allow_empty:
        raise TokyoProbeError(f"remote command returned empty output: {remote_command}")
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


def _socket_connect(host: str, port: int, timeout: float) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _print_human_report(report: dict[str, Any]) -> None:
    facts = report["facts"]
    checks = report["checks"]
    health = facts["health"]
    print(f"status={report['status']}")
    print(f"host={facts['host']}")
    print(f"user={facts['user']}")
    print(f"current_realpath={facts['current_realpath']}")
    print(f"release_identity_source={facts['release_identity_source']}")
    print(f"current_head={facts['current_head']}")
    print(f"migration_count={facts['migration_count']}")
    print(f"latest_migration={facts['latest_migration']}")
    print(f"health_http_status={health['http_status']}")
    print(f"health_body={health['body']}")
    if facts.get("probe_error"):
        print(f"probe_error={facts['probe_error']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))
    print(
        "ready_for_controlled_deploy_preflight="
        + str(checks["ready_for_controlled_deploy_preflight"]).lower()
    )


if __name__ == "__main__":
    raise SystemExit(main())
