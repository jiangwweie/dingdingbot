#!/usr/bin/env python3
"""Plan a git-based Tokyo runtime-governance deployment.

This is the preferred deployment plan for follow-up runtime-governance stages.
It avoids uploading a local archive: Tokyo fetches a pushed branch head from the
repository, exports that exact commit into a clean release directory, writes a
release manifest, then follows the same backup/migration/restart/smoke gates as
the archive fallback.

Default behavior is dry-run planning only. This script does not SSH, fetch on
Tokyo, write remote files, run migrations, restart services, create orders, call
OrderLifecycle, or call exchange APIs.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.plan_tokyo_runtime_governance_deploy import (
    CONFIRMATION_PHRASE,
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_ENV_PATH,
    DEFAULT_HOST,
    DEFAULT_PG_CONTAINER_NAME,
    DEFAULT_SERVICE_NAME,
    DEFAULT_VENV_PYTHON,
)


DEFAULT_GIT_REF = "dev"
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-06-10-070_add_execution_intent_local_orders_registered_status.py"
)


class GitDeployPlanError(RuntimeError):
    """Raised when git deployment planning cannot proceed."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    repo_url = args.repo_url or _git(repo_root, "remote", "get-url", "origin").stdout
    report = build_git_deploy_plan(
        repo_root=repo_root,
        repo_url=repo_url,
        git_ref=args.git_ref,
        target_commit=args.target_commit,
        release_name=args.release_name,
        host=args.host,
        deploy_root=args.deploy_root,
        service_name=args.service_name,
        env_path=args.env_path,
        venv_python=args.venv_python,
        api_base=args.api_base,
        previous_release=args.previous_release,
        expected_deployed_head=args.expected_deployed_head,
        expected_remote_migration_count=args.expected_remote_migration_count,
        expected_remote_latest_migration=args.expected_remote_latest_migration,
        expected_latest_migration=args.expected_latest_migration,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["checks"]["ready_for_owner_authorized_remote_deploy"] else 2


def build_git_deploy_plan(
    *,
    repo_root: Path,
    repo_url: str,
    git_ref: str,
    target_commit: str | None,
    release_name: str | None,
    host: str,
    deploy_root: str,
    service_name: str,
    env_path: str,
    venv_python: str,
    api_base: str,
    previous_release: str,
    expected_deployed_head: str,
    expected_remote_migration_count: int,
    expected_remote_latest_migration: str,
    expected_latest_migration: str = DEFAULT_EXPECTED_LATEST_MIGRATION,
) -> dict[str, Any]:
    """Build a non-executing git deployment command plan."""

    head = _git(repo_root, "rev-parse", "HEAD").stdout
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD").stdout
    branch = _git(repo_root, "branch", "--show-current").stdout
    target = target_commit or head
    tracked_dirty = _tracked_dirty(repo_root)
    blockers: list[str] = []
    warnings: list[str] = []

    if tracked_dirty:
        blockers.append("tracked_worktree_dirty")
    if not repo_url.strip():
        blockers.append("git_repo_url_required")
    if git_ref.startswith("refs/"):
        blockers.append("git_deploy_v1_requires_branch_name_not_full_ref")
    if not git_ref.strip():
        blockers.append("git_ref_required")
    if _git(repo_root, "cat-file", "-e", f"{target}^{{commit}}").returncode != 0:
        blockers.append("target_commit_not_found_locally")

    remote_ref_head = None
    if repo_url.strip() and git_ref.strip() and not git_ref.startswith("refs/"):
        remote_ref_head = _remote_branch_head(repo_url=repo_url, branch=git_ref)
        if not remote_ref_head:
            blockers.append("target_git_ref_missing_on_remote")
        elif remote_ref_head != target:
            blockers.append("target_commit_not_remote_branch_head")

    final_release_name = release_name or _default_release_name(short_head)
    if not final_release_name.startswith("brc-runtime-governance-"):
        warnings.append("release_name_not_standard_runtime_governance_prefix")

    deploy_root = deploy_root.rstrip("/")
    source_root = f"{deploy_root}/source"
    source_repo_path = f"{source_root}/dingdingbot"
    releases_dir = f"{deploy_root}/releases"
    reports_dir = f"{deploy_root}/reports/{final_release_name}"
    backups_dir = f"{deploy_root}/backups"
    app_current = f"{deploy_root}/app/current"
    remote_release_path = f"{releases_dir}/{final_release_name}"
    remote_tmp_release_path = f"{remote_release_path}.tmp"
    backup_path = f"{backups_dir}/{final_release_name}.pgdump"
    release_manifest = f"{remote_release_path}/.brc-release-manifest.json"
    manifest_payload = _release_manifest_payload(
        branch=branch,
        git_ref=git_ref,
        repo_url=repo_url,
        target_commit=target,
        short_head=short_head,
    )

    plan_phases = _plan_phases(
        host=host,
        repo_root=repo_root,
        repo_url=repo_url,
        git_ref=git_ref,
        target_commit=target,
        source_root=source_root,
        source_repo_path=source_repo_path,
        reports_dir=reports_dir,
        backups_dir=backups_dir,
        app_current=app_current,
        remote_release_path=remote_release_path,
        remote_tmp_release_path=remote_tmp_release_path,
        release_manifest=release_manifest,
        backup_path=backup_path,
        service_name=service_name,
        env_path=env_path,
        venv_python=venv_python,
        api_base=api_base,
        previous_release=previous_release,
        expected_deployed_head=expected_deployed_head,
        expected_remote_migration_count=expected_remote_migration_count,
        expected_remote_latest_migration=expected_remote_latest_migration,
        expected_latest_migration=expected_latest_migration,
        manifest_payload=manifest_payload,
    )

    return {
        "status": (
            "ready_for_owner_authorized_remote_git_deploy_plan"
            if not blockers
            else "blocked"
        ),
        "scope": "tokyo_runtime_governance_git_deploy_plan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "repo_url": repo_url,
            "git_ref": git_ref,
            "target_commit": target,
            "release_name": final_release_name,
            "service_name": service_name,
            "env_path": env_path,
            "venv_python": venv_python,
            "api_base": api_base,
            "previous_release": previous_release,
            "expected_deployed_head": expected_deployed_head,
            "expected_remote_migration_count": expected_remote_migration_count,
            "expected_remote_latest_migration": expected_remote_latest_migration,
            "expected_latest_migration": expected_latest_migration,
        },
        "release": {
            "head": target,
            "short_head": target[:8],
            "local_head": head,
            "local_branch": branch,
            "remote_ref_head": remote_ref_head,
            "release_name": final_release_name,
            "source_repo_path": source_repo_path,
            "remote_release_path": remote_release_path,
            "remote_tmp_release_path": remote_tmp_release_path,
            "remote_release_manifest_path": release_manifest,
            "backup_path": backup_path,
        },
        "checks": {
            "ready_for_owner_authorized_remote_deploy": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "remote_mutation_requires_confirmation_phrase": CONFIRMATION_PHRASE,
        },
        "plan_phases": plan_phases,
        "safety_invariants": {
            "planning_run_only": True,
            "ssh_called": False,
            "scp_called": False,
            "remote_files_modified": False,
            "database_connected": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "secrets_read": False,
        },
    }


