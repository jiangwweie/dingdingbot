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
        expected_latest_migration=(
            "2026-06-10-069_allow_adapter_registration_failure_results.py"
        ),
    )


def _owner_packet_for_plan(plan: dict, *, head: str | None = None) -> dict:
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
        },
        "safety_invariants": {
            "deploy_apply_requested": False,
        },
    }


def test_deploy_executor_dry_run_does_not_execute_commands(tmp_path: Path):
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

    assert report["status"] == "dry_run_ready"
    assert report["apply_requested"] is False
    assert report["checks"]["blockers"] == []
    assert report["checks"]["commands_planned"] > 0
    assert report["checks"]["commands_executed"] == 0
    assert report["planned_commands"]
    assert calls == []
    assert report["effects"]["remote_files_modified"] is False
    assert report["effects"]["migrations_run"] is False


def test_deploy_executor_blocks_apply_without_exact_confirmation(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase="wrong",
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert "owner_confirmation_phrase_missing_or_mismatch" in report["checks"]["blockers"]
    assert report["effects"]["remote_files_modified"] is False


def test_deploy_executor_blocks_apply_without_owner_deploy_packet(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert report["checks"]["blockers"] == ["owner_deploy_decision_packet_required"]
    assert report["effects"]["remote_files_modified"] is False


def test_deploy_executor_blocks_apply_with_stale_owner_deploy_packet(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        owner_deploy_packet=_owner_packet_for_plan(plan, head="stale-head"),
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert "owner_deploy_packet_head_mismatch" in report["checks"]["blockers"]
    assert report["effects"]["remote_files_modified"] is False


def test_deploy_executor_apply_runs_commands_with_fake_runner(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=runner,
    )

    assert report["status"] == "applied"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["commands_executed"] == report["checks"]["commands_planned"]
    assert len(calls) == report["checks"]["commands_planned"]
    assert any("alembic upgrade head" in command for command in calls)
    assert any("verify_tokyo_runtime_governance_postdeploy.py" in command for command in calls)
    assert report["effects"]["remote_files_modified"] is True
    assert report["effects"]["migrations_run"] is True
    assert report["effects"]["order_created"] is False
    assert report["effects"]["exchange_called"] is False


def test_deploy_executor_stops_on_failed_command(tmp_path: Path):
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
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=runner,
    )

    assert report["status"] == "failed"
    assert report["checks"]["commands_executed"] == 2
    assert report["checks"]["blockers"] == ["command_failed:0_local_preflight"]
    assert report["command_results"][-1]["stderr_tail"] == "boom"


def test_deploy_executor_failed_remote_smoke_reports_partial_effects(tmp_path: Path):
    module = _load_module()
    plan = _ready_plan(tmp_path)

    def runner(command: str):
        if "HEALTH_URL=" in command:
            return module.ShellResult(command, "", "connection refused", 7)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=runner,
    )

    assert report["status"] == "failed"
    assert report["checks"]["blockers"] == ["command_failed:4_switch_start_and_smoke"]
    assert report["effects"]["remote_files_modified"] is True
    assert report["effects"]["database_backup_created"] is True
    assert report["effects"]["migrations_run"] is True
    assert report["effects"]["services_restarted"] is True
    assert report["effects"]["order_created"] is False
    assert report["effects"]["exchange_called"] is False


def test_deploy_executor_blocks_remote_mutation_phase_without_gate(tmp_path: Path):
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
        confirmation_phrase="OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=runner,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert report["checks"]["blockers"] == [
        "remote_mutation_phase_missing_confirmation_gate:unsafe_remote_phase"
    ]
    assert calls == []
