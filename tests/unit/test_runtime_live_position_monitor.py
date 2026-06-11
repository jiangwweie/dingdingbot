from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.reconciliation import ReconciliationMismatch, ReconciliationReadModelResult
from src.application.runtime_live_position_monitor_service import (
    RuntimeLivePositionMonitorService,
)
from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
    Position,
    PositionInfo,
)
from src.domain.runtime_live_position_monitor import (
    RuntimeLivePositionMonitorStatus,
    RuntimeLiveProtectionStatus,
    build_runtime_live_position_monitor_packet,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


NOW_MS = 1781166600000
RUNTIME_ID = "strategy-runtime-monitor-1"
SYMBOL = "AVAX/USDT:USDT"


def _runtime(**overrides) -> StrategyRuntimeInstance:
    values = {
        "runtime_instance_id": RUNTIME_ID,
        "trial_binding_id": "trial-binding-1",
        "admission_decision_id": "admission-decision-1",
        "strategy_family_id": "BRF",
        "strategy_family_version_id": "BRF-v1",
        "symbol": SYMBOL,
        "side": "short",
        "status": StrategyRuntimeInstanceStatus.ACTIVE,
        "boundary": StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=Decimal("0.08776474"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("8"),
            total_budget=Decimal("6"),
            allowed_symbols=[SYMBOL],
            allowed_sides=["short"],
            max_leverage=Decimal("1"),
            requires_protection=True,
            requires_review=True,
        ),
        "execution_enabled": True,
        "shadow_mode": False,
        "created_at_ms": 1,
        "updated_at_ms": 2,
        "metadata": {
            "live_runtime_enablement_mutation_id": "mutation-1",
            "owner_live_runtime_enablement_authorization_id": "owner-live-1",
            "owner_real_submit_authorization_id": "owner-submit-1",
        },
    }
    values.update(overrides)
    return StrategyRuntimeInstance(**values)


def _position(**overrides) -> Position:
    values = {
        "id": "pos-sig-1",
        "signal_id": "sig-1",
        "symbol": SYMBOL,
        "direction": Direction.SHORT,
        "entry_price": Decimal("6.595"),
        "current_qty": Decimal("1"),
        "watermark_price": Decimal("6.595"),
        "realized_pnl": Decimal("0"),
        "opened_at": 1,
        "is_closed": False,
        "runtime_instance_id": RUNTIME_ID,
        "trial_binding_id": "trial-binding-1",
        "strategy_family_id": "BRF",
        "strategy_family_version_id": "BRF-v1",
        "signal_evaluation_id": "signal-eval-1",
        "order_candidate_id": "candidate-1",
    }
    values.update(overrides)
    return Position(**values)


def _order(order_id: str, role: OrderRole, **overrides) -> Order:
    values = {
        "id": order_id,
        "signal_id": "sig-1",
        "exchange_order_id": f"ex-{order_id}",
        "symbol": SYMBOL,
        "direction": Direction.SHORT,
        "order_type": OrderType.STOP_MARKET,
        "order_role": role,
        "trigger_price": Decimal("6.635") if role == OrderRole.SL else Decimal("6.555"),
        "requested_qty": Decimal("1"),
        "filled_qty": Decimal("0"),
        "status": OrderStatus.OPEN,
        "created_at": 1,
        "updated_at": 2,
        "reduce_only": role == OrderRole.SL,
        "runtime_instance_id": RUNTIME_ID,
    }
    values.update(overrides)
    return Order(**values)


def _exchange_position() -> PositionInfo:
    return PositionInfo(
        symbol=SYMBOL,
        side="short",
        size=Decimal("1"),
        entry_price=Decimal("6.595"),
        mark_price=Decimal("6.62844777"),
        unrealized_pnl=Decimal("-0.03344777"),
        leverage=1,
        liquidation_price=Decimal("36.88823464"),
        margin_mode="cross",
    )


def _exchange_sl_order() -> dict:
    return {
        "id": "4000001547813056",
        "clientOrderId": "rtod-a194d1ef363c12c3df-sl",
        "symbol": SYMBOL,
        "type": "market",
        "side": "buy",
        "triggerPrice": "6.635",
        "stopPrice": "6.635",
        "amount": "1",
        "remaining": "1",
        "status": "open",
        "reduceOnly": True,
        "info": {"positionSide": "SHORT", "orderType": "STOP_MARKET"},
    }


def _reconciliation_warning() -> ReconciliationReadModelResult:
    return ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=NOW_MS,
        mismatches=[
            ReconciliationMismatch(
                symbol=SYMBOL,
                mismatch_type="missing_tp_protection",
                severity="WARNING",
                reason="Local active position has SL protection but no TP protection order.",
            )
        ],
    )


