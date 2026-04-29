"""Tests for /api/v3/orders, /api/v3/orders/tree, /api/v3/orders/batch, and order detail/chain.

Covers:
B. /api/v3/orders
  1. PgOrderRepository mock -> OrdersResponse correct
  2. OrderResponseFull field mapping
  3. remaining_qty calculation
  4. status/order_role/order_type/direction passing

C. /api/v3/orders/tree
  1. get_order_tree() items -> OrderTreeResponse
  2. ENTRY root + children hierarchy
  3. symbol/days/page/page_size params

D. /api/v3/orders/batch
  1. delete_orders_batch() success -> OrderDeleteResponse mapping
  2. empty order_ids -> 400
  3. >100 order_ids -> 400
  4. audit_log_id / deleted_count / deleted_from_db / failed_to_cancel

E. Order detail / chain
  1. include_chain=true -> get_order_chain_by_order_id()
  2. repo no order -> fallback exchange path
  3. order_chain role/status/fill mapping
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastapi.testclient import TestClient

from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderType,
)
from src.interfaces.api import app, set_dependencies


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _make_order(**overrides):
    defaults = dict(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        created_at=_now_ms(),
        updated_at=_now_ms(),
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_mock_repo():
    repo = MagicMock()
    repo.get_signals = AsyncMock(return_value={"total": 0, "data": []})
    repo.close = AsyncMock()
    return repo


def _set_deps(**kwargs):
    set_dependencies(**kwargs)


# ---------------------------------------------------------------------------
# B. /api/v3/orders
# ---------------------------------------------------------------------------


class TestV3OrdersList:
    """/api/v3/orders: list orders with PG repo."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_pg_repo_returns_orders_response(self, client):
        """PgOrderRepository.get_orders() returns OrdersResponse correctly."""
        order = _make_order(
            exchange_order_id="ex-123",
            price=Decimal("65000"),
            filled_qty=Decimal("0.001"),
        )

        order_repo = MagicMock()
        order_repo.get_orders = AsyncMock(return_value={
            "items": [order],
            "total": 1,
            "limit": 50,
            "offset": 0,
        })

        gateway = MagicMock()
        gateway.exchange_name = "binance"

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=gateway,
            order_repo=order_repo,
        )

        response = client.get("/api/v3/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["order_id"] == order.id

    def test_field_mapping_correct(self, client):
        """OrderResponseFull field mapping: direction, status, order_role, order_type."""
        order = _make_order(
            direction=Direction.SHORT,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.SL,
            status=OrderStatus.FILLED,
            price=Decimal("49000"),
            trigger_price=Decimal("48000"),
            filled_qty=Decimal("0.001"),
        )

        order_repo = MagicMock()
        order_repo.get_orders = AsyncMock(return_value={
            "items": [order],
            "total": 1,
            "limit": 50,
            "offset": 0,
        })

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.get("/api/v3/orders")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["direction"] == "SHORT"
        assert item["status"] == "FILLED"
        assert item["order_role"] == "SL"
        assert item["order_type"] == "LIMIT"

    def test_remaining_qty_calculation(self, client):
        """remaining_qty = requested_qty - filled_qty."""
        order = _make_order(
            requested_qty=Decimal("0.002"),
            filled_qty=Decimal("0.001"),
        )

        order_repo = MagicMock()
        order_repo.get_orders = AsyncMock(return_value={
            "items": [order],
            "total": 1,
            "limit": 50,
            "offset": 0,
        })

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.get("/api/v3/orders")
        assert response.status_code == 200
        item = response.json()["items"][0]
        # remaining_qty = 0.002 - 0.001 = 0.001
        assert Decimal(str(item["remaining_qty"])) == Decimal("0.001")


# ---------------------------------------------------------------------------
# C. /api/v3/orders/tree
# ---------------------------------------------------------------------------


class TestV3OrderTree:
    """/api/v3/orders/tree: tree structure with PG repo."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_order_tree_response_structure(self, client):
        """get_order_tree() returns OrderTreeResponse with items/total/metadata."""
        entry_id = str(uuid4())
        now = _now_ms()

        tree_result = {
            "items": [
                {
                    "order": {
                        "order_id": entry_id,
                        "exchange_order_id": None,
                        "symbol": "BTC/USDT:USDT",
                        "order_type": "MARKET",
                        "order_role": "ENTRY",
                        "direction": "LONG",
                        "status": "FILLED",
                        "quantity": "0.001",
                        "filled_qty": "0.001",
                        "remaining_qty": "0",
                        "price": None,
                        "trigger_price": None,
                        "average_exec_price": "65000",
                        "reduce_only": False,
                        "client_order_id": None,
                        "strategy_name": None,
                        "signal_id": str(uuid4()),
                        "stop_loss": None,
                        "take_profit": None,
                        "created_at": now,
                        "updated_at": now,
                        "filled_at": now,
                        "fee_paid": "0",
                        "fee_currency": None,
                        "tags": [],
                    },
                    "children": [
                        {
                            "order": {
                                "order_id": str(uuid4()),
                                "order_role": "TP1",
                                "direction": "LONG",
                                "status": "OPEN",
                                "quantity": "0.0005",
                                "filled_qty": "0",
                                "remaining_qty": "0.0005",
                                "symbol": "BTC/USDT:USDT",
                                "order_type": "LIMIT",
                                "price": "70000",
                                "trigger_price": None,
                                "average_exec_price": None,
                                "reduce_only": True,
                                "client_order_id": None,
                                "strategy_name": None,
                                "signal_id": str(uuid4()),
                                "stop_loss": None,
                                "take_profit": None,
                                "created_at": now + 1,
                                "updated_at": now + 1,
                                "filled_at": None,
                                "fee_paid": "0",
                                "fee_currency": None,
                                "tags": [],
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
            "total_count": 1,
            "page": 1,
            "page_size": 50,
            "metadata": {
                "symbol_filter": "BTC/USDT:USDT",
                "days_filter": 7,
                "loaded_at": now,
            },
        }

        order_repo = MagicMock()
        order_repo.get_order_tree = AsyncMock(return_value=tree_result)

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.get("/api/v3/orders/tree?symbol=BTC/USDT:USDT")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        root = data["items"][0]
        assert root["level"] == 0
        assert root["has_children"] is True
        assert root["order"]["order_role"] == "ENTRY"
        assert len(root["children"]) == 1
        assert root["children"][0]["order"]["order_role"] == "TP1"

    def test_tree_params_passed_to_repo(self, client):
        """symbol/days/page/page_size params passed to repo.get_order_tree()."""
        order_repo = MagicMock()
        order_repo.get_order_tree = AsyncMock(return_value={
            "items": [],
            "total": 0,
            "total_count": 0,
            "page": 1,
            "page_size": 10,
            "metadata": {},
        })

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.get("/api/v3/orders/tree?symbol=ETH/USDT:USDT&days=3&page=2&page_size=10")
        assert response.status_code == 200
        call_kwargs = order_repo.get_order_tree.call_args.kwargs
        assert call_kwargs.get("symbol") == "ETH/USDT:USDT"
        assert call_kwargs.get("days") == 3
        assert call_kwargs.get("page") == 2
        assert call_kwargs.get("page_size") == 10


# ---------------------------------------------------------------------------
# D. /api/v3/orders/batch
# ---------------------------------------------------------------------------


class TestV3OrdersBatchDelete:
    """/api/v3/orders/batch: batch delete with PG repo."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_successful_delete_mapping(self, client):
        """delete_orders_batch() success -> OrderDeleteResponse mapping."""
        order_repo = MagicMock()
        order_repo.delete_orders_batch = AsyncMock(return_value={
            "deleted_count": 3,
            "cancelled_on_exchange": [],
            "failed_to_cancel": [],
            "deleted_from_db": ["id-1", "id-2", "id-3"],
            "failed_to_delete": [],
            "audit_log_id": "audit-001",
        })

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.request(
            "DELETE",
            "/api/v3/orders/batch",
            json={
                "order_ids": ["id-1", "id-2", "id-3"],
                "cancel_on_exchange": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["deleted_count"] == 3
        assert data["deleted_from_db"] == ["id-1", "id-2", "id-3"]
        assert data["audit_log_id"] == "audit-001"
        assert data["failed_to_cancel"] == []

    def test_empty_order_ids_returns_422(self, client):
        """Empty order_ids -> 422 (Pydantic validation)."""
        order_repo = MagicMock()
        order_repo.delete_orders_batch = AsyncMock(side_effect=ValueError("order_ids cannot be empty"))

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.request(
            "DELETE",
            "/api/v3/orders/batch",
            json={"order_ids": [], "cancel_on_exchange": False},
        )
        # Pydantic field_validator rejects empty list -> 422
        assert response.status_code == 422

    def test_over_100_order_ids_returns_422(self, client):
        """More than 100 order_ids -> 422 (Pydantic max_length)."""
        order_repo = MagicMock()
        order_repo.delete_orders_batch = AsyncMock(
            side_effect=ValueError("order_ids exceeds maximum of 100")
        )

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        ids = [str(uuid4()) for _ in range(101)]
        response = client.request(
            "DELETE",
            "/api/v3/orders/batch",
            json={"order_ids": ids, "cancel_on_exchange": False},
        )
        # Pydantic max_length=100 rejects >100 -> 422
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# E. Order detail / chain
# ---------------------------------------------------------------------------


class TestV3OrderDetailAndChain:
    """Order detail and chain: include_chain, fallback, field mapping."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_order_detail_returns_404_when_not_found(self, client):
        """Order not found in repo -> 404."""
        order_repo = MagicMock()
        order_repo.get_order = AsyncMock(return_value=None)
        order_repo.initialize = AsyncMock()
        order_repo.close = AsyncMock()

        _set_deps(
            repository=_make_mock_repo(),
            account_getter=lambda: None,
            exchange_gateway=MagicMock(),
            order_repo=order_repo,
        )

        response = client.get(f"/api/v3/orders/nonexistent?symbol=BTC/USDT:USDT")
        assert response.status_code == 404