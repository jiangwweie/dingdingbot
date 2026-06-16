from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "probe_tokyo_runtime_governance_readonly.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "probe_tokyo_runtime_governance_readonly",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ready_facts() -> dict:
    return {
        "host": "VM-0-11-ubuntu",
        "user": "ubuntu",
        "current_realpath": (
            "/home/ubuntu/brc-deploy/releases/"
            "brc-runtime-governance-ae9b209e-20260610T061250Z"
        ),
        "current_head": "ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        "current_status": "## HEAD (no branch)",
        "migration_count": "64",
        "latest_migration": "2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
        "health": {
            "http_status": 200,
            "body": (
                '{"status":"ok","service":"brc_operator_console",'
                '"runtime_bound":true,"live_ready":false}'
            ),
            "body_json": {
                "status": "ok",
                "service": "brc_operator_console",
                "runtime_bound": True,
                "live_ready": False,
            },
        },
        "process_snapshot": (
            "2518668 1 ubuntu python "
            "/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/"
            "bin/python -m src.main\n"
            "19125 19104 70 postgres postgres"
        ),
    }


def test_tokyo_probe_checks_ready_remote_predeploy_baseline():
    module = _load_module()

    checks = module.evaluate_probe_checks(
        facts=_ready_facts(),
        expected_current_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        expected_migration_count=64,
        expected_latest_migration="2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
    )

    assert checks["ready_for_controlled_deploy_preflight"] is True
    assert checks["blockers"] == []
    assert checks["warnings"] == []
    assert checks["dirty_status_lines"] == []


def test_tokyo_probe_blocks_dirty_remote_release_and_live_ready_health():
    module = _load_module()
    facts = _ready_facts()
    facts.update(
        {
            "current_status": "## HEAD (no branch)\n M src/interfaces/api.py",
            "health": {
                "http_status": 200,
                "body": '{"status":"ok","runtime_bound":true,"live_ready":true}',
                "body_json": {
                    "status": "ok",
                    "runtime_bound": True,
                    "live_ready": True,
                },
            },
        }
    )

    checks = module.evaluate_probe_checks(
        facts=facts,
        expected_current_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        expected_migration_count=64,
        expected_latest_migration="2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
    )

    assert checks["ready_for_controlled_deploy_preflight"] is False
    assert "remote_current_release_worktree_dirty" in checks["blockers"]
    assert "remote_health_live_ready_true_before_controlled_deploy" in checks["blockers"]
    assert checks["dirty_status_lines"] == [" M src/interfaces/api.py"]


def test_tokyo_probe_blocks_unexpected_remote_head_and_schema_drift():
    module = _load_module()
    facts = _ready_facts()
    facts.update(
        {
            "current_head": "unexpected",
            "migration_count": "63",
            "latest_migration": "2026-06-10-063_create_strategy_runtime_promotion_confirmations.py",
        }
    )

    checks = module.evaluate_probe_checks(
        facts=facts,
        expected_current_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        expected_migration_count=64,
        expected_latest_migration="2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
    )

    assert checks["ready_for_controlled_deploy_preflight"] is False
    assert "remote_current_head_mismatch" in checks["blockers"]
    assert "remote_migration_count_mismatch" in checks["blockers"]
    assert "remote_latest_migration_mismatch" in checks["blockers"]


def test_tokyo_connectivity_probe_classifies_tcp_unreachable_without_side_effects():
    module = _load_module()

    def connector(host: str, port: int, timeout: float) -> None:
        raise TimeoutError("timed out")

    report = module.build_tokyo_connectivity_probe(
        host="54.199.90.212",
        ports=(22,),
        connect_timeout_seconds=1,
        connector=connector,
    )

    assert report["status"] == "blocked"
    assert report["checks"]["dns_resolved"] is True
    assert report["checks"]["tcp_ports_reachable"] is False
    assert report["checks"]["blockers"] == ["tokyo_tcp_22_unreachable"]
    assert report["facts"]["ports"]["22"]["reachable"] is False
    assert all(value is False for value in report["safety_invariants"].values())


def test_tokyo_connectivity_probe_classifies_reachable_tcp_port():
    module = _load_module()
    calls: list[tuple[str, int, float]] = []

    def connector(host: str, port: int, timeout: float) -> None:
        calls.append((host, port, timeout))

    report = module.build_tokyo_connectivity_probe(
        host="127.0.0.1",
        ports=(22,),
        connect_timeout_seconds=2,
        connector=connector,
    )

    assert report["status"] == "ready"
    assert report["checks"]["blockers"] == []
    assert report["facts"]["ports"]["22"]["reachable"] is True
    assert calls == [("127.0.0.1", 22, 2.0)]


