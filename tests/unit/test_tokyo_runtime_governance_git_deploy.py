from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "plan_tokyo_runtime_governance_git_deploy.py"
)
EXECUTE_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "execute_tokyo_runtime_governance_git_deploy.py"
)
PACKET_SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_tokyo_runtime_governance_git_owner_deploy_packet.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_plan_module():
    return _load_module(PLAN_SCRIPT_PATH, "plan_tokyo_runtime_governance_git_deploy")


def _load_execute_module():
    return _load_module(
        EXECUTE_SCRIPT_PATH,
        "execute_tokyo_runtime_governance_git_deploy",
    )


def _load_packet_module():
    return _load_module(
        PACKET_SCRIPT_PATH,
        "build_tokyo_runtime_governance_git_owner_deploy_packet",
    )


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


def _ready_git_plan():
    module = _load_plan_module()
    head = _git("rev-parse", "HEAD")
    module._tracked_dirty = lambda repo_root: False
    module._remote_branch_probe = (
        lambda *, repo_url, branch: module.RemoteBranchProbeResult(
            head=head,
            status="head_resolved",
            blocker=None,
            attempts=[
                {
                    "transport": "test",
                    "returncode": 0,
                    "stdout_tail": f"{head}\trefs/heads/{branch}",
                }
            ],
        )
    )
    return module.build_git_deploy_plan(
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit=head,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release="/home/ubuntu/brc-deploy/releases/current-baseline",
        expected_deployed_head="baseline-head",
        expected_remote_migration_count=76,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
    )


def _owner_packet_for_plan(plan: dict, *, head: str | None = None) -> dict:
    return {
        "status": "ready_for_owner_git_deploy_decision",
        "candidate": {
            "head": head or plan["release"]["head"],
            "repo_url": plan["inputs"]["repo_url"],
            "git_ref": plan["inputs"]["git_ref"],
        },
        "checks": {
            "ready_for_owner_git_deploy_decision": True,
            "first_real_submit_still_blocked": True,
            "forbidden_effects": [],
        },
        "owner_gate": {
            "deploy_confirmation_phrase": "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY",
            "deploy_confirmation_phrase_required": False,
        },
        "safety_invariants": {
            "deploy_apply_requested": False,
        },
    }


