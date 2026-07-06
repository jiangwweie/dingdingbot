#!/usr/bin/env python3
"""Plan a git-based Tokyo runtime-governance deployment.

This is the Tokyo deployment plan for follow-up runtime-governance stages. It
avoids uploading a local archive: Tokyo fetches a pushed branch head from the
repository, exports that exact commit into a clean release directory, writes a
release manifest, then runs migration/restart/smoke gates without report-file
or deploy-backup side effects.

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

from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)


DEFAULT_HOST = "tokyo"
DEFAULT_DEPLOY_ROOT = "/home/ubuntu/brc-deploy"
DEFAULT_SERVICE_NAME = "brc-owner-console-backend.service"
DEFAULT_ENV_PATH = "/home/ubuntu/brc-deploy/env/live-readonly.env"
DEFAULT_VENV_PYTHON = (
    "/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python"
)
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_GIT_REF = "program/live-safe-v1"
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-07-05-090_create_runtime_retention_runs.py"
)
CONFIRMATION_PHRASE = "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME = "brc-runtime-signal-watcher.service"
DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME = "brc-runtime-signal-watcher.timer"
DEFAULT_RUNTIME_MONITOR_SERVICE_NAME = "brc-runtime-monitor.service"
DEFAULT_RUNTIME_MONITOR_TIMER_NAME = "brc-runtime-monitor.timer"
RUNTIME_SIGNAL_WATCHER_SERVICE_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service"
)
RUNTIME_SIGNAL_WATCHER_TIMER_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.timer"
)
RUNTIME_MONITOR_SERVICE_REPO_PATH = "deploy/systemd/brc-runtime-monitor.service"
RUNTIME_MONITOR_TIMER_REPO_PATH = "deploy/systemd/brc-runtime-monitor.timer"
RUNTIME_SIGNAL_WATCHER_DISPATCHER_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/90-resume-dispatcher-after-refresh.conf"
)
RUNTIME_SIGNAL_WATCHER_PRODUCT_STATE_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf"
)
RUNTIME_SIGNAL_WATCHER_ACTION_TIME_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/85-action-time-refresh-if-needed.conf"
)


class GitDeployPlanError(RuntimeError):
    """Raised when git deployment planning cannot proceed."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


@dataclass(frozen=True)
class RemoteBranchProbeResult:
    head: str | None
    status: str
    blocker: str | None
    attempts: list[dict[str, Any]]


