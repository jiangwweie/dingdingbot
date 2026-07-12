from __future__ import annotations

from scripts.plan_tokyo_runtime_governance_git_deploy import (
    action_time_capability_certification_command,
    ticket_lifecycle_pre_switch_readiness_command,
    ticket_lifecycle_phase_two_enable_command,
    ticket_lifecycle_quiesce_and_migrate_command,
)


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


def test_phase_two_deploy_is_pg_gated_and_rolls_back_capability_on_failure():
    command = ticket_lifecycle_phase_two_enable_command(
        remote_release_path="/home/ubuntu/brc-deploy/releases/release-1",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/venv/bin/python",
        certification_ref="tokyo-release:abc123",
    )

    assert "verify_ticket_lifecycle_phase_two_readiness.py" in command
    assert "build_runtime_account_safe_facts.py" in command
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
    assert "no_maintainable_lifecycle" in command
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
