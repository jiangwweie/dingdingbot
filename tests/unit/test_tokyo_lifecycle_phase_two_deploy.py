from __future__ import annotations

from pathlib import Path

from scripts.plan_tokyo_runtime_governance_git_deploy import (
    DEFAULT_EXPECTED_LATEST_MIGRATION,
    _plan_phases,
    action_time_capability_certification_command,
    backend_runtime_identity_dropin_install_command,
    ticket_lifecycle_pre_switch_readiness_command,
    ticket_lifecycle_phase_two_enable_command,
    ticket_lifecycle_quiesce_and_migrate_command,
)


def test_deploy_plan_default_tracks_exit_policy_canary_migration():
    assert DEFAULT_EXPECTED_LATEST_MIGRATION == (
        "2026-07-15-123_activate_sor_long_exit_policy_canary.py"
    )


def test_backend_runtime_identity_dropin_is_repository_owned():
    dropin = (
        Path(__file__).resolve().parents[2]
        / "deploy/systemd/brc-owner-console-backend.service.d/30-runtime-order-capable-identity.conf"
    )

    text = dropin.read_text(encoding="utf-8")

    assert "EnvironmentFile=-/home/ubuntu/brc-deploy/env/runtime-order-capable.env" in text
    assert "BRC_RUNTIME_EXCHANGE_ACCOUNT_ID=" not in text
    assert "BRC_RUNTIME_EXCHANGE_ID=" not in text


def test_backend_identity_dropin_install_verifies_effective_process_environment():
    command = backend_runtime_identity_dropin_install_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-new",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
    )

    assert "30-runtime-order-capable-identity.conf" in command
    assert "systemctl daemon-reload" in command
    assert "runtime-order-capable.env" in command
    assert "systemctl cat brc-owner-console-backend.service" in command
    assert "BRC_RUNTIME_EXCHANGE_ACCOUNT_ID=" not in command


def test_full_phase_builder_propagates_release_name_into_activation_command(
    tmp_path,
) -> None:
    phases = _plan_phases(
        host="tokyo",
        repo_root=tmp_path,
        repo_url="https://example.invalid/repo.git",
        git_ref="codex/test",
        target_commit="a" * 40,
        release_name="brc-runtime-governance-full-plan",
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/new",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/new.tmp",
        release_manifest="/home/ubuntu/brc-deploy/releases/new/.brc-release-manifest.json",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/old",
        expected_deployed_head="b" * 40,
        expected_remote_migration_count=116,
        expected_remote_latest_migration="2026-07-12-116_example.py",
        expected_latest_migration="2026-07-12-116_example.py",
        target_migration_count=116,
        remote_migration_revision="116",
        target_migration_revision="116",
        migration_gap_revision_count=0,
        manifest_payload={"scope": "test"},
    )

    phase = next(
        item
        for item in phases
        if item["phase"] == "6_certify_action_time_capability_truth"
    )
    assert "--release-name brc-runtime-governance-full-plan" in phase["commands"][0]


def test_full_phase_builder_passes_runtime_venv_to_postdeploy_verifier(
    tmp_path,
) -> None:
    venv_python = "/home/ubuntu/brc-deploy/venvs/runtime/bin/python"
    phases = _plan_phases(
        host="tokyo",
        repo_root=tmp_path,
        repo_url="https://example.invalid/repo.git",
        git_ref="codex/test",
        target_commit="a" * 40,
        release_name="brc-runtime-governance-full-plan",
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/new",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/new.tmp",
        release_manifest="/home/ubuntu/brc-deploy/releases/new/.brc-release-manifest.json",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python=venv_python,
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/old",
        expected_deployed_head="b" * 40,
        expected_remote_migration_count=116,
        expected_remote_latest_migration="2026-07-12-116_example.py",
        expected_latest_migration="2026-07-12-116_example.py",
        target_migration_count=116,
        remote_migration_revision="116",
        target_migration_revision="116",
        migration_gap_revision_count=0,
        manifest_payload={"scope": "test"},
    )

    phase = next(
        item for item in phases if item["phase"] == "4_switch_start_and_smoke"
    )
    postdeploy_command = phase["commands"][2]

    assert f"--venv-python {venv_python}" in postdeploy_command


