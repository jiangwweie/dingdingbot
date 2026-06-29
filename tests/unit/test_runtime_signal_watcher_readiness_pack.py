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
            "status_packet_status": "legacy_tick_status_must_not_win",
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
                "non_authority_checkpoint": (
                    "run_official_action_time_final_gate_preflight"
                ),
                "checkpoint_source": "runtime_signal_watcher_tick",
                "downgrade_mode": "no_real_submit_until_final_gate_pass",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(report_dir / "wakeup-evidence.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-evidence.json", {"status": "strategy_group_signal_review_available"})
    _write(
        report_dir / "status-artifact.json",
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

    deployment = json.loads((output_dir / "deployment-readiness-artifact.json").read_text())
    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["deployment_readiness_artifact"].endswith(
        "deployment-readiness-artifact.json"
    )
    assert "deployment_readiness_packet" not in summary
    assert summary["deployment_status"] == "ready"
    assert summary["resume_status"] == "ready_for_action_time_final_gate"
    assert summary["can_continue_steps_5_8"] is True
    assert deployment["notification"]["duplicate_suppression_observed"] is True
    assert deployment["watcher_status"]["watcher_status_evidence_status"] == "ok"
    assert "status_packet_status" not in deployment["watcher_status"]
    assert deployment["safety_invariants"]["exchange_write_called"] is False
    assert deployment["post_signal_auto_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert resume["can_continue_steps_5_8"] is True
    assert resume["current_watcher_status_evidence_status"] == "ok"
    assert "current_status_packet_status" not in resume
    assert "automatic_recovery_action" not in resume["post_signal_auto_resume"]
    assert resume["post_signal_auto_resume"]["non_authority_checkpoint"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert "automatic_recovery_action" not in resume
    assert resume["non_authority_checkpoint"] == (
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
    assert resume["owner_state"]["status"] == "ready_for_action_time_final_gate"
    assert "automatic_recovery_action" not in resume["owner_state"]
    assert resume["owner_state"]["non_authority_checkpoint"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert resume["owner_state"]["checkpoint_source"] == "action_time_resume"
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


def test_build_runtime_signal_watcher_readiness_pack_owner_state_prefers_allowed_action(
    tmp_path,
):
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
                "automatic_recovery_action": "legacy_next_step_must_not_win",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(
        report_dir / "wakeup-evidence.json",
        {"status": "prepared_shadow_evidence_ready_for_owner_review"},
    )
    _write(report_dir / "operator-evidence.json", {"status": "strategy_group_signal_review_available"})
    _write(
        report_dir / "status-artifact.json",
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
                    "status": "waiting_for_signal",
                }
            ],
        },
    )
    _write(report_dir / "notification-state.json", {})

    build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert resume["action_time_resume"]["allowed_auto_actions"] == [
        "run_official_action_time_final_gate_preflight"
    ]
    assert "automatic_recovery_action" not in resume["owner_state"]
    assert resume["owner_state"]["non_authority_checkpoint"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert resume["owner_state"]["checkpoint_source"] == "action_time_resume"


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
    _write(report_dir / "wakeup-evidence.json", {"status": "prepared_shadow_evidence_ready_for_owner_review"})
    _write(report_dir / "operator-evidence.json", {"status": "strategy_group_signal_review_available"})
    _write(report_dir / "status-artifact.json", {"status": "ok"})
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


def test_build_runtime_signal_watcher_readiness_pack_ignores_legacy_watcher_packet_files(
    tmp_path,
):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "watching_no_signal",
            "notification": {"configured": True},
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
            "post_signal_auto_resume": {
                "status": "waiting_for_market",
                "automatic_recovery_action": "continue_watcher_observation",
            },
        },
    )
    _write(report_dir / "wakeup-packet.json", {"status": "operator_evidence_needs_review"})
    _write(report_dir / "operator-packet.json", {"status": "operator_review"})
    _write(report_dir / "status-artifact.json", {"status": "ok"})
    _write(report_dir / "notification-state.json", {})

    build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    deployment = json.loads((output_dir / "deployment-readiness-artifact.json").read_text())
    assert deployment["files"]["wakeup_evidence"]["path"].endswith("wakeup-evidence.json")
    assert deployment["files"]["operator_evidence"]["path"].endswith("operator-evidence.json")
    assert deployment["files"]["wakeup_evidence"]["present"] is False
    assert deployment["files"]["operator_evidence"]["present"] is False
    assert deployment["watcher_status"]["wakeup_status"] == "unknown"
    assert deployment["watcher_status"]["operator_status"] == "unknown"


def test_build_runtime_signal_watcher_readiness_pack_preserves_non_executing_prepare_checkpoint(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_attention_pending",
            "wakeup_status": "runtime_signal_ready_for_non_executing_prepare",
            "operator_status": "operator_review",
            "status_packet_status": "attention",
            "notification": {
                "configured": True,
                "attempted": False,
                "sent": False,
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
                "status": "ready_for_non_executing_prepare",
                "blocked_at": "non_executing_prepare_records",
                "blocked_reason": "fresh_strategy_signal_ready",
                "next_recover_condition": (
                    "shadow_candidate_runtime_grant_authorization_evidence_exists"
                ),
                "automatic_recovery_action": (
                    "wait_for_prepare_records_then_rebuild_final_gate_status"
                ),
                "downgrade_mode": "armed_observation_no_real_submit",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(
        report_dir / "wakeup-evidence.json",
        {"status": "runtime_signal_ready_for_non_executing_prepare"},
    )
    _write(report_dir / "operator-evidence.json", {"status": "operator_review"})
    _write(
        report_dir / "status-artifact.json",
        {
            "status": "attention",
            "blockers": [],
            "warnings": [],
            "active_runtime_count": 1,
            "monitored_runtime_count": 1,
            "selected_runtime_instance_ids": ["runtime-mpg-1"],
            "signal_input_json": "/reports/runtime-mpg-1/signal-input.json",
            "prepared_authorization_id": None,
            "shadow_candidate_id": None,
            "runtime_signal_summaries": [
                {
                    "runtime_instance_id": "runtime-mpg-1",
                    "strategy_family_id": "MPG-001",
                    "strategy_family_version_id": "MPG-001-v0",
                    "symbol": "MSTR/USDT:USDT",
                    "side": "long",
                    "status": "ready_for_prepare",
                }
            ],
        },
    )
    _write(report_dir / "notification-state.json", {})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["resume_status"] == "ready_for_non_executing_prepare"
    assert summary["can_continue_steps_5_8"] is True
    assert resume["status"] == "ready_for_non_executing_prepare"
    assert resume["owner_state"]["blocker_class"] == "none"
    assert "automatic_recovery_action" not in resume["owner_state"]
    assert resume["owner_state"]["non_authority_checkpoint"] == (
        "prepare_fresh_candidate_authorization_evidence"
    )
    assert resume["owner_state"]["checkpoint_source"] == "action_time_resume"
    assert resume["action_time_resume"]["status"] == (
        "ready_for_non_executing_prepare"
    )
    assert resume["action_time_resume"]["next_step"] == (
        "prepare_fresh_candidate_grant_authorization_evidence"
    )
    assert resume["action_time_resume"]["allowed_auto_actions"] == [
        "prepare_fresh_candidate_authorization_evidence"
    ]
    assert resume["action_time_resume"][
        "requires_fresh_candidate_authorization_evidence"
    ] is True
    assert resume["action_time_resume"]["places_order"] is False
    assert resume["action_time_resume"]["exchange_write_called"] is False


def test_build_runtime_signal_watcher_readiness_pack_downgrades_ready_without_actionable_signal(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "owner_attention_pending",
            "wakeup_status": "runtime_signal_ready_for_non_executing_prepare",
            "operator_status": "operator_review",
            "status_packet_status": "ok",
            "notification": {
                "configured": True,
                "attempted": False,
                "sent": False,
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
                "status": "ready_for_non_executing_prepare",
                "blocked_at": "non_executing_prepare_records",
                "blocked_reason": "fresh_strategy_signal_ready",
                "next_recover_condition": (
                    "shadow_candidate_runtime_grant_authorization_evidence_exists"
                ),
                "automatic_recovery_action": (
                    "wait_for_prepare_records_then_rebuild_final_gate_status"
                ),
                "downgrade_mode": "armed_observation_no_real_submit",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(
        report_dir / "wakeup-evidence.json",
        {"status": "runtime_signal_ready_for_non_executing_prepare"},
    )
    _write(report_dir / "operator-evidence.json", {"status": "operator_review"})
    _write(
        report_dir / "status-artifact.json",
        {
            "status": "ok",
            "blockers": [],
            "warnings": [],
            "active_runtime_count": 2,
            "monitored_runtime_count": 2,
            "selected_runtime_instance_ids": ["runtime-mpg-1", "runtime-sor-1"],
            "signal_input_json": None,
            "prepared_authorization_id": None,
            "shadow_candidate_id": None,
            "runtime_signal_summaries": [
                {
                    "runtime_instance_id": "runtime-mpg-1",
                    "strategy_family_id": "MPG-001",
                    "symbol": "MSTR/USDT:USDT",
                    "side": "long",
                    "status": "waiting_for_signal",
                },
                {
                    "runtime_instance_id": "runtime-sor-1",
                    "strategy_family_id": "SOR-001",
                    "symbol": "XAG/USDT:USDT",
                    "side": "short",
                    "status": "waiting_for_signal",
                },
            ],
        },
    )
    _write(report_dir / "notification-state.json", {})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["resume_status"] == "waiting_for_market"
    assert summary["can_continue_steps_5_8"] is False
    assert resume["status"] == "waiting_for_market"
    assert resume["owner_state"]["blocker_class"] == "waiting_for_market"
    assert resume["post_signal_resume_normalization"] == {
        "actionable_runtime_signal": False,
        "normalized_ready_status_without_actionable_signal": True,
    }
    assert resume["action_time_resume"]["allowed_auto_actions"] == [
        "continue_watcher_observation"
    ]
    assert resume["safety_invariants"]["places_order"] is False
    assert resume["safety_invariants"]["mutates_pg"] is False
    assert "normalized_ready_status_without_actionable_signal" in resume["warnings"]


def test_build_runtime_signal_watcher_readiness_pack_normalizes_no_signal(tmp_path):
    report_dir = tmp_path / "report"
    output_dir = tmp_path / "out"
    report_dir.mkdir()
    _write(
        report_dir / "watcher-tick.json",
        {
            "status": "watching_no_signal",
            "wakeup_status": "operator_evidence_needs_review",
            "operator_status": "operator_review",
            "status_packet_status": "ok",
            "blockers": [
                "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "notification": {
                "configured": True,
                "attempted": False,
                "sent": False,
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
                "status": "waiting_for_market",
                "blocked_at": "watcher_signal",
                "blocked_reason": "no_fresh_strategy_signal",
                "next_recover_condition": (
                    "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
                ),
                "automatic_recovery_action": "continue_watcher_observation",
                "downgrade_mode": "observe_only",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
        },
    )
    _write(report_dir / "wakeup-evidence.json", {"status": "operator_evidence_needs_review"})
    _write(report_dir / "operator-evidence.json", {"status": "operator_review"})
    _write(
        report_dir / "status-artifact.json",
        {
            "status": "ok",
            "blockers": [
                "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "warnings": [],
            "active_runtime_count": 1,
            "monitored_runtime_count": 1,
            "selected_runtime_instance_ids": ["runtime-1"],
            "prepared_authorization_id": None,
            "shadow_candidate_id": None,
            "signal_input_json": None,
        },
    )
    _write(report_dir / "notification-state.json", {})

    summary = build_pack(
        report_dir=report_dir,
        output_dir=output_dir,
        stale_after_seconds=180,
        label="unit-test",
    )

    resume = json.loads((output_dir / "post-signal-resume-pack.json").read_text())
    assert summary["resume_status"] == "waiting_for_market"
    assert summary["can_continue_steps_5_8"] is False
    assert resume["status"] == "waiting_for_market"
    assert resume["owner_state"] == {
        "status": "waiting_for_market",
        "blocker_class": "waiting_for_market",
        "blocked_at": "watcher_signal",
        "blocked_reason": "no_fresh_strategy_signal",
        "next_recover_condition": (
            "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
        ),
        "non_authority_checkpoint": "continue_watcher_observation",
        "checkpoint_source": "action_time_resume",
        "downgrade_mode": "observe_only",
    }
    assert resume["action_time_resume"]["status"] == "waiting_for_market"
    assert resume["action_time_resume"]["allowed_auto_actions"] == [
        "continue_watcher_observation"
    ]
    assert resume["action_time_resume"]["places_order"] is False
