#!/usr/bin/env python3
"""Standing-authorization Tokyo runtime-governance deployment executor.

Default behavior is dry-run only: build the deployment plan and report the
commands that would run. Remote mutation requires `--apply`; during the current
development-stage pilot it uses the Owner standing authorization unless
`--require-confirmation-phrase` is explicitly set. When applied, this script can
run SSH/scp, transfer release artifacts, stop/start the backend service, create
a PG backup, run Alembic migrations, repoint the release symlink, and run
read-only smoke checks. It does not create execution records, create orders,
call OrderLifecycle, or call exchange APIs.
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
    owner_deploy_artifact = (
        _load_owner_deploy_artifact(Path(args.owner_deploy_artifact_path))
        if args.owner_deploy_artifact_path
        else None
    )
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
        owner_deploy_artifact=owner_deploy_artifact,
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
    """Execute or dry-run a generated deploy plan."""

    blockers = list(plan.get("checks", {}).get("blockers") or [])
    if ARCHIVE_UPLOAD_DEPLOY_BLOCKER not in blockers:
        blockers.append(ARCHIVE_UPLOAD_DEPLOY_BLOCKER)
    if blockers:
        return _execution_report(
            plan=plan,
            status="blocked",
            apply=apply,
            blockers=["deploy_plan_blocked", *blockers],
            command_results=[],
        )

    if not apply:
        return _execution_report(
            plan=plan,
            status="dry_run_ready",
            apply=False,
            blockers=[],
            command_results=[],
        )

    required_phrase = plan.get("checks", {}).get(
        "remote_mutation_requires_confirmation_phrase"
    )
    confirmation_phrase_matches = (
        confirmation_phrase == required_phrase
        and required_phrase == CONFIRMATION_PHRASE
    )
    if require_confirmation_phrase and not confirmation_phrase_matches:
        return _execution_report(
            plan=plan,
            status="blocked",
            apply=True,
            blockers=["owner_confirmation_phrase_missing_or_mismatch"],
            command_results=[],
            confirmation_phrase_required=True,
            confirmation_phrase_matches=confirmation_phrase_matches,
        )

    artifact_blockers = _owner_deploy_artifact_blockers(
        plan,
        owner_deploy_artifact,
        require_confirmation_phrase=require_confirmation_phrase,
    )
    if artifact_blockers:
        return _execution_report(
            plan=plan,
            status="blocked",
            apply=True,
            blockers=artifact_blockers,
            command_results=[],
            confirmation_phrase_required=require_confirmation_phrase,
            confirmation_phrase_matches=confirmation_phrase_matches,
        )

    command_runner = runner or _run_shell
    command_results: list[dict[str, Any]] = []
    for phase in plan.get("plan_phases", []):
        if phase.get("remote_mutation") and not _remote_mutation_phase_authorized(
            phase,
            required_phrase=required_phrase,
            require_confirmation_phrase=require_confirmation_phrase,
        ):
            return _execution_report(
                plan=plan,
                status="blocked",
                apply=True,
                blockers=[
                    "remote_mutation_phase_missing_authorization_marker:"
                    f"{phase.get('phase')}"
                ],
                command_results=command_results,
                confirmation_phrase_required=require_confirmation_phrase,
                confirmation_phrase_matches=confirmation_phrase_matches,
            )
        for command in phase.get("commands") or []:
            result = command_runner(str(command))
            command_results.append(
                {
                    "phase": phase.get("phase"),
                    "command": result.command,
                    "returncode": result.returncode,
                    "stdout_tail": _tail(result.stdout),
                    "stderr_tail": _tail(result.stderr),
                }
            )
            if result.returncode != 0:
                return _execution_report(
                    plan=plan,
                    status="failed",
                    apply=True,
                    blockers=[f"command_failed:{phase.get('phase')}"],
                    command_results=command_results,
                    confirmation_phrase_required=require_confirmation_phrase,
                    confirmation_phrase_matches=confirmation_phrase_matches,
                )

    return _execution_report(
        plan=plan,
        status="applied",
        apply=True,
        blockers=[],
        command_results=command_results,
        confirmation_phrase_required=require_confirmation_phrase,
        confirmation_phrase_matches=confirmation_phrase_matches,
    )


def _owner_deploy_artifact_blockers(
    plan: dict[str, Any],
    artifact: dict[str, Any] | None,
    *,
    require_confirmation_phrase: bool = False,
) -> list[str]:
    if artifact is None:
        return []

    blockers: list[str] = []
    checks = artifact.get("checks") if isinstance(artifact.get("checks"), dict) else {}
    owner_gate = (
        artifact.get("owner_gate") if isinstance(artifact.get("owner_gate"), dict) else {}
    )
    candidate = (
        artifact.get("candidate") if isinstance(artifact.get("candidate"), dict) else {}
    )
    safety_invariants = (
        artifact.get("safety_invariants")
        if isinstance(artifact.get("safety_invariants"), dict)
        else {}
    )
    plan_release = plan.get("release") if isinstance(plan.get("release"), dict) else {}
    plan_inputs = plan.get("inputs") if isinstance(plan.get("inputs"), dict) else {}

    if artifact.get("status") != "ready_for_owner_deploy_decision":
        blockers.append("owner_deploy_confirmation_record_not_ready")
    if checks.get("ready_for_owner_deploy_decision") is not True:
        blockers.append("owner_deploy_decision_check_not_ready")
    if checks.get("blockers"):
        blockers.append("owner_deploy_artifact_has_blockers")
    if checks.get("forbidden_effects"):
        blockers.append("owner_deploy_artifact_contains_forbidden_effects")
    if (
        require_confirmation_phrase
        and owner_gate.get("deploy_confirmation_phrase") != CONFIRMATION_PHRASE
    ):
        blockers.append("owner_deploy_artifact_confirmation_phrase_mismatch")
    if candidate.get("head") != plan_release.get("head"):
        blockers.append("owner_deploy_artifact_head_mismatch")
    if candidate.get("archive_path") != plan_inputs.get("archive_path"):
        blockers.append("owner_deploy_artifact_archive_path_mismatch")
    if candidate.get("manifest_path") != plan_inputs.get("manifest_path"):
        blockers.append("owner_deploy_artifact_manifest_path_mismatch")
    if safety_invariants.get("deploy_apply_requested") is True:
        blockers.append("owner_deploy_artifact_was_built_from_apply")
    return blockers


def _remote_mutation_phase_authorized(
    phase: dict[str, Any],
    *,
    required_phrase: str | None,
    require_confirmation_phrase: bool,
) -> bool:
    phase_confirmation_gate_matches = (
        bool(required_phrase)
        and phase.get("requires_confirmation_phrase") == required_phrase
    )
    if require_confirmation_phrase:
        return phase_confirmation_gate_matches
    return (
        phase.get("remote_mutation_authorization")
        == OWNER_STANDING_AUTHORIZATION_REFERENCE
        or phase_confirmation_gate_matches
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


def _tail(value: str, *, max_chars: int = 2000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


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


def _load_owner_deploy_artifact(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except OSError as exc:
        raise DeployExecutionError(f"owner deploy confirmation record unreadable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DeployExecutionError(f"owner deploy confirmation record is not JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise DeployExecutionError("owner deploy confirmation record must be a JSON object")
    return payload


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply an owner-gated Tokyo runtime-governance deploy plan."
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
        help="Run remote-mutating commands. Uses standing authorization by default.",
    )
    parser.add_argument(
        "--confirmation-phrase",
        default=None,
        help=(
            "Legacy phrase, required only with --require-confirmation-phrase: "
            f"{CONFIRMATION_PHRASE}"
        ),
    )
    parser.add_argument(
        "--require-confirmation-phrase",
        action="store_true",
        help="Require the legacy exact confirmation phrase even during apply.",
    )
    parser.add_argument(
        "--owner-deploy-artifact-path",
        default=None,
        help=(
            "Optional with --apply: JSON output from "
            "build_tokyo_runtime_governance_owner_deploy_policy_artifact.py for the same "
            "archive, manifest, and HEAD."
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
