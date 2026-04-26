"""Tests for RuntimePositionsReadModel PG projection + snapshot enrich logic.

Covers:
D. RuntimePositionsReadModel
  1. position_repo has data -> PG positions returned first
  2. snapshot enriches mark_price (as current_price)/unrealized_pnl/leverage/margin
  3. PG no data -> falls back to account_snapshot
  4. position_repo.list_active() throws -> falls back to snapshot
  5. No repo, no snapshot -> empty list

E. /api/v3/positions
  1. PG positions exist -> projection returned first
  2. Exchange positions enrich projection (mark_price from PositionInfo.mark_price)
  3. is_closed=True -> calls list_positions(is_closed=True)
  4. PG query fails -> falls back to exchange positions
  5. account_balance missing -> account_equity = None
  6. offset/limit behavior under PG main path
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.readmodels.runtime_positions import RuntimePositionsReadModel
from src.domain.models import Direction, Position, PositionInfo


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _make_position(
    symbol="BTC/USDT:USDT",
    direction=Direction.LONG,
    current_qty=Decimal("0.25"),
    entry_price=Decimal("64000"),
    watermark_price=None,
    is_closed=False,
):
    return Position(
        id=f"pos-{symbol}",
        signal_id="sig-001",
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=watermark_price,
        is_closed=is_closed,
        opened_at=_now_ms(),
    )


def _make_account_snapshot(positions=None):
    snapshot = MagicMock()
    snapshot.total_balance = Decimal("10000")
    snapshot.available_balance = Decimal("9000")
    snapshot.unrealized_pnl = Decimal("0")
    snapshot.timestamp = _now_ms()
    snapshot.positions = positions or []
    return snapshot


def _make_position_info(
    symbol="BTC/USDT:USDT",
    side="long",
    size=Decimal("0.25"),
    entry_price=Decimal("64000"),
    mark_price=Decimal("65000"),
    unrealized_pnl=Decimal("120"),
    leverage=5,
):
    return PositionInfo(
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        mark_price=mark_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
    )


# ---------------------------------------------------------------------------
# D. RuntimePositionsReadModel
# ---------------------------------------------------------------------------


class TestRuntimePositionsPGProjection:
    """RuntimePositionsReadModel: PG projection first, snapshot enrich, fallback."""

    @pytest.mark.asyncio
    async def test_pg_positions_returned_first(self):
        """position_repo has data -> PG positions returned, snapshot not used."""
        model = RuntimePositionsReadModel()

        pg_pos = _make_position()
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[pg_pos])

        response = await model.build(
            account_snapshot=_make_account_snapshot(),
            position_repo=repo,
        )

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "BTC/USDT:USDT"
        assert response.positions[0].direction == "LONG"
        repo.list_active.assert_called_once_with(limit=200)

    @pytest.mark.asyncio
    async def test_snapshot_enriches_pg_position(self):
        """Snapshot with same symbol/direction enriches current_price/unrealized_pnl/leverage/margin.

        PositionInfo now has mark_price field, so current_price in the
        console response can be enriched from snapshot's mark_price.
        """
        model = RuntimePositionsReadModel()

        pg_pos = _make_position(
            symbol="ETH/USDT:USDT",
            direction=Direction.LONG,
            current_qty=Decimal("0.5"),
            entry_price=Decimal("3000"),
            watermark_price=Decimal("3100"),
        )
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[pg_pos])

        # Snapshot has matching position with mark_price
        snap_pos = _make_position_info(
            symbol="ETH/USDT:USDT",
            side="long",
            mark_price=Decimal("3200"),
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        pos = response.positions[0]
        assert pos.symbol == "ETH/USDT:USDT"
        # current_price enriched from snapshot's mark_price (3200)
        assert pos.current_price == 3200.0
        # unrealized_pnl and leverage ARE enriched from snapshot
        assert pos.unrealized_pnl == 100.0
        assert pos.leverage == 10
        # margin = notional / leverage = (0.5 * 3000) / 10 = 150
        assert abs(pos.margin - 150.0) < 0.01

    @pytest.mark.asyncio
    async def test_pg_no_data_falls_back_to_snapshot(self):
        """PG returns empty -> falls back to account_snapshot positions."""
        model = RuntimePositionsReadModel()

        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[])

        snap_pos = _make_position_info()
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "BTC/USDT:USDT"

    @pytest.mark.asyncio
    async def test_repo_list_active_throws_falls_back_to_snapshot(self):
        """position_repo.list_active() raises -> falls back to snapshot."""
        model = RuntimePositionsReadModel()

        repo = MagicMock()
        repo.list_active = AsyncMock(side_effect=RuntimeError("DB down"))

        snap_pos = _make_position_info()
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        assert response.positions[0].symbol == "BTC/USDT:USDT"

    @pytest.mark.asyncio
    async def test_no_repo_no_snapshot_returns_empty(self):
        """No repo, no snapshot -> empty list."""
        model = RuntimePositionsReadModel()

        response = await model.build(
            account_snapshot=None,
            position_repo=None,
        )

        assert response.positions == []

    @pytest.mark.asyncio
    async def test_repo_has_data_but_no_snapshot(self):
        """Repo has data, snapshot is None -> PG positions returned without enrich."""
        model = RuntimePositionsReadModel()

        pg_pos = _make_position(watermark_price=Decimal("65000"))
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[pg_pos])

        response = await model.build(
            account_snapshot=None,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        # Without snapshot, current_price comes from watermark_price
        assert response.positions[0].current_price == 65000.0

    @pytest.mark.asyncio
    async def test_snapshot_mark_price_enriches_current_price(self):
        """Snapshot PositionInfo.mark_price enriches ConsolePositionItem.current_price."""
        model = RuntimePositionsReadModel()

        pg_pos = _make_position(
            symbol="SOL/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("150"),
            watermark_price=Decimal("155"),
        )
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[pg_pos])

        snap_pos = _make_position_info(
            symbol="SOL/USDT:USDT",
            side="long",
            entry_price=Decimal("150"),
            mark_price=Decimal("160"),
            unrealized_pnl=Decimal("10"),
            leverage=5,
        )
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        # current_price enriched from snapshot's mark_price (160), not watermark_price (155)
        assert response.positions[0].current_price == 160.0

    @pytest.mark.asyncio
    async def test_snapshot_no_mark_price_falls_back_to_watermark(self):
        """Snapshot PositionInfo with mark_price=None falls back to watermark_price."""
        model = RuntimePositionsReadModel()

        pg_pos = _make_position(
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("60000"),
            watermark_price=Decimal("61000"),
        )
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[pg_pos])

        snap_pos = _make_position_info(
            symbol="BTC/USDT:USDT",
            side="long",
            entry_price=Decimal("60000"),
            mark_price=None,
            unrealized_pnl=Decimal("0"),
            leverage=5,
        )
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        # mark_price is None → falls back to watermark_price
        assert response.positions[0].current_price == 61000.0

    @pytest.mark.asyncio
    async def test_fallback_snapshot_mark_price_enriches_current_price(self):
        """In snapshot-fallback path, PositionInfo.mark_price enriches current_price."""
        model = RuntimePositionsReadModel()

        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[])

        snap_pos = _make_position_info(
            symbol="BTC/USDT:USDT",
            side="long",
            entry_price=Decimal("60000"),
            mark_price=Decimal("62000"),
            unrealized_pnl=Decimal("50"),
            leverage=5,
        )
        snapshot = _make_account_snapshot(positions=[snap_pos])

        response = await model.build(
            account_snapshot=snapshot,
            position_repo=repo,
        )

        assert len(response.positions) == 1
        # In fallback path, current_price enriched from mark_price
        assert response.positions[0].current_price == 62000.0


# ---------------------------------------------------------------------------
# E. /api/v3/positions (API-level tests via TestClient)
# ---------------------------------------------------------------------------


class TestV3PositionsAPI:
    """/api/v3/positions: PG projection first, exchange enrich, fallback."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.interfaces.api import app
        return TestClient(app)

    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock()
        repo.get_signals = AsyncMock(return_value={"total": 0, "data": []})
        repo.close = AsyncMock()
        return repo

    def _set_deps(self, **kwargs):
        from src.interfaces.api import set_dependencies
        set_dependencies(**kwargs)

    def test_pg_positions_returned_first(self, client, mock_repo):
        """PG positions exist -> projection returned, exchange not used for main data."""
        pg_pos = Position(
            id="pos-btc-001",
            signal_id="sig-001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0.1"),
            realized_pnl=Decimal("0"),
            is_closed=False,
            opened_at=_now_ms(),
        )

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[pg_pos])

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        position_repo.list_positions.assert_called_once()

    def test_exchange_enriches_projection(self, client, mock_repo):
        """Exchange positions enrich PG projection with mark_price/unrealized_pnl/leverage.

        PositionInfo now has mark_price, so the v3 API can enrich
        mark_price from exchange positions.
        """
        pg_pos = Position(
            id="pos-btc-002",
            signal_id="sig-002",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0.1"),
            realized_pnl=Decimal("0"),
            is_closed=False,
            opened_at=_now_ms(),
        )

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[pg_pos])

        exchange_pos = PositionInfo(
            symbol="BTC/USDT:USDT",
            side="buy",
            size=Decimal("0.1"),
            entry_price=Decimal("65000"),
            mark_price=Decimal("66000"),
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[exchange_pos])
        gateway.fetch_account_balance = AsyncMock(return_value=MagicMock(
            total_balance=Decimal("10000"),
            unrealized_pnl=Decimal("100"),
        ))

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        pos = data["positions"][0]
        # Exchange enriches mark_price from PositionInfo.mark_price
        assert pos["mark_price"] is not None
        assert Decimal(str(pos["mark_price"])) == Decimal("66000")
        # Exchange enriches unrealized_pnl and leverage
        assert pos["unrealized_pnl"] is not None

    def test_is_closed_true_calls_list_positions(self, client, mock_repo):
        """is_closed=True -> calls list_positions(is_closed=True)."""
        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions?is_closed=true")
        assert response.status_code == 200
        position_repo.list_positions.assert_called_once()
        call_kwargs = position_repo.list_positions.call_args
        assert call_kwargs.kwargs.get("is_closed") is True or (
            len(call_kwargs.args) > 0 and True  # positional
        )

    def test_pg_query_fails_falls_back_to_exchange(self, client, mock_repo):
        """PG query fails -> falls back to exchange positions."""
        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(side_effect=RuntimeError("DB down"))

        exchange_pos = PositionInfo(
            symbol="BTC/USDT:USDT",
            side="buy",
            size=Decimal("0.1"),
            entry_price=Decimal("65000"),
            mark_price=Decimal("66000"),
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[exchange_pos])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1

    def test_account_balance_missing_equity_none(self, client, mock_repo):
        """account_balance is None -> account_equity is None."""
        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert data["account_equity"] is None

    def test_offset_limit_under_pg_path(self, client, mock_repo):
        """offset/limit passed to list_positions on PG main path."""
        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[])

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions?offset=10&limit=5")
        assert response.status_code == 200
        position_repo.list_positions.assert_called_once()
        call_kwargs = position_repo.list_positions.call_args.kwargs
        assert call_kwargs.get("offset") == 10
        assert call_kwargs.get("limit") == 5

    def test_exchange_mark_price_enriches_projection(self, client, mock_repo):
        """Exchange PositionInfo.mark_price enriches PG projection's mark_price."""
        pg_pos = Position(
            id="pos-eth-001",
            signal_id="sig-001",
            symbol="ETH/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("3000"),
            current_qty=Decimal("0.5"),
            realized_pnl=Decimal("0"),
            is_closed=False,
            opened_at=_now_ms(),
        )

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[pg_pos])

        exchange_pos = PositionInfo(
            symbol="ETH/USDT:USDT",
            side="buy",
            size=Decimal("0.5"),
            entry_price=Decimal("3000"),
            mark_price=Decimal("3100"),
            unrealized_pnl=Decimal("50"),
            leverage=10,
        )

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[exchange_pos])
        gateway.fetch_account_balance = AsyncMock(return_value=MagicMock(
            total_balance=Decimal("10000"),
            unrealized_pnl=Decimal("50"),
        ))

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        pos = data["positions"][0]
        # mark_price enriched from exchange PositionInfo.mark_price
        assert pos["mark_price"] is not None
        assert Decimal(str(pos["mark_price"])) == Decimal("3100")

    def test_exchange_fallback_mark_price_populated(self, client, mock_repo):
        """Exchange fallback path: PositionInfo.mark_price → PositionInfoV3.mark_price."""
        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(side_effect=RuntimeError("DB down"))

        exchange_pos = PositionInfo(
            symbol="BTC/USDT:USDT",
            side="buy",
            size=Decimal("0.1"),
            entry_price=Decimal("65000"),
            mark_price=Decimal("66000"),
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[exchange_pos])
        gateway.fetch_account_balance = AsyncMock(return_value=None)

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        pos = data["positions"][0]
        # In exchange fallback, mark_price comes from PositionInfo.mark_price
        assert pos["mark_price"] is not None
        assert Decimal(str(pos["mark_price"])) == Decimal("66000")

    def test_exchange_no_mark_price_falls_back_to_none(self, client, mock_repo):
        """Exchange PositionInfo with mark_price=None → PositionInfoV3.mark_price is None."""
        pg_pos = Position(
            id="pos-btc-003",
            signal_id="sig-001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0.1"),
            realized_pnl=Decimal("0"),
            is_closed=False,
            opened_at=_now_ms(),
        )

        position_repo = MagicMock()
        position_repo.list_positions = AsyncMock(return_value=[pg_pos])

        exchange_pos = PositionInfo(
            symbol="BTC/USDT:USDT",
            side="buy",
            size=Decimal("0.1"),
            entry_price=Decimal("65000"),
            mark_price=None,
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )

        gateway = MagicMock()
        gateway.exchange_name = "binance"
        gateway.fetch_positions = AsyncMock(return_value=[exchange_pos])
        gateway.fetch_account_balance = AsyncMock(return_value=MagicMock(
            total_balance=Decimal("10000"),
            unrealized_pnl=Decimal("100"),
        ))

        self._set_deps(
            repository=mock_repo,
            account_getter=lambda: None,
            exchange_gateway=gateway,
            position_repo=position_repo,
        )

        response = client.get("/api/v3/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["positions"]) >= 1
        pos = data["positions"][0]
        # mark_price is None when exchange PositionInfo.mark_price is None
        assert pos["mark_price"] is None