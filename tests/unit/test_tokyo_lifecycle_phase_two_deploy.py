from __future__ import annotations

from scripts.plan_tokyo_runtime_governance_git_deploy import (
    ticket_lifecycle_phase_two_enable_command,
)


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