def test_tokyo_probe_builds_report_with_fake_runner_and_home_expanding_paths():
    module = _load_module()
    commands = []

    def runner(command):
        commands.append(command)
        remote = command[-1]
        if remote == "set -eu; hostname":
            return module.CommandResult("VM-0-11-ubuntu\n", "", 0)
        if remote == "set -eu; whoami":
            return module.CommandResult("ubuntu\n", "", 0)
        if "readlink -f" in remote:
            return module.CommandResult(
                "/home/ubuntu/brc-deploy/releases/"
                "brc-runtime-governance-ae9b209e-20260610T061250Z\n",
                "",
                0,
            )
        if "git rev-parse HEAD" in remote:
            return module.CommandResult(
                "ae9b209e33cd287273491f2e93dfdff3b6a814fd\n",
                "",
                0,
            )
        if "git status --short --branch" in remote:
            return module.CommandResult("## HEAD (no branch)\n", "", 0)
        if "wc -l" in remote:
            return module.CommandResult("64\n", "", 0)
        if "tail -1" in remote:
            return module.CommandResult(
                "2026-06-10-064_add_runtime_profile_proposal_snapshot.py\n",
                "",
                0,
            )
        if "curl -fsS" in remote:
            return module.CommandResult(
                '{"status":"ok","runtime_bound":true,"live_ready":false}'
                "\nHTTP_STATUS:200\n",
                "",
                0,
            )
        if "ps -eo" in remote:
            return module.CommandResult(
                "2518668 1 ubuntu python /venv/bin/python -m src.main\n"
                "19125 19104 70 postgres postgres\n",
                "",
                0,
            )
        raise AssertionError(f"unexpected command: {remote}")

    report = module.build_tokyo_probe_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head="ae9b209e33cd287273491f2e93dfdff3b6a814fd",
        expected_migration_count=64,
        expected_latest_migration="2026-06-10-064_add_runtime_profile_proposal_snapshot.py",
        connect_timeout_seconds=8,
        runner=runner,
    )

    assert report["status"] == "ready_for_controlled_deploy_preflight"
    assert report["checks"]["ready_for_controlled_deploy_preflight"] is True
    assert report["checks"]["blockers"] == []
    assert all(value is False for value in report["safety_invariants"].values())
    remote_commands = [command[-1] for command in commands]
    assert any(
        '"$HOME"/brc-deploy/app/current' in command
        for command in remote_commands
    )
    assert not any("'$HOME/" in command for command in remote_commands)


def test_tokyo_probe_accepts_git_archive_release_manifest_identity():
    module = _load_module()
    manifest = {
        "scope": "tokyo_runtime_governance_release_preparation",
        "generated_at_utc": "2026-06-10T04:57:41Z",
        "local_git": {
            "head": "a6f0a49f3d001e9294f49495281703aaa218adab",
            "short_head": "a6f0a49f",
        },
    }

    def runner(command):
        remote = command[-1]
        if remote == "set -eu; hostname":
            return module.CommandResult("VM-0-11-ubuntu\n", "", 0)
        if remote == "set -eu; whoami":
            return module.CommandResult("ubuntu\n", "", 0)
        if "readlink -f" in remote:
            return module.CommandResult(
                "/home/ubuntu/brc-deploy/releases/"
                "brc-runtime-governance-a6f0a49f-20260610T045741Z\n",
                "",
                0,
            )
        if "git rev-parse HEAD" in remote:
            return module.CommandResult("", "fatal: not a git repository\n", 128)
        if "cat .brc-release-manifest.json" in remote:
            return module.CommandResult(json.dumps(manifest), "", 0)
        if "wc -l" in remote:
            return module.CommandResult("64\n", "", 0)
        if "tail -1" in remote:
            return module.CommandResult(
                "2026-06-10-064_add_runtime_profile_proposal_snapshot.py\n",
                "",
                0,
            )
        if "curl -fsS" in remote:
            return module.CommandResult(
                '{"status":"ok","runtime_bound":true,"live_ready":false}'
                "\nHTTP_STATUS:200\n",
                "",
                0,
            )
        if "ps -eo" in remote:
            return module.CommandResult(
                "2518668 1 ubuntu python /venv/bin/python -m src.main\n"
                "19125 19104 70 postgres postgres\n",
                "",
                0,
            )
        raise AssertionError(f"unexpected command: {remote}")

    report = module.build_tokyo_probe_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head="a6f0a49f3d001e9294f49495281703aaa218adab",
        expected_migration_count=64,
        expected_latest_migration=(
            "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"
        ),
        connect_timeout_seconds=8,
        runner=runner,
    )

    assert report["status"] == "ready_for_controlled_deploy_preflight"
    assert report["facts"]["release_identity_source"] == "release_manifest"
    assert report["facts"]["current_head"] == (
        "a6f0a49f3d001e9294f49495281703aaa218adab"
    )
    assert report["facts"]["current_status"] == "release_manifest_without_git_status"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["dirty_status_lines"] == []
    assert report["checks"]["warnings"] == [
        "remote_release_identity_from_manifest_without_git_status"
    ]
