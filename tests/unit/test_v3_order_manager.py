"""
Unit tests for OrderManager and OrderStrategy (Phase 4)

Test coverage:
- UT-001: OrderStrategy single TP configuration
- UT-002: OrderStrategy multi TP configuration
- UT-003: OrderStrategy ratio validation
- UT-004: create_order_chain generates only ENTRY orders
- UT-005: handle_order_filled ENTRY filled generates TP + SL
- UT-006: TP target price calculation (LONG)
- UT-007: TP target price calculation (SHORT)
- UT-008: handle_order_filled TP1 filled updates SL quantity
- UT-009: handle_order_filled SL filled cancels all TP orders
- UT-010: apply_oco_logic fully closed cancels all pending orders
- UT-011: apply_oco_logic partially closed updates SL quantity
- UT-012: get_order_chain_status returns correct status
- UT-013: Decimal precision protection
- UT-014: Responsibility boundary verification
"""
import pytest
from decimal import Decimal
from typing import List

from src.domain.models import (
    Order,
    OrderStrategy,
    OrderType,
    OrderRole,
    OrderStatus,
    Position,
    Direction,
    Account,
)
from src.domain.order_manager import OrderManager


# ============================================================
# OrderStrategy Tests
# ============================================================

class TestOrderStrategy:
    """OrderStrategy 类测试"""

    def test_ut_001_single_tp_config(self):
        """UT-001: OrderStrategy 单 TP 配置"""
        strategy = OrderStrategy(
            id="std_single_tp",
            name="标准单 TP",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
            initial_stop_loss_rr=Decimal('-1.0'),
            trailing_stop_enabled=True,
            oco_enabled=True,
        )

        assert strategy.tp_levels == 1
        assert strategy.tp_ratios == [Decimal('1.0')]
        assert strategy.validate_ratios() is True

    def test_ut_002_multi_tp_config(self):
        """UT-002: OrderStrategy 多 TP 配置"""
        strategy = OrderStrategy(
            id="multi_tp",
            name="多级别止盈",
            tp_levels=3,
            tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
            initial_stop_loss_rr=Decimal('-1.0'),
            trailing_stop_enabled=True,
            oco_enabled=True,
        )

        assert strategy.tp_levels == 3
        assert len(strategy.tp_ratios) == 3
        assert strategy.validate_ratios() is True
        assert strategy.get_tp_ratio(1) == Decimal('0.5')
        assert strategy.get_tp_ratio(2) == Decimal('0.3')
        assert strategy.get_tp_ratio(3) == Decimal('0.2')

    def test_ut_003_ratio_validation_invalid(self):
        """UT-003: OrderStrategy 比例验证失败 (总和≠1.0)"""
        # 比例总和不等于 1.0 应该抛出异常
        with pytest.raises(ValueError, match="tp_ratios 总和必须为 1.0"):
            OrderStrategy(
                id="invalid_ratios",
                name="无效比例",
                tp_levels=2,
                tp_ratios=[Decimal('0.5'), Decimal('0.6')],  # 总和 1.1
            )

    def test_ut_003_ratio_validation_empty(self):
        """UT-003b: 空比例列表验证"""
        strategy = OrderStrategy(
            id="empty_ratios",
            name="空比例",
            tp_levels=1,
            tp_ratios=[],
        )
        # 空列表应该返回 False
        assert strategy.validate_ratios() is False

    def test_ut_013_decimal_precision(self):
        """UT-013: Decimal 精度保护"""
        # 所有计算应该使用 Decimal，无 float 污染
        strategy = OrderStrategy(
            id="decimal_test",
            name="精度测试",
            tp_ratios=[Decimal('0.3333333333333333'), Decimal('0.6666666666666667')],
        )
        # 允许小误差
        total = sum(strategy.tp_ratios)
        assert abs(total - Decimal('1.0')) < Decimal('0.0001')


# ============================================================
# OrderManager Tests
# ============================================================

