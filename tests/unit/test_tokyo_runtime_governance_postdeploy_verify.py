from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_tokyo_runtime_governance_postdeploy.py"
EXPECTED_HEAD = "0c350ca7d34db7d2db7c9ae2b99fa6c6e0ddcafe"
LATEST_MIGRATION = "2026-06-10-064_add_runtime_profile_proposal_snapshot.py"


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
            return module.CommandResult("64\n", "", 0)
        if "tail -1" in remote:
            return module.CommandResult(LATEST_MIGRATION + "\n", "", 0)
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
            return module.CommandResult('{"ok":true}\nHTTP_STATUS:200\n', "", 0)
        raise AssertionError(f"unexpected command: {remote}")

    return runner


def test_postdeploy_verifier_passes_archive_release_with_readonly_api_checks():
    module = _load_module()

    report = module.build_postdeploy_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head=EXPECTED_HEAD,
        expected_migration_count=64,
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
    assert len(report["facts"]["http_checks"]) == 11
    assert all(value is False for value in report["safety_invariants"].values())


def test_postdeploy_verifier_blocks_live_ready_true_and_unblocked_generic_post():
    module = _load_module()

    report = module.build_postdeploy_report(
        host="tokyo",
        deploy_root="~/brc-deploy",
        api_base="http://127.0.0.1:18080",
        expected_current_head=EXPECTED_HEAD,
        expected_migration_count=64,
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
