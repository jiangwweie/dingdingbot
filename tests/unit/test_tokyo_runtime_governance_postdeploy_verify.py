from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_tokyo_runtime_governance_postdeploy.py"
EXPECTED_HEAD = "0c350ca7d34db7d2db7c9ae2b99fa6c6e0ddcafe"
LATEST_MIGRATION = (
    "2026-06-10-070_add_execution_intent_local_orders_registered_status.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_tokyo_runtime_governance_postdeploy",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _json_response(payload: dict, status: int = 200):
    module = _load_module()
    return module.CommandResult(
        json.dumps(payload) + f"\nHTTP_STATUS:{status}\n",
        "",
        0,
    )


def _runner(*, live_ready: bool = False, generic_post_status: int = 405):
    module = _load_module()
    manifest = {
        "scope": "tokyo_runtime_governance_release_preparation",
        "generated_at_utc": "2026-06-10T05:07:28Z",
        "local_git": {"head": EXPECTED_HEAD, "short_head": "0c350ca7"},
    }

    def runner(command):
        remote = command[-1]
        if remote == "set -eu; hostname":
            return module.CommandResult("VM-0-11-ubuntu\n", "", 0)
        if "readlink -f" in remote:
            return module.CommandResult(
                "/home/ubuntu/brc-deploy/releases/"
                "brc-runtime-governance-0c350ca7-20260610T050728Z\n",
                "",
                0,
            )
        if "git rev-parse HEAD" in remote:
            return module.CommandResult("", "fatal: not a git repository\n", 128)
        if "cat .brc-release-manifest.json" in remote:
            return module.CommandResult(json.dumps(manifest), "", 0)
        if "wc -l" in remote:
            return module.CommandResult("70\n", "", 0)
        if "tail -1" in remote:
            return module.CommandResult(LATEST_MIGRATION + "\n", "", 0)
        if remote == "set -eu; systemctl is-enabled brc-ticket-lifecycle-maintenance.timer":
            return module.CommandResult("enabled\n", "", 0)
        if remote == "set -eu; systemctl is-active brc-ticket-lifecycle-maintenance.timer":
            return module.CommandResult("active\n", "", 0)
        if "systemctl show brc-ticket-lifecycle-maintenance.service" in remote:
            return module.CommandResult("success\n0\n", "", 0)
        if "cmp -s /etc/systemd/system/brc-ticket-lifecycle-maintenance.service" in remote:
            return module.CommandResult("match\n", "", 0)
        if "/api/health" in remote:
            return module.CommandResult(
                json.dumps(
                    {
                        "status": "ok",
                        "service": "brc_operator_console",
                        "runtime_bound": True,
                        "live_ready": live_ready,
                    }
                )
                + "\nHTTP_STATUS:200\n",
                "",
                0,
            )
        if "-X POST" in remote and "/api/trading-console/operations-cockpit" in remote:
            return module.CommandResult(
                '{"detail":"Method Not Allowed"}'
                f"\nHTTP_STATUS:{generic_post_status}\n",
                "",
                0,
            )
        if "/api/trading-console/" in remote or "/api/brc/" in remote:
            return module.CommandResult(
                '{"error_code":"401","message":"Operator login required"}'
                "\nHTTP_STATUS:401\n",
                "",
                0,
            )
        raise AssertionError(f"unexpected command: {remote}")

    return runner


def test_postdeploy_verifier_passes_archive_release_with_readonly_api_checks():
    module = _load_module()

    report = module.build_postdeploy_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head=EXPECTED_HEAD,
        expected_migration_count=70,
        expected_latest_migration=LATEST_MIGRATION,
        connect_timeout_seconds=8,
        runner=_runner(),
    )

    assert report["status"] == "postdeploy_acceptance_passed"
    assert report["checks"]["postdeploy_acceptance_passed"] is True
    assert report["checks"]["blockers"] == []
    assert report["checks"]["warnings"] == [
        "release_identity_from_manifest_without_git_status"
    ]
    assert report["facts"]["release_identity"]["source"] == "release_manifest"
    assert report["facts"]["release_identity_source"] == "release_manifest"
    assert report["facts"]["current_head"] == EXPECTED_HEAD
    assert len(report["facts"]["http_checks"]) == 17
    auth_checks = [
        item
        for item in report["facts"]["http_checks"]
        if item["method"] == "GET"
        and (
            item["url"].startswith("http://127.0.0.1:18080/api/trading-console/")
            or item["url"].startswith("http://127.0.0.1:18080/api/brc/")
        )
    ]
    assert auth_checks
    assert all(item["expected_status"] == 401 for item in auth_checks)
    assert all(item["http_status"] == 401 for item in auth_checks)
    scheduled_post = next(
        item
        for item in report["facts"]["http_checks"]
        if item["name"] == "trading_console_scheduled_observation_run_requires_auth"
    )
    assert scheduled_post["method"] == "POST"
    assert scheduled_post["expected_status"] == 401
    assert scheduled_post["http_status"] == 401
    runtime_write_checks = [
        item
        for item in report["facts"]["http_checks"]
        if item["name"]
        in {
            "runtime_execution_recorded_intent_write_requires_auth",
            "runtime_execution_attempt_mutation_write_requires_auth",
            "runtime_execution_controlled_submit_write_requires_auth",
        }
    ]
    assert len(runtime_write_checks) == 3
    assert all(item["method"] == "POST" for item in runtime_write_checks)
    assert all(item["expected_status"] == 401 for item in runtime_write_checks)
    assert all(item["http_status"] == 401 for item in runtime_write_checks)
    assert all(value is False for value in report["safety_invariants"].values())


