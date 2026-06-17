from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_SCRIPT_PATH = REPO_ROOT / "scripts" / "probe_tokyo_runtime_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "probe_tokyo_runtime_snapshot",
        SNAPSHOT_SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _healthy_remote_payload(*, frontend_release: dict | None = None) -> dict:
    return {
        "collector_status": "ok",
        "hostname": "VM-0-11-ubuntu",
        "release": {
            "current_realpath": "/home/ubuntu/brc-deploy/releases/current",
            "manifest": {"head": "runtime-head"},
            "head": "runtime-head",
        },
        "systemd": {
            "brc-runtime-signal-watcher.timer": {
                "active": "active",
                "enabled": "enabled",
            },
            "brc-runtime-signal-watcher.service": {
                "active": "inactive",
                "enabled": "static",
            },
            "brc-owner-console-backend.service": {
                "active": "active",
                "enabled": "enabled",
            },
            "nginx.service": {"active": "active", "enabled": "enabled"},
        },
        "frontend": {
            "root": "/var/www/brc-owner-console",
            "nginx_root": "/var/www/brc-owner-console",
            "index_exists": True,
            "release_exists": frontend_release is not None,
            "release": frontend_release,
        },
        "reports": {
            "owner-console-source-readiness.json": {
                "exists": True,
                "payload": {
                    "status": "ready",
                    "owner_state": "等待机会",
                },
            },
            "strategygroup-runtime-goal-status.json": {
                "exists": True,
                "payload": {
                    "status": "waiting_for_signal",
                    "deployment_aligned": True,
                    "watcher_liveness_healthy": True,
                    "fresh_signal_present": False,
                    "ready_for_real_order_action": False,
                },
            },
            "runtime-dry-run-audit-chain.json": {
                "exists": True,
                "payload": {
                    "status": "passed",
                    "scenario_count": 13,
                    "checks": {"scenario_count": 13},
                },
            },
            "latest-summary.json": {
                "exists": True,
                "payload": {"status": "waiting_for_signal"},
            },
            "watcher-tick.json": {
                "exists": True,
                "payload": {"status": "no_action"},
            },
        },
    }


def test_tokyo_runtime_snapshot_collects_all_facts_with_one_ssh_call():
    module = _load_module()
    calls = []

    def runner(command: tuple[str, ...]):
        calls.append(command)
        return module.CommandResult(
            stdout=json.dumps(_healthy_remote_payload()),
            stderr="",
            returncode=0,
        )

    report = module.build_tokyo_runtime_snapshot(
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        report_dir="/home/ubuntu/brc-deploy/reports/runtime-signal-watcher",
        frontend_root="/var/www/brc-owner-console",
        expected_runtime_head="runtime-head",
        expected_frontend_head=None,
        runner=runner,
    )

    assert len(calls) == 1
    assert calls[0][0] == "ssh"
    assert report["interaction"]["level"] == "L1_readonly_snapshot"
    assert report["interaction"]["remote_interaction_count"] == 1
    assert report["interaction"]["mutates_remote_files"] is False
    assert report["interaction"]["approaches_real_order"] is False
    assert report["interaction"]["calls_exchange_write"] is False
    assert report["status"] == "product_gap"
    assert report["checks"]["blockers"] == []
    assert report["checks"]["product_gaps"] == ["frontend_release_missing"]
    assert report["owner_summary"]["state"] == "等待机会"
    assert report["owner_summary"]["owner_intervention_required"] is False


def test_tokyo_runtime_snapshot_accepts_current_frontend_release():
    module = _load_module()

    def runner(command: tuple[str, ...]):
        return module.CommandResult(
            stdout=json.dumps(
                _healthy_remote_payload(frontend_release={"head": "frontend-head"})
            ),
            stderr="",
            returncode=0,
        )

    report = module.build_tokyo_runtime_snapshot(
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        report_dir="/home/ubuntu/brc-deploy/reports/runtime-signal-watcher",
        frontend_root="/var/www/brc-owner-console",
        expected_runtime_head="runtime-head",
        expected_frontend_head="frontend-head",
        runner=runner,
    )

    assert report["status"] == "ready"
    assert report["checks"]["product_gaps"] == []
    assert report["checks"]["frontend_release_present"] is True
    assert report["owner_summary"]["frontend"] == "已发布"
    assert report["safety_invariants"]["remote_files_modified"] is False
    assert report["safety_invariants"]["order_created"] is False
    assert report["safety_invariants"]["exchange_write_called"] is False


def test_tokyo_runtime_snapshot_reads_head_from_release_manifest_local_git():
    module = _load_module()
    payload = _healthy_remote_payload(frontend_release={"head": "frontend-head"})
    payload["release"] = {
        "current_realpath": "/home/ubuntu/brc-deploy/releases/current",
        "manifest": {
            "scope": "tokyo_runtime_governance_git_release",
            "local_git": {"head": "nested-runtime-head"},
        },
        "head": None,
    }

    def runner(command: tuple[str, ...]):
        return module.CommandResult(
            stdout=json.dumps(payload),
            stderr="",
            returncode=0,
        )

    report = module.build_tokyo_runtime_snapshot(
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        report_dir="/home/ubuntu/brc-deploy/reports/runtime-signal-watcher",
        frontend_root="/var/www/brc-owner-console",
        expected_runtime_head="nested-runtime-head",
        expected_frontend_head="frontend-head",
        runner=runner,
    )

    assert report["status"] == "ready"
    assert report["facts"]["release"]["head"] == "nested-runtime-head"
    assert report["checks"]["runtime_head_matches_expected"] is True


def test_tokyo_runtime_snapshot_blocks_on_runtime_liveness_failure():
    module = _load_module()
    payload = _healthy_remote_payload(frontend_release={"head": "frontend-head"})
    payload["systemd"]["brc-owner-console-backend.service"]["active"] = "inactive"

    def runner(command: tuple[str, ...]):
        return module.CommandResult(
            stdout=json.dumps(payload),
            stderr="",
            returncode=0,
        )

    report = module.build_tokyo_runtime_snapshot(
        host="tokyo",
        deploy_root="/home/ubuntu/brc-deploy",
        report_dir="/home/ubuntu/brc-deploy/reports/runtime-signal-watcher",
        frontend_root="/var/www/brc-owner-console",
        expected_runtime_head="runtime-head",
        expected_frontend_head="frontend-head",
        runner=runner,
    )

    assert report["status"] == "blocked"
    assert "owner_console_backend_inactive" in report["checks"]["blockers"]
    assert report["owner_summary"]["state"] == "暂不可用"
    assert report["owner_summary"]["owner_intervention_required"] is True
