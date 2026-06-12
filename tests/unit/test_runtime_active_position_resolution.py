from __future__ import annotations

from decimal import Decimal

from src.domain.runtime_active_position_resolution import (
    RuntimeActivePositionResolutionStatus,
    build_runtime_active_position_resolution_packet,
)
from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorPacket,
    RuntimeLivePositionMonitorStatus,
    RuntimeLiveProtectionStatus,
)
from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupPacket,
    RuntimePostCloseFollowupStatus,
)
from src.domain.strategy_runtime import StrategyRuntimeInstanceStatus


NOW_MS = 1781256000000


def _monitor(**overrides) -> RuntimeLivePositionMonitorPacket:
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
    return RuntimeLivePositionMonitorPacket(**values)


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
        "full_reduce_only_close_requires_owner_authorization": True,
        "market_min_qty": Decimal("0.01"),
        "market_qty_step": Decimal("0.01"),
        "tp1_quantity_feasible": False,
        "recommended_owner_decision": (
            "keep_hard_stop_only_or_owner_authorize_full_reduce_only_close"
        ),
        "blockers": [],
        "warnings": ["tp1_partial_quantity_below_min_qty_or_step"],
        "created_at_ms": NOW_MS,
    }
    values.update(overrides)
    return RuntimePositionExitPlan(**values)


def _followup(**overrides) -> RuntimePostCloseFollowupPacket:
    values = {
        "packet_id": "followup-1",
        "status": RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION,
        "runtime_instance_id": "runtime-1",
        "symbol": "BNB/USDT:USDT",
        "active_position_present": True,
        "source_monitor_id": "monitor-1",
        "owner_close_packet_status": "ready_for_owner_authorization",
        "owner_close_approval_env": "OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE",
        "owner_close_approval_value": (
            "runtime-reduce-only-close:runtime-1:BNB/USDT:USDT:long:"
            "qty=0.01:owner-authorized"
        ),
        "closed_review_facts_status": "waiting_for_close",
        "closed_review_recorded": False,
        "required_steps": [
            "owner_authorize_exact_reduce_only_close_value",
            "execute_runtime_owner_reduce_only_close_flow",
            "verify_runtime_live_position_monitor_flat",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ],
        "completed_steps": ["fresh_monitor_read", "owner_close_packet_built"],
        "recommended_next_action": "owner_authorize_reduce_only_close_or_continue_holding",
        "blockers": [],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "created_at_ms": NOW_MS,
    }
    values.update(overrides)
    return RuntimePostCloseFollowupPacket(**values)


def test_resolution_holds_protected_position_and_blocks_new_attempts():
    packet = build_runtime_active_position_resolution_packet(
        monitor=_monitor(),
        exit_plan=_exit_plan(),
        post_close_followup=_followup(),
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeActivePositionResolutionStatus.HOLD_WITH_HARD_STOP
    assert packet.can_continue_holding is True
    assert packet.next_attempt_blocked_by_active_position is True
    assert packet.full_reduce_only_close_feasible is True
    assert packet.owner_close_approval_value.endswith("qty=0.01:owner-authorized")
    assert "optional_owner_authorize_exact_reduce_only_close" in packet.required_steps
    assert packet.exchange_order_submitted is False
    assert packet.order_lifecycle_called is False
    assert packet.position_closed is False


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

    packet = build_runtime_active_position_resolution_packet(
        monitor=monitor,
        exit_plan=None,
        post_close_followup=None,
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeActivePositionResolutionStatus.BLOCKED
    assert "active_position_missing_hard_stop" in packet.blockers
    assert packet.next_attempt_blocked_by_active_position is True


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
        owner_close_packet_status=None,
        owner_close_approval_env=None,
        owner_close_approval_value=None,
        closed_review_facts_status="ready_for_closed_review",
        required_steps=[
            "use_resolved_closed_review_order_ids",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ],
        completed_steps=["runtime_flat_observed", "closed_review_facts_resolved"],
        recommended_next_action="run_closed_trade_review_from_resolved_order_facts",
    )

    packet = build_runtime_active_position_resolution_packet(
        monitor=monitor,
        exit_plan=None,
        post_close_followup=followup,
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeActivePositionResolutionStatus.READY_FOR_CLOSED_REVIEW
    assert packet.active_position_present is False
    assert packet.next_attempt_blocked_by_active_position is False
    assert "record_runtime_closed_trade_review" in packet.required_steps
