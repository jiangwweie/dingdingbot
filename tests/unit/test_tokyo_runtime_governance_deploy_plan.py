from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "plan_tokyo_runtime_governance_deploy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "plan_tokyo_runtime_governance_deploy",
        SCRIPT_PATH,
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


def test_deploy_plan_requires_artifact_and_manifest():
    module = _load_module()

    report = module.build_deploy_plan(
        repo_root=REPO_ROOT,
        archive_path=None,
        manifest_path=None,
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
            "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
        ),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["ready_for_owner_authorized_remote_deploy"] is False
    assert "archive_path_required" in report["checks"]["blockers"]
    assert "manifest_path_required" in report["checks"]["blockers"]
    assert all(
        value is False
        for key, value in report["safety_invariants"].items()
        if key != "planning_run_only"
    )


def test_deploy_plan_builds_owner_gated_remote_mutation_commands(tmp_path: Path):
    module = _load_module()
    module._tracked_dirty = lambda repo_root: False
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

    report = module.build_deploy_plan(
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
        expected_remote_migration_count=85,
        expected_remote_latest_migration=(
            "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
        ),
        expected_latest_migration=(
            "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
        ),
    )

    assert report["status"] == "blocked"
    assert "archive_upload_deploy_forbidden_use_git_deploy" in report["checks"]["blockers"]
    assert report["checks"]["ready_for_owner_authorized_remote_deploy"] is False
    assert report["checks"]["remote_mutation_requires_confirmation_phrase"] == (
        "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
    )
    assert report["release"]["manifest_head"] == head
    assert report["release"]["remote_release_manifest_path"].endswith(
        "/.brc-release-manifest.json"
    )
    phases = {phase["phase"]: phase for phase in report["plan_phases"]}
    assert phases["0_local_preflight"]["remote_mutation"] is False
    assert phases["1_remote_preflight_readonly"]["remote_mutation"] is False
    assert phases["2_owner_authorized_upload_and_extract"]["remote_mutation"] is True
    assert phases["3_quiesce_backup_and_migrate"]["remote_mutation"] is True
    assert phases["4_switch_start_and_smoke"]["remote_mutation"] is True
    assert (
        "runtime submit pre-live registration draft chain does not pass"
        in phases["0_local_preflight"]["stop_if"]
    )
    assert all(
        phase.get("requires_confirmation_phrase")
        == "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
        for phase in report["plan_phases"]
        if phase["remote_mutation"]
    )
    all_commands = "\n".join(
        command
        for phase in report["plan_phases"]
        for command in phase["commands"]
    )
    assert "scp " in all_commands
    assert "pg_dump" in all_commands
    assert "PG_DATABASE_URL" in all_commands
    assert 'pg_dump "$DB_URL"' in all_commands
    assert "docker exec brc_prelive_pg_20260601" in all_commands
    assert "alembic upgrade head" in all_commands
    assert "ln -sfn" in all_commands
    assert "systemctl stop brc-owner-console-backend.service" in all_commands
    assert "systemctl start brc-owner-console-backend.service" in all_commands
    assert "--expected-current-head ae9b209e33cd287273491f2e93dfdff3b6a814fd" in all_commands
    assert "--deployed-head ae9b209e33cd287273491f2e93dfdff3b6a814fd" in all_commands
    assert "--expected-min-migrations 85" in all_commands
    assert "--expected-migration-count 85" in all_commands
    assert (
        "--expected-latest-migration "
        "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
    ) in all_commands
    assert "HEALTH_URL=http://127.0.0.1:18080/api/health" in all_commands
    assert "for attempt in $(seq 1 30)" in all_commands
    assert 'curl -fsS "$HEALTH_URL"' in all_commands
    assert "--base-revision 085 --head-revision 085" in all_commands
    assert "--expected-revision-count 0" in all_commands
    assert "verify_strategy_observation_shadow_planning_rehearsal.py --json" in all_commands
    assert "verify_runtime_submit_rehearsal_pre_live_evidence.py --json" in all_commands
    assert "--skip-current-head-deployed-check" in all_commands
    assert "--expected-current-head" in all_commands
    assert "verify_tokyo_runtime_governance_postdeploy.py" in all_commands


def test_deploy_plan_blocks_manifest_head_mismatch(tmp_path: Path):
    module = _load_module()
    module._tracked_dirty = lambda repo_root: False
    archive = tmp_path / "brc-runtime-governance-test.tar.gz"
    archive.write_bytes(b"fake archive")
    manifest = tmp_path / "release-readiness-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "scope": "tokyo_runtime_governance_release_preparation",
                "local_git": {
                    "head": "not-current-head",
                    "short_head": "notcur",
                },
            }
        )
    )

    report = module.build_deploy_plan(
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
            "2026-06-23-085_rename_live_lifecycle_owner_action_flag.py"
        ),
    )

    assert report["status"] == "blocked"
    assert "manifest_head_mismatch_current_head" in report["checks"]["blockers"]
