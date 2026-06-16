#!/usr/bin/env python3
"""Build the Owner decision packet for git-based Tokyo deployment."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from scripts.execute_tokyo_runtime_governance_git_deploy import (
    execute_git_deploy_plan,
)
from scripts.plan_tokyo_runtime_governance_deploy import (
    CONFIRMATION_PHRASE,
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_ENV_PATH,
    DEFAULT_HOST,
    DEFAULT_SERVICE_NAME,
    DEFAULT_VENV_PYTHON,
)
from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)
from scripts.plan_tokyo_runtime_governance_git_deploy import (
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    DEFAULT_GIT_REF,
    build_git_deploy_plan,
)
from scripts.prepare_tokyo_runtime_governance_release import (
    DEFAULT_EXPECTED_MIN_MIGRATIONS,
    build_release_readiness_report,
)
from scripts.probe_tokyo_runtime_governance_readonly import (
    TokyoProbeError,
    build_tokyo_connectivity_probe,
    build_tokyo_probe_report,
)
from scripts.verify_runtime_submit_rehearsal_pre_live_packet import (
    build_pre_live_packet,
)


class GitOwnerDeployPacketError(RuntimeError):
    """Raised when the git owner deploy packet cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    packet = asyncio.run(_build_owner_deploy_packet_from_args(args))
    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        _print_human(packet)
    return 0 if packet["checks"]["ready_for_owner_git_deploy_decision"] else 2


