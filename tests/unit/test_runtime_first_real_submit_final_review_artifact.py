from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "build_runtime_first_real_submit_final_review_artifact.py"
)
HEAD = "cb82d4388416217a2deac50705023cf40624c965"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_final_review_artifact",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_review_artifact_can_reach_owner_action_review():
    module = _load_module()

    artifact = module.build_first_real_submit_final_review_artifact(
        postdeploy_acceptance_evidence=_postdeploy_evidence(),
        first_real_submit_owner_evidence=_owner_evidence(),
        expected_current_head=HEAD,
    )

    assert artifact["status"] == "ready_for_owner_first_real_submit_action_review"
    assert artifact["checks"]["ready_for_prerequisite_review"] is True
    assert artifact["checks"]["ready_for_owner_action_review"] is True
    assert artifact["checks"]["target_head_consistent"] is True
    assert artifact["checks"]["blockers"] == []
    assert (
        artifact["evidence"]["first_real_submit_owner_evidence_status"]
        == "ready_for_owner_controlled_first_real_submit_review"
    )
    assert artifact["scope"] == "runtime_first_real_submit_final_review_artifact"
    assert artifact["evidence"]["owner_evidence_local_head"] == HEAD
    assert artifact["action_review"]["owner_evidence_ready_for_decision"] is True
    assert artifact["checks"]["owner_evidence_ready"] is True
    assert artifact["safety_invariants"]["artifact_build_only"] is True
    assert "owner_" + "packet_local_head" not in artifact["evidence"]
    assert "owner_evidence_status" not in artifact["evidence"]
    assert "packet_" + "build_only" not in artifact["safety_invariants"]
    assert artifact["owner_gate"]["next_authorization_if_ready"] == (
        "explicit first-real-submit action authorization"
    )
    assert artifact["first_real_submit_action_context"][
        "submit_authorization_id"
    ] == "runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5"
    assert artifact["first_real_submit_action_context"][
        "submit_authorization_id_authoritative_for_remote_execution"
    ] is False
    assert artifact["safety_invariants"]["exchange_called"] is False
    assert artifact["safety_invariants"]["remote_files_modified"] is False


def test_final_review_artifact_blocks_stale_owner_evidence_head():
    module = _load_module()
    owner_evidence = _owner_evidence(head="stale-head")

    artifact = module.build_first_real_submit_final_review_artifact(
        postdeploy_acceptance_evidence=_postdeploy_evidence(),
        first_real_submit_owner_evidence=owner_evidence,
        expected_current_head=HEAD,
    )

    assert artifact["status"] == "blocked_before_first_real_submit_final_review"
    assert artifact["checks"]["ready_for_owner_action_review"] is False
    assert "first_real_submit_owner_evidence_head_mismatch" in (
        artifact["checks"]["blockers"]
    )
    assert "first_real_submit_owner_" + "packet_head_mismatch" not in (
        artifact["checks"]["blockers"]
    )


def test_final_review_artifact_allows_prerequisite_review_before_action_ready():
    module = _load_module()

    artifact = module.build_first_real_submit_final_review_artifact(
        postdeploy_acceptance_evidence=_postdeploy_evidence(),
        first_real_submit_owner_evidence=_owner_evidence(action_ready=False),
        expected_current_head=HEAD,
    )

    assert artifact["status"] == "ready_for_owner_first_real_submit_prerequisite_review"
    assert artifact["checks"]["ready_for_prerequisite_review"] is True
    assert artifact["checks"]["ready_for_owner_action_review"] is False
    assert artifact["checks"]["owner_action_ready"] is False
    assert artifact["checks"]["blockers"] == []
    assert artifact["action_review"]["remaining_action_blockers"] == [
        "exchange_submit_adapter_pre_execution_not_ready",
        "first_real_submit_action_not_ready",
    ]


def test_final_review_artifact_cli_reads_json_inputs(tmp_path: Path, capsys):
    module = _load_module()
    postdeploy_path = tmp_path / "postdeploy.json"
    owner_path = tmp_path / "owner.json"
    postdeploy_path.write_text(json.dumps(_postdeploy_evidence()))
    owner_path.write_text(json.dumps(_owner_evidence()))

    exit_code = module.main(
        [
            "--json",
            "--postdeploy-acceptance-artifact-path",
            str(postdeploy_path),
            "--first-real-submit-owner-evidence-path",
            str(owner_path),
            "--expected-current-head",
            HEAD,
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready_for_owner_first_real_submit_action_review"
    assert payload["scope"] == "runtime_first_real_submit_final_review_artifact"
    assert "owner_" + "packet_local_head" not in json.dumps(payload)
    assert "final_review_" + "packet_contains_forbidden_effects" not in json.dumps(payload)


def _postdeploy_evidence(head: str = HEAD, *, ready: bool = True):
    return {
        "status": "postdeploy_acceptance_ready" if ready else "blocked",
        "expected_current_head": head,
        "postdeploy_summary": {
            "current_head": head,
            "health": {"live_ready": False},
        },
        "checks": {
            "postdeploy_acceptance_ready": ready,
            "warnings": [],
        },
        "safety_invariants": {
            "artifact_build_only": True,
            "remote_files_modified": False,
            "migrations_run": False,
            "services_restarted": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _owner_evidence(head: str = HEAD, *, action_ready: bool = True):
    action_blockers = (
        []
        if action_ready
        else [
            "exchange_submit_adapter_pre_execution_not_ready",
            "first_real_submit_action_not_ready",
        ]
    )
    return {
        "status": (
            "ready_for_owner_controlled_first_real_submit_review"
            if action_ready
            else "ready_for_owner_first_real_submit_decision"
        ),
        "local_git": {"head": head, "short_head": head[:8]},
        "deployment_gate": {"current_head_deployed": True},
        "checks": {
            "evidence_ready_for_owner_review": True,
            "ready_for_first_real_submit": action_ready,
            "blockers": [],
        },
        "first_real_submit_action_boundary": {
            "ready_for_first_real_submit": action_ready,
            "exchange_submit_adapter_pre_execution_ready": action_ready,
            "exchange_submit_execution_disabled_proved": True,
            "remaining_action_blockers": action_blockers,
            "requires_separate_action_authorization": True,
            "does_not_authorize_live_action": True,
        },
        "local_registration_rehearsal": {
            "action_authorization_id": (
                "runtime-local-registration-action-authorization-"
                "runtime-submit-authorization-intent_rt_1d7d7a346233063607e711f5"
            ),
        },
        "safety_invariants": {
            "artifact_build_only": True,
            "database_connected": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "migrations_run": False,
            "runtime_started": False,
            "persistent_runtime_budget_mutated": False,
            "execution_intent_status_changed": False,
            "order_created": False,
            "owner_bounded_execution_called": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
