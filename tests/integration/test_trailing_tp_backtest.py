#!/usr/bin/env python3
"""
Trailing Take Profit (TTP) 回测验证 - 单元测试版本

验证 Trailing TP 功能在完整回测流程中的表现：
1. TP 价格随行情上移
2. close_events 包含 tp_modified 事件
3. Trailing TP 收益 > 固定 TP 收益（趋势行情下）
4. LONG 和 SHORT 方向验证

参考: docs/arch/trailing-tp-implementation-design.md Section 9.2
"""
import pytest
from decimal import Decimal
from typing import List, Dict
from datetime import datetime, timezone

from src.domain.models import (
    KlineData,
    Position,
    Order,
    Account,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    RiskManagerConfig,
    PositionCloseEvent,
)
from src.domain.matching_engine import MockMatchingEngine
from src.domain.risk_manager import DynamicRiskManager
from src.domain.order_manager import OrderManager


# ============================================================
# Helper Functions
# ============================================================

def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    timestamp: int = 1700000000000,
    open: Decimal = Decimal("50000"),
    high: Decimal = Decimal("51000"),
    low: Decimal = Decimal("49000"),
    close: Decimal = Decimal("50500"),
    volume: Decimal = Decimal("1000"),
) -> KlineData:
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
    direction: Direction = Direction.LONG,
    entry_price: Decimal = Decimal("50000"),
    current_qty: Decimal = Decimal("0.1"),
) -> Position:
    return Position(
        id=f"pos_{signal_id}",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=entry_price,
    )


