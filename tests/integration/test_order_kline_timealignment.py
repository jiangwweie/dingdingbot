"""
Order K-line Time Alignment - Integration Tests

测试订单链时间线对齐的端到端功能

测试用例清单:
- IT-OKA-001: 订单链时间线对齐验证
- IT-OKA-002: 部分成交的订单链
- IT-OKA-003: 无 filled_at 时使用 created_at 备选
- IT-OKA-004: 多订单时间线对齐
- IT-OKA-005: K 线时间范围覆盖完整订单周期
"""
import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, patch, MagicMock

from src.domain.models import Order, OrderStatus, OrderType, OrderRole, Direction


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


# ============================================================
# 通用 Mock 设置
# ============================================================

def setup_mocks(entry_order, order_chain=None, mock_ohlcv=None):
    """设置通用的 mock 配置"""
    if order_chain is None:
        order_chain = [entry_order]
    if mock_ohlcv is None:
        mock_ohlcv = []

    # Mock OrderRepository
    repo_patch = patch('src.infrastructure.order_repository.OrderRepository')
    mock_repo_cls = repo_patch.start()
    mock_repo_instance = MagicMock()
    mock_repo_instance.get_order = AsyncMock(return_value=entry_order)
    mock_repo_instance.get_order_chain_by_order_id = AsyncMock(return_value=order_chain)
    mock_repo_instance.initialize = AsyncMock()
    mock_repo_instance.close = AsyncMock()
    mock_repo_cls.return_value = mock_repo_instance

    # Mock CCXT
    ccxt_patch = patch('ccxt.async_support.binanceusdm')
    mock_ccxt_cls = ccxt_patch.start()
    mock_exchange = MagicMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=mock_ohlcv)
    mock_exchange.close = AsyncMock()
    mock_ccxt_cls.return_value = mock_exchange

    return repo_patch, ccxt_patch


def teardown_mocks(repo_patch, ccxt_patch):
    """清理 mock"""
    repo_patch.stop()
    ccxt_patch.stop()


# ============================================================
# E2E 时间线对齐测试
# ============================================================

