#!/usr/bin/env python3
"""Plan a controlled Tokyo runtime-governance deployment.

Default behavior is dry-run planning only. The script reads local artifact and
manifest metadata, then prints a command plan. It does not SSH, scp, deploy,
write remote files, connect to a database, run migrations, restart services,
read secrets, create execution records, create orders, call OrderLifecycle, or
call exchange APIs.
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

from src.domain.standing_authorization import (  # noqa: E402
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
DEFAULT_PREVIOUS_RELEASE = (
    "/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ae9b209e-20260610T061250Z"
)
DEFAULT_EXPECTED_DEPLOYED_HEAD = "ae9b209e33cd287273491f2e93dfdff3b6a814fd"
DEFAULT_EXPECTED_REMOTE_MIGRATION_COUNT = 64
DEFAULT_EXPECTED_REMOTE_LATEST_MIGRATION = (
    "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
)
DEFAULT_EXPECTED_LATEST_MIGRATION = (
    "2026-06-10-070_add_execution_intent_local_orders_registered_status.py"
)
DEFAULT_PG_CONTAINER_NAME = "brc_prelive_pg_20260601"
CONFIRMATION_PHRASE = "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME = "brc-runtime-signal-watcher.service"
DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME = "brc-runtime-signal-watcher.timer"
RUNTIME_SIGNAL_WATCHER_SERVICE_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service"
)
RUNTIME_SIGNAL_WATCHER_TIMER_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.timer"
)
RUNTIME_SIGNAL_WATCHER_DISPATCHER_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/40-resume-dispatcher.conf"
)
RUNTIME_SIGNAL_WATCHER_DRY_RUN_AUDIT_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/60-dry-run-audit-chain.conf"
)
RUNTIME_SIGNAL_WATCHER_GOAL_STATUS_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/70-goal-status.conf"
)
RUNTIME_SIGNAL_WATCHER_PRODUCT_STATE_DROPIN_REPO_PATH = (
    "deploy/systemd/brc-runtime-signal-watcher.service.d/80-product-state-refresh.conf"
)


class DeployPlanError(RuntimeError):
    """Raised when deployment planning cannot proceed."""


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    report = build_deploy_plan(
        repo_root=repo_root,
        archive_path=Path(args.archive_path) if args.archive_path else None,
        manifest_path=Path(args.manifest_path) if args.manifest_path else None,
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


def build_deploy_plan(
    *,
    repo_root: Path,
    archive_path: Path | None,
    manifest_path: Path | None,
    release_name: str | None,
    host: str,
    deploy_root: str,
    service_name: str,
    env_path: str,
    venv_python: str,
    api_base: str,
    previous_release: str,
    expected_deployed_head: str,
    expected_remote_migration_count: int = DEFAULT_EXPECTED_REMOTE_MIGRATION_COUNT,
    expected_remote_latest_migration: str = DEFAULT_EXPECTED_REMOTE_LATEST_MIGRATION,
    expected_latest_migration: str = DEFAULT_EXPECTED_LATEST_MIGRATION,
) -> dict[str, Any]:
    """Build a non-executing deployment command plan."""

    head = _git(repo_root, "rev-parse", "HEAD").stdout
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD").stdout
    tracked_dirty = _tracked_dirty(repo_root)
    target_migration_count = _local_migration_count(repo_root)
    local_latest_migration = _local_latest_migration(repo_root)
    remote_migration_revision = _migration_revision(expected_remote_latest_migration)
    target_migration_revision = _migration_revision(expected_latest_migration)
    migration_gap_revision_count = (
        target_migration_count - expected_remote_migration_count
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if tracked_dirty:
        blockers.append("tracked_worktree_dirty")
    if local_latest_migration != expected_latest_migration:
        blockers.append("expected_latest_migration_not_local_latest")
    if remote_migration_revision is None:
        blockers.append("expected_remote_latest_migration_revision_unparseable")
    if target_migration_revision is None:
        blockers.append("expected_latest_migration_revision_unparseable")
    if migration_gap_revision_count < 0:
        blockers.append("expected_remote_migration_count_ahead_of_target")

    manifest: dict[str, Any] | None = None
    if archive_path is None:
        blockers.append("archive_path_required")
    elif not archive_path.exists():
        blockers.append("archive_path_missing")
    if manifest_path is None:
        blockers.append("manifest_path_required")
    elif not manifest_path.exists():
        blockers.append("manifest_path_missing")
    else:
        manifest = _load_manifest(manifest_path)
        manifest_head = _manifest_head(manifest)
        if manifest_head and manifest_head != head:
            blockers.append("manifest_head_mismatch_current_head")
        if not manifest_head:
            blockers.append("manifest_head_missing")

    final_release_name = release_name or _default_release_name(short_head)
    if not final_release_name.startswith("brc-runtime-governance-"):
        warnings.append("release_name_not_standard_runtime_governance_prefix")

    deploy_root = deploy_root.rstrip("/")
    incoming_dir = f"{deploy_root}/incoming"
    releases_dir = f"{deploy_root}/releases"
    reports_dir = f"{deploy_root}/reports/{final_release_name}"
    backups_dir = f"{deploy_root}/backups"
    app_current = f"{deploy_root}/app/current"
    remote_release_path = f"{releases_dir}/{final_release_name}"
    remote_tmp_release_path = f"{remote_release_path}.tmp"
    remote_archive_path = (
        f"{incoming_dir}/{archive_path.name}" if archive_path is not None else None
    )
    remote_manifest_path = (
        f"{incoming_dir}/{manifest_path.name}" if manifest_path is not None else None
    )
    backup_path = f"{backups_dir}/{final_release_name}.pgdump"

    plan_phases = _plan_phases(
        host=host,
        repo_root=repo_root,
        archive_path=archive_path,
        manifest_path=manifest_path,
        deploy_root=deploy_root,
        incoming_dir=incoming_dir,
        reports_dir=reports_dir,
        backups_dir=backups_dir,
        app_current=app_current,
        remote_release_path=remote_release_path,
        remote_tmp_release_path=remote_tmp_release_path,
        remote_archive_path=remote_archive_path,
        remote_manifest_path=remote_manifest_path,
        backup_path=backup_path,
        service_name=service_name,
        env_path=env_path,
        venv_python=venv_python,
        api_base=api_base,
        previous_release=previous_release,
        expected_deployed_head=expected_deployed_head,
        expected_remote_migration_count=expected_remote_migration_count,
        expected_remote_latest_migration=expected_remote_latest_migration,
        head=head,
        expected_latest_migration=expected_latest_migration,
        target_migration_count=target_migration_count,
        remote_migration_revision=remote_migration_revision,
        target_migration_revision=target_migration_revision,
        migration_gap_revision_count=migration_gap_revision_count,
    )

    return {
        "status": (
            "ready_for_owner_authorized_remote_deploy_plan"
            if not blockers
            else "blocked"
        ),
        "scope": "tokyo_runtime_governance_controlled_deploy_plan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "archive_path": str(archive_path) if archive_path else None,
            "manifest_path": str(manifest_path) if manifest_path else None,
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
            "target_migration_count": target_migration_count,
            "remote_migration_revision": remote_migration_revision,
            "target_migration_revision": target_migration_revision,
            "migration_gap_revision_count": migration_gap_revision_count,
        },
        "release": {
            "head": head,
            "short_head": short_head,
            "manifest_head": _manifest_head(manifest) if manifest else None,
            "release_name": final_release_name,
            "remote_release_path": remote_release_path,
            "remote_tmp_release_path": remote_tmp_release_path,
            "remote_archive_path": remote_archive_path,
            "remote_manifest_path": remote_manifest_path,
            "remote_release_manifest_path": (
                f"{remote_release_path}/.brc-release-manifest.json"
            ),
            "backup_path": backup_path,
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
    archive_path: Path | None,
    manifest_path: Path | None,
    deploy_root: str,
    incoming_dir: str,
    reports_dir: str,
    backups_dir: str,
    app_current: str,
    remote_release_path: str,
    remote_tmp_release_path: str,
    remote_archive_path: str | None,
    remote_manifest_path: str | None,
    backup_path: str,
    service_name: str,
    env_path: str,
    venv_python: str,
    api_base: str,
    previous_release: str,
    expected_deployed_head: str,
    expected_remote_migration_count: int,
    expected_remote_latest_migration: str,
    head: str,
    expected_latest_migration: str,
    target_migration_count: int,
    remote_migration_revision: str | None,
    target_migration_revision: str | None,
    migration_gap_revision_count: int,
) -> list[dict[str, Any]]:
    q = shlex.quote
    local_python = "/opt/homebrew/bin/python3"
    archive = str(archive_path) if archive_path else "<archive_path_required>"
    manifest = str(manifest_path) if manifest_path else "<manifest_path_required>"
    remote_archive = remote_archive_path or f"{incoming_dir}/<archive>"
    remote_manifest = remote_manifest_path or f"{incoming_dir}/<manifest>"
    release_manifest = f"{remote_release_path}/.brc-release-manifest.json"
    health_url = api_base.rstrip("/") + "/api/health"
    health_wait_command = (
        f"set -eu; HEALTH_URL={q(health_url)}; "
        "for attempt in $(seq 1 30); do "
        'curl -fsS "$HEALTH_URL" 2>/dev/null && exit 0; '
        "sleep 1; "
        "done; "
        'curl -fsS "$HEALTH_URL"'
    )
    base_revision = remote_migration_revision or "UNKNOWN_REMOTE_REVISION"
    head_revision = target_migration_revision or "UNKNOWN_TARGET_REVISION"
    expected_gap_count = max(migration_gap_revision_count, 0)

    return [
        {
            "phase": "0_local_preflight",
            "remote_mutation": False,
            "commands": [
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/prepare_tokyo_runtime_governance_release.py --json "
                f"--deployed-head {q(expected_deployed_head)} "
                f"--expected-min-migrations {target_migration_count} "
                f"--expected-latest-migration {q(expected_latest_migration)}",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/audit_tokyo_runtime_governance_migration_gap.py --json "
                f"--base-revision {q(base_revision)} "
                f"--head-revision {q(head_revision)} "
                f"--expected-revision-count {expected_gap_count}",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json",
                f"cd {q(str(repo_root))} && {local_python} "
                "scripts/verify_runtime_submit_rehearsal_pre_live_packet.py --json "
                "--skip-current-head-deployed-check",
            ],
            "stop_if": [
                "ready_for_packaging is not true",
                "ready_for_controlled_migration_preflight is not true",
                "scheduled-observation shadow-planning rehearsal does not pass",
                "runtime submit pre-live technical rehearsal does not pass",
                "runtime submit pre-live registration draft chain does not pass",
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
                "ready_for_controlled_deploy_preflight is not true",
                "remote current head differs from expected baseline",
                "health live_ready is true",
            ],
        },
        {
            "phase": "2_owner_authorized_upload_and_extract",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [
                _ssh(host, f"set -eu; mkdir -p {q(incoming_dir)} {q(reports_dir)} {q(backups_dir)}"),
                f"scp {q(archive)} {q(host + ':' + remote_archive)}",
                f"scp {q(manifest)} {q(host + ':' + remote_manifest)}",
                _ssh(
                    host,
                    (
                        f"set -eu; test ! -e {q(remote_release_path)}; "
                        f"rm -rf {q(remote_tmp_release_path)}; "
                        f"mkdir -p {q(remote_tmp_release_path)}; "
                        f"tar -xzf {q(remote_archive)} -C {q(remote_tmp_release_path)} "
                        "--strip-components=1; "
                        f"cp {q(remote_manifest)} {q(remote_tmp_release_path)}/.brc-release-manifest.json; "
                        f"mv {q(remote_tmp_release_path)} {q(remote_release_path)}"
                    ),
                ),
                _ssh(
                    host,
                    (
                        f"set -eu; test $(readlink -f {q(app_current)}) = "
                        f"{q(previous_release)}"
                    ),
                ),
            ],
            "stop_if": [
                "release path already exists",
                "archive extraction fails",
                "app/current no longer points to the expected previous release",
            ],
        },
        {
            "phase": "3_quiesce_backup_and_migrate",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
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
            "rollback_hint": (
                "If migration fails after service stop, do not blindly downgrade. "
                "Restart the previous release only after inspecting migration state."
            ),
        },
        {
            "phase": "4_switch_start_and_smoke",
            "remote_mutation": True,
            "remote_mutation_authorization": (
                OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "requires_confirmation_phrase": CONFIRMATION_PHRASE,
            "commands": [
                _ssh(host, f"set -eu; ln -sfn {q(remote_release_path)} {q(app_current)}"),
                _ssh(host, f"sudo -n systemctl start {q(service_name)}"),
                _ssh(host, f"sudo -n systemctl is-active {q(service_name)}"),
                _ssh(host, health_wait_command),
                _ssh(
                    host,
                    runtime_signal_watcher_dispatcher_dropin_install_command(
                        remote_release_path=remote_release_path
                    ),
                ),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/probe_tokyo_runtime_governance_readonly.py --json "
                    f"--expected-current-head {q(head)} "
                    f"--expected-migration-count {target_migration_count} "
                    f"--expected-latest-migration {q(expected_latest_migration)}"
                ),
                (
                    f"cd {q(str(repo_root))} && {local_python} "
                    "scripts/verify_tokyo_runtime_governance_postdeploy.py --json "
                    f"--expected-current-head {q(head)} "
                    f"--expected-migration-count {target_migration_count} "
                    f"--expected-latest-migration {q(expected_latest_migration)}"
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


def runtime_signal_watcher_dispatcher_dropin_install_command(
    *,
    remote_release_path: str,
) -> str:
    q = shlex.quote
    service_dir = "/etc/systemd/system"
    service_path = f"{service_dir}/{DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME}"
    timer_path = f"{service_dir}/{DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME}"
    service_dropin_dir = (
        f"/etc/systemd/system/{DEFAULT_RUNTIME_SIGNAL_WATCHER_SERVICE_NAME}.d"
    )
    service_dropin_path = f"{service_dropin_dir}/40-resume-dispatcher.conf"
    dry_run_audit_dropin_path = f"{service_dropin_dir}/60-dry-run-audit-chain.conf"
    goal_status_dropin_path = f"{service_dropin_dir}/70-goal-status.conf"
    product_state_dropin_path = f"{service_dropin_dir}/80-product-state-refresh.conf"
    stale_scope_dropin_path = (
        f"{service_dropin_dir}/30-strategygroup-runtime-pilot-scope.conf"
    )
    stale_operation_layer_flags_dropin_path = (
        f"{service_dropin_dir}/30-operation-layer-followup-flags.conf"
    )
    stale_product_state_refresh_dropin_path = (
        f"{service_dropin_dir}/50-product-state-refresh.conf"
    )
    release_service_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_SERVICE_REPO_PATH}"
    )
    release_timer_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_TIMER_REPO_PATH}"
    )
    release_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_DISPATCHER_DROPIN_REPO_PATH}"
    )
    release_dry_run_audit_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_DRY_RUN_AUDIT_DROPIN_REPO_PATH}"
    )
    release_goal_status_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_GOAL_STATUS_DROPIN_REPO_PATH}"
    )
    release_product_state_dropin_path = (
        f"{remote_release_path.rstrip('/')}/"
        f"{RUNTIME_SIGNAL_WATCHER_PRODUCT_STATE_DROPIN_REPO_PATH}"
    )
    return (
        f"set -eu; "
        f"test -f {q(release_service_path)}; "
        f"test -f {q(release_timer_path)}; "
        f"test -f {q(release_dropin_path)}; "
        f"test -f {q(release_dry_run_audit_dropin_path)}; "
        f"test -f {q(release_goal_status_dropin_path)}; "
        f"test -f {q(release_product_state_dropin_path)}; "
        f"sudo -n cp {q(release_service_path)} {q(service_path)}; "
        f"sudo -n cp {q(release_timer_path)} {q(timer_path)}; "
        f"sudo -n chmod 0644 {q(service_path)} {q(timer_path)}; "
        f"sudo -n mkdir -p {q(service_dropin_dir)}; "
        f"sudo -n cp {q(release_dropin_path)} {q(service_dropin_path)}; "
        f"sudo -n cp {q(release_dry_run_audit_dropin_path)} {q(dry_run_audit_dropin_path)}; "
        f"sudo -n cp {q(release_goal_status_dropin_path)} {q(goal_status_dropin_path)}; "
        f"sudo -n cp {q(release_product_state_dropin_path)} {q(product_state_dropin_path)}; "
        f"sudo -n chmod 0644 {q(service_dropin_path)} {q(dry_run_audit_dropin_path)} {q(goal_status_dropin_path)} {q(product_state_dropin_path)}; "
        f"sudo -n rm -f {q(stale_scope_dropin_path)}; "
        f"sudo -n rm -f {q(stale_operation_layer_flags_dropin_path)}; "
        f"sudo -n rm -f {q(stale_product_state_refresh_dropin_path)}; "
        "sudo -n systemctl daemon-reload; "
        f"sudo -n systemctl enable --now {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}; "
        f"sudo -n systemctl restart {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}; "
        f"sudo -n systemctl is-enabled {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}; "
        f"sudo -n systemctl is-active {q(DEFAULT_RUNTIME_SIGNAL_WATCHER_TIMER_NAME)}"
    )


def _ssh(host: str, remote_command: str) -> str:
    return f"ssh {shlex.quote(host)} {shlex.quote(remote_command)}"


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeployPlanError(f"cannot read manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DeployPlanError(f"manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise DeployPlanError("manifest JSON root must be an object")
    return payload


def _manifest_head(manifest: dict[str, Any] | None) -> str | None:
    if not manifest:
        return None
    local_git = manifest.get("local_git")
    if not isinstance(local_git, dict):
        return None
    head = local_git.get("head")
    return str(head).strip() if head else None


def _default_release_name(short_head: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"brc-runtime-governance-{short_head}-{stamp}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing Tokyo runtime-governance deploy plan."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--archive-path", help="Local git-archive release artifact.")
    parser.add_argument("--manifest-path", help="Local release-readiness manifest.")
    parser.add_argument("--release-name", help="Remote release directory name.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host alias.")
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    parser.add_argument("--venv-python", default=DEFAULT_VENV_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--previous-release", default=DEFAULT_PREVIOUS_RELEASE)
    parser.add_argument(
        "--expected-deployed-head",
        default=DEFAULT_EXPECTED_DEPLOYED_HEAD,
    )
    parser.add_argument(
        "--expected-remote-migration-count",
        type=int,
        default=DEFAULT_EXPECTED_REMOTE_MIGRATION_COUNT,
    )
    parser.add_argument(
        "--expected-remote-latest-migration",
        default=DEFAULT_EXPECTED_REMOTE_LATEST_MIGRATION,
    )
    parser.add_argument(
        "--expected-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
    )
    return parser.parse_args(argv)


def _repo_root() -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd())
    if result.returncode != 0 or not result.stdout:
        raise DeployPlanError("not inside a git repository")
    return Path(result.stdout.strip())


def _git(repo_root: Path, *args: str) -> CommandResult:
    result = _run(("git", *args), cwd=repo_root)
    if result.returncode != 0:
        raise DeployPlanError(f"git {' '.join(args)} failed")
    return result


def _tracked_dirty(repo_root: Path) -> bool:
    status = _git(repo_root, "status", "--porcelain").stdout
    for line in status.splitlines():
        if line and not line.startswith("?? "):
            return True
    return False


def _local_migration_files(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "migrations" / "versions").glob("*.py"))


def _local_migration_count(repo_root: Path) -> int:
    return len(_local_migration_files(repo_root))


def _local_latest_migration(repo_root: Path) -> str | None:
    files = _local_migration_files(repo_root)
    return files[-1].name if files else None


def _migration_revision(filename: str) -> str | None:
    prefix = Path(str(filename)).name.split("_", 1)[0]
    revision = prefix.rsplit("-", 1)[-1]
    return revision if revision.isdigit() else None


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
    except DeployPlanError as exc:
        print(f"deploy_plan_error={exc}", file=sys.stderr)
        raise SystemExit(2)
