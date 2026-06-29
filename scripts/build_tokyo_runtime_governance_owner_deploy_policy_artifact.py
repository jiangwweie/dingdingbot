#!/usr/bin/env python3
"""Build the Owner confirmation record for Tokyo runtime-governance deployment.

This script aggregates existing non-mutating evidence into a concise deploy
authorization evidence. It does not deploy, run migrations, restart services,
create execution records, create orders, call OrderLifecycle, call exchange
APIs, read secrets, or authorize a real submit.
"""

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

from scripts.execute_tokyo_runtime_governance_deploy import execute_deploy_plan
from scripts.plan_tokyo_runtime_governance_deploy import (
    CONFIRMATION_PHRASE,
    DEFAULT_API_BASE,
    DEFAULT_DEPLOY_ROOT,
    DEFAULT_ENV_PATH,
    DEFAULT_EXPECTED_DEPLOYED_HEAD,
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    DEFAULT_HOST,
    DEFAULT_PREVIOUS_RELEASE,
    DEFAULT_SERVICE_NAME,
    DEFAULT_VENV_PYTHON,
    build_deploy_plan,
)
from scripts.prepare_tokyo_runtime_governance_release import (
    DEFAULT_EXPECTED_LATEST_MIGRATION as RELEASE_EXPECTED_LATEST_MIGRATION,
)
from scripts.prepare_tokyo_runtime_governance_release import (
    DEFAULT_EXPECTED_MIN_MIGRATIONS,
    build_release_readiness_report,
)
from scripts.probe_tokyo_runtime_governance_readonly import (
    DEFAULT_EXPECTED_LATEST_MIGRATION as TOKYO_EXPECTED_LATEST_MIGRATION,
)
from scripts.probe_tokyo_runtime_governance_readonly import (
    DEFAULT_EXPECTED_MIGRATION_COUNT as TOKYO_EXPECTED_MIGRATION_COUNT,
)
from scripts.probe_tokyo_runtime_governance_readonly import (
    build_tokyo_probe_report,
)
from scripts.verify_runtime_submit_rehearsal_pre_live_evidence import (
    build_pre_live_evidence,
)
from src.domain.standing_authorization import (
    OWNER_STANDING_AUTHORIZATION_REFERENCE,
)


class OwnerDeployArtifactError(RuntimeError):
    """Raised when the owner deploy evidence cannot be built."""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact = asyncio.run(_build_owner_deploy_artifact_from_args(args))
    if args.json:
        print(json.dumps(artifact, indent=2, sort_keys=True))
    else:
        _print_human(artifact)
    return 0 if artifact["checks"]["ready_for_owner_deploy_decision"] else 2


async def _build_owner_deploy_artifact_from_args(
    args: argparse.Namespace,
) -> dict[str, Any]:
    repo_root = _repo_root()
    archive_path = Path(args.archive_path)
    manifest_path = Path(args.manifest_path)
    release_report = build_release_readiness_report(
        repo_root=repo_root,
        deployed_head=args.expected_deployed_head,
        expected_min_migrations=args.expected_min_migrations,
        expected_latest_migration=args.expected_release_latest_migration,
        write_artifacts=False,
        output_dir=Path(args.output_dir),
    )
    deploy_plan = build_deploy_plan(
        repo_root=repo_root,
        archive_path=archive_path,
        manifest_path=manifest_path,
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
        expected_latest_migration=args.expected_deploy_latest_migration,
    )
    deploy_dry_run = execute_deploy_plan(
        deploy_plan,
        apply=False,
        confirmation_phrase=None,
    )
    tokyo_probe = None
    if not args.skip_remote_probe:
        tokyo_probe = build_tokyo_probe_report(
            host=args.host,
            deploy_root=args.remote_probe_deploy_root,
            api_base=args.api_base,
            expected_current_head=args.expected_deployed_head,
            expected_migration_count=args.expected_remote_migration_count,
            expected_latest_migration=args.expected_remote_latest_migration,
            connect_timeout_seconds=args.connect_timeout_seconds,
        )
    pre_live_evidence = None
    if not args.skip_pre_live_evidence:
        pre_live_evidence = await build_pre_live_evidence(
            deployed_head=args.expected_deployed_head,
            owner_real_submit_authorized=False,
            owner_live_runtime_enablement_authorized=False,
            require_current_head_deployed=False,
            active_positions=args.active_positions,
        )
    return build_owner_deploy_artifact(
        release_report=release_report,
        deploy_plan=deploy_plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_evidence=pre_live_evidence,
        archive_path=archive_path,
        manifest_path=manifest_path,
    )


