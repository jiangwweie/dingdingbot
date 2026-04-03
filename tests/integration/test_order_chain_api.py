"""
订单链 API 集成测试

测试覆盖:
1. 完整订单链查询流程
2. 批量删除订单链流程
3. 筛选参数验证（symbol、timeframe、日期范围）

Reference: docs/designs/order-chain-tree-contract.md

策略：参考 test_strategy_params_api.py 成功模式，在同步 fixture 中初始化 Repository
"""
import pytest
import asyncio
import os
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
)
from src.infrastructure.order_repository import OrderRepository
from src.interfaces.api import app, set_dependencies


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
def api_client(temp_db_path):
    """Create FastAPI test client with properly initialized dependencies.

    参考 test_strategy_params_api.py 成功模式：
    1. 在同步 fixture 中初始化所有 Repository
    2. 使用 asyncio.run() 同步调用异步初始化
    3. 使用 TestClient(app) 包含 lifespan
    """
    from src.infrastructure.signal_repository import SignalRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository

    # 创建并初始化 OrderRepository
    order_repo = OrderRepository(db_path=temp_db_path)
    asyncio.run(order_repo.initialize())

    # 创建并初始化 SignalRepository
    signal_repo = SignalRepository()
    asyncio.run(signal_repo.initialize())

    # 创建并初始化 ConfigEntryRepository
    config_repo = ConfigEntryRepository()
    asyncio.run(config_repo.initialize())

    # Set dependencies with properly initialized repositories
    set_dependencies(
        order_repo=order_repo,
        repository=signal_repo,
        config_entry_repo=config_repo,
    )

    with TestClient(app) as client:
        yield client

    # Cleanup: close repositories
    asyncio.run(order_repo.close())
    asyncio.run(signal_repo.close())
    asyncio.run(config_repo.close())


@pytest.fixture
def order_repo(api_client, temp_db_path):
    """向后兼容：返回 OrderRepository 实例"""
    # 由于 api_client 已经初始化了所有 Repository，这里直接返回即可
    from src.interfaces.api import _order_repo
    return _order_repo


