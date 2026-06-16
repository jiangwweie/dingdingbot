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
DRY_RUN_AUDIT_DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "60-dry-run-audit-chain.conf"
)
GOAL_STATUS_DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "70-goal-status.conf"
)
PRODUCT_STATE_DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "80-product-state-refresh.conf"
)
SERVICE_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service"
)


def test_signal_watcher_service_allows_non_executing_prepare_without_runtime_pin():
    text = SERVICE_PATH.read_text(encoding="utf-8")

    assert "--allow-prepare-records" in text
    assert "Environment=BRC_SELECTED_STRATEGY_GROUP_ID=MPG-001" in text
    assert "Environment=BRC_STRATEGYGROUP_MAX_SYMBOLS=3" in text
    assert "Environment=BRC_STRATEGYGROUP_STALE_AFTER_SECONDS=180" in text
    assert "EnvironmentFile=-/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env" in text
    for strategy_family_id in ("MPG-001", "TEQ-001", "FBS-001", "PMR-001", "SOR-001"):
        assert f"--strategy-family-id {strategy_family_id}" in text
    assert "--runtime-instance-id" not in text


def test_signal_watcher_dispatcher_dropin_uses_official_resume_path():
    text = DROPIN_PATH.read_text(encoding="utf-8")

    assert "runtime_signal_watcher_resume_dispatcher.py" in text
    assert "--selected-strategy-group-id ${BRC_SELECTED_STRATEGY_GROUP_ID}" in text
    assert "--execute-preflight" in text
    assert "--execute-operation-layer-submit" in text
    assert "--execute-post-submit-finalize" in text
    assert "OwnerBoundedExecution" not in text
    assert "withdrawal" not in text
    assert "transfer" not in text


def test_signal_watcher_dry_run_audit_dropin_is_non_executing():
    text = DRY_RUN_AUDIT_DROPIN_PATH.read_text(encoding="utf-8")

    assert "runtime_dry_run_audit_chain.py" in text
    assert "runtime-dry-run-audit-chain.json" in text
    assert "exchange write" in text
    assert "withdrawals" in text
    assert "transfers" in text


def test_signal_watcher_goal_status_dropin_is_read_only_summary():
    text = GOAL_STATUS_DROPIN_PATH.read_text(encoding="utf-8")

    assert "build_strategygroup_runtime_goal_status.py" in text
    assert "strategygroup-runtime-goal-status.json" in text
    assert "FinalGate" in text
    assert "Operation" in text
    assert "exchange write" in text
    assert "withdrawals" in text
    assert "transfers" in text


def test_signal_watcher_product_state_dropin_refreshes_owner_console_readmodel():
    text = PRODUCT_STATE_DROPIN_PATH.read_text(encoding="utf-8")

    assert "refresh_strategygroup_runtime_product_state_packets.py" in text
    assert "--collect-live-facts-before-refresh" in text
    assert "--live-facts-output" in text
    assert "strategy-group-live-facts-input.json" in text
    assert "product-state-refresh-packet.json" in text
    assert "owner-console-source-readiness" not in text
    assert "FinalGate" in text
    assert "Operation" in text
    assert "exchange write" in text
    assert "withdrawals" in text
    assert "transfers" in text


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
    assert "brc-runtime-signal-watcher.service" in commands
    assert "brc-runtime-signal-watcher.timer" in commands
    assert "40-resume-dispatcher.conf" in commands
    assert "60-dry-run-audit-chain.conf" in commands
    assert "70-goal-status.conf" in commands
    assert "80-product-state-refresh.conf" in commands
    assert "30-strategygroup-runtime-pilot-scope.conf" in commands
    assert "50-product-state-refresh.conf" in commands
    assert "rm -f" in commands
    assert "systemctl daemon-reload" in commands
    assert "brc-runtime-signal-watcher.timer" in commands
    assert "systemctl enable --now" in commands
