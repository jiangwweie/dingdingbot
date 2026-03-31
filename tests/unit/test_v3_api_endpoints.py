"""
Test Phase 6 v3 REST API Endpoints

Tests for:
- POST /api/v3/orders - Create order
- DELETE /api/v3/orders/{order_id} - Cancel order
- GET /api/v3/orders/{order_id} - Get order details
- GET /api/v3/orders - List orders
- GET /api/v3/positions - List positions
- GET /api/v3/positions/{position_id} - Get position details
- GET /api/v3/account/balance - Get account balance
- GET /api/v3/account/snapshot - Get account snapshot
- POST /api/v3/reconciliation - Start reconciliation

Reference: docs/designs/phase5-contract.md
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.domain.models import (
    OrderRequest, OrderResponseFull, OrderCancelResponse,
    PositionInfoV3, PositionResponse,
    AccountBalance, AccountResponse,
    ReconciliationRequest, ReconciliationReport,
    OrderType, OrderStatus, OrderRole, Direction,
    OrderPlacementResult, OrderCancelResult,
    AccountSnapshot, PositionInfo,
)
from src.domain.exceptions import OrderNotFoundError, OrderAlreadyFilledError
from src.interfaces.api import app, set_dependencies, set_v3_dependencies


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def client():
    """Create test FastAPI client"""
    return TestClient(app)


@pytest.fixture
def mock_repository():
    """Mock signal repository"""
    repo = MagicMock()
    repo.get_signals = AsyncMock(return_value={"total": 0, "data": []})
    repo.close = AsyncMock()
    return repo


@pytest.fixture
def mock_account_getter():
    """Mock account getter function"""
    def getter():
        return AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("9000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
    return getter


@pytest.fixture
def mock_exchange_gateway():
    """Mock exchange gateway"""
    gateway = MagicMock()
    gateway.exchange_name = "binance"
    gateway.place_order = AsyncMock()
    gateway.cancel_order = AsyncMock()
    gateway.fetch_order = AsyncMock()
    gateway.fetch_positions = AsyncMock(return_value=[])
    gateway.fetch_account_balance = AsyncMock()
    return gateway


@pytest.fixture
def mock_capital_protection():
    """Mock capital protection manager"""
    protection = MagicMock()
    protection.pre_order_check = AsyncMock(return_value=MagicMock(
        allowed=True,
        reason=None,
        reason_message=None,
    ))
    return protection


@pytest.fixture
def sample_order_request():
    """Sample order request for testing"""
    return OrderRequest(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        direction=Direction.LONG,
        role=OrderRole.ENTRY,
        amount=Decimal("0.001"),
        price=None,
        trigger_price=None,
        reduce_only=False,
        client_order_id=None,
        strategy_name="test_strategy",
        stop_loss=Decimal("40000"),
        take_profit=Decimal("50000"),
    )


# ============================================================
# Order Management Tests
# ============================================================
class TestCreateOrder:
    """Test POST /api/v3/orders"""

    def test_create_order_market_long_entry(
        self, client, mock_repository, mock_account_getter,
        mock_exchange_gateway, mock_capital_protection
    ):
        """Test creating a MARKET LONG ENTRY order"""
        # Setup dependencies
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )
        set_v3_dependencies(capital_protection=mock_capital_protection)

        # Mock place_order response
        mock_exchange_gateway.place_order.return_value = OrderPlacementResult(
            order_id="order_123",
            exchange_order_id="binance_456",
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            direction=Direction.LONG,
            side="buy",
            amount=Decimal("0.001"),
            status=OrderStatus.OPEN,
        )

        # Make request
        response = client.post("/api/v3/orders", json={
            "symbol": "BTC/USDT:USDT",
            "order_type": "MARKET",
            "direction": "LONG",
            "role": "ENTRY",
            "amount": "0.001",
            "reduce_only": False,
            "strategy_name": "test_strategy",
            "stop_loss": "40000",
            "take_profit": "50000",
        })

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "order_123"
        assert data["exchange_order_id"] == "binance_456"
        assert data["symbol"] == "BTC/USDT:USDT"
        assert data["order_type"] == "MARKET"
        assert data["direction"] == "LONG"
        assert data["role"] == "ENTRY"
        assert data["status"] == "OPEN"
        assert data["amount"] == "0.001"

    def test_create_order_limit_requires_price(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test that LIMIT order requires price parameter"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Make request without price
        response = client.post("/api/v3/orders", json={
            "symbol": "BTC/USDT:USDT",
            "order_type": "LIMIT",
            "direction": "LONG",
            "role": "ENTRY",
            "amount": "0.001",
            "reduce_only": False,
        })

        # Should fail validation
        assert response.status_code == 400
        data = response.json()
        assert "F-011" in str(data) or "price" in str(data).lower()

    def test_create_order_stop_market_requires_trigger_price(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test that STOP_MARKET order requires trigger_price parameter"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Make request without trigger_price
        response = client.post("/api/v3/orders", json={
            "symbol": "BTC/USDT:USDT",
            "order_type": "STOP_MARKET",
            "direction": "LONG",
            "role": "ENTRY",
            "amount": "0.001",
            "trigger_price": None,
            "reduce_only": False,
        })

        # Should fail validation
        assert response.status_code == 400

    def test_create_order_tp_sl_must_be_reduce_only(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test that TP/SL orders must have reduce_only=True"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Make request with TP1 role but reduce_only=False
        response = client.post("/api/v3/orders", json={
            "symbol": "BTC/USDT:USDT",
            "order_type": "LIMIT",
            "direction": "LONG",
            "role": "TP1",
            "amount": "0.001",
            "price": "45000",
            "reduce_only": False,  # Should be True for TP/SL
        })

        # Should fail validation
        assert response.status_code == 400

    def test_create_order_capital_protection_rejects(
        self, client, mock_repository, mock_account_getter,
        mock_exchange_gateway, mock_capital_protection
    ):
        """Test order rejection by capital protection"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )
        set_v3_dependencies(capital_protection=mock_capital_protection)

        # Mock capital protection to reject
        mock_capital_protection.pre_order_check.return_value = MagicMock(
            allowed=False,
            reason="SINGLE_TRADE_LOSS_LIMIT",
            reason_message="单笔交易损失超限",
        )

        response = client.post("/api/v3/orders", json={
            "symbol": "BTC/USDT:USDT",
            "order_type": "MARKET",
            "direction": "LONG",
            "role": "ENTRY",
            "amount": "0.001",
            "reduce_only": False,
        })

        # Should be rejected
        assert response.status_code == 400
        data = response.json()
        assert "SINGLE_TRADE_LOSS_LIMIT" in str(data)


