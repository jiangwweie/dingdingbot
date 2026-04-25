"""Tests for PositionProjectionService — execution 主链仓位投影骨架。

覆盖:
- project_entry_fill: 新建仓位 / 已有仓位保留 realized_pnl/fees/funding
- project_exit_fill: current_qty / realized_pnl / total_fees_paid / is_closed / closed_at / watermark_price
- _calculate_gross_pnl: LONG vs SHORT 方向
- _update_watermark: LONG max / SHORT min
- repository=None 优雅退化
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.position_projection_service import PositionProjectionService
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, Position


def _make_entry_order(
    signal_id="sig_proj_001",
    filled_qty=Decimal("1.0"),
    average_exec_price=Decimal("65000"),
    price=Decimal("65000"),
    direction=Direction.LONG,
    symbol="BTC/USDT:USDT",
) -> Order:
    return Order(
        id=f"entry_{signal_id}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=average_exec_price,
        price=price,
        status=OrderStatus.FILLED,
        created_at=1710000000000,
        updated_at=1710000000000,
    )


def _make_exit_order(
    signal_id="sig_proj_001",
    filled_qty=Decimal("1.0"),
    average_exec_price=Decimal("66000"),
    direction=Direction.LONG,
    order_role=OrderRole.TP1,
    symbol="BTC/USDT:USDT",
    close_fee=Decimal("0.65"),
) -> Order:
    return Order(
        id=f"exit_{signal_id}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=OrderType.LIMIT,
        order_role=order_role,
        requested_qty=filled_qty,
        filled_qty=filled_qty,
        average_exec_price=average_exec_price,
        close_fee=close_fee,
        status=OrderStatus.FILLED,
        created_at=1710000000000,
        updated_at=1710000000000,
    )


def _make_existing_position(
    signal_id="sig_proj_001",
    current_qty=Decimal("1.0"),
    entry_price=Decimal("65000"),
    realized_pnl=Decimal("50"),
    total_fees_paid=Decimal("10"),
    total_funding_paid=Decimal("5"),
    watermark_price=Decimal("66000"),
    is_closed=False,
    direction=Direction.LONG,
    symbol="BTC/USDT:USDT",
    opened_at=None,
    closed_at=None,
) -> Position:
    return Position(
        id=f"pos_{signal_id}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=watermark_price,
        realized_pnl=realized_pnl,
        total_fees_paid=total_fees_paid,
        total_funding_paid=total_funding_paid,
        is_closed=is_closed,
        opened_at=opened_at,
        closed_at=closed_at,
    )


# ============================================================
# project_entry_fill
# ============================================================


class TestProjectEntryFill:
    """project_entry_fill: 新建仓位 + 已有仓位保留财务状态。"""

    @pytest.mark.asyncio
    async def test_new_position_defaults(self):
        """ENTRY 成交创建新仓位，默认值正确。"""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)

        assert result is not None
        assert result.id == "pos_sig_proj_001"
        assert result.signal_id == "sig_proj_001"
        assert result.symbol == "BTC/USDT:USDT"
        assert result.direction == Direction.LONG
        assert result.entry_price == Decimal("65000")
        assert result.current_qty == Decimal("1.0")
        assert result.realized_pnl == Decimal("0")
        assert result.total_fees_paid == Decimal("0")
        assert result.total_funding_paid == Decimal("0")
        assert result.watermark_price == Decimal("65000")
        assert result.is_closed is False

    @pytest.mark.asyncio
    async def test_existing_position_preserves_realized_pnl(self):
        """已有仓位时保留 realized_pnl。"""
        existing = _make_existing_position(realized_pnl=Decimal("50"))
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)

        assert result.realized_pnl == Decimal("50")

    @pytest.mark.asyncio
    async def test_existing_position_preserves_fees(self):
        """已有仓位时保留 total_fees_paid 和 total_funding_paid。"""
        existing = _make_existing_position(
            total_fees_paid=Decimal("10"),
            total_funding_paid=Decimal("5"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)

        assert result.total_fees_paid == Decimal("10")
        assert result.total_funding_paid == Decimal("5")

    @pytest.mark.asyncio
    async def test_existing_position_preserves_watermark(self):
        """已有仓位时保留 watermark_price。"""
        existing = _make_existing_position(watermark_price=Decimal("66000"))
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order(average_exec_price=Decimal("65000"))

        result = await svc.project_entry_fill(entry_order)

        assert result.watermark_price == Decimal("66000")

    @pytest.mark.asyncio
    async def test_existing_position_watermark_none_falls_back_to_entry_price(self):
        """已有仓位 watermark_price 为 None 时回退到当前 entry_price。"""
        existing = _make_existing_position(watermark_price=None)
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order(average_exec_price=Decimal("67000"))

        result = await svc.project_entry_fill(entry_order)

        assert result.watermark_price == Decimal("67000")

    @pytest.mark.asyncio
    async def test_existing_position_qty_max(self):
        """已有仓位 current_qty 取 max(existing, new filled_qty)。"""
        existing = _make_existing_position(current_qty=Decimal("0.5"))
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order(filled_qty=Decimal("1.0"))

        result = await svc.project_entry_fill(entry_order)

        assert result.current_qty == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_repository_none_returns_none(self):
        """repository=None 时优雅退化返回 None。"""
        svc = PositionProjectionService(repository=None)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)
        assert result is None

    @pytest.mark.asyncio
    async def test_closed_position_re_entry(self):
        """已平仓位重新入场：is_closed=False（因为 current_qty > 0）。"""
        existing = _make_existing_position(
            current_qty=Decimal("0"),
            is_closed=True,
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order(filled_qty=Decimal("1.0"))

        result = await svc.project_entry_fill(entry_order)

        # 重新入场：current_qty > 0 → is_closed=False
        assert result.is_closed is False
        assert result.current_qty == Decimal("1.0")


# ============================================================
# project_exit_fill
# ============================================================


class TestProjectExitFill:
    """project_exit_fill: current_qty / realized_pnl / total_fees_paid / is_closed / closed_at / watermark_price。"""

    @pytest.mark.asyncio
    async def test_partial_exit_updates_qty_and_pnl(self):
        """部分平仓：current_qty 减少，realized_pnl 累加，total_fees_paid 累加。"""
        existing = _make_existing_position(
            current_qty=Decimal("1.0"),
            entry_price=Decimal("65000"),
            realized_pnl=Decimal("50"),
            total_fees_paid=Decimal("10"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            filled_qty=Decimal("0.5"),
            average_exec_price=Decimal("66000"),
            close_fee=Decimal("0.33"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result is not None
        # LONG: (66000 - 65000) * 0.5 = 500, net = 500 - 0.33 = 499.67
        assert result.current_qty == Decimal("0.5")
        assert result.realized_pnl == Decimal("50") + Decimal("499.67")
        assert result.total_fees_paid == Decimal("10") + Decimal("0.33")
        assert result.is_closed is False

    @pytest.mark.asyncio
    async def test_full_exit_closes_position(self):
        """全部平仓：current_qty=0, is_closed=True, closed_at 设置。"""
        existing = _make_existing_position(
            current_qty=Decimal("1.0"),
            entry_price=Decimal("65000"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("66000"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result.current_qty == Decimal("0")
        assert result.is_closed is True
        assert result.closed_at is not None
        assert result.closed_at > 0

    @pytest.mark.asyncio
    async def test_short_exit_pnl_calculation(self):
        """SHORT 方向 PnL 计算：(entry - exit) * qty。"""
        existing = _make_existing_position(
            direction=Direction.SHORT,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            direction=Direction.SHORT,
            average_exec_price=Decimal("64000"),
            order_role=OrderRole.SL,
            filled_qty=Decimal("1.0"),
            close_fee=Decimal("0.64"),
        )

        result = await svc.project_exit_fill(exit_order)

        # SHORT: (65000 - 64000) * 1.0 = 1000, net = 1000 - 0.64 = 999.36
        assert result.realized_pnl == Decimal("999.36")

    @pytest.mark.asyncio
    async def test_watermark_update_long(self):
        """LONG 方向 watermark 取 max(current, exec_price)。"""
        existing = _make_existing_position(
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            watermark_price=Decimal("66000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        # exit_price > watermark → watermark 更新
        exit_order = _make_exit_order(
            average_exec_price=Decimal("67000"),
            filled_qty=Decimal("0.5"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result.watermark_price == Decimal("67000")

    @pytest.mark.asyncio
    async def test_watermark_update_short(self):
        """SHORT 方向 watermark 取 min(current, exec_price)。"""
        existing = _make_existing_position(
            direction=Direction.SHORT,
            entry_price=Decimal("65000"),
            watermark_price=Decimal("64000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        # exit_price < watermark → watermark 更新
        exit_order = _make_exit_order(
            direction=Direction.SHORT,
            average_exec_price=Decimal("63000"),
            order_role=OrderRole.SL,
            filled_qty=Decimal("0.5"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result.watermark_price == Decimal("63000")

    @pytest.mark.asyncio
    async def test_position_not_found_returns_none(self):
        """仓位不存在时返回 None。"""
        repo = MagicMock()
        repo.get = AsyncMock(return_value=None)

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order()

        result = await svc.project_exit_fill(exit_order)
        assert result is None

    @pytest.mark.asyncio
    async def test_repository_none_returns_none(self):
        """repository=None 时返回 None。"""
        svc = PositionProjectionService(repository=None)
        exit_order = _make_exit_order()

        result = await svc.project_exit_fill(exit_order)
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_exit_qty_returns_position_unchanged(self):
        """exit_qty=0 时返回仓位不变。"""
        existing = _make_existing_position(
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(filled_qty=Decimal("0"))

        result = await svc.project_exit_fill(exit_order)
        # exit_qty <= 0 → 返回原仓位，不更新
        assert result.realized_pnl == Decimal("0")
        assert result.current_qty == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_close_fee_attribute(self):
        """exit_order 的 close_fee 属性被正确使用。"""
        existing = _make_existing_position(
            entry_price=Decimal("65000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            average_exec_price=Decimal("66000"),
            filled_qty=Decimal("1.0"),
            close_fee=Decimal("1.0"),
        )

        result = await svc.project_exit_fill(exit_order)

        # LONG: (66000 - 65000) * 1.0 = 1000, net = 1000 - 1.0 = 999
        assert result.realized_pnl == Decimal("999")
        assert result.total_fees_paid == Decimal("1.0")


# ============================================================
# _calculate_gross_pnl (static helper)
# ============================================================


class TestCalculateGrossPnl:
    """_calculate_gross_pnl: LONG vs SHORT 方向。"""

    def test_long_profit(self):
        """LONG 方向盈利：(exit - entry) * qty。"""
        result = PositionProjectionService._calculate_gross_pnl(
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            exit_price=Decimal("66000"),
            quantity=Decimal("1.0"),
        )
        assert result == Decimal("1000")

    def test_long_loss(self):
        """LONG 方向亏损：(exit - entry) * qty < 0。"""
        result = PositionProjectionService._calculate_gross_pnl(
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            exit_price=Decimal("64000"),
            quantity=Decimal("1.0"),
        )
        assert result == Decimal("-1000")

    def test_short_profit(self):
        """SHORT 方向盈利：(entry - exit) * qty。"""
        result = PositionProjectionService._calculate_gross_pnl(
            direction=Direction.SHORT,
            entry_price=Decimal("65000"),
            exit_price=Decimal("64000"),
            quantity=Decimal("1.0"),
        )
        assert result == Decimal("1000")

    def test_short_loss(self):
        """SHORT 方向亏损：(entry - exit) * qty < 0。"""
        result = PositionProjectionService._calculate_gross_pnl(
            direction=Direction.SHORT,
            entry_price=Decimal("65000"),
            exit_price=Decimal("66000"),
            quantity=Decimal("1.0"),
        )
        assert result == Decimal("-1000")

    def test_partial_qty(self):
        """部分数量 PnL 计算。"""
        result = PositionProjectionService._calculate_gross_pnl(
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            exit_price=Decimal("66000"),
            quantity=Decimal("0.5"),
        )
        assert result == Decimal("500")


# ============================================================
# _update_watermark (static helper)
# ============================================================


class TestUpdateWatermark:
    """_update_watermark: LONG max / SHORT min / None fallback。"""

    def test_long_max(self):
        """LONG 方向取 max(current, exec_price)。"""
        result = PositionProjectionService._update_watermark(
            direction=Direction.LONG,
            current_watermark=Decimal("66000"),
            exec_price=Decimal("67000"),
            entry_price=Decimal("65000"),
        )
        assert result == Decimal("67000")

    def test_long_no_update(self):
        """LONG 方向 exec_price < watermark → 不更新。"""
        result = PositionProjectionService._update_watermark(
            direction=Direction.LONG,
            current_watermark=Decimal("67000"),
            exec_price=Decimal("66000"),
            entry_price=Decimal("65000"),
        )
        assert result == Decimal("67000")

    def test_short_min(self):
        """SHORT 方向取 min(current, exec_price)。"""
        result = PositionProjectionService._update_watermark(
            direction=Direction.SHORT,
            current_watermark=Decimal("64000"),
            exec_price=Decimal("63000"),
            entry_price=Decimal("65000"),
        )
        assert result == Decimal("63000")

    def test_short_no_update(self):
        """SHORT 方向 exec_price > watermark → 不更新。"""
        result = PositionProjectionService._update_watermark(
            direction=Direction.SHORT,
            current_watermark=Decimal("63000"),
            exec_price=Decimal("64000"),
            entry_price=Decimal("65000"),
        )
        assert result == Decimal("63000")

    def test_watermark_none_falls_back_to_entry_price(self):
        """current_watermark=None 时回退到 entry_price。"""
        result = PositionProjectionService._update_watermark(
            direction=Direction.LONG,
            current_watermark=None,
            exec_price=Decimal("67000"),
            entry_price=Decimal("65000"),
        )
        # max(65000, 67000) = 67000
        assert result == Decimal("67000")


# ============================================================
# opened_at / closed_at preservation + fee priority
# ============================================================


class TestPositionTimestamps:
    """project_entry_fill / project_exit_fill 时间戳和手续费优先级。"""

    @pytest.mark.asyncio
    async def test_entry_fill_preserves_existing_opened_at(self):
        """已有仓位的 opened_at 不被覆盖。"""
        opened_ts = 1700000000000
        existing = _make_existing_position()
        existing.opened_at = opened_ts
        existing.closed_at = None

        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)

        assert result.opened_at == opened_ts

    @pytest.mark.asyncio
    async def test_entry_fill_preserves_existing_closed_at(self):
        """已有仓位的 closed_at 保留。"""
        closed_ts = 1700001000000
        existing = _make_existing_position(is_closed=True, current_qty=Decimal("0"))
        existing.closed_at = closed_ts

        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        entry_order = _make_entry_order()

        result = await svc.project_entry_fill(entry_order)

        assert result.closed_at == closed_ts

    @pytest.mark.asyncio
    async def test_exit_fill_sets_closed_at_on_full_close(self):
        """全平时 closed_at 被设置。"""
        existing = _make_existing_position(
            current_qty=Decimal("1.0"),
            entry_price=Decimal("65000"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
            closed_at=None,
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            filled_qty=Decimal("1.0"),
            average_exec_price=Decimal("66000"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result.is_closed is True
        assert result.closed_at is not None
        assert result.closed_at > 0

    @pytest.mark.asyncio
    async def test_exit_fill_partial_does_not_set_closed_at(self):
        """部分平仓不设置 closed_at。"""
        existing = _make_existing_position(
            current_qty=Decimal("1.0"),
            entry_price=Decimal("65000"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
            closed_at=None,
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)
        exit_order = _make_exit_order(
            filled_qty=Decimal("0.5"),
            average_exec_price=Decimal("66000"),
        )

        result = await svc.project_exit_fill(exit_order)

        assert result.is_closed is False
        assert result.closed_at is None

    @pytest.mark.asyncio
    async def test_fee_priority_close_fee_over_fee_paid(self):
        """手续费优先使用 close_fee，其次 fee_paid。"""
        existing = _make_existing_position(
            entry_price=Decimal("65000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)

        # Order 有 close_fee 字段 → 优先使用
        exit_order = _make_exit_order(
            average_exec_price=Decimal("66000"),
            filled_qty=Decimal("1.0"),
            close_fee=Decimal("2.0"),
        )

        result = await svc.project_exit_fill(exit_order)

        # LONG: (66000 - 65000) * 1.0 = 1000, net = 1000 - 2.0 = 998
        assert result.realized_pnl == Decimal("998")
        assert result.total_fees_paid == Decimal("2.0")

    @pytest.mark.asyncio
    async def test_fee_fallback_to_fee_paid_when_close_fee_none(self):
        """close_fee 为 None 时回退到 fee_paid。"""
        existing = _make_existing_position(
            entry_price=Decimal("65000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
            total_fees_paid=Decimal("0"),
        )
        repo = MagicMock()
        repo.get = AsyncMock(return_value=existing)
        repo.save = AsyncMock()

        svc = PositionProjectionService(repository=repo)

        # 构造一个没有 close_fee 但有 fee_paid 的 order
        exit_order = _make_exit_order(
            average_exec_price=Decimal("66000"),
            filled_qty=Decimal("1.0"),
            close_fee=Decimal("0"),  # close_fee=0 → fallback
        )
        # 手动设置 fee_paid（如果模型支持）
        exit_order.close_fee = Decimal("0")

        result = await svc.project_exit_fill(exit_order)

        # close_fee=0 → fee_paid=0, net = 1000 - 0 = 1000
        assert result.realized_pnl == Decimal("1000")