def test_postdeploy_http_check_retries_only_transport_failure_inside_one_ssh_call():
    module = _load_module()
    commands = []

    def runner(command):
        commands.append(command)
        return module.CommandResult(
            '{"error_code":"401"}\nHTTP_STATUS:401\n',
            "",
            0,
        )

    result = module._remote_http(
        "tokyo",
        method="GET",
        url="http://127.0.0.1:18080/api/example",
        expected_status=401,
        expect_json=True,
        name="bounded_retry",
        connect_timeout_seconds=8,
        runner=runner,
    )

    remote_command = commands[0][-1]
    assert "for attempt in 1 2 3" in remote_command
    assert "sleep 1" in remote_command
    assert "curl -sS -m 8" in remote_command
    assert result["http_status"] == 401
    assert result["body_json"] == {"error_code": "401"}


def test_postdeploy_verifier_defaults_track_current_stage_migration_head():
    module = _load_module()

    assert module.DEFAULT_EXPECTED_MIGRATION_COUNT == 117
    assert module.DEFAULT_EXPECTED_LATEST_MIGRATION == (
        "2026-07-12-117_extend_owner_notifications.py"
    )


def test_postdeploy_verifier_blocks_live_ready_true_and_unblocked_generic_post():
    module = _load_module()

    report = module.build_postdeploy_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head=EXPECTED_HEAD,
        expected_migration_count=70,
        expected_latest_migration=LATEST_MIGRATION,
        connect_timeout_seconds=8,
        runner=_runner(live_ready=True, generic_post_status=200),
    )

    assert report["status"] == "blocked"
    blockers = report["checks"]["blockers"]
    assert "health_live_ready_true_after_deploy" in blockers
    assert "http_status_mismatch:trading_console_generic_post_blocked" in blockers


def test_postdeploy_verifier_blocks_head_and_schema_mismatch():
    module = _load_module()

    report = module.build_postdeploy_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head="wrong-head",
        expected_migration_count=63,
        expected_latest_migration="wrong.py",
        connect_timeout_seconds=8,
        runner=_runner(),
    )

    assert report["status"] == "blocked"
    blockers = report["checks"]["blockers"]
    assert "postdeploy_release_head_mismatch" in blockers
    assert "postdeploy_migration_count_mismatch" in blockers
    assert "postdeploy_latest_migration_mismatch" in blockers


def test_postdeploy_verifier_subprocess_timeout_returns_failure(monkeypatch):
    module = _load_module()

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=("ssh", "tokyo"), timeout=20)

    monkeypatch.setattr(module.subprocess, "run", timeout_run)

    result = module._run(("ssh", "tokyo", "hostname"))

    assert result.returncode == 124
    assert "command timed out after 20s" in result.stderr
