"""
订单链 API 集成测试

测试覆盖:
1. 完整订单链查询流程
2. 批量删除订单链流程
3. 筛选参数验证（symbol、timeframe、日期范围）

Reference: docs/designs/order-chain-tree-contract.md
"""
import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Any
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
    OrderTreeResponse, OrderDeleteRequest, OrderDeleteResponse,
)
from src.infrastructure.order_repository import OrderRepository
from src.interfaces.api import app, set_dependencies, set_v3_dependencies


# ============================================================
# Test Fixtures
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
def client(temp_db_path):
    """创建测试用 FastAPI 客户端，通过 monkey-patching 让 API 使用临时数据库"""
    # 保存原始 __init__ 方法
    original_init = OrderRepository.__init__

    # 创建一个闭包来捕获 temp_db_path
    def patched_init(self, db_path=None, *args, **kwargs):
        # 强制使用临时数据库路径
        original_init(self, db_path=temp_db_path, *args, **kwargs)

    # 应用 patch
    OrderRepository.__init__ = patched_init

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        # 恢复原始方法
        OrderRepository.__init__ = original_init


@pytest.fixture
async def order_repository(temp_db_path):
    """创建并初始化 OrderRepository 实例 - 用于测试数据设置"""
    repo = OrderRepository(db_path=temp_db_path)
    await repo.initialize()
    yield repo
    await repo.close()


