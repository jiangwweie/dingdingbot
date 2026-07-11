from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "90-resume-dispatcher-after-refresh.conf"
)
DRY_RUN_AUDIT_DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "60-dry-run-audit-chain.conf"
)
ACTION_TIME_DROPIN_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-signal-watcher.service.d"
    / "85-action-time-refresh-if-needed.conf"
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
RUNTIME_MONITOR_SERVICE_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-runtime-monitor.service"
)
TICKET_LIFECYCLE_MAINTENANCE_SERVICE_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-ticket-lifecycle-maintenance.service"
)
TICKET_LIFECYCLE_MAINTENANCE_TIMER_PATH = (
    REPO_ROOT
    / "deploy"
    / "systemd"
    / "brc-ticket-lifecycle-maintenance.timer"
)

def test_signal_watcher_service_observes_action_time_ticket_readiness_without_runtime_pin():
    text = SERVICE_PATH.read_text(encoding="utf-8")

    assert "--allow-prepare-records" not in text
    assert "--allow-action-time-ticket-materialization" not in text
    assert "Environment=BRC_SELECTED_STRATEGY_GROUP_ID=MPG-001" not in text
    assert "Environment=BRC_STRATEGYGROUP_MAX_SYMBOLS=3" in text
    assert "Environment=BRC_STRATEGYGROUP_STALE_AFTER_SECONDS=180" in text
    assert "EnvironmentFile=-/home/ubuntu/brc-deploy/env/runtime-order-capable.env" in text
    assert "EnvironmentFile=-/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env" in text
    assert "CPUQuota=60%" in text
    assert "Nice=10" in text
    assert "IOAccounting=true" in text
    assert "ExecStartPre=" in text
    assert "fetch_binance_usdm_public_facts.py" in text
    assert text.index("fetch_binance_usdm_public_facts.py") < text.index(
        "runtime_signal_watcher_tick.py"
    )
    assert "--require-database-url" in text
    assert "--candidate-universe-json" not in text
    assert "latest-strategy-live-candidate-pool.json" not in text
    for strategy_family_id in (
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    ):
        assert f"--strategy-family-id {strategy_family_id}" in text
    for support_only_strategy_family_id in ("TEQ-001", "FBS-001", "PMR-001"):
        assert f"--strategy-family-id {support_only_strategy_family_id}" not in text
    assert "--runtime-instance-id" not in text
    assert "build_runtime_signal_watcher_readiness_pack.py" not in text


def test_signal_watcher_dispatcher_dropin_uses_official_resume_path():
    text = DROPIN_PATH.read_text(encoding="utf-8")

    assert "runtime_signal_watcher_resume_dispatcher.py" in text
    assert "--identity-source pg_ticket" in text
    assert "post-signal-resume-pack.json" not in text
    assert "--resume-pack-json" not in text
    assert "--output-json" not in text
    assert "resume-dispatch-artifact.json" not in text
    assert "resume-dispatch-packet.json" not in text
    assert "--report-dir" not in text
    assert "--resume-dispatch-json" not in text
    assert "--owner-operator-id" not in text
    assert "--owner-confirmation-reference" not in text
    assert "--selected-strategy-group-id ${BRC_SELECTED_STRATEGY_GROUP_ID}" not in text
    assert "--execute-preflight" in text
    assert "--execute-operation-layer-submit" in text
    assert "--operation-layer-submit-mode from_submit_mode_decision" in text
    assert "--production-submit-execution-policy armed" in text
    assert "--operation-layer-submit-mode real_gateway_action" not in text
    assert "--execute-post-submit-finalize" not in text
    assert "OwnerBoundedExecution" not in text
    assert "withdrawal" not in text
    assert "transfer" not in text


def test_signal_watcher_timer_does_not_persistent_catch_up():
    timer_text = (
        REPO_ROOT / "deploy" / "systemd" / "brc-runtime-signal-watcher.timer"
    ).read_text(encoding="utf-8")

    assert "OnActiveSec=5min" in timer_text
    assert "OnBootSec=" not in timer_text
    assert "OnUnitActiveSec=10min" in timer_text
    assert "OnUnitActiveSec=60s" not in timer_text
    assert "Persistent=false" in timer_text
    assert "Persistent=true" not in timer_text


def test_signal_watcher_dry_run_audit_dropin_is_removed_from_production_tick():
    assert not DRY_RUN_AUDIT_DROPIN_PATH.exists()


