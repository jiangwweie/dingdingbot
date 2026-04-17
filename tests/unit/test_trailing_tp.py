"""
Unit tests for Trailing Take Profit (TTP) feature.

Tests cover:
1. Basic functionality (enable/disable, activation threshold)
2. Price adjustment logic (LONG/SHORT, step threshold, floor protection)
3. Multi-level TP support (TP1-TP5 independent tracking)
4. Event recording (tp_modified events)
5. Edge cases (closed position, None watermark, Decimal precision)

Reference: docs/arch/trailing-tp-implementation-design.md Section 9.1
"""
import pytest
from decimal import Decimal
from typing import List

from src.domain.models import (
    KlineData,
    Position,
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    RiskManagerConfig,
    PositionCloseEvent,
)
from src.domain.risk_manager import DynamicRiskManager


# ============================================================
# Test Fixtures and Helpers
# ============================================================

def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1234567890000,
    open: Decimal = Decimal("65000"),
    high: Decimal = Decimal("66000"),
    low: Decimal = Decimal("64000"),
    close: Decimal = Decimal("65500"),
    volume: Decimal = Decimal("100"),
) -> KlineData:
    """Helper to create KlineData."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


def create_position(
    signal_id: str = "signal_001",
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    entry_price: Decimal = Decimal("60000"),
    current_qty: Decimal = Decimal("1"),
    watermark_price: Decimal = None,
    is_closed: bool = False,
    tp_trailing_activated: bool = False,
    original_tp_prices: dict = None,
) -> Position:
    """Helper to create Position."""
    return Position(
        id="position_001",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=watermark_price,
        is_closed=is_closed,
        tp_trailing_activated=tp_trailing_activated,
        original_tp_prices=original_tp_prices or {},
    )


def create_order(
    signal_id: str = "signal_001",
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    order_type: OrderType = OrderType.LIMIT,
    order_role: OrderRole = OrderRole.TP1,
    requested_qty: Decimal = Decimal("1"),
    trigger_price: Decimal = None,
    price: Decimal = None,
    status: OrderStatus = OrderStatus.OPEN,
    filled_qty: Decimal = Decimal("0"),
) -> Order:
    """Helper to create Order."""
    return Order(
        id=f"order_{order_role.value}_{signal_id}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=order_type,
        order_role=order_role,
        requested_qty=requested_qty,
        trigger_price=trigger_price,
        price=price,
        status=status,
        filled_qty=filled_qty,
        created_at=1234567890000,
        updated_at=1234567890000,
    )


def create_sl_order(
    signal_id: str = "signal_001",
    direction: Direction = Direction.LONG,
    trigger_price: Decimal = Decimal("58000"),
    order_type: OrderType = OrderType.STOP_MARKET,
) -> Order:
    """Helper to create SL order."""
    return create_order(
        signal_id=signal_id,
        direction=direction,
        order_type=order_type,
        order_role=OrderRole.SL,
        trigger_price=trigger_price,
        price=None,
    )


def create_tp_order(
    signal_id: str = "signal_001",
    direction: Direction = Direction.LONG,
    order_role: OrderRole = OrderRole.TP1,
    price: Decimal = Decimal("66000"),
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    """Helper to create TP order."""
    return create_order(
        signal_id=signal_id,
        direction=direction,
        order_type=OrderType.LIMIT,
        order_role=order_role,
        price=price,
        status=status,
    )


# ============================================================
# 1. Basic Functionality Tests
# ============================================================

class TestTrailingTPBasic:
    """基础功能测试"""

    def test_tp_trailing_disabled_by_default(self):
        """默认关闭时，TP 价格不应改变"""
        # Arrange - 使用默认配置（tp_trailing_enabled=False）
        config = RiskManagerConfig()  # 默认 tp_trailing_enabled=False
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("65000"),  # 水位线已超过原始 TP
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("63000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("65000"))

        original_tp_price = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - TP 价格不变
        assert tp1_order.price == original_tp_price
        assert len(events) == 0

    def test_tp_trailing_activation_threshold(self):
        """价格未达到激活阈值时，不应启动追踪"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.5"),  # 需要达到 TP 的 50%
        )
        manager = DynamicRiskManager(config=config)

        # entry=60000, tp=66000, activation=60000 + 0.5*(66000-60000) = 63000
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("62000"),  # 未达到激活阈值 63000
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("62000"))

        original_tp_price = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 未激活，TP 价格不变
        assert tp1_order.price == original_tp_price
        assert position.tp_trailing_activated is False
        assert len(events) == 0

    def test_tp_trailing_activation_long(self):
        """LONG: 水位线达到 activation_rr 后激活"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.5"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        # entry=60000, tp=66000, activation=63000
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("64000"),  # 达到激活阈值
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("64000"))

        # Act
        manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 已激活
        assert position.tp_trailing_activated is True
        # original_tp_prices 应该记录原始 TP 价格
        assert "TP1" in position.original_tp_prices
        assert position.original_tp_prices["TP1"] == Decimal("66000")

    def test_tp_trailing_activation_short(self):
        """SHORT: 水位线达到 activation_rr 后激活"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.5"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        # SHORT: entry=60000, tp=54000, activation=60000 - 0.5*(60000-54000) = 57000
        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal("60000"),
            watermark_price=Decimal("56000"),  # 达到激活阈值
        )
        sl_order = create_sl_order(direction=Direction.SHORT, trigger_price=Decimal("62000"))
        tp1_order = create_tp_order(
            direction=Direction.SHORT,
            price=Decimal("54000"),
        )
        orders = [sl_order, tp1_order]
        kline = create_kline(low=Decimal("56000"))

        # Act
        manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 已激活
        assert position.tp_trailing_activated is True
        assert "TP1" in position.original_tp_prices
        assert position.original_tp_prices["TP1"] == Decimal("54000")


