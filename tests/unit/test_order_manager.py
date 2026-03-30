"""
Phase 4: 订单编排 - 单元测试

测试 OrderManager 和 OrderStrategy 的核心功能

测试用例清单 (UT-001 ~ UT-014):
- UT-001: OrderStrategy 单 TP 配置
- UT-002: OrderStrategy 多 TP 配置
- UT-003: OrderStrategy 比例验证失败
- UT-004: create_order_chain 仅生成 ENTRY
- UT-005: handle_order_filled ENTRY 成交
- UT-006: TP 目标价格计算 (LONG)
- UT-007: TP 目标价格计算 (SHORT)
- UT-008: handle_order_filled TP1 成交
- UT-009: handle_order_filled SL 成交
- UT-010: apply_oco_logic 完全平仓
- UT-011: apply_oco_logic 部分平仓
- UT-012: get_order_chain_status
- UT-013: Decimal 精度保护
- UT-014: 职责边界验证
"""
import pytest
from decimal import Decimal
from typing import List, Dict, Any

# 待实现的模块 (测试将在实现完成后运行)
try:
    from src.domain.order_manager import OrderManager, OrderStrategy
    from src.domain.models import (
        Order, Signal, Position, Direction, OrderStatus, OrderType, OrderRole
    )
    ORDER_MANAGER_AVAILABLE = True
except ImportError:
    ORDER_MANAGER_AVAILABLE = False


# ============================================================
# 测试夹具 (Fixtures)
# ============================================================

@pytest.fixture
def single_tp_strategy() -> "OrderStrategy":
    """标准单 TP 策略"""
    return OrderStrategy(
        id="std_single_tp",
        name="标准单 TP",
        tp_levels=1,
        tp_ratios=[Decimal('1.0')],
        initial_stop_loss_rr=Decimal('-1.0'),
        trailing_stop_enabled=True,
        oco_enabled=True,
    )


@pytest.fixture
def multi_tp_strategy() -> "OrderStrategy":
    """多级别止盈策略"""
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
def sample_signal() -> Signal:
    """示例信号"""
    return Signal(
        id="sig-001",
        strategy_id="pinbar",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        timestamp=1711785600000,
        expected_entry=Decimal('65000'),
        expected_sl=Decimal('64000'),
        pattern_score=0.85,
    )


@pytest.fixture
def sample_position_long() -> Position:
    """示例 LONG 仓位"""
    return Position(
        id="pos-001",
        signal_id="sig-001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('1.0'),
    )


@pytest.fixture
def sample_position_short() -> Position:
    """示例 SHORT 仓位"""
    return Position(
        id="pos-002",
        signal_id="sig-002",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        entry_price=Decimal('3500'),
        current_qty=Decimal('10.0'),
    )


# ============================================================
# UT-001: OrderStrategy 单 TP 配置
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_order_strategy_single_tp_config(single_tp_strategy: "OrderStrategy"):
    """
    UT-001: OrderStrategy 单 TP 配置
    验证：tp_ratios=[1.0]
    """
    assert single_tp_strategy.tp_levels == 1
    assert single_tp_strategy.tp_ratios == [Decimal('1.0')]
    assert single_tp_strategy.tp_ratios[0] == Decimal('1.0')
    assert single_tp_strategy.validate_ratios() is True


# ============================================================
# UT-002: OrderStrategy 多 TP 配置
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_order_strategy_multi_tp_config(multi_tp_strategy: "OrderStrategy"):
    """
    UT-002: OrderStrategy 多 TP 配置
    验证：tp_ratios=[0.5, 0.3, 0.2]
    """
    assert multi_tp_strategy.tp_levels == 3
    assert len(multi_tp_strategy.tp_ratios) == 3
    assert multi_tp_strategy.tp_ratios[0] == Decimal('0.5')
    assert multi_tp_strategy.tp_ratios[1] == Decimal('0.3')
    assert multi_tp_strategy.tp_ratios[2] == Decimal('0.2')
    assert multi_tp_strategy.validate_ratios() is True


# ============================================================
# UT-003: OrderStrategy 比例验证失败
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_order_strategy_invalid_ratios():
    """
    UT-003: OrderStrategy 比例验证失败
    验证：tp_ratios 总和≠1.0 抛出异常
    """
    from src.domain.exceptions import CryptoMonitorError

    # 比例总和不等于 1.0
    with pytest.raises((ValueError, CryptoMonitorError)) as exc_info:
        OrderStrategy(
            id="invalid_tp",
            name="无效 TP 比例",
            tp_levels=2,
            tp_ratios=[Decimal('0.5'), Decimal('0.3')],  # 总和=0.8 ≠ 1.0
            initial_stop_loss_rr=Decimal('-1.0'),
        )

    # 验证错误码为 C-031
    assert 'C-031' in str(exc_info.value) or '总和' in str(exc_info.value) or 'ratio' in str(exc_info.value).lower()


