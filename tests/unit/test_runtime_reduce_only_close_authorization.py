from __future__ import annotations

from decimal import Decimal

from src.domain.runtime_position_exit_plan import (
    RuntimePositionExitPlan,
    RuntimePositionExitPlanStatus,
)
from src.domain.runtime_reduce_only_close_authorization import (
    OWNER_REDUCE_ONLY_CLOSE_APPROVAL_ENV,
    RuntimeReduceOnlyCloseOwnerPacketStatus,
    STANDING_REDUCE_ONLY_RECOVERY_SCOPE,
    build_runtime_reduce_only_close_owner_packet,
)


def _exit_plan(**overrides) -> RuntimePositionExitPlan:
    data = {
        "plan_id": "exit-plan-1",
        "runtime_instance_id": "runtime-1",
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "status": RuntimePositionExitPlanStatus.READY_FOR_OWNER_REVIEW,
        "source_monitor_id": "monitor-1",
        "active_position_present": True,
        "hard_stop_boundary_present": True,
        "existing_tp_protection_present": False,
        "current_qty": Decimal("1.0"),
        "entry_price": Decimal("6.566"),
        "stop_price_reference": Decimal("6.639"),
        "risk_per_unit": Decimal("0.073"),
        "tp1_price_reference": Decimal("6.493"),
        "tp1_quantity_requested": Decimal("0.50"),
        "tp1_quantity_step_aligned": Decimal("0.0"),
        "runner_quantity_reference": Decimal("1.0"),
        "tp1_reduce_only_side": "buy",
        "full_reduce_only_close_quantity": Decimal("1.0"),
        "full_reduce_only_close_notional_reference": Decimal("6.57"),
        "full_reduce_only_close_feasible": True,
        "full_reduce_only_close_requires_owner_authorization": False,
        "market_min_qty": Decimal("1.0"),
        "market_qty_step": Decimal("1.0"),
        "tp1_quantity_feasible": False,
        "recommended_owner_decision": (
            "keep_hard_stop_only_or_prepare_official_reduce_only_recovery"
        ),
        "warnings": ["tp1_partial_quantity_below_min_qty_or_step"],
        "created_at_ms": 1,
    }
    data.update(overrides)
    return RuntimePositionExitPlan(**data)


def test_reduce_only_close_owner_packet_ready_when_full_close_feasible():
    packet = build_runtime_reduce_only_close_owner_packet(
        exit_plan=_exit_plan(),
        now_ms=123,
    )

    assert (
        packet.status
        == RuntimeReduceOnlyCloseOwnerPacketStatus.READY_FOR_STANDING_RECOVERY_AUTHORIZATION
    )
    assert packet.owner_approval_env is None
    assert packet.owner_approval_value is None
    assert packet.owner_approval_required is False
    assert packet.standing_authorization_scope == STANDING_REDUCE_ONLY_RECOVERY_SCOPE
    assert packet.operation_layer_required is True
    assert packet.finalgate_required is True
    assert packet.close_quantity == Decimal("1.0")
    assert packet.reduce_only_side == "buy"
    assert packet.not_order is True
    assert packet.not_execution_authority is True
    assert packet.exchange_order_submitted is False
    assert packet.position_closed is False
    assert "tp1_partial_quantity_below_min_qty_or_step" in packet.warnings


def test_reduce_only_close_owner_packet_blocks_when_full_close_not_feasible():
    packet = build_runtime_reduce_only_close_owner_packet(
        exit_plan=_exit_plan(
            full_reduce_only_close_feasible=False,
            full_reduce_only_close_quantity=Decimal("0"),
        ),
        now_ms=123,
    )

    assert packet.status == RuntimeReduceOnlyCloseOwnerPacketStatus.BLOCKED
    assert packet.owner_approval_value is None
    assert "full_reduce_only_close_not_feasible" in packet.blockers
