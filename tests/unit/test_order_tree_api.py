"""
订单树 API 端点单元测试

测试覆盖:
1. GET /api/v3/orders/tree - 订单树查询端点
2. DELETE /api/v3/orders/batch - 批量删除端点

Reference: docs/designs/order-chain-tree-contract.md
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.domain.models import (
    OrderTreeResponse, OrderTreeNode, OrderDeleteRequest, OrderDeleteResponse,
    OrderStatus, OrderRole, OrderType, Direction,
)
from src.interfaces.api import app


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def client():
    """Create test FastAPI client"""
    return TestClient(app)


@pytest.fixture
def mock_order_repository():
    """Mock order repository"""
    repo = MagicMock()
    repo.initialize = AsyncMock()
    repo.close = AsyncMock()
    repo.get_order_tree = AsyncMock()
    repo.delete_orders_batch = AsyncMock()
    return repo


# ============================================================
# Sample Data Fixtures
# ============================================================

@pytest.fixture
def sample_order_tree_data():
    """样本订单树数据"""
    return {
        "items": [
            {
                "order": {
                    "order_id": "entry-001",
                    "symbol": "BTC/USDT:USDT",
                    "order_role": "ENTRY",
                    "status": "FILLED",
                    "direction": "LONG",
                    "quantity": "0.1",
                    "filled_qty": "0.1",
                    "price": "50000",
                    "average_exec_price": "50000",
                    "created_at": 1711785660000,
                    "filled_at": 1711785660000,
                    "order_type": "MARKET",
                    "remaining_qty": "0",
                    "reduce_only": False,
                    "signal_id": "sig-001",
                    "updated_at": 1711785660000,
                    "trigger_price": None,
                    "exchange_order_id": "binance-001",
                    "client_order_id": "binance-001",
                },
                "children": [
                    {
                        "order": {
                            "order_id": "tp1-001",
                            "parent_order_id": "entry-001",
                            "order_role": "TP1",
                            "status": "FILLED",
                            "direction": "LONG",
                            "quantity": "0.05",
                            "filled_qty": "0.05",
                            "price": "52000",
                            "average_exec_price": "52000",
                            "order_type": "LIMIT",
                            "remaining_qty": "0",
                            "reduce_only": True,
                            "signal_id": "sig-001",
                            "created_at": 1711785660000,
                            "updated_at": 1711785660000,
                            "filled_at": 1711785660000,
                            "trigger_price": None,
                            "exchange_order_id": "binance-tp1-001",
                            "client_order_id": "binance-tp1-001",
                        },
                        "children": [],
                        "level": 1,
                        "has_children": False,
                    },
                    {
                        "order": {
                            "order_id": "sl-001",
                            "parent_order_id": "entry-001",
                            "order_role": "SL",
                            "status": "OPEN",
                            "direction": "LONG",
                            "quantity": "0.1",
                            "filled_qty": "0",
                            "price": "48000",
                            "order_type": "STOP_MARKET",
                            "remaining_qty": "0.1",
                            "reduce_only": True,
                            "signal_id": "sig-001",
                            "created_at": 1711785660000,
                            "updated_at": 1711785660000,
                            "filled_at": None,
                            "trigger_price": None,
                            "exchange_order_id": "binance-sl-001",
                            "client_order_id": "binance-sl-001",
                        },
                        "children": [],
                        "level": 1,
                        "has_children": False,
                    },
                ],
                "level": 0,
                "has_children": True,
            },
        ],
        "total": 1,
        "metadata": {
            "symbol_filter": "BTC/USDT:USDT",
            "days_filter": 7,
            "loaded_at": 1711785660000,
        },
    }


@pytest.fixture
def sample_delete_result():
    """样本批量删除结果"""
    return {
        "deleted_count": 3,
        "cancelled_on_exchange": ["sl-001"],
        "failed_to_cancel": [],
        "deleted_from_db": ["entry-001", "tp1-001", "sl-001"],
        "failed_to_delete": [],
        "audit_log_id": "audit-20260402-001",
    }


# ============================================================
# GET /api/v3/orders/tree Tests
# ============================================================

class TestGetOrderTree:
    """GET /api/v3/orders/tree 端点测试"""

    @pytest.mark.asyncio
    async def test_get_order_tree_success(self, client, sample_order_tree_data):
        """测试：成功获取订单树"""
        # Mock OrderRepository class - patch in the module where it's used
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.initialize = AsyncMock()
            mock_repo_instance.close = AsyncMock()
            mock_repo_instance.get_order_tree = AsyncMock(return_value=sample_order_tree_data)
            MockRepo.return_value = mock_repo_instance
            MockRepo.return_value.__aenter__ = AsyncMock(return_value=mock_repo_instance)
            MockRepo.return_value.__aexit__ = AsyncMock(return_value=None)

            response = client.get("/api/v3/orders/tree")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "metadata" in data
        assert data["total"] == 1
        assert len(data["items"]) == 1

        # 验证根节点
        root_node = data["items"][0]
        assert root_node["level"] == 0
        assert root_node["has_children"] is True
        assert root_node["order"]["order_role"] == "ENTRY"

        # 验证子节点
        assert len(root_node["children"]) == 2
        assert root_node["children"][0]["order"]["order_role"] == "TP1"
        assert root_node["children"][1]["order"]["order_role"] == "SL"

    @pytest.mark.asyncio
    async def test_get_order_tree_with_symbol_filter(self, client, sample_order_tree_data):
        """测试：带币种对过滤的订单树查询"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.get_order_tree = AsyncMock(return_value=sample_order_tree_data)
            MockRepo.return_value = mock_repo

            response = client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT")

        assert response.status_code == 200
        # 验证 repository 被正确调用
        mock_repo.get_order_tree.assert_called_once()
        call_kwargs = mock_repo.get_order_tree.call_args.kwargs
        assert call_kwargs["symbol"] == "BTC/USDT:USDT"

    @pytest.mark.asyncio
    async def test_get_order_tree_with_days_filter(self, client, sample_order_tree_data):
        """测试：带天数过滤的订单树查询"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.get_order_tree = AsyncMock(return_value=sample_order_tree_data)
            MockRepo.return_value = mock_repo

            response = client.get("/api/v3/orders/tree?days=14")

        assert response.status_code == 200
        call_kwargs = mock_repo.get_order_tree.call_args.kwargs
        assert call_kwargs["days"] == 14

    @pytest.mark.asyncio
    async def test_get_order_tree_with_limit(self, client, sample_order_tree_data):
        """测试：带数量限制的订单树查询"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.get_order_tree = AsyncMock(return_value=sample_order_tree_data)
            MockRepo.return_value = mock_repo

            response = client.get("/api/v3/orders/tree?limit=50")

        assert response.status_code == 200
        call_kwargs = mock_repo.get_order_tree.call_args.kwargs
        assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_order_tree_invalid_start_date_format(self, client):
        """测试：无效的 start_date 格式返回 400"""
        response = client.get("/api/v3/orders/tree?start_date=invalid-date")

        assert response.status_code == 400
        assert "格式错误" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_order_tree_invalid_end_date_format(self, client):
        """测试：无效的 end_date 格式返回 400"""
        response = client.get("/api/v3/orders/tree?end_date=invalid-date")

        assert response.status_code == 400
        assert "格式错误" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_order_tree_start_date_and_days_conflict(self, client):
        """测试：start_date 和 days 同时指定返回 400"""
        response = client.get("/api/v3/orders/tree?start_date=2026-04-01&days=7")

        assert response.status_code == 400
        assert "互斥" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_order_tree_empty_result(self, client):
        """测试：空结果返回"""
        empty_result = {
            "items": [],
            "total": 0,
            "metadata": {
                "symbol_filter": None,
                "days_filter": 7,
                "loaded_at": 1711785660000,
            },
        }

        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.get_order_tree = AsyncMock(return_value=empty_result)
            MockRepo.return_value = mock_repo

            response = client.get("/api/v3/orders/tree")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_order_tree_repository_error(self, client):
        """测试：Repository 错误返回 500"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.get_order_tree = AsyncMock(side_effect=Exception("Database error"))
            MockRepo.return_value = mock_repo

            response = client.get("/api/v3/orders/tree")

        assert response.status_code == 500


# ============================================================
# DELETE /api/v3/orders/batch Tests
# ============================================================

class TestDeleteOrdersBatch:
    """DELETE /api/v3/orders/batch 端点测试"""

    @pytest.mark.asyncio
    async def test_delete_orders_batch_success(self, client, sample_delete_result):
        """测试：成功批量删除订单"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.delete_orders_batch = AsyncMock(return_value=sample_delete_result)
            MockRepo.return_value = mock_repo

            request_body = {
                "order_ids": ["entry-001"],
                "cancel_on_exchange": True,
                "audit_info": {
                    "operator_id": "user-001",
                    "ip_address": "192.168.1.1",
                },
            }

            response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 200
        data = response.json()

        assert "deleted_count" in data
        assert "cancelled_on_exchange" in data
        assert "deleted_from_db" in data
        assert "audit_log_id" in data

        assert data["deleted_count"] == 3
        assert len(data["cancelled_on_exchange"]) == 1
        assert len(data["deleted_from_db"]) == 3

    @pytest.mark.asyncio
    async def test_delete_orders_batch_without_cancel_on_exchange(self, client, sample_delete_result):
        """测试：不调用交易所取消的批量删除"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.delete_orders_batch = AsyncMock(return_value=sample_delete_result)
            MockRepo.return_value = mock_repo

            request_body = {
                "order_ids": ["entry-001"],
                "cancel_on_exchange": False,
            }

            response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 200
        # 验证 cancel_on_exchange 参数传递
        call_kwargs = mock_repo.delete_orders_batch.call_args.kwargs
        assert call_kwargs["cancel_on_exchange"] is False

    @pytest.mark.asyncio
    async def test_delete_orders_batch_empty_order_ids(self, client):
        """测试：空订单 ID 列表返回 422"""
        request_body = {
            "order_ids": [],
        }

        response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 422  # Pydantic 验证错误

    @pytest.mark.asyncio
    async def test_delete_orders_batch_exceeds_limit(self, client):
        """测试：订单 ID 数量超限返回 422"""
        request_body = {
            "order_ids": [f"order-{i}" for i in range(101)],  # 101 个订单 ID
        }

        response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 422  # Pydantic 验证错误

    @pytest.mark.asyncio
    async def test_delete_orders_batch_partial_failure(self, client):
        """测试：部分订单删除失败"""
        partial_result = {
            "deleted_count": 2,
            "cancelled_on_exchange": ["sl-001"],
            "failed_to_cancel": [
                {"order_id": "tp1-001", "reason": "交易所 API 超时"}
            ],
            "deleted_from_db": ["entry-001", "tp1-001", "sl-001"],
            "failed_to_delete": [],
            "audit_log_id": "audit-20260402-002",
        }

        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.delete_orders_batch = AsyncMock(return_value=partial_result)
            MockRepo.return_value = mock_repo

            request_body = {
                "order_ids": ["entry-001"],
                "cancel_on_exchange": True,
            }

            response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 200
        data = response.json()
        assert len(data["failed_to_cancel"]) == 1
        assert data["failed_to_cancel"][0]["reason"] == "交易所 API 超时"

    @pytest.mark.asyncio
    async def test_delete_orders_batch_repository_error(self, client):
        """测试：Repository 错误返回 500"""
        with patch('src.interfaces.api.OrderRepository') as MockRepo:
            mock_repo = MagicMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.close = AsyncMock()
            mock_repo.delete_orders_batch = AsyncMock(side_effect=Exception("Database error"))
            MockRepo.return_value = mock_repo

            request_body = {
                "order_ids": ["entry-001"],
            }

            response = client.request("DELETE", "/api/v3/orders/batch", json=request_body)

        assert response.status_code == 500


# ============================================================
# Pydantic Model Tests
# ============================================================

class TestOrderTreeResponseModel:
    """OrderTreeResponse 模型测试"""

    def test_order_tree_response_creation(self, sample_order_tree_data):
        """测试：创建 OrderTreeResponse 模型"""
        from pydantic import TypeAdapter
        from typing import List

        items_adapter = TypeAdapter(List[OrderTreeNode])
        items = items_adapter.validate_python(sample_order_tree_data["items"])

        response = OrderTreeResponse(
            items=items,
            total=sample_order_tree_data["total"],
            metadata=sample_order_tree_data["metadata"],
        )

        assert response.total == 1
        assert len(response.items) == 1
        assert response.items[0].level == 0
        assert response.items[0].has_children is True

    def test_order_tree_node_validation(self):
        """测试：OrderTreeNode 模型验证"""
        node = OrderTreeNode(
            order={"order_id": "test-001", "symbol": "BTC/USDT:USDT"},
            children=[],
            level=0,
            has_children=False,
        )

        assert node.level == 0
        assert node.has_children is False
        assert len(node.children) == 0


class TestOrderDeleteRequestModel:
    """OrderDeleteRequest 模型测试"""

    def test_delete_request_creation(self):
        """测试：创建 OrderDeleteRequest 模型"""
        request = OrderDeleteRequest(
            order_ids=["order-001", "order-002"],
            cancel_on_exchange=True,
            audit_info={"operator_id": "user-001"},
        )

        assert len(request.order_ids) == 2
        assert request.cancel_on_exchange is True

    def test_delete_request_empty_order_ids_validation(self):
        """测试：空订单 ID 列表验证"""
        with pytest.raises(ValueError, match="订单 ID 列表不能为空"):
            OrderDeleteRequest(order_ids=[])

    def test_delete_request_exceeds_limit_validation(self):
        """测试：订单 ID 数量超限验证"""
        with pytest.raises(Exception):  # Pydantic 验证错误
            OrderDeleteRequest(order_ids=[f"order-{i}" for i in range(101)])

    def test_delete_request_default_values(self):
        """测试：默认值"""
        request = OrderDeleteRequest(order_ids=["order-001"])

        assert request.cancel_on_exchange is True
        assert request.audit_info is None


class TestOrderDeleteResponseModel:
    """OrderDeleteResponse 模型测试"""

    def test_delete_response_creation(self, sample_delete_result):
        """测试：创建 OrderDeleteResponse 模型"""
        response = OrderDeleteResponse(
            deleted_count=sample_delete_result["deleted_count"],
            cancelled_on_exchange=sample_delete_result["cancelled_on_exchange"],
            failed_to_cancel=sample_delete_result["failed_to_cancel"],
            deleted_from_db=sample_delete_result["deleted_from_db"],
            failed_to_delete=sample_delete_result["failed_to_delete"],
            audit_log_id=sample_delete_result["audit_log_id"],
        )

        assert response.deleted_count == 3
        assert len(response.cancelled_on_exchange) == 1
        assert len(response.deleted_from_db) == 3


# ============================================================
# Integration Tests (if needed)
# ============================================================

@pytest.mark.integration
class TestOrderTreeIntegration:
    """订单树 API 集成测试（需要真实数据库）"""

    @pytest.mark.skip(reason="需要真实数据库和测试数据")
    async def test_get_order_tree_integration(self, client, test_db):
        """集成测试：获取订单树（需要真实数据库）"""
        # TODO: 实现集成测试
        # 1. 创建测试订单数据
        # 2. 调用 API 获取订单树
        # 3. 验证返回结果
        pass

    @pytest.mark.skip(reason="需要真实数据库和交易所模拟")
    async def test_delete_orders_batch_integration(self, client, test_db):
        """集成测试：批量删除订单（需要真实数据库）"""
        # TODO: 实现集成测试
        # 1. 创建测试订单数据
        # 2. 调用 API 批量删除
        # 3. 验证数据库记录已删除
        pass