def _owner_deploy_packet_inputs() -> tuple[dict, dict, dict, dict]:
    plan = _ready_git_plan()
    deploy_dry_run = {
        "status": "dry_run_ready",
        "apply_requested": False,
        "checks": {"commands_executed": 0},
        "effects": {
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }
    release_report = {
        "release_checks": {
            "ready_for_packaging": True,
            "warnings": ["untracked_files_exist_and_are_not_in_git_archive"],
        },
        "local_git": {
            "branch": "release/test",
            "head": plan["release"]["head"],
            "short_head": plan["release"]["short_head"],
        },
        "migrations": {"count": 69},
        "tokyo_baseline": {"deployed_head_is_ancestor": True},
        "safety_invariants": {
            "remote_files_modified": False,
            "migrations_run": False,
            "order_created": False,
            "exchange_called": False,
        },
    }
    tokyo_probe = {
        "checks": {
            "ready_for_controlled_deploy_preflight": True,
            "warnings": ["remote_release_identity_from_manifest_without_git_status"],
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "migrations_run": False,
            "order_created": False,
            "exchange_called": False,
        },
    }
    return plan, deploy_dry_run, release_report, tokyo_probe


def test_git_deploy_plan_blocks_when_target_commit_is_not_remote_branch_head():
    module = _load_plan_module()
    head = _git("rev-parse", "HEAD")
    module._tracked_dirty = lambda repo_root: False
    module._remote_branch_probe = (
        lambda *, repo_url, branch: module.RemoteBranchProbeResult(
            head="remote-other-head",
            status="head_resolved",
            blocker=None,
            attempts=[
                {
                    "transport": "test",
                    "returncode": 0,
                    "stdout_tail": f"remote-other-head\trefs/heads/{branch}",
                }
            ],
        )
    )

    report = module.build_git_deploy_plan(
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit=head,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release="/home/ubuntu/brc-deploy/releases/current-baseline",
        expected_deployed_head="baseline-head",
        expected_remote_migration_count=76,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
    )

    assert report["status"] == "blocked"
    assert "target_commit_not_remote_branch_head" in report["checks"]["blockers"]
    assert report["checks"]["remote_ref_probe"]["status"] == "head_resolved"
    assert report["safety_invariants"]["ssh_called"] is False
    assert report["safety_invariants"]["remote_files_modified"] is False


def test_git_deploy_plan_classifies_remote_probe_network_failure():
    module = _load_plan_module()
    head = _git("rev-parse", "HEAD")
    module._tracked_dirty = lambda repo_root: False
    module._remote_branch_probe = (
        lambda *, repo_url, branch: module.RemoteBranchProbeResult(
            head=None,
            status="probe_failed",
            blocker="git_remote_probe_network_failed",
            attempts=[
                {
                    "transport": "default",
                    "returncode": 128,
                    "stdout_tail": (
                        "RPC failed; curl 92 HTTP/2 stream was not closed cleanly: "
                        "INTERNAL_ERROR"
                    ),
                },
                {
                    "transport": "http1",
                    "returncode": 128,
                    "stdout_tail": "fatal: unable to access repository",
                },
            ],
        )
    )

    report = module.build_git_deploy_plan(
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit=head,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python="/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python",
        api_base="http://127.0.0.1:18080",
        previous_release="/home/ubuntu/brc-deploy/releases/current-baseline",
        expected_deployed_head="baseline-head",
        expected_remote_migration_count=76,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
    )

    assert report["status"] == "blocked"
    assert "git_remote_probe_network_failed" in report["checks"]["blockers"]
    assert "target_git_ref_missing_on_remote" not in report["checks"]["blockers"]
    assert report["checks"]["remote_ref_probe"]["status"] == "probe_failed"


def test_remote_branch_probe_falls_back_to_http1():
    module = _load_plan_module()
    head = "1" * 40
    commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], *, cwd: Path):
        commands.append(command)
        if "-c" in command and "http.version=HTTP/1.1" in command:
            return module.CommandResult(
                stdout=f"{head}\trefs/heads/release/test",
                returncode=0,
            )
        return module.CommandResult(
            stdout=(
                "fatal: unable to access repository: "
                "Error in the HTTP2 framing layer"
            ),
            returncode=128,
        )

    module._run = fake_run

    result = module._remote_branch_probe(
        repo_url="https://github.com/example/dingdingbot.git",
        branch="release/test",
    )

    assert result.head == head
    assert result.status == "head_resolved"
    assert result.blocker is None
    assert [attempt["transport"] for attempt in result.attempts] == [
        "default",
        "retry",
        "http1",
    ]
    assert commands[-1][:4] == ("git", "-c", "http.version=HTTP/1.1", "ls-remote")


def test_git_deploy_default_ref_is_live_safe_program_branch():
    plan_module = _load_plan_module()
    packet_module = _load_packet_module()
    execute_module = _load_execute_module()

    assert plan_module.DEFAULT_GIT_REF == "program/live-safe-v1"
    assert packet_module.DEFAULT_GIT_REF == "program/live-safe-v1"
    assert execute_module.DEFAULT_GIT_REF == "program/live-safe-v1"


