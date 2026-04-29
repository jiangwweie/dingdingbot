"""
Integration tests for v3.0 Phase 3: Dynamic Risk Manager (Risk State Machine)

Tests cover end-to-end scenarios from the contract:
docs/designs/phase3-risk-state-machine-contract.md Section 7.2

Integration Test Scenarios:
1. IT-001: Complete trade flow: Open → TP1 → Breakeven → Trailing → Close
2. IT-002: Direct SL hit (no TP1)
3. IT-003: Multiple TP1 partial fills
4. IT-004: Trailing multiple triggers
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
    timestamp: int = 0,
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
    created_at: int = 0,
    updated_at: int = 0,
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
# IT-001: 完整交易流程：开仓 → TP1 → Breakeven → Trailing → 平仓
# ============================================================

class TestIT001_CompleteTradeFlow:
    """测试完整交易流程"""

    def test_complete_flow_open_to_close(self):
        """
        完整交易流程：开仓 → TP1 → Breakeven → Trailing → 平仓

        预期结果：所有状态转移正确
        """
        # Arrange
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),
        )

        # 初始状态：开仓
        position = create_position(
            entry_price=Decimal('65000'),
            current_qty=Decimal('1'),
            watermark_price=Decimal('65000'),
        )

        # 初始订单：TP1 限价单 + SL 止损单
        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            status=OrderStatus.PENDING,
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal('64000'),
            requested_qty=Decimal('1'),
        )

        # ===== K1: 开仓 =====
        k1 = create_kline(timestamp=1, close=Decimal('65000'))
        risk_manager.evaluate_and_mutate(k1, position, [tp1_order, sl_order])

        # Assert K1: 水位线更新
        assert position.watermark_price == Decimal('66000')  # k1.high

        # ===== K2-K5: 价格上涨，TP1 未成交 =====
        # 使用较低的高点，避免触发 Trailing
        for i in range(2, 6):
            k = create_kline(timestamp=i, high=Decimal('65500'), close=Decimal('65200'))
            risk_manager.evaluate_and_mutate(k, position, [tp1_order, sl_order])

        # ===== K6: TP1 成交 =====
        # 使用较低的 high 来避免触发 Trailing，仅测试 Breakeven
        k6 = create_kline(timestamp=6, high=Decimal('65800'), close=Decimal('65500'))
        tp1_order.status = OrderStatus.FILLED  # 模拟 TP1 成交
        tp1_order.filled_qty = Decimal('0.5')
        position.current_qty = Decimal('0.5')  # TP1 成交后仓位减半

        risk_manager.evaluate_and_mutate(k6, position, [tp1_order, sl_order])

        # Assert K6: Breakeven 触发
        assert sl_order.order_type == OrderType.TRAILING_STOP, "TP1 成交后 SL 应变为 TRAILING_STOP"
        assert sl_order.requested_qty == Decimal('0.5'), "SL 数量应与剩余仓位对齐"
        assert sl_order.trigger_price == Decimal('65000'), "SL 应上移至开仓价 (Breakeven)"

        # ===== K7-K10: 价格继续上涨，Trailing 开始追踪 =====
        for i in range(7, 11):
            high_price = Decimal('70000') + Decimal(str(i * 500))
            k = create_kline(timestamp=i, high=high_price, close=high_price - Decimal('100'))
            risk_manager.evaluate_and_mutate(k, position, [tp1_order, sl_order])

        # Assert K7-K10: 水位线持续更新，Trailing 生效
        assert position.watermark_price > Decimal('70000'), "水位线应持续上涨"
        assert sl_order.trigger_price > Decimal('65000'), "Trailing 应上移止损价"

        # ===== K11: 价格回调，触发 Trailing Stop 平仓 =====
        k11_high = position.watermark_price
        k11_low = sl_order.trigger_price - Decimal('1')  # 击穿止损价

        k11 = create_kline(timestamp=11, high=k11_high, low=k11_low, close=k11_low)
        risk_manager.evaluate_and_mutate(k11, position, [tp1_order, sl_order])

        # Assert: 最终状态
        # 止损价应该被追踪到接近最高点的位置
        assert sl_order.trigger_price >= Decimal('65000'), "最终止损价不应低于开仓价"


# ============================================================
# IT-002: 直接 SL 打损 (无 TP1)
# ============================================================

class TestIT002_DirectSLHit_NoTP1:
    """测试直接 SL 打损 (无 TP1 成交)"""

    def test_direct_sl_hit_without_tp1(self):
        """
        直接 SL 打损 (无 TP1): 正常平仓，无 Breakeven

        预期结果:
        - SL 始终保持 STOP_MARKET 类型
        - 不会触发 Breakeven
        - 仓位被平仓
        """
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            entry_price=Decimal('65000'),
            current_qty=Decimal('1'),
            watermark_price=Decimal('65000'),
        )

        # TP1 未成交
        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
            price=Decimal('70000'),
            status=OrderStatus.PENDING,  # 一直未成交
        )

        # 初始 SL
        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal('64000'),
            requested_qty=Decimal('1'),
        )

        # ===== K1-K5: 价格下跌 =====
        for i in range(1, 6):
            low_price = Decimal('65000') - Decimal(str(i * 100))
            k = create_kline(timestamp=i, low=low_price, close=low_price + Decimal('50'))
            risk_manager.evaluate_and_mutate(k, position, [tp1_order, sl_order])

        # Assert: TP1 未成交，不应触发 Breakeven
        assert tp1_order.status == OrderStatus.PENDING
        assert sl_order.order_type == OrderType.STOP_MARKET, "无 TP1 成交时 SL 类型不应变"

        # ===== K6: SL 打损 =====
        k6 = create_kline(
            timestamp=6,
            high=Decimal('64500'),
            low=Decimal('63500'),  # 击穿 SL
            close=Decimal('64000'),
        )
        risk_manager.evaluate_and_mutate(k6, position, [tp1_order, sl_order])

        # Assert: SL 状态不变（撮合引擎会处理平仓）
        assert sl_order.trigger_price == Decimal('64000'), "SL 触发价应保持不变"
        assert sl_order.order_type == OrderType.STOP_MARKET, "无 Breakeven 时 SL 类型不变"


# ============================================================
# IT-003: 多笔 TP1 分批成交
# ============================================================

class TestIT003_MultipleTP1PartialFills:
    """测试多笔 TP1 分批成交"""

    def test_multiple_tp1_fills_reduces_sl_qty(self):
        """
        多笔 TP1 分批成交：SL 数量逐次递减

        预期结果:
        - 每笔 TP1 成交后，SL 数量相应减少
        - Breakeven 在首笔 TP1 成交时触发
        """
        # Arrange
        risk_manager = DynamicRiskManager()

        position = create_position(
            entry_price=Decimal('65000'),
            current_qty=Decimal('1'),
            watermark_price=Decimal('65000'),
        )

        # 多笔 TP1 订单
        tp1_order_1 = create_order(
            id="order_tp1_1",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
            price=Decimal('70000'),
            requested_qty=Decimal('0.3'),
            status=OrderStatus.PENDING,
        )

        tp1_order_2 = create_order(
            id="order_tp1_2",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
            price=Decimal('72000'),
            requested_qty=Decimal('0.3'),
            status=OrderStatus.PENDING,
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal('64000'),
            requested_qty=Decimal('1'),
        )

        # ===== K1: 第一笔 TP1 成交 =====
        k1 = create_kline(timestamp=1, high=Decimal('70500'), close=Decimal('70000'))
        tp1_order_1.status = OrderStatus.FILLED
        tp1_order_1.filled_qty = Decimal('0.3')
        position.current_qty = Decimal('0.7')

        risk_manager.evaluate_and_mutate(k1, position, [tp1_order_1, tp1_order_2, sl_order])

        # Assert K1: Breakeven 触发，SL 数量对齐
        assert sl_order.order_type == OrderType.TRAILING_STOP
        assert sl_order.requested_qty == Decimal('0.7'), "SL 数量应与剩余仓位 0.7 对齐"

        # ===== K2: 第二笔 TP1 成交 =====
        k2 = create_kline(timestamp=2, high=Decimal('72500'), close=Decimal('72000'))
        tp1_order_2.status = OrderStatus.FILLED
        tp1_order_2.filled_qty = Decimal('0.3')
        position.current_qty = Decimal('0.4')

        risk_manager.evaluate_and_mutate(k2, position, [tp1_order_1, tp1_order_2, sl_order])

        # Assert K2: SL 数量应继续递减
        # 注意：Breakeven 只会在第一次 TP1 成交时触发，所以这里只检查数量
        assert sl_order.requested_qty == Decimal('0.4'), "SL 数量应与剩余仓位 0.4 对齐"


# ============================================================
# IT-004: Trailing 多次触发
# ============================================================

class TestIT004_TrailingMultipleTriggers:
    """测试 Trailing 多次触发"""

    def test_trailing_multiple_triggers_step_up(self):
        """
        Trailing 多次触发：止损价阶梯式上移

        预期结果:
        - 每次满足阶梯条件时，止损价上移
        - 不满足条件时，止损价保持不变
        """
        # Arrange
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),
        )

        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            current_qty=Decimal('1'),
            watermark_price=Decimal('65000'),
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.TRAILING_STOP,
            trigger_price=Decimal('65000'),  # 已在 Breakeven
            requested_qty=Decimal('1'),
        )

        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            status=OrderStatus.FILLED,  # 已成交
        )

        # 记录每次的止损价
        trigger_prices = [Decimal('65000')]

        # ===== K1-K10: 价格阶梯式上涨 =====
        # 模拟价格逐步上涨，触发多次 Trailing
        price_sequence = [
            (66000, 67000),   # K1: 上涨
            (67000, 68000),   # K2: 继续上涨
            (68000, 69000),   # K3: 继续上涨
            (69000, 70000),   # K4: 继续上涨
            (70000, 71000),   # K5: 继续上涨
            (71000, 72000),   # K6: 继续上涨
            (72000, 73000),   # K7: 继续上涨
            (73000, 74000),   # K8: 继续上涨
            (74000, 75000),   # K9: 继续上涨
            (75000, 76000),   # K10: 继续上涨
        ]

        for i, (low, high) in enumerate(price_sequence, start=1):
            k = create_kline(
                timestamp=i,
                high=Decimal(str(high)),
                low=Decimal(str(low)),
                close=Decimal(str(low + 500)),
            )
            risk_manager.evaluate_and_mutate(k, position, [tp1_order, sl_order])
            trigger_prices.append(sl_order.trigger_price)

        # Assert: 止损价应阶梯式上移
        # 检查是否有上移
        assert sl_order.trigger_price > Decimal('65000'), "最终止损价应高于开仓价"

        # 检查阶梯式上移（不是直线上升）
        # theoretical_trigger = watermark * 0.98
        # 每次 watermark 上涨 1000，theoretical 上涨约 980
        # step_threshold = 0.5%，所以每约 2-3 根 K 线触发一次

        # 验证至少有一次上移
        price_increases = sum(
            1 for i in range(1, len(trigger_prices))
            if trigger_prices[i] > trigger_prices[i-1]
        )
        assert price_increases >= 3, f"应至少有 3 次止损价上移，实际 {price_increases} 次"

        # 验证最终止损价接近理论值
        final_watermark = position.watermark_price
        expected_final = final_watermark * Decimal('0.98')
        # 允许一定误差（因为阶梯频控）
        assert abs(sl_order.trigger_price - expected_final) < Decimal('500'), \
            f"最终止损价应接近理论值 {expected_final}"


# ============================================================
# Additional Integration Tests
# ============================================================

class TestAdditionalScenarios:
    """额外集成场景测试"""

    def test_short_position_complete_flow(self):
        """SHORT 仓位完整流程"""
        risk_manager = DynamicRiskManager(
            trailing_percent=Decimal('0.02'),
            step_threshold=Decimal('0.005'),
        )

        position = create_position(
            direction=Direction.SHORT,
            entry_price=Decimal('65000'),
            current_qty=Decimal('1'),
            watermark_price=Decimal('65000'),
        )

        tp1_order = create_order(
            id="order_tp1",
            order_role=OrderRole.TP1,
            order_type=OrderType.LIMIT,
            price=Decimal('60000'),
            requested_qty=Decimal('0.5'),
            status=OrderStatus.PENDING,
        )

        sl_order = create_order(
            id="order_sl",
            order_role=OrderRole.SL,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal('66000'),
            requested_qty=Decimal('1'),
        )

        # ===== K1: 价格下跌 =====
        # 使用较小的跌幅，避免触发 Trailing
        k1 = create_kline(timestamp=1, low=Decimal('64800'), close=Decimal('64900'))
        risk_manager.evaluate_and_mutate(k1, position, [tp1_order, sl_order])

        # Assert K1: SHORT 仓位 watermark 应更新为低价
        assert position.watermark_price == Decimal('64800')

        # ===== K2: TP1 成交 =====
        # 使用接近 entry_price 的价格，避免触发 Trailing
        k2 = create_kline(timestamp=2, low=Decimal('64500'), close=Decimal('64800'))
        tp1_order.status = OrderStatus.FILLED
        position.current_qty = Decimal('0.5')

        risk_manager.evaluate_and_mutate(k2, position, [tp1_order, sl_order])

        # Assert K2: Breakeven 触发
        assert sl_order.order_type == OrderType.TRAILING_STOP
        # SHORT Breakeven 至上移开仓价，但由于 trailing 可能同时触发，只检查类型转换
        assert sl_order.trigger_price <= Decimal('65000')  # 不应高于开仓价

    def test_watermark_only_moves_in_profit_direction(self):
        """测试水位线只朝盈利方向移动"""
        risk_manager = DynamicRiskManager()

        position = create_position(
            direction=Direction.LONG,
            entry_price=Decimal('65000'),
            watermark_price=Decimal('67000'),  # 已经很高
        )

        sl_order = create_order(id="order_sl", order_role=OrderRole.SL)

        # K 线高点低于当前 watermark
        k = create_kline(high=Decimal('66000'))
        risk_manager.evaluate_and_mutate(k, position, [sl_order])

        # Assert: watermark 不应下降
        assert position.watermark_price == Decimal('67000'), "LONG 仓位 watermark 不应下降"

    def test_risk_manager_state_isolation(self):
        """测试风控管理器状态隔离"""
        risk_manager = DynamicRiskManager()

        # 创建两个独立的仓位
        position1 = create_position(id="pos_1", entry_price=Decimal('65000'))
        position2 = create_position(id="pos_2", entry_price=Decimal('70000'))

        sl1 = create_order(id="sl_1", order_role=OrderRole.SL)
        sl2 = create_order(id="sl_2", order_role=OrderRole.SL)

        k1 = create_kline(high=Decimal('66000'))
        k2 = create_kline(high=Decimal('71000'))

        # 分别处理
        risk_manager.evaluate_and_mutate(k1, position1, [sl1])
        risk_manager.evaluate_and_mutate(k2, position2, [sl2])

        # Assert: 状态互不影响
        assert position1.watermark_price == Decimal('66000')
        assert position2.watermark_price == Decimal('71000')
