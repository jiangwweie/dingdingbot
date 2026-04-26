"""Tests for v3 positions API — PG projection first + exchange enrich/fallback.

覆盖:
- list_positions: PG projection first, exchange enriches
- list_positions: PG fails → exchange fallback
- list_positions: is_closed=True → calls list_positions with is_closed=True
- list_positions: offset/limit passed to repo
- list_positions: account_balance missing → account_equity is None
- get_position: from PG projection returns detail / 404
"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fastapi.testclient import TestClient

from src.domain.models import (
    AccountSnapshot,
    Direction,
    Position,
    PositionInfo,
)
from src.interfaces.api import app, set_dependencies


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_repository():
    repo = MagicMock()
    repo.get_signals = AsyncMock(return_value={"total": 0, "data": []})
    repo.close = AsyncMock()
    return repo


@pytest.fixture
def mock_account_getter():
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
    gateway = MagicMock()
    gateway.exchange_name = "binance"
    gateway.fetch_positions = AsyncMock(return_value=[])
    gateway.fetch_account_balance = AsyncMock(return_value=AccountSnapshot(
        total_balance=Decimal("10000"),
        available_balance=Decimal("9000"),
        unrealized_pnl=Decimal("0"),
        positions=[],
        timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
    ))
    return gateway


# ============================================================
# list_positions: exchange-first + fallback
# ============================================================


class TestListPositionsPGProjectionFirst:
    """list_positions: PG projection first, exchange enriches."""

    def test_pg_projection_returned_first(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """PG projection exists → returned first, exchange enriches."""
        pg_position = Position(
            id="pos_btc_001",
            signal_id="sig_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0.1"),
            realized_pnl=Decimal("0"),
        )

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[pg_position])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        position_repo.list_positions.assert_called_once()

    def test_pg_failure_falls_back_to_exchange(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """PG query fails → falls back to exchange positions."""
        mock_exchange_gateway.fetch_positions.return_value = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="buy",
                size=Decimal("0.1"),
                entry_price=Decimal("65000"),
                current_price=Decimal("66000"),
                unrealized_pnl=Decimal("100"),
                leverage=10,
            )
        ]

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(side_effect=RuntimeError("DB down"))

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1

    def test_both_empty_returns_empty(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """PG and exchange both empty → empty list."""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert data["positions"] == []


# ============================================================
# get_position: PG projection 详情
# ============================================================


class TestGetPositionFromProjection:
    """get_position(position_id) 从 PG projection 返回详情。"""

    def test_position_found_in_repo(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """position_repo.get() 返回仓位详情。"""
        position = Position(
            id="pos_detail_001",
            signal_id="sig_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1.0"),
            realized_pnl=Decimal("0"),
        )

        position_repo = MagicMock()
        position_repo.get = AsyncMock(return_value=position)

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions/pos_detail_001")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "BTC/USDT:USDT"
        position_repo.get.assert_called_once_with("pos_detail_001")

    def test_position_not_found_returns_404(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """position_repo.get() 返回 None → 404。"""
        position_repo = MagicMock()
        position_repo.get = AsyncMock(return_value=None)

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions/pos_nonexist")

        assert response.status_code == 404

    def test_repo_none_returns_404(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """position_repo 为 None 时返回 404。"""
        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=None,
        )

        response = client.get("/api/v3/positions/pos_any")

        assert response.status_code == 404


# ============================================================
# list_positions: is_closed / offset+limit / account_equity
# ============================================================


class TestListPositionsEdgeCases:
    """list_positions 边界条件：is_closed / offset+limit / account_equity。"""

    def test_is_closed_true_calls_list_positions(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """is_closed=True → calls list_positions with is_closed=True."""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions?is_closed=true")

        assert response.status_code == 200
        position_repo.list_positions.assert_called_once()
        call_kwargs = position_repo.list_positions.call_args.kwargs
        assert call_kwargs.get("is_closed") is True

    def test_offset_limit_passed_to_repo(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """offset/limit passed to list_positions on PG main path."""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions?offset=10&limit=5")

        assert response.status_code == 200
        position_repo.list_positions.assert_called_once()
        call_kwargs = position_repo.list_positions.call_args.kwargs
        assert call_kwargs.get("offset") == 10
        assert call_kwargs.get("limit") == 5

    def test_account_balance_missing_equity_none(
        self, client, mock_repository, mock_exchange_gateway
    ):
        """account_balance 返回 None 时 account_equity 为 None。"""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        set_dependencies(
            repository=mock_repository,
            account_getter=lambda: None,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert data["account_equity"] is None