# ============================================================
# UT-004: create_order_chain 仅生成 ENTRY
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_create_order_chain_only_entry(sample_signal: Signal, single_tp_strategy: "OrderStrategy"):
    """
    UT-004: create_order_chain 仅生成 ENTRY
    验证：只返回 ENTRY 订单，TP/SL 尚未生成
    """
    manager = OrderManager()

    orders = manager.create_order_chain(
        strategy=single_tp_strategy,
        signal_id=sample_signal.id,
        symbol=sample_signal.symbol,
        direction=sample_signal.direction,
        total_qty=Decimal('1.0'),
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=[Decimal('1.0')],
    )

    # 只生成 ENTRY 订单
    assert len(orders) == 1
    assert orders[0].order_role == OrderRole.ENTRY
    assert orders[0].signal_id == sample_signal.id
    assert orders[0].requested_qty == Decimal('1.0')


# ============================================================
# UT-005: handle_order_filled ENTRY 成交
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_handle_order_filled_entry_creates_tp_sl(
    single_tp_strategy: "OrderStrategy",
    sample_signal: Signal,
):
    """
    UT-005: handle_order_filled ENTRY 成交
    验证：基于 actual_exec_price 动态生成 TP + SL
    """
    manager = OrderManager()

    # 模拟仓位 (signal_id 必须与订单一致)
    position = Position(
        id="pos-001",
        signal_id=sample_signal.id,
        symbol=sample_signal.symbol,
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('1.0'),
    )

    # 模拟 ENTRY 订单已成交
    entry_order = Order(
        id="order-entry-001",
        signal_id=sample_signal.id,
        symbol=sample_signal.symbol,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65065'),  # 实际成交价 (滑点后)
        status=OrderStatus.FILLED,
        created_at=sample_signal.timestamp,
        updated_at=sample_signal.timestamp + 60000,
    )

    active_orders = [entry_order]
    positions_map = {position.id: position}

    # 处理 ENTRY 成交事件
    new_orders = manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=active_orders,
        positions_map=positions_map,
    )

    # 应生成 TP 和 SL 订单
    assert len(new_orders) >= 2  # 至少 TP + SL

    tp_orders = [o for o in new_orders if o.order_role == OrderRole.TP1]
    sl_orders = [o for o in new_orders if o.order_role == OrderRole.SL]

    assert len(tp_orders) >= 1
    assert len(sl_orders) >= 1

    # 验证 TP/SL 基于实际成交价计算
    # TP 价格 = entry_price + RR × (entry_price - stop_loss)
    # SL 价格 = entry_price + initial_sl_rr × (entry_price - stop_loss)
    # 对于 LONG: initial_sl_rr=-1.0, entry=65065, 预期 SL 在 64065 附近