@pytest.mark.asyncio
async def test_order_chain_timeline_alignment(temp_db_path):
    """IT-OKA-001: E2E 测试 - 订单链时间线对齐验证"""
    from src.infrastructure.order_repository import OrderRepository

    # 使用固定时间戳创建订单链
    entry_time = 1711785660000  # 2024-03-30 12:01:00 UTC
    tp1_time = 1711789200000    # 2024-03-30 13:00:00 UTC
    sl_time = 1711789200000     # SL 与 TP1 同时创建（OCO 组）

    # 1. 创建完整订单链
    entry = Order(
        id="ord_e2e_entry",
        signal_id="sig_e2e_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('50000'),
        status=OrderStatus.FILLED,
        created_at=entry_time - 60000,
        updated_at=entry_time,
        filled_at=entry_time,
        reduce_only=False,
    )

    tp1 = Order(
        id="ord_e2e_tp1",
        signal_id="sig_e2e_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('52000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0.5'),
        status=OrderStatus.FILLED,
        created_at=entry_time,
        updated_at=tp1_time,
        filled_at=tp1_time,
        reduce_only=True,
        parent_order_id="ord_e2e_entry",
    )

    sl = Order(
        id="ord_e2e_sl",
        signal_id="sig_e2e_001",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('48000'),
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=entry_time,
        updated_at=sl_time,
        reduce_only=True,
        parent_order_id="ord_e2e_entry",
        oco_group_id="oco_sig_e2e_001",
    )

    # 保存订单链到临时数据库
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(entry)
    await repo.save_order(tp1)
    await repo.save_order(sl)
    await repo.close()

    # 计算预期的 K 线范围
    timeframe_ms = 900000  # 15m
    min_time = entry_time
    max_time = tp1_time
    since = min_time - (20 * timeframe_ms)
    limit = int((max_time - since) / timeframe_ms) + 40

    # Mock CCXT - 返回覆盖整个订单周期的 K 线
    mock_ohlcv = [
        [since + i * timeframe_ms, 49800 + i * 10, 49900 + i * 10, 49700 + i * 10, 49850 + i * 10, 100]
        for i in range(limit + 10)
    ]

    # 设置 mock
    repo_patch, ccxt_patch = setup_mocks(entry, [entry, tp1, sl], mock_ohlcv)
    try:
        from src.interfaces.api import get_order_klines
        result = await get_order_klines(
            order_id=entry.id,
            symbol="BTC/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result
    assert "order" in result

    # 验证订单时间戳在 K 线范围内
    kline_timestamps = [k[0] for k in result["klines"]]
    min_kline_time = min(kline_timestamps)
    max_kline_time = max(kline_timestamps)

    assert min_kline_time <= entry_time <= max_kline_time, \
        f"Entry time {entry_time} not in K-line range [{min_kline_time}, {max_kline_time}]"
    assert min_kline_time <= tp1_time <= max_kline_time, \
        f"TP1 time {tp1_time} not in K-line range [{min_kline_time}, {max_kline_time}]"


@pytest.mark.asyncio
async def test_partial_filled_order_chain(temp_db_path):
    """IT-OKA-002: 测试部分成交的订单链"""
    from src.infrastructure.order_repository import OrderRepository

    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    # 创建部分成交的订单链
    entry = Order(
        id="ord_partial_entry",
        signal_id="sig_partial",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('10.0'),
        average_exec_price=Decimal('3500'),
        status=OrderStatus.FILLED,
        created_at=current_time - 7200000,
        updated_at=current_time - 3600000,
        filled_at=current_time - 3600000,
        reduce_only=False,
    )

    tp1 = Order(
        id="ord_partial_tp1",
        signal_id="sig_partial",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('3600'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('5.0'),
        status=OrderStatus.FILLED,
        created_at=current_time - 3600000,
        updated_at=current_time - 1800000,
        filled_at=current_time - 1800000,
        reduce_only=True,
        parent_order_id="ord_partial_entry",
    )

    tp2 = Order(
        id="ord_partial_tp2",
        signal_id="sig_partial",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal('3700'),
        requested_qty=Decimal('5.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time - 3600000,
        updated_at=current_time,
        reduce_only=True,
        parent_order_id="ord_partial_entry",
    )

    sl = Order(
        id="ord_partial_sl",
        signal_id="sig_partial",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('3400'),
        requested_qty=Decimal('10.0'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time - 3600000,
        updated_at=current_time,
        reduce_only=True,
        parent_order_id="ord_partial_entry",
        oco_group_id="oco_sig_partial",
    )

    # 保存订单
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(entry)
    await repo.save_order(tp1)
    await repo.save_order(tp2)
    await repo.save_order(sl)
    await repo.close()

    # Mock CCXT
    timeframe_ms = 900000
    min_time = current_time - 7200000
    max_time = current_time - 1800000
    since = min_time - (20 * timeframe_ms)
    limit = int((max_time - since) / timeframe_ms) + 40

    mock_ohlcv = [
        [min_time + i * timeframe_ms, 3480 + i * 5, 3490 + i * 5, 3470 + i * 5, 3485 + i * 5, 1000]
        for i in range(limit + 10)
    ]

    repo_patch, ccxt_patch = setup_mocks(entry, [entry, tp1, tp2, sl], mock_ohlcv)
    try:
        from src.interfaces.api import get_order_klines
        result = await get_order_klines(
            order_id=entry.id,
            symbol="ETH/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result

    kline_timestamps = [k[0] for k in result["klines"]]
    assert min(kline_timestamps) <= entry.filled_at
    assert max(kline_timestamps) >= tp1.filled_at


@pytest.mark.asyncio
async def test_no_filled_at_fallback(temp_db_path):
    """IT-OKA-003: 测试无 filled_at 时使用 created_at 备选"""
    from src.infrastructure.order_repository import OrderRepository

    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

    order = Order(
        id="ord_no_filled",
        signal_id="sig_no_filled",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal('52000'),
        requested_qty=Decimal('0.5'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=current_time,
        updated_at=current_time,
        reduce_only=True,
    )

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(order)
    await repo.close()

    # Mock CCXT
    timeframe_ms = 900000
    since = current_time - (20 * timeframe_ms)
    limit = 50

    mock_ohlcv = [
        [current_time + i * timeframe_ms, 49800 + i * 10, 49900 + i * 10, 49700 + i * 10, 49850 + i * 10, 100]
        for i in range(limit)
    ]

    repo_patch, ccxt_patch = setup_mocks(order, [order], mock_ohlcv)
    try:
        from src.interfaces.api import get_order_klines
        result = await get_order_klines(
            order_id=order.id,
            symbol="BTC/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result

    kline_timestamps = [k[0] for k in result["klines"]]
    assert current_time in kline_timestamps or \
           any(abs(ts - current_time) < 900000 for ts in kline_timestamps)


@pytest.mark.asyncio
async def test_multi_order_timeline_alignment(temp_db_path):
    """IT-OKA-004: 测试多订单时间线对齐"""
    from src.infrastructure.order_repository import OrderRepository
    from src.interfaces.api import get_order_klines

    # 创建多个不同时间的订单
    base_time = 1711785660000

    orders = []
    for i in range(5):
        order = Order(
            id=f"ord_multi_{i}",
            signal_id=f"sig_multi_{i}",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('50000') + Decimal('100') * i,
            status=OrderStatus.FILLED,
            created_at=base_time + i * 3600000,
            updated_at=base_time + i * 3600000,
            filled_at=base_time + i * 3600000,
            reduce_only=False,
        )
        orders.append(order)

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    for order in orders:
        await repo.save_order(order)
    await repo.close()

    # Mock CCXT - 返回覆盖所有订单时间的 K 线
    timeframe_ms = 900000
    all_timestamps = [o.filled_at for o in orders]
    min_time = min(all_timestamps)
    max_time = max(all_timestamps)
    since = min_time - (20 * timeframe_ms)
    limit = int((max_time - since) / timeframe_ms) + 40

    mock_ohlcv = [
        [min_time + i * timeframe_ms, 50000 + i * 10, 50200 + i * 10, 49900 + i * 10, 50100 + i * 10, 100]
        for i in range(limit + 10)
    ]

    # 测试每个订单
    for order in orders:
        repo_patch, ccxt_patch = setup_mocks(order, [order], mock_ohlcv)
        try:
            result = await get_order_klines(
                order_id=order.id,
                symbol="BTC/USDT:USDT",
                include_chain=True
            )
        finally:
            teardown_mocks(repo_patch, ccxt_patch)

        assert result is not None
        assert "klines" in result

        kline_timestamps = [k[0] for k in result["klines"]]
        assert order.filled_at in kline_timestamps or \
               any(abs(ts - order.filled_at) < 1800000 for ts in kline_timestamps), \
            f"Order {order.id} time {order.filled_at} not aligned with K-lines"


@pytest.mark.asyncio
async def test_kline_range_covers_full_order_cycle(temp_db_path):
    """IT-OKA-005: 测试 K 线时间范围覆盖完整订单周期"""
    from src.infrastructure.order_repository import OrderRepository
    from src.interfaces.api import get_order_klines

    # 创建长周期订单链
    entry_time = 1711785660000
    tp4_time = entry_time + 86400000  # 24 小时后

    entry = Order(
        id="ord_cycle_entry",
        signal_id="sig_cycle",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('50000'),
        status=OrderStatus.FILLED,
        created_at=entry_time,
        updated_at=entry_time,
        filled_at=entry_time,
        reduce_only=False,
    )

    tp4 = Order(
        id="ord_cycle_tp4",
        signal_id="sig_cycle",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP4,
        price=Decimal('55000'),
        requested_qty=Decimal('0.25'),
        filled_qty=Decimal('0.25'),
        status=OrderStatus.FILLED,
        created_at=entry_time,
        updated_at=tp4_time,
        filled_at=tp4_time,
        reduce_only=True,
        parent_order_id="ord_cycle_entry",
    )

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(entry)
    await repo.save_order(tp4)
    await repo.close()

    # Mock CCXT - 返回覆盖 24 小时的 K 线
    timeframe_ms = 900000
    since = entry_time - (20 * timeframe_ms)
    limit = int((tp4_time - since) / timeframe_ms) + 40

    mock_ohlcv = [
        [entry_time + i * timeframe_ms, 50000 + i * 10, 50100 + i * 10, 49900 + i * 10, 50050 + i * 10, 100]
        for i in range(limit + 10)
    ]

    repo_patch, ccxt_patch = setup_mocks(entry, [entry, tp4], mock_ohlcv)
    try:
        result = await get_order_klines(
            order_id=entry.id,
            symbol="BTC/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result

    kline_timestamps = [k[0] for k in result["klines"]]
    min_kline = min(kline_timestamps)
    max_kline = max(kline_timestamps)

    assert min_kline <= entry_time, "K-line range should start before or at entry time"
    assert max_kline >= tp4_time, "K-line range should end after or at last TP time"


@pytest.mark.asyncio
async def test_order_chain_with_multiple_tp_levels(temp_db_path):
    """IT-OKA-006: 测试多止盈层级订单链"""
    from src.infrastructure.order_repository import OrderRepository
    from src.interfaces.api import get_order_klines

    base_time = 1711785660000

    # 创建 ENTRY + TP1 + TP2 + TP3 + SL 的完整订单链
    entry = Order(
        id="ord_mt_entry",
        signal_id="sig_mt",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('50000'),
        status=OrderStatus.FILLED,
        created_at=base_time,
        updated_at=base_time,
        filled_at=base_time,
        reduce_only=False,
    )

    tp_orders = []
    for i, (role, price, fill_time) in enumerate([
        (OrderRole.TP1, Decimal('51000'), base_time + 3600000),
        (OrderRole.TP2, Decimal('52000'), base_time + 7200000),
        (OrderRole.TP3, Decimal('53000'), base_time + 10800000),
    ]):
        tp = Order(
            id=f"ord_mt_tp{i+1}",
            signal_id="sig_mt",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=role,
            price=price,
            requested_qty=Decimal('0.33'),
            filled_qty=Decimal('0.33'),
            status=OrderStatus.FILLED,
            created_at=base_time,
            updated_at=fill_time,
            filled_at=fill_time,
            reduce_only=True,
            parent_order_id="ord_mt_entry",
        )
        tp_orders.append(tp)

    sl = Order(
        id="ord_mt_sl",
        signal_id="sig_mt",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal('49000'),
        requested_qty=Decimal('0.01'),
        filled_qty=Decimal('0'),
        status=OrderStatus.OPEN,
        created_at=base_time,
        updated_at=base_time + 10800000,
        reduce_only=True,
        parent_order_id="ord_mt_entry",
        oco_group_id="oco_sig_mt",
    )

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(entry)
    for tp in tp_orders:
        await repo.save_order(tp)
    await repo.save_order(sl)
    await repo.close()

    # Mock CCXT
    timeframe_ms = 900000
    min_time = base_time
    max_time = base_time + 10800000
    since = min_time - (20 * timeframe_ms)
    limit = int((max_time - since) / timeframe_ms) + 40

    mock_ohlcv = [
        [base_time + i * timeframe_ms, 50000 + i * 50, 50200 + i * 50, 49900 + i * 50, 50100 + i * 50, 100]
        for i in range(limit + 10)
    ]

    all_orders = [entry] + tp_orders + [sl]
    repo_patch, ccxt_patch = setup_mocks(entry, all_orders, mock_ohlcv)
    try:
        result = await get_order_klines(
            order_id=entry.id,
            symbol="BTC/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result

    kline_timestamps = [k[0] for k in result["klines"]]
    for tp in tp_orders:
        assert any(abs(ts - tp.filled_at) < 1800000 for ts in kline_timestamps), \
            f"TP {tp.order_role} time {tp.filled_at} not covered"


# ============================================================
# 边界条件测试
# ============================================================

@pytest.mark.asyncio
async def test_very_old_order_kline_fetch(temp_db_path):
    """IT-OKA-007: 测试非常久远的订单 K 线获取"""
    from src.infrastructure.order_repository import OrderRepository
    from src.interfaces.api import get_order_klines

    # 使用久远的时间戳（30 天前）
    old_time = int(datetime.now(timezone.utc).timestamp() * 1000) - 30 * 24 * 3600 * 1000

    order = Order(
        id="ord_old_001",
        signal_id="sig_old",
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal('1.0'),
        filled_qty=Decimal('1.0'),
        average_exec_price=Decimal('45000'),
        status=OrderStatus.FILLED,
        created_at=old_time,
        updated_at=old_time,
        filled_at=old_time,
        reduce_only=False,
    )

    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    await repo.save_order(order)
    await repo.close()

    # Mock CCXT - 模拟历史 K 线
    timeframe_ms = 900000
    since = old_time - (20 * timeframe_ms)
    limit = 50

    mock_ohlcv = [
        [old_time + i * timeframe_ms, 44800 + i * 10, 44900 + i * 10, 44700 + i * 10, 44850 + i * 10, 100]
        for i in range(limit)
    ]

    repo_patch, ccxt_patch = setup_mocks(order, [order], mock_ohlcv)
    try:
        result = await get_order_klines(
            order_id=order.id,
            symbol="BTC/USDT:USDT",
            include_chain=True
        )
    finally:
        teardown_mocks(repo_patch, ccxt_patch)

    # 验证
    assert result is not None
    assert "klines" in result

    kline_timestamps = [k[0] for k in result["klines"]]
    assert old_time in kline_timestamps or \
           any(abs(ts - old_time) < 900000 for ts in kline_timestamps)