def test_remote_preflight_requires_explicit_runtime_gateway_identity(tmp_path):
    phases = _plan_phases(
        host="tokyo",
        repo_root=tmp_path,
        repo_url="https://example.invalid/repo.git",
        git_ref="codex/test",
        target_commit="a" * 40,
        release_name="brc-runtime-governance-full-plan",
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/new",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/new.tmp",
        release_manifest=(
            "/home/ubuntu/brc-deploy/releases/new/.brc-release-manifest.json"
        ),
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/old",
        expected_deployed_head="b" * 40,
        expected_remote_migration_count=116,
        expected_remote_latest_migration="2026-07-12-116_example.py",
        expected_latest_migration="2026-07-12-116_example.py",
        target_migration_count=116,
        remote_migration_revision="116",
        target_migration_revision="116",
        migration_gap_revision_count=0,
        manifest_payload={"scope": "test"},
    )

    phase = next(
        item
        for item in phases
        if item["phase"] == "1_remote_preflight_readonly"
    )
    commands = "\n".join(phase["commands"])

    assert "/home/ubuntu/brc-deploy/env/runtime-order-capable.env" in commands
    assert "BRC_RUNTIME_EXCHANGE_ACCOUNT_ID" in commands
    assert "BRC_RUNTIME_EXCHANGE_ID" in commands
    assert "binance_usdm" in commands


def test_switch_installs_backend_identity_before_backend_start(tmp_path):
    phases = _plan_phases(
        host="tokyo",
        repo_root=tmp_path,
        repo_url="https://example.invalid/repo.git",
        git_ref="codex/test",
        target_commit="a" * 40,
        release_name="brc-runtime-governance-full-plan",
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/new",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/new.tmp",
        release_manifest="/home/ubuntu/brc-deploy/releases/new/.brc-release-manifest.json",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/old",
        expected_deployed_head="b" * 40,
        expected_remote_migration_count=116,
        expected_remote_latest_migration="2026-07-12-116_example.py",
        expected_latest_migration="2026-07-12-116_example.py",
        target_migration_count=116,
        remote_migration_revision="116",
        target_migration_revision="116",
        migration_gap_revision_count=0,
        manifest_payload={"scope": "test"},
    )

    command = next(
        item for item in phases if item["phase"] == "4_switch_start_and_smoke"
    )["commands"][0]

    assert command.index("30-runtime-order-capable-identity.conf") < command.index(
        "systemctl start brc-owner-console-backend.service"
    )
    assert command.index("systemctl start brc-owner-console-backend.service") < (
        command.index("BRC_RUNTIME_EXCHANGE_ACCOUNT_ID")
    )
    assert "BRC_RUNTIME_EXCHANGE_ID" in command
    assert "cut -d= -f1" in command


def test_postdeploy_action_time_capability_runs_matrix_before_pg_certification_and_projection_publish():
    command = action_time_capability_certification_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-new",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        runtime_head="a" * 40,
        release_name="brc-runtime-governance-test",
    )

    matrix = (
        "test_six_event_specs_across_all_active_scopes_reach_disabled_smoke_"
        "from_production_shape"
    )
    assert matrix in command
    assert "timeout 300" in command
    assert "scripts/record_runtime_release_activation.py" in command
    assert "--release-name brc-runtime-governance-test" in command
    assert "scripts/certify_action_time_capability.py" in command
    assert "--runtime-head " + "a" * 40 in command
    assert "--certification-ref tokyo-release:" + "a" * 40 in command
    assert "scripts/publish_runtime_control_current_projections.py --json" in command
    assert command.index(matrix) < command.index(
        "scripts/record_runtime_release_activation.py"
    ) < command.index("scripts/certify_action_time_capability.py") < command.index(
        "scripts/publish_runtime_control_current_projections.py"
    )
    assert "exchange" not in command.lower()