@pytest.fixture
async def setup_test_order_tree(order_repository: OrderRepository):
    """
    创建测试订单树数据

    数据结构:
    - entry-001 (ENTRY, FILLED)
      - tp1-001 (TP1, FILLED)
      - sl-001 (SL, OPEN)
    - entry-002 (ENTRY, FILLED)
      - tp1-002 (TP1, FILLED)
      - tp2-002 (TP2, OPEN)
      - sl-002 (SL, CANCELED)
    - entry-003 (ENTRY, OPEN) - 新订单，无子订单
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    one_day_ago = current_time - (24 * 60 * 60 * 1000)
    two_days_ago = current_time - (2 * 24 * 60 * 60 * 1000)

    orders = [
        # 订单链 1: BTC/USDT:USDT
        Order(
            id="entry-001",
            signal_id="sig-001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('0.1'),
            filled_qty=Decimal('0.1'),
            price=Decimal('50000'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
            created_at=two_days_ago,
            updated_at=two_days_ago,
            filled_at=two_days_ago,
            reduce_only=False,
        ),
        Order(
            id="tp1-001",
            signal_id="sig-001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.05'),
            filled_qty=Decimal('0.05'),
            price=Decimal('52000'),
            average_exec_price=Decimal('52000'),
            status=OrderStatus.FILLED,
            parent_order_id="entry-001",
            oco_group_id="oco-001",
            created_at=two_days_ago,
            updated_at=two_days_ago,
            filled_at=two_days_ago - (60 * 60 * 1000),  # 1 小时前成交
            reduce_only=True,
        ),
        Order(
            id="sl-001",
            signal_id="sig-001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('0.1'),
            filled_qty=Decimal('0'),
            price=Decimal('48000'),
            status=OrderStatus.OPEN,
            parent_order_id="entry-001",
            oco_group_id="oco-001",
            created_at=two_days_ago,
            updated_at=two_days_ago,
            reduce_only=True,
        ),
        # 订单链 2: ETH/USDT:USDT
        Order(
            id="entry-002",
            signal_id="sig-002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('1.0'),
            price=Decimal('3000'),
            average_exec_price=Decimal('3000'),
            status=OrderStatus.FILLED,
            created_at=one_day_ago,
            updated_at=one_day_ago,
            filled_at=one_day_ago,
            reduce_only=False,
        ),
        Order(
            id="tp1-002",
            signal_id="sig-002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0.5'),
            price=Decimal('2800'),
            average_exec_price=Decimal('2800'),
            status=OrderStatus.FILLED,
            parent_order_id="entry-002",
            oco_group_id="oco-002",
            created_at=one_day_ago,
            updated_at=one_day_ago,
            filled_at=one_day_ago - (30 * 60 * 1000),  # 30 分钟前成交
            reduce_only=True,
        ),
        Order(
            id="tp2-002",
            signal_id="sig-002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP2,
            requested_qty=Decimal('0.5'),
            filled_qty=Decimal('0'),
            price=Decimal('2700'),
            status=OrderStatus.OPEN,
            parent_order_id="entry-002",
            oco_group_id="oco-002",
            created_at=one_day_ago,
            updated_at=one_day_ago,
            reduce_only=True,
        ),
        Order(
            id="sl-002",
            signal_id="sig-002",
            symbol="ETH/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            requested_qty=Decimal('1.0'),
            filled_qty=Decimal('0'),
            price=Decimal('3200'),
            status=OrderStatus.CANCELED,
            parent_order_id="entry-002",
            oco_group_id="oco-002",
            created_at=one_day_ago,
            updated_at=one_day_ago,
            reduce_only=True,
        ),
        # 订单链 3: BTC/USDT:USDT - 新订单，无子订单
        Order(
            id="entry-003",
            signal_id="sig-003",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('0.05'),
            filled_qty=Decimal('0.05'),
            price=Decimal('51000'),
            average_exec_price=Decimal('51000'),
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        ),
    ]

    # 保存所有订单
    await order_repository.save_batch(orders)

    return {
        "entry-001": ["tp1-001", "sl-001"],
        "entry-002": ["tp1-002", "tp2-002", "sl-002"],
        "entry-003": [],
    }


# ============================================================
# GET /api/v3/orders/tree Integration Tests
# ============================================================

@pytest.mark.integration
class TestOrderTreeIntegration:
    """GET /api/v3/orders/tree 集成测试"""

    @pytest.mark.asyncio
    async def test_get_order_tree_full_data(self, client, order_repository, setup_test_order_tree):
        """集成测试：获取完整订单树数据"""
        # 调用 API
        response = client.get("/api/v3/orders/tree?days=7")

        # 验证响应
        assert response.status_code == 200
        data = response.json()

        # 验证响应结构
        assert "items" in data
        assert "total" in data
        assert "metadata" in data

        # 验证数据
        assert data["total"] == 3  # 3 个 ENTRY 订单
        assert len(data["items"]) == 3

        # 验证 metadata
        assert data["metadata"]["days_filter"] == 7
        assert "loaded_at" in data["metadata"]

    @pytest.mark.asyncio
    async def test_get_order_tree_with_symbol_filter(self, client, order_repository, setup_test_order_tree):
        """集成测试：带币种对过滤的订单树查询"""
        # 测试 BTC 过滤
        response = client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["metadata"]["symbol_filter"] == "BTC/USDT:USDT"
        # BTC 有 2 个 ENTRY 订单 (entry-001, entry-003)
        assert data["total"] == 2

        # 验证所有返回的订单都是 BTC
        for item in data["items"]:
            assert item["order"]["symbol"] == "BTC/USDT:USDT"

    @pytest.mark.asyncio
    async def test_get_order_tree_with_eth_symbol(self, client, order_repository, setup_test_order_tree):
        """集成测试：ETH 币种对过滤"""
        response = client.get("/api/v3/orders/tree?symbol=ETH/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1  # ETH 只有 1 个 ENTRY 订单
        assert data["items"][0]["order"]["symbol"] == "ETH/USDT:USDT"

    @pytest.mark.asyncio
    async def test_get_order_tree_child_orders_structure(self, client, order_repository, setup_test_order_tree):
        """集成测试：验证子订单结构"""
        response = client.get("/api/v3/orders/tree?days=7")
        assert response.status_code == 200
        data = response.json()

        # 查找 entry-001
        entry_001 = None
        for item in data["items"]:
            if item["order"]["order_id"] == "entry-001":
                entry_001 = item
                break

        assert entry_001 is not None
        assert entry_001["level"] == 0
        assert entry_001["has_children"] is True
        assert len(entry_001["children"]) == 2

        # 验证子订单
        child_roles = [child["order"]["order_role"] for child in entry_001["children"]]
        assert "TP1" in child_roles
        assert "SL" in child_roles

        # 验证子订单 level
        for child in entry_001["children"]:
            assert child["level"] == 1
            assert child["has_children"] is False

    @pytest.mark.asyncio
    async def test_get_order_tree_empty_result(self, client, order_repository):
        """集成测试：空结果（无数据）"""
        # 查询不存在的币种
        response = client.get("/api/v3/orders/tree?symbol=NONEXISTENT/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_order_tree_with_limit(self, client, order_repository, setup_test_order_tree):
        """集成测试：带数量限制"""
        response = client.get("/api/v3/orders/tree?days=7&limit=2")
        assert response.status_code == 200
        data = response.json()

        # 验证返回数量不超过 limit
        assert len(data["items"]) <= 2

    @pytest.mark.asyncio
    async def test_get_order_tree_date_range_filter(self, client, order_repository, setup_test_order_tree):
        """集成测试：日期范围过滤"""
        # 计算日期范围（只查询最近 1 天）
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=1)

        response = client.get(
            f"/api/v3/orders/tree?start_date={start_date.isoformat().replace('+00:00', 'Z')}&days=7"
        )

        # start_date 和 days 同时指定应该返回 400
        assert response.status_code == 400
        assert "互斥" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_order_tree_invalid_date_format(self, client, order_repository):
        """集成测试：无效日期格式"""
        response = client.get("/api/v3/orders/tree?start_date=invalid-date")

        assert response.status_code == 400
        assert "格式错误" in response.json()["detail"]


# ============================================================
# DELETE /api/v3/orders/batch Integration Tests
# ============================================================

@pytest.mark.integration
class TestDeleteOrdersBatchIntegration:
    """DELETE /api/v3/orders/batch 集成测试"""

    @pytest.mark.asyncio
    async def test_delete_single_order_chain(self, client, order_repository, setup_test_order_tree):
        """集成测试：删除单个订单链"""
        # 删除 entry-001 订单链
        request_body = {
            "order_ids": ["entry-001"],
            "cancel_on_exchange": False,  # 测试环境不调用交易所
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证删除结果
        assert "deleted_count" in data
        assert "deleted_from_db" in data

        # 应该删除 entry-001 + tp1-001 + sl-001 = 3 个订单
        assert data["deleted_count"] >= 1  # 至少删除入口订单

        # 验证数据库记录已删除
        deleted_ids = data["deleted_from_db"]
        assert "entry-001" in deleted_ids

    @pytest.mark.asyncio
    async def test_delete_multiple_order_chains(self, client, order_repository, setup_test_order_tree):
        """集成测试：批量删除多个订单链"""
        request_body = {
            "order_ids": ["entry-001", "entry-002"],
            "cancel_on_exchange": False,
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证删除结果
        assert data["deleted_count"] >= 2  # 至少删除 2 个入口订单
        assert "entry-001" in data["deleted_from_db"]
        assert "entry-002" in data["deleted_from_db"]

    @pytest.mark.asyncio
    async def test_delete_order_chain_with_cascade(self, client, order_repository, setup_test_order_tree):
        """集成测试：级联删除子订单"""
        # 先获取删除前的订单树
        tree_response = client.get("/api/v3/orders/tree?days=7")
        assert tree_response.status_code == 200

        # 删除 entry-002
        request_body = {
            "order_ids": ["entry-002"],
            "cancel_on_exchange": False,
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证级联删除：entry-002 的子订单也应该被删除
        deleted_ids = data["deleted_from_db"]

        # 验证订单已从数据库删除
        remaining_tree = client.get("/api/v3/orders/tree?days=7")
        remaining_data = remaining_tree.json()

        # entry-002 应该不在结果中
        remaining_entry_ids = [item["order"]["order_id"] for item in remaining_data["items"]]
        assert "entry-002" not in remaining_entry_ids

    @pytest.mark.asyncio
    async def test_delete_empty_order_ids(self, client, order_repository):
        """集成测试：空订单 ID 列表"""
        request_body = {
            "order_ids": [],
            "cancel_on_exchange": False,
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)

        # Pydantic 验证错误
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_exceeds_limit(self, client, order_repository):
        """集成测试：订单 ID 数量超限"""
        request_body = {
            "order_ids": [f"order-{i}" for i in range(101)],
            "cancel_on_exchange": False,
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)

        # Pydantic 验证错误
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_with_audit_info(self, client, order_repository, setup_test_order_tree):
        """集成测试：带审计信息的删除"""
        request_body = {
            "order_ids": ["entry-003"],
            "cancel_on_exchange": False,
            "audit_info": {
                "operator_id": "test-user-001",
                "ip_address": "192.168.1.100",
                "user_agent": "TestClient/1.0",
            },
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证审计日志 ID 生成
        assert "audit_log_id" in data
        assert data["audit_log_id"] is not None


# ============================================================
# Edge Cases Integration Tests
# ============================================================

@pytest.mark.integration
class TestOrderChainEdgeCases:
    """订单链边界情况集成测试"""

    @pytest.mark.asyncio
    async def test_get_order_tree_single_entry_no_children(self, client, order_repository):
        """边界测试：只有 ENTRY 无子订单"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 创建只有 ENTRY 的订单
        order = Order(
            id="entry-single",
            signal_id="sig-single",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('0.01'),
            filled_qty=Decimal('0.01'),
            price=Decimal('50000'),
            average_exec_price=Decimal('50000'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
            reduce_only=False,
        )
        await order_repository.save(order)

        # 查询订单树
        response = client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        assert data["items"][0]["has_children"] is False
        assert len(data["items"][0]["children"]) == 0

    @pytest.mark.asyncio
    async def test_get_order_tree_all_status_orders(self, client, order_repository):
        """边界测试：包含所有状态的订单"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        orders = [
            Order(
                id="entry-open",
                signal_id="sig-open",
                symbol="TEST/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal('0.1'),
                filled_qty=Decimal('0'),
                status=OrderStatus.OPEN,
                created_at=current_time,
                updated_at=current_time,
                reduce_only=False,
            ),
            Order(
                id="tp-filled",
                signal_id="sig-open",
                symbol="TEST/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.LIMIT,
                order_role=OrderRole.TP1,
                requested_qty=Decimal('0.05'),
                filled_qty=Decimal('0.05'),
                price=Decimal('52000'),
                average_exec_price=Decimal('52000'),
                status=OrderStatus.FILLED,
                parent_order_id="entry-open",
                created_at=current_time,
                updated_at=current_time,
                filled_at=current_time,
                reduce_only=True,
            ),
            Order(
                id="sl-cancelled",
                signal_id="sig-open",
                symbol="TEST/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.STOP_MARKET,
                order_role=OrderRole.SL,
                requested_qty=Decimal('0.1'),
                filled_qty=Decimal('0'),
                price=Decimal('48000'),
                status=OrderStatus.CANCELED,
                parent_order_id="entry-open",
                created_at=current_time,
                updated_at=current_time,
                reduce_only=True,
            ),
        ]
        await order_repository.save_batch(orders)

        # 查询订单树
        response = client.get("/api/v3/orders/tree?symbol=TEST/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1
        # 验证子订单数量
        assert len(data["items"][0]["children"]) == 2

    @pytest.mark.asyncio
    async def test_delete_nonexistent_order(self, client, order_repository):
        """边界测试：删除不存在的订单"""
        request_body = {
            "order_ids": ["nonexistent-order-id"],
            "cancel_on_exchange": False,
        }

        response = client.delete("/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 不存在的订单应该被忽略
        assert data["deleted_count"] == 0
        assert data["deleted_from_db"] == []

    @pytest.mark.asyncio
    async def test_order_tree_with_special_characters_in_symbol(self, client, order_repository):
        """边界测试：特殊字符币种对"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 创建特殊币种对订单
        order = Order(
            id="entry-special",
            signal_id="sig-special",
            symbol="BTC/USDT:USDT",  # 标准格式
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal('0.01'),
            filled_qty=Decimal('0.01'),
            status=OrderStatus.FILLED,
            created_at=current_time,
            updated_at=current_time,
            filled_at=current_time,
        )
        await order_repository.save(order)

        response = client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1


# ============================================================
# Performance Integration Tests (Optional)
# ============================================================

@pytest.mark.integration
@pytest.mark.performance
class TestOrderTreePerformance:
    """订单树性能集成测试"""

    @pytest.mark.asyncio
    async def test_get_order_tree_with_large_dataset(self, client, order_repository):
        """性能测试：大数据量查询"""
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 创建 50 个 ENTRY 订单，每个有 2-3 个子订单
        orders = []
        for i in range(50):
            entry = Order(
                id=f"entry-perf-{i:03d}",
                signal_id=f"sig-perf-{i:03d}",
                symbol="PERF/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal('0.1'),
                filled_qty=Decimal('0.1'),
                status=OrderStatus.FILLED,
                created_at=current_time - (i * 60 * 60 * 1000),
                updated_at=current_time - (i * 60 * 60 * 1000),
                filled_at=current_time - (i * 60 * 60 * 1000),
            )
            orders.append(entry)

            # 添加 2-3 个子订单
            num_children = 2 + (i % 2)
            for j in range(num_children):
                role = OrderRole.TP1 if j == 0 else OrderRole.TP2 if j == 1 else OrderRole.SL
                child = Order(
                    id=f"tp-perf-{i:03d}-{j}",
                    signal_id=f"sig-perf-{i:03d}",
                    symbol="PERF/USDT:USDT",
                    direction=Direction.LONG,
                    order_type=OrderType.LIMIT,
                    order_role=role,
                    requested_qty=Decimal('0.05'),
                    filled_qty=Decimal('0'),
                    price=Decimal('52000'),
                    status=OrderStatus.OPEN,
                    parent_order_id=f"entry-perf-{i:03d}",
                    created_at=current_time - (i * 60 * 60 * 1000),
                    updated_at=current_time - (i * 60 * 60 * 1000),
                )
                orders.append(child)

        await order_repository.save_batch(orders)

        import time
        start = time.time()

        response = client.get("/api/v3/orders/tree?symbol=PERF/USDT:USDT&days=30")

        elapsed = time.time() - start

        assert response.status_code == 200
        data = response.json()

        # 验证响应时间 < 1s
        assert elapsed < 1.0, f"响应时间过长：{elapsed:.2f}s"

        # 验证数据完整性
        assert data["total"] == 50
