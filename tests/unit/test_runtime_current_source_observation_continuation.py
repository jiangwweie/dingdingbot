from __future__ import annotations

import argparse
import json
import sys

from scripts import runtime_current_source_observation_continuation as script


def test_continuation_waits_without_running_pipeline(tmp_path):
    calls = {"loop": 0, "pipeline": 0}

    def loop_builder(args):
        calls["loop"] += 1
        return _loop_packet("waiting_for_signal")

    def pipeline_builder(args):
        calls["pipeline"] += 1
        raise AssertionError("pipeline must not run while waiting for signal")

    packet = script._build_packet(
        _args(tmp_path),
        fresh_loop_builder=loop_builder,
        current_pipeline_builder=pipeline_builder,
    )

    assert packet["status"] == "waiting_for_signal"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_observation_until_genuine_would_enter"
    )
    assert calls == {"loop": 1, "pipeline": 0}
    assert packet["current_source_pipeline"] is None
    assert packet["safety_invariants"]["uses_historical_rtf015_sample_handoff"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_continuation_requires_evidence_before_current_source_pipeline(tmp_path):
    calls = {"pipeline": 0}

    def pipeline_builder(args):
        calls["pipeline"] += 1
        raise AssertionError("pipeline must not run without readiness evidence")

    packet = script._build_packet(
        _args(tmp_path),
        fresh_loop_builder=lambda args: _loop_packet("ready_for_final_gate_preflight"),
        current_pipeline_builder=pipeline_builder,
    )

    assert packet["status"] == "ready_for_current_source_pipeline_evidence"
    assert packet["signal_input_json"] == "/tmp/ready-signal.json"
    assert packet["operator_command_plan"]["requires_readiness_evidence"] is True
    assert calls["pipeline"] == 0
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["runtime_budget_mutated"] is False


def test_continuation_runs_current_source_pipeline_after_evidence(tmp_path):
    seen = {}

    def pipeline_builder(args):
        seen["signal_input_json"] = args.signal_input_json
        seen["readiness_evidence_json"] = args.readiness_evidence_json
        return _pipeline_ready_packet()

    packet = script._build_packet(
        _args(tmp_path, readiness_evidence_json="/tmp/evidence.json"),
        fresh_loop_builder=lambda args: _loop_packet("ready_for_final_gate_preflight"),
        current_pipeline_builder=pipeline_builder,
    )

    assert packet["status"] == "ready_current_persisted_source_disabled_smoke"
    assert seen == {
        "signal_input_json": "/tmp/ready-signal.json",
        "readiness_evidence_json": "/tmp/evidence.json",
    }
    assert packet["operator_command_plan"]["requires_real_submit_gate"] is True
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_order_lifecycle"] is False
    assert packet["safety_invariants"]["submit_authorization_created"] is True
    assert packet["safety_invariants"]["calls_official_submit_endpoint"] is True
    assert packet["safety_invariants"]["exchange_submit_execution_enabled"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_continuation_propagates_current_source_blocker(tmp_path):
    packet = script._build_packet(
        _args(tmp_path, auto_readiness_evidence=True),
        fresh_loop_builder=lambda args: _loop_packet("ready_for_final_gate_preflight"),
        current_pipeline_builder=lambda args: {
            "status": "blocked_at_strategy_signal_intent_draft_source",
            "blocked_stage": "strategy_signal_intent_draft_source",
            "blockers": ["intent_draft_source:strategy_signal_not_would_enter"],
            "warnings": [],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    assert packet["status"] == "blocked_at_strategy_signal_intent_draft_source"
    assert packet["blocked_stage"] == "strategy_signal_intent_draft_source"
    assert "current_source_pipeline:intent_draft_source:strategy_signal_not_would_enter" in (
        packet["blockers"]
    )
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_continuation_cli_stdout_is_json_only(monkeypatch, capsys):
    def fake_build(args):
        print("inner noisy continuation")
        return {"status": "waiting_for_signal", "ok": True}

    monkeypatch.setattr(script, "_build_packet", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_current_source_observation_continuation.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert script.main() == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_signal"
    assert "inner noisy continuation" not in captured.out
    assert "inner noisy continuation" in captured.err


def test_continuation_cli_writes_output_json(monkeypatch, capsys, tmp_path):
    output = tmp_path / "continuation.json"

    def fake_build(args):
        return {
            "status": "ready_for_current_source_pipeline_evidence",
            "runtime_instance_id": args.runtime_instance_id,
        }

    monkeypatch.setattr(script, "_build_packet", fake_build)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_current_source_observation_continuation.py",
            "--runtime-instance-id",
            "runtime-1",
            "--output-json",
            str(output),
        ],
    )

    assert script.main() == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output.read_text())
    assert stdout_payload == file_payload
    assert file_payload["status"] == "ready_for_current_source_pipeline_evidence"


def _loop_packet(status):
    return {
        "status": status,
        "blockers": []
        if status == "ready_for_final_gate_preflight"
        else ["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        "warnings": [],
        "signal_input_json": "/tmp/ready-signal.json",
        "safety_invariants": {
            "prepare_records_created": status == "ready_for_final_gate_preflight",
            "shadow_candidate_created": status == "ready_for_final_gate_preflight",
            "runtime_execution_intent_draft_created": (
                status == "ready_for_final_gate_preflight"
            ),
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_budget_mutated_by_script": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _pipeline_ready_packet():
    return {
        "status": "ready_current_persisted_source_disabled_smoke",
        "blocked_stage": None,
        "blockers": [],
        "warnings": [],
        "safety_invariants": {
            "uses_current_runtime_persisted_source": True,
            "uses_historical_rtf015_sample_handoff": False,
            "signal_evaluation_created": True,
            "order_candidate_created": True,
            "runtime_execution_intent_draft_created": True,
            "execution_intent_created": True,
            "submit_authorization_created": True,
            "calls_official_submit_endpoint": True,
            "requests_real_gateway_action": False,
            "owner_confirmed_for_first_real_submit_action": False,
            "exchange_submit_execution_enabled": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _args(tmp_path, **overrides):
    values = {
        "runtime_instance_id": "runtime-rtf063",
        "authorization_id": None,
        "reservation_id": None,
        "closed_review_required": False,
        "protection_blocker": None,
        "env_file": None,
        "api_base": "http://fixture",
        "metadata_json": None,
        "source": "live_market",
        "include_exchange": False,
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "family": "BTPC-001",
        "strategy_family_id": "BTPC-001",
        "carrier_id": "BTPC-001-v0",
        "quantity": None,
        "target_notional_usdt": None,
        "max_notional": None,
        "leverage": None,
        "max_attempts": None,
        "protection_mode": None,
        "review_requirement": None,
        "evaluation_id": None,
        "playbook_id": None,
        "one_hour_limit": 25,
        "four_hour_limit": 25,
        "timeout_seconds": 10.0,
        "allow_prepare_records": False,
        "candidate_id": None,
        "context_id": None,
        "owner_operator_id": "owner",
        "owner_confirmation_reference": "owner-authorized-rtf063",
        "reason": "unit",
        "next_attempt_symbol": None,
        "next_attempt_side": None,
        "next_attempt_family": None,
        "next_attempt_strategy_family_id": None,
        "next_attempt_carrier_id": None,
        "readiness_evidence_json": None,
        "auto_readiness_evidence": False,
        "final_gate_preview_id": None,
        "final_gate_passed": False,
        "runtime_grant_authorization_id": "grant-rtf063",
        "owner_real_submit_authorization_id": None,
        "trusted_submit_fact_snapshot_id": None,
        "submit_idempotency_policy_id": None,
        "attempt_outcome_policy_id": None,
        "protection_creation_failure_policy_id": None,
        "local_registration_enablement_decision_id": None,
        "exchange_submit_enablement_decision_id": None,
        "exchange_submit_action_authorization_id": None,
        "order_lifecycle_submit_enablement_id": None,
        "exchange_submit_adapter_enablement_id": None,
        "deployment_readiness_evidence_id": None,
        "protection_required_and_ready": False,
        "active_position_source_trusted": False,
        "account_facts_fresh": False,
        "duplicate_submit_guard_ready": False,
        "legacy_runtime_submit_rehearsal_id": None,
        "durable_exchange_submit_execution_result_id": None,
        "final_gate_preview_json": None,
        "trusted_submit_facts_json": None,
        "submit_idempotency_json": None,
        "attempt_outcome_policy_json": None,
        "protection_failure_policy_json": None,
        "local_registration_enablement_json": None,
        "exchange_submit_enablement_json": None,
        "exchange_action_authorization_json": None,
        "order_lifecycle_submit_enablement_json": None,
        "exchange_adapter_enablement_json": None,
        "deployment_readiness_json": None,
        "requested_fresh_submit_authorization_id": None,
        "expires_at_ms": None,
        "active_positions_count": 0,
        "output_dir": str(tmp_path / "artifacts"),
        "flow_id": "rtf063",
        "output_json": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)