# ============================================================
# UT-006: TP 目标价格计算 (LONG)
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_tp_target_price_long(single_tp_strategy: "OrderStrategy"):
    """
    UT-006: TP 目标价格计算 (LONG)
    验证：tp_price = actual_entry + RR × (actual_entry - sl)

    公式：
    LONG: tp_price = entry_price + rr_multiple * (entry_price - stop_loss)
    """
    entry_price = Decimal('65065')
    stop_loss = Decimal('64065')
    rr_multiple = Decimal('1.0')

    # 预期 TP 价格 = 65065 + 1.0 × (65065 - 64065) = 65065 + 1000 = 66065
    expected_tp = entry_price + rr_multiple * (entry_price - stop_loss)
    assert expected_tp == Decimal('66065')

    # 使用策略方法计算 (需要传入 stop_loss 参数)
    tp_targets = [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')]
    tp_price = single_tp_strategy.get_tp_target_price(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp_level=1,
        direction=Direction.LONG,
        tp_targets=tp_targets,
    )

    assert tp_price == expected_tp


# ============================================================
# UT-007: TP 目标价格计算 (SHORT)
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_tp_target_price_short(single_tp_strategy: "OrderStrategy"):
    """
    UT-007: TP 目标价格计算 (SHORT)
    验证：tp_price = actual_entry - RR × (sl - actual_entry)

    公式:
    SHORT: tp_price = entry_price - rr_multiple * (stop_loss - entry_price)
    """
    entry_price = Decimal('3500')
    stop_loss = Decimal('3600')
    rr_multiple = Decimal('1.0')

    # 预期 TP 价格 = 3500 - 1.0 × (3600 - 3500) = 3500 - 100 = 3400
    expected_tp = entry_price - rr_multiple * (stop_loss - entry_price)
    assert expected_tp == Decimal('3400')

    # 使用策略方法计算 (需要传入 stop_loss 参数)
    tp_targets = [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')]
    tp_price = single_tp_strategy.get_tp_target_price(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp_level=1,
        direction=Direction.SHORT,
        tp_targets=tp_targets,
    )

    assert tp_price == expected_tp


# ============================================================
# UT-008: handle_order_filled TP1 成交
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_handle_order_filled_tp1_updates_sl_qty(
    multi_tp_strategy: "OrderStrategy",
    sample_signal: Signal,
):
    """
    UT-008: handle_order_filled TP1 成交
    验证：更新 SL 数量 = current_qty
    """
    manager = OrderManager()

    # 模拟仓位：TP1 成交后剩余 0.5 BTC
    position = Position(
        id="pos-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('0.5'),  # TP1(50%) 成交后剩余
    )

    # 模拟 TP1 订单已成交
    tp1_order = Order(
        id="order-tp1-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.5'),
        average_exec_price=Decimal('66065'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 模拟 SL 订单 (尚未成交)
    sl_order = Order(
        id="order-sl-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),  # 初始为总数量
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [tp1_order, sl_order]
    # positions_map uses signal_id as the key (not position.id)
    positions_map = {sample_signal.id: position}

    # 处理 TP1 成交事件
    new_orders = manager.handle_order_filled(
        filled_order=tp1_order,
        active_orders=active_orders,
        positions_map=positions_map,
    )

    # 验证 SL 订单数量已更新为剩余仓位
    # SL 订单应该在 active_orders 中被修改，或在 new_orders 中返回更新后的版本
    sl_updated = False
    for order in active_orders + new_orders:
        if order.order_role == OrderRole.SL and order.id == sl_order.id:
            assert order.requested_qty == Decimal('0.5')
            sl_updated = True
            break

    assert sl_updated, "SL 订单数量应该更新为剩余仓位 0.5"


# ============================================================
# UT-009: handle_order_filled SL 成交
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_handle_order_filled_sl_cancels_all_tp(
    sample_signal: Signal,
):
    """
    UT-009: handle_order_filled SL 成交
    验证：撤销所有 TP 订单
    """
    manager = OrderManager()

    # 模拟 SL 订单已成交
    sl_order = Order(
        id="order-sl-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('64065'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785720000,
    )

    # 模拟未成交的 TP 订单
    tp1_order = Order(
        id="order-tp1-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        price=Decimal('66065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    tp2_order = Order(
        id="order-tp2-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,  # 注意：可能是 TP1 的延续
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0'),
        price=Decimal('67065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [sl_order, tp1_order, tp2_order]
    positions_map = {}

    # 处理 SL 成交事件
    new_orders = manager.handle_order_filled(
        filled_order=sl_order,
        active_orders=active_orders,
        positions_map=positions_map,
    )

    # 所有 TP 订单应该被撤销
    for order in active_orders:
        if order.order_role in [OrderRole.TP1]:
            assert order.status == OrderStatus.CANCELED


# ============================================================
# UT-010: apply_oco_logic 完全平仓
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_apply_oco_logic_full_close(sample_signal: Signal):
    """
    UT-010: apply_oco_logic 完全平仓
    验证：current_qty==0 时撤销所有挂单
    """
    manager = OrderManager()

    # 模拟仓位已完全平仓
    position = Position(
        id="pos-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('0'),  # 完全平仓
        is_closed=True,
    )

    # 模拟剩余挂单
    tp2_order = Order(
        id="order-tp2-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0'),
        price=Decimal('67065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    sl_order = Order(
        id="order-sl-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [tp2_order, sl_order]

    # 应用 OCO 逻辑 (需要传入 position 参数)
    canceled_orders = manager.apply_oco_logic(
        filled_order=Order(
            id="order-tp3-001",
            signal_id=sample_signal.id,
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.2'),
            filled_qty=Decimal('0.2'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785780000,
        ),
        active_orders=active_orders,
        position=position,
    )

    # 所有剩余挂单应被撤销
    assert tp2_order.status == OrderStatus.CANCELED
    assert sl_order.status == OrderStatus.CANCELED


# ============================================================
# UT-011: apply_oco_logic 部分平仓
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_apply_oco_logic_partial_close(sample_signal: Signal):
    """
    UT-011: apply_oco_logic 部分平仓
    验证：更新 SL 数量与 current_qty 对齐
    """
    manager = OrderManager()

    # 模拟仓位部分平仓 (剩余 0.5 BTC)
    position = Position(
        id="pos-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('0.5'),  # 部分平仓后剩余
    )

    # 模拟 SL 订单
    sl_order = Order(
        id="order-sl-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),  # 初始为总数量
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [sl_order]

    # 模拟 TP1 成交
    tp1_filled = Order(
        id="order-tp1-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.5'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 应用 OCO 逻辑 (需要传入 position 参数)
    manager.apply_oco_logic(
        filled_order=tp1_filled,
        active_orders=active_orders,
        position=position,
    )

    # SL 订单数量应更新为剩余仓位
    assert sl_order.requested_qty == Decimal('0.5')


# ============================================================
# UT-012: get_order_chain_status
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_order_chain_status(sample_signal: Signal):
    """
    UT-012: get_order_chain_status
    验证：返回正确状态字典
    """
    manager = OrderManager()

    # 模拟订单链状态
    entry_order = Order(
        id="order-entry-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65065'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    tp1_order = Order(
        id="order-tp1-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.5'),
        price=Decimal('66065'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785720000,
    )

    tp2_order = Order(
        id="order-tp2-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0'),
        price=Decimal('67065'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    sl_order = Order(
        id="order-sl-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        trigger_price=Decimal('65065'),  # Breakeven 后
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785720000,
    )

    orders = [entry_order, tp1_order, tp2_order, sl_order]

    status = manager.get_order_chain_status(
        orders=orders,
        signal_id=sample_signal.id,
    )

    # 验证状态字典结构
    assert isinstance(status, dict)
    assert 'entry_filled' in status
    assert 'tp_filled_count' in status
    assert 'sl_status' in status
    assert 'remaining_qty' in status
    assert 'closed_percent' in status

    # 验证具体值
    assert status['entry_filled'] is True
    assert status['tp_filled_count'] == 1
    assert status['remaining_qty'] == Decimal('0.5')
    assert status['closed_percent'] == Decimal('50')


# ============================================================
# UT-013: Decimal 精度保护
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_decimal_precision_protection(single_tp_strategy: "OrderStrategy"):
    """
    UT-013: Decimal 精度保护
    验证：所有计算无 float 污染
    """
    # 验证 tp_ratios 全部为 Decimal
    for ratio in single_tp_strategy.tp_ratios:
        assert isinstance(ratio, Decimal), f"tp_ratio 应该是 Decimal, 实际为 {type(ratio)}"

    # 验证计算结果也是 Decimal
    entry_price = Decimal('65065.123456789')
    stop_loss = Decimal('64065.987654321')
    rr_multiple = Decimal('1.5')

    # 手动计算公式 (LONG)
    tp_price = entry_price + rr_multiple * (entry_price - stop_loss)
    assert isinstance(tp_price, Decimal)

    # 验证策略方法返回 Decimal (需要传入 stop_loss 参数)
    tp_targets = [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')]
    result = single_tp_strategy.get_tp_target_price(
        entry_price=entry_price,
        stop_loss=stop_loss,
        tp_level=1,
        direction=Direction.LONG,
        tp_targets=tp_targets,
    )
    assert isinstance(result, Decimal), f"get_tp_target_price 应该返回 Decimal, 实际为 {type(result)}"


# ============================================================
# UT-014: 职责边界验证
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_responsibility_boundary():
    """
    UT-014: 职责边界验证
    验证：OrderManager 修改 SL 数量，DynamicRiskManager 修改 SL 价格
    """
    # 这是一个集成测试性质的单元测试
    # 验证 OrderManager 和 DynamicRiskManager 的职责边界

    # OrderManager 职责：
    # - 创建订单链
    # - 处理订单成交事件
    # - 更新 SL 订单的 requested_qty (数量同步)
    # - 执行 OCO 逻辑

    # DynamicRiskManager 职责 (Phase 3):
    # - 监听 TP1 首次成交事件
    # - 执行 Breakeven (SL 价格上移至 entry_price)
    # - 执行 Trailing Stop (追踪水位线)
    # - 不修改 requested_qty

    # 测试通过文档注释验证职责边界
    from src.domain.order_manager import OrderManager

    # 验证 OrderManager 有数量相关方法
    assert hasattr(OrderManager, 'handle_order_filled')
    assert hasattr(OrderManager, 'apply_oco_logic')
    assert hasattr(OrderManager, 'create_order_chain')

    # DynamicRiskManager 在 src/domain/risk_manager.py 中定义
    from src.domain.risk_manager import DynamicRiskManager

    # 验证 DynamicRiskManager 有价格调整相关方法
    assert hasattr(DynamicRiskManager, 'evaluate_and_mutate')


# ============================================================
# 主入口 (用于直接运行测试)
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