def test_signal_watcher_action_time_dropin_runs_only_if_pg_triggered():
    text = ACTION_TIME_DROPIN_PATH.read_text(encoding="utf-8")

    assert "run_server_product_state_refresh_sequence.py" in text
    assert "--mode action_time_if_needed" in text
    assert "--report-dir /home/ubuntu/brc-deploy/reports/runtime-signal-watcher" not in text
    assert "--runtime-monitor-dir /home/ubuntu/brc-deploy/reports/runtime-monitor" not in text
    assert "server-action-time-refresh-sequence.json" not in text
    assert "runtime_dry_run_audit_chain.py" not in text
    assert "--resume-pack-json" not in text


def test_signal_watcher_goal_status_dropin_is_removed_from_repo():
    assert not GOAL_STATUS_DROPIN_PATH.exists()


def test_signal_watcher_product_state_dropin_refreshes_owner_console_readmodel():
    text = PRODUCT_STATE_DROPIN_PATH.read_text(encoding="utf-8")

    assert "run_server_product_state_refresh_sequence.py" in text
    assert "server-product-state-refresh-sequence.json" not in text
    assert "--report-dir /home/ubuntu/brc-deploy/reports/runtime-signal-watcher" not in text
    assert "--runtime-monitor-dir /home/ubuntu/brc-deploy/reports/runtime-monitor" not in text
    assert "--env-file /home/ubuntu/brc-deploy/env/live-readonly.env" not in text
    assert "--mode watcher_tick_summary" in text
    assert "/bin/sh -lc" not in text
    assert "set -eu;" not in text
    assert "build_strategygroup_runtime_goal_status.py" not in text
    assert "--refresh-goal-status" not in text
    assert "--goal-status-output-json" not in text
    assert "owner-console-source-readiness" not in text
    assert "FinalGate" in text
    assert "Operation" in text
    assert "exchange write" in text
    assert "withdrawals" in text
    assert "transfers" in text


def test_runtime_monitor_service_uses_pg_control_state_not_json_sources():
    text = RUNTIME_MONITOR_SERVICE_PATH.read_text(encoding="utf-8")

    assert "run_tokyo_runtime_server_monitor.py" in text
    assert "--require-database-url" in text
    assert "EnvironmentFile=/home/ubuntu/brc-deploy/env/live-readonly.env" in text
    assert "fetch_binance_usdm_public_facts.py" not in text
    assert "--daily-table-json" not in text
    assert "--candidate-pool-json" not in text
    assert "--public-facts-json" not in text
    assert "--account-safe-facts-json" not in text
    assert "--watcher-status-json" not in text
    assert "--deploy-health-json" not in text
    assert "--dedupe-state-json" not in text
    assert "ReadWritePaths=/home/ubuntu/brc-deploy/reports/runtime-monitor" not in text
    assert "FinalGate" not in text
    assert "Operation Layer" not in text
    assert "exchange write" not in text
    assert "withdrawal" not in text
    assert "transfer" not in text


def test_runtime_db_retention_systemd_units_are_not_shipped():
    assert not (REPO_ROOT / "deploy" / "systemd" / "brc-runtime-db-retention.service").exists()
    assert not (REPO_ROOT / "deploy" / "systemd" / "brc-runtime-db-retention.timer").exists()


