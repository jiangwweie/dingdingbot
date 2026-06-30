from __future__ import annotations

import json

from scripts.runtime_active_observation_status import build_status_artifact


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_status_summarizes_waiting_loop_without_side_effects(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "supervisor-artifact.json",
        {
            "status": "supervisor_running",
            "safety_invariants": {
                "real_submit_requested": False,
                "exchange_order_requested": False,
            },
        },
    )
    _write_json(
        root / "loop-artifact.json",
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
                "observation_plan": {
                    "next_step": "continue_waiting_for_strategy_signal"
                },
            },
            "observation_loop_plan": {
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

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "waiting_for_signal"
    assert artifact["iterations_requested"] == 5
    assert artifact["iterations_completed"] == 2
    assert artifact["iterations_remaining"] == 3
    assert artifact["latest_iteration"] == 2
    assert artifact["observation_running"] is True
    assert artifact["observation_window_complete"] is False
    assert "operator_command_plan" not in artifact
    assert artifact["observation_plan"]["not_execution_authority"] is True
    assert artifact["observation_plan"]["observation_next_step"] == (
        "continue_active_observation_loop"
    )
    assert artifact["active_runtime_count"] == 1
    assert artifact["monitored_runtime_count"] == 1
    assert artifact["selected_runtime_instance_ids"] == ["runtime-1"]
    assert artifact["runtime_signal_summaries"][0]["strategy_family_id"] == "CPM-001"
    assert artifact["runtime_signal_summaries"][0]["reason_codes"] == ["cpm_no_action"]
    assert "legacy_artifact_sources" not in artifact
    assert artifact["safety_invariants"]["read_artifacts_only"] is True
    assert artifact["safety_invariants"]["connects_to_api"] is False
    assert artifact["safety_invariants"]["places_order"] is False


def test_status_blocks_on_stale_artifacts(tmp_path):
    root = tmp_path / "obs"
    _write_json(root / "loop-artifact.json", {"status": "waiting_for_signal"})

    artifact = build_status_artifact(root, stale_after_seconds=0, now_ms=10**15)

    assert artifact["status"] == "stale"
    assert artifact["artifact_stale"] is True
    assert "active_observation_artifacts_stale_or_missing" in artifact["blockers"]


def test_status_ignores_legacy_packet_sources(tmp_path):
    root = tmp_path / "obs"
    _write_json(root / "loop-packet.json", {"status": "blocked"})

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "stale"
    assert artifact["latest_status"] is None
    assert "legacy_artifact_sources" not in artifact
    loop_source = next(
        source for source in artifact["artifact_sources"] if source["role"] == "loop"
    )
    assert loop_source == {
        "role": "loop",
        "artifact_name": "loop-artifact.json",
        "source_path": str(root / "loop-artifact.json"),
        "loaded": False,
    }


def test_status_blocks_on_forbidden_effects(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-artifact.json",
        {
            "status": "disabled_smoke_blocked",
            "safety_invariants": {"exchange_order_submitted": True},
        },
    )

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "blocked_forbidden_effect"
    assert "active_observation_forbidden_effects_detected" in artifact["blockers"]
    assert artifact["forbidden_effects"] == [
        "followup-artifact.json:exchange_order_submitted"
    ]
    assert "legacy_artifact_sources" not in artifact


def test_status_allows_standing_operation_layer_evidence_prep_effects(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-artifact.json",
        {
            "status": "disabled_smoke_blocked",
            "followup_plan": {
                "mutating_attempt_consumption_allowed_by_this_artifact": True
            },
            "safety_invariants": {
                "standing_authorized_operation_layer_evidence_prep_called": True,
                "attempt_counter_mutated": True,
                "runtime_budget_mutated": True,
                "exchange_called": False,
                "exchange_order_submitted": False,
                "order_created": False,
                "order_lifecycle_submit_called": False,
                "real_submit_requested": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "blocked"
    assert artifact["forbidden_effects"] == []
    assert "active_observation_forbidden_effects_detected" not in artifact["blockers"]
    assert artifact["allowed_operation_layer_evidence_prep_effects"] == [
        "followup-artifact.json:attempt_counter_mutated",
        "followup-artifact.json:runtime_budget_mutated",
    ]
    assert artifact["safety_invariants"][
        "allowed_operation_layer_evidence_prep_effects"
    ] == [
        "followup-artifact.json:attempt_counter_mutated",
        "followup-artifact.json:runtime_budget_mutated",
    ]


def test_status_blocks_evidence_prep_when_dangerous_effect_appears(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-artifact.json",
        {
            "status": "disabled_smoke_blocked",
            "followup_plan": {
                "mutating_attempt_consumption_allowed_by_this_artifact": True
            },
            "safety_invariants": {
                "standing_authorized_operation_layer_evidence_prep_called": True,
                "attempt_counter_mutated": True,
                "runtime_budget_mutated": True,
                "exchange_order_submitted": True,
            },
        },
    )

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["forbidden_effects"] == [
        "followup-artifact.json:exchange_order_submitted",
        "followup-artifact.json:attempt_counter_mutated",
        "followup-artifact.json:runtime_budget_mutated",
    ]


def test_status_marks_prepare_followup_as_attention(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-artifact.json",
        {
            "status": "ready_for_prepare_records",
            "followup_plan": {
                "next_step": "review_ready_signal_then_continue_prepare_record_path"
            },
            "safety_invariants": {
                "exchange_called": False,
                "order_created": False,
            },
        },
    )

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "attention"
    assert artifact["latest_status"] == "ready_for_prepare_records"
    assert artifact["observation_plan"]["followup_next_step"] == (
        "review_ready_signal_then_continue_prepare_record_path"
    )


def test_status_ignores_legacy_operator_command_plan_next_step(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "followup-artifact.json",
        {
            "status": "ready_for_prepare_records",
            "operator_command_plan": {
                "next_step": "legacy_operator_step_must_not_drive_status"
            },
            "safety_invariants": {
                "exchange_called": False,
                "order_created": False,
            },
        },
    )

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "attention"
    assert artifact["observation_plan"]["followup_next_step"] is None
    assert artifact["observation_plan"]["observation_next_step"] == (
        "review_non_executing_prepare_or_preview_artifact"
    )


def test_status_exposes_observed_prepare_record_evidence(tmp_path):
    root = tmp_path / "obs"
    _write_json(
        root / "loop-artifact.json",
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
                "signal_input_json": "/tmp/signal-input-ready.json",
                "prepared_authorization_id": "auth-ready-1",
                "runtime_signal_summaries": [
                    {
                        "runtime_instance_id": "runtime-1",
                        "strategy_family_id": "MPG-001",
                        "strategy_family_version_id": "MPG-001-v0",
                        "symbol": "COIN/USDT:USDT",
                        "side": "long",
                        "status": "ready_for_final_gate_preflight",
                        "signal_input_json": "/tmp/signal-input-ready.json",
                        "prepared_authorization_id": "auth-ready-1",
                    }
                ],
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

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "attention"
    assert artifact["latest_status"] == "ready_for_final_gate_preflight"
    assert artifact["signal_input_json"] == "/tmp/signal-input-ready.json"
    assert artifact["prepared_authorization_id"] == "auth-ready-1"
    assert artifact["runtime_signal_summaries"][0]["signal_input_json"] == (
        "/tmp/signal-input-ready.json"
    )
    assert artifact["runtime_signal_summaries"][0]["prepared_authorization_id"] == (
        "auth-ready-1"
    )
    assert artifact["allowed_prepare_record_effects"] == [
        "prepare_records_created",
        "shadow_candidate_created",
        "runtime_execution_intent_draft_created",
        "recorded_execution_intent_created",
        "submit_authorization_created",
        "protection_plan_created",
    ]
    safety = artifact["safety_invariants"]
    assert safety["read_artifacts_only"] is True
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
        root / "loop-artifact.json",
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
            "observation_loop_plan": {
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

    artifact = build_status_artifact(root, stale_after_seconds=10**15, now_ms=10**15)

    assert artifact["status"] == "observation_window_complete_no_signal"
    assert artifact["latest_status"] == "waiting_for_signal"
    assert artifact["iterations_requested"] == 3
    assert artifact["iterations_completed"] == 3
    assert artifact["iterations_remaining"] == 0
    assert artifact["observation_running"] is False
    assert artifact["observation_window_complete"] is True
    assert artifact["observation_plan"]["observation_next_step"] == (
        "review_no_signal_window_or_start_new_observation"
    )
    assert artifact["safety_invariants"]["places_order"] is False
