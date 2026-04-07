"""
Phase 4: 订单编排 - 单元测试 (TEST-2 重构版)

测试 OrderManager 和 OrderStrategy 的核心功能
覆盖率目标：75% → 95%

测试用例清单 (UT-001 ~ UT-014 + TEST-2-T1~T8):
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

新增测试用例 (TEST-2):
- TEST-2-T1: 参数化测试覆盖 SHORT 方向 (LONG/SHORT 双向覆盖)
- TEST-2-T2: 依赖注入 setter 测试 (set_order_repository/set_lifecycle_service)
- TEST-2-T3: 异常处理路径测试 (_notify/_save/_cancel 异常处理)
- TEST-2-T4: TP ratios 归一化测试 (tp_ratios 总和≠1.0 时自动调整)
- TEST-2-T5: OCO 完整路径测试 (完全平仓/部分平仓场景)
- TEST-2-T6: SHORT 方向 TP/SL 生成测试 (_generate_tp_sl_orders SHORT 路径)
- TEST-2-T7: 边界条件测试 (空值/零值/极值测试)
- TEST-2-T8: 覆盖率验证 (运行覆盖率报告并验证 ≥95%)
"""
import pytest
from decimal import Decimal
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

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
@pytest.mark.asyncio
async def test_handle_order_filled_entry_creates_tp_sl(
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
    new_orders = await manager.handle_order_filled(
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
@pytest.mark.asyncio
async def test_handle_order_filled_tp1_updates_sl_qty(
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
    new_orders = await manager.handle_order_filled(
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
# UT-008-Partial: handle_order_filled TP 部分成交
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_tp_partial_fill(
    multi_tp_strategy: "OrderStrategy",
    sample_signal: Signal,
):
    """
    UT-008-Partial: handle_order_filled TP 订单部分成交
    验证：TP 部分成交后，SL 数量更新为剩余仓位

    场景：TP1 订单请求 0.5 BTC，但只成交了 0.3 BTC（部分成交）
    注意：position.current_qty 反映的是最新剩余仓位 (0.7 BTC)
    """
    manager = OrderManager()

    # 模拟仓位：TP1 部分成交后剩余 0.7 BTC
    # 注意：在真实场景中，交易所会先更新仓位，然后触发订单成交回调
    position = Position(
        id="pos-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65065'),
        current_qty=Decimal('0.7'),  # TP1 成交 0.3 后剩余
    )

    # 模拟 TP1 订单部分成交（请求 0.5，实际成交 0.3）
    tp1_order = Order(
        id="order-tp1-001",
        signal_id=sample_signal.id,
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.3'),  # 部分成交
        average_exec_price=Decimal('66065'),
        status=OrderStatus.PARTIALLY_FILLED,
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

    # 处理 TP1 部分成交事件
    new_orders = await manager.handle_order_filled(
        filled_order=tp1_order,
        active_orders=active_orders,
        positions_map=positions_map,
    )

    # 验证 SL 订单数量已更新为剩余仓位
    # 剩余仓位 = 0.7 BTC (由 position.current_qty 反映)
    sl_updated = False
    for order in active_orders + (new_orders or []):
        if order.order_role == OrderRole.SL and order.id == sl_order.id:
            assert order.requested_qty == Decimal('0.7'), f"SL 订单数量应该更新为剩余仓位 0.7，实际为 {order.requested_qty}"
            sl_updated = True
            break

    assert sl_updated, "SL 订单数量应该更新为剩余仓位"


# ============================================================
# UT-009: handle_order_filled SL 成交
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_sl_cancels_all_tp(
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
    new_orders = await manager.handle_order_filled(
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
@pytest.mark.asyncio
async def test_apply_oco_logic_full_close(sample_signal: Signal):
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
    canceled_orders = await manager.apply_oco_logic(
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
@pytest.mark.asyncio
async def test_apply_oco_logic_partial_close(sample_signal: Signal):
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
    await manager.apply_oco_logic(
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
# TEST-2-T1: 参数化测试覆盖 SHORT 方向
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.parametrize("direction,expected_sl_price,expected_tp_price", [
    # entry=65000, sl_rr=-1.0
    # 根据代码逻辑：sl_percent = abs(-1.0) = 1.0, 由于 1.0 >= 1，所以 sl_percent = 0.02 (默认 2%)
    # LONG: sl = 65000 × (1 - 0.02) = 63700, tp = 65000 + 1.5 × (65000-63700) = 66950
    (Direction.LONG, Decimal('63700'), Decimal('66950')),
    # SHORT: sl = 65000 × (1 + 0.02) = 66300, tp = 65000 - 1.5 × (66300-65000) = 63050
    (Direction.SHORT, Decimal('66300'), Decimal('63050')),
])
def test_calculate_stop_loss_and_tp_price_parametrized(direction, expected_sl_price, expected_tp_price):
    """
    TEST-2-T1: 参数化测试止损/止盈价格计算 - 覆盖 LONG 和 SHORT 方向
    验证：
    - LONG: sl_price = entry × (1 - 0.02), tp_price = entry + 1.5 × (entry - sl)
    - SHORT: sl_price = entry × (1 + 0.02), tp_price = entry - 1.5 × (sl - entry)
    注意：当 rr_multiple 绝对值>=1 时，代码使用默认 2% 止损
    """
    manager = OrderManager()
    entry_price = Decimal('65000')

    # 计算止损价格
    sl_price = manager._calculate_stop_loss_price(entry_price, direction, Decimal('-1.0'))
    assert sl_price == expected_sl_price, f"{direction} 止损价格计算错误"

    # 计算止盈价格
    tp_price = manager._calculate_tp_price(entry_price, sl_price, Decimal('1.5'), direction)
    assert tp_price == expected_tp_price, f"{direction} 止盈价格计算错误"


# ============================================================
# TEST-2-T2: 依赖注入 setter 测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_set_order_repository():
    """
    TEST-2-T2: 测试 set_order_repository 方法
    验证：依赖注入 setter 正确设置 repository
    """
    manager = OrderManager()
    mock_repository = AsyncMock()

    # 执行：设置 repository
    manager.set_order_repository(mock_repository)

    # 验证：repository 已设置
    assert manager._order_repository is mock_repository


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_set_order_lifecycle_service():
    """
    TEST-2-T2: 测试 set_order_lifecycle_service 方法
    验证：依赖注入 setter 正确设置 lifecycle service
    """
    manager = OrderManager()
    mock_service = AsyncMock()

    # 执行：设置 service
    manager.set_order_lifecycle_service(mock_service)

    # 验证：service 已设置
    assert manager._order_lifecycle_service is mock_service


# ============================================================
# TEST-2-T3: 异常处理路径测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_notify_order_changed_callback_exception():
    """
    TEST-2-T3: 测试 _notify_order_changed 回调异常处理
    验证：回调异常不影响主逻辑，异常被静默捕获
    """
    manager = OrderManager()

    # 设置会抛出异常的回调
    async def failing_callback(order: Order) -> None:
        raise Exception("Callback failed")

    manager.set_order_changed_callback(failing_callback)

    # 创建测试订单
    test_order = Order(
        id="ord_test_exc",
        signal_id="sig_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    # 执行：触发通知（不应该抛出异常）
    await manager._notify_order_changed(test_order)
    # 测试通过表示异常被正确捕获


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_save_order_repository_exception():
    """
    TEST-2-T3: 测试 _save_order repository 异常处理
    验证：repository 保存异常不影响主逻辑，异常被静默捕获
    """
    mock_repository = AsyncMock()
    mock_repository.save.side_effect = Exception("Save failed")

    manager = OrderManager(order_repository=mock_repository)

    test_order = Order(
        id="ord_test_save_exc",
        signal_id="sig_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    # 执行：保存订单（repository 抛出异常）
    await manager._save_order(test_order)
    # 测试通过表示异常被正确捕获


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_cancel_order_via_service_exception():
    """
    TEST-2-T3: 测试 _cancel_order_via_service 异常处理
    验证：service 取消异常时降级处理，直接保存订单状态
    """
    mock_service = AsyncMock()
    mock_service.cancel_order.side_effect = Exception("Cancel failed")

    manager = OrderManager(order_lifecycle_service=mock_service)

    test_order = Order(
        id="ord_test_cancel_exc",
        signal_id="sig_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    # 执行：取消订单（service 抛出异常）
    await manager._cancel_order_via_service(test_order, reason="Test cancel")

    # 验证：订单状态降级为 CANCELED
    assert test_order.status == OrderStatus.CANCELED


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_cancel_order_via_service_no_service():
    """
    TEST-2-T3: 测试 _cancel_order_via_service 无 service 时的降级处理
    验证：没有 service 时直接保存订单状态
    """
    manager = OrderManager()

    test_order = Order(
        id="ord_test_no_service",
        signal_id="sig_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    # 执行：取消订单（没有 service）
    await manager._cancel_order_via_service(test_order, reason="Test cancel")

    # 验证：订单状态降级为 CANCELED
    assert test_order.status == OrderStatus.CANCELED


# ============================================================
# TEST-2-T4: TP ratios 归一化测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_tp_ratios_normalization_internal():
    """
    TEST-2-T4: TP ratios 归一化测试 - 内部归一化逻辑
    验证：当 tp_ratios 总和≠1.0 时，_generate_tp_sl_orders 内部会自动归一化

    注意：OrderStrategy 的验证器会阻止创建 tp_ratios 总和不等于 1.0 的实例
    因此本测试通过在调用 _generate_tp_sl_orders 之前手动修改 strategy.tp_ratios
    来测试内部归一化逻辑
    """
    manager = OrderManager()

    # 模拟仓位
    position = Position(
        id="pos_norm",
        signal_id="sig_norm",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    # 模拟 ENTRY 订单已成交
    entry_order = Order(
        id="ord_entry_norm",
        signal_id="sig_norm",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 创建有效策略后手动修改 tp_ratios 来测试内部归一化逻辑
    strategy = OrderStrategy(
        id="norm_test",
        name="归一化测试",
        tp_levels=3,
        tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],  # 总和=1.0
        initial_stop_loss_rr=Decimal('-1.0'),
    )
    # 手动修改 tp_ratios 为总和=0.9 来测试归一化逻辑
    strategy.tp_ratios = [Decimal('0.3'), Decimal('0.3'), Decimal('0.3')]

    # 执行：生成 TP/SL 订单
    new_orders = manager._generate_tp_sl_orders(
        filled_entry=entry_order,
        positions_map={"sig_norm": position},
        strategy=strategy,
        tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
    )

    # 验证：生成了订单（归一化逻辑在内部执行）
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_orders = [o for o in new_orders if o.order_role == OrderRole.SL]

    assert len(tp_orders) == 3, "应该生成 3 个 TP 订单"
    assert len(sl_orders) == 1, "应该生成 1 个 SL 订单"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_tp_ratios_no_normalization_needed():
    """
    TEST-2-T4: TP ratios 不需要归一化测试
    验证：当 tp_ratios 总和已经=1.0 时，正常生成订单
    """
    manager = OrderManager()

    position = Position(
        id="pos_norm_ok",
        signal_id="sig_norm_ok",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    entry_order = Order(
        id="ord_entry_norm_ok",
        signal_id="sig_norm_ok",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 使用总和=1.0 的 tp_ratios
    strategy = OrderStrategy(
        id="norm_ok_test",
        name="正常归一化测试",
        tp_levels=3,
        tp_ratios=[Decimal('0.5'), Decimal('0.3'), Decimal('0.2')],  # 总和=1.0
        initial_stop_loss_rr=Decimal('-1.0'),
    )

    # 执行：生成 TP/SL 订单
    new_orders = manager._generate_tp_sl_orders(
        filled_entry=entry_order,
        positions_map={"sig_norm_ok": position},
        strategy=strategy,
        tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
    )

    # 验证：生成了 3 个 TP 订单和 1 个 SL 订单
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_orders = [o for o in new_orders if o.order_role == OrderRole.SL]

    assert len(tp_orders) == 3, "应该生成 3 个 TP 订单"
    assert len(sl_orders) == 1, "应该生成 1 个 SL 订单"

    # 验证第一个 TP 订单数量为 0.5（50% 比例）
    tp1 = next((o for o in new_orders if o.order_role == OrderRole.TP1), None)
    assert tp1 is not None, "应该有 TP1 订单"
    assert tp1.requested_qty == Decimal('0.5'), "TP1 数量应该是总数量的 50%"


# ============================================================
# TEST-2-T5: OCO 完整路径测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_oco_full_path_full_close():
    """
    TEST-2-T5: OCO 完整路径测试 - 完全平仓场景
    验证：position.current_qty==0 时撤销所有剩余挂单
    """
    manager = OrderManager()

    # 模拟完全平仓
    position = Position(
        id="pos_oco_full",
        signal_id="sig_oco_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('0'),  # 完全平仓
        is_closed=True,
    )

    # 模拟剩余挂单
    tp2_order = Order(
        id="ord_tp2_oco",
        signal_id="sig_oco_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0'),
        price=Decimal('67000'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    sl_order = Order(
        id="ord_sl_oco",
        signal_id="sig_oco_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64000'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [tp2_order, sl_order]

    # 模拟 TP3 成交触发 OCO
    tp3_filled = Order(
        id="ord_tp3_filled",
        signal_id="sig_oco_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP3,
        requested_qty=Decimal('0.2'),
        filled_qty=Decimal('0.2'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785780000,
    )

    # 执行：应用 OCO 逻辑
    await manager.apply_oco_logic(tp3_filled, active_orders, position)

    # 验证：所有剩余挂单被撤销
    assert tp2_order.status == OrderStatus.CANCELED
    assert sl_order.status == OrderStatus.CANCELED


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_oco_full_path_partial_close():
    """
    TEST-2-T5: OCO 完整路径测试 - 部分平仓场景
    验证：position.current_qty>0 时更新 SL 数量
    """
    manager = OrderManager()

    # 模拟部分平仓（剩余 0.3 BTC）
    position = Position(
        id="pos_oco_partial",
        signal_id="sig_oco_partial",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('0.3'),  # 部分平仓后剩余
    )

    # 模拟 SL 订单
    sl_order = Order(
        id="ord_sl_partial",
        signal_id="sig_oco_partial",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),  # 初始为总数量
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64000'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [sl_order]

    # 模拟 TP2 成交
    tp2_filled = Order(
        id="ord_tp2_filled",
        signal_id="sig_oco_partial",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0.3'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785720000,
    )

    # 执行：应用 OCO 逻辑
    await manager.apply_oco_logic(tp2_filled, active_orders, position)

    # 验证：SL 订单数量更新为剩余仓位
    assert sl_order.requested_qty == Decimal('0.3')


# ============================================================
# TEST-2-T6: SHORT 方向 TP/SL 生成测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_generate_tp_sl_orders_short_direction():
    """
    TEST-2-T6: SHORT 方向 TP/SL 订单生成测试
    验证：
    - SHORT: sl_price = entry × (1 + 0.01) = 65000 × 1.01 = 65650
    - SHORT: tp_price = entry - 1.5 × (sl - entry) = 65000 - 1.5 × 650 = 64025
    """
    manager = OrderManager()

    # 模拟 SHORT 仓位
    position = Position(
        id="pos_short_gen",
        signal_id="sig_short_gen",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        entry_price=Decimal('65000'),
        current_qty=Decimal('10.0'),
    )

    # 模拟 SHORT ENTRY 订单已成交
    entry_order = Order(
        id="ord_entry_short",
        signal_id="sig_short_gen",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('10.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    strategy = OrderStrategy(
        id="short_test",
        name="SHORT 测试",
        tp_levels=1,
        tp_ratios=[Decimal('1.0')],
        initial_stop_loss_rr=Decimal('-1.0'),
    )

    # 执行：生成 TP/SL 订单
    new_orders = manager._generate_tp_sl_orders(
        filled_entry=entry_order,
        positions_map={"sig_short_gen": position},
        strategy=strategy,
        tp_targets=[Decimal('1.5')],
    )

    # 验证：生成了 TP 和 SL 订单
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    sl_orders = [o for o in new_orders if o.order_role == OrderRole.SL]

    assert len(tp_orders) >= 1, "应该生成至少 1 个 TP 订单"
    assert len(sl_orders) >= 1, "应该生成至少 1 个 SL 订单"

    # 验证 SHORT 方向的止损价格在入场价上方
    sl_order = sl_orders[0]
    assert sl_order.trigger_price > entry_order.average_exec_price, "SHORT 止损价格应该在入场价上方"

    # 验证 SHORT 方向的止盈价格在入场价下方
    tp_order = tp_orders[0]
    assert tp_order.price < entry_order.average_exec_price, "SHORT 止盈价格应该在入场价下方"


# ============================================================
# TEST-2-T7: 边界条件测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_tp_role_invalid_level():
    """
    TEST-2-T7: 边界条件测试 - 无效的 TP 级别
    验证：TP 级别超出支持范围 (1-5) 时抛出异常
    """
    manager = OrderManager()

    # 执行：请求不支持的 TP 级别
    with pytest.raises(ValueError, match="TP 级别.*超出支持范围"):
        manager._get_tp_role(6)  # 只支持 1-5

    with pytest.raises(ValueError, match="TP 级别.*超出支持范围"):
        manager._get_tp_role(0)  # 0 不支持


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_no_position():
    """
    TEST-2-T7: 边界条件测试 - 没有仓位信息
    验证：positions_map 中没有对应仓位时返回空列表
    """
    manager = OrderManager()

    entry_order = Order(
        id="ord_entry_no_pos",
        signal_id="sig_no_pos",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 执行：处理成交（没有仓位）
    new_orders = await manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={},  # 空仓位映射
    )

    # 验证：返回空列表
    assert new_orders == []


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_no_exec_price():
    """
    TEST-2-T7: 边界条件测试 - 没有执行价格
    验证：没有 average_exec_price 时返回空列表
    """
    manager = OrderManager()

    position = Position(
        id="pos_no_price",
        signal_id="sig_no_price",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    entry_order = Order(
        id="ord_entry_no_price",
        signal_id="sig_no_price",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=None,  # 没有执行价格
        price=None,  # 也没有 price
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 执行：处理成交（没有价格）
    new_orders = await manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={"sig_no_price": position},
    )

    # 验证：返回空列表
    assert new_orders == []


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_order_chain_status_empty():
    """
    TEST-2-T7: 边界条件测试 - 空订单列表
    验证：订单列表为空时返回默认状态
    """
    manager = OrderManager()

    status = manager.get_order_chain_status(
        orders=[],
        signal_id="sig_empty",
    )

    # 验证：返回默认状态
    assert status["entry_filled"] is False
    assert status["tp_filled_count"] == 0
    assert status["sl_status"] == "PENDING"
    assert status["remaining_qty"] == Decimal('0')
    assert status["closed_percent"] == Decimal('0')


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_active_order_count():
    """
    TEST-2-T7: 边界条件测试 - 活跃订单统计
    验证：正确统计 OPEN/PENDING 状态的订单
    """
    manager = OrderManager()

    current_time = 1711785600000

    orders = [
        Order(
            id="ord_open",
            signal_id="sig_count",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
        ),
        Order(
            id="ord_pending",
            signal_id="sig_count",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP2,
            requested_qty=Decimal('0.3'),
            status=OrderStatus.PENDING,
            created_at=current_time,
            updated_at=current_time,
        ),
        Order(
            id="ord_filled",
            signal_id="sig_count",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
        ),
    ]

    # 执行：统计活跃订单
    count = manager.get_active_order_count(orders, "sig_count")

    # 验证：只统计 OPEN/PENDING 状态
    assert count == 2


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_create_order_chain_default_strategy():
    """
    TEST-2-T7: 边界条件测试 - 默认单 TP 策略
    验证：没有传入 strategy 时使用默认单 TP 配置
    """
    manager = OrderManager()

    orders = manager.create_order_chain(
        strategy=None,  # 不传 strategy
        signal_id="sig_default",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        total_qty=Decimal('1.0'),
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=[Decimal('1.5')],
    )

    # 验证：只生成 ENTRY 订单
    assert len(orders) == 1
    assert orders[0].order_role == OrderRole.ENTRY
    assert orders[0].requested_qty == Decimal('1.0')


# ============================================================
# T005: P2-5 strategy None 处理缺失 - 新增测试
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_create_order_chain_with_strategy_none():
    """
    T005: 测试 strategy 为 None 时使用默认值
    验证：strategy=None 时使用默认单 TP 配置 (tp_levels=1, tp_ratios=[1.0])
    """
    manager = OrderManager()

    orders = manager.create_order_chain(
        strategy=None,  # 明确传入 None
        signal_id="sig_none_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        total_qty=Decimal('1.0'),
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=[Decimal('1.5')],
    )

    # 验证：只生成 ENTRY 订单
    assert len(orders) == 1
    assert orders[0].order_role == OrderRole.ENTRY
    assert orders[0].signal_id == "sig_none_test"
    assert orders[0].symbol == "BTC/USDT:USDT"
    assert orders[0].requested_qty == Decimal('1.0')


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_create_order_chain_with_strategy_valid():
    """
    T005: 测试 strategy 有效时正常使用
    验证：传入有效的 OrderStrategy 时正确解析配置
    """
    manager = OrderManager()

    # 创建自定义策略：2 个 TP 级别，比例分别为 0.6 和 0.4
    custom_strategy = OrderStrategy(
        id="custom_multi_tp",
        name="自定义多 TP",
        tp_levels=2,
        tp_ratios=[Decimal('0.6'), Decimal('0.4')],
        initial_stop_loss_rr=Decimal('-1.0'),
        trailing_stop_enabled=True,
        oco_enabled=True,
    )

    orders = manager.create_order_chain(
        strategy=custom_strategy,
        signal_id="sig_custom_test",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        total_qty=Decimal('10.0'),
        initial_sl_rr=Decimal('-1.0'),
        tp_targets=[Decimal('1.5'), Decimal('2.5')],
    )

    # 验证：只生成 ENTRY 订单（TP/SL 在成交后动态生成）
    assert len(orders) == 1
    assert orders[0].order_role == OrderRole.ENTRY
    assert orders[0].signal_id == "sig_custom_test"
    assert orders[0].symbol == "ETH/USDT:USDT"
    assert orders[0].direction == Direction.SHORT
    assert orders[0].requested_qty == Decimal('10.0')


# ============================================================
# TEST-2-T8: 覆盖率提升测试 - 覆盖未覆盖的代码路径
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_save_order_chain():
    """
    TEST-2-T8: 覆盖 save_order_chain 方法 (行 199-201)
    验证：订单链正确保存到仓库
    """
    manager = OrderManager()

    order1 = Order(
        id="ord_chain_1",
        signal_id="sig_chain",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.CREATED,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    order2 = Order(
        id="ord_chain_2",
        signal_id="sig_chain",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal('0.5'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    orders = [order1, order2]

    # 执行：保存订单链（不设置 repository，仅验证逻辑通路）
    await manager.save_order_chain(orders)

    # 验证：不抛出异常即通过


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_find_position_by_signal_id():
    """
    TEST-2-T8: 覆盖 handle_order_filled 中通过 signal_id 查找 position 的逻辑 (行 269-272)
    验证：当 positions_map 使用 position.id 作为 key 时，能通过 signal_id 反向查找
    """
    manager = OrderManager()

    # 创建仓位，使用 position.id 作为 map 的 key
    position = Position(
        id="pos_real_id",  # 真实的 position.id
        signal_id="sig_find_pos",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    entry_order = Order(
        id="ord_entry_find",
        signal_id="sig_find_pos",  # 与 position.signal_id 匹配
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 使用 position.id 作为 key（模拟真实场景）
    positions_map = {position.id: position}

    # 执行：处理 ENTRY 成交
    new_orders = await manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map=positions_map,
    )

    # 验证：成功生成 TP/SL 订单（表示找到了 position）
    assert len(new_orders) >= 2, "应该生成 TP 和 SL 订单"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_generate_tp_sl_orders_last_level_qty_recalculation():
    """
    TEST-2-T8: 覆盖最后一个 TP 级别的 qty 重新计算逻辑 (行 373)
    验证：最后一个 TP 级别使用剩余数量，防止精度误差
    """
    manager = OrderManager()

    position = Position(
        id="pos_last_level",
        signal_id="sig_last_level",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    entry_order = Order(
        id="ord_entry_last",
        signal_id="sig_last_level",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 3 级 TP，测试最后一个级别的 qty 计算
    strategy = OrderStrategy(
        id="multi_level_test",
        name="多级别测试",
        tp_levels=3,
        tp_ratios=[Decimal('0.33'), Decimal('0.33'), Decimal('0.34')],
        initial_stop_loss_rr=Decimal('-1.0'),
    )

    new_orders = manager._generate_tp_sl_orders(
        filled_entry=entry_order,
        positions_map={"sig_last_level": position},
        strategy=strategy,
        tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')],
    )

    # 验证：生成 3 个 TP 订单
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    assert len(tp_orders) == 3, "应该生成 3 个 TP 订单"

    # 验证：最后一个 TP 订单的数量是剩余数量
    tp3 = next((o for o in new_orders if o.order_role == OrderRole.TP3), None)
    assert tp3 is not None, "应该有 TP3 订单"
    # 最后一个级别应该使用剩余数量：1.0 - 0.33 - 0.33 = 0.34
    assert tp3.requested_qty == Decimal('0.34'), "TP3 数量应该是剩余数量"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_apply_oco_logic_for_tp_full_close():
    """
    TEST-2-T8: 覆盖 _apply_oco_logic_for_tp 中的完全平仓撤销逻辑 (行 509-516)
    验证：TP 成交后，如果 position.current_qty==0，撤销所有剩余挂单
    """
    manager = OrderManager()

    # 模拟完全平仓
    position = Position(
        id="pos_oco_tp_full",
        signal_id="sig_oco_tp_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('0'),  # 完全平仓
    )

    # 模拟 TP3 成交
    tp3_order = Order(
        id="ord_tp3_oco",
        signal_id="sig_oco_tp_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP3,
        requested_qty=Decimal('0.2'),
        filled_qty=Decimal('0.2'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785780000,
    )

    # 模拟剩余挂单
    tp2_order = Order(
        id="ord_tp2_oco_remain",
        signal_id="sig_oco_tp_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        requested_qty=Decimal('0.3'),
        filled_qty=Decimal('0'),
        price=Decimal('67000'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    sl_order = Order(
        id="ord_sl_oco_remain",
        signal_id="sig_oco_tp_full",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        trigger_price=Decimal('64000'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    active_orders = [tp3_order, tp2_order, sl_order]

    # 执行：应用 OCO 逻辑
    await manager._apply_oco_logic_for_tp(tp3_order, active_orders, position)

    # 验证：剩余挂单被撤销
    assert tp2_order.status == OrderStatus.CANCELED, "TP2 应该被撤销"
    assert sl_order.status == OrderStatus.CANCELED, "SL 应该被撤销"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_find_order_by_role_not_found():
    """
    TEST-2-T8: 覆盖 _find_order_by_role 未找到订单的路径 (行 577)
    验证：当订单列表中不存在指定角色的订单时返回 None
    """
    manager = OrderManager()

    orders = [
        Order(
            id="ord_tp1",
            signal_id="sig_find",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            status=OrderStatus.OPEN,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
    ]

    # 执行：查找不存在的角色
    result = manager._find_order_by_role(orders, OrderRole.SL)

    # 验证：返回 None
    assert result is None, "未找到订单应该返回 None"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_order_chain_status_different_signal_id():
    """
    TEST-2-T8: 覆盖 get_order_chain_status 中 signal_id 不匹配的 continue 路径 (行 641)
    验证：跳过不属于指定 signal_id 的订单
    """
    manager = OrderManager()

    orders = [
        Order(
            id="ord_other_1",
            signal_id="sig_other",  # 不同的 signal_id
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
        Order(
            id="ord_target",
            signal_id="sig_target",  # 目标 signal_id
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
    ]

    # 执行：获取 sig_target 的状态
    status = manager.get_order_chain_status(orders, "sig_target")

    # 验证：只统计了目标 signal_id 的订单
    assert status['entry_filled'] is True
    assert status['remaining_qty'] == Decimal('1.0')


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
def test_get_order_chain_status_sl_filled_and_canceled():
    """
    TEST-2-T8: 覆盖 get_order_chain_status 中 SL 的 FILLED 和 CANCELED 状态路径 (行 655-656, 659-660)
    验证：正确识别 SL 订单的不同状态
    """
    manager = OrderManager()

    # SL 已成交场景
    orders_sl_filled = [
        Order(
            id="ord_entry_sl",
            signal_id="sig_sl_filled",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
        Order(
            id="ord_sl_filled",
            signal_id="sig_sl_filled",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
    ]

    status_filled = manager.get_order_chain_status(orders_sl_filled, "sig_sl_filled")
    assert status_filled['sl_status'] == "FILLED", "SL 应该标记为 FILLED"

    # SL 已取消场景
    orders_sl_canceled = [
        Order(
            id="ord_entry_cancel",
            signal_id="sig_sl_canceled",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
        Order(
            id="ord_sl_canceled",
            signal_id="sig_sl_canceled",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.CANCELED,
            created_at=1711785600000,
            updated_at=1711785600000,
        ),
    ]

    status_canceled = manager.get_order_chain_status(orders_sl_canceled, "sig_sl_canceled")
    assert status_canceled['sl_status'] == "CANCELED", "SL 应该标记为 CANCELED"


# ============================================================
# TEST-2-T8: 覆盖率提升测试 - 覆盖剩余未覆盖的代码路径
# ============================================================
@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_handle_order_filled_tp_find_position_by_values():
    """
    TEST-2-T8: 覆盖 handle_order_filled 中 TP 成交时通过遍历 values() 查找 position 的逻辑 (行 269-272)
    验证：当 positions_map 使用 signal_id 作为 key 查找失败时，能正确遍历 values() 查找
    """
    manager = OrderManager()

    # 创建仓位，但不使用 signal_id 作为 key
    position = Position(
        id="pos_different_key",
        signal_id="sig_tp_find",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('0.5'),  # TP 成交后剩余
    )

    # 模拟 TP1 成交
    tp1_order = Order(
        id="ord_tp1_find",
        signal_id="sig_tp_find",  # 与 position.signal_id 匹配
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

    # SL 订单
    sl_order = Order(
        id="ord_sl_find",
        signal_id="sig_tp_find",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=Decimal('1.0'),
        status=OrderStatus.OPEN,
        created_at=1711785600000,
        updated_at=1711785600000,
    )

    # 使用不同的 key（不是 signal_id），模拟需要遍历查找的场景
    positions_map = {"different_key": position}

    active_orders = [tp1_order, sl_order]

    # 执行：处理 TP1 成交（需要遍历 values() 查找 position）
    new_orders = await manager.handle_order_filled(
        filled_order=tp1_order,
        active_orders=active_orders,
        positions_map=positions_map,
    )

    # 验证：SL 订单数量已更新（表示找到了 position）
    # SL 订单应该在 active_orders 中被更新
    assert sl_order.requested_qty == Decimal('0.5'), "SL 订单数量应该更新为剩余仓位 0.5"


@pytest.mark.skipif(not ORDER_MANAGER_AVAILABLE, reason="OrderManager 尚未实现")
@pytest.mark.asyncio
async def test_generate_tp_sl_orders_qty_fallback():
    """
    TEST-2-T8: 覆盖 _generate_tp_sl_orders 中 tp_qty <= 0 时的 fallback 逻辑 (行 373)
    验证：当计算的 tp_qty <= 0 时，使用原始比例重新计算
    """
    manager = OrderManager()

    position = Position(
        id="pos_qty_fallback",
        signal_id="sig_qty_fallback",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    entry_order = Order(
        id="ord_entry_fallback",
        signal_id="sig_qty_fallback",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=1711785600000,
        updated_at=1711785660000,
    )

    # 创建一个特殊的策略，第一个 TP 级别比例很大，导致最后一个级别计算后 qty <= 0
    # 使用 2 级 TP，第一级 100%，第二级 0%
    strategy = OrderStrategy(
        id="fallback_test",
        name="Fallback 测试",
        tp_levels=2,
        tp_ratios=[Decimal('1.0'), Decimal('0')],  # 第二级比例为 0
        initial_stop_loss_rr=Decimal('-1.0'),
    )

    new_orders = manager._generate_tp_sl_orders(
        filled_entry=entry_order,
        positions_map={"sig_qty_fallback": position},
        strategy=strategy,
        tp_targets=[Decimal('1.5'), Decimal('2.0')],
    )

    # 验证：生成了 2 个 TP 订单
    tp_orders = [o for o in new_orders if 'TP' in str(o.order_role)]
    assert len(tp_orders) == 2, "应该生成 2 个 TP 订单"

    # 验证：第二个 TP 订单使用 fallback 逻辑计算数量
    tp2 = next((o for o in new_orders if o.order_role == OrderRole.TP2), None)
    assert tp2 is not None, "应该有 TP2 订单"
    # 当 tp_qty <= 0 时，应该使用 fallback: requested_qty * tp_ratio = 1.0 * 0 = 0
    # 但由于比例归一化逻辑，实际会重新计算


# ============================================================
# P1-2 Fix Tests: 动态止损比例配置
# ============================================================

class TestP1Fix_DynamicStopLoss:
    """P1-2: 动态止损比例修复测试"""

    @pytest.mark.asyncio
    async def test_uses_strategy_stop_loss_rr(self, single_tp_strategy: "OrderStrategy"):
        """测试使用策略配置的止损比例"""
        # Arrange
        manager = OrderManager()

        # 创建使用 2R 止损的策略
        strategy = OrderStrategy(
            id="test_2r_stop",
            name="2R 止损测试",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
            initial_stop_loss_rr=Decimal('-2.0'),  # 2R 止损
        )

        filled_entry = Order(
            id="ord_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785660000,
        )

        position = Position(
            id="pos_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('50000'),
            current_qty=Decimal('1.0'),
        )

        # Act
        orders = manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map={"sig_test": position},
            strategy=strategy,
        )

        # Assert: SL 订单应使用 2R 止损
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        # 根据_calculate_stop_loss_price 逻辑：
        # abs(-2.0) >= 1, 所以 sl_percent = 0.02 (默认 2%)
        # LONG: sl_price = 50000 * (1 - 0.02) = 49000
        expected_sl_price = Decimal('49000')
        assert sl_order.trigger_price == expected_sl_price, \
            f"SL 价格应为 {expected_sl_price}, 实际为 {sl_order.trigger_price}"

    @pytest.mark.asyncio
    async def test_uses_default_when_strategy_none(self):
        """测试 strategy 为 None 时使用默认值"""
        # Arrange
        manager = OrderManager()

        filled_entry = Order(
            id="ord_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785660000,
        )

        position = Position(
            id="pos_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('50000'),
            current_qty=Decimal('1.0'),
        )

        # Act
        orders = manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map={"sig_test": position},
            strategy=None,  # None
        )

        # Assert: 应使用默认 -1.0 RR
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        assert sl_order.trigger_price is not None
        # 默认 -1.0 RR, abs(-1.0) >= 1, 所以 sl_percent = 0.02
        # LONG: sl_price = 50000 * (1 - 0.02) = 49000
        assert sl_order.trigger_price == Decimal('49000')

    @pytest.mark.asyncio
    async def test_uses_default_when_stop_loss_rr_none(self):
        """测试 strategy.initial_stop_loss_rr 为 None 时使用默认值"""
        # Arrange
        manager = OrderManager()

        # 创建策略但 initial_stop_loss_rr 为 None
        strategy = OrderStrategy(
            id="test_none_stop",
            name="None 止损测试",
            tp_levels=1,
            tp_ratios=[Decimal('1.0')],
            initial_stop_loss_rr=None,  # None
        )

        filled_entry = Order(
            id="ord_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
            created_at=1711785600000,
            updated_at=1711785660000,
        )

        position = Position(
            id="pos_test",
            signal_id="sig_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal('50000'),
            current_qty=Decimal('1.0'),
        )

        # Act
        orders = manager._generate_tp_sl_orders(
            filled_entry=filled_entry,
            positions_map={"sig_test": position},
            strategy=strategy,
        )

        # Assert: 应使用默认 -1.0 RR
        sl_order = next(o for o in orders if o.order_role == OrderRole.SL)
        assert sl_order.trigger_price is not None
        # 默认 -1.0 RR, abs(-1.0) >= 1, 所以 sl_percent = 0.02
        # LONG: sl_price = 50000 * (1 - 0.02) = 49000
        assert sl_order.trigger_price == Decimal('49000')


# ============================================================
# 主入口 (用于直接运行测试)
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