def test_ticket_lifecycle_maintenance_timer_is_bounded_and_report_free():
    service_text = TICKET_LIFECYCLE_MAINTENANCE_SERVICE_PATH.read_text(encoding="utf-8")
    timer_text = TICKET_LIFECYCLE_MAINTENANCE_TIMER_PATH.read_text(encoding="utf-8")

    assert "run_ticket_bound_lifecycle_maintenance_once.py" in service_text
    assert "--require-database-url" in service_text
    assert "--allow-exchange-mutation" not in service_text
    assert "--max-lifecycle-scopes 1" in service_text
    assert "EnvironmentFile=/home/ubuntu/brc-deploy/env/live-readonly.env" in service_text
    assert "EnvironmentFile=-/home/ubuntu/brc-deploy/env/runtime-order-capable.env" in service_text
    assert "--report-dir" not in service_text
    assert "--output-json" not in service_text
    assert "ReadWritePaths=" not in service_text
    assert "TimeoutStartSec=35s" in service_text
    assert "--global-deadline-seconds 28" in service_text
    assert "CPUQuota=40%" in service_text
    assert "OnUnitActiveSec=30s" in timer_text
    assert "Persistent=false" in timer_text
    assert "Persistent=true" not in timer_text


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
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/test",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/test.tmp",
        release_manifest=(
            "/home/ubuntu/brc-deploy/releases/test/.brc-release-manifest.json"
        ),
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
            "2026-07-05-087_harden_live_signal_event_time_authority.py"
        ),
        target_migration_count=90,
        remote_migration_revision="081",
        target_migration_revision="087",
        migration_gap_revision_count=6,
        manifest_payload={"scope": "test"},
    )

    commands = "\n".join(
        command for phase in phases for command in phase["commands"]
    )
    quiesce_command = next(
        phase["commands"][0]
        for phase in phases
        if phase["phase"] == "3_quiesce_and_migrate"
    )
    switch_command = next(
        phase["commands"][0]
        for phase in phases
        if phase["phase"] == "4_switch_start_and_smoke"
    )
    assert "brc-runtime-signal-watcher.service" in commands
    assert "brc-runtime-signal-watcher.timer" in commands
    assert "brc-runtime-monitor.service" in commands
    assert "brc-runtime-monitor.timer" in commands
    assert "brc-ticket-lifecycle-maintenance.service" in commands
    assert "brc-ticket-lifecycle-maintenance.timer" in commands
    assert "90-resume-dispatcher-after-refresh.conf" in commands
    assert "40-resume-dispatcher.conf" in commands
    assert "60-dry-run-audit-chain.conf" in commands
    assert re.search(r"cp [^;]*60-dry-run-audit-chain\.conf", commands) is None
    assert "70-goal-status.conf" in commands
    assert re.search(r"cp [^;]*70-goal-status\.conf", commands) is None
    assert "80-product-state-refresh.conf" in commands
    assert "85-action-time-refresh-if-needed.conf" in commands
    assert "30-strategygroup-runtime-pilot-scope.conf" in commands
    assert "50-product-state-refresh.conf" in commands
    assert "rm -f" in commands
    assert "systemctl daemon-reload" in commands
    assert "brc-runtime-signal-watcher.timer" in commands
    assert "systemctl enable --now" in commands
    assert "systemctl enable --now brc-runtime-signal-watcher.timer" not in commands
    assert "systemctl enable brc-runtime-signal-watcher.timer" in commands
    assert "systemctl start brc-runtime-signal-watcher.timer" in commands
    assert "systemctl is-active brc-runtime-signal-watcher.timer" in commands
    assert "systemctl restart brc-runtime-signal-watcher.timer" not in commands
    assert "for attempt in $(seq 1 15)" in switch_command
    assert "curl --connect-timeout 1 --max-time 1 -fsS" in switch_command
    assert "timeout 30 sudo -n systemctl stop brc-runtime-signal-watcher.timer" in (
        quiesce_command
    )
    assert "timeout 30 sudo -n systemctl stop brc-runtime-monitor.timer" in (
        quiesce_command
    )
    assert "timeout 30 sudo -n systemctl stop brc-ticket-lifecycle-maintenance.timer" in (
        quiesce_command
    )
    assert "timeout 60 sudo -n systemctl stop brc-runtime-signal-watcher.service" in (
        quiesce_command
    )
    assert "timeout 60 sudo -n systemctl stop brc-runtime-monitor.service" in (
        quiesce_command
    )
    assert (
        "timeout 60 sudo -n systemctl stop brc-ticket-lifecycle-maintenance.service"
        in quiesce_command
    )
    assert "timeout 60 sudo -n systemctl stop brc-owner-console-backend.service" in (
        quiesce_command
    )
    assert (
        quiesce_command.index("systemctl stop brc-runtime-signal-watcher.timer")
        < quiesce_command.index("systemctl stop brc-runtime-monitor.timer")
        < quiesce_command.index("systemctl stop brc-ticket-lifecycle-maintenance.timer")
        < quiesce_command.index("systemctl stop brc-runtime-signal-watcher.service")
        < quiesce_command.index("systemctl stop brc-runtime-monitor.service")
        < quiesce_command.index("systemctl stop brc-ticket-lifecycle-maintenance.service")
        < quiesce_command.index("systemctl stop brc-owner-console-backend.service")
    )
    assert (
        switch_command.index('test "$HEALTH_READY" = 1')
        < switch_command.index("systemctl start brc-runtime-signal-watcher.timer")
        < switch_command.index("systemctl is-active brc-runtime-signal-watcher.timer")
    )
    assert "systemctl start brc-runtime-monitor.service" in commands
    assert "systemctl enable --now brc-ticket-lifecycle-maintenance.timer" in commands
    assert "systemctl restart brc-ticket-lifecycle-maintenance.timer" in commands
    assert "systemctl disable --now brc-runtime-db-retention.timer" in commands
    assert "systemctl enable --now brc-runtime-db-retention.timer" not in commands
    assert "tokyo-deploy-channel-status.json" not in commands
    assert "latest-deploy-health.json" not in commands
    assert "/home/ubuntu/brc-deploy/reports" not in commands
    assert "pg_dump" not in commands
