from __future__ import annotations

import json
from decimal import Decimal

import pytest

from scripts import runtime_active_position_resolution_from_reports
from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionArtifact,
    RuntimeActivePositionResolutionStatus,
    build_runtime_active_position_resolution_artifact,
)
from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorArtifact,
    RuntimeLivePositionMonitorStatus,
    RuntimeLiveProtectionStatus,
)
from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupArtifact,
    RuntimePostCloseFollowupStatus,
)
from src.domain.strategy_runtime import StrategyRuntimeInstanceStatus


NOW_MS = 1781256000000


def _monitor(**overrides) -> RuntimeLivePositionMonitorArtifact:
    values = {
        "monitor_id": "monitor-1",
        "runtime_instance_id": "runtime-1",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "status": RuntimeLivePositionMonitorStatus.ACTIVE_PROTECTION_WARNING,
        "protection_status": RuntimeLiveProtectionStatus.HARD_STOP_ONLY,
        "runtime_status": StrategyRuntimeInstanceStatus.ACTIVE,
        "runtime_execution_enabled": False,
        "runtime_shadow_mode": True,
        "active_position_present": True,
        "local_active_position_count": 1,
        "exchange_active_position_count": 1,
        "local_open_order_count": 1,
        "exchange_open_stop_order_count": 1,
        "sl_protection_present": True,
        "tp_protection_present": False,
        "hard_stop_boundary_present": True,
        "current_qty": Decimal("0.01"),
        "entry_price": Decimal("603.86"),
        "mark_price": Decimal("605"),
        "unrealized_pnl": Decimal("0.01"),
        "attempts_used": 1,
        "attempts_remaining": 2,
        "max_attempts": 3,
        "budget_reserved": Decimal("6"),
        "budget_remaining": Decimal("24"),
        "max_active_positions": 1,
        "reconciliation_severe_count": 0,
        "reconciliation_warning_count": 1,
        "reconciliation_mismatch_types": ["warning_only"],
        "blocks_new_entries_until_resolved": True,
        "can_continue_holding": True,
        "review_required_before_next_attempt": False,
        "owner_action_required": False,
        "blockers": ["runtime_max_active_positions_in_use"],
        "warnings": [
            "missing_tp_protection_right_tail_exit_not_mounted",
            "reconciliation_warning_present",
        ],
        "created_at_ms": NOW_MS,
    }
    values.update(overrides)
    return RuntimeLivePositionMonitorArtifact(**values)


def _exit_plan(**overrides) -> RuntimePositionExitPlan:
    values = {
        "plan_id": "exit-plan-1",
        "runtime_instance_id": "runtime-1",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "status": RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW,
        "source_monitor_id": "monitor-1",
        "active_position_present": True,
        "hard_stop_boundary_present": True,
        "existing_tp_protection_present": False,
        "current_qty": Decimal("0.01"),
        "entry_price": Decimal("603.86"),
        "stop_price_reference": Decimal("591.63"),
        "risk_per_unit": Decimal("12.23"),
        "tp1_price_reference": Decimal("616.09"),
        "tp1_quantity_requested": Decimal("0.005"),
        "tp1_quantity_step_aligned": Decimal("0"),
        "runner_quantity_reference": Decimal("0.01"),
        "tp1_reduce_only_side": "sell",
        "full_reduce_only_close_quantity": Decimal("0.01"),
        "full_reduce_only_close_notional_reference": Decimal("6.05"),
        "full_reduce_only_close_feasible": True,
        "full_reduce_only_close_requires_owner_authorization": False,
        "market_min_qty": Decimal("0.01"),
        "market_qty_step": Decimal("0.01"),
        "tp1_quantity_feasible": False,
        "recommended_recovery_action": (
            "keep_hard_stop_only_or_prepare_official_reduce_only_recovery"
        ),
        "blockers": [],
        "warnings": ["tp1_partial_quantity_below_min_qty_or_step"],
        "created_at_ms": NOW_MS,
    }
    values.update(overrides)
    return RuntimePositionExitPlan(**values)


def _followup(**overrides) -> RuntimePostCloseFollowupArtifact:
    values = {
        "artifact_id": "followup-1",
        "status": RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY,
        "runtime_instance_id": "runtime-1",
        "symbol": "BNB/USDT:USDT",
        "active_position_present": True,
        "source_monitor_id": "monitor-1",
        "owner_close_evidence_status": "ready_for_standing_recovery_authorization",
        "owner_close_approval_env": None,
        "owner_close_approval_value": None,
        "standing_recovery_authorization_scope": (
            "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
        ),
        "closed_review_facts_status": "waiting_for_close",
        "closed_review_recorded": False,
        "required_steps": [
            "prepare_official_operation_layer_reduce_only_recovery",
            "run_action_time_finalgate_for_reduce_only_recovery",
            "execute_reduce_only_recovery_through_operation_layer",
            "verify_runtime_live_position_monitor_flat",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ],
        "completed_steps": ["fresh_monitor_read", "owner_close_artifact_built"],
        "recommended_review_checkpoint": "prepare_official_reduce_only_recovery_or_continue_holding",
        "blockers": [],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "created_at_ms": NOW_MS,
    }
    values.update(overrides)
    return RuntimePostCloseFollowupArtifact(**values)