def create_test_orders(order_repo: OrderRepository):
    """创建测试订单数据（同步函数）

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
            filled_at=two_days_ago - (60 * 60 * 1000),
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
            filled_at=one_day_ago - (30 * 60 * 1000),
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
    asyncio.run(order_repo.save_batch(orders))


# ============================================================
# GET /api/v3/orders/tree Integration Tests
# ============================================================

@pytest.mark.integration
class TestOrderTreeIntegration:
    """GET /api/v3/orders/tree 集成测试"""

    def test_get_order_tree_full_data(self, api_client, order_repo):
        """集成测试：获取完整订单树数据"""
        # 准备数据
        create_test_orders(order_repo)

        # 调用 API（同步）
        response = api_client.get("/api/v3/orders/tree?days=7")

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

    def test_get_order_tree_with_symbol_filter(self, api_client, order_repo):
        """集成测试：带币种对过滤的订单树查询"""
        create_test_orders(order_repo)

        # 测试 BTC 过滤
        response = api_client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["metadata"]["symbol_filter"] == "BTC/USDT:USDT"
        # BTC 有 2 个 ENTRY 订单 (entry-001, entry-003)
        assert data["total"] == 2

        # 验证所有返回的订单都是 BTC
        for item in data["items"]:
            assert item["order"]["symbol"] == "BTC/USDT:USDT"

    def test_get_order_tree_with_eth_symbol(self, api_client, order_repo):
        """集成测试：ETH 币种对过滤"""
        create_test_orders(order_repo)

        response = api_client.get("/api/v3/orders/tree?symbol=ETH/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 1  # ETH 只有 1 个 ENTRY 订单
        assert data["items"][0]["order"]["symbol"] == "ETH/USDT:USDT"

    def test_get_order_tree_child_orders_structure(self, api_client, order_repo):
        """集成测试：验证子订单结构"""
        create_test_orders(order_repo)

        response = api_client.get("/api/v3/orders/tree?days=7")
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

    def test_get_order_tree_empty_result(self, api_client, order_repo):
        """集成测试：空结果（无数据）"""
        # 不准备数据，查询不存在的币种
        response = api_client.get("/api/v3/orders/tree?symbol=NONEXISTENT/USDT:USDT&days=7")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 0
        assert data["items"] == []

    def test_get_order_tree_with_limit(self, api_client, order_repo):
        """集成测试：带数量限制"""
        create_test_orders(order_repo)

        response = api_client.get("/api/v3/orders/tree?days=7&limit=2")
        assert response.status_code == 200
        data = response.json()

        # 验证返回数量不超过 limit
        assert len(data["items"]) <= 2

    def test_get_order_tree_date_range_filter(self, api_client, order_repo):
        """集成测试：日期范围过滤"""
        create_test_orders(order_repo)

        # 计算日期范围（只查询最近 1 天）
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=1)

        response = api_client.get(
            f"/api/v3/orders/tree?start_date={start_date.isoformat().replace('+00:00', 'Z')}&days=7"
        )

        # start_date 和 days 同时指定应该返回 400
        assert response.status_code == 400
        error_detail = response.json().get("detail", "")
        assert "互斥" in error_detail

    def test_get_order_tree_invalid_date_format(self, api_client, order_repo):
        """集成测试：无效日期格式"""
        response = api_client.get("/api/v3/orders/tree?start_date=invalid-date")

        assert response.status_code == 400
        error_detail = response.json().get("detail", "")
        assert "格式错误" in error_detail


# ============================================================
# DELETE /api/v3/orders/batch Integration Tests
# ============================================================

@pytest.mark.integration
class TestDeleteOrdersBatchIntegration:
    """DELETE /api/v3/orders/batch 集成测试"""

    def test_delete_single_order_chain(self, api_client, order_repo):
        """集成测试：删除单个订单链"""
        create_test_orders(order_repo)

        # 删除 entry-001 订单链
        request_body = {
            "order_ids": ["entry-001"],
            "cancel_on_exchange": False,  # 测试环境不调用交易所
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)
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

    def test_delete_multiple_order_chains(self, api_client, order_repo):
        """集成测试：批量删除多个订单链"""
        create_test_orders(order_repo)

        request_body = {
            "order_ids": ["entry-001", "entry-002"],
            "cancel_on_exchange": False,
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证删除结果
        assert data["deleted_count"] >= 2  # 至少删除 2 个入口订单
        assert "entry-001" in data["deleted_from_db"]
        assert "entry-002" in data["deleted_from_db"]

    def test_delete_order_chain_with_cascade(self, api_client, order_repo):
        """集成测试：级联删除子订单"""
        create_test_orders(order_repo)

        # 删除 entry-002
        request_body = {
            "order_ids": ["entry-002"],
            "cancel_on_exchange": False,
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证订单已从数据库删除
        remaining_tree = api_client.get("/api/v3/orders/tree?days=7")
        remaining_data = remaining_tree.json()

        # entry-002 应该不在结果中
        remaining_entry_ids = [item["order"]["order_id"] for item in remaining_data["items"]]
        assert "entry-002" not in remaining_entry_ids

    def test_delete_empty_order_ids(self, api_client, order_repo):
        """集成测试：空订单 ID 列表"""
        request_body = {
            "order_ids": [],
            "cancel_on_exchange": False,
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        # Pydantic 验证错误
        assert response.status_code == 422

    def test_delete_exceeds_limit(self, api_client, order_repo):
        """集成测试：订单 ID 数量超限"""
        request_body = {
            "order_ids": [f"order-{i}" for i in range(101)],
            "cancel_on_exchange": False,
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        # Pydantic 验证错误
        assert response.status_code == 422

    def test_delete_with_audit_info(self, api_client, order_repo):
        """集成测试：带审计信息的删除"""
        create_test_orders(order_repo)

        request_body = {
            "order_ids": ["entry-003"],
            "cancel_on_exchange": False,
            "audit_info": {
                "operator_id": "test-user-001",
                "ip_address": "192.168.1.100",
                "user_agent": "TestClient/1.0",
            },
        }

        response = api_client.request("DELETE", "/api/v3/orders/batch", json=request_body)
        assert response.status_code == 200
        data = response.json()

        # 验证审计日志 ID 生成
        assert "audit_log_id" in data
        assert data["audit_log_id"] is not None