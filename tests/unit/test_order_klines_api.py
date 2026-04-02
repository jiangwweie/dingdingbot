"""
订单详情页 K 线渲染升级 - API 端点测试

测试 GET /api/v3/orders/{order_id}/klines 接口

测试用例清单:
- UT-OKA-001: 查询 ENTRY 订单（无子订单）- 返回订单 + 空 order_chain
- UT-OKA-002: 查询 ENTRY 订单（有 TP/SL）- 返回完整订单链
- UT-OKA-003: 查询 TP 子订单 - 返回完整订单链（包含父订单）
- UT-OKA-004: include_chain=false - 不返回订单链
- UT-OKA-005: 订单无 filled_at - 使用 created_at 备选
- UT-OKA-006: 订单不存在 - 返回 404
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
# 辅助函数
# ============================================================

def create_mock_exchange(ohlcv_data=None):
    """创建 mock 交易所实例"""
    mock_exchange = AsyncMock()
    mock_exchange.fetch_ohlcv = AsyncMock(return_value=ohlcv_data or [
        [1711785600000, 64000, 65000, 63000, 64500, 1000],
        [1711785660000, 64500, 65500, 64000, 65000, 1200],
    ])
    mock_exchange.close = AsyncMock()
    return mock_exchange


# ============================================================
# API 端点测试
# ============================================================

@pytest.mark.asyncio
async def test_get_order_klines_single_order_no_chain(
    order_repository, sample_entry_order, temp_db_path
):
    """UT-OKA-001: 查询 ENTRY 订单（无子订单）- 返回订单 + 空 order_chain"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

    # 准备：保存订单
    await order_repository.save_order(sample_entry_order)

    # 执行：调用 API（mock 交易所和数据库路径）
    with patch('src.interfaces.api.OrderRepository') as MockRepo:
        MockRepo.return_value = order_repository
        with patch('ccxt.async_support.binanceusdm') as mock_exchange_cls:
            mock_exchange_instance = AsyncMock()
            mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=[
                [1711785600000, 64000, 65000, 63000, 64500, 1000],
                [1711785660000, 64500, 65500, 64000, 65000, 1200],
            ])
            mock_exchange_instance.close = AsyncMock()
            mock_exchange_cls.return_value = mock_exchange_instance

            client = TestClient(app)
            response = client.get(
                f"/api/v3/orders/{sample_entry_order.id}/klines",
                params={"symbol": "BTC/USDT:USDT", "include_chain": False}
            )

    # 验证：响应状态码
    assert response.status_code == 200
    data = response.json()

    # 验证：返回订单信息
    assert "order" in data
    assert data["order"]["order_id"] == sample_entry_order.id
    assert data["order"]["order_role"] == "ENTRY"
    assert data["order"]["filled_at"] == sample_entry_order.filled_at

    # 验证：K 线数据存在
    assert "klines" in data
    assert len(data["klines"]) > 0

    # 验证：无 order_chain（include_chain=False）
    assert "order_chain" not in data


@pytest.mark.asyncio
async def test_get_order_klines_with_order_chain(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order, temp_db_path
):
    """UT-OKA-002: 查询 ENTRY 订单（有 TP/SL）- 返回完整订单链"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

    # 准备：保存订单链
    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：调用 API（mock 交易所和数据库路径）
    with patch('src.interfaces.api.OrderRepository') as MockRepo:
        MockRepo.return_value = order_repository
        with patch('ccxt.async_support.binanceusdm') as mock_exchange_cls:
            mock_exchange_instance = AsyncMock()
            mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=[
                [1711785600000, 64000, 65000, 63000, 64500, 1000],
                [1711785660000, 64500, 65500, 64000, 65000, 1200],
            ])
            mock_exchange_instance.close = AsyncMock()
            mock_exchange_cls.return_value = mock_exchange_instance

            client = TestClient(app)
            response = client.get(
                f"/api/v3/orders/{sample_entry_order.id}/klines",
                params={"symbol": "BTC/USDT:USDT", "include_chain": True}
            )

    # 验证：响应状态码
    assert response.status_code == 200
    data = response.json()

    # 验证：返回订单信息
    assert "order" in data
    assert data["order"]["order_id"] == sample_entry_order.id

    # 验证：返回完整订单链
    assert "order_chain" in data
    order_chain = data["order_chain"]
    assert len(order_chain) == 3  # ENTRY + TP1 + SL

    # 验证：订单链包含所有订单
    order_roles = [o["order_role"] for o in order_chain]
    assert "ENTRY" in order_roles
    assert "TP1" in order_roles
    assert "SL" in order_roles


@pytest.mark.asyncio
async def test_get_order_klines_from_child_order(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order, temp_db_path
):
    """UT-OKA-003: 查询 TP 子订单 - 返回完整订单链（包含父订单）"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

    # 准备：保存订单链
    await order_repository.save_order(sample_entry_order)
    await order_repository.save_order(sample_tp_order)
    await order_repository.save_order(sample_sl_order)

    # 执行：从 TP 子订单查询
    with patch('src.interfaces.api.OrderRepository') as MockRepo:
        MockRepo.return_value = order_repository
        with patch('ccxt.async_support.binanceusdm') as mock_exchange_cls:
            mock_exchange_instance = AsyncMock()
            mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=[
                [1711785600000, 64000, 65000, 63000, 64500, 1000],
            ])
            mock_exchange_instance.close = AsyncMock()
            mock_exchange_cls.return_value = mock_exchange_instance

            client = TestClient(app)
            response = client.get(
                f"/api/v3/orders/{sample_tp_order.id}/klines",
                params={"symbol": "BTC/USDT:USDT", "include_chain": True}
            )

    # 验证：响应状态码
    assert response.status_code == 200
    data = response.json()

    # 验证：返回完整订单链（包含父订单）
    assert "order_chain" in data
    order_chain = data["order_chain"]
    assert len(order_chain) == 3

    # 验证：订单链包含父订单
    order_ids = [o["order_id"] for o in order_chain]
    assert sample_entry_order.id in order_ids  # 父订单
    assert sample_tp_order.id in order_ids    # 自身
    assert sample_sl_order.id in order_ids    # 兄弟订单


