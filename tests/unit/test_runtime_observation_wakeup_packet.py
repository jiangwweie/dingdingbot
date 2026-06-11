from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_runtime_observation_wakeup_packet.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "build_runtime_observation_wakeup_packet",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operator_packet(
    *,
    status: str = "observation_running_no_signal",
    ready_count: int = 0,
    prepared_authorization_id: str | None = None,
    shadow_candidate_id: str | None = None,
    forbidden: bool = False,
) -> dict:
    return {
        "scope": "runtime_observation_operator_packet",
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
        "operator_command_plan": {
            "allowed_next_actions": ["continue_active_runtime_observation"],
            "creates_execution_intent": False,
            "places_order": forbidden,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "operator_packet_only": True,
            "forbidden_effects": ["order_created"] if forbidden else [],
            "execution_intent_created": False,
            "order_created": forbidden,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_wakeup_packet_allows_owner_sleep_when_no_signal():
    module = _load_module()

    packet = module.build_wakeup_packet(_operator_packet())

    assert packet["status"] == "owner_sleep_safe_observation_running"
    assert packet["owner_attention"] == "no_owner_action_needed_now"
    assert packet["allowed_while_owner_asleep"] == [
        "continue_active_runtime_observation"
    ]
    assert packet["summary"]["runtime_ready_signal_count"] == 0
    assert packet["safety_invariants"]["execution_intent_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_wakeup_packet_surfaces_ready_signal_without_submit_authority():
    module = _load_module()

    packet = module.build_wakeup_packet(
        _operator_packet(status="runtime_signal_attention", ready_count=1)
    )

    assert packet["status"] == "runtime_signal_ready_for_non_executing_prepare"
    assert packet["owner_attention"] == "review_when_available"
    assert "create_shadow_order_candidate" in packet["allowed_while_owner_asleep"]
    assert "run_disabled_first_real_submit_smoke" in packet["allowed_while_owner_asleep"]
    assert "place_exchange_order" not in packet["allowed_while_owner_asleep"]
    assert "exchange_order_placement" in packet["requires_owner_before"]


def test_wakeup_packet_surfaces_prepared_shadow_evidence_for_owner_review():
    module = _load_module()

    packet = module.build_wakeup_packet(
        _operator_packet(
            status="runtime_signal_attention",
            prepared_authorization_id="auth-1",
            shadow_candidate_id="candidate-1",
        )
    )

    assert packet["status"] == "prepared_shadow_evidence_ready_for_owner_review"
    assert packet["summary"]["prepared_authorization_id"] == "auth-1"
    assert packet["summary"]["shadow_candidate_id"] == "candidate-1"
    assert packet["allowed_while_owner_asleep"] == [
        "run_final_gate_preview",
        "run_arm_preview",
        "run_disabled_first_real_submit_smoke",
    ]


def test_wakeup_packet_blocks_forbidden_source_effects():
    module = _load_module()

    packet = module.build_wakeup_packet(_operator_packet(forbidden=True))

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["allowed_while_owner_asleep"] == []
    assert "order_created" in packet["safety_invariants"]["source_forbidden_effects"]
    assert "command_plan.places_order" in packet["safety_invariants"][
        "source_forbidden_effects"
    ]


def test_wakeup_packet_cli_reads_and_writes_json(tmp_path, capsys):
    module = _load_module()
    input_path = tmp_path / "operator.json"
    output_path = tmp_path / "wakeup.json"
    input_path.write_text(json.dumps(_operator_packet()), encoding="utf-8")

    exit_code = module.main(
        [
            "--operator-packet-json",
            str(input_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "runtime_observation_wakeup_packet"
