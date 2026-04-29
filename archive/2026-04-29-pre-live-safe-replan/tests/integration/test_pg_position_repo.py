"""PG integration tests for PgPositionRepository — real PostgreSQL, no mocks.

Requires:
  - PG_DATABASE_URL env var (default: postgresql+asyncpg://postgres:postgres@localhost:5432/dingpan_test)
  - The database must already exist.

Usage:
  PG_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname \
    pytest tests/integration/test_pg_position_repo.py -v
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.domain.models import Direction, Position
from src.infrastructure.pg_models import PGPositionORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_position(**overrides):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    defaults = dict(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        direction=Direction.LONG,
        entry_price=Decimal("50000.00"),
        current_qty=Decimal("0.001"),
        realized_pnl=Decimal("0"),
        total_fees_paid=Decimal("0"),
        total_funding_paid=Decimal("0"),
        opened_at=now,
        is_closed=False,
    )
    defaults.update(overrides)
    return Position(**defaults)


# ---------------------------------------------------------------------------
# 1. save / get round trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_get_round_trip(position_repo):
    pos = make_position()
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.id == pos.id
    assert loaded.signal_id == pos.signal_id
    assert loaded.symbol == pos.symbol
    assert loaded.direction == pos.direction
    assert loaded.entry_price == pos.entry_price
    assert loaded.current_qty == pos.current_qty
    assert loaded.realized_pnl == pos.realized_pnl
    assert loaded.is_closed == pos.is_closed
    assert loaded.opened_at == pos.opened_at
    assert loaded.closed_at == pos.closed_at


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(position_repo):
    assert await position_repo.get("nonexistent-id") is None


# ---------------------------------------------------------------------------
# 2. save upsert — same id, updated quantity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_upsert(position_repo):
    pos = make_position(current_qty=Decimal("0.001"))
    await position_repo.save(pos)

    updated = make_position(
        id=pos.id,
        signal_id=pos.signal_id,
        current_qty=Decimal("0.005"),
        realized_pnl=Decimal("12.50"),
    )
    await position_repo.save(updated)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.current_qty == Decimal("0.005")
    assert loaded.realized_pnl == Decimal("12.50")


# ---------------------------------------------------------------------------
# 3. get_by_signal_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_signal_id(position_repo):
    signal_id = str(uuid4())
    pos_a = make_position(signal_id=signal_id, symbol="BTC/USDT:USDT")
    pos_b = make_position(signal_id=signal_id, symbol="ETH/USDT:USDT")
    pos_other = make_position(signal_id=str(uuid4()), symbol="SOL/USDT:USDT")

    await position_repo.save(pos_a)
    await position_repo.save(pos_b)
    await position_repo.save(pos_other)

    results = await position_repo.get_by_signal_id(signal_id)
    ids = {r.id for r in results}
    assert ids == {pos_a.id, pos_b.id}


@pytest.mark.asyncio
async def test_get_by_signal_id_empty(position_repo):
    results = await position_repo.get_by_signal_id("no-such-signal")
    assert results == []


# ---------------------------------------------------------------------------
# 4. list_active
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_active_filters_closed(position_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    open_pos = make_position(is_closed=False, opened_at=now)
    closed_pos = make_position(
        is_closed=True,
        closed_at=now + 1000,
        opened_at=now,
    )
    await position_repo.save(open_pos)
    await position_repo.save(closed_pos)

    active = await position_repo.list_active()
    assert len(active) == 1
    assert active[0].id == open_pos.id
    assert active[0].is_closed is False


@pytest.mark.asyncio
async def test_list_active_symbol_filter(position_repo):
    btc = make_position(symbol="BTC/USDT:USDT", is_closed=False)
    eth = make_position(symbol="ETH/USDT:USDT", is_closed=False)
    await position_repo.save(btc)
    await position_repo.save(eth)

    results = await position_repo.list_active(symbol="BTC/USDT:USDT")
    assert len(results) == 1
    assert results[0].symbol == "BTC/USDT:USDT"


@pytest.mark.asyncio
async def test_list_active_limit(position_repo):
    for i in range(5):
        await position_repo.save(make_position(symbol=f"TEST{i}/USDT:USDT", is_closed=False))

    results = await position_repo.list_active(limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# 5. list_positions — is_closed, symbol, limit/offset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_positions_is_closed_filter(position_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    open_a = make_position(is_closed=False, opened_at=now)
    closed_a = make_position(is_closed=True, closed_at=now + 1000, opened_at=now)
    await position_repo.save(open_a)
    await position_repo.save(closed_a)

    only_open = await position_repo.list_positions(is_closed=False)
    assert all(p.is_closed is False for p in only_open)

    only_closed = await position_repo.list_positions(is_closed=True)
    assert all(p.is_closed is True for p in only_closed)


@pytest.mark.asyncio
async def test_list_positions_symbol_filter(position_repo):
    btc = make_position(symbol="BTC/USDT:USDT")
    eth = make_position(symbol="ETH/USDT:USDT")
    await position_repo.save(btc)
    await position_repo.save(eth)

    results = await position_repo.list_positions(symbol="ETH/USDT:USDT")
    assert len(results) == 1
    assert results[0].symbol == "ETH/USDT:USDT"


@pytest.mark.asyncio
async def test_list_positions_limit_offset_pagination(position_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    for i in range(6):
        await position_repo.save(make_position(symbol=f"PAGE{i}/USDT:USDT", opened_at=now + i))

    page1 = await position_repo.list_positions(limit=3, offset=0)
    page2 = await position_repo.list_positions(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 3
    # Pages should not overlap
    ids_page1 = {p.id for p in page1}
    ids_page2 = {p.id for p in page2}
    assert ids_page1.isdisjoint(ids_page2)


# ---------------------------------------------------------------------------
# 6. position_payload JSONB round trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_payload_jsonb_round_trip(position_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    pos = make_position(
        watermark_price=Decimal("52000.50"),
        tp_trailing_activated=True,
        original_tp_prices={"TP1": Decimal("65000"), "TP2": Decimal("70000")},
        trailing_exit_activated=True,
        trailing_exit_price=Decimal("68000"),
        trailing_activation_time=now + 5000,
        total_fees_paid=Decimal("1.2345"),
        total_funding_paid=Decimal("0.5678"),
        projected_exit_fills={"TP1": Decimal("0.0005"), "TP2": Decimal("0.0005")},
        projected_exit_fees={"TP1": Decimal("0.25"), "TP2": Decimal("0.25")},
    )
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.watermark_price == Decimal("52000.50")
    assert loaded.tp_trailing_activated is True
    assert loaded.original_tp_prices == {"TP1": Decimal("65000"), "TP2": Decimal("70000")}
    assert loaded.trailing_exit_activated is True
    assert loaded.trailing_exit_price == Decimal("68000")
    assert loaded.trailing_activation_time == now + 5000
    assert loaded.total_fees_paid == Decimal("1.2345")
    assert loaded.total_funding_paid == Decimal("0.5678")
    assert loaded.projected_exit_fills == {"TP1": Decimal("0.0005"), "TP2": Decimal("0.0005")}
    assert loaded.projected_exit_fees == {"TP1": Decimal("0.25"), "TP2": Decimal("0.25")}


@pytest.mark.asyncio
async def test_payload_defaults_when_empty(position_repo):
    pos = make_position()  # all payload fields at default
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.watermark_price is None
    assert loaded.tp_trailing_activated is False
    assert loaded.original_tp_prices == {}
    assert loaded.trailing_exit_activated is False
    assert loaded.trailing_exit_price is None
    assert loaded.trailing_activation_time is None
    assert loaded.total_fees_paid == Decimal("0")
    assert loaded.total_funding_paid == Decimal("0")
    assert loaded.projected_exit_fills == {}
    assert loaded.projected_exit_fees == {}


# ---------------------------------------------------------------------------
# 7. Decimal precision
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decimal_precision(position_repo):
    pos = make_position(
        entry_price=Decimal("0.00000001"),
        current_qty=Decimal("0.00000001"),
        realized_pnl=Decimal("0.00000001"),
        total_fees_paid=Decimal("0.00000001"),
        total_funding_paid=Decimal("0.00000001"),
        watermark_price=Decimal("0.00000001"),
    )
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.entry_price == Decimal("0.00000001")
    assert loaded.current_qty == Decimal("0.00000001")
    assert loaded.realized_pnl == Decimal("0.00000001")
    assert loaded.total_fees_paid == Decimal("0.00000001")
    assert loaded.total_funding_paid == Decimal("0.00000001")
    assert loaded.watermark_price == Decimal("0.00000001")


# ---------------------------------------------------------------------------
# 8. CheckConstraint violations — direct ORM insert to bypass repo validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_constraint_invalid_direction(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGPositionORM(
            id=str(uuid4()),
            signal_id=str(uuid4()),
            symbol="BTC/USDT:USDT",
            direction="INVALID",
            quantity=Decimal("0.001"),
            entry_price=Decimal("50000"),
            is_closed=False,
            opened_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_negative_quantity(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGPositionORM(
            id=str(uuid4()),
            signal_id=str(uuid4()),
            symbol="BTC/USDT:USDT",
            direction="LONG",
            quantity=Decimal("-0.001"),
            entry_price=Decimal("50000"),
            is_closed=False,
            opened_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


# ---------------------------------------------------------------------------
# 9. opened_at / closed_at / is_closed round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opened_at_closed_at_is_closed_round_trip(position_repo):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    pos = make_position(
        opened_at=now,
        closed_at=None,
        is_closed=False,
    )
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.opened_at == now
    assert loaded.closed_at is None
    assert loaded.is_closed is False

    # Close the position
    closed = make_position(
        id=pos.id,
        signal_id=pos.signal_id,
        opened_at=now,
        closed_at=now + 60000,
        is_closed=True,
    )
    await position_repo.save(closed)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.is_closed is True
    assert loaded.closed_at == now + 60000


# ---------------------------------------------------------------------------
# 10. watermark_price round trip via position_payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watermark_price_round_trip(position_repo):
    pos = make_position(watermark_price=Decimal("65500.75"))
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.watermark_price == Decimal("65500.75")


# ---------------------------------------------------------------------------
# 11. projected_exit_fills / projected_exit_fees round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_projected_exit_fills_fees_round_trip(position_repo):
    pos = make_position(
        projected_exit_fills={
            "TP1": Decimal("0.0003"),
            "TP2": Decimal("0.0002"),
            "SL": Decimal("0.001"),
        },
        projected_exit_fees={
            "TP1": Decimal("0.15"),
            "TP2": Decimal("0.10"),
            "SL": Decimal("0.50"),
        },
    )
    await position_repo.save(pos)

    loaded = await position_repo.get(pos.id)
    assert loaded is not None
    assert loaded.projected_exit_fills == {
        "TP1": Decimal("0.0003"),
        "TP2": Decimal("0.0002"),
        "SL": Decimal("0.001"),
    }
    assert loaded.projected_exit_fees == {
        "TP1": Decimal("0.15"),
        "TP2": Decimal("0.10"),
        "SL": Decimal("0.50"),
    }


# ---------------------------------------------------------------------------
# 12. CheckConstraint: leverage must be positive or NULL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraint_zero_leverage(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGPositionORM(
            id=str(uuid4()),
            signal_id=str(uuid4()),
            symbol="BTC/USDT:USDT",
            direction="LONG",
            quantity=Decimal("0.001"),
            entry_price=Decimal("50000"),
            leverage=0,
            is_closed=False,
            opened_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


# ---------------------------------------------------------------------------
# 13. CheckConstraint: negative leverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraint_negative_leverage(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGPositionORM(
            id=str(uuid4()),
            signal_id=str(uuid4()),
            symbol="BTC/USDT:USDT",
            direction="LONG",
            quantity=Decimal("0.001"),
            entry_price=Decimal("50000"),
            leverage=-5,
            is_closed=False,
            opened_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()
