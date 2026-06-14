from __future__ import annotations

import json
from pathlib import Path

from scripts.build_runtime_signal_watcher_readiness_pack import build_pack


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_runtime_signal_watcher_readiness_pack_ready_for_resume(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_notified",
            "wakeup_status": "prepared_shadow_evidence_ready_for_owner_review",
            "operator_status": "strategy_group_signal_review_available",
            "status_packet_status": "ok",
            "notification": {
                "configured": True,
                "attempted": True,
                "sent": True,
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
            "post_signal_auto_resume": {
                "status": "ready_for_action_time_final_gate",
                "blocked_at": "FinalGate",
                "blocked_reason": "action_time_final_gate_not_run_yet",
                "next_recover_condition": (
                    "official_final_gate_preflight_passes_with_current_facts"
                ),
                "automatic_recovery_action": (
                    "run_official_action_time_final_gate_preflight"
                ),
                "downgrade_mode": "no_real_submit_until_final_gate_pass",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(report_dir / "wakeup-packet.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-packet.json", {"status": "strategy_group_signal_review_available"})
    _write(
        report_dir / "status-packet.json",
        {
            "status": "ok",
            "blockers": [],
            "warnings": [],
            "active_runtime_count": 1,
            "monitored_runtime_count": 1,
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "signal_input_json": "/reports/runtime-mpg-1/signal-input.json",
            "prepared_authorization_id": "auth-ready-1",
            "shadow_candidate_id": "shadow-candidate-1",
            "runtime_signal_summaries": [
                {
                    "runtime_instance_id": "runtime-mpg-1",
                    "strategy_family_id": "MPG-001",
                    "strategy_family_version_id": "MPG-001-v0",
                    "symbol": "COIN/USDT:USDT",
                    "side": "long",
                    "status": "waiting_for_signal",
                }
            ],
        },
    )
    _write(report_dir / "notification-state.json", {"last_notified_event_key": "ready-event"})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    deployment = json.loads((output_dir / "deployment-readiness-packet.json").read_text())
    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["deployment_status"] == "ready"
    assert summary["resume_status"] == "ready_for_steps_5_8"
    assert summary["can_continue_steps_5_8"] is True
    assert deployment["notification"]["duplicate_suppression_observed"] is True
    assert deployment["safety_invariants"]["exchange_write_called"] is False
    assert deployment["post_signal_auto_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert resume["can_continue_steps_5_8"] is True
    assert resume["post_signal_auto_resume"]["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert resume["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert resume["can_continue_without_owner_chat"] is True
    assert resume["requires_action_time_final_gate"] is True
    assert resume["requires_official_operation_layer"] is True
    assert resume["selected_runtime_instance_ids"] == ["runtime-mpg-1"]
    assert resume["signal_input_json"] == "/reports/runtime-mpg-1/signal-input.json"
    assert resume["prepared_authorization_id"] == "auth-ready-1"
    assert resume["shadow_candidate_id"] == "shadow-candidate-1"
    assert resume["prepared_evidence"] == {
        "signal_input_json": "/reports/runtime-mpg-1/signal-input.json",
        "shadow_candidate_id": "shadow-candidate-1",
        "prepared_authorization_id": "auth-ready-1",
        "ready_for_action_time_final_gate": True,
    }
    assert resume["action_time_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert resume["action_time_resume"]["next_step"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert resume["action_time_resume"]["allowed_auto_actions"] == [
        "run_official_action_time_final_gate_preflight"
    ]
    assert "official_operation_layer_submit" in resume["action_time_resume"][
        "forbidden_auto_actions_until_final_gate_pass"
    ]
    assert resume["action_time_resume"]["requires_fresh_action_time_facts"] is True
    assert resume["action_time_resume"]["places_order"] is False
    assert resume["runtime_signal_summaries"] == [
        {
            "runtime_instance_id": "runtime-mpg-1",
            "strategy_family_id": "MPG-001",
            "strategy_family_version_id": "MPG-001-v0",
            "symbol": "COIN/USDT:USDT",
            "side": "long",
            "status": "waiting_for_signal",
        }
    ]
    assert "action-time FinalGate" in resume["required_before_real_submit"]


def test_build_runtime_signal_watcher_readiness_pack_blocks_unsafe_effect(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_notified",
            "wakeup_status": "prepared_shadow_evidence_ready_for_owner_review",
            "operator_status": "strategy_group_signal_review_available",
            "notification": {"configured": True},
            "safety_invariants": {
                "exchange_write_called": True,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        },
    )
    _write(report_dir / "wakeup-packet.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-packet.json", {"status": "strategy_group_signal_review_available"})
    _write(report_dir / "status-packet.json", {"status": "ok"})
    _write(report_dir / "notification-state.json", {})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["deployment_status"] == "unsafe_watcher_effect_detected"
    assert summary["can_continue_steps_5_8"] is False
    assert resume["status"] == "blocked"
    assert "exchange_write_called" in resume["blockers"]
    assert resume["action_time_resume"]["status"] == "blocked"
    assert resume["action_time_resume"]["allowed_auto_actions"] == []
