from __future__ import annotations

from scripts.execute_tokyo_runtime_governance_git_deploy import (
    ShellResult,
    build_remote_state_machine_invocation,
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


def test_remote_state_machine_invocation_is_one_bounded_transient_service(tmp_path):
    script = tmp_path / "tokyo_runtime_deploy_remote_state_machine.py"
    script.write_text("print('verified bootstrap')\n", encoding="utf-8")
    plan = {
        "repo_root": str(tmp_path),
        "inputs": {
            "host": "tokyo",
            "deploy_root": "/home/ubuntu/brc-deploy",
            "repo_url": "https://example.invalid/repo.git",
            "git_ref": "codex/release",
            "target_commit": "a" * 40,
            "release_name": "brc-runtime-governance-a1",
            "service_name": "brc-owner-console-backend.service",
            "env_path": "/home/ubuntu/brc-deploy/env/live-readonly.env",
            "previous_release_path": "/home/ubuntu/brc-deploy/releases/old",
            "expected_latest_migration": "2026-07-15-124_x.py",
        },
        "release": {
            "remote_release_path": "/home/ubuntu/brc-deploy/releases/new",
        },
    }

    invocation = build_remote_state_machine_invocation(
        plan,
        transaction_id="a1b2c3d4",
        deploy_nonce="nonce-a1b2c3d4",
        bootstrap_path=script,
    )

    command = invocation["command"]
    assert command.count("ssh tokyo") == 1
    assert "sudo -n /usr/bin/systemd-run" in command
    assert "--wait --pipe --collect --service-type=exec" in command
    assert "--unit=brc-deploy-a1b2c3d4.service" in command
    assert "KillMode=control-group" in command
    assert "RuntimeMaxSec=60min" in command
    assert "/usr/bin/python3 -c" in command
    assert str(script) in command
    assert command.rstrip().endswith("< " + str(script))
    assert invocation["transaction_id"] == "a1b2c3d4"
    assert invocation["deploy_nonce"] == "nonce-a1b2c3d4"
    assert len(invocation["bootstrap_sha256"]) == 64


def test_executor_prints_identity_then_runs_exactly_one_remote_mutation(
    tmp_path, capsys
):
    script = tmp_path / "scripts/tokyo_runtime_deploy_remote_state_machine.py"
    script.parent.mkdir()
    script.write_text("print('bootstrap')\n", encoding="utf-8")
    calls = []

    def runner(command: str) -> ShellResult:
        calls.append(command)
        return ShellResult(
            command=command,
            stdout='{"status":"tokyo_runtime_deploy_applied"}',
            stderr="",
            returncode=0,
        )

    plan = {
        "repo_root": str(tmp_path),
        "checks": {
            "blockers": [],
            "remote_mutation_requires_confirmation_phrase": (
                "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
            ),
        },
        "inputs": {
            "host": "tokyo",
            "deploy_root": "/home/ubuntu/brc-deploy",
            "repo_url": "https://example.invalid/repo.git",
            "git_ref": "codex/release",
            "target_commit": "a" * 40,
            "release_name": "candidate",
            "service_name": "brc-owner-console-backend.service",
            "env_path": "/home/ubuntu/brc-deploy/env/live-readonly.env",
            "previous_release_path": "/home/ubuntu/brc-deploy/releases/old",
            "expected_deployed_head": "b" * 40,
            "expected_latest_migration": "2026-07-15-124_x.py",
        },
        "release": {"head": "a" * 40, "release_name": "candidate"},
        "plan_phases": [
            {
                "phase": "2_single_remote_deploy_transaction",
                "remote_mutation": True,
                "remote_state_machine": True,
                "remote_mutation_authorization": OWNER_STANDING_AUTHORIZATION_REFERENCE,
                "commands": [],
            }
        ],
    }

    report = execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
    )

    identity = capsys.readouterr().out
    assert "deploy_transaction_resolved" in identity
    assert len(calls) == 1
    assert calls[0].count("ssh tokyo") == 1
    assert "systemd-run" in calls[0]
    assert report["status"] == "applied"


def test_executor_resumes_exact_transaction_identity(tmp_path):
    script = tmp_path / "scripts/tokyo_runtime_deploy_remote_state_machine.py"
    script.parent.mkdir()
    script.write_text("print('bootstrap')\n", encoding="utf-8")
    calls = []

    def runner(command: str) -> ShellResult:
        calls.append(command)
        return ShellResult(command, '{"status":"tokyo_runtime_deploy_applied"}', "", 0)

    plan = {
        "repo_root": str(tmp_path),
        "checks": {"blockers": []},
        "inputs": {
            "host": "tokyo", "target_commit": "a" * 40,
            "expected_deployed_head": "b" * 40,
        },
        "release": {"head": "a" * 40},
        "plan_phases": [{
            "phase": "2_single_remote_deploy_transaction",
            "remote_mutation": True,
            "remote_state_machine": True,
            "remote_mutation_authorization": OWNER_STANDING_AUTHORIZATION_REFERENCE,
        }],
    }

    execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
        transaction_id="deadbeef",
        deploy_nonce="resume-nonce",
    )

    assert len(calls) == 1
    assert "--transaction-id deadbeef" in calls[0]
    assert "--deploy-nonce resume-nonce" in calls[0]


def test_executor_resume_skips_only_old_runtime_health_probe(tmp_path):
    script = tmp_path / "scripts/tokyo_runtime_deploy_remote_state_machine.py"
    script.parent.mkdir()
    script.write_text("print('bootstrap')\n", encoding="utf-8")
    calls = []

    def runner(command: str) -> ShellResult:
        calls.append(command)
        return ShellResult(command, '{"status":"ok"}', "", 0)

    plan = {
        "repo_root": str(tmp_path),
        "checks": {"blockers": []},
        "inputs": {
            "host": "tokyo", "target_commit": "a" * 40,
            "expected_deployed_head": "b" * 40,
        },
        "release": {"head": "a" * 40},
        "plan_phases": [
            {
                "phase": "1_remote_preflight_readonly",
                "remote_mutation": False,
                "commands": [
                    "python3 scripts/probe_tokyo_runtime_governance_readonly.py --json",
                    "ssh tokyo 'git ls-remote origin'",
                    "ssh tokyo 'test -f runtime-order-capable.env'",
                ],
            },
            {
                "phase": "2_single_remote_deploy_transaction",
                "remote_mutation": True,
                "remote_state_machine": True,
                "remote_mutation_authorization": OWNER_STANDING_AUTHORIZATION_REFERENCE,
            },
        ],
    }

    report = execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
        transaction_id="deadbeef",
        deploy_nonce="resume-nonce",
    )

    assert report["status"] == "applied"
    assert not any("probe_tokyo_runtime_governance_readonly.py" in call for call in calls)
    assert any("git ls-remote" in call for call in calls)
    assert any("runtime-order-capable.env" in call for call in calls)
    assert any("--transaction-id deadbeef" in call for call in calls)
