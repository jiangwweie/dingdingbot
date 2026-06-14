from __future__ import annotations

import json

from scripts.runtime_active_observation_status import build_status_packet


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_status_summarizes_waiting_loop_without_side_effects(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "supervisor-packet.json",
        {
            "status": "supervisor_running",
            "safety_invariants": {
                "real_submit_requested": False,
                "exchange_order_requested": False,
            },
        },
    )
    _write_json(
        root / "loop-packet.json",
        {
            "status": "waiting_for_signal",
            "iterations_requested": 5,
            "iterations_completed": 2,
            "stop_reason": "running",
            "latest_summary": {
                "iteration": 2,
                "active_runtime_count": 1,
                "monitored_runtime_count": 1,
                "selected_runtime_instance_ids": ["runtime-1"],
                "runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-1",
                        "strategy_family_id": "CPM-001",
                        "strategy_family_version_id": "CPM-001-v0",
                        "symbol": "BNB/USDT:USDT",
                        "side": "long",
                        "status": "waiting_for_signal",
                        "signal_summary": {
                            "evaluation_status": "observe_only",
                            "signal_type": "no_action",
                            "side": "none",
                            "confidence": "0.25",
                            "reason_codes": ["cpm_no_action"],
                            "human_summary": "No CPM action.",
                        },
                    }
                ],
                "operator_command_plan": {
                    "next_step": "continue_waiting_for_strategy_signal"
                },
            },
            "operator_command_plan": {
                "next_step": "continue_waiting_for_strategy_signal"
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_status_packet(root, stale_after_seconds=10**15, now_ms=10**15)

    assert packet["status"] == "waiting_for_signal"
    assert packet["iterations_requested"] == 5
    assert packet["iterations_completed"] == 2
    assert packet["iterations_remaining"] == 3
    assert packet["latest_iteration"] == 2
    assert packet["observation_running"] is True
    assert packet["observation_window_complete"] is False
    assert packet["operator_command_plan"]["observation_next_step"] == (
        "continue_active_observation_loop"
    )
    assert packet["active_runtime_count"] == 1
    assert packet["monitored_runtime_count"] == 1
    assert packet["selected_runtime_instance_ids"] == ["runtime-1"]
    assert packet["runtime_signal_summaries"][0]["strategy_family_id"] == "CPM-001"
    assert packet["runtime_signal_summaries"][0]["reason_codes"] == ["cpm_no_action"]
    assert packet["safety_invariants"]["read_packets_only"] is True
    assert packet["safety_invariants"]["connects_to_api"] is False
    assert packet["safety_invariants"]["places_order"] is False


def test_status_blocks_on_stale_packets(tmp_path):
    root = tmp_path / "obs"
    _write_json(root / "loop-packet.json", {"status": "waiting_for_signal"})

    packet = build_status_packet(root, stale_after_seconds=0, now_ms=10**15)

    assert packet["status"] == "stale"
    assert packet["packet_stale"] is True
    assert "active_observation_packets_stale_or_missing" in packet["blockers"]


def test_status_blocks_on_forbidden_effects(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-packet.json",
        {
            "status": "disabled_smoke_blocked",
            "safety_invariants": {"exchange_order_submitted": True},
        },
    )

    packet = build_status_packet(root, stale_after_seconds=10**15, now_ms=10**15)

    assert packet["status"] == "blocked_forbidden_effect"
    assert "active_observation_forbidden_effects_detected" in packet["blockers"]
    assert packet["forbidden_effects"] == [
        "followup-packet.json:exchange_order_submitted"
    ]


def test_status_marks_prepare_followup_as_attention(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-packet.json",
        {
            "status": "ready_for_prepare_records",
            "operator_command_plan": {
                "next_step": "review_ready_signal_then_continue_prepare_record_path"
            },
            "safety_invariants": {
                "exchange_called": False,
                "order_created": False,
            },
        },
    )

    packet = build_status_packet(root, stale_after_seconds=10**15, now_ms=10**15)

    assert packet["status"] == "attention"
    assert packet["latest_status"] == "ready_for_prepare_records"
    assert packet["operator_command_plan"]["followup_next_step"] == (
        "review_ready_signal_then_continue_prepare_record_path"
    )


def test_status_exposes_observed_prepare_record_evidence(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "loop-packet.json",
        {
            "status": "ready_for_final_gate_preflight",
            "latest_summary": {
                "iteration": 1,
                "active_runtime_count": 1,
                "monitored_runtime_count": 1,
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "prepared_authorization_id": "auth-ready-1",
            },
            "safety_invariants": {
                "prepare_records_created": True,
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "recorded_execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
            },
        },
    )

    packet = build_status_packet(root, stale_after_seconds=10**15, now_ms=10**15)

    assert packet["status"] == "attention"
    assert packet["latest_status"] == "ready_for_final_gate_preflight"
    assert packet["prepared_authorization_id"] == "auth-ready-1"
    assert packet["allowed_prepare_record_effects"] == [
        "prepare_records_created",
        "shadow_candidate_created",
        "runtime_execution_intent_draft_created",
        "recorded_execution_intent_created",
        "submit_authorization_created",
        "protection_plan_created",
    ]
    safety = packet["safety_invariants"]
    assert safety["read_packets_only"] is True
    assert safety["creates_prepare_records"] is False
    assert safety["observed_prepare_records_created"] is True
    assert safety["observed_shadow_candidate_created"] is True
    assert safety["observed_runtime_execution_intent_draft_created"] is True
    assert safety["observed_recorded_execution_intent_created"] is True
    assert safety["observed_submit_authorization_created"] is True
    assert safety["observed_protection_plan_created"] is True
    assert safety["places_order"] is False


def test_status_marks_exhausted_waiting_window_as_complete_no_signal(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "loop-packet.json",
        {
            "status": "waiting_for_signal",
            "iterations_requested": 3,
            "iterations_completed": 3,
            "stop_reason": "max_iterations_exhausted",
            "latest_summary": {
                "iteration": 3,
                "active_runtime_count": 2,
                "monitored_runtime_count": 0,
                "runtime_signal_summaries": [],
            },
            "operator_command_plan": {
                "next_step": "continue_waiting_for_strategy_signal"
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    packet = build_status_packet(root, stale_after_seconds=10**15, now_ms=10**15)

    assert packet["status"] == "observation_window_complete_no_signal"
    assert packet["latest_status"] == "waiting_for_signal"
    assert packet["iterations_requested"] == 3
    assert packet["iterations_completed"] == 3
    assert packet["iterations_remaining"] == 0
    assert packet["observation_running"] is False
    assert packet["observation_window_complete"] is True
    assert packet["operator_command_plan"]["observation_next_step"] == (
        "review_no_signal_window_or_start_new_observation"
    )
    assert packet["safety_invariants"]["places_order"] is False