# ============================================================
# 2. Price Adjustment Logic Tests
# ============================================================

class TestTrailingTPPriceAdjustment:
    """调价逻辑测试"""

    def test_tp_price_moves_up_with_watermark_long(self):
        """LONG: 水位线上升 -> TP 价格跟随上移"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),  # 较低激活阈值
            tp_trailing_percent=Decimal("0.01"),  # 1%
            tp_step_threshold=Decimal("0.003"),  # 0.3%
        )
        manager = DynamicRiskManager(config=config)

        # entry=60000, tp=66000
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("70000"),  # 高水位线
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        # theoretical_tp = 70000 * (1 - 0.01) = 69300
        # min_required = 66000 * (1 + 0.003) = 66198
        # 69300 > 66198, 满足阶梯条件
        # new_tp = max(66000, 69300) = 69300
        expected_tp = Decimal("70000") * (Decimal("1") - Decimal("0.01"))
        assert tp1_order.price == expected_tp
        assert len(events) == 1
        assert events[0].event_category == "tp_modified"

    def test_tp_price_moves_down_with_watermark_short(self):
        """SHORT: 水位线下降 -> TP 价格跟随下移"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        # SHORT: entry=60000, tp=54000
        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal("60000"),
            watermark_price=Decimal("50000"),  # 低水位线
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("54000")},
        )
        sl_order = create_sl_order(direction=Direction.SHORT, trigger_price=Decimal("62000"))
        tp1_order = create_tp_order(
            direction=Direction.SHORT,
            price=Decimal("54000"),
        )
        orders = [sl_order, tp1_order]
        kline = create_kline(low=Decimal("50000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        # theoretical_tp = 50000 * (1 + 0.01) = 50500
        # min_required = 54000 * (1 - 0.003) = 53838
        # 50500 <= 53838, 满足阶梯条件
        # new_tp = min(54000, 50500) = 50500
        expected_tp = Decimal("50000") * (Decimal("1") + Decimal("0.01"))
        assert tp1_order.price == expected_tp
        assert len(events) == 1
        assert events[0].event_category == "tp_modified"

    def test_tp_step_threshold_prevents_small_updates(self):
        """阶梯阈值：微小变动不触发更新"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.01"),  # 较大阶梯阈值 1%
        )
        manager = DynamicRiskManager(config=config)

        # entry=60000, tp=66000
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("66500"),  # 水位线略高于 TP
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("66500"))

        original_tp_price = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        # theoretical_tp = 66500 * 0.99 = 65835
        # min_required = 66000 * 1.01 = 66660
        # 65835 < 66660, 不满足阶梯条件
        assert tp1_order.price == original_tp_price  # 价格不变
        assert len(events) == 0

    def test_tp_floor_protection_long(self):
        """LONG: TP 价格不低于原始 TP 价格"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.10"),  # 大回撤 10%
            tp_step_threshold=Decimal("0.001"),
        )
        manager = DynamicRiskManager(config=config)

        # entry=60000, original_tp=66000
        # watermark=63000, 理论 TP = 63000 * 0.9 = 56700
        # 但 floor protection 要求 TP >= 66000
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("63000"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("63000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 由于 floor protection，TP 不低于原始价格
        # theoretical_tp = 63000 * 0.9 = 56700
        # 但 floor = max(66000, 56700) = 66000
        # min_required = 66000 * 1.001 = 66066
        # 56700 < 66066, 不满足阶梯条件，价格不变
        assert tp1_order.price >= Decimal("66000")  # 不低于原始 TP

    def test_tp_floor_protection_short(self):
        """SHORT: TP 价格不高于原始 TP 价格"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.10"),  # 大回撤 10%
            tp_step_threshold=Decimal("0.001"),
        )
        manager = DynamicRiskManager(config=config)

        # SHORT: entry=60000, original_tp=54000
        # watermark=58000, 理论 TP = 58000 * 1.1 = 63800
        # 但 floor protection 要求 TP <= 54000
        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal("60000"),
            watermark_price=Decimal("58000"),  # 水位线上升（不利）
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("54000")},
        )
        sl_order = create_sl_order(direction=Direction.SHORT, trigger_price=Decimal("62000"))
        tp1_order = create_tp_order(
            direction=Direction.SHORT,
            price=Decimal("54000"),
        )
        orders = [sl_order, tp1_order]
        kline = create_kline(low=Decimal("58000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 由于 floor protection，TP 不高于原始价格
        # theoretical_tp = 58000 * 1.1 = 63800
        # 但 floor = min(54000, 63800) = 54000
        # min_required = 54000 * 0.999 = 53838
        # 63800 > 53838，不满足 SHORT 的阶梯条件
        assert tp1_order.price <= Decimal("54000")  # 不高于原始 TP


# ============================================================
# 3. Multi-Level Tests
# ============================================================

class TestTrailingTPMultiLevel:
    """多级别测试"""

    def test_only_enabled_levels_are_trailed(self):
        """仅 tp_trailing_enabled_levels 中的级别被追踪"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
            tp_trailing_enabled_levels=["TP2"],  # 仅 TP2 启用 trailing
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("75000"),  # 更高水位线，使 TP2 能被调整
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000"), "TP2": Decimal("70000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(order_role=OrderRole.TP1, price=Decimal("66000"))
        tp2_order = create_tp_order(order_role=OrderRole.TP2, price=Decimal("70000"))
        orders = [sl_order, tp1_order, tp2_order]
        kline = create_kline(high=Decimal("75000"))

        tp1_original = tp1_order.price
        tp2_original = tp2_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - TP1 价格不变（未启用），TP2 价格变化
        # TP2: theoretical_tp = 75000 * 0.99 = 74250
        #      min_required = 70000 * 1.003 = 70210
        #      74250 > 70210, 满足条件，TP2 应该被调整
        assert tp1_order.price == tp1_original
        assert tp2_order.price != tp2_original  # TP2 应该被调整
        expected_tp2 = Decimal("75000") * (Decimal("1") - Decimal("0.01"))
        assert tp2_order.price == expected_tp2

    def test_tp2_tp3_trailing_independent(self):
        """TP2 和 TP3 独立追踪，互不影响"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
            tp_trailing_enabled_levels=["TP2", "TP3"],
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("72000"),
            tp_trailing_activated=True,
            original_tp_prices={
                "TP2": Decimal("70000"),
                "TP3": Decimal("75000"),
            },
        )
        sl_order = create_sl_order()
        tp2_order = create_tp_order(order_role=OrderRole.TP2, price=Decimal("70000"))
        tp3_order = create_tp_order(order_role=OrderRole.TP3, price=Decimal("75000"))
        orders = [sl_order, tp2_order, tp3_order]
        kline = create_kline(high=Decimal("72000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        # TP2: theoretical_tp = 72000 * 0.99 = 71280
        #      min_required = 70000 * 1.003 = 70210
        #      71280 > 70210, 满足条件，TP2 应该被更新
        # TP3: theoretical_tp = 72000 * 0.99 = 71280
        #      min_required = 75000 * 1.003 = 75225
        #      71280 < 75225, 不满足条件，TP3 不更新

        # TP2 应该被更新
        expected_tp2 = Decimal("72000") * (Decimal("1") - Decimal("0.01"))
        assert tp2_order.price == expected_tp2

        # TP3 不应该被更新（水位线未达到）
        # 由于 floor protection，TP3 价格应保持原值
        assert tp3_order.price == Decimal("75000")

        # 应该只有一个事件（TP2）
        assert len(events) == 1
        assert events[0].event_type == "TP2"


# ============================================================
# 4. Event Recording Tests
# ============================================================

class TestTrailingTPEventRecording:
    """事件记录测试"""

    def test_tp_modified_event_generated(self):
        """调价时生成 event_category='tp_modified' 事件"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("70000"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        assert len(events) == 1
        event = events[0]
        assert event.event_category == "tp_modified"
        assert event.event_type == "TP1"

    def test_tp_modified_event_fields(self):
        """调价事件的 close_price/qty/pnl/fee 均为 None"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("70000"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(timestamp=1234567890000, high=Decimal("70000"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        event = events[0]
        assert event.close_price is None
        assert event.close_qty is None
        assert event.close_pnl is None
        assert event.close_fee is None
        assert event.close_time == kline.timestamp
        assert "TRAILING_TP" in event.exit_reason

    def test_no_event_when_no_update(self):
        """未达到调价条件时不生成事件"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.01"),  # 较大阶梯阈值
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("66500"),  # 水位线不足以触发更新
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("66500"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        assert len(events) == 0


# ============================================================
# 5. Edge Cases Tests
# ============================================================

class TestTrailingTPEdgeCases:
    """边界条件测试"""

    def test_tp_trailing_with_closed_position(self):
        """已平仓仓位不执行追踪"""
        # Arrange
        config = RiskManagerConfig(tp_trailing_enabled=True)
        manager = DynamicRiskManager(config=config)

        position = create_position(
            current_qty=Decimal("0"),
            is_closed=True,
            watermark_price=Decimal("70000"),
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        original_tp = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        assert tp1_order.price == original_tp
        assert len(events) == 0

    def test_tp_trailing_watermark_none(self):
        """watermark 为 None 时跳过"""
        # Arrange
        config = RiskManagerConfig(tp_trailing_enabled=True)
        manager = DynamicRiskManager(config=config)

        position = create_position(
            watermark_price=None,  # 水位线为 None
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        original_tp = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - watermark 会被更新，但 TTP 可能在 watermark 更新前就被调用
        # 实际上 watermark 会在 Step 2 被更新，然后 Step 4 使用更新后的 watermark
        # 这个测试验证的是 watermark 为 None 的初始状态
        # 由于 evaluate_and_mutate 会先更新 watermark，所以 TP 可能会被调整
        # 这里主要验证不会抛出异常
        assert tp1_order.price >= original_tp  # TP 价格只会上升或保持

    def test_tp_trailing_decimal_precision(self):
        """所有计算使用 Decimal，验证精度"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.5"),
            tp_trailing_percent=Decimal("0.0123456789"),  # 高精度
            tp_step_threshold=Decimal("0.003456789"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000.123456789"),
            watermark_price=Decimal("70000.987654321"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000.111111111")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000.111111111"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000.987654321"))

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 验证所有结果都是 Decimal
        assert isinstance(tp1_order.price, Decimal)
        assert isinstance(position.watermark_price, Decimal)

        if events:
            assert isinstance(events[0].close_time, int)
            # exit_reason 中的价格应该是 Decimal 的字符串表示
            assert "TRAILING_TP" in events[0].exit_reason

    def test_tp_trailing_with_zero_qty_position(self):
        """零仓位不执行追踪"""
        # Arrange
        config = RiskManagerConfig(tp_trailing_enabled=True)
        manager = DynamicRiskManager(config=config)

        position = create_position(
            current_qty=Decimal("0"),
            is_closed=False,  # 标记为未关闭，但数量为 0
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        original_tp = tp1_order.price

        # Act
        events = manager.evaluate_and_mutate(kline, position, orders)

        # Assert
        assert tp1_order.price == original_tp
        assert len(events) == 0

    def test_tp_trailing_activated_state_persists(self):
        """激活状态是单向的：一旦激活就不会关闭"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
        )
        manager = DynamicRiskManager(config=config)

        # 第一次调用：激活
        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("64000"),  # 达到激活阈值
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("64000"))

        # Act - 第一次调用
        manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 已激活
        assert position.tp_trailing_activated is True

        # 第二次调用：水位线下降（不利方向）
        position.watermark_price = Decimal("62000")
        kline2 = create_kline(high=Decimal("62000"))

        # Act - 第二次调用
        manager.evaluate_and_mutate(kline2, position, orders)

        # Assert - 激活状态保持
        assert position.tp_trailing_activated is True

    def test_multiple_klines_progressive_trailing(self):
        """多根 K 线逐步追踪测试"""
        # Arrange
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]

        # K 线 1: watermark=70000
        kline1 = create_kline(high=Decimal("70000"), timestamp=1000)
        events1 = manager.evaluate_and_mutate(kline1, position, orders)
        # theoretical_tp = 70000 * 0.99 = 69300
        # min_required = 66000 * 1.003 = 66198
        # 69300 > 66198, 更新
        assert tp1_order.price == Decimal("69300")
        assert len(events1) == 1

        # K 线 2: watermark=72000
        position.watermark_price = Decimal("72000")
        kline2 = create_kline(high=Decimal("72000"), timestamp=2000)
        events2 = manager.evaluate_and_mutate(kline2, position, orders)
        # theoretical_tp = 72000 * 0.99 = 71280
        # min_required = 69300 * 1.003 = 69507.9
        # 71280 > 69507.9, 更新
        assert tp1_order.price == Decimal("71280")
        assert len(events2) == 1

        # K 线 3: watermark 保持 72000（价格回撤）
        kline3 = create_kline(high=Decimal("71000"), timestamp=3000)
        events3 = manager.evaluate_and_mutate(kline3, position, orders)
        # watermark 保持 72000（只升不降）
        # theoretical_tp = 72000 * 0.99 = 71280
        # min_required = 71280 * 1.003 = 71493.84
        # 71280 < 71493.84, 不更新
        assert tp1_order.price == Decimal("71280")  # 价格保持
        assert len(events3) == 0


# ============================================================
# 6. Integration-like Tests (verify behavior with real calculations)
# ============================================================

class TestTrailingTPIntegration:
    """集成风格测试（验证实际计算结果）"""

    def test_design_doc_example_long(self):
        """
        验证设计文档附录 A 的 LONG 方向示例

        初始状态:
          entry_price = 60000
          original_tp = 66000 (1.5R)
          tp_trailing_percent = 0.01 (1%)
          tp_step_threshold = 0.003 (0.3%)
          activation_rr = 0.5

        激活阈值:
          activation_price = 60000 + 0.5 * (66000 - 60000) = 63000
        """
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
            tp_trailing_activation_rr=Decimal("0.5"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]

        # K 线 1: high=62000, watermark=62000 -> 未达激活阈值
        kline1 = create_kline(high=Decimal("62000"), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, orders)

        assert position.tp_trailing_activated is False
        assert tp1_order.price == Decimal("66000")

        # K 线 2: high=64000, watermark=64000 -> 达到激活阈值
        kline2 = create_kline(high=Decimal("64000"), timestamp=2000)
        manager.evaluate_and_mutate(kline2, position, orders)

        # 激活条件满足
        assert position.tp_trailing_activated is True

        # theoretical_tp = 64000 * 0.99 = 63360
        # min_required = 66000 * 1.003 = 66198
        # 63360 < 66198, 不更新
        assert tp1_order.price == Decimal("66000")

        # K 线 3: high=68000, watermark=68000
        kline3 = create_kline(high=Decimal("68000"), timestamp=3000)
        manager.evaluate_and_mutate(kline3, position, orders)

        # theoretical_tp = 68000 * 0.99 = 67320
        # min_required = 66000 * 1.003 = 66198
        # 67320 > 66198, 更新! TP: 66000 -> 67320
        assert tp1_order.price == Decimal("67320")

        # K 线 4: high=70000, watermark=70000
        kline4 = create_kline(high=Decimal("70000"), timestamp=4000)
        manager.evaluate_and_mutate(kline4, position, orders)

        # theoretical_tp = 70000 * 0.99 = 69300
        # min_required = 67320 * 1.003 = 67521.96
        # 69300 > 67521.96, 更新! TP: 67320 -> 69300
        assert tp1_order.price == Decimal("69300")

    def test_return_value_is_event_list(self):
        """验证 evaluate_and_mutate 返回事件列表"""
        config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_activation_rr=Decimal("0.3"),
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
        )
        manager = DynamicRiskManager(config=config)

        position = create_position(
            entry_price=Decimal("60000"),
            watermark_price=Decimal("70000"),
            tp_trailing_activated=True,
            original_tp_prices={"TP1": Decimal("66000")},
        )
        sl_order = create_sl_order()
        tp1_order = create_tp_order(price=Decimal("66000"))
        orders = [sl_order, tp1_order]
        kline = create_kline(high=Decimal("70000"))

        # Act
        result = manager.evaluate_and_mutate(kline, position, orders)

        # Assert - 返回值应该是列表
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], PositionCloseEvent)