def test_git_deploy_plan_uses_remote_fetch_export_without_scp():
    report = _ready_git_plan()

    assert report["status"] == "ready_for_owner_authorized_remote_git_deploy_plan"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is False
    assert report["checks"]["remote_mutation_authorization"]
    assert report["inputs"]["target_migration_count"] == 84
    assert report["inputs"]["local_latest_migration"] == (
        "2026-06-11-084_create_runtime_post_submit_budget_settlements.py"
    )
    assert report["inputs"]["remote_migration_revision"] == "081"
    assert report["inputs"]["target_migration_revision"] == "084"
    assert report["inputs"]["migration_gap_revision_count"] == 8
    phases = {phase["phase"]: phase for phase in report["plan_phases"]}
    assert phases["2_owner_authorized_git_fetch_and_export"]["remote_mutation"] is True
    assert all(
        phase.get("requires_confirmation_phrase")
        == "OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY"
        for phase in report["plan_phases"]
        if phase["remote_mutation"]
    )
    assert all(
        phase.get("remote_mutation_authorization")
        == report["checks"]["remote_mutation_authorization"]
        for phase in report["plan_phases"]
        if phase["remote_mutation"]
    )
    all_commands = "\n".join(
        command
        for phase in report["plan_phases"]
        for command in phase["commands"]
    )
    assert "scp " not in all_commands
    assert "timeout 45 git ls-remote" in all_commands
    assert "git clone --no-checkout" in all_commands
    assert "git fetch --prune origin" in all_commands
    assert "git archive" in all_commands
    assert ".brc-release-manifest.json" in all_commands
    assert "tokyo-deploy-channel-status.json" in all_commands
    assert "tokyo_runtime_governance_deploy_channel_status" in all_commands
    assert '"status": "postdeploy_accepted"' in all_commands
    assert "alembic upgrade head" in all_commands
    assert "verify_tokyo_runtime_governance_postdeploy.py" in all_commands
    assert "--expected-min-migrations 84" in all_commands
    assert "--base-revision 081 --head-revision 084 --expected-revision-count 8" in all_commands
    assert "--expected-migration-count 84" in all_commands
    assert "--expected-migration-count 70" not in all_commands
    assert "--base-revision 064 --head-revision 070" not in all_commands


def test_git_deploy_plan_batches_tokyo_ssh_commands_to_reduce_server_interactions():
    report = _ready_git_plan()

    ssh_commands = [
        command
        for phase in report["plan_phases"]
        for command in phase["commands"]
        if command.startswith("ssh tokyo ")
    ]

    assert len(ssh_commands) == 4
    assert any(
        "systemctl stop brc-owner-console-backend.service" in command
        for command in ssh_commands
    )
    assert any(
        "pg_dump" in command and "alembic upgrade head" in command
        for command in ssh_commands
    )
    assert any(
        "systemctl start brc-owner-console-backend.service" in command
        for command in ssh_commands
    )
    assert any(
        "tokyo-deploy-channel-status.json" in command
        for command in ssh_commands
    )


def test_git_deploy_plan_allows_dirty_worktree_for_remote_git_export():
    module = _load_plan_module()
    head = _git("rev-parse", "HEAD")
    module._tracked_dirty = lambda repo_root: True
    module._remote_branch_probe = (
        lambda *, repo_url, branch: module.RemoteBranchProbeResult(
            head=head,
            status="head_resolved",
            blocker=None,
            attempts=[
                {
                    "transport": "test",
                    "returncode": 0,
                    "stdout_tail": f"{head}\trefs/heads/{branch}",
                }
            ],
        )
    )

    report = module.build_git_deploy_plan(
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit=head,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python=(
            "/home/ubuntu/brc-deploy/venvs/"
            "brc-bnb-prelive-20260601/bin/python"
        ),
        api_base="http://127.0.0.1:18080",
        previous_release="/home/ubuntu/brc-deploy/releases/current-baseline",
        expected_deployed_head="baseline-head",
        expected_remote_migration_count=76,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
    )

    assert report["status"] == "ready_for_owner_authorized_remote_git_deploy_plan"
    assert "tracked_worktree_dirty" not in report["checks"]["blockers"]
    assert (
        "tracked_worktree_dirty_remote_git_export_ignores_local_changes"
        in report["checks"]["warnings"]
    )
    all_commands = "\n".join(
        command
        for phase in report["plan_phases"]
        for command in phase["commands"]
    )
    assert "--allow-tracked-dirty-for-remote-git-export" in all_commands
    assert "git archive" in all_commands
    assert "scp " not in all_commands