def _plan_phases(
    *,
    host: str,
    repo_root: Path,
    repo_url: str,
    git_ref: str,
    target_commit: str,
    source_root: str,
    source_repo_path: str,
    reports_dir: str,
    backups_dir: str,
    app_current: str,
    remote_release_path: str,
    remote_tmp_release_path: str,
    release_manifest: str,
    backup_path: str,
    service_name: str,
    env_path: str,
    venv_python: str,
    api_base: str,
    previous_release: str,
    expected_deployed_head: str,
    expected_remote_migration_count: int,
    expected_remote_latest_migration: str,
    expected_latest_migration: str,
    manifest_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    q = shlex.quote
    local_python = "/opt/homebrew/bin/python3"
    manifest_json = json.dumps(manifest_payload, indent=2, sort_keys=True)
    health_url = api_base.rstrip("/") + "/api/health"
    health_wait_command = (
        f"set -eu; HEALTH_URL={q(health_url)}; "
        "for attempt in $(seq 1 30); do "
        'curl -fsS "$HEALTH_URL" 2>/dev/null && exit 0; '
        "sleep 1; "
        "done; "
        'curl -fsS "$HEALTH_URL"'
    )
    remote_fetch_ref = f"refs/heads/{git_ref}:refs/remotes/origin/{git_ref}"
    remote_export_command = (
        f"set -eu; mkdir -p {q(source_root)} {q(reports_dir)} {q(backups_dir)}; "
        f"if [ ! -d {q(source_repo_path)}/.git ]; then "
        f"git clone --no-checkout {q(repo_url)} {q(source_repo_path)}; "
        "fi; "
        f"cd {q(source_repo_path)}; "
        f"git remote set-url origin {q(repo_url)}; "
        f"git fetch --prune origin {q(remote_fetch_ref)}; "
        f"test $(git rev-parse {q('refs/remotes/origin/' + git_ref)}) = {q(target_commit)}; "
        f"git cat-file -e {q(target_commit + '^{commit}')}; "
        f"test ! -e {q(remote_release_path)}; "
        f"rm -rf {q(remote_tmp_release_path)}; "
        f"mkdir -p {q(remote_tmp_release_path)}; "
        f"git archive {q(target_commit)} | tar -x -C {q(remote_tmp_release_path)}; "
        f"cat > {q(remote_tmp_release_path + '/.brc-release-manifest.json')} <<'JSON'\n"
        f"{manifest_json}\nJSON\n"
        f"mv {q(remote_tmp_release_path)} {q(remote_release_path)}; "
        f"test $(readlink -f {q(app_current)}) = {q(previous_release)}"
    )

    return [
        {
            "phase": "0_local_preflight",
            "remote_mutation": False,
            "commands": [
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/prepare_tokyo_runtime_governance_release.py --json "
                f"--deployed-head {q(expected_deployed_head)}",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/audit_tokyo_runtime_governance_migration_gap.py --json "
                "--base-revision 064 --head-revision 070 "
                "--expected-revision-count 6",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/verify_runtime_submit_rehearsal_pre_live_packet.py --json "
                "--skip-current-head-deployed-check",
            ],
            "stop_if": [
                "local release readiness is not true",
                "target commit is not the pushed remote branch head",
                "migration gap audit does not pass",
                "shadow-planning rehearsal does not pass",
                "runtime submit pre-live packet contains forbidden execution flags",
            ],
        },
        {
            "phase": "1_remote_preflight_readonly",
            "remote_mutation": False,
            "commands": [
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/probe_tokyo_runtime_governance_readonly.py --json "
                f"--expected-current-head {q(expected_deployed_head)} "
                f"--expected-migration-count {expected_remote_migration_count} "
                f"--expected-latest-migration {q(expected_remote_latest_migration)}",
            ],
            "stop_if": [
                "remote current head differs from expected baseline",
                "remote migration state differs from expected baseline",
                "health live_ready is true",
            ],
        },
        {
            "phase": "2_owner_authorized_git_fetch_and_export",
            "remote_mutation": True,
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [_ssh(host, remote_export_command)],
            "stop_if": [
                "target release path already exists",
                "remote git fetch cannot reach the repository",
                "remote branch head is not the target commit",
                "app/current no longer points to the expected previous release",
            ],
        },
        {
            "phase": "3_quiesce_backup_and_migrate",
            "remote_mutation": True,
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [
                _ssh(host, f"sudo -n systemctl stop {q(service_name)}"),
                _ssh(
                    host,
                    (
                        "set -eu; umask 077; set -a; "
                        f". {q(env_path)}; set +a; "
                        'DB_URL="${PG_DATABASE_URL:-${DATABASE_URL:-}}"; '
                        'test -n "$DB_URL" || '
                        "{ echo PG_DATABASE_URL_or_DATABASE_URL_required >&2; exit 2; }; "
                        "if command -v pg_dump >/dev/null 2>&1; then "
                        f"pg_dump \"$DB_URL\" -Fc -f {q(backup_path)}; "
                        "else "
                        f"DB_USER=$({q(venv_python)} -c "
                        "'import os; from urllib.parse import urlparse; "
                        "print(urlparse(os.environ[\"PG_DATABASE_URL\"]).username or \"\")'); "
                        f"DB_NAME=$({q(venv_python)} -c "
                        "'import os; from urllib.parse import urlparse; "
                        "print((urlparse(os.environ[\"PG_DATABASE_URL\"]).path or \"/\").lstrip(\"/\"))'); "
                        'test -n "$DB_USER"; test -n "$DB_NAME"; '
                        f"sudo -n docker exec {q(DEFAULT_PG_CONTAINER_NAME)} "
                        'pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc '
                        f"> {q(backup_path)}; "
                        "fi"
                    ),
                ),
                _ssh(
                    host,
                    (
                        f"set -eu; cd {q(remote_release_path)}; set -a; "
                        f". {q(env_path)}; set +a; "
                        f"PYTHONPATH=$PWD {q(venv_python)} -m compileall -q src; "
                        f"PYTHONPATH=$PWD {q(venv_python)} -m alembic heads; "
                        f"PYTHONPATH=$PWD {q(venv_python)} -m alembic upgrade head"
                    ),
                ),
            ],
            "stop_if": [
                "service cannot be stopped with non-interactive sudo",
                "database backup is not created",
                "alembic upgrade fails",
            ],
        },
        {
            "phase": "4_switch_start_and_smoke",
            "remote_mutation": True,
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [
                _ssh(host, f"set -eu; ln -sfn {q(remote_release_path)} {q(app_current)}"),
                _ssh(host, f"sudo -n systemctl start {q(service_name)}"),
                _ssh(host, f"sudo -n systemctl is-active {q(service_name)}"),
                _ssh(host, health_wait_command),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/probe_tokyo_runtime_governance_readonly.py --json "
                    f"--expected-current-head {q(target_commit)} "
                    "--expected-migration-count 70 "
                    f"--expected-latest-migration {q(expected_latest_migration)}"
                ),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/verify_tokyo_runtime_governance_postdeploy.py --json "
                    f"--expected-current-head {q(target_commit)}"
                ),
                _ssh(
                    host,
                    (
                        f"test -f {q(release_manifest)} && "
                        f"test $(readlink -f {q(app_current)}) = {q(remote_release_path)}"
                    ),
                ),
            ],
            "stop_if": [
                "service is not active",
                "health is not ok",
                "health live_ready is true",
                "post-deploy readonly probe fails",
            ],
        },
    ]


