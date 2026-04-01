"""
P5-011: 订单清理机制 - 单元测试

测试 OrderRepository 和 OrderManager 集成订单入库逻辑

测试用例清单:
- UT-P5-011-001: OrderRepository 初始化
- UT-P5-011-002: OrderRepository 保存订单
- UT-P5-011-003: OrderRepository 批量保存订单
- UT-P5-011-004: OrderRepository 更新订单状态
- UT-P5-011-005: OrderRepository 按信号 ID 查询订单
- UT-P5-011-006: OrderRepository 获取订单链
- UT-P5-011-007: OrderRepository 获取 OCO 组订单
- UT-P5-011-008: OrderManager 集成订单入库
- UT-P5-011-009: OrderManager handle_order_filled 保存 TP/SL 订单
- UT-P5-011-010: OrderManager apply_oco_logic 保存撤销订单
- UT-P5-011-011: ExchangeGateway 全局订单回调注册
- UT-P5-011-012: ExchangeGateway watch_orders 调用全局回调
"""
import pytest
import asyncio
import os
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Any
from unittest.mock import AsyncMock, MagicMock, patch

# 导入被测模块
from src.domain.order_manager import OrderManager
from src.domain.models import (
    Order, Position, Direction, OrderStatus, OrderType, OrderRole, Signal
)


# ============================================================
# 测试夹具 (Fixtures)
# ============================================================

@pytest.fixture
def temp_db_path():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # 清理
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
async def order_repository(temp_db_path):
    """创建 OrderRepository 实例"""
    from src.infrastructure.order_repository import OrderRepository
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
def sample_order() -> Order:
    """创建示例订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return Order(
        id="ord_test_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )


@pytest.fixture
def sample_tp_order() -> Order:
    """创建示例 TP 订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return Order(
        id="ord_tp1_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('70000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
        parent_order_id="ord_entry_001",
        oco_group_id="oco_sig_001",
    )


@pytest.fixture
def sample_sl_order() -> Order:
    """创建示例 SL 订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return Order(
        id="ord_sl_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('60000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
        parent_order_id="ord_entry_001",
        oco_group_id="oco_sig_001",
    )


@pytest.fixture
def sample_position() -> Position:
    """创建示例仓位"""
    return Position(
        id="pos_001",
        signal_id="sig_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )


# ============================================================
# OrderRepository 基础测试
# ============================================================

@pytest.mark.asyncio
async def test_order_repository_initialization(order_repository):
    """UT-P5-011-001: OrderRepository 初始化"""
    # 验证：初始化后数据库连接已建立
    assert order_repository._db is not None


@pytest.mark.asyncio
async def test_order_repository_save(order_repository, sample_order):
    """UT-P5-011-002: OrderRepository 保存订单"""
    # 执行：保存订单
    await order_repository.save(sample_order)

    # 验证：订单已保存
    saved_order = await order_repository.get_order(sample_order.id)
    assert saved_order is not None
    assert saved_order.id == sample_order.id
    assert saved_order.signal_id == sample_order.signal_id
    assert saved_order.symbol == sample_order.symbol
    assert saved_order.direction == sample_order.direction
    assert saved_order.order_role == sample_order.order_role
    assert saved_order.requested_qty == sample_order.requested_qty


@pytest.mark.asyncio
async def test_order_repository_save_batch(order_repository):
    """UT-P5-011-003: OrderRepository 批量保存订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建多个订单
    orders = [
        Order(
            id=f"ord_batch_{i}",
            signal_id="sig_batch",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )
        for i in range(5)
    ]

    # 执行：批量保存
    await order_repository.save_batch(orders)

    # 验证：所有订单已保存
    all_orders = await order_repository.get_all_orders(limit=100)
    batch_orders = [o for o in all_orders if o.signal_id == "sig_batch"]
    assert len(batch_orders) == 5


@pytest.mark.asyncio
async def test_order_repository_update_status(order_repository, sample_order):
    """UT-P5-011-004: OrderRepository 更新订单状态"""
    # 准备：先保存订单
    await order_repository.save(sample_order)

    # 执行：更新状态
    await order_repository.update_status(
        order_id=sample_order.id,
        status=OrderStatus.FILLED,
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
    )

    # 验证：状态已更新
    updated_order = await order_repository.get_order(sample_order.id)
    assert updated_order.status == OrderStatus.FILLED
    assert updated_order.filled_qty == Decimal('1.0')
    assert updated_order.average_exec_price == Decimal('65000')


@pytest.mark.asyncio
async def test_order_repository_get_orders_by_signal(order_repository, sample_order, sample_tp_order, sample_sl_order):
    """UT-P5-011-005: OrderRepository 按信号 ID 查询订单"""
    # 准备：保存多个订单
    await order_repository.save(sample_order)
    await order_repository.save(sample_tp_order)
    await order_repository.save(sample_sl_order)

    # 执行：按信号 ID 查询
    orders = await order_repository.get_orders_by_signal("sig_001")

    # 验证：返回所有关联订单
    assert len(orders) == 3
    order_roles = [o.order_role for o in orders]
    assert OrderRole.ENTRY in order_roles
    assert OrderRole.TP1 in order_roles
    assert OrderRole.SL in order_roles


@pytest.mark.asyncio
async def test_order_repository_get_order_chain(order_repository, sample_order, sample_tp_order, sample_sl_order):
    """UT-P5-011-006: OrderRepository 获取订单链"""
    # 准备：保存订单链
    await order_repository.save(sample_order)
    await order_repository.save(sample_tp_order)
    await order_repository.save(sample_sl_order)

    # 执行：获取订单链
    chain = await order_repository.get_order_chain("sig_001")

    # 验证：订单链结构正确
    assert "entry" in chain
    assert "tps" in chain
    assert "sl" in chain
    assert len(chain["entry"]) == 1
    assert len(chain["tps"]) == 1
    assert len(chain["sl"]) == 1


@pytest.mark.asyncio
async def test_order_repository_get_oco_group(order_repository, sample_tp_order, sample_sl_order):
    """UT-P5-011-007: OrderRepository 获取 OCO 组订单"""
    # 准备：保存 OCO 组订单
    await order_repository.save(sample_tp_order)
    await order_repository.save(sample_sl_order)

    # 执行：获取 OCO 组
    oco_orders = await order_repository.get_oco_group("oco_sig_001")

    # 验证：返回 OCO 组所有订单
    assert len(oco_orders) == 2
    assert all(o.oco_group_id == "oco_sig_001" for o in oco_orders)


# ============================================================
# OrderManager 集成测试
# ============================================================

@pytest.mark.asyncio
async def test_order_manager_save_order_chain(order_repository):
    """UT-P5-011-008: OrderManager 集成订单入库"""
    # 准备：创建 OrderManager 并设置 repository
    manager = OrderManager(order_repository=order_repository)

    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    orders = [
        Order(
            id="ord_mgr_001",
            signal_id="sig_mgr_001",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('10.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )
    ]

    # 执行：保存订单链
    await manager.save_order_chain(orders)

    # 验证：订单已保存
    saved_order = await order_repository.get_order("ord_mgr_001")
    assert saved_order is not None
    assert saved_order.signal_id == "sig_mgr_001"


@pytest.mark.asyncio
async def test_order_manager_handle_order_filled_saves_tp_sl(order_repository, sample_order, sample_position):
    """UT-P5-011-009: OrderManager handle_order_filled 保存 TP/SL 订单"""
    # 准备：创建 OrderManager 并设置 repository
    manager = OrderManager(order_repository=order_repository)

    # 模拟 ENTRY 订单已成交
    sample_order.status = OrderStatus.FILLED
    sample_order.filled_qty = Decimal('1.0')
    sample_order.average_exec_price = Decimal('65000')

    # 执行：处理成交事件
    strategy = None  # 使用默认配置
    tp_targets = [Decimal('1.5')]  # 1.5R 止盈
    new_orders = await manager.handle_order_filled(
        filled_order=sample_order,
        active_orders=[sample_order],
        positions_map={"sig_001": sample_position},
        strategy=strategy,
        tp_targets=tp_targets,
    )

    # 验证：生成了 TP 和 SL 订单并已保存
    assert len(new_orders) >= 2  # 至少 1 个 TP + 1 个 SL

    # 验证新订单已保存到数据库
    for order in new_orders:
        saved = await order_repository.get_order(order.id)
        assert saved is not None
        assert saved.order_role in [OrderRole.TP1, OrderRole.SL]


@pytest.mark.asyncio
async def test_order_manager_apply_oco_logic_saves_canceled_orders(order_repository):
    """UT-P5-011-010: OrderManager apply_oco_logic 保存撤销订单"""
    # 准备：创建 OrderManager 和订单
    manager = OrderManager(order_repository=order_repository)

    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    tp_order = Order(
        id="ord_tp_oco",
        signal_id="sig_oco",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('70000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
    )

    position = Position(
        id="pos_oco",
        signal_id="sig_oco",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('0'),  # 完全平仓
    )

    # 执行：应用 OCO 逻辑（完全平仓场景）
    await manager._apply_oco_logic_for_tp(tp_order, [tp_order], position)

    # 验证：TP 订单被撤销并已保存
    saved_order = await order_repository.get_order("ord_tp_oco")
    assert saved_order is not None
    assert saved_order.status == OrderStatus.CANCELED


# ============================================================
# ExchangeGateway 全局回调测试
# ============================================================

@pytest.mark.asyncio
async def test_exchange_gateway_set_global_order_callback():
    """UT-P5-011-011: ExchangeGateway 全局订单回调注册"""
    from src.infrastructure.exchange_gateway import ExchangeGateway

    # 准备：创建 gateway 实例（不实际连接交易所）
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

    # 准备：创建回调函数
    callback_called = []
    async def mock_callback(order: Order) -> None:
        callback_called.append(order)

    # 执行：注册全局回调
    gateway.set_global_order_callback(mock_callback)

    # 验证：回调已注册
    assert gateway._global_order_callback is not None

    # 执行：触发回调通知
    test_order = Order(
        id="ord_callback_test",
        signal_id="sig_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        reduce_only=False,
    )
    await gateway._notify_global_order_callback(test_order)

    # 验证：回调被调用
    assert len(callback_called) == 1
    assert callback_called[0].id == "ord_callback_test"


@pytest.mark.asyncio
async def test_order_manager_set_order_changed_callback(order_repository):
    """测试 OrderManager 设置订单变更回调"""
    # 准备
    manager = OrderManager(order_repository=order_repository)

    callback_orders = []
    async def mock_callback(order: Order) -> None:
        callback_orders.append(order)

    # 执行
    manager.set_order_changed_callback(mock_callback)

    # 验证：回调已设置
    assert manager._on_order_changed is not None

    # 执行：触发通知
    test_order = Order(
        id="ord_callback_mgr",
        signal_id="sig_mgr",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        updated_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        reduce_only=False,
    )
    await manager._notify_order_changed(test_order)

    # 验证：回调被调用
    assert len(callback_orders) == 1


# ============================================================
# 集成场景测试
# ============================================================

@pytest.mark.asyncio
async def test_full_order_lifecycle_persistence(order_repository):
    """测试完整订单生命周期的持久化"""
    # 准备：创建 OrderManager
    manager = OrderManager(order_repository=order_repository)

    # 阶段 1: 创建 ENTRY 订单
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_order = Order(
        id="ord_lifecycle_entry",
        signal_id="sig_lifecycle",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    # 执行：保存 ENTRY 订单
    await manager.save_order_chain([entry_order])

    # 验证：ENTRY 订单已保存
    saved_entry = await order_repository.get_order("ord_lifecycle_entry")
    assert saved_entry is not None
    assert saved_entry.status == OrderStatus.OPEN

    # 阶段 2: 模拟 ENTRY 成交并生成 TP/SL
    entry_order.status = OrderStatus.FILLED
    entry_order.filled_qty = Decimal('1.0')
    entry_order.average_exec_price = Decimal('65000')

    position = Position(
        id="pos_lifecycle",
        signal_id="sig_lifecycle",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal('65000'),
        current_qty=Decimal('1.0'),
    )

    # 执行：处理 ENTRY 成交
    tp_targets = [Decimal('1.5')]
    new_orders = await manager.handle_order_filled(
        filled_order=entry_order,
        active_orders=[entry_order],
        positions_map={"sig_lifecycle": position},
        strategy=None,
        tp_targets=tp_targets,
    )

    # 验证：TP/SL 订单已生成并保存
    tp_orders = await order_repository.get_orders_by_role(OrderRole.TP1, signal_id="sig_lifecycle")
    sl_orders = await order_repository.get_orders_by_role(OrderRole.SL, signal_id="sig_lifecycle")
    assert len(tp_orders) >= 1
    assert len(sl_orders) >= 1

    # 阶段 3: 更新 ENTRY 订单状态
    await order_repository.update_status(
        order_id="ord_lifecycle_entry",
        status=OrderStatus.FILLED,
        filled_qty=Decimal('1.0'),
    )

    # 验证：订单状态已更新
    updated_entry = await order_repository.get_order("ord_lifecycle_entry")
    assert updated_entry.status == OrderStatus.FILLED
    assert updated_entry.filled_qty == Decimal('1.0')

    # 阶段 4: 查询完整订单链
    chain = await order_repository.get_order_chain("sig_lifecycle")
    assert len(chain["entry"]) >= 1
    assert len(chain["tps"]) >= 1
    assert len(chain["sl"]) >= 1
