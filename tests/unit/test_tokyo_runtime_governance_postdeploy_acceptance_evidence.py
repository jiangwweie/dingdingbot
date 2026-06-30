from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_tokyo_runtime_governance_postdeploy_acceptance_evidence.py"
)
EXPECTED_HEAD = "deployed-head"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_tokyo_runtime_governance_postdeploy_acceptance_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _postdeploy_report(*, live_ready: bool = False, head: str = EXPECTED_HEAD) -> dict:
    return {
        "status": "postdeploy_acceptance_passed",
        "facts": {
            "release_identity": {
                "source": "release_manifest",
                "head": head,
            },
            "migration_count": "70",
            "latest_migration": (
                "2026-06-10-070_add_execution_intent_local_orders_registered_status.py"
            ),
            "http_checks": [
                {
                    "name": "health",
                    "http_status": 200,
                    "expected_status": 200,
                    "body_json": {
                        "status": "ok",
                        "runtime_bound": True,
                        "live_ready": live_ready,
                    },
                },
                {
                    "name": "runtime_execution_controlled_submit_write_requires_auth",
                    "http_status": 401,
                    "expected_status": 401,
                    "body_json": {"message": "Operator login required"},
                },
            ],
        },
        "checks": {
            "postdeploy_acceptance_passed": True,
            "blockers": [],
            "warnings": ["release_identity_from_manifest_without_git_status"],
        },
        "safety_invariants": {
            "remote_files_modified": False,
            "env_files_read": False,
            "secrets_read": False,
            "database_connected_directly": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "trading_console_include_exchange": False,
        },
    }


def _pre_live_evidence(
    *,
    current_head_deployed: bool = True,
    ready_for_first_real_submit: bool = False,
) -> dict:
    return {
        "status": (
            "ready_for_first_real_submit"
            if ready_for_first_real_submit
            else "blocked_before_first_real_submit"
        ),
        "checks": {
            "technical_rehearsal_passed": True,
            "registration_draft_chain_passed": True,
            "current_head_deployed": current_head_deployed,
            "ready_for_first_real_submit": ready_for_first_real_submit,
            "technical_blockers": [],
            "implementation_blockers": [
                "runtime_not_live_execution_enabled",
                "order_lifecycle_adapter_disabled",
            ],
            "forbidden_execution_flags": [],
        },
        "safety_invariants": {
            "attempt_consumed": False,
            "database_connected": False,
            "exchange_called": False,
            "execution_intent_status_changed": False,
            "migrations_run": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "owner_bounded_execution_called": False,
            "persistent_runtime_budget_mutated": False,
            "remote_files_modified": False,
            "runtime_budget_mutated": False,
            "runtime_started": False,
            "services_restarted": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _build_artifact(**overrides):
    module = _load_module()
    kwargs = {
        "postdeploy_report": _postdeploy_report(),
        "pre_live_evidence": _pre_live_evidence(),
        "expected_current_head": EXPECTED_HEAD,
    }
    kwargs.update(overrides)
    return module.build_postdeploy_acceptance_evidence(**kwargs)


def test_postdeploy_acceptance_evidence_ready_while_real_submit_still_blocked():
    artifact = _build_artifact()

    assert artifact["status"] == "postdeploy_acceptance_ready"
    assert artifact["checks"]["postdeploy_acceptance_ready"] is True
    assert artifact["checks"]["current_head_matches_expected"] is True
    assert artifact["checks"]["health_live_ready_false"] is True
    assert artifact["checks"]["current_head_deployed_gate"] is True
    assert artifact["checks"]["first_real_submit_still_blocked"] is True
    assert artifact["checks"]["blockers"] == []
    assert "real runtime submit" in artifact["owner_gate"]["does_not_authorize"]
    assert artifact["safety_invariants"]["order_created"] is False
    assert artifact["safety_invariants"]["exchange_called"] is False


def test_postdeploy_acceptance_human_output_reads_artifact(capsys):
    module = _load_module()
    artifact = _build_artifact()

    module._print_human(artifact)

    output = capsys.readouterr().out
    assert "status=postdeploy_acceptance_ready" in output
    assert "postdeploy_acceptance_ready=true" in output
    assert "expected_current_head=deployed-head" in output
    assert "current_head=deployed-head" in output
    assert "first_real_submit_still_blocked=true" in output


def test_postdeploy_acceptance_evidence_blocks_live_ready_true_and_head_mismatch():
    artifact = _build_artifact(
        postdeploy_report=_postdeploy_report(live_ready=True, head="old-head")
    )

    assert artifact["status"] == "blocked"
    blockers = artifact["checks"]["blockers"]
    assert "postdeploy_current_head_mismatch" in blockers
    assert "postdeploy_health_live_ready_not_false" in blockers


def test_postdeploy_acceptance_evidence_warns_if_first_real_submit_is_ready():
    artifact = _build_artifact(pre_live_evidence=_pre_live_evidence(ready_for_first_real_submit=True))

    assert artifact["status"] == "postdeploy_acceptance_ready"
    assert artifact["checks"]["blockers"] == []
    assert "first_real_submit_not_a_postdeploy_acceptance_precondition" in (
        artifact["checks"]["warnings"]
    )


def test_postdeploy_acceptance_evidence_requires_current_head_deployed_gate():
    artifact = _build_artifact(
        pre_live_evidence=_pre_live_evidence(current_head_deployed=False)
    )

    assert artifact["status"] == "blocked"
    assert "pre_live_current_head_deployed_gate_not_true" in artifact["checks"]["blockers"]


def test_postdeploy_acceptance_cli_can_use_existing_pre_live_evidence(
    monkeypatch,
    capsys,
    tmp_path,
):
    module = _load_module()
    pre_live_path = tmp_path / "pre-live.json"
    pre_live_path.write_text(json.dumps(_pre_live_evidence()) + "\n")

    def fake_postdeploy_report(**kwargs):
        assert kwargs["expected_current_head"] == EXPECTED_HEAD
        return _postdeploy_report()

    monkeypatch.setattr(module, "build_postdeploy_report", fake_postdeploy_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_tokyo_runtime_governance_postdeploy_acceptance_evidence.py",
            "--json",
            "--expected-current-head",
            EXPECTED_HEAD,
            "--pre-live-evidence-path",
            str(pre_live_path),
        ],
    )

    assert module.main() == 0

    artifact = json.loads(capsys.readouterr().out)
    assert artifact["status"] == "postdeploy_acceptance_ready"
    assert artifact["checks"]["postdeploy_acceptance_ready"] is True
    assert artifact["pre_live_submit_summary"]["current_head_deployed"] is True
