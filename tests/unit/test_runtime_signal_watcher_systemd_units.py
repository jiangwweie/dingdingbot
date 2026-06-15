from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "40-resume-dispatcher.conf"
)


def test_signal_watcher_dispatcher_dropin_uses_official_resume_path():
    text = DROPIN_PATH.read_text(encoding="utf-8")

    assert "runtime_signal_watcher_resume_dispatcher.py" in text
    assert "--execute-preflight" in text
    assert "--execute-operation-layer-submit" in text
    assert "--execute-post-submit-finalize" in text
    assert "OwnerBoundedExecution" not in text
    assert "withdrawal" not in text
    assert "transfer" not in text


def test_git_deploy_plan_installs_signal_watcher_dispatcher_dropin():
    from scripts.plan_tokyo_runtime_governance_git_deploy import (
        _plan_phases,
    )

    phases = _plan_phases(
        host="tokyo",
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit="abc123",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        reports_dir="/home/ubuntu/brc-deploy/reports/test",
        backups_dir="/home/ubuntu/brc-deploy/backups",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/test",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/test.tmp",
        release_manifest=(
            "/home/ubuntu/brc-deploy/releases/test/.brc-release-manifest.json"
        ),
        backup_path="/home/ubuntu/brc-deploy/backups/test.pgdump",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python=(
            "/home/ubuntu/brc-deploy/venvs/"
            "brc-bnb-prelive-20260601/bin/python"
        ),
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/current-baseline",
        expected_deployed_head="baseline",
        expected_remote_migration_count=81,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
        expected_latest_migration=(
            "2026-06-11-084_create_runtime_post_submit_budget_settlements.py"
        ),
        target_migration_count=84,
        remote_migration_revision="081",
        target_migration_revision="084",
        migration_gap_revision_count=3,
        manifest_payload={"scope": "test"},
    )

    commands = "\n".join(
        command for phase in phases for command in phase["commands"]
    )
    assert "40-resume-dispatcher.conf" in commands
    assert "systemctl daemon-reload" in commands
    assert "brc-runtime-signal-watcher.timer" in commands
    assert "systemctl enable --now" in commands