def test_git_deploy_plan_expands_short_previous_release_for_current_symlink_check():
    module = _load_plan_module()
    head = _git("rev-parse", "HEAD")
    module._tracked_dirty = lambda repo_root: False
    module._remote_branch_probe = (
        lambda *, repo_url, branch: module.RemoteBranchProbeResult(
            head=head,
            status="head_resolved",
            blocker=None,
            attempts=[
                {
                    "transport": "test",
                    "returncode": 0,
                    "stdout_tail": f"{head}\trefs/heads/{branch}",
                }
            ],
        )
    )

    report = module.build_git_deploy_plan(
        repo_root=REPO_ROOT,
        repo_url="https://github.com/example/dingdingbot.git",
        git_ref="release/test",
        target_commit=head,
        release_name="brc-runtime-governance-test",
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        service_name="brc-owner-console-backend.service",
        env_path="/home/ubuntu/brc-deploy/env/live-readonly.env",
        venv_python=(
            "/home/ubuntu/brc-deploy/venvs/"
            "brc-bnb-prelive-20260601/bin/python"
        ),
        api_base="http://127.0.0.1:18080",
        previous_release="current-baseline",
        expected_deployed_head="baseline-head",
        expected_remote_migration_count=76,
        expected_remote_latest_migration=(
            "2026-06-11-081_create_llm_advisory_plane.py"
        ),
    )

    assert report["inputs"]["previous_release"] == "current-baseline"
    assert report["inputs"]["previous_release_path"] == (
        "/home/ubuntu/brc-deploy/releases/current-baseline"
    )
    export_phase = next(
        phase
        for phase in report["plan_phases"]
        if phase["phase"] == "2_owner_authorized_git_fetch_and_export"
    )
    command = export_phase["commands"][0]
    assert (
        "test $(readlink -f /home/ubuntu/brc-deploy/app/current) = "
        "/home/ubuntu/brc-deploy/releases/current-baseline"
    ) in command


def test_git_deploy_plan_health_wait_does_not_skip_post_health_steps():
    plan = _ready_git_plan()
    switch_phase = next(
        phase
        for phase in plan["plan_phases"]
        if phase["phase"] == "4_switch_start_and_smoke"
    )
    command = switch_phase["commands"][0]

    assert 'curl -fsS "$HEALTH_URL" 2>/dev/null && exit 0' not in command
    assert "HEALTH_READY=1; break" in command
    assert "systemctl daemon-reload" in command
    assert command.index("HEALTH_READY=1; break") < command.index(
        "systemctl daemon-reload"
    )


def test_git_deploy_executor_dry_run_does_not_execute_commands():
    module = _load_execute_module()
    plan = _ready_git_plan()
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_git_deploy_plan(
        plan,
        apply=False,
        confirmation_phrase=None,
        runner=runner,
    )

    assert report["status"] == "dry_run_ready"
    assert report["checks"]["commands_planned"] > 0
    assert report["checks"]["commands_executed"] == 0
    assert report["planned_commands"]
    assert calls == []
    assert report["effects"]["remote_files_modified"] is False
    assert report["effects"]["migrations_run"] is False
    assert report["interaction"]["level"] == "L1_deploy_plan_only"
    assert report["interaction"]["remote_interaction_count"] == 0
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["owner_summary"]["owner_intervention_required"] is False
    assert report["owner_summary"]["frontend_static_site"] == "not_included"
    assert report["owner_summary"]["postdeploy_snapshot_recommended"] is False