class TestOrderManager:
    """OrderManager 类测试"""

    def test_ut_004_create_order_chain_only_entry(self):
        """UT-004: create_order_chain 仅生成 ENTRY 订单"""
        manager = OrderManager()
        strategy = OrderStrategy(
            id="test_strategy",
            name="测试策略",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
        )

        orders = manager.create_order_chain(
            strategy=strategy,
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # 应该只返回 1 个 ENTRY 订单
        assert len(orders) == 1
        assert orders[0].order_role == OrderRole.ENTRY
        assert orders[0].order_type == OrderType.MARKET
        assert orders[0].requested_qty == Decimal('1.0')
        # TP/SL 订单尚未生成
        assert not any(o.order_role == OrderRole.TP1 for o in orders)
        assert not any(o.order_role == OrderRole.SL for o in orders)

    def test_ut_005_handle_order_filled_entry_generates_tp_sl(self):
        """UT-005: handle_order_filled ENTRY 成交动态生成 TP + SL"""
        manager = OrderManager()

        # 模拟已成交的 ENTRY 订单
        entry_order = Order(
            id="ord_entry_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('65065'),  # 实际成交价（滑点后）
            status=OrderStatus.FILLED,
            created_at=1000000,
            updated_at=1000000,
        )

        # 模拟仓位
        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('1.0'),
        )
        positions_map = {"sig_test_001": position}
        active_orders: List[Order] = []

        # 处理 ENTRY 成交
        new_orders = manager.handle_order_filled(
            filled_order=entry_order,
            active_orders=active_orders,
            positions_map=positions_map,
        )

        # 应该生成 TP 和 SL 订单
        assert len(new_orders) == 2
        tp_order = next(o for o in new_orders if o.order_role == OrderRole.TP1)
        sl_order = next(o for o in new_orders if o.order_role == OrderRole.SL)

        # TP/SL 应该基于实际开仓价计算
        assert tp_order.price is not None
        assert sl_order.trigger_price is not None
        # TP 价格应该 > 入场价 (LONG)
        assert tp_order.price > entry_order.average_exec_price
        # SL 价格应该 < 入场价 (LONG)
        assert sl_order.trigger_price < entry_order.average_exec_price

    def test_ut_006_tp_price_calculation_long(self):
        """UT-006: TP 目标价格计算 (LONG)"""
        manager = OrderManager()

        # LONG: tp_price = actual_entry + RR × (actual_entry - sl)
        actual_entry = Decimal('65065')
        stop_loss = Decimal('64000')
        rr_multiple = Decimal('1.5')

        tp_price = manager._calculate_tp_price(
            actual_entry_price=actual_entry,
            stop_loss_price=stop_loss,
            rr_multiple=rr_multiple,
            direction=Direction.LONG,
        )

        # 预期：65065 + 1.5 × (65065 - 64000) = 65065 + 1.5 × 1065 = 65065 + 1597.5 = 66662.5
        expected_tp = actual_entry + rr_multiple * (actual_entry - stop_loss)
        assert tp_price == expected_tp

    def test_ut_007_tp_price_calculation_short(self):
        """UT-007: TP 目标价格计算 (SHORT)"""
        manager = OrderManager()

        # SHORT: tp_price = actual_entry - RR × (sl - actual_entry)
        actual_entry = Decimal('65000')
        stop_loss = Decimal('66000')
        rr_multiple = Decimal('1.5')

        tp_price = manager._calculate_tp_price(
            actual_entry_price=actual_entry,
            stop_loss_price=stop_loss,
            rr_multiple=rr_multiple,
            direction=Direction.SHORT,
        )

        # 预期：65000 - 1.5 × (66000 - 65000) = 65000 - 1.5 × 1000 = 65000 - 1500 = 63500
        expected_tp = actual_entry - rr_multiple * (stop_loss - actual_entry)
        assert tp_price == expected_tp

    def test_ut_008_tp_filled_updates_sl_quantity(self):
        """UT-008: handle_order_filled TP1 成交更新 SL 数量"""
        manager = OrderManager()

        # 模拟已成交的 TP1 订单
        tp_order = Order(
            id="ord_tp1_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0.5'),
            price=Decimal('66065'),
            status=OrderStatus.FILLED,
            created_at=1000000,
            updated_at=1000000,
        )

        # 模拟仓位（TP1 成交后剩余 0.5）
        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('0.5'),  # TP1 成交后剩余
        )

        # 模拟 SL 订单
        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),  # 初始数量
            trigger_price=Decimal('64000'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        active_orders = [sl_order]

        # 处理 TP 成交
        manager.handle_order_filled(
            filled_order=tp_order,
            active_orders=active_orders,
            positions_map={"sig_test_001": position},
        )

        # SL 数量应该更新为 current_qty
        assert sl_order.requested_qty == Decimal('0.5')

    def test_ut_009_sl_filled_cancels_tp_orders(self):
        """UT-009: handle_order_filled SL 成交撤销所有 TP 订单"""
        manager = OrderManager()

        # 模拟已成交的 SL 订单
        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            trigger_price=Decimal('64000'),
            status=OrderStatus.FILLED,
            created_at=1000000,
            updated_at=1000000,
        )

        # 模拟 TP 订单
        tp_order = Order(
            id="ord_tp1_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('1.0'),
            price=Decimal('66065'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        active_orders = [tp_order]

        # 处理 SL 成交
        manager.handle_order_filled(
            filled_order=sl_order,
            active_orders=active_orders,
            positions_map={},
        )

        # TP 订单应该被撤销
        assert tp_order.status == OrderStatus.CANCELED

    def test_ut_010_oco_fully_closed_cancels_pending(self):
        """UT-010: apply_oco_logic 完全平仓撤销所有挂单"""
        manager = OrderManager()

        # 模拟仓位归零
        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('0'),  # 完全平仓
        )

        # 模拟挂单
        tp_order = Order(
            id="ord_tp2_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.3'),
            price=Decimal('67065'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            trigger_price=Decimal('64000'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        active_orders = [tp_order, sl_order]
        filled_order = tp_order  # 假设是 TP 成交触发

        # 执行 OCO 逻辑
        canceled = manager.apply_oco_logic(
            filled_order=filled_order,
            active_orders=active_orders,
            position=position,
        )

        # current_qty == 0 时，所有挂单应该被撤销
        assert tp_order.status == OrderStatus.CANCELED
        assert sl_order.status == OrderStatus.CANCELED
        assert len(canceled) == 2

    def test_ut_011_oco_partially_closed_updates_sl(self):
        """UT-011: apply_oco_logic 部分平仓更新 SL 数量"""
        manager = OrderManager()

        # 模拟部分平仓
        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('0.5'),  # 部分平仓
        )

        # 模拟 SL 订单
        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            trigger_price=Decimal('64000'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        active_orders = [sl_order]
        filled_order = Order(
            id="ord_tp1_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            status=OrderStatus.FILLED,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0.5'),
            created_at=1000000,
            updated_at=1000000,
        )

        # 执行 OCO 逻辑
        manager.apply_oco_logic(
            filled_order=filled_order,
            active_orders=active_orders,
            position=position,
        )

        # SL 数量应该更新为 current_qty
        assert sl_order.requested_qty == Decimal('0.5')

    def test_ut_012_get_order_chain_status(self):
        """UT-012: get_order_chain_status 返回正确状态字典"""
        manager = OrderManager()

        # 模拟订单链
        entry_order = Order(
            id="ord_entry_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1000000,
            updated_at=1000000,
        )

        tp_order = Order(
            id="ord_tp1_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0.5'),
            price=Decimal('66065'),
            status=OrderStatus.FILLED,
            created_at=1000000,
            updated_at=1000000,
        )

        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('0.5'),
            trigger_price=Decimal('64000'),
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        orders = [entry_order, tp_order, sl_order]

        status = manager.get_order_chain_status(
            orders=orders,
            signal_id="sig_test_001",
        )

        assert status["entry_filled"] is True
        assert status["tp_filled_count"] == 1
        assert status["sl_status"] == "OPEN"
        assert status["remaining_qty"] == Decimal('0.5')
        assert status["closed_percent"] == Decimal('50')

    def test_ut_014_responsibility_boundary(self):
        """UT-014: 职责边界验证 - OrderManager 修改 SL 数量，DynamicRiskManager 修改 SL 价格"""
        manager = OrderManager()

        # OrderManager 职责：更新 SL 的 requested_qty
        sl_order = Order(
            id="ord_sl_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            trigger_price=Decimal('64000'),  # 价格不应该被 OrderManager 修改
            status=OrderStatus.OPEN,
            created_at=1000000,
            updated_at=1000000,
        )

        # 模拟部分平仓
        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('0.5'),
        )

        active_orders = [sl_order]
        filled_order = Order(
            id="ord_tp1_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            status=OrderStatus.FILLED,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0.5'),
            created_at=1000000,
            updated_at=1000000,
        )

        # 执行 OCO 逻辑
        manager.apply_oco_logic(
            filled_order=filled_order,
            active_orders=active_orders,
            position=position,
        )

        # OrderManager 只修改数量，不修改价格
        assert sl_order.requested_qty == Decimal('0.5')  # 数量更新
        assert sl_order.trigger_price == Decimal('64000')  # 价格保持不变


# ============================================================
# Integration Tests
# ============================================================

class TestOrderManagerIntegration:
    """OrderManager 集成测试"""

    def test_it_001_full_order_chain_workflow(self):
        """IT-001: 完整订单链流程"""
        manager = OrderManager()
        strategy = OrderStrategy(
            id="test_strategy",
            name="测试策略",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
        )

        # Step 1: 创建 ENTRY 订单
        entry_orders = manager.create_order_chain(
            strategy=strategy,
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5')],
        )

        # Step 2: 模拟 ENTRY 成交
        entry_order = entry_orders[0]
        entry_order.status = OrderStatus.FILLED
        entry_order.filled_qty = Decimal('1.0')
        entry_order.average_exec_price = Decimal('65065')

        position = Position(
            id="pos_001",
            signal_id="sig_test_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('65065'),
            current_qty=Decimal('1.0'),
        )
        positions_map = {"sig_test_001": position}
        active_orders: List[Order] = []

        # Step 3: ENTRY 成交后动态生成 TP/SL
        new_orders = manager.handle_order_filled(
            filled_order=entry_order,
            active_orders=active_orders,
            positions_map=positions_map,
        )
        active_orders.extend(new_orders)

        # 验证 TP/SL 已生成
        assert any(o.order_role == OrderRole.TP1 for o in active_orders)
        assert any(o.order_role == OrderRole.SL for o in active_orders)

    def test_it_002_multi_tp_strategy_workflow(self):
        """IT-002: 多 TP 策略完整流程"""
        strategy = OrderStrategy(
            id="multi_tp",
            name="多级别止盈",
            tp_levels=3,
            tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
        )

        assert strategy.validate_ratios() is True
        assert strategy.get_tp_ratio(1) == Decimal('0.5')
        assert strategy.get_tp_ratio(2) == Decimal('0.3')
        assert strategy.get_tp_ratio(3) == Decimal('0.2')


class TestOrderStrategyValidation:
    """OrderStrategy 验证测试"""

    def test_tp_ratio_sum_exactly_one(self):
        """测试 tp_ratios 总和精确等于 1.0"""
        strategy = OrderStrategy(
            id="exact_one",
            name="精确 1.0",
            tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
        )
        assert sum(strategy.tp_ratios) == Decimal('1.0')

    def test_get_tp_ratio_out_of_range(self):
        """测试获取超出范围的 TP 比例返回 0"""
        strategy = OrderStrategy(
            id="single_tp",
            name="单 TP",
            tp_ratios=[Decimal('1.0')],
        )

        assert strategy.get_tp_ratio(0) == Decimal('0')  # 级别太小
        assert strategy.get_tp_ratio(2) == Decimal('0')  # 级别太大
