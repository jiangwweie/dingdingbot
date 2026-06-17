#!/usr/bin/env python3
"""Publish the Owner Console static homepage to Tokyo with release metadata."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_HOST = "tokyo"
DEFAULT_DIST_DIR = "owner-runtime-console/dist"
DEFAULT_FRONTEND_ROOT = "/var/www/brc-owner-console"


@dataclass(frozen=True)
class ShellResult:
    command: str
    stdout: str
    stderr: str
    returncode: int


ShellRunner = Callable[[str], ShellResult]


class OwnerConsolePublishError(RuntimeError):
    """Raised when the frontend publish command cannot be prepared."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    report = publish_owner_console_frontend(
        repo_root=repo_root,
        dist_dir=repo_root / args.dist_dir,
        host=args.host,
        frontend_root=args.frontend_root,
        apply=args.apply,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"dry_run_ready", "applied"} else 2


def publish_owner_console_frontend(
    *,
    repo_root: Path,
    dist_dir: Path,
    host: str,
    frontend_root: str,
    apply: bool,
    runner: ShellRunner | None = None,
) -> dict[str, Any]:
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(repo_root, "rev-parse", "HEAD")
    blockers = _dist_blockers(dist_dir)
    if blockers:
        return _publish_report(
            status="blocked",
            repo_root=repo_root,
            dist_dir=dist_dir,
            host=host,
            frontend_root=frontend_root,
            branch=branch,
            head=head,
            apply=apply,
            blockers=blockers,
            command_results=[],
        )

    if not apply:
        return _publish_report(
            status="dry_run_ready",
            repo_root=repo_root,
            dist_dir=dist_dir,
            host=host,
            frontend_root=frontend_root,
            branch=branch,
            head=head,
            apply=False,
            blockers=[],
            command_results=[],
        )

    command_runner = runner or _run_shell
    with tempfile.TemporaryDirectory(prefix="brc-owner-console-publish-") as tmp:
        staging_dir = Path(tmp) / "site"
        shutil.copytree(dist_dir, staging_dir)
        release_manifest = _frontend_release_manifest(
            branch=branch,
            head=head,
            dist_dir=dist_dir,
            frontend_root=frontend_root,
        )
        (staging_dir / "frontend-release.json").write_text(
            json.dumps(release_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        command = _publish_command(
            staging_dir=staging_dir,
            host=host,
            frontend_root=frontend_root,
        )
        result = command_runner(command)

    command_results = [
        {
            "phase": "owner_console_frontend_publish",
            "command": result.command,
            "returncode": result.returncode,
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }
    ]
    status = "applied" if result.returncode == 0 else "failed"
    blockers = [] if result.returncode == 0 else ["frontend_publish_command_failed"]
    return _publish_report(
        status=status,
        repo_root=repo_root,
        dist_dir=dist_dir,
        host=host,
        frontend_root=frontend_root,
        branch=branch,
        head=head,
        apply=True,
        blockers=blockers,
        command_results=command_results,
    )


def _dist_blockers(dist_dir: Path) -> list[str]:
    blockers: list[str] = []
    if not dist_dir.exists():
        blockers.append("owner_console_dist_missing")
    if not (dist_dir / "index.html").exists():
        blockers.append("owner_console_dist_index_missing")
    return blockers


def _frontend_release_manifest(
    *,
    branch: str,
    head: str,
    dist_dir: Path,
    frontend_root: str,
) -> dict[str, Any]:
    return {
        "scope": "owner_console_frontend_static_release",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "head": head,
        "short_head": head[:8],
        "dist_dir": str(dist_dir),
        "frontend_root": frontend_root,
        "homepage_focus_only": True,
        "source_readiness_endpoint": (
            "/api/trading-console/owner-console-source-readiness"
        ),
        "safety_invariants": {
            "backend_service_restarted": False,
            "env_files_read": False,
            "secrets_read": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def _publish_command(
    *,
    staging_dir: Path,
    host: str,
    frontend_root: str,
) -> str:
    quoted_staging = _shell_quote(str(staging_dir))
    quoted_root = _shell_quote(frontend_root)
    remote_script = (
        "set -euo pipefail; "
        "tmp=$(mktemp -d /tmp/brc-owner-console.XXXXXX); "
        "tar -xzf - -C \"$tmp\"; "
        f"sudo mkdir -p {quoted_root}; "
        f"sudo rsync -a --delete \"$tmp\"/ {quoted_root}/; "
        "rm -rf \"$tmp\""
    )
    return (
        f"cd {quoted_staging} && "
        f"tar -czf - . | ssh {host} {_shell_quote(remote_script)}"
    )


def _publish_report(
    *,
    status: str,
    repo_root: Path,
    dist_dir: Path,
    host: str,
    frontend_root: str,
    branch: str,
    head: str,
    apply: bool,
    blockers: list[str],
    command_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "scope": "owner_console_frontend_homepage_publish",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "apply_requested": apply,
        "interaction": {
            "level": "L3_frontend_static_publish" if apply else "L1_publish_plan_only",
            "remote_interaction_count": 1 if apply else 0,
            "mutates_remote_files": bool(apply and status == "applied"),
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "inputs": {
            "repo_root": str(repo_root),
            "dist_dir": str(dist_dir),
            "host": host,
            "frontend_root": frontend_root,
            "branch": branch,
            "head": head,
        },
        "owner_summary": {
            "state": "首页已发布" if status == "applied" else "首页发布待执行",
            "owner_intervention_required": bool(blockers),
            "current_action": (
                "运行 L1 快照核验 frontend-release.json"
                if status == "applied"
                else "构建并发布 Owner Console 首页"
            ),
            "frontend_static_site": (
                "included" if status == "applied" else "planned"
            ),
            "blockers": blockers,
        },
        "checks": {
            "blockers": blockers,
            "dist_exists": dist_dir.exists(),
            "dist_index_exists": (dist_dir / "index.html").exists(),
            "commands_executed": len(command_results),
        },
        "command_results": command_results,
        "effects": {
            "remote_files_modified": bool(apply and status == "applied"),
            "frontend_static_site_published": bool(apply and status == "applied"),
            "frontend_release_marker_written": bool(apply and status == "applied"),
            "backend_service_restarted": False,
            "migrations_run": False,
            "secrets_read_by_codex": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
        "safety_invariants": {
            "backend_service_restarted": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _run_shell(command: str) -> ShellResult:
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return ShellResult(
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise OwnerConsolePublishError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _repo_root() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel"))


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _tail(value: str, *, max_chars: int = 2000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or publish Owner Console static homepage to Tokyo."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--dist-dir", default=DEFAULT_DIST_DIR)
    parser.add_argument("--frontend-root", default=DEFAULT_FRONTEND_ROOT)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


def _print_human_report(report: dict[str, Any]) -> None:
    print(f"status={report['status']}")
    print(f"interaction={report['interaction']['level']}")
    print(f"frontend_static_site={report['owner_summary']['frontend_static_site']}")
    if report["checks"]["blockers"]:
        print("blockers=" + ",".join(report["checks"]["blockers"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OwnerConsolePublishError as exc:
        print(f"owner_console_publish_error={exc}", file=sys.stderr)
        raise SystemExit(2)
