from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_observation_wakeup_evidence.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_observation_wakeup_evidence",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operator_evidence(
    *,
    status: str = "observation_running_no_signal",
    ready_count: int = 0,
    prepared_authorization_id: str | None = None,
    shadow_candidate_id: str | None = None,
    forbidden: bool = False,
) -> dict:
    return {
        "scope": "runtime_observation_operator_evidence",
        "status": status,
        "active_runtime_observation": {
            "active_runtime_count": 2,
            "latest_iteration": 8,
            "iterations_completed": 8,
            "iterations_remaining": 69,
            "stop_reason": "running",
            "prepared_authorization_id": prepared_authorization_id,
            "shadow_candidate_id": shadow_candidate_id,
        },
        "signal_counts": {
            "runtime_ready_signal_count": ready_count,
            "strategy_group_would_enter_signal_count": 0,
            "strategy_group_no_action_signal_count": 8,
        },
        "runtime_prepare_context": {
            "prepared_authorization_id": prepared_authorization_id,
            "shadow_candidate_id": shadow_candidate_id,
            "allowed_non_executing_followups": [
                "create_shadow_signal_evaluation",
                "create_shadow_order_candidate",
                "create_prepare_authorization_record",
                "run_final_gate_preview",
                "run_arm_preview",
                "run_disabled_first_real_submit_smoke",
                "place_exchange_order",
            ],
        },
        "operator_review_plan": {
            "allowed_review_checkpoints": ["continue_active_runtime_observation"],
            "places_order": forbidden,
        },
        "safety_invariants": {
            "operator_evidence_only": True,
            "forbidden_effects": ["order_created"] if forbidden else [],
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_wakeup_evidence_allows_owner_sleep_when_no_signal():
    module = _load_module()

    artifact = module.build_wakeup_evidence(_operator_evidence())

    assert artifact["status"] == "owner_sleep_safe_observation_running"
    assert artifact["owner_attention"] == "no_owner_action_needed_now"
    assert artifact["allowed_while_owner_asleep"] == [
        "continue_active_runtime_observation"
    ]
    assert artifact["summary"]["runtime_ready_signal_count"] == 0
    assert artifact["safety_invariants"]["wakeup_evidence_only"] is True
    assert artifact["safety_invariants"]["source_operator_evidence_read_only"] is True
    assert "operator_evidence_only" not in artifact["safety_invariants"]
    assert "wakeup_packet_only" not in artifact["safety_invariants"]
    assert "source_packet_read_only" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"]["execution_intent_created"] is False
    assert artifact["safety_invariants"]["exchange_write_called"] is False


def test_wakeup_evidence_surfaces_ready_signal_without_submit_authority():
    module = _load_module()

    artifact = module.build_wakeup_evidence(
        _operator_evidence(status="runtime_signal_attention", ready_count=1)
    )

    assert artifact["status"] == "runtime_signal_ready_for_non_executing_prepare"
    assert artifact["owner_attention"] == "review_when_available"
    assert "create_shadow_order_candidate" in artifact["allowed_while_owner_asleep"]
    assert "run_disabled_first_real_submit_smoke" in artifact["allowed_while_owner_asleep"]
    assert "place_exchange_order" not in artifact["allowed_while_owner_asleep"]
    assert "exchange_order_placement" in artifact["requires_owner_before"]


def test_wakeup_evidence_surfaces_prepared_shadow_evidence_for_owner_review():
    module = _load_module()

    artifact = module.build_wakeup_evidence(
        _operator_evidence(
            status="runtime_signal_attention",
            prepared_authorization_id="auth-1",
            shadow_candidate_id="candidate-1",
        )
    )

    assert artifact["status"] == "prepared_shadow_evidence_ready_for_owner_review"
    assert artifact["summary"]["prepared_authorization_id"] == "auth-1"
    assert artifact["summary"]["shadow_candidate_id"] == "candidate-1"
    assert artifact["allowed_while_owner_asleep"] == [
        "run_final_gate_preview",
        "run_arm_preview",
        "run_disabled_first_real_submit_smoke",
    ]


def test_wakeup_evidence_blocks_forbidden_source_effects():
    module = _load_module()

    artifact = module.build_wakeup_evidence(_operator_evidence(forbidden=True))

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["allowed_while_owner_asleep"] == []
    assert "order_created" in artifact["safety_invariants"]["source_forbidden_effects"]
    assert "operator_review_plan.places_order" in artifact["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_wakeup_evidence_cli_reads_and_writes_json(tmp_path, capsys):
    module = _load_module()
    input_path = tmp_path / "operator.json"
    output_path = tmp_path / "wakeup.json"
    input_path.write_text(json.dumps(_operator_evidence()), encoding="utf-8")

    exit_code = module.main(
        [
            "--operator-evidence-json",
            str(input_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_observation_wakeup_evidence"