def test_git_deploy_executor_applies_with_standing_authorization_without_owner_packet():
    module = _load_execute_module()
    plan = _ready_git_plan()
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        runner=runner,
    )

    assert report["status"] == "applied"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is False
    assert report["checks"]["commands_executed"] == report["checks"]["commands_planned"]
    assert calls


def test_git_deploy_executor_can_require_legacy_confirmation_phrase():
    module = _load_execute_module()
    plan = _ready_git_plan()

    report = module.execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        require_confirmation_phrase=True,
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=lambda command: module.ShellResult(command, "ok", "", 0),
    )

    assert report["status"] == "blocked"
    assert report["checks"]["commands_executed"] == 0
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is True
    assert "owner_confirmation_phrase_missing_or_mismatch" in (
        report["checks"]["blockers"]
    )


def test_git_deploy_executor_apply_runs_commands_with_fake_runner():
    module = _load_execute_module()
    plan = _ready_git_plan()
    calls = []

    def runner(command: str):
        calls.append(command)
        return module.ShellResult(command, "ok", "", 0)

    report = module.execute_git_deploy_plan(
        plan,
        apply=True,
        confirmation_phrase=None,
        owner_deploy_packet=_owner_packet_for_plan(plan),
        runner=runner,
    )

    assert report["status"] == "applied"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["commands_executed"] == report["checks"]["commands_planned"]
    assert len(calls) == report["checks"]["commands_planned"]
    assert any("git fetch --prune origin" in command for command in calls)
    assert any("alembic upgrade head" in command for command in calls)
    assert report["effects"]["remote_files_modified"] is True
    assert report["effects"]["migrations_run"] is True
    assert report["effects"]["order_created"] is False
    assert report["checks"]["remote_mutation_confirmation_phrase_required"] is False
    assert report["interaction"]["level"] == "L3_bounded_deploy_apply"
    assert report["interaction"]["remote_interaction_count"] == 7
    assert report["interaction"]["mutates_remote_files"] is True
    assert report["interaction"]["approaches_real_order"] is False
    assert report["interaction"]["calls_operation_layer"] is False
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["owner_summary"]["state"] == "部署完成"
    assert report["owner_summary"]["changed"]["remote_files"] is True
    assert report["owner_summary"]["changed"]["services_restarted"] is True
    assert report["owner_summary"]["not_changed"]["exchange_orders"] is True
    assert report["owner_summary"]["frontend_static_site"] == "not_included"
    assert report["owner_summary"]["postdeploy_snapshot_recommended"] is True
    assert report["owner_summary"]["safety"]["order_created"] is False