def test_active_short_with_sl_only_is_holdable_warning_not_runaway_blocker():
    packet = build_runtime_live_position_monitor_packet(
        runtime=_runtime(),
        local_positions=[_position()],
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_positions=[_exchange_position()],
        exchange_open_stop_orders=[_exchange_sl_order()],
        reconciliation_result=_reconciliation_warning(),
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeLivePositionMonitorStatus.ACTIVE_PROTECTION_WARNING
    assert packet.protection_status == RuntimeLiveProtectionStatus.HARD_STOP_ONLY
    assert packet.sl_protection_present is True
    assert packet.tp_protection_present is False
    assert packet.can_continue_holding is True
    assert packet.blocks_new_entries_until_resolved is True
    assert packet.owner_action_required is False
    assert packet.blockers == ["runtime_max_active_positions_in_use"]
    assert "missing_tp_protection_right_tail_exit_not_mounted" in packet.warnings
    assert packet.current_qty == Decimal("1")
    assert packet.unrealized_pnl == Decimal("-0.03344777")
    assert packet.order_created is False
    assert packet.exchange_order_submitted is False


def test_active_position_without_hard_stop_requires_owner_action():
    packet = build_runtime_live_position_monitor_packet(
        runtime=_runtime(),
        local_positions=[_position()],
        local_open_orders=[],
        exchange_positions=[_exchange_position()],
        exchange_open_stop_orders=[],
        reconciliation_result=None,
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeLivePositionMonitorStatus.ACTIVE_UNPROTECTED
    assert packet.protection_status == RuntimeLiveProtectionStatus.HARD_STOP_MISSING
    assert packet.can_continue_holding is False
    assert packet.owner_action_required is True
    assert "active_position_missing_hard_stop" in packet.blockers


def test_flat_after_attempt_requires_review_before_next_attempt():
    packet = build_runtime_live_position_monitor_packet(
        runtime=_runtime(),
        local_positions=[],
        local_open_orders=[],
        exchange_positions=[],
        exchange_open_stop_orders=[],
        reconciliation_result=None,
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeLivePositionMonitorStatus.FLAT_REVIEW_REQUIRED
    assert packet.protection_status == RuntimeLiveProtectionStatus.NO_ACTIVE_POSITION
    assert packet.review_required_before_next_attempt is True
    assert packet.owner_action_required is True
    assert packet.blocks_new_entries_until_resolved is True


def test_severe_reconciliation_blocks_monitor_packet():
    result = ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=NOW_MS,
        mismatches=[
            ReconciliationMismatch(
                symbol=SYMBOL,
                mismatch_type="local_position_missing_on_exchange",
                severity="SEVERE",
                reason="Local active position exists but exchange is flat.",
            )
        ],
    )

    packet = build_runtime_live_position_monitor_packet(
        runtime=_runtime(),
        local_positions=[_position()],
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_positions=[],
        exchange_open_stop_orders=[],
        reconciliation_result=result,
        now_ms=NOW_MS,
    )

    assert packet.status == RuntimeLivePositionMonitorStatus.BLOCKED
    assert "reconciliation_severe_mismatch" in packet.blockers
    assert packet.owner_action_required is True


class _RuntimeRepo:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime

    async def get(self, runtime_instance_id: str):
        assert runtime_instance_id == self.runtime.runtime_instance_id
        return self.runtime


class _PositionRepo:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        assert symbol == SYMBOL
        return [_position()]


class _OrderRepo:
    async def get_open_orders(self, symbol: str | None = None):
        assert symbol == SYMBOL
        return [_order("ord-sl", OrderRole.SL)]


class _Exchange:
    async def fetch_positions(self, symbol: str | None = None):
        assert symbol == SYMBOL
        return [_exchange_position()]

    async def fetch_open_orders(self, symbol: str, params=None):
        assert symbol == SYMBOL
        assert params == {"stop": True}
        return [_exchange_sl_order()]


class _Reconciliation:
    async def build_read_model(self, symbol: str):
        assert symbol == SYMBOL
        return _reconciliation_warning()


@pytest.mark.asyncio
async def test_service_builds_packet_from_runtime_local_exchange_and_reconciliation_facts():
    service = RuntimeLivePositionMonitorService(
        runtime_repository=_RuntimeRepo(_runtime()),
        position_repository=_PositionRepo(),
        order_repository=_OrderRepo(),
        exchange_gateway=_Exchange(),
        reconciliation_service=_Reconciliation(),
    )

    packet = await service.build_monitor_packet(
        runtime_instance_id=RUNTIME_ID,
        now_ms=NOW_MS,
    )

    assert packet.runtime_instance_id == RUNTIME_ID
    assert packet.status == RuntimeLivePositionMonitorStatus.ACTIVE_PROTECTION_WARNING
    assert packet.exchange_active_position_count == 1
    assert packet.reconciliation_mismatch_types == ["missing_tp_protection"]