@dataclass(frozen=True)
class CanonicalRepoUrl:
    value: str
    normalized_from: str | None = None


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

    canonical_repo_url = _canonical_git_fetch_repo_url(repo_url)
    repo_url = canonical_repo_url.value
    head = _git(repo_root, "rev-parse", "HEAD").stdout
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD").stdout
    branch = _git(repo_root, "branch", "--show-current").stdout
    target = target_commit or head
    tracked_dirty = _tracked_dirty(repo_root)
    migration_files = _migration_files(repo_root)
    target_migration_count = len(migration_files)
    local_latest_migration = migration_files[-1] if migration_files else None
    remote_migration_revision = _migration_revision(expected_remote_latest_migration)
    target_migration_revision = _migration_revision(expected_latest_migration)
    migration_gap_revision_count = (
        target_migration_count - expected_remote_migration_count
    )
    blockers: list[str] = []
    warnings: list[str] = []

    if canonical_repo_url.normalized_from:
        warnings.append("git_repo_url_normalized_to_https_for_remote_fetch")
    if tracked_dirty:
        warnings.append(
            "tracked_worktree_dirty_remote_git_export_ignores_local_changes"
        )
    if not migration_files:
        blockers.append("local_migration_files_missing")
    if local_latest_migration != expected_latest_migration:
        blockers.append("expected_latest_migration_not_local_latest")
    if remote_migration_revision is None:
        blockers.append("expected_remote_latest_migration_revision_unparseable")
    if target_migration_revision is None:
        blockers.append("expected_latest_migration_revision_unparseable")
    if migration_gap_revision_count < 0:
        blockers.append("target_migration_count_less_than_remote_baseline")
    if not repo_url.strip():
        blockers.append("git_repo_url_required")
    elif not _repo_url_uses_https(repo_url):
        blockers.append("git_repo_url_must_use_https")
    if git_ref.startswith("refs/"):
        blockers.append("git_deploy_v1_requires_branch_name_not_full_ref")
    if not git_ref.strip():
        blockers.append("git_ref_required")
    if _git(repo_root, "cat-file", "-e", f"{target}^{{commit}}").returncode != 0:
        blockers.append("target_commit_not_found_locally")

    remote_ref_head = None
    remote_ref_probe = RemoteBranchProbeResult(
        head=None,
        status="skipped",
        blocker=None,
        attempts=[],
    )
    if (
        repo_url.strip()
        and _repo_url_uses_https(repo_url)
        and git_ref.strip()
        and not git_ref.startswith("refs/")
    ):
        remote_ref_probe = _remote_branch_probe(repo_url=repo_url, branch=git_ref)
        remote_ref_head = remote_ref_probe.head
        if remote_ref_probe.blocker:
            blockers.append(remote_ref_probe.blocker)
        elif remote_ref_head != target:
            blockers.append("target_commit_not_remote_branch_head")

    final_release_name = release_name or _default_release_name(short_head)
    if not final_release_name.startswith("brc-runtime-governance-"):
        warnings.append("release_name_not_standard_runtime_governance_prefix")

    deploy_root = deploy_root.rstrip("/")
    source_root = f"{deploy_root}/source"
    source_repo_path = f"{source_root}/dingdingbot"
    releases_dir = f"{deploy_root}/releases"
    app_current = f"{deploy_root}/app/current"
    remote_release_path = f"{releases_dir}/{final_release_name}"
    remote_tmp_release_path = f"{remote_release_path}.tmp"
    previous_release_path = _remote_release_path(
        releases_dir=releases_dir,
        previous_release=previous_release,
    )
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
        deploy_root=deploy_root,
        source_root=source_root,
        source_repo_path=source_repo_path,
        app_current=app_current,
        remote_release_path=remote_release_path,
        remote_tmp_release_path=remote_tmp_release_path,
        release_manifest=release_manifest,
        service_name=service_name,
        env_path=env_path,
        venv_python=venv_python,
        api_base=api_base,
        previous_release_path=previous_release_path,
        expected_deployed_head=expected_deployed_head,
        expected_remote_migration_count=expected_remote_migration_count,
        expected_remote_latest_migration=expected_remote_latest_migration,
        expected_latest_migration=expected_latest_migration,
        target_migration_count=target_migration_count,
        remote_migration_revision=remote_migration_revision,
        target_migration_revision=target_migration_revision,
        migration_gap_revision_count=migration_gap_revision_count,
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
            "previous_release_path": previous_release_path,
            "expected_deployed_head": expected_deployed_head,
            "expected_remote_migration_count": expected_remote_migration_count,
            "expected_remote_latest_migration": expected_remote_latest_migration,
            "expected_latest_migration": expected_latest_migration,
            "target_migration_count": target_migration_count,
            "local_latest_migration": local_latest_migration,
            "remote_migration_revision": remote_migration_revision,
            "target_migration_revision": target_migration_revision,
            "migration_gap_revision_count": migration_gap_revision_count,
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
            "target_migration_count": target_migration_count,
            "latest_migration": local_latest_migration,
        },
        "checks": {
            "ready_for_owner_authorized_remote_deploy": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "remote_mutation_confirmation_phrase_required": False,
            "remote_mutation_requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "remote_ref_probe": {
                "status": remote_ref_probe.status,
                "blocker": remote_ref_probe.blocker,
                "attempts": remote_ref_probe.attempts,
            },
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
    deploy_root: str,
    source_root: str,
    source_repo_path: str,
    app_current: str,
    remote_release_path: str,
    remote_tmp_release_path: str,
    release_manifest: str,
    service_name: str,
    env_path: str,
    venv_python: str,
    api_base: str,
    previous_release_path: str,
    expected_deployed_head: str,
    expected_remote_migration_count: int,
    expected_remote_latest_migration: str,
    expected_latest_migration: str,
    target_migration_count: int,
    remote_migration_revision: str | None,
    target_migration_revision: str | None,
    migration_gap_revision_count: int,
    manifest_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    q = shlex.quote
    local_python = "/opt/homebrew/bin/python3"
    manifest_json = json.dumps(manifest_payload, indent=2, sort_keys=True)
    health_url = api_base.rstrip("/") + "/api/health"
    health_wait_command = (
        f"set -eu; HEALTH_URL={q(health_url)}; "
        "HEALTH_READY=0; "
        "for attempt in $(seq 1 30); do "
        'if curl -fsS "$HEALTH_URL" 2>/dev/null; then '
        "HEALTH_READY=1; break; "
        "fi; "
        "sleep 1; "
        "done; "
        'test "$HEALTH_READY" = 1 || curl -fsS "$HEALTH_URL"'
    )
    base_revision = remote_migration_revision or "UNKNOWN_REMOTE_REVISION"
    head_revision = target_migration_revision or "UNKNOWN_TARGET_REVISION"
    expected_gap_count = max(migration_gap_revision_count, 0)
    remote_fetch_ref = f"refs/heads/{git_ref}:refs/remotes/origin/{git_ref}"
    remote_ref_probe_command = (
        "set -eu; "
        f"REMOTE_HEAD=$(timeout 45 git ls-remote {q(repo_url)} "
        f"{q('refs/heads/' + git_ref)} | awk '{{print $1; exit}}'); "
        'test -n "$REMOTE_HEAD"; '
        f'test "$REMOTE_HEAD" = {q(target_commit)}'
    )
    remote_export_command = (
        f"set -eu; mkdir -p {q(source_root)}; "
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
        f"test $(readlink -f {q(app_current)}) = {q(previous_release_path)}"
    )
    quiesce_and_migrate_command = (
        f"set -eu; sudo -n systemctl stop {q(service_name)}; "
        f"cd {q(remote_release_path)}; set -a; . {q(env_path)}; set +a; "
        f"test ! -f requirements.txt || {q(venv_python)} -m pip install "
        "--disable-pip-version-check -r requirements.txt; "
        f"PYTHONPATH=$PWD {q(venv_python)} -m compileall -q src; "
        f"PYTHONPATH=$PWD {q(venv_python)} -m alembic heads; "
        f"PYTHONPATH=$PWD {q(venv_python)} -m alembic upgrade head; "
        f"PYTHONPATH=$PWD {q(venv_python)} "
        "scripts/seed_runtime_control_state_foundation.py --apply --json; "
        f"PYTHONPATH=$PWD {q(venv_python)} "
        "scripts/validate_runtime_control_state_repository.py --json"
    )
    switch_start_and_smoke_command = (
        f"set -eu; ln -sfn {q(remote_release_path)} {q(app_current)}; "
        f"sudo -n systemctl start {q(service_name)}; "
        f"sudo -n systemctl is-active {q(service_name)}; "
        f"{health_wait_command}; "
        f"{runtime_signal_watcher_dispatcher_dropin_install_command(remote_release_path=remote_release_path, deploy_root=deploy_root)}; "
        f"test -f {q(release_manifest)}; "
        f"test $(readlink -f {q(app_current)}) = {q(remote_release_path)}"
    )

    return [
        {
            "phase": "0_local_preflight",
            "remote_mutation": False,
            "commands": [
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/prepare_tokyo_runtime_governance_release.py --json "
                f"--deployed-head {q(expected_deployed_head)} "
                f"--expected-min-migrations {target_migration_count} "
                f"--expected-latest-migration {q(expected_latest_migration)} "
                "--allow-tracked-dirty-for-remote-git-export",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/audit_tokyo_runtime_governance_migration_gap.py --json "
                f"--base-revision {q(base_revision)} "
                f"--head-revision {q(head_revision)} "
                f"--expected-revision-count {expected_gap_count}",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json",
            ],
            "stop_if": [
                "local release readiness is not true",
                "target commit is not the pushed remote branch head",
                "migration gap audit does not pass",
                "shadow-planning rehearsal does not pass",
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
                _ssh(host, remote_ref_probe_command),
            ],
            "stop_if": [
                "remote current head differs from expected baseline",
                "remote migration state differs from expected baseline",
                "Tokyo cannot reach the GitHub branch head",
                "Tokyo branch head differs from the target commit",
                "health live_ready is true",
            ],
        },
        {
            "phase": "2_owner_authorized_git_fetch_and_export",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
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
            "phase": "3_quiesce_and_migrate",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [_ssh(host, quiesce_and_migrate_command)],
            "stop_if": [
                "service cannot be stopped with non-interactive sudo",
                "alembic upgrade fails",
            ],
        },
        {
            "phase": "4_switch_start_and_smoke",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [
                _ssh(host, switch_start_and_smoke_command),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/probe_tokyo_runtime_governance_readonly.py --json "
                    f"--expected-current-head {q(target_commit)} "
                    f"--expected-migration-count {target_migration_count} "
                    f"--expected-latest-migration {q(expected_latest_migration)}"
                ),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/verify_tokyo_runtime_governance_postdeploy.py --json "
                    f"--expected-current-head {q(target_commit)} "
                    f"--expected-migration-count {target_migration_count} "
                    f"--expected-latest-migration {q(expected_latest_migration)}"
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


def _canonical_git_fetch_repo_url(repo_url: str) -> CanonicalRepoUrl:
    stripped = repo_url.strip()
    if stripped.startswith("git@github.com:"):
        path = stripped.removeprefix("git@github.com:")
        return CanonicalRepoUrl(
            value=f"https://github.com/{path}",
            normalized_from=stripped,
        )
    if stripped.startswith("ssh://git@github.com/"):
        path = stripped.removeprefix("ssh://git@github.com/")
        return CanonicalRepoUrl(
            value=f"https://github.com/{path}",
            normalized_from=stripped,
        )
    return CanonicalRepoUrl(value=stripped)


def _repo_url_uses_https(repo_url: str) -> bool:
    return repo_url.strip().startswith("https://")


def _remote_branch_probe(*, repo_url: str, branch: str) -> RemoteBranchProbeResult:
    attempts: list[dict[str, Any]] = []
    ref = f"refs/heads/{branch}"
    commands = [
        ("default", ("git", "ls-remote", repo_url, ref)),
        ("retry", ("git", "ls-remote", repo_url, ref)),
        (
            "http1",
            ("git", "-c", "http.version=HTTP/1.1", "ls-remote", repo_url, ref),
        ),
    ]
    for transport, command in commands:
        result = _run(command, cwd=Path.cwd())
        attempts.append(
            {
                "transport": transport,
                "returncode": result.returncode,
                "stdout_tail": _text_tail(result.stdout),
            }
        )
        if result.returncode != 0:
            continue
        head = _parse_ls_remote_head(result.stdout)
        if head:
            return RemoteBranchProbeResult(
                head=head,
                status="head_resolved",
                blocker=None,
                attempts=attempts,
            )
        return RemoteBranchProbeResult(
            head=None,
            status="branch_missing",
            blocker="target_git_ref_missing_on_remote",
            attempts=attempts,
        )

    return RemoteBranchProbeResult(
        head=None,
        status="probe_failed",
        blocker=_remote_probe_failure_blocker(attempts),
        attempts=attempts,
    )


def _remote_branch_head(*, repo_url: str, branch: str) -> str | None:
    return _remote_branch_probe(repo_url=repo_url, branch=branch).head


def _parse_ls_remote_head(text: str) -> str | None:
    if not text.strip():
        return None
    first = text.strip().splitlines()[0].split()[0]
    return first if first else None


def _remote_probe_failure_blocker(attempts: list[dict[str, Any]]) -> str:
    combined = "\n".join(
        str(attempt.get("stdout_tail", "")) for attempt in attempts
    ).lower()
    timeout_markers = (
        "operation timed out",
        "timed out",
        "timeout",
    )
    if any(marker in combined for marker in timeout_markers):
        return "git_remote_probe_timed_out"
    network_markers = (
        "http2 framing",
        "failed to connect",
        "couldn't connect",
        "could not resolve host",
        "connection reset",
        "network is unreachable",
        "unable to access",
        "the requested url returned error",
        "tls",
        "ssl",
    )
    if any(marker in combined for marker in network_markers):
        return "git_remote_probe_network_failed"
    return "git_remote_probe_failed"


def _text_tail(text: str, *, max_chars: int = 500) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[-max_chars:]


def runtime_signal_watcher_dispatcher_dropin_install_command(
    *,
    remote_release_path: str,
    deploy_root: str = DEFAULT_DEPLOY_ROOT,
) -> str:
    q = shlex.quote
    service_dir = "/etc/systemd/system"
    service_path = f"{service_dir}/{DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME}"
    timer_path = f"{service_dir}/{DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME}"
    runtime_monitor_service_path = (
        f"{service_dir}/{DEFAULT_RUNTIME_MONITOR_SERVICE_NAME}"
    )
    runtime_monitor_timer_path = f"{service_dir}/{DEFAULT_RUNTIME_MONITOR_TIMER_NAME}"
    stale_runtime_db_retention_service_path = (
        f"{service_dir}/brc-runtime-db-retention.service"
    )
    stale_runtime_db_retention_timer_path = (
        f"{service_dir}/brc-runtime-db-retention.timer"
    )
    service_dropin_dir = (
        f"/etc/systemd/system/{DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME}.d"
    )
    service_dropin_path = f"{service_dropin_dir}/90-resume-dispatcher-after-refresh.conf"
    dry_run_audit_dropin_path = f"{service_dropin_dir}/60-dry-run-audit-chain.conf"
    goal_status_dropin_path = f"{service_dropin_dir}/70-goal-status.conf"
    product_state_dropin_path = f"{service_dropin_dir}/80-product-state-refresh.conf"
    action_time_dropin_path = f"{service_dropin_dir}/85-action-time-refresh-if-needed.conf"
    stale_scope_dropin_path = (
        f"{service_dropin_dir}/30-strategygroup-runtime-pilot-scope.conf"
    )
    stale_operation_layer_flags_dropin_path = (
        f"{service_dropin_dir}/30-operation-layer-followup-flags.conf"
    )
    stale_product_state_refresh_dropin_path = (
        f"{service_dropin_dir}/50-product-state-refresh.conf"
    )
    stale_resume_dispatcher_dropin_path = (
        f"{service_dropin_dir}/40-resume-dispatcher.conf"
    )
    release_service_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_SERVICE_REPO_PATH}"
    )
    release_timer_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_TIMER_REPO_PATH}"
    )
    release_runtime_monitor_service_path = (
        f"{remote_release_path.rstrip('/')}/{RUNTIME_MONITOR_SERVICE_REPO_PATH}"
    )
    release_runtime_monitor_timer_path = (
        f"{remote_release_path.rstrip('/')}/{RUNTIME_MONITOR_TIMER_REPO_PATH}"
    )
    release_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_DISPATCHER_DROPIN_REPO_PATH}"
    )
    release_product_state_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_PRODUCT_STATE_DROPIN_REPO_PATH}"
    )
    release_action_time_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_ACTION_TIME_DROPIN_REPO_PATH}"
    )
    return (
        f"set -eu; "
        f"test -f {q(release_service_path)}; "
        f"test -f {q(release_timer_path)}; "
        f"test -f {q(release_runtime_monitor_service_path)}; "
        f"test -f {q(release_runtime_monitor_timer_path)}; "
        f"test -f {q(release_dropin_path)}; "
        f"test -f {q(release_product_state_dropin_path)}; "
        f"test -f {q(release_action_time_dropin_path)}; "
        f"sudo -n cp {q(release_service_path)} {q(service_path)}; "
        f"sudo -n cp {q(release_timer_path)} {q(timer_path)}; "
        f"sudo -n cp {q(release_runtime_monitor_service_path)} {q(runtime_monitor_service_path)}; "
        f"sudo -n cp {q(release_runtime_monitor_timer_path)} {q(runtime_monitor_timer_path)}; "
        f"sudo -n chmod 0644 {q(service_path)} {q(timer_path)} {q(runtime_monitor_service_path)} {q(runtime_monitor_timer_path)}; "
        f"sudo -n mkdir -p {q(service_dropin_dir)}; "
        f"sudo -n cp {q(release_dropin_path)} {q(service_dropin_path)}; "
        f"sudo -n cp {q(release_product_state_dropin_path)} {q(product_state_dropin_path)}; "
        f"sudo -n cp {q(release_action_time_dropin_path)} {q(action_time_dropin_path)}; "
        f"sudo -n chmod 0644 {q(service_dropin_path)} {q(product_state_dropin_path)} {q(action_time_dropin_path)}; "
        f"sudo -n rm -f {q(dry_run_audit_dropin_path)}; "
        f"sudo -n rm -f {q(goal_status_dropin_path)}; "
        f"sudo -n rm -f {q(stale_scope_dropin_path)}; "
        f"sudo -n rm -f {q(stale_operation_layer_flags_dropin_path)}; "
        f"sudo -n rm -f {q(stale_product_state_refresh_dropin_path)}; "
        f"sudo -n rm -f {q(stale_resume_dispatcher_dropin_path)}; "
        "sudo -n systemctl disable --now brc-runtime-db-retention.timer 2>/dev/null || true; "
        f"sudo -n rm -f {q(stale_runtime_db_retention_service_path)}; "
        f"sudo -n rm -f {q(stale_runtime_db_retention_timer_path)}; "
        "sudo -n systemctl daemon-reload; "
        f"sudo -n systemctl enable {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}; "
        f"sudo -n systemctl enable --now {q(DEFAULT_RUNTIME_MONITOR_TIMER_NAME)}; "
        f"sudo -n systemctl restart {q(DEFAULT_RUNTIME_MONITOR_TIMER_NAME)}; "
        f"sudo -n systemctl start {q(DEFAULT_RUNTIME_MONITOR_SERVICE_NAME)}; "
        f"sudo -n systemctl is-enabled {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}; "
        f"sudo -n systemctl is-enabled {q(DEFAULT_RUNTIME_MONITOR_TIMER_NAME)}; "
        f"sudo -n systemctl is-active {q(DEFAULT_RUNTIME_MONITOR_TIMER_NAME)}"
    )


def _ssh(host: str, remote_command: str) -> str:
    return f"ssh {shlex.quote(host)} {shlex.quote(remote_command)}"


def _default_release_name(short_head: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"brc-runtime-governance-{short_head}-{stamp}"


def _remote_release_path(*, releases_dir: str, previous_release: str) -> str:
    normalized = previous_release.strip().rstrip("/")
    if normalized.startswith("/"):
        return normalized
    if "/" in normalized:
        return normalized
    return f"{releases_dir.rstrip('/')}/{normalized}"


def _migration_files(repo_root: Path) -> list[str]:
    versions_dir = repo_root / "migrations" / "versions"
    if not versions_dir.is_dir():
        return []
    return sorted(path.name for path in versions_dir.glob("*.py"))


def _migration_revision(filename: str) -> str | None:
    prefix = Path(filename).name.split("_", 1)[0]
    revision = prefix.rsplit("-", 1)[-1]
    return revision if revision.isdigit() else None


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
