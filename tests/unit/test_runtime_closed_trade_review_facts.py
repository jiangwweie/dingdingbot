from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.runtime_closed_trade_review_facts_service import (
    RuntimeClosedTradeReviewFactsService,
)
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, Position
from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsStatus,
    build_runtime_closed_trade_review_facts_packet,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class _RuntimeRepo:
    def __init__(self, runtime: StrategyRuntimeInstance | None) -> None:
        self.runtime = runtime

    async def get(self, runtime_instance_id: str):
        if self.runtime and self.runtime.runtime_instance_id == runtime_instance_id:
            return self.runtime
        return None


class _OrderRepo:
    def __init__(self, orders: list[Order], open_orders: list[Order] | None = None) -> None:
        self.orders = list(orders)
        self.open_orders = list(open_orders or [])

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100):
        return [order for order in self.orders if order.symbol == symbol][:limit]

    async def get_open_orders(self, symbol: str | None = None):
        return [
            order
            for order in self.open_orders
            if symbol is None or order.symbol == symbol
        ]


class _PositionRepo:
    def __init__(self, active: list[Position] | None = None) -> None:
        self.active = list(active or [])

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [
            position
            for position in self.active
            if symbol is None or position.symbol == symbol
        ][:limit]


def test_review_facts_waits_for_close_when_position_active() -> None:
    packet = build_runtime_closed_trade_review_facts_packet(
        runtime=_runtime(),
        orders=[_order("entry-1", OrderRole.ENTRY)],
        active_positions=[_position(active=True)],
        open_orders=[],
        now_ms=3,
    )

    assert packet.status == RuntimeClosedTradeReviewFactsStatus.WAITING_FOR_CLOSE
    assert packet.active_position_count == 1
    assert packet.review_command_args == []
    assert packet.review_record_created is False
    assert packet.exchange_called is False


def test_review_facts_resolves_closed_entry_exit_order_ids() -> None:
    packet = build_runtime_closed_trade_review_facts_packet(
        runtime=_runtime(),
        orders=[
            _order("entry-1", OrderRole.ENTRY, filled_at=1),
            _order("exit-1", OrderRole.EXIT, filled_at=2),
        ],
        active_positions=[],
        open_orders=[],
        now_ms=3,
    )

    assert packet.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
    assert packet.entry_order_id == "entry-1"
    assert packet.exit_order_id == "exit-1"
    assert packet.authorization_id == "auth-avx-1"
    assert packet.review_command_args == [
        "scripts/create_runtime_closed_trade_review.py",
        "--runtime-instance-id",
        "strategy-runtime-95655873b76c",
        "--entry-order-id",
        "entry-1",
        "--exit-order-id",
        "exit-1",
        "--authorization-id",
        "auth-avx-1",
    ]
    assert packet.review_record_created is False
    assert packet.runtime_state_mutated is False


def test_review_facts_resolves_legacy_exit_without_runtime_id_by_signal() -> None:
    entry = _order("entry-1", OrderRole.ENTRY, filled_at=1)
    exit_order = _order(
        "exit-legacy",
        OrderRole.EXIT,
        filled_at=2,
        runtime_instance_id=None,
        parent_order_id="entry-1",
    )

    packet = build_runtime_closed_trade_review_facts_packet(
        runtime=_runtime(),
        orders=[entry, exit_order],
        active_positions=[],
        open_orders=[],
        now_ms=3,
    )

    assert packet.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
    assert packet.exit_order_id == "exit-legacy"


def test_review_facts_blocks_when_flat_but_terminal_exit_missing() -> None:
    packet = build_runtime_closed_trade_review_facts_packet(
        runtime=_runtime(),
        orders=[_order("entry-1", OrderRole.ENTRY)],
        active_positions=[],
        open_orders=[],
        now_ms=3,
    )

    assert packet.status == RuntimeClosedTradeReviewFactsStatus.BLOCKED
    assert "terminal_exit_order_not_found" in packet.blockers


@pytest.mark.asyncio
async def test_review_facts_service_reads_repositories() -> None:
    runtime = _runtime()
    service = RuntimeClosedTradeReviewFactsService(
        runtime_repository=_RuntimeRepo(runtime),
        order_repository=_OrderRepo(
            [
                _order("entry-1", OrderRole.ENTRY, filled_at=1),
                _order("exit-1", OrderRole.EXIT, filled_at=2),
            ],
        ),
        position_repository=_PositionRepo(),
    )

    packet = await service.build_packet(
        runtime_instance_id=runtime.runtime_instance_id,
        now_ms=3,
    )

    assert packet.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
    assert packet.entry_order_id == "entry-1"
    assert packet.exit_order_id == "exit-1"


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="strategy-runtime-95655873b76c",
        trial_binding_id="trial-binding-1",
        admission_decision_id="admission-1",
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v1",
        owner_risk_acceptance_id="owner-risk-1",
        carrier_id="BRF-001-runtime",
        symbol="AVAX/USDT:USDT",
        side="short",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=2,
            budget_reserved=Decimal("0.16686422"),
            total_budget=Decimal("6"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            max_leverage=Decimal("2"),
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=1,
        updated_at_ms=2,
        metadata={"last_exchange_submit_action_authorization_id": "auth-avx-1"},
    )


def _order(
    order_id: str,
    role: OrderRole,
    *,
    filled_at: int = 1,
    runtime_instance_id: str | None = "strategy-runtime-95655873b76c",
    parent_order_id: str | None = None,
) -> Order:
    return Order(
        id=order_id,
        signal_id="signal-evaluation-adabffa08945",
        exchange_order_id=f"ex-{order_id}",
        symbol="AVAX/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        order_role=role,
        requested_qty=Decimal("1"),
        filled_qty=Decimal("1"),
        average_exec_price=Decimal("6.595") if role == OrderRole.ENTRY else Decimal("6.555"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=filled_at,
        filled_at=filled_at,
        parent_order_id=parent_order_id if parent_order_id is not None else (
            "entry-1" if role != OrderRole.ENTRY else None
        ),
        reduce_only=role != OrderRole.ENTRY,
        runtime_instance_id=runtime_instance_id,
        trial_binding_id="trial-binding-1" if runtime_instance_id else None,
        strategy_family_id="BRF-001" if runtime_instance_id else None,
        strategy_family_version_id="BRF-001-v1" if runtime_instance_id else None,
        signal_evaluation_id="signal-evaluation-adabffa08945",
        order_candidate_id="order-candidate-avx-1" if runtime_instance_id else None,
    )


def _position(*, active: bool) -> Position:
    return Position(
        id="pos_signal-evaluation-adabffa08945",
        signal_id="signal-evaluation-adabffa08945",
        symbol="AVAX/USDT:USDT",
        direction=Direction.SHORT,
        entry_price=Decimal("6.595"),
        current_qty=Decimal("1") if active else Decimal("0"),
        realized_pnl=Decimal("0"),
        opened_at=1,
        is_closed=not active,
        runtime_instance_id="strategy-runtime-95655873b76c",
        trial_binding_id="trial-binding-1",
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v1",
        signal_evaluation_id="signal-evaluation-adabffa08945",
        order_candidate_id="order-candidate-avx-1",
    )
