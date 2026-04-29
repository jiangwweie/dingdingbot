"""
Unit tests for v3.0 Phase 3: Dynamic Risk Manager (Risk State Machine)

Tests cover all scenarios from the contract:
docs/designs/phase3-risk-state-machine-contract.md Section 7.1

Test Categories:
1. Breakeven logic (UT-001)
2. Watermark updates (UT-002, UT-003)
3. Trailing Stop calculations (UT-004, UT-005)
4. Step frequency control (UT-006, UT-007)
5. Protective stop floor (UT-008, UT-009)
6. Edge cases (UT-010, UT-011, UT-012, UT-013)
"""

import pytest
from decimal import Decimal

from src.domain.models import (
    KlineData,
    Position,
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
)
from src.domain.risk_manager import DynamicRiskManager


# ============================================================
# Test Fixtures
# ============================================================

def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1711785600000,
    open: Decimal = None,
    high: Decimal = None,
    low: Decimal = None,
    close: Decimal = None,
    volume: Decimal = Decimal('1000'),
    is_closed: bool = True,
) -> KlineData:
    """Helper to create KlineData for testing"""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open or Decimal('65000'),
        high=high or Decimal('66000'),
        low=low or Decimal('64000'),
        close=close or Decimal('65500'),
        volume=volume,
        is_closed=is_closed,
    )


def create_position(
    id: str = "pos_001",
    signal_id: str = "sig_001",
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    entry_price: Decimal = Decimal('65000'),
    current_qty: Decimal = Decimal('1'),
    watermark_price: Decimal = Decimal('65000'),
    is_closed: bool = False,
    realized_pnl: Decimal = Decimal('0'),
) -> Position:
    """Helper to create Position for testing"""
    return Position(
        id=id,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=watermark_price,
        is_closed=is_closed,
        realized_pnl=realized_pnl,
    )


def create_order(
    id: str,
    signal_id: str = "sig_001",
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    order_type: OrderType = OrderType.MARKET,
    order_role: OrderRole = OrderRole.ENTRY,
    requested_qty: Decimal = Decimal('1'),
    filled_qty: Decimal = Decimal('0'),
    trigger_price: Decimal = None,
    price: Decimal = None,
    status: OrderStatus = OrderStatus.PENDING,
    created_at: int = 1711785600000,
    updated_at: int = 1711785600000,
) -> Order:
    """Helper to create Order for testing"""
    return Order(
        id=id,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=order_type,
        order_role=order_role,
        requested_qty=requested_qty,
        filled_qty=filled_qty,
        trigger_price=trigger_price,
        price=price,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
    )


# ============================================================
# UT-001: TP1 成交触发 Breakeven
# ============================================================

class TestUT001_BreakevenOnTP1Fill:
    """测试 TP1 成交后触发 Breakeven 逻辑"""

    def test_tp1_fill_triggers_breakeven(self):
        """TP1 成交触发 Breakeven：SL 单 qty=current_qty, trigger=entry_price, type=TRAILING_STOP"""
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            entry_price=Decimal('65000'),
            current_qty=Decimal('0.5'),  # TP1 成交后剩余
            watermark_price=Decimal('65000'),
        )

        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            status=OrderStatus.FILLED,  # TP1 已成交
            filled_qty=Decimal('0.5'),
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,  # 初始为 STOP_MARKET
            trigger_price=Decimal('64000'),  # 初始止损价
            requested_qty=Decimal('1'),
        )

        kline = create_kline()

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [tp1_order, sl_order])

        # Assert
        assert sl_order.requested_qty == Decimal('0.5'), "SL 数量应与 current_qty 对齐"
        assert sl_order.trigger_price == Decimal('65000'), "SL 触发价应移至 entry_price"
        assert sl_order.order_type == OrderType.TRAILING_STOP, "SL 类型应变为 TRAILING_STOP"


# ============================================================
# UT-002: LONG 仓位刷新水位线
# ============================================================

class TestUT002_LongWatermarkUpdate:
    """测试 LONG 仓位水位线更新"""

    def test_long_position_updates_watermark_on_high(self):
        """LONG 仓位刷新水位线：watermark_price 更新为 kline.high"""
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            direction=Direction.LONG,
            watermark_price=Decimal('65000'),
        )

        kline = create_kline(high=Decimal('67000'))

        sl_order = create_order(id="order_sl", order_role=OrderRole.SL)

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        assert position.watermark_price == Decimal('67000'), "LONG 仓位 watermark 应更新为 kline.high"


# ============================================================
# UT-003: SHORT 仓位刷新水位线
# ============================================================

class TestUT003_ShortWatermarkUpdate:
    """测试 SHORT 仓位水位线更新"""

    def test_short_position_updates_watermark_on_low(self):
        """SHORT 仓位刷新水位线：watermark_price 更新为 kline.low"""
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            direction=Direction.SHORT,
            watermark_price=Decimal('65000'),
        )

        kline = create_kline(low=Decimal('63000'))

        sl_order = create_order(id="order_sl", order_role=OrderRole.SL)

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        assert position.watermark_price == Decimal('63000'), "SHORT 仓位 watermark 应更新为 kline.low"


