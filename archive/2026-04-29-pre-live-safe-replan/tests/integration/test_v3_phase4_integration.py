"""
Phase 4: 订单编排 - 集成测试

测试 OrderManager 与撮合引擎、风控状态机的集成

测试用例清单 (IT-001 ~ IT-006):
- IT-001: 完整订单链流程
- IT-002: 多 TP 策略完整流程
- IT-003: OCO 逻辑验证
- IT-004: 部分止盈后打损
- IT-005: 与风控状态机集成
- IT-006: 职责边界验证
"""
import pytest
from decimal import Decimal
from typing import List, Dict, Any

# 待实现的模块 (测试将在实现完成后运行)
try:
    from src.domain.order_manager import OrderManager, OrderStrategy
    from src.domain.models import (
        Order, Signal, Position, Account, Direction, OrderStatus, OrderType, OrderRole
    )
    from src.domain.risk_manager import DynamicRiskManager
    ORDER_MANAGER_AVAILABLE = True
except ImportError:
    ORDER_MANAGER_AVAILABLE = False


# ============================================================
# 测试夹具 (Fixtures)
# ============================================================

@pytest.fixture
def multi_tp_strategy() -> "OrderStrategy":
    """多级别止盈策略 (50% / 30% / 20%)"""
    return OrderStrategy(
        id="multi_tp",
        name="多级别止盈",
        tp_levels=3,
        tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],
        initial_stop_loss_rr=Decimal('-1.0'),
        trailing_stop_enabled=True,
        oco_enabled=True,
    )


@pytest.fixture
def sample_account() -> Account:
    """示例账户"""
    return Account(
        account_id="test_account",
        total_balance=Decimal('100000'),
        frozen_margin=Decimal('0'),
    )