def _release_manifest_payload(
    *,
    branch: str,
    git_ref: str,
    repo_url: str,
    target_commit: str,
    short_head: str,
) -> dict[str, Any]:
    return {
        "scope": "tokyo_runtime_governance_git_release",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "local_git": {
            "branch": branch,
            "head": target_commit,
            "short_head": short_head,
        },
        "git_deploy": {
            "repo_url": repo_url,
            "git_ref": git_ref,
            "source": "remote_git_fetch_export",
            "archive_uploaded": False,
        },
    }


def _remote_branch_head(*, repo_url: str, branch: str) -> str | None:
    result = _run(("git", "ls-remote", repo_url, f"refs/heads/{branch}"), cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout.strip():
        return None
    first = result.stdout.strip().splitlines()[0].split()[0]
    return first if first else None


def _ssh(host: str, remote_command: str) -> str:
    return f"ssh {shlex.quote(host)} {shlex.quote(remote_command)}"


def _default_release_name(short_head: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"brc-runtime-governance-{short_head}-{stamp}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing git-based Tokyo deploy plan."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--repo-url", default=None, help="Git repository URL.")
    parser.add_argument("--git-ref", default=DEFAULT_GIT_REF, help="Remote branch name.")
    parser.add_argument("--target-commit", default=None, help="Commit to deploy; defaults to local HEAD.")
    parser.add_argument("--release-name", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    parser.add_argument("--venv-python", default=DEFAULT_VENV_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--previous-release", required=True)
    parser.add_argument("--expected-deployed-head", required=True)
    parser.add_argument("--expected-remote-migration-count", type=int, required=True)
    parser.add_argument("--expected-remote-latest-migration", required=True)
    parser.add_argument("--expected-latest-migration", default=DEFAULT_EXPECTED_LATEST_MIGRATION)
    return parser.parse_args(argv)


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout:
        raise GitDeployPlanError("not inside a git repository")
    return Path(result.stdout.strip())


def _git(repo_root: Path, *args: str) -> CommandResult:
    result = _run(("git", *args), cwd=repo_root)
    if result.returncode != 0:
        raise GitDeployPlanError(f"git {' '.join(args)} failed")
    return result


def _tracked_dirty(repo_root: Path) -> bool:
    status = _git(repo_root, "status", "--porcelain").stdout
    for line in status.splitlines():
        if line and not line.startswith("?? "):
            return True
    return False


def _run(command: tuple[str, ...], *, cwd: Path) -> CommandResult:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        stdout = completed.stderr.strip()
    return CommandResult(stdout=stdout, returncode=completed.returncode)


def _print_human_report(report: dict[str, Any]) -> None:
    checks = report["checks"]
    release = report["release"]
    print(f"status={report['status']}")
    print(f"release_name={release['release_name']}")
    print(f"remote_release_path={release['remote_release_path']}")
    print(f"repo_url={report['inputs']['repo_url']}")
    print(f"git_ref={report['inputs']['git_ref']}")
    print(f"target_commit={report['inputs']['target_commit']}")
    print(
        "ready_for_owner_authorized_remote_deploy="
        + str(checks["ready_for_owner_authorized_remote_deploy"]).lower()
    )
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))
    print(
        "remote_mutation_requires_confirmation_phrase="
        + checks["remote_mutation_requires_confirmation_phrase"]
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GitDeployPlanError as exc:
        print(f"git_deploy_plan_error={exc}", file=sys.stderr)
        raise SystemExit(2)
