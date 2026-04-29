"""
订单详情页 K 线渲染升级 - API 端点测试

测试 GET /api/v3/orders/{order_id}/klines 接口

注意：由于 API 端点依赖复杂的初始化逻辑，本测试文件主要测试
订单链查询逻辑，API 端点测试通过集成测试验证。

测试用例清单:
- UT-OKA-001: 订单链查询 - ENTRY 订单（有子订单）
- UT-OKA-002: 订单链查询 - TP 子订单（返回父订单 + 兄弟订单）
- UT-OKA-003: 订单链查询 - 无子订单的 ENTRY
- UT-OKA-004: 订单链查询 - 不存在的订单
- UT-OKA-005: K 线范围计算逻辑测试
"""
import pytest
import asyncio
import os
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Any
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.models import (
    Order, Direction, OrderStatus, OrderType, OrderRole,
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
def sample_entry_order() -> Order:
    """创建示例 ENTRY 订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    return Order(
        id="ord_entry_api_test",
        signal_id="sig_api_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('65000'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        filled_at=current_time,
        reduce_only=False,
    )


@pytest.fixture
def sample_tp_order(sample_entry_order) -> Order:
    """创建示例 TP 订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000) + 1000
    return Order(
        id="ord_tp_api_test",
        signal_id="sig_api_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('70000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.5'),
        average_exec_price=Decimal('70000'),
        status=OrderStatus.FILLED,
        created_at=current_time,
        updated_at=current_time,
        filled_at=current_time,
        parent_order_id=sample_entry_order.id,
        reduce_only=True,
    )


