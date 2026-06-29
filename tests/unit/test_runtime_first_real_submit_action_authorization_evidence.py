from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_runtime_first_real_submit_action_authorization_evidence.py"
)
HEAD = "e778f0ced812edfd687074793b8866c4b94be45f"
AUTHORIZATION_ID = "auth-1"
APPROVAL_VALUE = f"{AUTHORIZATION_ID}:first-real-submit:real_gateway_action"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_action_authorization_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_action_authorization_evidence_waits_for_exact_owner_value():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(),
        authorization_id=AUTHORIZATION_ID,
    )

    assert evidence["status"] == "waiting_for_owner_first_real_submit_action_authorization"
    assert evidence["scope"] == "runtime_first_real_submit_action_authorization_evidence"
    assert evidence["checks"]["ready_for_owner_action_authorization"] is True
    assert evidence["checks"]["action_authorized"] is False
    assert evidence["owner_confirmation"]["required_value"] == APPROVAL_VALUE
    assert "operator_command_plan" not in evidence
    assert evidence["action_authorization_plan"]["execute_env_required"] == {
        "name": "OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT",
        "value": APPROVAL_VALUE,
    }
    assert evidence["action_authorization_plan"]["execute_command"] is None
    assert (
        "prearmed_exchange_submit_evidence_required_for_execute_command"
        in evidence["action_authorization_plan"]["execute_command_blockers"]
    )
    assert evidence["safety_invariants"]["evidence_build_only"] is True
    assert "packet_" + "build_only" not in evidence["safety_invariants"]
    assert "next_packet_required" not in evidence["owner_gate"]
    assert evidence["owner_gate"]["next_evidence_required"] == (
        "exchange-arm-derived first-real-submit action evidence"
    )
    assert evidence["safety_invariants"]["exchange_called"] is False
    assert evidence["safety_invariants"]["order_lifecycle_called"] is False


def test_action_authorization_evidence_does_not_use_non_authoritative_hint():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(
            submit_authorization_id=AUTHORIZATION_ID
        ),
    )

    assert evidence["authorization_id"] is None
    assert evidence["authorization_id_hint"] == AUTHORIZATION_ID
    assert evidence["checks"]["ready_for_owner_action_authorization"] is False
    assert evidence["owner_confirmation"]["required_value"] is None


def test_action_authorization_evidence_uses_authoritative_context_id():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(
            submit_authorization_id=AUTHORIZATION_ID,
            submit_authorization_id_authoritative=True,
        ),
    )

    assert evidence["authorization_id"] == AUTHORIZATION_ID
    assert evidence["checks"]["ready_for_owner_action_authorization"] is True
    assert evidence["owner_confirmation"]["required_value"] == APPROVAL_VALUE


def test_action_authorization_evidence_marks_ready_with_exact_owner_value_only():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value=APPROVAL_VALUE,
    )

    assert evidence["status"] == "waiting_for_prearmed_exchange_submit_evidence"
    assert evidence["checks"]["owner_confirmation_value_matches"] is True
    assert evidence["checks"]["authorization_guard_satisfied"] is True
    assert evidence["checks"]["action_authorized"] is False
    assert evidence["owner_gate"]["authorized_execute_step_available"] is False
    assert (
        "prearmed_exchange_submit_evidence_required_for_execute_command"
        in evidence["checks"]["warnings"]
    )
    assert evidence["safety_invariants"]["api_called"] is False
    assert evidence["safety_invariants"]["exchange_order_submitted"] is False


def test_action_authorization_evidence_accepts_standing_authorization_without_env():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(),
        authorization_id=AUTHORIZATION_ID,
        standing_authorized_first_real_submit=True,
    )

    assert evidence["status"] == "waiting_for_prearmed_exchange_submit_evidence"
    assert evidence["checks"]["owner_confirmation_value_matches"] is False
    assert evidence["checks"]["standing_authorized_first_real_submit"] is True
    assert evidence["checks"]["authorization_guard_satisfied"] is True
    assert evidence["owner_confirmation"]["must_be_supplied_out_of_band_before_execute_command"] is False
    assert evidence["action_authorization_plan"]["execute_env_required"] is None
    assert (
        "prearmed_exchange_submit_evidence_required_for_execute_command"
        in evidence["action_authorization_plan"]["execute_command_blockers"]
    )
    assert evidence["safety_invariants"]["exchange_called"] is False
    assert evidence["safety_invariants"]["exchange_order_submitted"] is False


