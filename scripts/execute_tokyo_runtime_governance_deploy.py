#!/usr/bin/env python3
"""Retired archive-upload Tokyo runtime-governance deploy executor.

This command is a fail-closed tombstone. The archive/scp release-package deploy
path is disabled to avoid large release uploads and stale deployment semantics.
Use scripts/execute_tokyo_runtime_governance_git_deploy.py for Tokyo deploys.
All invocations of this legacy executor return ``blocked`` and do not run SSH,
scp, migrations, service restarts, FinalGate, Operation Layer, or exchange
writes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.plan_tokyo_runtime_governance_deploy import (
    ARCHIVE_UPLOAD_DEPLOY_BLOCKER,
    CONFIRMATION_PHRASE,
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_ENV_PATH,
    DEFAULT_EXPECTED_DEPLOYED_HEAD,
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    DEFAULT_EXPECTED_REMOTE_LATEST_MIGRATION,
    DEFAULT_EXPECTED_REMOTE_MIGRATION_COUNT,
    DEFAULT_HOST,
    DEFAULT_PREVIOUS_RELEASE,
    DEFAULT_SERVICE_NAME,
    DEFAULT_VENV_PYTHON,
    DeployPlanError,
    build_deploy_plan,
)
from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)


class DeployExecutionError(RuntimeError):
    """Raised when deployment execution cannot proceed safely."""


@dataclass(frozen=True)
class ShellResult:
    command: str
    stdout: str
    stderr: str
    returncode: int


ShellRunner = Callable[[str], ShellResult]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    plan = build_deploy_plan(
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
    report = execute_deploy_plan(
        plan,
        apply=args.apply,
        confirmation_phrase=args.confirmation_phrase,
        owner_deploy_artifact=None,
        require_confirmation_phrase=args.require_confirmation_phrase,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"dry_run_ready", "applied"} else 2


def execute_deploy_plan(
    plan: dict[str, Any],
    *,
    apply: bool,
    confirmation_phrase: str | None,
    owner_deploy_artifact: dict[str, Any] | None = None,
    require_confirmation_phrase: bool = False,
    runner: ShellRunner | None = None,
) -> dict[str, Any]:
    """Reject the retired archive-upload deploy path.

    The Tokyo deploy path is git-based only. This legacy executor remains as a
    tombstone so older commands fail closed without transferring release
    archives or running remote mutation commands.
    """

    blockers = list(plan.get("checks", {}).get("blockers") or [])
    if ARCHIVE_UPLOAD_DEPLOY_BLOCKER not in blockers:
        blockers.append(ARCHIVE_UPLOAD_DEPLOY_BLOCKER)

    return _execution_report(
        plan=plan,
        status="blocked",
        apply=apply,
        blockers=["deploy_plan_blocked", *blockers],
        command_results=[],
        confirmation_phrase_required=require_confirmation_phrase,
    )


def _execution_report(
    *,
    plan: dict[str, Any],
    status: str,
    apply: bool,
    blockers: list[str],
    command_results: list[dict[str, Any]],
    confirmation_phrase_required: bool = False,
    confirmation_phrase_matches: bool = False,
) -> dict[str, Any]:
    commands = [
        {"phase": phase.get("phase"), "command": command}
        for phase in plan.get("plan_phases", [])
        for command in phase.get("commands") or []
    ]
    return {
        "status": status,
        "scope": "tokyo_runtime_governance_controlled_deploy_execution",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "apply_requested": apply,
        "release": plan.get("release", {}),
        "checks": {
            "blockers": blockers,
            "remote_mutation_authorized_by": (
                "owner_confirmation_phrase"
                if confirmation_phrase_required
                else OWNER_STANDING_AUTHORIZATION_REFERENCE
            ),
            "remote_mutation_confirmation_phrase_required": (
                confirmation_phrase_required
            ),
            "confirmation_phrase_matches": confirmation_phrase_matches,
            "remote_mutation_requires_confirmation_phrase": plan.get("checks", {}).get(
                "remote_mutation_requires_confirmation_phrase"
            ),
            "commands_planned": len(commands),
            "commands_executed": len(command_results),
        },
        "planned_commands": commands if not apply else [],
        "command_results": command_results,
        "effects": _effects_from_command_results(
            apply=apply,
            command_results=command_results,
        ),
    }


def _effects_from_command_results(
    *,
    apply: bool,
    command_results: list[dict[str, Any]],
) -> dict[str, bool]:
    successful_commands = [
        str(result.get("command") or "")
        for result in command_results
        if result.get("returncode") == 0
    ]
    successful_phases = {
        str(result.get("phase") or "")
        for result in command_results
        if result.get("returncode") == 0
    }
    return {
        "remote_files_modified": bool(
            apply
            and (
                "2_owner_authorized_upload_and_extract" in successful_phases
                or any("ln -sfn" in command for command in successful_commands)
            )
        ),
        "database_backup_created": bool(
            apply and any("pg_dump" in command for command in successful_commands)
        ),
        "migrations_run": bool(
            apply
            and any("alembic upgrade head" in command for command in successful_commands)
        ),
        "services_restarted": bool(
            apply
            and any("systemctl start" in command for command in successful_commands)
        ),
        "execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "secrets_read_by_codex": False,
    }


def _repo_root() -> Path:
    completed = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise DeployExecutionError("not inside a git repository")
    return Path(completed.stdout.strip())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retired archive-upload deploy executor. Always returns blocked; "
            "use scripts/execute_tokyo_runtime_governance_git_deploy.py."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--archive-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    parser.add_argument("--venv-python", default=DEFAULT_VENV_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--previous-release", default=DEFAULT_PREVIOUS_RELEASE)
    parser.add_argument("--expected-deployed-head", default=DEFAULT_EXPECTED_DEPLOYED_HEAD)
    parser.add_argument(
        "--expected-remote-migration-count",
        type=int,
        default=DEFAULT_EXPECTED_REMOTE_MIGRATION_COUNT,
    )
    parser.add_argument(
        "--expected-remote-latest-migration",
        default=DEFAULT_EXPECTED_REMOTE_LATEST_MIGRATION,
    )
    parser.add_argument("--expected-latest-migration", default=DEFAULT_EXPECTED_LATEST_MIGRATION)
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Accepted for legacy CLI compatibility only; archive upload deploy "
            "remains blocked and no remote commands run."
        ),
    )
    parser.add_argument(
        "--confirmation-phrase",
        default=None,
        help=(
            "Ignored legacy phrase for the retired archive deploy path: "
            f"{CONFIRMATION_PHRASE}"
        ),
    )
    parser.add_argument(
        "--require-confirmation-phrase",
        action="store_true",
        help=(
            "Accepted for legacy CLI compatibility only; the retired executor "
            "still returns blocked."
        ),
    )
    parser.add_argument(
        "--owner-deploy-artifact-path",
        default=None,
        help=(
            "Ignored legacy archive-deploy policy artifact path; git deploy "
            "uses its own gate."
        ),
    )
    return parser.parse_args(argv)


def _print_human_report(report: dict[str, Any]) -> None:
    print(f"status={report['status']}")
    print(f"apply_requested={str(report['apply_requested']).lower()}")
    print(f"commands_planned={report['checks']['commands_planned']}")
    print(f"commands_executed={report['checks']['commands_executed']}")
    if report["checks"]["blockers"]:
        print("blockers=" + ",".join(report["checks"]["blockers"]))
    print(
        "remote_mutation_authorized_by="
        + str(report["checks"]["remote_mutation_authorized_by"])
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeployExecutionError, DeployPlanError) as exc:
        print(f"deploy_execution_error={exc}", file=sys.stderr)
        raise SystemExit(2)