@pytest.fixture
def sample_sl_order(sample_entry_order) -> Order:
    """创建示例 SL 订单"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000) + 1000
    return Order(
        id="ord_sl_api_test",
        signal_id="sig_api_test",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('60000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.CANCELED,
        created_at=current_time,
        updated_at=current_time,
        parent_order_id=sample_entry_order.id,
        reduce_only=True,
    )


# ============================================================
# 订单链查询测试（核心功能）
# ============================================================

@pytest.mark.asyncio
async def test_order_chain_query_from_entry_order(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order
):
    """UT-OKA-001: 订单链查询 - ENTRY 订单（有子订单）"""
    # 准备：保存订单链
    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：从 ENTRY 订单查询
    chain = await order_repository.get_order_chain_by_order_id(sample_entry_order.id)

    # 验证：返回完整订单链
    assert len(chain) == 3
    order_ids = [o.id for o in chain]
    assert sample_entry_order.id in order_ids
    assert sample_tp_order.id in order_ids
    assert sample_sl_order.id in order_ids

    # 验证：订单按正确顺序返回（ENTRY 第一）
    assert chain[0].order_role == OrderRole.ENTRY


@pytest.mark.asyncio
async def test_order_chain_query_from_child_order(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order
):
    """UT-OKA-002: 订单链查询 - TP 子订单（返回父订单 + 兄弟订单）"""
    # 准备：保存订单链
    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：从 TP 子订单查询
    chain = await order_repository.get_order_chain_by_order_id(sample_tp_order.id)

    # 验证：返回完整订单链（包含父订单）
    assert len(chain) == 3
    order_ids = [o.id for o in chain]
    assert sample_entry_order.id in order_ids  # 父订单
    assert sample_tp_order.id in order_ids    # 自身
    assert sample_sl_order.id in order_ids    # 兄弟订单

    # 验证：父订单在第一的位置
    assert chain[0].order_role == OrderRole.ENTRY


@pytest.mark.asyncio
async def test_order_chain_query_no_children(
    order_repository, sample_entry_order
):
    """UT-OKA-003: 订单链查询 - 无子订单的 ENTRY"""
    # 准备：保存 ENTRY 订单（无子订单）
    await order_repository.save_order(sample_entry_order)

    # 执行：查询订单链
    chain = await order_repository.get_order_chain_by_order_id(sample_entry_order.id)

    # 验证：只返回 ENTRY 订单本身
    assert len(chain) == 1
    assert chain[0].id == sample_entry_order.id
    assert chain[0].order_role == OrderRole.ENTRY


@pytest.mark.asyncio
async def test_order_chain_query_not_found(
    order_repository
):
    """UT-OKA-004: 订单链查询 - 不存在的订单"""
    # 执行：查询不存在的订单
    chain = await order_repository.get_order_chain_by_order_id("ord_not_exists")

    # 验证：返回空列表
    assert len(chain) == 0


# ============================================================
# K 线范围计算逻辑测试
# ============================================================

@pytest.mark.asyncio
async def test_kline_range_calculation_with_order_chain(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order
):
    """UT-OKA-005: K 线范围计算覆盖完整订单链生命周期"""
    # 准备：保存订单链（使用不同时间戳）
    base_time = 1711785600000  # 基准时间

    sample_entry_order.filled_at = base_time
    sample_entry_order.created_at = base_time

    sample_tp_order.filled_at = base_time + 3600000  # 1 小时后
    sample_tp_order.created_at = base_time + 1000

    sample_sl_order.filled_at = None  # SL 未成交
    sample_sl_order.created_at = base_time + 1000

    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：查询订单链
    chain = await order_repository.get_order_chain_by_order_id(sample_entry_order.id)

    # 收集所有 filled_at 时间戳
    timestamps = [o.filled_at for o in chain if o.filled_at]

    # 验证：时间戳收集正确
    assert len(timestamps) == 2  # ENTRY 和 TP1 有 filled_at
    assert base_time in timestamps
    assert base_time + 3600000 in timestamps

    # 验证：K 线范围计算逻辑
    from src.interfaces.api import BacktestConfig
    timeframe = "15m"
    timeframe_ms = BacktestConfig.get_timeframe_ms(timeframe)

    min_time = min(timestamps)
    max_time = max(timestamps)

    # 计算 K 线范围（前后各 20 根）
    since = min_time - (20 * timeframe_ms)
    limit = int((max_time - since) / timeframe_ms) + 40

    # 验证：范围计算正确
    assert since == min_time - (20 * 900000)  # 15m = 900000ms
    assert limit > 0


@pytest.mark.asyncio
async def test_kline_range_without_filled_at(
    order_repository
):
    """UT-OKA-006: K 线范围计算 - 无 filled_at 使用 created_at 备选"""
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 准备：创建无 filled_at 的订单
    order_no_filled = Order(
        id="ord_no_filled_at",
        signal_id="sig_no_filled",
        symbol="ETH/USDT:USDT",
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('3500'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        filled_at=None,  # 无 filled_at
        reduce_only=True,
    )

    await order_repository.save_order(order_no_filled)

    # 执行：查询订单
    order = await order_repository.get_order(order_no_filled.id)

    # 验证：使用 created_at 作为备选
    kline_timestamp = order.filled_at if order.filled_at else order.created_at
    assert kline_timestamp == current_time


# ============================================================
# 订单链时间线对齐测试
# ============================================================

@pytest.mark.asyncio
async def test_order_chain_timeline_alignment(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order
):
    """UT-OKA-007: 订单链时间线对齐验证"""
    # 准备：使用固定时间戳
    entry_time = 1711785600000  # ENTRY 时间
    tp_time = entry_time + 1800000  # TP 在 30 分钟后
    sl_time = entry_time + 3600000  # SL 在 60 分钟后

    sample_entry_order.filled_at = entry_time
    sample_tp_order.filled_at = tp_time
    sample_sl_order.filled_at = sl_time

    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：查询订单链
    chain = await order_repository.get_order_chain_by_order_id(sample_entry_order.id)

    # 验证：时间戳顺序正确
    timestamps = [o.filled_at for o in chain if o.filled_at]
    assert timestamps == sorted(timestamps)

    # 验证：时间跨度正确（60 分钟）
    time_span = max(timestamps) - min(timestamps)
    assert time_span == 3600000  # 60 分钟 = 3600000ms