def test_resolution_holds_protected_position_and_blocks_new_attempts():
    artifact = build_runtime_active_position_resolution_artifact(
        monitor=_monitor(),
        exit_plan=_exit_plan(),
        post_close_followup=_followup(),
        now_ms=NOW_MS,
    )

    assert artifact.status == RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP
    assert artifact.can_continue_holding is True
    assert artifact.next_attempt_blocked_by_active_position is True
    assert artifact.full_reduce_only_close_feasible is True
    assert artifact.owner_close_approval_value is None
    assert artifact.standing_recovery_authorization_scope == (
        "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
    )
    assert "optional_prepare_official_reduce_only_recovery" in artifact.required_steps
    assert artifact.exchange_order_submitted is False
    assert artifact.order_lifecycle_called is False
    assert artifact.position_closed is False
    payload = artifact.model_dump(mode="json")
    assert payload["active_position_resolution_evidence_only"] is True
    assert "packet_only" not in payload


def test_resolution_blocks_unprotected_active_position():
    monitor = _monitor(
        status=RuntimeLivePositionMonitorStatus.ACTIVE_UNPROTECTED,
        protection_status=RuntimeLiveProtectionStatus.HARD_STOP_MISSING,
        hard_stop_boundary_present=False,
        sl_protection_present=False,
        can_continue_holding=False,
        owner_action_required=True,
        blockers=["active_position_missing_hard_stop"],
    )

    artifact = build_runtime_active_position_resolution_artifact(
        monitor=monitor,
        exit_plan=None,
        post_close_followup=None,
        now_ms=NOW_MS,
    )

    assert artifact.status == RuntimeActivePositionResolutionStatus.BLOCKED
    assert "active_position_missing_hard_stop" in artifact.blockers
    assert artifact.next_attempt_blocked_by_active_position is True


def test_resolution_routes_flat_runtime_to_closed_review():
    monitor = _monitor(
        status=RuntimeLivePositionMonitorStatus.FLAT_REVIEW_REQUIRED,
        protection_status=RuntimeLiveProtectionStatus.NO_ACTIVE_POSITION,
        active_position_present=False,
        local_active_position_count=0,
        exchange_active_position_count=0,
        local_open_order_count=0,
        exchange_open_stop_order_count=0,
        current_qty=None,
        entry_price=None,
        mark_price=None,
        unrealized_pnl=None,
        hard_stop_boundary_present=False,
        sl_protection_present=False,
        tp_protection_present=False,
        blocks_new_entries_until_resolved=True,
        can_continue_holding=False,
        review_required_before_next_attempt=True,
        owner_action_required=True,
        blockers=[],
        warnings=[],
    )
    followup = _followup(
        status=RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW,
        active_position_present=False,
        owner_close_evidence_status=None,
        owner_close_approval_env=None,
        owner_close_approval_value=None,
        closed_review_facts_status="ready_for_closed_review",
        required_steps=[
            "use_resolved_closed_review_order_ids",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ],
        completed_steps=["runtime_flat_observed", "closed_review_facts_resolved"],
        recommended_review_checkpoint="run_closed_trade_review_from_resolved_order_facts",
    )

    artifact = build_runtime_active_position_resolution_artifact(
        monitor=monitor,
        exit_plan=None,
        post_close_followup=followup,
        now_ms=NOW_MS,
    )

    assert artifact.status == RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW
    assert artifact.active_position_present is False
    assert artifact.next_attempt_blocked_by_active_position is False
    assert "record_runtime_closed_trade_review" in artifact.required_steps


def test_resolution_rejects_legacy_packet_only_input():
    artifact = build_runtime_active_position_resolution_artifact(
        monitor=_monitor(),
        exit_plan=_exit_plan(),
        post_close_followup=_followup(),
        now_ms=NOW_MS,
    )
    legacy_payload = artifact.model_dump(mode="json")
    legacy_payload["packet_only"] = legacy_payload.pop(
        "active_position_resolution_evidence_only",
    )

    with pytest.raises(ValueError):
        RuntimeActivePositionResolutionArtifact.model_validate(legacy_payload)


def test_resolution_from_reports_output_is_projection_only(tmp_path, capsys):
    monitor_path = tmp_path / "monitor.json"
    exit_path = tmp_path / "exit-plan.json"
    followup_path = tmp_path / "followup.json"

    monitor_path.write_text(
        json.dumps({"artifact": _monitor().model_dump(mode="json")}),
        encoding="utf-8",
    )
    exit_path.write_text(
        json.dumps({"plan": _exit_plan().model_dump(mode="json")}),
        encoding="utf-8",
    )
    followup_path.write_text(
        json.dumps({"artifact": _followup().model_dump(mode="json")}),
        encoding="utf-8",
    )

    assert runtime_active_position_resolution_from_reports.main(
        [
            "--live-position-monitor-json",
            str(monitor_path),
            "--position-exit-plan-json",
            str(exit_path),
            "--post-close-followup-json",
            str(followup_path),
            "--now-ms",
            str(NOW_MS),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "hold_with_hard_stop"
    assert "artifact" in output
    assert "packet" not in output
    assert (
        output["safety_invariants"]["active_position_resolution_projection_only"]
        is True
    )
    assert "packet_only" not in output["safety_invariants"]
    assert output["safety_invariants"]["exchange_write_called"] is False
    assert output["safety_invariants"]["order_lifecycle_called"] is False
