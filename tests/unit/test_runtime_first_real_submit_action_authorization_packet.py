from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_runtime_first_real_submit_action_authorization_packet.py"
)
HEAD = "e778f0ced812edfd687074793b8866c4b94be45f"
AUTHORIZATION_ID = "auth-1"
APPROVAL_VALUE = f"{AUTHORIZATION_ID}:first-real-submit:real_gateway_action"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_first_real_submit_action_authorization_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_action_authorization_packet_waits_for_exact_owner_value():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(),
        authorization_id=AUTHORIZATION_ID,
    )

    assert packet["status"] == "waiting_for_owner_first_real_submit_action_authorization"
    assert packet["checks"]["ready_for_owner_action_authorization"] is True
    assert packet["checks"]["action_authorized"] is False
    assert packet["owner_confirmation"]["required_value"] == APPROVAL_VALUE
    assert packet["operator_command_plan"]["execute_env_required"] == {
        "name": "OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT",
        "value": APPROVAL_VALUE,
    }
    assert packet["operator_command_plan"]["execute_command"][-3:] == [
        "--authorization-id",
        AUTHORIZATION_ID,
        "--execute-real-submit",
    ]
    assert packet["safety_invariants"]["exchange_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_action_authorization_packet_infers_authorization_id_from_final_review():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(
            submit_authorization_id=AUTHORIZATION_ID
        ),
    )

    assert packet["authorization_id"] == AUTHORIZATION_ID
    assert packet["checks"]["ready_for_owner_action_authorization"] is True
    assert packet["owner_confirmation"]["required_value"] == APPROVAL_VALUE


def test_action_authorization_packet_marks_ready_with_exact_owner_value_only():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value=APPROVAL_VALUE,
    )

    assert packet["status"] == "owner_first_real_submit_action_authorization_packet_ready"
    assert packet["checks"]["action_authorized"] is True
    assert packet["owner_gate"]["authorized_execute_step_available"] is True
    assert packet["safety_invariants"]["api_called"] is False
    assert packet["safety_invariants"]["exchange_order_submitted"] is False


def test_action_authorization_packet_blocks_mismatched_owner_value():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value="wrong",
    )

    assert packet["status"] == "waiting_for_owner_first_real_submit_action_authorization"
    assert packet["checks"]["action_authorized"] is False
    assert "owner_confirmation_value_mismatch" in packet["checks"]["blockers"]


def test_action_authorization_packet_requires_submit_authorization_id():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(),
    )

    assert packet["status"] == "blocked_before_first_real_submit_action_authorization"
    assert packet["checks"]["ready_for_owner_action_authorization"] is False
    assert "submit_authorization_id_missing_for_action_plan" in (
        packet["checks"]["blockers"]
    )
    assert packet["operator_command_plan"]["execute_command"] is None


def test_action_authorization_packet_blocks_unready_final_review():
    module = _load_module()

    packet = module.build_first_real_submit_action_authorization_packet(
        final_review_packet=_final_review_packet(ready=False),
        authorization_id=AUTHORIZATION_ID,
        owner_confirmation_value=APPROVAL_VALUE,
    )

    assert packet["status"] == "blocked_before_first_real_submit_action_authorization"
    assert packet["checks"]["action_authorized"] is False
    assert "final_review_not_ready_for_action_authorization" in (
        packet["checks"]["blockers"]
    )


def test_action_authorization_packet_cli_reads_json(tmp_path: Path, capsys):
    module = _load_module()
    final_review_path = tmp_path / "final-review.json"
    output_path = tmp_path / "action-auth.json"
    final_review_path.write_text(json.dumps(_final_review_packet()))

    exit_code = module.main(
        [
            "--json",
            "--final-review-packet-path",
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
    assert payload["checks"]["action_authorized"] is True
    assert json.loads(output_path.read_text())["status"] == (
        "owner_first_real_submit_action_authorization_packet_ready"
    )


def _final_review_packet(
    *,
    ready: bool = True,
    submit_authorization_id: str | None = None,
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
            "requires_exact_owner_action_confirmation": True,
            "does_not_authorize_live_action": True,
        },
        "safety_invariants": {
            "packet_build_only": True,
            "exchange_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }
