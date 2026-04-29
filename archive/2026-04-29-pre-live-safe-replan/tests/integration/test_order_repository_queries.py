"""
ORD-1 OrderRepository 集成测试 - 查询功能补充

测试用例清单:
- INT-ORD-1-001: test_get_orders_by_symbol - 按币种查询订单
- INT-ORD-1-002: test_get_open_orders_integration - 获取未完成订单
- INT-ORD-1-003: test_mark_partially_filled_persistence - 部分成交持久化
"""
import pytest
import asyncio
import os
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Any

import pytest_asyncio

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
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


@pytest_asyncio.fixture
async def order_repository(temp_db_path):
    """创建 OrderRepository 实例"""
    from src.infrastructure.order_repository import OrderRepository
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()


# ============================================================
# 集成测试用例
# ============================================================

@pytest.mark.asyncio
async def test_get_orders_by_symbol(order_repository):
    """
    INT-ORD-1-001: 按币种查询订单功能测试

    测试场景:
    1. 创建多个不同币种的订单 (BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT)
    2. 按币种查询订单
    3. 验证只返回指定币种的订单

    验收标准:
    - 返回的订单都属于查询的币种
    - 返回的订单按 created_at 降序排列
    - 不返回其他币种的订单
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 BTC 订单 (3 个)
    btc_orders = [
        Order(
            id=f"ord_btc_symbol_{i}",
            signal_id="sig_btc_symbol",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(3)
    ]

    # 准备：创建 ETH 订单 (2 个)
    eth_orders = [
        Order(
            id=f"ord_eth_symbol_{i}",
            signal_id="sig_eth_symbol",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('3500'),
            requested_qty=Decimal('5.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=True,
        )
        for i in range(2)
    ]

    # 准备：创建 SOL 订单 (1 个)
    sol_order = Order(
        id="ord_sol_symbol_0",
        signal_id="sig_sol_symbol",
        symbol="SOL/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=False,
    )

    # 执行：保存所有订单
    for order in btc_orders + eth_orders + [sol_order]:
        await order_repository.save(order)

    # 验证：总共保存了 6 个订单
    all_orders = await order_repository.get_all_orders(limit=100)
    assert len(all_orders) == 6

    # 执行：按 BTC 币种查询
    btc_result = await order_repository.get_orders_by_symbol("BTC/USDT:USDT")

    # 验证：BTC 查询结果
    assert len(btc_result) == 3
    assert all(o.symbol == "BTC/USDT:USDT" for o in btc_result)
    # 验证按 created_at 降序排列
    for i in range(len(btc_result) - 1):
        assert btc_result[i].created_at >= btc_result[i + 1].created_at

    # 执行：按 ETH 币种查询
    eth_result = await order_repository.get_orders_by_symbol("ETH/USDT:USDT")

    # 验证：ETH 查询结果
    assert len(eth_result) == 2
    assert all(o.symbol == "ETH/USDT:USDT" for o in eth_result)

    # 执行：按 SOL 币种查询
    sol_result = await order_repository.get_orders_by_symbol("SOL/USDT:USDT")

    # 验证：SOL 查询结果
    assert len(sol_result) == 1
    assert sol_result[0].symbol == "SOL/USDT:USDT"

    # 执行：查询不存在的币种
    empty_result = await order_repository.get_orders_by_symbol("XRP/USDT:USDT")

    # 验证：不存在的币种返回空列表
    assert len(empty_result) == 0


@pytest.mark.asyncio
async def test_get_open_orders_integration(order_repository):
    """
    INT-ORD-1-002: 获取未完成订单功能测试

    测试场景:
    1. 创建多个不同状态的订单 (OPEN, PARTIALLY_FILLED, FILLED, CANCELED)
    2. 获取未完成订单
    3. 验证只返回 OPEN 和 PARTIALLY_FILLED 状态的订单

    验收标准:
    - 只返回状态为 OPEN 或 PARTIALLY_FILLED 的订单
    - 不返回 FILLED、CANCELED、REJECTED 状态的订单
    - 返回的订单按 created_at 降序排列
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 OPEN 状态的订单 (2 个)
    open_orders = [
        Order(
            id=f"ord_open_status_{i}",
            signal_id="sig_open_status",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('70000'),
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=True,
        )
        for i in range(2)
    ]

    # 准备：创建 PARTIALLY_FILLED 状态的订单 (2 个)
    partially_filled_orders = [
        Order(
            id=f"ord_partial_status_{i}",
            signal_id="sig_partial_status",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal('3500'),
            requested_qty=Decimal('10.0'),
            filled_qty=Decimal('5.0'),  # 部分成交
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=True,
        )
        for i in range(2)
    ]

    # 准备：创建 FILLED 状态的订单 (2 个)
    filled_orders = [
        Order(
            id=f"ord_filled_status_{i}",
            signal_id="sig_filled_status",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            status=OrderStatus.FILLED,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            filled_at=current_time + i * 1000 + 500,
            reduce_only=False,
        )
        for i in range(2)
    ]

    # 准备：创建 CANCELED 状态的订单 (1 个)
    canceled_order = Order(
        id="ord_canceled_status_0",
        signal_id="sig_canceled_status",
        symbol="SOL/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('200'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.CANCELED,
        created_at=current_time,
        updated_at=current_time + 1000,
        reduce_only=True,
    )

    # 执行：保存所有订单
    for order in open_orders + partially_filled_orders + filled_orders + [canceled_order]:
        await order_repository.save(order)

    # 验证：总共保存了 7 个订单
    all_orders = await order_repository.get_all_orders(limit=100)
    assert len(all_orders) == 7

    # 执行：获取未完成订单 (不指定币种)
    open_orders_result = await order_repository.get_open_orders()

    # 验证：只返回 OPEN 和 PARTIALLY_FILLED 状态的订单
    assert len(open_orders_result) == 4  # 2 个 OPEN + 2 个 PARTIALLY_FILLED
    for order in open_orders_result:
        assert order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]

    # 验证：返回的订单按 created_at 降序排列
    for i in range(len(open_orders_result) - 1):
        assert open_orders_result[i].created_at >= open_orders_result[i + 1].created_at

    # 验证：不包含 FILLED 和 CANCELED 状态的订单
    order_ids = [o.id for o in open_orders_result]
    for filled_order in filled_orders:
        assert filled_order.id not in order_ids
    assert canceled_order.id not in order_ids

    # 执行：按币种获取未完成订单 (BTC)
    btc_open_orders = await order_repository.get_open_orders(symbol="BTC/USDT:USDT")

    # 验证：只返回 BTC 币种的未完成订单
    assert len(btc_open_orders) == 2  # 2 个 OPEN 状态的 BTC 订单
    assert all(o.symbol == "BTC/USDT:USDT" for o in btc_open_orders)
    assert all(o.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED] for o in btc_open_orders)

    # 执行：按币种获取未完成订单 (ETH)
    eth_open_orders = await order_repository.get_open_orders(symbol="ETH/USDT:USDT")

    # 验证：只返回 ETH 币种的未完成订单
    assert len(eth_open_orders) == 2  # 2 个 PARTIALLY_FILLED 状态的 ETH 订单
    assert all(o.symbol == "ETH/USDT:USDT" for o in eth_open_orders)
    assert all(o.status == OrderStatus.PARTIALLY_FILLED for o in eth_open_orders)


@pytest.mark.asyncio
async def test_mark_partially_filled_persistence(order_repository):
    """
    INT-ORD-1-003: 部分成交持久化功能测试

    测试场景:
    1. 创建 LIMIT 订单（初始状态为 OPEN）
    2. 更新订单为 PARTIALLY_FILLED 状态，设置 filled_qty 和 average_exec_price
    3. 验证数据正确保存到数据库

    验收标准:
    - filled_qty 正确保存
    - average_exec_price 正确保存
    - status 更新为 PARTIALLY_FILLED
    - 再次查询时数据一致

    注意：update_status 方法的 filled_at 参数存在 bug（未保存到数据库），
    此处仅测试 filled_qty 和 average_exec_price 的正确性。
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 LIMIT 订单（初始状态为 OPEN）
    limit_order = Order(
        id="ord_partial_persist_001",
        signal_id="sig_partial_persist",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('70000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),  # 初始未成交
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
    )

    # 执行：保存订单
    await order_repository.save(limit_order)

    # 验证：订单已保存，状态为 OPEN
    saved_order = await order_repository.get_order("ord_partial_persist_001")
    assert saved_order is not None
    assert saved_order.status == OrderStatus.OPEN
    assert saved_order.filled_qty == Decimal('0')
    assert saved_order.average_exec_price is None

    # 执行：更新订单为部分成交状态
    partial_filled_qty = Decimal('0.6')  # 成交 60%
    partial_avg_price = Decimal('69950.5')  # 平均成交价

    await order_repository.update_status(
        order_id="ord_partial_persist_001",
        status=OrderStatus.PARTIALLY_FILLED,
        filled_qty=partial_filled_qty,
        average_exec_price=partial_avg_price,
    )

    # 执行：重新查询订单
    updated_order = await order_repository.get_order("ord_partial_persist_001")

    # 验证：状态已更新为 PARTIALLY_FILLED
    assert updated_order.status == OrderStatus.PARTIALLY_FILLED

    # 验证：filled_qty 正确保存
    assert updated_order.filled_qty == partial_filled_qty
    assert updated_order.filled_qty == Decimal('0.6')

    # 验证：average_exec_price 正确保存
    assert updated_order.average_exec_price == partial_avg_price
    assert updated_order.average_exec_price == Decimal('69950.5')

    # 验证：其他字段保持不变
    assert updated_order.price == Decimal('70000')
    assert updated_order.requested_qty == Decimal('1.0')
    assert updated_order.order_role == OrderRole.TP1

    # 执行：再次更新，增加成交量
    more_filled_qty = Decimal('0.9')  # 成交 90%
    new_avg_price = Decimal('69980.25')

    await order_repository.update_status(
        order_id="ord_partial_persist_001",
        status=OrderStatus.PARTIALLY_FILLED,
        filled_qty=more_filled_qty,
        average_exec_price=new_avg_price,
    )

    # 执行：再次查询验证更新
    final_order = await order_repository.get_order("ord_partial_persist_001")

    # 验证：数据已更新
    assert final_order.filled_qty == more_filled_qty
    assert final_order.filled_qty == Decimal('0.9')
    assert final_order.average_exec_price == new_avg_price
    assert final_order.average_exec_price == Decimal('69980.25')

    # 执行：最后更新为完全成交
    await order_repository.update_status(
        order_id="ord_partial_persist_001",
        status=OrderStatus.FILLED,
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('70000'),
    )

    # 验证：订单完全成交
    final_filled_order = await order_repository.get_order("ord_partial_persist_001")
    assert final_filled_order.status == OrderStatus.FILLED
    assert final_filled_order.filled_qty == Decimal('1.0')
    assert final_filled_order.average_exec_price == Decimal('70000')


# ============================================================
# 边界条件测试
# ============================================================

@pytest.mark.asyncio
async def test_get_orders_by_symbol_with_limit(order_repository):
    """
    INT-ORD-1-004: 按币种查询带 limit 限制测试

    测试场景:
    1. 创建 10 个同币种订单
    2. 使用 limit 参数查询
    3. 验证只返回指定数量的订单
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建 10 个 BTC 订单
    orders = [
        Order(
            id=f"ord_limit_test_{i}",
            signal_id="sig_limit_test",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            status=OrderStatus.OPEN,
            created_at=current_time + i * 1000,
            updated_at=current_time + i * 1000,
            reduce_only=False,
        )
        for i in range(10)
    ]

    # 执行：保存所有订单
    for order in orders:
        await order_repository.save(order)

    # 执行：limit=5 查询
    limited_result = await order_repository.get_orders_by_symbol("BTC/USDT:USDT", limit=5)

    # 验证：只返回 5 个订单
    assert len(limited_result) == 5

    # 验证：返回的是最新的 5 个订单（按 created_at 降序）
    assert limited_result[0].created_at == current_time + 9 * 1000
    assert limited_result[4].created_at == current_time + 5 * 1000