def build_owner_deploy_artifact(
    *,
    release_report: dict[str, Any],
    deploy_plan: dict[str, Any],
    deploy_dry_run: dict[str, Any],
    tokyo_probe: dict[str, Any] | None,
    pre_live_evidence: dict[str, Any] | None,
    archive_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Aggregate existing readiness reports into one Owner-facing evidence."""

    release_checks = release_report.get("release_checks", {})
    plan_checks = deploy_plan.get("checks", {})
    dry_run_checks = deploy_dry_run.get("checks", {})
    probe_checks = (tokyo_probe or {}).get("checks", {})
    pre_live_checks = (pre_live_evidence or {}).get("checks", {})

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
    pre_live_evidence_skipped = pre_live_evidence is None
    pre_live_technical_ready = bool(
        pre_live_evidence_skipped
        or (
            pre_live_evidence
            and pre_live_checks.get("technical_rehearsal_passed") is True
            and pre_live_checks.get("registration_draft_chain_passed") is True
        )
    )
    first_real_submit_still_blocked = bool(
        pre_live_evidence_skipped
        or (
            pre_live_evidence
            and pre_live_evidence.get("status") == "blocked_before_first_real_submit"
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
        pre_live_evidence=pre_live_evidence,
    )

    blockers: list[str] = []
    if not release_ready:
        blockers.append("release_not_ready_for_packaging")
    if not plan_ready:
        blockers.append("deploy_plan_not_ready")
    if not dry_run_ready:
        blockers.append("deploy_executor_dry_run_not_ready")
    if not remote_probe_ready:
        blockers.append("tokyo_readonly_probe_not_ready")
    if not pre_live_technical_ready:
        blockers.append("pre_live_submit_rehearsal_not_technically_ready")
    if forbidden_pre_live_flags:
        blockers.append("pre_live_evidence_contains_forbidden_execution_flags")
    if forbidden_effects:
        blockers.append("artifact_contains_forbidden_side_effect_flags")

    warnings: list[str] = []
    warnings.extend(release_checks.get("warnings") or [])
    warnings.extend(plan_checks.get("warnings") or [])
    warnings.extend(probe_checks.get("warnings") or [])
    if not first_real_submit_still_blocked:
        warnings.append("first_real_submit_not_a_deploy_apply_precondition")

    candidate = {
        "branch": release_report.get("local_git", {}).get("branch"),
        "head": release_report.get("local_git", {}).get("head"),
        "short_head": release_report.get("local_git", {}).get("short_head"),
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "migrations": release_report.get("migrations", {}),
        "tokyo_baseline": release_report.get("tokyo_baseline", {}),
    }
    release = deploy_plan.get("release", {})
    evidence = {
        "status": "ready_for_owner_deploy_decision" if not blockers else "blocked",
        "scope": "tokyo_runtime_governance_owner_deploy_confirmation_record",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "deploy_plan_summary": {
            "status": deploy_plan.get("status"),
            "phase_count": len(deploy_plan.get("plan_phases") or []),
            "commands_planned": dry_run_checks.get("commands_planned"),
            "commands_executed": dry_run_checks.get("commands_executed"),
            "remote_release_path": release.get("remote_release_path"),
            "backup_path": release.get("backup_path"),
        },
        "tokyo_readonly_summary": _tokyo_summary(tokyo_probe),
        "pre_live_submit_summary": _pre_live_summary(pre_live_evidence),
        "checks": {
            "ready_for_owner_deploy_decision": not blockers,
            "release_ready_for_packaging": release_ready,
            "deploy_plan_ready": plan_ready,
            "deploy_executor_dry_run_ready": dry_run_ready,
            "tokyo_readonly_probe_ready": remote_probe_ready,
            "pre_live_evidence_skipped": pre_live_evidence_skipped,
            "pre_live_submit_technical_ready": pre_live_technical_ready,
            "first_real_submit_still_blocked": first_real_submit_still_blocked,
            "forbidden_pre_live_flags": forbidden_pre_live_flags,
            "forbidden_effects": forbidden_effects,
            "blockers": blockers,
            "warnings": sorted(set(warnings)),
        },
        "owner_gate": {
            "deploy_apply_authorized_by": OWNER_STANDING_AUTHORIZATION_REFERENCE,
            "deploy_confirmation_phrase_required": False,
            "deploy_confirmation_phrase": CONFIRMATION_PHRASE,
            "authorizes_only": (
                "remote upload, backup, migration, symlink switch, restart, "
                "and post-deploy read-only smoke for this release"
            ),
            "does_not_authorize": [
                "real runtime submit",
                "exchange order placement",
                "OrderLifecycle adapter enablement",
                "withdrawal or transfer",
                "live runtime profile change",
            ],
        },
        "safety_invariants": {
            "artifact_build_only": True,
            "deploy_apply_requested": bool(deploy_dry_run.get("apply_requested")),
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
            "secrets_read": False,
        },
    }
    return evidence


def _tokyo_summary(tokyo_probe: dict[str, Any] | None) -> dict[str, Any]:
    if not tokyo_probe:
        return {"status": "not_collected"}
    facts = tokyo_probe.get("facts", {})
    health = facts.get("health") if isinstance(facts.get("health"), dict) else {}
    return {
        "status": tokyo_probe.get("status"),
        "current_head": facts.get("current_head"),
        "migration_count": facts.get("migration_count"),
        "latest_migration": facts.get("latest_migration"),
        "health": health.get("body_json"),
    }


def _pre_live_summary(pre_live_evidence: dict[str, Any] | None) -> dict[str, Any]:
    if not pre_live_evidence:
        return {"status": "not_collected"}
    checks = pre_live_evidence.get("checks", {})
    return {
        "status": pre_live_evidence.get("status"),
        "technical_rehearsal_passed": checks.get("technical_rehearsal_passed"),
        "registration_draft_chain_passed": checks.get(
            "registration_draft_chain_passed"
        ),
        "ready_for_first_real_submit": checks.get("ready_for_first_real_submit"),
        "implementation_blockers": checks.get("implementation_blockers"),
        "technical_blockers": checks.get("technical_blockers"),
        "forbidden_execution_flags": checks.get("forbidden_execution_flags"),
    }


def _forbidden_effects(
    *,
    release_report: dict[str, Any],
    deploy_plan: dict[str, Any],
    deploy_dry_run: dict[str, Any],
    tokyo_probe: dict[str, Any] | None,
    pre_live_evidence: dict[str, Any] | None,
) -> list[str]:
    sources = {
        "release": release_report.get("safety_invariants", {}),
        "deploy_plan": deploy_plan.get("safety_invariants", {}),
        "deploy_dry_run": deploy_dry_run.get("effects", {}),
        "tokyo_probe": (tokyo_probe or {}).get("safety_invariants", {}),
        "pre_live_evidence": (pre_live_evidence or {}).get("safety_invariants", {}),
    }
    allowed_true = {
        "planning_run_only",
        "artifact_build_only",
    }
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
        raise OwnerDeployArtifactError("not inside a git repository")
    return Path(completed.stdout.strip())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-mutating Owner deployment confirmation record."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--archive-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--release-name", default=None)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--deploy-root", default=DEFAULT_DEPLOY_ROOT)
    parser.add_argument("--remote-probe-deploy-root", default="~/brc-deploy")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH)
    parser.add_argument("--venv-python", default=DEFAULT_VENV_PYTHON)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--previous-release", default=DEFAULT_PREVIOUS_RELEASE)
    parser.add_argument("--expected-deployed-head", default=DEFAULT_EXPECTED_DEPLOYED_HEAD)
    parser.add_argument(
        "--expected-min-migrations",
        type=int,
        default=DEFAULT_EXPECTED_MIN_MIGRATIONS,
    )
    parser.add_argument(
        "--expected-release-latest-migration",
        default=RELEASE_EXPECTED_LATEST_MIGRATION,
    )
    parser.add_argument(
        "--expected-deploy-latest-migration",
        default=DEFAULT_EXPECTED_LATEST_MIGRATION,
    )
    parser.add_argument(
        "--expected-remote-migration-count",
        type=int,
        default=TOKYO_EXPECTED_MIGRATION_COUNT,
    )
    parser.add_argument(
        "--expected-remote-latest-migration",
        default=TOKYO_EXPECTED_LATEST_MIGRATION,
    )
    parser.add_argument("--output-dir", default="output/tokyo-runtime-governance-release")
    parser.add_argument("--connect-timeout-seconds", type=int, default=8)
    parser.add_argument("--active-positions", type=int, default=0)
    parser.add_argument(
        "--skip-remote-probe",
        action="store_true",
        help="Skip the Tokyo read-only probe. The evidence will not be deploy-ready.",
    )
    parser.add_argument(
        "--skip-pre-live-evidence",
        dest="skip_pre_live_evidence",
        action="store_true",
        help="Skip the pre-live submit evidence. The evidence will not be deploy-ready.",
    )
    return parser.parse_args(argv)


def _print_human(artifact: dict[str, Any]) -> None:
    checks = artifact["checks"]
    print(f"status={artifact['status']}")
    print(
        "ready_for_owner_deploy_decision="
        + str(checks["ready_for_owner_deploy_decision"]).lower()
    )
    print(f"candidate_head={artifact['candidate']['head']}")
    print(f"deploy_commands_planned={artifact['deploy_plan_summary']['commands_planned']}")
    print(f"deploy_confirmation_phrase={artifact['owner_gate']['deploy_confirmation_phrase']}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OwnerDeployArtifactError as exc:
        print(f"owner_deploy_artifact_error={exc}", file=sys.stderr)
        raise SystemExit(2)
