from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_tokyo_runtime_governance_owner_deploy_policy_artifact.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_tokyo_runtime_governance_owner_deploy_policy_artifact",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _release_report() -> dict:
    return {
        "status": "ready_for_local_packaging",
        "local_git": {
            "branch": "release/tokyo-runtime-governance-20260610",
            "head": "current-head",
            "short_head": "currenth",
        },
        "tokyo_baseline": {
            "deployed_head": "deployed-head",
            "deployed_head_is_ancestor": True,
            "commits_ahead_of_deployed": 20,
        },
        "migrations": {
            "count": 70,
            "latest": "2026-06-10-070_add_execution_intent_local_orders_registered_status.py",
        },
        "release_checks": {
            "ready_for_packaging": True,
            "blockers": [],
            "warnings": ["untracked_files_exist_and_are_not_in_git_archive"],
        },
        "safety_invariants": {
            "ssh_called": False,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "secrets_read": False,
        },
    }


def _deploy_plan() -> dict:
    return {
        "status": "ready_for_owner_authorized_remote_deploy_plan",
        "release": {
            "remote_release_path": "/home/ubuntu/brc-deploy/releases/currenth",
            "backup_path": "/home/ubuntu/brc-deploy/backups/currenth.pgdump",
        },
        "checks": {
            "ready_for_owner_authorized_remote_deploy": True,
            "blockers": [],
            "warnings": [],
            "remote_mutation_requires_confirmation_phrase": (
                "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
            ),
        },
        "plan_phases": [
            {"phase": "0_local_preflight", "commands": ["local"], "remote_mutation": False},
            {
                "phase": "2_owner_authorized_upload_and_extract",
                "commands": ["remote"],
                "remote_mutation": True,
                "requires_confirmation_phrase": (
                    "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
                ),
            },
        ],
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


def _dry_run() -> dict:
    return {
        "status": "dry_run_ready",
        "apply_requested": False,
        "checks": {
            "commands_planned": 2,
            "commands_executed": 0,
            "blockers": [],
        },
        "effects": {
            "remote_files_modified": False,
            "database_backup_created": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "secrets_read_by_codex": False,
        },
    }


def _tokyo_probe() -> dict:
    return {
        "status": "ready_for_controlled_deploy_preflight",
        "facts": {
            "current_head": "deployed-head",
            "migration_count": "64",
            "latest_migration": "2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
            "health": {
                "body_json": {
                    "status": "ok",
                    "runtime_bound": True,
                    "live_ready": False,
                }
            },
        },
        "checks": {
            "ready_for_controlled_deploy_preflight": True,
            "blockers": [],
            "warnings": ["remote_release_identity_from_manifest_without_git_status"],
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


def _pre_live_evidence() -> dict:
    return {
        "status": "blocked_before_first_real_submit",
        "checks": {
            "technical_rehearsal_passed": True,
            "registration_draft_chain_passed": True,
            "ready_for_first_real_submit": False,
            "technical_blockers": [],
            "implementation_blockers": [
                "runtime_not_live_execution_enabled",
                "order_lifecycle_adapter_disabled",
            ],
            "forbidden_execution_flags": [],
        },
        "safety_invariants": {
            "attempt_consumed": False,
            "database_connected": False,
            "exchange_called": False,
            "execution_intent_status_changed": False,
            "migrations_run": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "owner_bounded_execution_called": False,
            "persistent_runtime_budget_mutated": False,
            "remote_files_modified": False,
            "runtime_budget_mutated": False,
            "runtime_started": False,
            "services_restarted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _build_artifact(**overrides):
    module = _load_module()
    kwargs = {
        "release_report": _release_report(),
        "deploy_plan": _deploy_plan(),
        "deploy_dry_run": _dry_run(),
        "tokyo_probe": _tokyo_probe(),
        "pre_live_evidence": _pre_live_evidence(),
        "archive_path": Path("/tmp/release.tar.gz"),
        "manifest_path": Path("/tmp/release-readiness-manifest.json"),
    }
    kwargs.update(overrides)
    return module.build_owner_deploy_artifact(**kwargs)


def test_owner_deploy_artifact_ready_only_for_deploy_decision():
    artifact = _build_artifact()

    assert artifact["status"] == "ready_for_owner_deploy_decision"
    assert artifact["checks"]["ready_for_owner_deploy_decision"] is True
    assert artifact["checks"]["first_real_submit_still_blocked"] is True
    assert artifact["checks"]["forbidden_effects"] == []
    assert artifact["owner_gate"]["deploy_confirmation_phrase"] == (
        "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
    )


def test_owner_deploy_artifact_human_output_reads_artifact(capsys):
    module = _load_module()
    artifact = _build_artifact()

    module._print_human(artifact)

    output = capsys.readouterr().out
    assert "status=ready_for_owner_deploy_decision" in output
    assert "ready_for_owner_deploy_decision=true" in output
    assert "candidate_head=current-head" in output
    assert "deploy_commands_planned=2" in output
    assert (
        "deploy_confirmation_phrase=OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
        in output
    )
    assert artifact["owner_gate"]["deploy_confirmation_phrase_required"] is False
    assert artifact["owner_gate"]["deploy_apply_authorized_by"]
    assert "real runtime submit" in artifact["owner_gate"]["does_not_authorize"]
    assert artifact["safety_invariants"]["deploy_apply_requested"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_owner_deploy_artifact_blocks_if_dry_run_would_have_side_effects():
    dry_run = _dry_run()
    dry_run["status"] = "applied"
    dry_run["apply_requested"] = True
    dry_run["checks"]["commands_executed"] = 2
    dry_run["effects"]["remote_files_modified"] = True

    artifact = _build_artifact(deploy_dry_run=dry_run)

    assert artifact["status"] == "blocked"
    assert "deploy_executor_dry_run_not_ready" in artifact["checks"]["blockers"]
    assert "artifact_contains_forbidden_side_effect_flags" in artifact["checks"]["blockers"]
    assert "deploy_dry_run.remote_files_modified" in artifact["checks"]["forbidden_effects"]
    assert "deploy_dry_run.apply_requested" in artifact["checks"]["forbidden_effects"]


def test_owner_deploy_artifact_requires_remote_probe_but_allows_pre_live_skip():
    artifact = _build_artifact(tokyo_probe=None, pre_live_evidence=None)

    assert artifact["status"] == "blocked"
    assert "tokyo_readonly_probe_not_ready" in artifact["checks"]["blockers"]
    assert (
        "pre_live_submit_rehearsal_not_technically_ready"
        not in artifact["checks"]["blockers"]
    )
    assert artifact["checks"]["pre_live_evidence_skipped"] is True
    assert artifact["checks"]["pre_live_submit_technical_ready"] is True
    assert artifact["checks"]["first_real_submit_still_blocked"] is True
    assert "first_real_submit_not_confirmed_blocked" not in artifact["checks"]["blockers"]
    assert (
        "first_real_submit_not_a_deploy_apply_precondition"
        not in artifact["checks"]["warnings"]
    )