def test_action_authorization_evidence_blocks_mismatched_owner_value():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value="wrong",
    )

    assert evidence["status"] == "waiting_for_owner_first_real_submit_action_authorization"
    assert evidence["checks"]["action_authorized"] is False
    assert "owner_confirmation_value_mismatch" in evidence["checks"]["blockers"]


def test_action_authorization_evidence_requires_submit_authorization_id():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(),
    )

    assert evidence["status"] == "blocked_before_first_real_submit_action_authorization"
    assert evidence["checks"]["ready_for_owner_action_authorization"] is False
    assert "submit_authorization_id_missing_for_action_plan" in (
        evidence["checks"]["blockers"]
    )
    assert evidence["action_authorization_plan"]["execute_command"] is None


def test_action_authorization_evidence_blocks_unready_final_review():
    module = _load_module()

    evidence = module.build_first_real_submit_action_authorization_evidence(
        final_review_artifact=_final_review_artifact(ready=False),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value=APPROVAL_VALUE,
    )

    assert evidence["status"] == "blocked_before_first_real_submit_action_authorization"
    assert evidence["checks"]["action_authorized"] is False
    assert "final_review_not_ready_for_action_authorization" in (
        evidence["checks"]["blockers"]
    )


def test_action_authorization_evidence_cli_reads_json(tmp_path: Path, capsys):
    module = _load_module()
    final_review_path = tmp_path / "final-review.json"
    output_path = tmp_path / "action-auth.json"
    final_review_path.write_text(json.dumps(_final_review_artifact()))

    exit_code = module.main(
        [
            "--json",
            "--final-review-artifact-path",
            str(final_review_path),
            "--authorization-id",
            AUTHORIZATION_ID,
            "--owner-confirmation-value",
            APPROVAL_VALUE,
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"]["owner_confirmation_value_matches"] is True
    assert payload["checks"]["action_authorized"] is False
    assert payload["scope"] == "runtime_first_real_submit_action_authorization_evidence"
    assert "next_packet_required" not in json.dumps(payload)
    assert "packet_" + "build_only" not in json.dumps(payload)
    assert json.loads(output_path.read_text())["status"] == (
        "waiting_for_prearmed_exchange_submit_evidence"
    )


def _final_review_artifact(
    *,
    ready: bool = True,
    submit_authorization_id: str | None = None,
    submit_authorization_id_authoritative: bool = False,
):
    return {
        "status": (
            "ready_for_owner_first_real_submit_action_review"
            if ready
            else "blocked_before_first_real_submit_final_review"
        ),
        "target_head": HEAD,
        "checks": {
            "ready_for_owner_action_review": ready,
            "owner_action_ready": ready,
            "target_head_consistent": ready,
            "blockers": [] if ready else ["postdeploy_acceptance_not_ready"],
            "forbidden_effects": [],
            "warnings": ["release_identity_from_manifest_without_git_status"],
        },
        "owner_gate": {
            "final_review_only": True,
            "next_authorization_if_ready": (
                "explicit first-real-submit action authorization"
            ),
        },
        "first_real_submit_action_context": {
            "submit_authorization_id": submit_authorization_id,
            "submit_authorization_id_source": (
                "unit_test" if submit_authorization_id else None
            ),
            "submit_authorization_id_authoritative_for_remote_execution": (
                submit_authorization_id_authoritative
            ),
            "requires_exact_owner_action_confirmation": True,
            "does_not_authorize_live_action": True,
        },
        "safety_invariants": {
            "packet_" + "build_only": True,
            "exchange_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