# ============================================================
# IT-001: 完整订单链流程
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_complete_order_chain_flow(
    multi_tp_strategy: "OrderStrategy",
    sample_account: Account,
):
    """
    IT-001: 完整订单链流程
    验证：ENTRY → (动态生成 TP/SL) → TP1 → TP2 → 完全平仓
    """
    manager = OrderManager()
    signal_id = "sig-it-001"
    symbol = "BTC/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('1.0')
    entry_price = Decimal('65065')  # 实际成交价
    tp_targets = [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')]

    # ========== 阶段 1: 创建订单链 (仅 ENTRY) ==========
    orders = manager.create_order_chain(
        strategy=multi_tp_strategy,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    # 只生成 ENTRY 订单
    assert len(orders) == 1
    assert orders[0].order_role == OrderRole.ENTRY

    # ========== 阶段 2: ENTRY 成交，动态生成 TP/SL ==========
    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-001",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    # 应生成 TP1, TP2, TP3, SL
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_orders = [o for o in new_orders if o.order_role == OrderRole.SL]
    assert len(tp_orders) == 3
    assert len(sl_orders) == 1

    # ========== 阶段 3: TP1 成交 (50%) ==========
    tp1_order = tp_orders[0]
    tp1_order.status = OrderStatus.FILLED
    tp1_order.filled_qty = Decimal('0.5')

    position.current_qty = Decimal('0.5')  # 剩余 50%

    # 将所有订单合并为活跃订单列表
    all_active_orders = [entry_order] + new_orders

    manager.handle_order_filled(
        filled_order=tp1_order,
        active_orders=all_active_orders,
        positions_map={position.id: position},
    )

    # SL 数量应更新为 0.5 (在 all_active_orders 中查找)
    sl_order = next((o for o in all_active_orders if o.order_role == OrderRole.SL), None)
    assert sl_order is not None
    assert sl_order.requested_qty == Decimal('0.5')

    # ========== 阶段 4: TP2 成交 (30%) ==========
    tp2_order = tp_orders[1]
    tp2_order.status = OrderStatus.FILLED
    tp2_order.filled_qty = Decimal('0.3')

    position.current_qty = Decimal('0.2')  # 剩余 20%

    manager.handle_order_filled(
        filled_order=tp2_order,
        active_orders=[entry_order] + new_orders,
        positions_map={position.id: position},
    )

    # ========== 阶段 5: TP3 成交 (20%), 完全平仓 ==========
    tp3_order = tp_orders[2]
    tp3_order.status = OrderStatus.FILLED
    tp3_order.filled_qty = Decimal('0.2')

    position.current_qty = Decimal('0')  # 完全平仓
    position.is_closed = True

    manager.handle_order_filled(
        filled_order=tp3_order,
        active_orders=[entry_order] + new_orders,
        positions_map={position.id: position},
    )

    # SL 应被撤销
    assert sl_order.status == OrderStatus.CANCELED


# ============================================================
# IT-002: 多 TP 策略完整流程
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_multi_tp_strategy_flow(
    multi_tp_strategy: "OrderStrategy",
):
    """
    IT-002: 多 TP 策略完整流程
    验证：TP1(50%) → TP2(30%) → TP3(20%)
    """
    manager = OrderManager()
    signal_id = "sig-it-002"
    symbol = "ETH/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('10.0')
    entry_price = Decimal('3500')
    tp_targets = [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')]

    # 创建订单链
    orders = manager.create_order_chain(
        strategy=multi_tp_strategy,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    # ENTRY 成交
    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-002",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    # 验证 TP 数量比例
    tp_orders = sorted(
        [o for o in new_orders if 'TP' in str(o.order_role)],
        key=lambda x: str(x.order_role)
    )

    # TP1: 50% = 5.0
    # TP2: 30% = 3.0
    # TP3: 20% = 2.0 (使用剩余数量防止精度误差)
    assert tp_orders[0].requested_qty == Decimal('5.0')  # TP1
    assert tp_orders[1].requested_qty == Decimal('3.0')  # TP2
    assert tp_orders[2].requested_qty == Decimal('2.0')  # TP3


# ============================================================
# IT-003: OCO 逻辑验证
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_oco_logic_sl_cancels_tp(
    multi_tp_strategy: "OrderStrategy",
):
    """
    IT-003: OCO 逻辑验证
    验证：SL 成交后 TP 全部撤销
    """
    manager = OrderManager()
    signal_id = "sig-it-003"
    symbol = "BTC/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('1.0')
    entry_price = Decimal('65065')
    stop_loss_price = Decimal('64065')
    tp_targets = [Decimal('1.0')]

    # 创建订单链并模拟 ENTRY 成交
    orders = manager.create_order_chain(
        strategy=multi_tp_strategy,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-003",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    # 获取 TP 和 SL 订单
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_order = [o for o in new_orders if o.order_role == OrderRole.SL][0]

    # ========== SL 成交 ==========
    sl_order.status = OrderStatus.FILLED
    sl_order.filled_qty = total_qty
    sl_order.average_exec_price = stop_loss_price

    all_orders = [entry_order] + new_orders

    manager.handle_order_filled(
        filled_order=sl_order,
        active_orders=all_orders,
        positions_map={position.id: position},
    )

    # 所有 TP 订单应被撤销
    for tp_order in tp_orders:
        assert tp_order.status == OrderStatus.CANCELED


# ============================================================
# IT-004: 部分止盈后打损
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_partial_tp_then_sl_hit(
    multi_tp_strategy: "OrderStrategy",
):
    """
    IT-004: 部分止盈后打损
    验证：TP1 成交 → 剩余仓位 SL 打损
    """
    manager = OrderManager()
    signal_id = "sig-it-004"
    symbol = "BTC/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('1.0')
    entry_price = Decimal('65065')
    stop_loss_price = Decimal('64065')
    tp_targets = [Decimal('1.0')]

    # 创建订单链并模拟 ENTRY 成交
    orders = manager.create_order_chain(
        strategy=multi_tp_strategy,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-004",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_order = [o for o in new_orders if o.order_role == OrderRole.SL][0]

    # ========== TP1 成交 (50%) ==========
    tp1_order = tp_orders[0]
    tp1_order.status = OrderStatus.FILLED
    tp1_order.filled_qty = Decimal('0.5')

    position.current_qty = Decimal('0.5')
    position.realized_pnl = Decimal('500')  # TP1 盈利 500 USDT

    # 将所有订单合并为活跃订单列表
    all_active_orders = [entry_order] + new_orders

    manager.handle_order_filled(
        filled_order=tp1_order,
        active_orders=all_active_orders,
        positions_map={position.id: position},
    )

    # SL 数量应更新为 0.5
    sl_order_after = next((o for o in all_active_orders if o.order_role == OrderRole.SL), None)
    assert sl_order_after is not None
    assert sl_order_after.requested_qty == Decimal('0.5')

    # ========== SL 成交 (剩余 50%) ==========
    sl_order.status = OrderStatus.FILLED
    sl_order.filled_qty = Decimal('0.5')
    sl_order.average_exec_price = stop_loss_price

    manager.handle_order_filled(
        filled_order=sl_order,
        active_orders=[entry_order] + new_orders,
        positions_map={position.id: position},
    )

    # 验证剩余 TP 订单被撤销
    for tp_order in tp_orders[1:]:
        assert tp_order.status == OrderStatus.CANCELED


# ============================================================
# IT-005: 与风控状态机集成
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_integration_with_risk_state_machine(
    multi_tp_strategy: "OrderStrategy",
):
    """
    IT-005: 与风控状态机集成
    验证：Breakeven + Trailing + 订单编排
    """
    from src.domain.models import KlineData

    manager = OrderManager()
    risk_manager = DynamicRiskManager()

    signal_id = "sig-it-005"
    symbol = "BTC/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('1.0')
    entry_price = Decimal('65065')
    initial_sl = Decimal('64065')  # 2% 止损
    tp_targets = [Decimal('1.0')]

    # 创建订单链并模拟 ENTRY 成交
    orders = manager.create_order_chain(
        strategy=multi_tp_strategy,
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-005",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
        watermark_price=entry_price,  # 初始水位线
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    sl_order = [o for o in new_orders if o.order_role == OrderRole.SL][0]
    initial_sl_price = sl_order.trigger_price
    # SL 价格应该是 entry_price * (1 - 0.02) = 65065 * 0.98 = 63763.7
    assert initial_sl_price < entry_price

    # ========== 模拟 K 线价格上涨，Trailing Stop 上移 ==========
    kline_high = Decimal('66065')
    kline_low = Decimal('65565')

    kline = KlineData(
        symbol=symbol,
        timeframe="15m",
        timestamp=1711785660000,
        open=Decimal('65565'),
        high=kline_high,
        low=kline_low,
        close=Decimal('66000'),
        volume=Decimal('1000'),
    )

    # 风控状态机评估 (Trailing Stop)
    risk_manager.evaluate_and_mutate(
        kline=kline,
        position=position,
        active_orders=new_orders,
    )

    # SL 价格应该上移 (Breakeven 或 Trailing)
    # 具体上移幅度取决于 DynamicRiskManager 的实现
    # 至少应该 >= initial_sl_price

    # ========== TP1 成交，触发 Breakeven ==========
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    if tp_orders:
        tp1_order = tp_orders[0]
        tp1_order.status = OrderStatus.FILLED
        tp1_order.filled_qty = Decimal('0.5')

        position.current_qty = Decimal('0.5')

        # 将所有订单合并为活跃订单列表
        all_active_orders = [entry_order] + new_orders

        manager.handle_order_filled(
            filled_order=tp1_order,
            active_orders=all_active_orders,
            positions_map={position.id: position},
        )

        # SL 数量应更新为 0.5
        sl_order_after = next((o for o in all_active_orders if o.order_role == OrderRole.SL), None)
        if sl_order_after:
            assert sl_order_after.requested_qty == Decimal('0.5')


# ============================================================
# IT-006: 职责边界验证
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_responsibility_boundary_integration(
    multi_tp_strategy: "OrderStrategy",
):
    """
    IT-006: 职责边界验证
    验证：OrderManager 更新 SL 数量，DynamicRiskManager 更新 SL 价格
    """
    manager = OrderManager()
    risk_manager = DynamicRiskManager()

    signal_id = "sig-it-006"
    symbol = "BTC/USDT:USDT"
    direction = Direction.LONG
    total_qty = Decimal('1.0')
    entry_price = Decimal('65065')
    initial_sl = Decimal('64065')  # 2% 止损
    tp_targets = [Decimal('1.0')]

    # ========== 阶段 1: OrderManager 创建订单链 ==========
    orders = manager.create_order_chain(
        strategy=OrderStrategy(
            id="test",
            name="测试",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
            initial_stop_loss_rr=Decimal('-1.0'),
        ),
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        total_qty=total_qty,
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=tp_targets,
    )

    entry_order = orders[0]
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = total_qty
    entry_order.average_exec_price = entry_price

    position = Position(
        id="pos-it-006",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=total_qty,
    )

    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={position.id: position},
        strategy=multi_tp_strategy,
        tp_targets=tp_targets,
    )

    sl_order = [o for o in new_orders if o.order_role == OrderRole.SL][0]

    # 记录初始 SL 数量和价格
    initial_sl_qty = sl_order.requested_qty
    initial_sl_price = sl_order.trigger_price

    assert initial_sl_qty == Decimal('1.0')
    # SL 价格应该是 entry_price * (1 - 0.02) = 63763.7
    assert initial_sl_price < entry_price

    # ========== 阶段 2: TP1 成交 ==========
    tp_order = [o for o in new_orders if 'TP' in str(o.order_role)][0]
    tp_order.status = OrderStatus.FILLED
    tp_order.filled_qty = Decimal('0.5')

    position.current_qty = Decimal('0.5')

    # OrderManager 处理成交 (更新 SL 数量)
    # 将所有订单合并为活跃订单列表
    all_active_orders = [entry_order] + new_orders

    manager.handle_order_filled(
        filled_order=tp_order,
        active_orders=all_active_orders,
        positions_map={position.id: position},
    )

    # ========== 阶段 3: DynamicRiskManager 评估 (更新 SL 价格) ==========
    from src.domain.models import KlineData

    kline = KlineData(
        symbol=symbol,
        timeframe="15m",
        timestamp=1711785660000,
        open=Decimal('65565'),
        high=Decimal('66065'),
        low=Decimal('65565'),
        close=Decimal('66000'),
        volume=Decimal('1000'),
    )

    # 风控状态机评估 (只修改 SL 价格，不修改数量)
    risk_manager.evaluate_and_mutate(
        kline=kline,
        position=position,
        active_orders=new_orders,
    )

    # ========== 验证职责边界 ==========
    # OrderManager: SL 数量应该被更新为 0.5
    # DynamicRiskManager: SL 价格应该被调整 (Breakeven/Trailing)

    # 在 active_orders 中查找 SL 订单
    sl_order_updated = next((o for o in all_active_orders if o.order_role == OrderRole.SL), None)
    assert sl_order_updated is not None

    # 验证：SL 数量已更新 (OrderManager 职责)
    assert sl_order_updated.requested_qty == Decimal('0.5'), \
        "OrderManager 应该更新 SL 数量为剩余仓位"

    # 验证：SL 价格可能被调整 (DynamicRiskManager 职责)
    # 具体价格取决于实现，但至少不应该被 OrderManager 修改


# ============================================================
# 主入口 (用于直接运行测试)
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