class TestCancelOrder:
    """Test DELETE /api/v3/orders/{order_id}"""

    def test_cancel_order_success(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test successful order cancellation"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Mock cancel_order response
        mock_exchange_gateway.cancel_order.return_value = OrderCancelResult(
            order_id="order_123",
            exchange_order_id="binance_456",
            symbol="BTC/USDT:USDT",
            status=OrderStatus.CANCELED,
            message="Order canceled successfully",
        )

        response = client.delete(
            "/api/v3/orders/order_123",
            params={"symbol": "BTC/USDT:USDT"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "order_123"
        assert data["status"] == "CANCELED"
        assert data["message"] == "Order canceled successfully"

    def test_cancel_order_not_found(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test canceling non-existent order"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Mock order not found
        mock_exchange_gateway.cancel_order.side_effect = OrderNotFoundError("订单不存在", "F-012")

        response = client.delete(
            "/api/v3/orders/non_existent_order",
            params={"symbol": "BTC/USDT:USDT"}
        )

        assert response.status_code == 404


class TestGetOrder:
    """Test GET /api/v3/orders/{order_id}"""

    def test_get_order_success(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test successful order retrieval"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Mock fetch_order response
        mock_exchange_gateway.fetch_order.return_value = OrderPlacementResult(
            order_id="order_123",
            exchange_order_id="binance_456",
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            direction=Direction.LONG,
            side="buy",
            amount=Decimal("0.001"),
            price=Decimal("45000"),
            status=OrderStatus.OPEN,
        )

        response = client.get(
            "/api/v3/orders/order_123",
            params={"symbol": "BTC/USDT:USDT"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "order_123"
        assert data["symbol"] == "BTC/USDT:USDT"


# ============================================================
# Position Management Tests
# ============================================================
class TestListPositions:
    """Test GET /api/v3/positions"""

    def test_list_positions_empty(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test listing positions when no positions exist"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        mock_exchange_gateway.fetch_positions.return_value = []

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert data["positions"] == []

    def test_list_positions_with_data(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test listing positions with existing positions"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Mock positions
        mock_exchange_gateway.fetch_positions.return_value = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="buy",
                size=Decimal("0.001"),
                entry_price=Decimal("45000"),
                unrealized_pnl=Decimal("100"),
                leverage=10,
            )
        ]

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "BTC/USDT:USDT"


# ============================================================
# Account Tests
# ============================================================
class TestAccountBalance:
    """Test GET /api/v3/account/balance"""

    def test_get_account_balance_success(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test successful account balance retrieval"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        # Mock balance response
        mock_exchange_gateway.fetch_account_balance.return_value = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("9000"),
            unrealized_pnl=Decimal("500"),
            positions=[],
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

        response = client.get("/api/v3/account/balance")

        assert response.status_code == 200
        data = response.json()
        assert data["exchange"] == "binance"
        assert data["account_type"] == "FUTURES"


# ============================================================
# Reconciliation Tests
# ============================================================
class TestReconciliation:
    """Test POST /api/v3/reconciliation"""

    def test_reconciliation_consistent(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """Test reconciliation with consistent state"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
        )

        mock_exchange_gateway.fetch_positions.return_value = []

        response = client.post("/api/v3/reconciliation", json={
            "symbol": "BTC/USDT:USDT",
            "full_check": False,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT:USDT"
        assert data["is_consistent"] is True
        assert data["total_discrepancies"] == 0