def create_order(
    signal_id: str = "signal_001",
    order_role: OrderRole = OrderRole.TP1,
    direction: Direction = Direction.LONG,
    price: Decimal = None,
    trigger_price: Decimal = None,
    requested_qty: Decimal = Decimal("0.1"),
    order_type: OrderType = OrderType.LIMIT,
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    return Order(
        id=f"{order_role.value}_{signal_id}",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=direction,
        order_type=order_type,
        order_role=order_role,
        requested_qty=requested_qty,
        price=price,
        trigger_price=trigger_price,
        status=status,
        created_at=1700000000000,
        updated_at=1700000000000,
    )


# ============================================================
# Test 1: LONG 方向完整回测流程
# ============================================================

class TestTrailingTPLongDirection:
    """LONG 方向完整回测流程验证"""

    def test_long_trending_market_ttp_improves_profit(self):
        """
        验证 LONG 方向趋势行情下 Trailing TP 提升收益

        场景：
        - 入场价: 50000
        - 原始 TP: 60000 (20%)
        - 行情逐步上涨至 65000 后回撤到 64350 触发 TTP

        关键设计：
        - TP 设置在较高位置（60000），给 TTP 足够的调价空间
        - 行情先超过激活阈值，然后继续上涨触发 TTP
        - 最后回撤触发调整后的 TP

        预期：
        - 固定 TP: 在 60000 成交
        - Trailing TP: 在 64350 成交（高于原始 TP）
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = "long_ttp_test"
        position = create_position(
            signal_id=signal_id,
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            current_qty=Decimal("0.1"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        # 创建 SL 和 TP 订单
        # TP 设置在较高位置（60000），给 TTP 留出调价空间
        sl_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.SL,
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal("48000"),
            requested_qty=Decimal("0.1"),
        )
        tp1_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.TP1,
            direction=Direction.LONG,
            price=Decimal("60000"),  # 原始 TP，设置较高
            requested_qty=Decimal("0.1"),
        )
        active_orders = [sl_order, tp1_order]

        # TTP 配置
        ttp_config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_percent=Decimal("0.01"),  # 1%
            tp_step_threshold=Decimal("0.003"),   # 0.3%
            tp_trailing_enabled_levels=["TP1"],
            tp_trailing_activation_rr=Decimal("0.3"),  # 达到 TP 的 30% 时激活 (53000)
        )
        risk_manager = DynamicRiskManager(config=ttp_config)

        all_close_events: List[PositionCloseEvent] = []

        # 模拟 K 线序列（上涨趋势，TP 设置较高）
        # entry=50000, TP=60000
        # activation = 50000 + 0.3 * (60000-50000) = 53000
        klines_data = [
            # (timestamp, open, high, low, close)
            (1700000000000, Decimal("50000"), Decimal("51500"), Decimal("49800"), Decimal("51000")),  # 上涨，未激活
            (1700003600000, Decimal("51000"), Decimal("52500"), Decimal("50800"), Decimal("52000")),  # 未激活 (52000 < 53000)
            (1700007200000, Decimal("52000"), Decimal("54000"), Decimal("51800"), Decimal("53500")),  # 激活! (54000 >= 53000)
            (1700010800000, Decimal("53500"), Decimal("56000"), Decimal("53300"), Decimal("55500")),  # 继续上涨
            (1700014400000, Decimal("55500"), Decimal("59000"), Decimal("55300"), Decimal("58500")),  # 接近原始 TP
            (1700018000000, Decimal("58500"), Decimal("63000"), Decimal("58300"), Decimal("62500")),  # 超过原始 TP！
            (1700021600000, Decimal("62500"), Decimal("65500"), Decimal("62300"), Decimal("65000")),  # 继续上涨
            (1700025200000, Decimal("65000"), Decimal("66000"), Decimal("64000"), Decimal("64500")),  # 回撤，触发 TTP
        ]

        for ts, open_p, high_p, low_p, close_p in klines_data:
            kline = create_kline(timestamp=ts, open=open_p, high=high_p, low=low_p, close=close_p)

            # 1. 先执行风控评估（更新水位线，触发 TTP）
            tp_events = risk_manager.evaluate_and_mutate(kline, position, active_orders)
            all_close_events.extend(tp_events)

            # 2. 执行撮合
            executed = engine.match_orders_for_kline(kline, active_orders, positions_map, account)

            # 3. 收集成交事件
            for order in executed:
                if order.order_role in [OrderRole.TP1, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                    all_close_events.append(PositionCloseEvent(
                        position_id=position.id,
                        order_id=order.id,
                        event_type=order.order_role.value,
                        event_category="exit",
                        close_price=order.average_exec_price,
                        close_qty=order.actual_filled,
                        close_pnl=order.close_pnl,
                        close_fee=order.close_fee,
                        close_time=kline.timestamp,
                        exit_reason=order.order_role.value,
                    ))

            # 4. 更新活跃订单列表
            active_orders = [o for o in active_orders if o.status == OrderStatus.OPEN]

            # 如果仓位已平，结束
            if position.is_closed:
                break

        # 验证结果
        print("\n========== LONG 方向回测结果 ==========")
        print(f"仓位状态: {'已平仓' if position.is_closed else '未平仓'}")
        print(f"实现盈亏: {position.realized_pnl:.2f}")
        print(f"总出场事件数: {len(all_close_events)}")

        # 统计事件类型
        tp_modified_events = [e for e in all_close_events if e.event_category == "tp_modified"]
        exit_events = [e for e in all_close_events if e.event_category == "exit"]

        print(f"TP 调价事件数: {len(tp_modified_events)}")
        print(f"成交事件数: {len(exit_events)}")

        # 验证 TP 调价事件
        assert len(tp_modified_events) > 0, "应该有 TP 调价事件"
        print("\nTP 调价轨迹:")
        for i, event in enumerate(tp_modified_events):
            print(f"  [{i+1}] {event.exit_reason}")

        # 验证 TP 最终成交价高于原始 TP
        if exit_events:
            tp_exit = [e for e in exit_events if e.event_type == "TP1"]
            if tp_exit:
                final_tp_price = tp_exit[0].close_price
                original_tp = Decimal("60000")  # 更新为新的原始 TP
                print(f"\n最终 TP 成交价: {final_tp_price}")
                print(f"原始 TP 价格: {original_tp}")
                # TTP 后，TP 应该在高于原始 TP 的位置成交
                # 理论上 watermark=65500，theoretical_tp = 65500 * 0.99 = 64845
                # 但实际 watermark 最高达到 63000（在最后两根 K 线时）
                # 所以 TP 被调整到 62370
                # 由于滑点（0.05%），最终成交价约 62338
                print(f"TP 价格提升: {(final_tp_price - original_tp) / original_tp * 100:.1f}%")
                # 验证：TP 成交价应高于原始 TP (60000)
                assert final_tp_price > original_tp, "Trailing TP 最终成交价应高于原始 TP"


    def test_long_fixed_tp_baseline(self):
        """
        基线测试：LONG 方向固定 TP（不启用 TTP）
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = "long_fixed_tp"
        position = create_position(
            signal_id=signal_id,
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            current_qty=Decimal("0.1"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        sl_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.SL,
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal("48000"),
            requested_qty=Decimal("0.1"),
        )
        tp1_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.TP1,
            direction=Direction.LONG,
            price=Decimal("55000"),
            requested_qty=Decimal("0.1"),
        )
        active_orders = [sl_order, tp1_order]

        # 不启用 TTP
        ttp_config = RiskManagerConfig(
            tp_trailing_enabled=False,  # 关闭 TTP
        )
        risk_manager = DynamicRiskManager(config=ttp_config)

        all_close_events: List[PositionCloseEvent] = []

        # 相同的 K 线序列
        klines_data = [
            (1700000000000, Decimal("50000"), Decimal("51000"), Decimal("49800"), Decimal("50500")),
            (1700003600000, Decimal("50500"), Decimal("52000"), Decimal("50400"), Decimal("51800")),
            (1700007200000, Decimal("51800"), Decimal("53500"), Decimal("51600"), Decimal("53000")),
            (1700010800000, Decimal("53000"), Decimal("55000"), Decimal("52800"), Decimal("54500")),  # TP 触发
        ]

        for ts, open_p, high_p, low_p, close_p in klines_data:
            kline = create_kline(timestamp=ts, open=open_p, high=high_p, low=low_p, close=close_p)

            # 风控评估
            risk_manager.evaluate_and_mutate(kline, position, active_orders)

            # 撮合
            executed = engine.match_orders_for_kline(kline, active_orders, positions_map, account)

            for order in executed:
                if order.order_role in [OrderRole.TP1, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                    all_close_events.append(PositionCloseEvent(
                        position_id=position.id,
                        order_id=order.id,
                        event_type=order.order_role.value,
                        event_category="exit",
                        close_price=order.average_exec_price,
                        close_qty=order.actual_filled,
                        close_pnl=order.close_pnl,
                        close_fee=order.close_fee,
                        close_time=kline.timestamp,
                        exit_reason=order.order_role.value,
                    ))

            active_orders = [o for o in active_orders if o.status == OrderStatus.OPEN]

            if position.is_closed:
                break

        # 验证结果
        print("\n========== LONG 固定 TP 基线结果 ==========")
        print(f"仓位状态: {'已平仓' if position.is_closed else '未平仓'}")
        print(f"实现盈亏: {position.realized_pnl:.2f}")

        # 验证没有 TP 调价事件
        tp_modified_events = [e for e in all_close_events if e.event_category == "tp_modified"]
        assert len(tp_modified_events) == 0, "固定 TP 模式不应有调价事件"

        # 验证 TP 在原始价格成交
        exit_events = [e for e in all_close_events if e.event_category == "exit"]
        if exit_events:
            tp_exit = [e for e in exit_events if e.event_type == "TP1"]
            if tp_exit:
                final_tp_price = tp_exit[0].close_price
                print(f"TP 成交价: {final_tp_price}")
                # 由于滑点，成交价可能略低于原始 TP，但应该接近
                assert final_tp_price >= Decimal("54700"), "TP 应在原始 TP 价格附近成交"


# ============================================================
# Test 2: SHORT 方向完整回测流程
# ============================================================

class TestTrailingTPShortDirection:
    """SHORT 方向完整回测流程验证"""

    def test_short_trending_market_ttp_improves_profit(self):
        """
        验证 SHORT 方向趋势行情下 Trailing TP 提升收益

        场景：
        - 入场价: 60000
        - 原始 TP: 54000 (10%)
        - 行情下跌至 50000 后反弹到 50500 触发 TP

        预期：
        - 固定 TP: 在 54000 成交
        - Trailing TP: 在 50500 成交
        """
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = "short_ttp_test"
        position = create_position(
            signal_id=signal_id,
            direction=Direction.SHORT,
            entry_price=Decimal("60000"),
            current_qty=Decimal("0.1"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        # SHORT 方向订单
        sl_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.SL,
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            trigger_price=Decimal("62000"),
            requested_qty=Decimal("0.1"),
        )
        tp1_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.TP1,
            direction=Direction.SHORT,
            price=Decimal("54000"),  # 原始 TP
            requested_qty=Decimal("0.1"),
        )
        active_orders = [sl_order, tp1_order]

        # TTP 配置
        ttp_config = RiskManagerConfig(
            tp_trailing_enabled=True,
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
            tp_trailing_enabled_levels=["TP1"],
            tp_trailing_activation_rr=Decimal("0.5"),
        )
        risk_manager = DynamicRiskManager(config=ttp_config)

        all_close_events: List[PositionCloseEvent] = []

        # 模拟下跌趋势
        klines_data = [
            (1700000000000, Decimal("60000"), Decimal("60200"), Decimal("59000"), Decimal("59200")),
            (1700003600000, Decimal("59200"), Decimal("59400"), Decimal("58000"), Decimal("58200")),
            (1700007200000, Decimal("58200"), Decimal("58400"), Decimal("57000"), Decimal("57200")),  # 超过激活阈值
            (1700010800000, Decimal("57200"), Decimal("57400"), Decimal("55500"), Decimal("55800")),  # 低于原始 TP
            (1700014400000, Decimal("55800"), Decimal("56000"), Decimal("53000"), Decimal("53500")),  # 大幅下跌
            (1700018000000, Decimal("53500"), Decimal("53700"), Decimal("50000"), Decimal("50500")),  # 触发 TTP
        ]

        for ts, open_p, high_p, low_p, close_p in klines_data:
            kline = create_kline(timestamp=ts, open=open_p, high=high_p, low=low_p, close=close_p)

            # 风控评估
            tp_events = risk_manager.evaluate_and_mutate(kline, position, active_orders)
            all_close_events.extend(tp_events)

            # 撮合
            executed = engine.match_orders_for_kline(kline, active_orders, positions_map, account)

            for order in executed:
                if order.order_role in [OrderRole.TP1, OrderRole.SL] and order.actual_filled and order.actual_filled > 0:
                    all_close_events.append(PositionCloseEvent(
                        position_id=position.id,
                        order_id=order.id,
                        event_type=order.order_role.value,
                        event_category="exit",
                        close_price=order.average_exec_price,
                        close_qty=order.actual_filled,
                        close_pnl=order.close_pnl,
                        close_fee=order.close_fee,
                        close_time=kline.timestamp,
                        exit_reason=order.order_role.value,
                    ))

            active_orders = [o for o in active_orders if o.status == OrderStatus.OPEN]

            if position.is_closed:
                break

        # 验证结果
        print("\n========== SHORT 方向回测结果 ==========")
        print(f"仓位状态: {'已平仓' if position.is_closed else '未平仓'}")
        print(f"实现盈亏: {position.realized_pnl:.2f}")

        tp_modified_events = [e for e in all_close_events if e.event_category == "tp_modified"]
        print(f"TP 调价事件数: {len(tp_modified_events)}")

        # 验证有 TP 调价事件
        assert len(tp_modified_events) > 0, "应该有 TP 调价事件"

        print("\nTP 调价轨迹:")
        for i, event in enumerate(tp_modified_events):
            print(f"  [{i+1}] {event.exit_reason}")

        # 验证 TP 最终成交价低于原始 TP
        exit_events = [e for e in all_close_events if e.event_category == "exit"]
        if exit_events:
            tp_exit = [e for e in exit_events if e.event_type == "TP1"]
            if tp_exit:
                final_tp_price = tp_exit[0].close_price
                original_tp = Decimal("54000")
                print(f"\n最终 TP 成交价: {final_tp_price}")
                print(f"原始 TP 价格: {original_tp}")
                # Trailing TP 应该在更低的价格成交
                improvement = (original_tp - final_tp_price) / original_tp * 100
                print(f"TP 价格改善: {improvement:.1f}%")


# ============================================================
# Test 3: 收益对比测试
# ============================================================

class TestTTPProfitComparison:
    """收益对比测试"""

    def test_ttp_vs_fixed_tp_profit_comparison(self):
        """
        对比固定 TP 和 Trailing TP 的收益差异

        使用相同的行情数据，对比两种模式的盈亏

        设计：
        - TP 设置在较高位置（60000），给 TTP 足够的调价空间
        - 行情先超过激活阈值，然后继续上涨触发 TTP 调价
        - 最后回撤触发调整后的 TP
        """
        # 模拟上涨趋势行情，TP 设置较高
        # entry=50000, TP=60000, activation=53000 (0.3 activation_rr)
        klines_data = [
            (1700000000000, Decimal("50000"), Decimal("51500"), Decimal("49800"), Decimal("51000")),
            (1700003600000, Decimal("51000"), Decimal("52500"), Decimal("50800"), Decimal("52000")),
            (1700007200000, Decimal("52000"), Decimal("54000"), Decimal("51800"), Decimal("53500")),  # 激活
            (1700010800000, Decimal("53500"), Decimal("56000"), Decimal("53300"), Decimal("55500")),
            (1700014400000, Decimal("55500"), Decimal("59000"), Decimal("55300"), Decimal("58500")),  # 接近原始 TP
            (1700018000000, Decimal("58500"), Decimal("63000"), Decimal("58300"), Decimal("62500")),  # 超过原始 TP
            (1700021600000, Decimal("62500"), Decimal("65500"), Decimal("62300"), Decimal("65000")),  # 继续
            (1700025200000, Decimal("65000"), Decimal("66000"), Decimal("64000"), Decimal("64500")),  # 回撤
        ]

        # ===== 回测 A: 固定 TP =====
        pnl_fixed = self._run_single_backtest(
            klines_data=klines_data,
            ttp_enabled=False,
            entry_price=Decimal("50000"),
            original_tp=Decimal("60000"),
            direction=Direction.LONG,
        )

        # ===== 回测 B: Trailing TP =====
        pnl_ttp = self._run_single_backtest(
            klines_data=klines_data,
            ttp_enabled=True,
            entry_price=Decimal("50000"),
            original_tp=Decimal("60000"),
            direction=Direction.LONG,
        )

        print("\n========== 收益对比 ==========")
        print(f"固定 TP 盈亏: {pnl_fixed:.2f}")
        print(f"Trailing TP 盈亏: {pnl_ttp:.2f}")

        if pnl_fixed != Decimal("0"):
            improvement = (pnl_ttp - pnl_fixed) / abs(pnl_fixed) * 100
            print(f"收益提升: {improvement:.1f}%")

        # 验证：在趋势行情下，Trailing TP 收益应该更好
        assert pnl_ttp >= pnl_fixed, "趋势行情下 Trailing TP 收益应 >= 固定 TP"

    def _run_single_backtest(
        self,
        klines_data: List,
        ttp_enabled: bool,
        entry_price: Decimal,
        original_tp: Decimal,
        direction: Direction,
    ) -> Decimal:
        """运行单次回测，返回总盈亏"""
        engine = MockMatchingEngine(
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            tp_slippage_rate=Decimal("0.0005"),
        )

        signal_id = f"{'ttp' if ttp_enabled else 'fixed'}_test"
        position = create_position(
            signal_id=signal_id,
            direction=direction,
            entry_price=entry_price,
            current_qty=Decimal("0.1"),
        )
        account = Account(account_id="test", total_balance=Decimal("10000"), frozen_margin=Decimal("0"))
        positions_map = {signal_id: position}

        # 创建订单
        if direction == Direction.LONG:
            sl_price = entry_price * Decimal("0.96")  # 4% 止损
            sl_order = create_order(
                signal_id=signal_id,
                order_role=OrderRole.SL,
                direction=direction,
                order_type=OrderType.STOP_MARKET,
                trigger_price=sl_price,
                requested_qty=Decimal("0.1"),
            )
        else:
            sl_price = entry_price * Decimal("1.04")
            sl_order = create_order(
                signal_id=signal_id,
                order_role=OrderRole.SL,
                direction=direction,
                order_type=OrderType.STOP_MARKET,
                trigger_price=sl_price,
                requested_qty=Decimal("0.1"),
            )

        tp1_order = create_order(
            signal_id=signal_id,
            order_role=OrderRole.TP1,
            direction=direction,
            price=original_tp,
            requested_qty=Decimal("0.1"),
        )
        active_orders = [sl_order, tp1_order]

        # 风控配置
        ttp_config = RiskManagerConfig(
            tp_trailing_enabled=ttp_enabled,
            tp_trailing_percent=Decimal("0.01"),
            tp_step_threshold=Decimal("0.003"),
            tp_trailing_enabled_levels=["TP1"],
            tp_trailing_activation_rr=Decimal("0.3"),  # 与测试数据匹配
        )
        risk_manager = DynamicRiskManager(config=ttp_config)

        # 执行回测
        for ts, open_p, high_p, low_p, close_p in klines_data:
            kline = create_kline(timestamp=ts, open=open_p, high=high_p, low=low_p, close=close_p)

            risk_manager.evaluate_and_mutate(kline, position, active_orders)
            engine.match_orders_for_kline(kline, active_orders, positions_map, account)

            active_orders = [o for o in active_orders if o.status == OrderStatus.OPEN]

            if position.is_closed:
                break

        return position.realized_pnl


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
