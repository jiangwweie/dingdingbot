from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "execute_tokyo_runtime_governance_deploy.py"
PLAN_SCRIPT_PATH = REPO_ROOT / "scripts" / "plan_tokyo_runtime_governance_deploy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "execute_tokyo_runtime_governance_deploy",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_plan_module():
    spec = importlib.util.spec_from_file_location(
        "plan_tokyo_runtime_governance_deploy",
        PLAN_SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _ready_plan(tmp_path: Path) -> dict:
    plan_module = _load_plan_module()
    plan_module._tracked_dirty = lambda repo_root: False
    head = _git("rev-parse", "HEAD")
    archive = tmp_path / "brc-runtime-governance-test.tar.gz"
    archive.write_bytes(b"fake archive")
    manifest = tmp_path / "release-readiness-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "scope": "tokyo_runtime_governance_release_preparation",
                "local_git": {
                    "head": head,
                    "short_head": _git("rev-parse", "--short=8", "HEAD"),
                },
            }
        )
    )
    return plan_module.build_deploy_plan(
        repo_root=REPO_ROOT,
        archive_path=archive,
        manifest_path=manifest,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release=(
            "/home/ubuntu/brc-deploy/releases/"
            "brc-runtime-governance-ae9b209e-20260610T061250Z"
        ),
        expected_deployed_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        expected_remote_migration_count=79,
        expected_remote_latest_migration=(
            "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
        ),
        expected_latest_migration=(
            "2026-07-05-087_harden_live_signal_event_time_authority.py"
        ),
    )


def _owner_evidence_for_plan(plan: dict, *, head: str | None = None) -> dict:
    return {
        "status": "ready_for_owner_deploy_decision",
        "candidate": {
            "head": head or plan["release"]["head"],
            "archive_path": plan["inputs"]["archive_path"],
            "manifest_path": plan["inputs"]["manifest_path"],
        },
        "checks": {
            "ready_for_owner_deploy_decision": True,
            "first_real_submit_still_blocked": True,
            "forbidden_effects": [],
        },
        "owner_gate": {
            "deploy_confirmation_phrase": "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
            "deploy_confirmation_phrase_required": False,
        },
        "safety_invariants": {
            "deploy_apply_requested": False,
        },
    }


def _assert_archive_upload_blocked(report: dict, calls: list[str]) -> None:
    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert "archive_upload_deploy_forbidden_use_git_deploy" in report["checks"]["blockers"]
    assert report["effects"]["remote_files_modified"] is False
    assert report["effects"]["migrations_run"] is False
    assert report["effects"]["order_created"] is False
    assert report["effects"]["exchange_called"] is False
    assert calls == []


def test_archive_deploy_executor_blocks_dry_run_without_commands(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=False,
        confirmation_phrase=None,
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)
    assert report["apply_requested"] is False
    assert report["checks"]["commands_planned"] > 0
    assert report["planned_commands"]


def test_archive_deploy_executor_blocks_apply_with_standing_authorization(
    tmp_path: Path,
):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is False


def test_archive_deploy_executor_blocks_before_legacy_confirmation_gate(
    tmp_path: Path,
):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        require_confirmation_phrase=True,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    _assert_archive_upload_blocked(report, [])


def test_archive_deploy_executor_blocks_apply_without_owner_evidence(
    tmp_path: Path,
):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is False


def test_archive_deploy_executor_blocks_before_stale_owner_artifact_gate(
    tmp_path: Path,
):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan, head="stale-head"),
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    _assert_archive_upload_blocked(report, [])


def test_archive_deploy_executor_never_runs_fake_runner(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)


def test_archive_deploy_executor_blocks_before_command_failure_branch(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        if len(calls) == 2:
            return module.ShellResult(command, "", "boom", 1)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)


def test_archive_deploy_executor_blocks_before_remote_smoke_branch(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    def runner(command: str):
        if "HEALTH_URL=" in command:
            return module.ShellResult(command, "", "connection refused", 7)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=runner,
    )

    _assert_archive_upload_blocked(report, [])


def test_archive_deploy_executor_blocks_before_remote_mutation_phase_gate(
    tmp_path: Path,
):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    mutated_plan = {
        **plan,
        "plan_phases": [
            {
                "phase": "unsafe_remote_phase",
                "remote_mutation": True,
                "commands": ["ssh tokyo 'echo unsafe'"],
            }
        ],
    }
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        mutated_plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_artifact=_owner_evidence_for_plan(plan),
        runner=runner,
    )

    _assert_archive_upload_blocked(report, calls)