def test_git_owner_deploy_packet_requires_ready_git_plan_and_blocked_real_submit():
    module = _load_packet_module()
    plan = _ready_git_plan()
    deploy_dry_run = {
        "status": "dry_run_ready",
        "apply_requested": False,
        "checks": {"commands_executed": 0},
        "effects": {
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }
    release_report = {
        "release_checks": {
            "ready_for_packaging": True,
            "warnings": ["untracked_files_exist_and_are_not_in_git_archive"],
        },
        "local_git": {
            "branch": "release/test",
            "head": plan["release"]["head"],
            "short_head": plan["release"]["short_head"],
        },
        "migrations": {"count": 69},
        "tokyo_baseline": {"deployed_head_is_ancestor": True},
        "safety_invariants": {
            "remote_files_modified": False,
            "migrations_run": False,
            "order_created": False,
            "exchange_called": False,
        },
    }
    tokyo_probe = {
        "checks": {
            "ready_for_controlled_deploy_preflight": True,
            "warnings": ["remote_release_identity_from_manifest_without_git_status"],
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "migrations_run": False,
            "order_created": False,
            "exchange_called": False,
        },
    }
    pre_live_packet = {
        "status": "blocked_before_first_real_submit",
        "checks": {
            "technical_rehearsal_passed": True,
            "registration_draft_chain_passed": True,
            "ready_for_first_real_submit": False,
            "forbidden_execution_flags": [],
        },
        "safety_invariants": {
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }

    packet = module.build_git_owner_deploy_packet(
        release_report=release_report,
        deploy_plan=plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_packet=pre_live_packet,
    )

    assert packet["status"] == "ready_for_owner_git_deploy_decision"
    assert packet["checks"]["ready_for_owner_git_deploy_decision"] is True
    assert packet["checks"]["first_real_submit_still_blocked"] is True
    assert packet["checks"]["forbidden_effects"] == []
    assert packet["candidate"]["repo_url"] == plan["inputs"]["repo_url"]
    assert packet["candidate"]["git_ref"] == plan["inputs"]["git_ref"]
    assert packet["owner_gate"]["deploy_confirmation_phrase_required"] is False
    assert packet["owner_gate"]["deploy_apply_authorized_by"]
    assert "real runtime submit" in (
        packet["owner_gate"]["deploy_confirmation_does_not_authorize"]
    )


def test_git_owner_deploy_packet_can_skip_pre_live_packet_for_deploy_only():
    module = _load_packet_module()
    plan, deploy_dry_run, release_report, tokyo_probe = (
        _owner_deploy_packet_inputs()
    )

    packet = module.build_git_owner_deploy_packet(
        release_report=release_report,
        deploy_plan=plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_packet=None,
    )

    assert packet["status"] == "ready_for_owner_git_deploy_decision"
    assert packet["checks"]["ready_for_owner_git_deploy_decision"] is True
    assert packet["checks"]["pre_live_packet_skipped"] is True
    assert packet["checks"]["first_real_submit_still_blocked"] is True
    assert "pre_live_packet_skipped_for_deploy_only" in packet["checks"]["warnings"]


def test_git_owner_deploy_packet_surfaces_tokyo_connectivity_blocker():
    module = _load_packet_module()
    plan, deploy_dry_run, release_report, _tokyo_probe = (
        _owner_deploy_packet_inputs()
    )
    connectivity_probe = {
        "status": "blocked",
        "checks": {
            "dns_resolved": True,
            "tcp_ports_reachable": False,
            "blockers": ["tokyo_tcp_22_unreachable"],
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }
    tokyo_probe = {
        "status": "blocked",
        "checks": {
            "ready_for_controlled_deploy_preflight": False,
            "blockers": [
                "tokyo_readonly_probe_error",
                "tokyo_tcp_22_unreachable",
            ],
            "warnings": [],
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
        },
    }

    packet = module.build_git_owner_deploy_packet(
        release_report=release_report,
        deploy_plan=plan,
        deploy_dry_run=deploy_dry_run,
        tokyo_probe=tokyo_probe,
        pre_live_packet=None,
        connectivity_probe=connectivity_probe,
    )

    assert packet["status"] == "blocked"
    assert "tokyo_readonly_probe_not_ready" in packet["checks"]["blockers"]
    assert (
        "tokyo_probe:tokyo_readonly_probe_error" in packet["checks"]["blockers"]
    )
    assert (
        "tokyo_connectivity:tokyo_tcp_22_unreachable"
        in packet["checks"]["blockers"]
    )
    assert packet["checks"]["tokyo_connectivity_probe_ready"] is False
    assert packet["checks"]["tokyo_connectivity_blockers"] == [
        "tokyo_tcp_22_unreachable"
    ]
    assert packet["safety_invariants"]["deploy_apply_requested"] is False


def test_git_deploy_executor_allows_deploy_only_packet_when_pre_live_skipped():
    module = _load_execute_module()
    plan = _ready_git_plan()
    packet = _owner_packet_for_plan(plan)
    packet["checks"]["first_real_submit_still_blocked"] = False
    packet["checks"]["pre_live_packet_skipped"] = True

    blockers = module._owner_deploy_packet_blockers(plan, packet)

    assert "owner_git_deploy_packet_first_real_submit_not_blocked" not in blockers
