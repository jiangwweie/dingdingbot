#!/usr/bin/env python3
"""Standing-authorization git-based Tokyo runtime-governance deployment executor."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shlex
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.plan_tokyo_runtime_governance_git_deploy import (
    CONFIRMATION_PHRASE,
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_ENV_PATH,
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    DEFAULT_GIT_REF,
    DEFAULT_HOST,
    DEFAULT_SERVICE_NAME,
    DEFAULT_VENV_PYTHON,
    GitDeployPlanError,
    build_git_deploy_plan,
)
from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)


class GitDeployExecutionError(RuntimeError):
    """Raised when git deploy execution cannot proceed safely."""


@dataclass(frozen=True)
class ShellResult:
    command: str
    stdout: str
    stderr: str
    returncode: int


ShellRunner = Callable[[str], ShellResult]

_LOWER_HEX_TRANSACTION_ID = re.compile(r"^[0-9a-f]{8,64}$")


def build_remote_state_machine_invocation(
    plan: dict[str, Any],
    *,
    transaction_id: str,
    deploy_nonce: str,
    bootstrap_path: Path | None = None,
) -> dict[str, str]:
    """Build the one bounded, stdin-bootstrapped remote mutation session."""

    if not _LOWER_HEX_TRANSACTION_ID.fullmatch(transaction_id):
        raise GitDeployExecutionError("deploy_transaction_id_invalid")
    if not deploy_nonce or any(char.isspace() for char in deploy_nonce):
        raise GitDeployExecutionError("deploy_nonce_invalid")
    inputs = plan.get("inputs") or {}
    release = plan.get("release") or {}
    repo_root = Path(str(plan.get("repo_root") or _repo_root()))
    source = bootstrap_path or (
        repo_root / "scripts/tokyo_runtime_deploy_remote_state_machine.py"
    )
    raw = source.read_bytes()
    bootstrap_sha256 = hashlib.sha256(raw).hexdigest()
    host = str(inputs.get("host") or DEFAULT_HOST)
    target_sha = str(inputs.get("target_commit") or release.get("head") or "")
    old_sha = str(inputs.get("expected_deployed_head") or "")
    loader = (
        "import hashlib,os,platform,sys;"
        "b=sys.stdin.buffer.read();e=sys.argv[1];"
        "(_ for _ in ()).throw(RuntimeError('bootstrap_sha256_mismatch')) "
        "if hashlib.sha256(b).hexdigest()!=e else None;"
        "(_ for _ in ()).throw(RuntimeError('bootstrap_python_abi_mismatch')) "
        "if not(platform.python_implementation()=='CPython' and "
        "sys.version_info[:2]==(3,10)) else None;"
        "(_ for _ in ()).throw(RuntimeError('bootstrap_root_required')) "
        "if os.geteuid()!=0 else None;"
        "sys.argv=['tokyo_runtime_deploy_remote_state_machine.py']+sys.argv[2:];"
        "exec(compile(b,'tokyo_runtime_deploy_remote_state_machine.py','exec'),"
        "{'__name__':'__main__','__bootstrap_source__':b})"
    )
    remote_argv = [
        "sudo", "-n", "/usr/bin/systemd-run", "--wait", "--pipe",
        "--collect", "--service-type=exec",
        f"--unit=brc-deploy-{transaction_id}.service",
        "-p", "KillMode=control-group", "-p", "SendSIGKILL=yes",
        "-p", "TimeoutStopSec=30s", "-p", "RuntimeMaxSec=60min",
        "-p", "Restart=no", "/usr/bin/python3", "-c", loader,
        bootstrap_sha256,
        "--bootstrap-sha256", bootstrap_sha256,
        "--transaction-id", transaction_id,
        "--deploy-nonce", deploy_nonce,
        "--old-sha", old_sha,
        "--target-sha", target_sha,
        "--deploy-root", str(inputs.get("deploy_root") or DEFAULT_DEPLOY_ROOT),
        "--repo-url", str(inputs.get("repo_url") or ""),
        "--git-ref", str(inputs.get("git_ref") or ""),
        "--release-name", str(inputs.get("release_name") or release.get("release_name") or ""),
        "--previous-release-path", str(inputs.get("previous_release_path") or ""),
        "--service-name", str(inputs.get("service_name") or DEFAULT_SERVICE_NAME),
        "--env-path", str(inputs.get("env_path") or DEFAULT_ENV_PATH),
        "--expected-latest-migration", str(inputs.get("expected_latest_migration") or ""),
    ]
    command = (
        f"ssh {shlex.quote(host)} {shlex.quote(shlex.join(remote_argv))} "
        f"< {shlex.quote(str(source))}"
    )
    return {
        "command": command,
        "transaction_id": transaction_id,
        "deploy_nonce": deploy_nonce,
        "bootstrap_sha256": bootstrap_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    repo_url = args.repo_url or _git(repo_root, "remote", "get-url", "origin")
    plan = build_git_deploy_plan(
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
    report = execute_git_deploy_plan(
        plan,
        apply=args.apply,
        confirmation_phrase=args.confirmation_phrase,
        require_confirmation_phrase=args.require_confirmation_phrase,
        transaction_id=args.transaction_id,
        deploy_nonce=args.deploy_nonce,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human_report(report)
    return 0 if report["status"] in {"dry_run_ready", "applied"} else 2


def execute_git_deploy_plan(
    plan: dict[str, Any],
    *,
    apply: bool,
    confirmation_phrase: str | None,
    require_confirmation_phrase: bool = False,
    transaction_id: str | None = None,
    deploy_nonce: str | None = None,
    runner: ShellRunner | None = None,
) -> dict[str, Any]:
    blockers = list(plan.get("checks", {}).get("blockers") or [])
    if blockers:
        return _execution_report(
            plan=plan,
            status="blocked",
            apply=apply,
            blockers=["git_deploy_plan_blocked", *blockers],
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

    command_runner = runner or _run_shell
    command_results: list[dict[str, Any]] = []
    mutation_started = False
    transaction_identity: dict[str, str] | None = None
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
        if phase.get("remote_state_machine"):
            if transaction_identity is not None:
                raise GitDeployExecutionError("multiple_remote_state_machine_phases")
            if (transaction_id is None) != (deploy_nonce is None):
                raise GitDeployExecutionError(
                    "resume_transaction_id_and_deploy_nonce_required_together"
                )
            transaction_identity = {
                "transaction_id": transaction_id or uuid.uuid4().hex,
                "deploy_nonce": deploy_nonce or secrets.token_hex(32),
            }
            if not _LOWER_HEX_TRANSACTION_ID.fullmatch(
                transaction_identity["transaction_id"]
            ):
                raise GitDeployExecutionError("deploy_transaction_id_invalid")
            if not transaction_identity["deploy_nonce"] or any(
                char.isspace() for char in transaction_identity["deploy_nonce"]
            ):
                raise GitDeployExecutionError("deploy_nonce_invalid")
            print(
                json.dumps(
                    {
                        "status": "deploy_transaction_resolved",
                        **transaction_identity,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            invocation = build_remote_state_machine_invocation(
                plan,
                transaction_id=transaction_identity["transaction_id"],
                deploy_nonce=transaction_identity["deploy_nonce"],
            )
            mutation_started = True
            result = command_runner(invocation["command"])
            command_results.append(
                {
                    "phase": phase.get("phase"),
                    "command": result.command,
                    "returncode": result.returncode,
                    "stdout_tail": _tail(result.stdout),
                    "stderr_tail": _tail(result.stderr),
                    **transaction_identity,
                    "bootstrap_sha256": invocation["bootstrap_sha256"],
                }
            )
            if result.returncode != 0:
                writers_left_disabled = '"status": "failed_contained"' in result.stdout
                return _execution_report(
                    plan=plan,
                    status=(
                        "failed_contained"
                        if writers_left_disabled
                        else "failed"
                    ),
                    apply=True,
                    blockers=[f"command_failed:{phase.get('phase')}"],
                    command_results=command_results,
                    confirmation_phrase_required=require_confirmation_phrase,
                    confirmation_phrase_matches=confirmation_phrase_matches,
                    writers_left_disabled=writers_left_disabled,
                )
            continue
        for command in phase.get("commands") or []:
            mutation_started = mutation_started or bool(phase.get("remote_mutation"))
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
                writers_left_disabled = False
                status = "failed"
                if mutation_started:
                    containment_command = _failure_containment_command(plan)
                    containment = command_runner(containment_command)
                    command_results.append(
                        {
                            "phase": "failure_containment",
                            "command": containment.command,
                            "returncode": containment.returncode,
                            "stdout_tail": _tail(containment.stdout),
                            "stderr_tail": _tail(containment.stderr),
                        }
                    )
                    writers_left_disabled = containment.returncode == 0
                    status = (
                        "failed_contained"
                        if writers_left_disabled
                        else "failed_uncontained"
                    )
                return _execution_report(
                    plan=plan,
                    status=status,
                    apply=True,
                    blockers=[f"command_failed:{phase.get('phase')}"],
                    command_results=command_results,
                    confirmation_phrase_required=require_confirmation_phrase,
                    confirmation_phrase_matches=confirmation_phrase_matches,
                    writers_left_disabled=writers_left_disabled,
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
    writers_left_disabled: bool = False,
) -> dict[str, Any]:
    commands = [
        {"phase": phase.get("phase"), "command": command}
        for phase in plan.get("plan_phases", [])
        for command in (
            phase.get("commands")
            or (["<single_remote_state_machine>"] if phase.get("remote_state_machine") else [])
        )
    ]
    effects = _effects_from_command_results(
        apply=apply,
        command_results=command_results,
    )
    interaction = _interaction_summary(apply=apply, effects=effects)
    owner_summary = _owner_deploy_summary(
        status=status,
        apply=apply,
        blockers=blockers,
        commands=commands,
        effects=effects,
    )
    return {
        "status": status,
        "scope": "tokyo_runtime_governance_git_deploy_execution",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "apply_requested": apply,
        "interaction": interaction,
        "owner_summary": owner_summary,
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
            "writers_left_disabled": writers_left_disabled,
        },
        "planned_commands": commands if not apply else [],
        "command_results": command_results,
        "effects": effects,
    }


def _failure_containment_command(plan: dict[str, Any]) -> str:
    inputs = plan.get("inputs") or {}
    release = plan.get("release") or {}
    host = str(inputs.get("host") or DEFAULT_HOST)
    env_path = str(inputs.get("env_path") or DEFAULT_ENV_PATH)
    release_path = str(
        release.get("remote_release_path")
        or f"{DEFAULT_DEPLOY_ROOT}/app/current"
    )
    python = f"{release_path.rstrip('/')}/.venv/bin/python"
    services = (
        "brc-runtime-signal-watcher.timer",
        "brc-runtime-monitor.timer",
        "brc-ticket-lifecycle-maintenance.timer",
        "brc-runtime-signal-watcher.service",
        "brc-runtime-monitor.service",
        "brc-ticket-lifecycle-maintenance.service",
        "brc-runtime-signal-watcher-canary.service",
        "brc-owner-console-canary-readonly.service",
    )
    remote = (
        "set -eu; "
        + " ".join(
            f"sudo -n systemctl stop {shlex.quote(service)};"
            for service in services
        )
        + f" cd {shlex.quote(release_path)}; "
        + f"set -a; . {shlex.quote(env_path)}; set +a; "
        + f"PYTHONPATH=$PWD {shlex.quote(python)} "
        + "scripts/set_ticket_lifecycle_mutation_capability.py --disable "
        + "--require-database-url --certification-ref deploy-failure-containment --json"
    )
    return f"ssh {shlex.quote(host)} {shlex.quote(remote)}"


def _interaction_summary(
    *,
    apply: bool,
    effects: dict[str, bool],
) -> dict[str, bool | str]:
    return {
        "level": "L3_bounded_deploy_apply" if apply else "L1_deploy_plan_only",
        "remote_interaction_count": _remote_interaction_count(effects),
        "mutates_remote_files": bool(effects.get("remote_files_modified")),
        "approaches_real_order": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "requires_owner_chat_confirmation": False,
    }


def _remote_interaction_count(effects: dict[str, Any]) -> int:
    if not effects.get("apply_requested"):
        return 0
    return int(effects.get("remote_interaction_count") or 0)


def _owner_deploy_summary(
    *,
    status: str,
    apply: bool,
    blockers: list[str],
    commands: list[dict[str, Any]],
    effects: dict[str, bool],
) -> dict[str, Any]:
    return {
        "state": "部署完成" if status == "applied" else "部署规划完成",
        "result": status,
        "interaction_level": (
            "L3_bounded_deploy_apply" if apply else "L1_deploy_plan_only"
        ),
        "owner_intervention_required": bool(blockers),
        "blockers": blockers,
        "changed": {
            "remote_files": bool(effects.get("remote_files_modified")),
            "deploy_backup": False,
            "migrations": bool(effects.get("migrations_run")),
            "services_restarted": bool(effects.get("services_restarted")),
        },
        "not_changed": {
            "secrets": True,
            "credentials": True,
            "live_profile": True,
            "order_sizing_defaults": True,
            "withdrawals_or_transfers": True,
            "exchange_orders": True,
        },
        "postdeploy_snapshot_recommended": bool(apply and not blockers),
        "safety": {
            "finalgate_bypassed": False,
            "operation_layer_bypassed": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def _effects_from_command_results(
    *,
    apply: bool,
    command_results: list[dict[str, Any]],
) -> dict[str, Any]:
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
    remote_interaction_count = sum(
        1 for command in successful_commands if _command_touches_tokyo(command)
    )
    return {
        "apply_requested": bool(apply),
        "remote_interaction_count": remote_interaction_count,
        "remote_files_modified": bool(
            apply
            and (
                "2_owner_authorized_git_fetch_and_export" in successful_phases
                or "2_single_remote_deploy_transaction" in successful_phases
                or any("ln -sfn" in command for command in successful_commands)
            )
        ),
        "deploy_backup_created": False,
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


def _command_touches_tokyo(command: str) -> bool:
    markers = (
        "ssh ",
        "probe_tokyo_runtime_governance_readonly.py",
        "verify_tokyo_runtime_governance_postdeploy.py",
    )
    return any(marker in command for marker in markers)


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
        raise GitDeployExecutionError("not inside a git repository")
    return Path(completed.stdout.strip())


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
        raise GitDeployExecutionError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply an owner-gated git-based Tokyo deploy plan."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--git-ref", default=DEFAULT_GIT_REF)
    parser.add_argument("--target-commit", default=None)
    parser.add_argument("--release-name", required=True)
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
    parser.add_argument(
        "--transaction-id",
        help="Resume the exact journaled deployment transaction; requires --deploy-nonce.",
    )
    parser.add_argument(
        "--deploy-nonce",
        help="Resume nonce printed by the first attempt; requires --transaction-id.",
    )
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
    except (GitDeployExecutionError, GitDeployPlanError) as exc:
        print(f"git_deploy_execution_error={exc}", file=sys.stderr)
        raise SystemExit(2)
