from __future__ import annotations

import json

from scripts import runtime_official_controlled_gateway_action_proof as script


def test_official_controlled_gateway_action_passes(tmp_path):
    report = script.build_proof_report(tmp_path / "rtf087")

    assert report["status"] == "official_controlled_gateway_action_passed"
    assert report["order_candidate_id"] == "order-candidate-rtf075-contract"
    assert report["authorization_id"].startswith("runtime-submit-authorization-")
    assert report["exchange_submit_execution_result_id"].startswith(
        "runtime-exchange-submit-execution-result-"
    )

    checks = report["checks"]
    assert checks["exchange_boundary_packet_passed"] is True
    assert checks["exchange_adapter_result_armed"] is True
    assert checks["exchange_execution_result_submitted"] is True
    assert checks["exchange_execution_enabled_true"] is True
    assert checks["exchange_execution_mode_in_memory"] is True
    assert checks["fake_gateway_called_twice"] is True
    assert checks["exchange_call_count_two"] is True
    assert checks["order_lifecycle_submit_call_count_two"] is True
    assert checks["local_lifecycle_submit_called_twice"] is True
    assert checks["submitted_local_order_ids_present"] is True
    assert checks["submitted_exchange_order_ids_present"] is True
    assert checks["entry_exchange_order_id_present"] is True
    assert checks["protection_exchange_order_id_present"] is True
    assert checks["durable_result_lock_acquired"] is True
    assert checks["durable_result_completed"] is True
    assert checks["entry_fill_projected"] is True
    assert checks["no_recovery_task_created"] is True
    assert checks["uses_official_fastapi_routes"] is True
    assert checks["uses_fake_console_api"] is False
    assert checks["pg_written"] is False
    assert checks["live_exchange_called"] is False
    assert checks["fake_gateway_called"] is True
    assert checks["exchange_order_submitted"] is True
    assert checks["order_lifecycle_submit_called"] is True
    assert checks["execution_intent_status_changed"] is False
    assert checks["withdrawal_or_transfer_created"] is False


def test_official_controlled_gateway_action_outputs_packet(tmp_path):
    output_dir = tmp_path / "rtf087"

    report = script.build_proof_report(output_dir)

    expected_files = [
        "contract-report.json",
        "exchange-submit-boundary-packet.json",
        "exchange-submit-execution-result.json",
        "controlled-gateway-action-packet.json",
    ]
    for name in expected_files:
        assert (output_dir / name).exists()

    assert json.loads((output_dir / "contract-report.json").read_text())[
        "status"
    ] == report["status"]
    packet = json.loads(
        (output_dir / "controlled-gateway-action-packet.json").read_text()
    )
    assert packet["status"] == "controlled_gateway_action_submitted"
    assert packet["statuses"]["exchange_submit_adapter_result"] == (
        "exchange_submit_adapter_armed"
    )
    assert packet["statuses"]["exchange_submit_execution_result"] == (
        "exchange_submit_orders_submitted"
    )
    action = packet["gateway_action"]
    assert action["execution_mode"] == "in_memory_simulation"
    assert action["exchange_submit_execution_enabled"] is True
    assert action["fake_gateway_call_count"] == 2
    assert action["exchange_call_count"] == 2
    assert action["order_lifecycle_submit_call_count"] == 2
    assert action["gateway_reduce_only_flags"] == [False, True]
    assert len(action["submitted_local_order_ids"]) == 2
    assert len(action["submitted_exchange_order_ids"]) == 2
    assert action["entry_exchange_order_id"].startswith("controlled-ex-")
    assert len(action["protection_exchange_order_ids"]) == 1
    assert action["blockers"] == []
    assert packet["local_projection"]["registered_order_count"] == 2
    assert packet["local_projection"]["submit_call_count"] == 2
    assert packet["local_projection"]["entry_fill_projected"] is True
    assert packet["durable_result"]["repo_acquire_calls"] == 1
    assert packet["durable_result"]["repo_complete_calls"] == 1
    assert packet["safety_invariants"]["fake_gateway_called"] is True
    assert packet["safety_invariants"]["live_exchange_called"] is False
    assert packet["safety_invariants"]["durable_execution_result_recorded"] is True
    assert packet["safety_invariants"]["withdrawal_or_transfer_created"] is False


def test_official_controlled_gateway_action_cli_stdout_is_json_only(
    capsys,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        script.sys,
        "argv",
        [
            "runtime_official_controlled_gateway_action_proof.py",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "official_controlled_gateway_action_passed"
    assert captured.err == ""