async def _build_owner_deploy_packet_from_args(
    args: argparse.Namespace,
) -> dict[str, Any]:
    repo_root = _repo_root()
    repo_url = args.repo_url or _git(repo_root, "remote", "get-url", "origin")
    release_report = build_release_readiness_report(
        repo_root=repo_root,
        deployed_head=args.expected_deployed_head,
        expected_min_migrations=args.expected_min_migrations,
        expected_latest_migration=args.expected_latest_migration,
        write_artifacts=False,
        output_dir=Path(args.output_dir),
        allow_tracked_dirty_for_remote_git_export=True,
    )
    deploy_plan = build_git_deploy_plan(
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
    deploy_dry_run = execute_git_deploy_plan(
        deploy_plan,
        apply=False,
        confirmation_phrase=None,
    )
    tokyo_probe = None
    connectivity_probe = None
    if not args.skip_remote_probe:
        connectivity_probe = build_tokyo_connectivity_probe(
            host=args.host,
            ports=(22,),
            connect_timeout_seconds=args.connect_timeout_seconds,
        )
        try:
            tokyo_probe = build_tokyo_probe_report(
                host=args.host,
                deploy_root=args.remote_probe_deploy_root,
                api_base=args.api_base,
                expected_current_head=args.expected_deployed_head,
                expected_migration_count=args.expected_remote_migration_count,
                expected_latest_migration=args.expected_remote_latest_migration,
                connect_timeout_seconds=args.connect_timeout_seconds,
            )
        except TokyoProbeError as exc:
            tokyo_probe = _blocked_tokyo_probe_report(
                host=args.host,
                deploy_root=args.remote_probe_deploy_root,
                api_base=args.api_base,
                error=str(exc),
                connectivity_probe=connectivity_probe,
            )
    pre_live_packet = None
    if not args.skip_pre_live_packet:
        pre_live_packet = await build_pre_live_packet(
            deployed_head=args.expected_deployed_head,
            owner_real_submit_authorized=False,
            owner_live_runtime_enablement_authorized=False,
            require_current_head_deployed=False,
            active_positions=args.active_positions,
        )
    return build_git_owner_deploy_packet(
        release_report=release_report,
        deploy_plan=deploy_plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_packet=pre_live_packet,
        connectivity_probe=connectivity_probe,
    )


def build_git_owner_deploy_packet(
    *,
    release_report: dict[str, Any],
    deploy_plan: dict[str, Any],
    deploy_dry_run: dict[str, Any],
    tokyo_probe: dict[str, Any] | None,
    pre_live_packet: dict[str, Any] | None,
    connectivity_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    release_checks = release_report.get("release_checks", {})
    plan_checks = deploy_plan.get("checks", {})
    dry_run_checks = deploy_dry_run.get("checks", {})
    probe_checks = (tokyo_probe or {}).get("checks", {})
    connectivity_checks = (connectivity_probe or {}).get("checks", {})
    pre_live_checks = (pre_live_packet or {}).get("checks", {})

    release_ready = bool(release_checks.get("ready_for_packaging"))
    plan_ready = bool(plan_checks.get("ready_for_owner_authorized_remote_deploy"))
    dry_run_ready = (
        deploy_dry_run.get("status") == "dry_run_ready"
        and deploy_dry_run.get("apply_requested") is False
        and dry_run_checks.get("commands_executed") == 0
    )
    remote_probe_ready = bool(
        tokyo_probe
        and probe_checks.get("ready_for_controlled_deploy_preflight") is True
    )
    pre_live_packet_skipped = pre_live_packet is None
    pre_live_technical_ready = bool(
        pre_live_packet_skipped
        or (
            pre_live_packet
            and pre_live_checks.get("technical_rehearsal_passed") is True
            and pre_live_checks.get("registration_draft_chain_passed") is True
        )
    )
    first_real_submit_still_blocked = bool(
        pre_live_packet_skipped
        or (
            pre_live_packet
            and pre_live_packet.get("status") == "blocked_before_first_real_submit"
            and pre_live_checks.get("ready_for_first_real_submit") is False
        )
    )
    forbidden_pre_live_flags = list(
        pre_live_checks.get("forbidden_execution_flags") or []
    )
    forbidden_effects = _forbidden_effects(
        release_report=release_report,
        deploy_plan=deploy_plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_packet=pre_live_packet,
    )

    blockers: list[str] = []
    if not release_ready:
        blockers.append("release_not_ready_for_packaging")
    if not plan_ready:
        blockers.append("git_deploy_plan_not_ready")
    if not dry_run_ready:
        blockers.append("git_deploy_executor_dry_run_not_ready")
    if not remote_probe_ready:
        blockers.append("tokyo_readonly_probe_not_ready")
        blockers.extend(
            f"tokyo_probe:{item}" for item in list(probe_checks.get("blockers") or [])
        )
        blockers.extend(
            f"tokyo_connectivity:{item}"
            for item in list(connectivity_checks.get("blockers") or [])
        )
    if not pre_live_technical_ready:
        blockers.append("pre_live_submit_rehearsal_not_technically_ready")
    if forbidden_pre_live_flags:
        blockers.append("pre_live_packet_contains_forbidden_execution_flags")
    if forbidden_effects:
        blockers.append("packet_contains_forbidden_side_effect_flags")

    warnings: list[str] = []
    warnings.extend(release_checks.get("warnings") or [])
    warnings.extend(plan_checks.get("warnings") or [])
    warnings.extend(probe_checks.get("warnings") or [])
    if pre_live_packet_skipped:
        warnings.append("pre_live_packet_skipped_for_deploy_only")
    if not first_real_submit_still_blocked:
        warnings.append("first_real_submit_not_a_deploy_apply_precondition")

    plan_inputs = deploy_plan.get("inputs", {})
    release = deploy_plan.get("release", {})
    candidate = {
        "branch": release_report.get("local_git", {}).get("branch"),
        "head": release.get("head"),
        "short_head": release.get("short_head"),
        "repo_url": plan_inputs.get("repo_url"),
        "git_ref": plan_inputs.get("git_ref"),
        "remote_ref_head": release.get("remote_ref_head"),
        "release_name": release.get("release_name"),
        "remote_release_path": release.get("remote_release_path"),
        "migrations": release_report.get("migrations", {}),
        "tokyo_baseline": release_report.get("tokyo_baseline", {}),
    }

    return {
        "status": (
            "ready_for_owner_git_deploy_decision"
            if not blockers
            else "blocked"
        ),
        "scope": "tokyo_runtime_governance_git_owner_deploy_decision_packet",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "checks": {
            "ready_for_owner_git_deploy_decision": not blockers,
            "release_ready_for_packaging": release_ready,
            "git_deploy_plan_ready": plan_ready,
            "git_deploy_executor_dry_run_ready": dry_run_ready,
            "tokyo_readonly_probe_ready": remote_probe_ready,
            "tokyo_connectivity_probe_ready": (
                connectivity_probe.get("status") == "ready"
                if connectivity_probe is not None
                else None
            ),
            "tokyo_probe_blockers": list(probe_checks.get("blockers") or []),
            "tokyo_connectivity_blockers": list(
                connectivity_checks.get("blockers") or []
            ),
            "pre_live_submit_technical_ready": pre_live_technical_ready,
            "first_real_submit_still_blocked": first_real_submit_still_blocked,
            "pre_live_packet_skipped": pre_live_packet_skipped,
            "forbidden_pre_live_flags": forbidden_pre_live_flags,
            "forbidden_effects": forbidden_effects,
            "blockers": blockers,
            "warnings": _dedupe(warnings),
        },
        "owner_gate": {
            "deploy_apply_authorized_by": OWNER_STANDING_AUTHORIZATION_REFERENCE,
            "deploy_confirmation_phrase_required": False,
            "deploy_confirmation_phrase": CONFIRMATION_PHRASE,
            "deploy_confirmation_authorizes": [
                "git fetch/export release tree",
                "remote PG backup",
                "alembic migration",
                "backend service restart",
                "postdeploy read-only smoke",
            ],
            "deploy_confirmation_does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "runtime live execution enablement",
                "withdrawal or transfer",
            ],
        },
        "safety_invariants": {
            "deploy_apply_requested": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "migrations_run": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
            "secrets_read": False,
            "packet_build_only": True,
        },
    }


def _blocked_tokyo_probe_report(
    *,
    host: str,
    deploy_root: str,
    api_base: str,
    error: str,
    connectivity_probe: dict[str, Any] | None,
) -> dict[str, Any]:
    connectivity_blockers = list(
        ((connectivity_probe or {}).get("checks") or {}).get("blockers") or []
    )
    blockers = ["tokyo_readonly_probe_error", *connectivity_blockers]
    return {
        "status": "blocked",
        "scope": "tokyo_runtime_governance_readonly_probe",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "host": host,
            "deploy_root": deploy_root,
            "api_base": api_base,
        },
        "facts": {
            "probe_error": error,
            "connectivity_probe": connectivity_probe,
        },
        "checks": {
            "ready_for_controlled_deploy_preflight": False,
            "blockers": _dedupe(blockers),
            "warnings": [],
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


def _forbidden_effects(
    *,
    release_report: dict[str, Any],
    deploy_plan: dict[str, Any],
    deploy_dry_run: dict[str, Any],
    tokyo_probe: dict[str, Any] | None,
    pre_live_packet: dict[str, Any] | None,
) -> list[str]:
    sources = {
        "release": release_report.get("safety_invariants", {}),
        "deploy_plan": deploy_plan.get("safety_invariants", {}),
        "deploy_dry_run": deploy_dry_run.get("effects", {}),
        "tokyo_probe": (tokyo_probe or {}).get("safety_invariants", {}),
        "pre_live": (pre_live_packet or {}).get("safety_invariants", {}),
    }
    allowed_true = {"planning_run_only", "packet_build_only"}
    forbidden: list[str] = []
    for source, flags in sources.items():
        if not isinstance(flags, dict):
            continue
        for name, value in flags.items():
            if name in allowed_true:
                continue
            if value is True:
                forbidden.append(f"{source}.{name}")
    if deploy_dry_run.get("apply_requested") is True:
        forbidden.append("deploy_dry_run.apply_requested")
    return forbidden


def _repo_root() -> Path:
    import subprocess

    completed = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise GitOwnerDeployPacketError("not inside a git repository")
    return Path(completed.stdout.strip())


def _git(repo_root: Path, *args: str) -> str:
    import subprocess

    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise GitOwnerDeployPacketError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-mutating git Owner deployment decision packet."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--repo-url", default=None)
    parser.add_argument("--git-ref", default=DEFAULT_GIT_REF)
    parser.add_argument("--target-commit", default=None)
    parser.add_argument("--release-name", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--remote-probe-deploy-root", default="~/brc-deploy")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    parser.add_argument("--venv-python", default=DEFAULT_VENV_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--previous-release", required=True)
    parser.add_argument("--expected-deployed-head", required=True)
    parser.add_argument("--expected-min-migrations", type=int, default=DEFAULT_EXPECTED_MIN_MIGRATIONS)
    parser.add_argument("--expected-remote-migration-count", type=int, required=True)
    parser.add_argument("--expected-remote-latest-migration", required=True)
    parser.add_argument("--expected-latest-migration", default=DEFAULT_EXPECTED_LATEST_MIGRATION)
    parser.add_argument("--output-dir", default="output/tokyo-runtime-governance-release")
    parser.add_argument("--connect-timeout-seconds", type=int, default=8)
    parser.add_argument("--active-positions", type=int, default=0)
    parser.add_argument("--skip-remote-probe", action="store_true")
    parser.add_argument("--skip-pre-live-packet", action="store_true")
    return parser.parse_args(argv)


def _print_human(packet: dict[str, Any]) -> None:
    checks = packet["checks"]
    candidate = packet["candidate"]
    print(f"status={packet['status']}")
    print(
        "ready_for_owner_git_deploy_decision="
        + str(checks["ready_for_owner_git_deploy_decision"]).lower()
    )
    print(f"head={candidate.get('head')}")
    print(f"repo_url={candidate.get('repo_url')}")
    print(f"git_ref={candidate.get('git_ref')}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GitOwnerDeployPacketError as exc:
        print(f"git_owner_deploy_packet_error={exc}", file=sys.stderr)
        raise SystemExit(2)