def test_watcher_timer_starts_only_after_action_time_capability_truth_publish():
    phases = _plan_phases(
        host="tokyo",
        repo_root=Path("/tmp/repo"),
        repo_url="https://example.invalid/repo.git",
        git_ref="codex/test",
        target_commit="a" * 40,
        release_name="brc-runtime-governance-test",
        deploy_root="/home/ubuntu/brc-deploy",
        source_root="/home/ubuntu/brc-deploy/source",
        source_repo_path="/home/ubuntu/brc-deploy/source/dingdingbot",
        app_current="/home/ubuntu/brc-deploy/app/current",
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-new",
        remote_tmp_release_path="/home/ubuntu/brc-deploy/releases/release-new.tmp",
        release_manifest="/home/ubuntu/brc-deploy/releases/release-new/.brc-release-manifest.json",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release_path="/home/ubuntu/brc-deploy/releases/release-old",
        expected_deployed_head="b" * 40,
        expected_remote_migration_count=120,
        expected_remote_latest_migration="2026-07-13-120_example.py",
        expected_latest_migration="2026-07-13-120_example.py",
        target_migration_count=120,
        remote_migration_revision="120",
        target_migration_revision="120",
        migration_gap_revision_count=0,
        manifest_payload={"scope": "test"},
    )
    switch = next(
        item for item in phases if item["phase"] == "4_switch_start_and_smoke"
    )["commands"][0]
    phase_two = ticket_lifecycle_phase_two_enable_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-new",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        certification_ref="tokyo-release:" + "a" * 40,
    )
    certification = action_time_capability_certification_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-new",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/runtime/bin/python",
        runtime_head="a" * 40,
        release_name="brc-runtime-governance-test",
    )

    phase_two_success_tail = phase_two.split("SUCCESS=1; trap - EXIT", 1)[1]
    assert "systemctl start brc-runtime-signal-watcher.timer" not in switch
    assert (
        "systemctl start brc-runtime-signal-watcher.timer"
        not in phase_two_success_tail
    )
    assert "restore_watcher_timer" in certification
    assert "trap restore_watcher_timer EXIT" in certification
    assert certification.index(
        "scripts/publish_runtime_control_current_projections.py --json"
    ) < certification.rindex("systemctl start brc-runtime-signal-watcher.timer")


def test_phase_two_deploy_is_pg_gated_and_rolls_back_capability_on_failure():
    command = ticket_lifecycle_phase_two_enable_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-1",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/venv/bin/python",
        certification_ref="tokyo-release:abc123",
    )

    assert "verify_ticket_lifecycle_phase_two_readiness.py" in command
    assert "build_runtime_account_safe_facts.py" in command
    assert "/home/ubuntu/brc-deploy/env/runtime-order-capable.env" in command
    assert command.index("build_runtime_account_safe_facts.py") < command.index(
        "verify_ticket_lifecycle_phase_two_readiness.py"
    )
    assert "audit_production_runtime_file_io.py --json" in command
    assert "set_ticket_lifecycle_mutation_capability.py --enable" in command
    assert "set_ticket_lifecycle_mutation_capability.py --disable" in command
    assert "set_ticket_lifecycle_mutation_capability.py --status" in command
    assert "CAPABILITY_OUTPUT" in command
    assert "rollback_phase_two" in command
    assert "run_ticket_bound_lifecycle_maintenance_once.py" in command
    assert "scheduler_complete" in command
    assert "selected_scope_count" in command
    assert "exchange_write_called" in command
    assert command.index("verify_ticket_lifecycle_phase_two_readiness.py") < command.index(
        "set_ticket_lifecycle_mutation_capability.py --enable"
    )
    assert command.index("set_ticket_lifecycle_mutation_capability.py --enable") < (
        command.index("set_ticket_lifecycle_mutation_capability.py --status")
    )


def test_repeat_deploy_checks_enabled_capability_before_quiescing_it():
    pre_switch = ticket_lifecycle_pre_switch_readiness_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-2",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/venv/bin/python",
    )
    quiesce = ticket_lifecycle_quiesce_and_migrate_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-2",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/venv/bin/python",
        service_name="brc-owner-console-backend.service",
        certification_ref="deploy-quiesce:abc123",
    )

    assert "verify_ticket_lifecycle_phase_two_readiness.py" in pre_switch
    assert "--deploy-quiescence" in pre_switch
    assert "set_ticket_lifecycle_mutation_capability.py --disable" not in pre_switch
    assert "set_ticket_lifecycle_mutation_capability.py --enable" not in pre_switch
    assert "rollback_quiesce" in quiesce
    assert "CAPABILITY_WAS_ENABLED" in quiesce
    assert "--deploy-quiescence" in quiesce
    assert "set_ticket_lifecycle_mutation_capability.py --disable" in quiesce
    assert "set_ticket_lifecycle_mutation_capability.py --enable" in quiesce
    assert "deploy-quiesce:abc123" in quiesce
    assert quiesce.index("systemctl stop brc-owner-console-backend.service") < (
        quiesce.index("verify_ticket_lifecycle_phase_two_readiness.py")
    )
    assert quiesce.index("verify_ticket_lifecycle_phase_two_readiness.py") < (
        quiesce.index("set_ticket_lifecycle_mutation_capability.py --disable")
    )
    assert quiesce.index("set_ticket_lifecycle_mutation_capability.py --disable") < (
        quiesce.index("alembic upgrade head")
    )