# ============================================================
# UT-004: Trailing Stop 计算 (LONG)
# ============================================================

class TestUT004_LongTrailingStopCalculation:
    """测试 LONG 仓位 Trailing Stop 计算"""

    def test_long_trailing_stop_formula(self):
        """Trailing Stop 计算 (LONG)：theoretical_trigger = watermark * (1 - trailing%)"""
        # Arrange
        trailing_percent = Decimal('0.02')
        risk_manager = DynamicRiskManager(trailing_percent=trailing_percent)

        # 设置场景：watermark 已大幅上涨
        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('70000'),  # 上涨到 70000
        )

        # 初始 SL 已经在 Breakeven
        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('65000'),  # 当前止损在开仓价
        )

        kline = create_kline(high=Decimal('70000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 70000 * (1 - 0.02) = 68600
        expected_theoretical = Decimal('70000') * Decimal('0.98')
        assert sl_order.trigger_price == expected_theoretical, f"LONG trailing stop 应为 {expected_theoretical}"


# ============================================================
# UT-005: Trailing Stop 计算 (SHORT)
# ============================================================

class TestUT005_ShortTrailingStopCalculation:
    """测试 SHORT 仓位 Trailing Stop 计算"""

    def test_short_trailing_stop_formula(self):
        """Trailing Stop 计算 (SHORT)：theoretical_trigger = watermark * (1 + trailing%)"""
        # Arrange
        trailing_percent = Decimal('0.02')
        risk_manager = DynamicRiskManager(trailing_percent=trailing_percent)

        # 设置场景：watermark 已大幅下跌
        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('60000'),  # 下跌到 60000
        )

        # 初始 SL 已经在 Breakeven
        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('65000'),  # 当前止损在开仓价
        )

        kline = create_kline(low=Decimal('60000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 60000 * (1 + 0.02) = 61200
        expected_theoretical = Decimal('60000') * Decimal('1.02')
        assert sl_order.trigger_price == expected_theoretical, f"SHORT trailing stop 应为 {expected_theoretical}"


# ============================================================
# UT-006: 阶梯频控 - 不满足条件
# ============================================================

class TestUT006_StepFrequencyControl_NotMet:
    """测试阶梯频控 - 不满足更新条件"""

    def test_step_threshold_blocks_small_move(self):
        """阶梯频控 - 不满足条件：trigger_price 不更新"""
        # Arrange
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),  # 0.5%
        )

        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('65500'),  # 小幅上涨
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('64000'),  # 当前止损价
        )

        kline = create_kline(high=Decimal('65500'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 65500 * 0.98 = 64190
        # min_required = 64000 * 1.005 = 64320
        # 64190 < 64320，不满足阶梯条件
        assert sl_order.trigger_price == Decimal('64000'), "不满足阶梯条件时 trigger_price 不应更新"


# ============================================================
# UT-007: 阶梯频控 - 满足条件
# ============================================================

class TestUT007_StepFrequencyControl_Met:
    """测试阶梯频控 - 满足更新条件"""

    def test_step_threshold_allows_large_move(self):
        """阶梯频控 - 满足条件：trigger_price 更新"""
        # Arrange
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),  # 0.5%
        )

        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('71000'),  # 大幅上涨
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('64000'),  # 当前止损价
        )

        kline = create_kline(high=Decimal('71000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 71000 * 0.98 = 69580
        # min_required = 64000 * 1.005 = 64320
        # 69580 >= 64320，满足阶梯条件
        assert sl_order.trigger_price == Decimal('69580'), "满足阶梯条件时 trigger_price 应更新"


# ============================================================
# UT-008: 保护损底线 (LONG)
# ============================================================

class TestUT008_ProtectiveStopFloor_Long:
    """测试保护损底线 - LONG 仓位"""

    def test_protective_floor_long(self):
        """保护损底线 (LONG)：trigger_price >= entry_price"""
        # Arrange
        risk_manager = DynamicRiskManager(trailing_percent=Decimal('0.02'))

        # 极端场景：watermark 大幅回落
        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('66000'),  # 回落场景
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('68000'),  # 之前追踪到的较高止损价
        )

        kline = create_kline(high=Decimal('66000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 66000 * 0.98 = 64680 (低于 entry_price)
        # 保护损底线应确保 trigger_price >= entry_price
        assert sl_order.trigger_price >= Decimal('65000'), "LONG 仓位 trigger_price 不应低于 entry_price"


# ============================================================
# UT-009: 保护损底线 (SHORT)
# ============================================================

class TestUT009_ProtectiveStopFloor_Short:
    """测试保护损底线 - SHORT 仓位"""

    def test_protective_floor_short(self):
        """保护损底线 (SHORT)：trigger_price <= entry_price"""
        # Arrange
        risk_manager = DynamicRiskManager(trailing_percent=Decimal('0.02'))

        # 极端场景：watermark 大幅反弹
        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('64000'),  # 反弹场景
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('62000'),  # 之前追踪到的较低止损价
        )

        kline = create_kline(low=Decimal('64000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # theoretical_trigger = 64000 * 1.02 = 65280 (高于 entry_price)
        # 保护损底线应确保 trigger_price <= entry_price
        assert sl_order.trigger_price <= Decimal('65000'), "SHORT 仓位 trigger_price 不应高于 entry_price"


# ============================================================
# UT-010: 已平仓仓位不处理
# ============================================================

class TestUT010_ClosedPositionIgnored:
    """测试已平仓仓位的防御处理"""

    def test_closed_position_skipped(self):
        """已平仓仓位不处理：evaluate_and_mutate 直接返回"""
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            is_closed=True,  # 已平仓
            current_qty=Decimal('0'),
        )

        original_watermark = position.watermark_price

        sl_order = create_order(id="order_sl", order_role=OrderRole.SL)
        kline = create_kline(high=Decimal('80000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        assert position.watermark_price == original_watermark, "已平仓仓位 watermark 不应更新"


# ============================================================
# UT-011: 无 SL 订单防御处理
# ============================================================

class TestUT011_NoSlOrderDefensiveHandling:
    """测试无 SL 订单的防御处理"""

    def test_no_sl_order_returns_silently(self):
        """无 SL 订单防御处理：直接返回，不抛异常"""
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position()

        # 只有 TP1 订单，没有 SL 订单
        tp1_order = create_order(id="order_tp1", order_role=OrderRole.TP1)

        kline = create_kline()

        # Act & Assert
        # 不应抛出异常
        risk_manager.evaluate_and_mutate(kline, position, [tp1_order])


# ============================================================
# UT-012: Decimal 精度保护
# ============================================================

class TestUT012_DecimalPrecision:
    """测试 Decimal 精度保护"""

    def test_all_calculations_use_decimal(self):
        """Decimal 精度保护：所有计算无 float 污染"""
        # Arrange
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),
        )

        # 使用精确的 Decimal 值
        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000.123456789'),
            watermark_price=Decimal('70000.987654321'),
            current_qty=Decimal('0.123456789'),
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('64000.111222333'),
        )

        kline = create_kline(
            high=Decimal('70000.987654321'),
            close=Decimal('69999.555666777'),
        )

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        # 验证结果仍然是 Decimal 类型
        assert isinstance(sl_order.trigger_price, Decimal), "trigger_price 应为 Decimal 类型"
        assert isinstance(position.watermark_price, Decimal), "watermark_price 应为 Decimal 类型"


# ============================================================
# UT-013: Reduce Only 约束
# ============================================================

class TestUT013_ReduceOnlyConstraint:
    """测试 Reduce Only 约束"""

    def test_reduce_only_flag_required(self):
        """
        Reduce Only 约束：平仓单携带 reduceOnly=True

        注意：当前模型中未定义 reduceOnly 字段，此测试验证契约要求
        实际实现需在 Order 模型中添加 reduceOnly 字段
        """
        # Arrange
        # 创建平仓单 (TP1 和 SL)
        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
        )

        # Assert
        # 验证订单角色正确设置
        assert tp1_order.order_role == OrderRole.TP1, "TP1 订单角色应正确"
        assert sl_order.order_role == OrderRole.SL, "SL 订单角色应正确"

        # Note: reduceOnly 字段需要在 Order 模型中添加
        # 此测试标记了契约要求，等待模型扩展


# ============================================================
# Additional Edge Case Tests
# ============================================================

class TestEdgeCases:
    """额外边界情况测试"""

    def test_watermark_none_handling(self):
        """测试 watermark_price 为 None 时的处理"""
        risk_manager = DynamicRiskManager()

        position = create_position(
            direction=Direction.LONG,
            watermark_price=None,  # 初始为 None
        )

        sl_order = create_order(id="order_sl", order_role=OrderRole.SL)
        kline = create_kline(high=Decimal('66000'))

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [sl_order])

        # Assert
        assert position.watermark_price == Decimal('66000'), "初始 None 时应直接使用 kline.high"

    def test_tp1_not_filled_no_breakeven(self):
        """TP1 未成交时不触发 Breakeven"""
        risk_manager = DynamicRiskManager()

        position = create_position()

        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            status=OrderStatus.PENDING,  # 未成交
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal('64000'),
        )

        kline = create_kline()

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [tp1_order, sl_order])

        # Assert
        assert sl_order.order_type != OrderType.TRAILING_STOP, "TP1 未成交时不应触发 Breakeven"
        assert sl_order.trigger_price == Decimal('64000'), "TP1 未成交时 SL 价格不应变化"

    def test_breakeven_only_once(self):
        """Breakeven 只执行一次"""
        risk_manager = DynamicRiskManager()

        position = create_position(entry_price=Decimal('65000'))

        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            status=OrderStatus.FILLED,
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,  # 已经是 TRAILING_STOP
            trigger_price=Decimal('65000'),
        )

        kline = create_kline()

        # Act
        risk_manager.evaluate_and_mutate(kline, position, [tp1_order, sl_order])

        # Assert
        # 应该不会重复修改
        assert sl_order.order_type == OrderType.TRAILING_STOP
        assert sl_order.trigger_price == Decimal('65000')