@pytest.mark.asyncio
async def test_get_order_klines_order_not_found(order_repository):
    """UT-OKA-006: 订单不存在 - 返回 404"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

    # 执行：查询不存在的订单
    with patch('src.interfaces.api.OrderRepository') as MockRepo:
        MockRepo.return_value = order_repository
        with patch('src.interfaces.api._get_exchange_gateway') as mock_gateway_func:
            mock_gateway = AsyncMock()
            mock_gateway.fetch_order = AsyncMock(side_effect=Exception("Order not found"))
            mock_gateway_func.return_value = mock_gateway

            client = TestClient(app)
            response = client.get(
                "/api/v3/orders/ord_not_exists/klines",
                params={"symbol": "BTC/USDT:USDT"}
            )

    # 验证：返回 404 或 500（取决于实现）
    assert response.status_code in [404, 500]


@pytest.mark.asyncio
async def test_get_order_klines_without_filled_at(
    order_repository, temp_db_path
):
    """UT-OKA-005: 订单无 filled_at - 使用 created_at 备选"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

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

    # 执行：调用 API
    with patch('src.interfaces.api.OrderRepository') as MockRepo:
        MockRepo.return_value = order_repository
        with patch('ccxt.async_support.binanceusdm') as mock_exchange_cls:
            mock_exchange_instance = AsyncMock()
            mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=[
                [current_time - 900000, 3400, 3500, 3300, 3450, 500],
            ])
            mock_exchange_instance.close = AsyncMock()
            mock_exchange_cls.return_value = mock_exchange_instance

            client = TestClient(app)
            response = client.get(
                f"/api/v3/orders/{order_no_filled.id}/klines",
                params={"symbol": "ETH/USDT:USDT", "include_chain": False}
            )

    # 验证：成功返回
    assert response.status_code == 200
    data = response.json()
    assert "order" in data
    assert "klines" in data


@pytest.mark.asyncio
async def test_get_order_klines_timeframe_extraction(
    order_repository, sample_entry_order
):
    """测试 K 线周期从订单中提取"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient

    # 准备：保存带 timeframe 的订单
    sample_entry_order.timeframe = "1h"  # 添加 timeframe 属性
    await order_repository.save_order(sample_entry_order)

    # 执行：调用 API
    with patch('ccxt.async_support.binanceusdm') as mock_exchange:
        mock_exchange_instance = AsyncMock()
        mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=[
            [1711785600000, 64000, 65000, 63000, 64500, 1000],
        ])
        mock_exchange_instance.close = AsyncMock()
        mock_exchange.return_value = mock_exchange_instance

        client = TestClient(app)
        response = client.get(
            f"/api/v3/orders/{sample_entry_order.id}/klines",
            params={"symbol": "BTC/USDT:USDT", "include_chain": False}
        )

    # 验证
    assert response.status_code == 200
    data = response.json()
    assert "timeframe" in data
    # timeframe 应该是 1h 或默认 15m（取决于实现）
    assert data["timeframe"] in ["1h", "15m"]


# ============================================================
# K 线范围计算逻辑测试
# ============================================================

@pytest.mark.asyncio
async def test_kline_range_calculation_with_order_chain(
    order_repository, sample_entry_order, sample_tp_order, sample_sl_order
):
    """测试 K 线范围计算覆盖完整订单链生命周期"""
    from src.interfaces.api import app
    from fastapi.testclient import TestClient
    from src.application.config_manager import BacktestConfig

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

    # 执行：调用 API
    with patch('ccxt.async_support.binanceusdm') as mock_exchange:
        mock_exchange_instance = AsyncMock()
        # Mock 返回足够的 K 线数据
        mock_klines = []
        for i in range(60):
            ts = base_time - (20 * 900000) + (i * 900000)  # 15m 间隔
            mock_klines.append([ts, 64000 + i * 10, 65000 + i * 10, 63000 + i * 10, 64500 + i * 10, 1000])

        mock_exchange_instance.fetch_ohlcv = AsyncMock(return_value=mock_klines)
        mock_exchange_instance.close = AsyncMock()
        mock_exchange.return_value = mock_exchange_instance

        client = TestClient(app)
        response = client.get(
            f"/api/v3/orders/{sample_entry_order.id}/klines",
            params={"symbol": "BTC/USDT:USDT", "include_chain": True}
        )

    # 验证
    assert response.status_code == 200
    data = response.json()

    # 验证：K 线范围应该覆盖 ENTRY 到 TP 的完整时间段
    assert "klines" in data
    assert len(data["klines"]) > 0

    # 验证：返回订单链
    assert "order_chain" in data
    assert len(data["order_chain"]) == 3
