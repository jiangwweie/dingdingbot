from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.runtime_closed_trade_lifecycle_review_service import (
    RuntimeClosedTradeLifecycleReviewService,
)
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, Position
from src.domain.runtime_semantic_review_artifact import (
    build_runtime_semantic_review_artifact,
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
        self.orders = {item.id: item for item in orders}
        self.open_orders = list(open_orders or [])

    async def get_order(self, order_id: str):
        return self.orders.get(order_id)

    async def get_open_orders(self, symbol: str | None = None):
        return [
            item for item in self.open_orders
            if symbol is None or item.symbol == symbol
        ]


class _PositionRepo:
    def __init__(self, positions: list[Position], active: list[Position] | None = None) -> None:
        self.positions = list(positions)
        self.active = list(active or [])

    async def get_by_signal_id(self, signal_id: str):
        return [item for item in self.positions if item.signal_id == signal_id]

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [
            item for item in self.active
            if symbol is None or item.symbol == symbol
        ][:limit]


class _ReviewRepo:
    def __init__(self) -> None:
        self.records = []

    async def append(self, record):
        self.records.append(record)
        return record

    async def list(self, *, authorization_id=None, symbol=None, limit=50):
        records = [
            item for item in self.records
            if (authorization_id is None or item.authorization_id == authorization_id)
            and (symbol is None or item.symbol == symbol)
        ]
        return list(reversed(records))[:limit]


class _ReconciliationService:
    def __init__(self, *, severe: int = 0, warning: int = 0) -> None:
        self.severe = severe
        self.warning = warning

    async def build_read_model(self, symbol: str):
        return SimpleNamespace(
            symbol=symbol,
            checked_at=1781168901471,
            severe_count=self.severe,
            warning_count=self.warning,
            mismatches=[object()] * (self.severe + self.warning),
        )


@pytest.mark.asyncio
async def test_closed_short_stopout_records_small_bounded_loss_review() -> None:
    runtime = _runtime()
    entry = _order(
        "entry-1",
        OrderRole.ENTRY,
        average_exec_price=Decimal("6.595"),
        filled_at=1781165000000,
        exchange_order_id="39005273607",
    )
    sl = _order(
        "sl-1",
        OrderRole.SL,
        average_exec_price=Decimal("6.635"),
        trigger_price=Decimal("6.635"),
        filled_at=1781166956564,
        exchange_order_id="4000001547813056",
        exit_reason="EXCHANGE_CLOSE_PROJECTION_RECOVERY",
    )
    position = _position(realized_pnl=Decimal("-0.0400"))
    review_repo = _ReviewRepo()
    service = _service(runtime, [entry, sl], [position], review_repo)

    result = await service.create_closed_trade_review(
        runtime_instance_id=runtime.runtime_instance_id,
        entry_order_id=entry.id,
        exit_order_id=sl.id,
        apply=True,
        now_ms=1781169000000,
    )

    assert result.status == "recorded"
    assert result.live_lifecycle_review_written is True
    assert result.exchange_write_called is False
    assert result.order_created is False
    assert result.runtime_budget_mutated is False
    assert result.right_tail_classification == "small_bounded_loss"
    assert result.attempt_continuation_quality == "continue_after_small_loss"
    assert len(review_repo.records) == 1

    record = review_repo.records[0]
    assert record.lifecycle_status == "closed_reviewed"
    assert record.review_status == "closed_reviewed"
    assert record.metadata["review_outcome"] == "revise"
    assert "review_decision" not in record.metadata
    assert record.metadata["right_tail_trade_path"]["entry_price"] == "6.595"
    assert record.metadata["right_tail_trade_path"]["exit_price"] == "6.635"
    assert record.metadata["right_tail_trade_path"]["mfe_price"] == "6.595"
    assert record.metadata["right_tail_trade_path"]["mae_price"] == "6.635"
    assert record.metadata["right_tail_trade_path"]["max_loss_budget"] == "0.08776474"

    artifact = build_runtime_semantic_review_artifact(record)
    assert artifact.right_tail_review_status == "reviewed"
    assert artifact.semantic_trace_complete is False
    assert "execution_intent_id" in artifact.missing_semantic_ids
    assert artifact.calls_exchange is False


@pytest.mark.asyncio
async def test_closed_trade_review_dry_run_does_not_append() -> None:
    runtime = _runtime()
    entry = _order("entry-1", OrderRole.ENTRY, average_exec_price=Decimal("6.595"))
    sl = _order("sl-1", OrderRole.SL, average_exec_price=Decimal("6.635"))
    review_repo = _ReviewRepo()
    service = _service(runtime, [entry, sl], [_position()], review_repo)

    result = await service.create_closed_trade_review(
        runtime_instance_id=runtime.runtime_instance_id,
        entry_order_id=entry.id,
        exit_order_id=sl.id,
        apply=False,
        now_ms=1781169000000,
    )

    assert result.status == "ready_to_record"
    assert result.local_state_mutated is False
    assert result.live_lifecycle_review_written is False
    assert review_repo.records == []


@pytest.mark.asyncio
async def test_closed_trade_review_blocks_on_severe_reconciliation_mismatch() -> None:
    runtime = _runtime()
    entry = _order("entry-1", OrderRole.ENTRY, average_exec_price=Decimal("6.595"))
    sl = _order("sl-1", OrderRole.SL, average_exec_price=Decimal("6.635"))
    review_repo = _ReviewRepo()
    service = _service(
        runtime,
        [entry, sl],
        [_position()],
        review_repo,
        reconciliation_service=_ReconciliationService(severe=1),
    )

    result = await service.create_closed_trade_review(
        runtime_instance_id=runtime.runtime_instance_id,
        entry_order_id=entry.id,
        exit_order_id=sl.id,
        apply=True,
        now_ms=1781169000000,
    )

    assert result.status == "blocked"
    assert "reconciliation_severe_mismatch" in result.blockers
    assert result.live_lifecycle_review_written is False
    assert review_repo.records == []


def _service(
    runtime: StrategyRuntimeInstance,
    orders: list[Order],
    positions: list[Position],
    review_repo: _ReviewRepo,
    *,
    reconciliation_service: _ReconciliationService | None = None,
) -> RuntimeClosedTradeLifecycleReviewService:
    return RuntimeClosedTradeLifecycleReviewService(
        runtime_repository=_RuntimeRepo(runtime),
        order_repository=_OrderRepo(orders),
        position_repository=_PositionRepo(positions),
        live_lifecycle_review_repository=review_repo,
        reconciliation_service=reconciliation_service or _ReconciliationService(),
    )


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
            attempts_used=1,
            budget_reserved=Decimal("0.08776474"),
            total_budget=Decimal("6"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            max_leverage=Decimal("2"),
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=1781164000000,
        updated_at_ms=1781168900000,
        metadata={
            "last_exchange_submit_action_authorization_id": "auth-avx-1",
            "last_final_gate_result": "passed",
        },
    )


def _order(
    order_id: str,
    role: OrderRole,
    *,
    average_exec_price: Decimal,
    trigger_price: Decimal | None = None,
    filled_at: int = 1781166000000,
    exchange_order_id: str | None = None,
    exit_reason: str | None = None,
) -> Order:
    return Order(
        id=order_id,
        signal_id="signal-evaluation-adabffa08945",
        exchange_order_id=exchange_order_id,
        symbol="AVAX/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET if role == OrderRole.ENTRY else OrderType.STOP_MARKET,
        order_role=role,
        price=None,
        trigger_price=trigger_price,
        requested_qty=Decimal("1"),
        filled_qty=Decimal("1"),
        average_exec_price=average_exec_price,
        status=OrderStatus.FILLED,
        created_at=1781164000000,
        updated_at=filled_at,
        filled_at=filled_at,
        parent_order_id="entry-1" if role != OrderRole.ENTRY else None,
        reduce_only=role != OrderRole.ENTRY,
        runtime_instance_id="strategy-runtime-95655873b76c",
        trial_binding_id="trial-binding-1",
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v1",
        signal_evaluation_id="signal-evaluation-adabffa08945",
        order_candidate_id="order-candidate-avx-1",
        exit_reason=exit_reason,
    )


def _position(realized_pnl: Decimal = Decimal("-0.0400")) -> Position:
    return Position(
        id="pos_signal-evaluation-adabffa08945",
        signal_id="signal-evaluation-adabffa08945",
        symbol="AVAX/USDT:USDT",
        direction=Direction.SHORT,
        entry_price=Decimal("6.595"),
        current_qty=Decimal("0"),
        watermark_price=Decimal("6.595"),
        realized_pnl=realized_pnl,
        total_fees_paid=Decimal("0"),
        opened_at=1781165000000,
        closed_at=1781166956564,
        is_closed=True,
        runtime_instance_id="strategy-runtime-95655873b76c",
        trial_binding_id="trial-binding-1",
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v1",
        signal_evaluation_id="signal-evaluation-adabffa08945",
        order_candidate_id="order-candidate-avx-1",
    )
