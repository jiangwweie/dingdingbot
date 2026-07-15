from __future__ import annotations

from scripts.execute_tokyo_runtime_governance_git_deploy import (
    ShellResult,
    execute_git_deploy_plan,
)
from src.domain.standing_authorization import OWNER_STANDING_AUTHORIZATION_REFERENCE


def test_post_mutation_failure_engages_persistent_writer_fence():
    calls: list[str] = []

    def runner(command: str) -> ShellResult:
        calls.append(command)
        if command == "post-switch-smoke":
            return ShellResult(command, "", "boom", 1)
        return ShellResult(command, "", "", 0)

    plan = {
        "checks": {
            "blockers": [],
            "remote_mutation_requires_confirmation_phrase": (
                "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
            ),
        },
        "inputs": {"host": "tokyo"},
        "release": {"remote_release_path": "/candidate"},
        "plan_phases": [
            {
                "phase": "3_quiesce_and_migrate",
                "remote_mutation": True,
                "remote_mutation_authorization": OWNER_STANDING_AUTHORIZATION_REFERENCE,
                "requires_confirmation_phrase": "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
                "commands": ["post-switch-smoke"],
            }
        ],
    }

    report = execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
    )

    assert report["status"] == "failed_contained"
    assert report["checks"]["writers_left_disabled"] is True
    assert any(
        "systemctl stop brc-runtime-signal-watcher.timer" in command
        for command in calls
    )
    assert any(
        "set_ticket_lifecycle_mutation_capability.py --disable" in command
        for command in calls
    )
