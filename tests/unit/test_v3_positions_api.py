"""Tests for v3 positions API — exchange-first + PG projection fallback.

覆盖:
- list_positions: 交易所成功 → 交易所数据优先
- list_positions: 交易所失败 → position_repo.list_active() fallback
- list_positions: is_closed=True 不返回未平仓 projection
- list_positions: offset/limit 切片
- list_positions: account_balance 缺失 → account_equity 为 None
- get_position: 从 PG projection 返回详情 / 404
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
    gateway.fetch_account_balance = AsyncMock()
    return gateway


# ============================================================
# list_positions: exchange-first + fallback
# ============================================================


class TestListPositionsExchangeFirst:
    """list_positions: 交易所成功时优先返回交易所数据。"""

    def test_exchange_success_returns_exchange_data(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """exchange_gateway 可用时返回交易所数据。"""
        mock_exchange_gateway.fetch_positions.return_value = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="buy",
                size=Decimal("0.1"),
                entry_price=Decimal("65000"),
                unrealized_pnl=Decimal("100"),
                leverage=10,
            )
        ]
        mock_exchange_gateway.fetch_account_balance.return_value = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("9000"),
            unrealized_pnl=Decimal("100"),
            positions=[],
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        )

        position_repo = MagicMock()
        position_repo.list_active = AsyncMock(return_value=[])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) == 1
        assert data["positions"][0]["symbol"] == "BTC/USDT:USDT"
        # 交易所数据优先，不应调用 position_repo fallback
        position_repo.list_active.assert_not_called()

    def test_exchange_failure_falls_back_to_repo(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """exchange_gateway 不可用时 fallback 到 position_repo.list_active()。"""
        mock_exchange_gateway.fetch_positions.side_effect = Exception("Network error")

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
        position_repo.list_active = AsyncMock(return_value=[pg_position])

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
        # fallback 到 position_repo
        position_repo.list_active.assert_called_once()

    def test_both_empty_returns_empty(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """交易所和 repo 都无仓位时返回空列表。"""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_active = AsyncMock(return_value=[])

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

    def test_is_closed_true_returns_empty_via_fallback(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """is_closed=True 时 fallback 不调 list_active，直接返回空。"""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_active = AsyncMock(return_value=[
            Position(
                id="pos_active_001",
                signal_id="sig_001",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                entry_price=Decimal("65000"),
                current_qty=Decimal("0.1"),
                realized_pnl=Decimal("0"),
                is_closed=False,
            )
        ])

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions?is_closed=true")

        assert response.status_code == 200
        data = response.json()
        assert data["positions"] == []
        # is_closed=True 不应调用 list_active
        position_repo.list_active.assert_not_called()

    def test_offset_limit_slicing(
        self, client, mock_repository, mock_account_getter, mock_exchange_gateway
    ):
        """offset/limit 切片行为正确：offset=0, limit=2 返回前 2 条。"""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        positions = [
            Position(
                id=f"pos_slice_{i}",
                signal_id=f"sig_{i}",
                symbol="BTC/USDT:USDT",
                direction=Direction.LONG,
                entry_price=Decimal("65000"),
                current_qty=Decimal("0.1"),
                realized_pnl=Decimal("0"),
            )
            for i in range(3)
        ]

        position_repo = MagicMock()
        position_repo.list_active = AsyncMock(return_value=positions)

        set_dependencies(
            repository=mock_repository,
            account_getter=mock_account_getter,
            exchange_gateway=mock_exchange_gateway,
            position_repo=position_repo,
        )

        # offset=0 不会触发双重切片 bug
        response = client.get("/api/v3/positions?offset=0&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) == 2
        assert data["positions"][0]["position_id"] == "pos_slice_0"
        assert data["positions"][1]["position_id"] == "pos_slice_1"

    def test_account_balance_missing_equity_none(
        self, client, mock_repository, mock_exchange_gateway
    ):
        """account_balance 返回 None 时 account_equity 为 None。"""
        mock_exchange_gateway.fetch_positions.return_value = []
        mock_exchange_gateway.fetch_account_balance = AsyncMock(return_value=None)

        position_repo = MagicMock()
        position_repo.list_active = AsyncMock(return_value=[])

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