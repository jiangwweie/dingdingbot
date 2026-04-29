"""PG integration tests for PgSignalRepository — real PostgreSQL, no mocks.

Requires:
  - PG_DATABASE_URL env var (default: postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot)
  - The database must already exist.

Usage:
  PG_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname \
    pytest tests/integration/test_pg_signal_repo.py -v
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from src.domain.models import Direction, SignalQuery, SignalResult
from src.infrastructure.pg_models import PGSignalORM, PGSignalTakeProfitORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_uid_counter = 0


def _uid() -> str:
    global _uid_counter
    _uid_counter += 1
    return f"test-sig-{_uid_counter:04d}"


def make_signal(**overrides) -> SignalResult:
    defaults = dict(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000.00"),
        suggested_stop_loss=Decimal("49000.00"),
        suggested_position_size=Decimal("0.001"),
        current_leverage=10,
        tags=[{"name": "EMA", "value": "Bullish"}],
        risk_reward_info="Risk 1% = 50 USDT",
        strategy_name="pinbar",
        score=0.85,
        take_profit_levels=[
            {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "51500"},
            {"id": "TP2", "position_ratio": "0.5", "risk_reward": "3.0", "price": "53000"},
        ],
    )
    defaults.update(overrides)
    return SignalResult(**defaults)


# ---------------------------------------------------------------------------
# 1. save_signal / get_signal_by_tracker_id round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_get_by_tracker_id(signal_repo):
    signal = make_signal()
    signal_id = await signal_repo.save_signal(signal, signal_id="rt-001")

    loaded = await signal_repo.get_signal_by_tracker_id("rt-001")
    assert loaded is not None
    assert loaded["signal_id"] == "rt-001"
    assert loaded["symbol"] == "BTC/USDT:USDT"
    assert loaded["direction"] == "LONG"
    assert Decimal(loaded["entry_price"]) == Decimal("50000.00")
    assert Decimal(loaded["stop_loss"]) == Decimal("49000.00")
    assert loaded["strategy_name"] == "pinbar"
    assert loaded["status"] == "PENDING"


@pytest.mark.asyncio
async def test_get_by_tracker_id_not_found(signal_repo):
    result = await signal_repo.get_signal_by_tracker_id("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# 2. get_active_signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_signal(signal_repo):
    signal = make_signal(direction=Direction.LONG, strategy_name="pinbar")
    await signal_repo.save_signal(signal, signal_id="active-001", status="ACTIVE")

    dedup_key = "BTC/USDT:USDT:15m:LONG:pinbar"
    active = await signal_repo.get_active_signal(dedup_key)
    assert active is not None
    assert active["signal_id"] == "active-001"
    assert active["direction"] == "LONG"


@pytest.mark.asyncio
async def test_get_active_signal_no_match(signal_repo):
    dedup_key = "BTC/USDT:USDT:15m:LONG:pinbar"
    result = await signal_repo.get_active_signal(dedup_key)
    assert result is None


@pytest.mark.asyncio
async def test_get_active_signal_ignores_pending(signal_repo):
    signal = make_signal(direction=Direction.LONG, strategy_name="pinbar")
    await signal_repo.save_signal(signal, signal_id="pending-001", status="PENDING")

    dedup_key = "BTC/USDT:USDT:15m:LONG:pinbar"
    result = await signal_repo.get_active_signal(dedup_key)
    assert result is None


# ---------------------------------------------------------------------------
# 3. get_opposing_signal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_opposing_signal(signal_repo):
    long_signal = make_signal(direction=Direction.LONG)
    short_signal = make_signal(direction=Direction.SHORT, entry_price=Decimal("49000.00"),
                               suggested_stop_loss=Decimal("50000.00"))
    await signal_repo.save_signal(long_signal, signal_id="opp-long-001", status="ACTIVE")
    await signal_repo.save_signal(short_signal, signal_id="opp-short-001", status="ACTIVE")

    opposing = await signal_repo.get_opposing_signal("BTC/USDT:USDT", "15m", "LONG")
    assert opposing is not None
    assert opposing["direction"] == "SHORT"
    assert opposing["signal_id"] == "opp-short-001"


@pytest.mark.asyncio
async def test_get_opposing_signal_none(signal_repo):
    result = await signal_repo.get_opposing_signal("BTC/USDT:USDT", "15m", "LONG")
    assert result is None


# ---------------------------------------------------------------------------
# 4. get_pending_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_signals(signal_repo):
    s1 = make_signal(symbol="BTC/USDT:USDT")
    s2 = make_signal(symbol="BTC/USDT:USDT")
    s3 = make_signal(symbol="ETH/USDT:USDT", entry_price=Decimal("3000.00"),
                     suggested_stop_loss=Decimal("2900.00"))
    await signal_repo.save_signal(s1, signal_id="pend-001", status="PENDING")
    await signal_repo.save_signal(s2, signal_id="pend-002", status="PENDING")
    await signal_repo.save_signal(s3, signal_id="pend-003", status="PENDING")

    pending = await signal_repo.get_pending_signals("BTC/USDT:USDT")
    assert len(pending) == 2
    symbols = {p["symbol"] for p in pending}
    assert symbols == {"BTC/USDT:USDT"}


@pytest.mark.asyncio
async def test_get_pending_signals_excludes_non_pending(signal_repo):
    s1 = make_signal()
    await signal_repo.save_signal(s1, signal_id="pend-active-001", status="ACTIVE")

    pending = await signal_repo.get_pending_signals("BTC/USDT:USDT")
    assert len(pending) == 0


# ---------------------------------------------------------------------------
# 5. update_signal_status_by_tracker_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_signal_status_by_tracker_id(signal_repo):
    signal = make_signal()
    await signal_repo.save_signal(signal, signal_id="upd-001")

    await signal_repo.update_signal_status_by_tracker_id("upd-001", "ACTIVE")
    loaded = await signal_repo.get_signal_by_tracker_id("upd-001")
    assert loaded is not None
    assert loaded["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_update_signal_status_nonexistent(signal_repo):
    # Should not raise — silently ignores missing signal
    await signal_repo.update_signal_status_by_tracker_id("nonexistent", "ACTIVE")


# ---------------------------------------------------------------------------
# 6. update_superseded_by
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_superseded_by(signal_repo):
    old_signal = make_signal()
    await signal_repo.save_signal(old_signal, signal_id="super-old-001", status="ACTIVE")

    await signal_repo.update_superseded_by("super-old-001", "super-new-001")
    loaded = await signal_repo.get_signal_by_tracker_id("super-old-001")
    assert loaded is not None
    assert loaded["superseded_by"] == "super-new-001"
    assert loaded["status"] == "SUPERSEDED"


@pytest.mark.asyncio
async def test_update_superseded_by_nonexistent(signal_repo):
    await signal_repo.update_superseded_by("nonexistent", "anything")


# ---------------------------------------------------------------------------
# 7. get_signals (default live source)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_signals_default_live(signal_repo):
    s1 = make_signal()
    s2 = make_signal(strategy_name="engulfing")
    await signal_repo.save_signal(s1, signal_id="gs-001")
    await signal_repo.save_signal(s2, signal_id="gs-002")

    result = await signal_repo.get_signals()
    assert result["total"] == 2
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_get_signals_filters(signal_repo):
    s1 = make_signal(strategy_name="pinbar")
    s2 = make_signal(strategy_name="engulfing")
    await signal_repo.save_signal(s1, signal_id="gs-f-001")
    await signal_repo.save_signal(s2, signal_id="gs-f-002")

    result = await signal_repo.get_signals(strategy_name="pinbar")
    assert result["total"] == 1
    assert result["data"][0]["strategy_name"] == "pinbar"


@pytest.mark.asyncio
async def test_get_signals_backtest_source_returns_empty(signal_repo):
    s1 = make_signal()
    await signal_repo.save_signal(s1, signal_id="gs-bt-001")

    result = await signal_repo.get_signals(source="backtest")
    assert result["total"] == 0
    assert result["data"] == []


@pytest.mark.asyncio
async def test_get_signals_pagination(signal_repo):
    for i in range(5):
        await signal_repo.save_signal(make_signal(), signal_id=f"gs-page-{i:03d}")

    page1 = await signal_repo.get_signals(limit=2, offset=0)
    page2 = await signal_repo.get_signals(limit=2, offset=2)
    assert len(page1["data"]) == 2
    assert len(page2["data"]) == 2
    ids_p1 = {d["signal_id"] for d in page1["data"]}
    ids_p2 = {d["signal_id"] for d in page2["data"]}
    assert ids_p1.isdisjoint(ids_p2)


@pytest.mark.asyncio
async def test_get_signals_via_signal_query(signal_repo):
    await signal_repo.save_signal(make_signal(), signal_id="gs-sq-001")
    query = SignalQuery(limit=10, offset=0, symbol="BTC/USDT:USDT")
    result = await signal_repo.get_signals(query=query)
    assert result["total"] >= 1


# ---------------------------------------------------------------------------
# 8. get_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_stats(signal_repo):
    s1 = make_signal(direction=Direction.LONG)
    s2 = make_signal(direction=Direction.SHORT, entry_price=Decimal("49000.00"),
                     suggested_stop_loss=Decimal("50000.00"))
    await signal_repo.save_signal(s1, signal_id="stat-001")
    await signal_repo.save_signal(s2, signal_id="stat-002")

    stats = await signal_repo.get_stats()
    assert stats["total"] == 2
    assert stats["long_count"] == 1
    assert stats["short_count"] == 1
    assert stats["won_count"] == 0
    assert stats["lost_count"] == 0
    assert stats["win_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_stats_win_rate(signal_repo):
    s1 = make_signal()
    await signal_repo.save_signal(s1, signal_id="stat-w-001", status="WON")
    s2 = make_signal()
    await signal_repo.save_signal(s2, signal_id="stat-l-001", status="LOST")

    stats = await signal_repo.get_stats()
    assert stats["won_count"] == 1
    assert stats["lost_count"] == 1
    assert stats["win_rate"] == 0.5


# ---------------------------------------------------------------------------
# 9. clear_all_signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_all_signals(signal_repo):
    await signal_repo.save_signal(make_signal(), signal_id="clr-001")
    await signal_repo.save_signal(make_signal(), signal_id="clr-002")

    deleted = await signal_repo.clear_all_signals()
    assert deleted == 2

    result = await signal_repo.get_signals()
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# 10. signal_take_profits round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_profit_levels_round_trip(signal_repo):
    signal = make_signal(take_profit_levels=[
        {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "51500"},
        {"id": "TP2", "position_ratio": "0.3", "risk_reward": "2.5", "price": "52500"},
        {"id": "TP3", "position_ratio": "0.2", "risk_reward": "4.0", "price": "54000"},
    ])
    signal_id = await signal_repo.save_signal(signal, signal_id="tp-rt-001")

    loaded = await signal_repo.get_signal_by_tracker_id("tp-rt-001")
    assert loaded is not None
    tps = loaded["take_profit_levels"]
    assert len(tps) == 3
    assert tps[0]["tp_id"] == "TP1"
    assert Decimal(tps[0]["position_ratio"]) == Decimal("0.5")
    assert Decimal(tps[0]["risk_reward"]) == Decimal("1.5")
    assert Decimal(tps[0]["price_level"]) == Decimal("51500")
    assert tps[0]["status"] == "PENDING"
    assert tps[2]["tp_id"] == "TP3"


@pytest.mark.asyncio
async def test_take_profit_levels_empty(signal_repo):
    signal = make_signal(take_profit_levels=[])
    signal_id = await signal_repo.save_signal(signal, signal_id="tp-empty-001")

    loaded = await signal_repo.get_signal_by_tracker_id("tp-empty-001")
    assert loaded is not None
    assert loaded["take_profit_levels"] == []


@pytest.mark.asyncio
async def test_store_and_get_take_profit_levels(signal_repo):
    signal = make_signal(take_profit_levels=[])
    signal_id = await signal_repo.save_signal(signal, signal_id="tp-store-001")

    tps = [
        {"id": "TP1", "position_ratio": "0.6", "risk_reward": "2.0", "price": "52000"},
        {"id": "TP2", "position_ratio": "0.4", "risk_reward": "3.5", "price": "53500"},
    ]
    await signal_repo.store_take_profit_levels("tp-store-001", tps)

    loaded = await signal_repo.get_take_profit_levels("tp-store-001")
    assert len(loaded) == 2
    assert loaded[0]["tp_id"] == "TP1"
    assert Decimal(loaded[0]["position_ratio"]) == Decimal("0.6")
    assert Decimal(loaded[1]["price_level"]) == Decimal("53500")


@pytest.mark.asyncio
async def test_store_take_profit_replaces_existing(signal_repo):
    signal = make_signal(take_profit_levels=[
        {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "51500"},
    ])
    signal_id = await signal_repo.save_signal(signal, signal_id="tp-replace-001")

    new_tps = [
        {"id": "TP1", "position_ratio": "0.7", "risk_reward": "2.0", "price": "52000"},
        {"id": "TP2", "position_ratio": "0.3", "risk_reward": "4.0", "price": "54000"},
    ]
    await signal_repo.store_take_profit_levels("tp-replace-001", new_tps)

    loaded = await signal_repo.get_take_profit_levels("tp-replace-001")
    assert len(loaded) == 2
    assert Decimal(loaded[0]["position_ratio"]) == Decimal("0.7")


# ---------------------------------------------------------------------------
# 11. PG constraints on signals / signal_take_profits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_constraint_invalid_direction(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalORM(
            signal_id="const-001",
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction="INVALID",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            position_size=Decimal("0.001"),
            leverage=10,
            tags_json=[],
            risk_info="",
            status="PENDING",
            strategy_name="pinbar",
            score=Decimal("0.85"),
            source="live",
            pattern_score=Decimal("0.85"),
            ema_trend="",
            mtf_status="",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_negative_entry_price(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalORM(
            signal_id="const-002",
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction="LONG",
            entry_price=Decimal("-50000"),
            stop_loss=Decimal("49000"),
            position_size=Decimal("0.001"),
            leverage=10,
            tags_json=[],
            risk_info="",
            status="PENDING",
            strategy_name="pinbar",
            score=Decimal("0.85"),
            source="live",
            pattern_score=Decimal("0.85"),
            ema_trend="",
            mtf_status="",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_zero_leverage(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalORM(
            signal_id="const-003",
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            position_size=Decimal("0.001"),
            leverage=0,
            tags_json=[],
            risk_info="",
            status="PENDING",
            strategy_name="pinbar",
            score=Decimal("0.85"),
            source="live",
            pattern_score=Decimal("0.85"),
            ema_trend="",
            mtf_status="",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_negative_position_size(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalORM(
            signal_id="const-004",
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            position_size=Decimal("-0.001"),
            leverage=10,
            tags_json=[],
            risk_info="",
            status="PENDING",
            strategy_name="pinbar",
            score=Decimal("0.85"),
            source="live",
            pattern_score=Decimal("0.85"),
            ema_trend="",
            mtf_status="",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_tp_negative_price_level(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalTakeProfitORM(
            signal_id="const-tp-001",
            tp_id="TP1",
            position_ratio=Decimal("0.5"),
            risk_reward=Decimal("1.5"),
            price_level=Decimal("-51500"),
            status="PENDING",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_tp_negative_risk_reward(pg_session_maker):
    async with pg_session_maker() as session:
        orm = PGSignalTakeProfitORM(
            signal_id="const-tp-002",
            tp_id="TP1",
            position_ratio=Decimal("0.5"),
            risk_reward=Decimal("-1.5"),
            price_level=Decimal("51500"),
            status="PENDING",
        )
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_signal_id_unique(pg_session_maker):
    async with pg_session_maker() as session:
        ts = datetime.now(timezone.utc).isoformat()
        for _ in range(2):
            orm = PGSignalORM(
                signal_id="dup-sig-id",
                created_at=ts,
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                direction="LONG",
                entry_price=Decimal("50000"),
                stop_loss=Decimal("49000"),
                position_size=Decimal("0.001"),
                leverage=10,
                tags_json=[],
                risk_info="",
                status="PENDING",
                strategy_name="pinbar",
                score=Decimal("0.85"),
                source="live",
                pattern_score=Decimal("0.85"),
                ema_trend="",
                mtf_status="",
            )
            session.add(orm)
        # merge() in save_signal avoids this, but raw insert should fail on duplicate
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_constraint_tp_fk_cascade(pg_session_maker):
    """signal_take_profits FK → signals.signal_id with CASCADE delete."""
    async with pg_session_maker() as session:
        sig = PGSignalORM(
            signal_id="fk-cascade-001",
            created_at=datetime.now(timezone.utc).isoformat(),
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction="LONG",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            position_size=Decimal("0.001"),
            leverage=10,
            tags_json=[],
            risk_info="",
            status="PENDING",
            strategy_name="pinbar",
            score=Decimal("0.85"),
            source="live",
            pattern_score=Decimal("0.85"),
            ema_trend="",
            mtf_status="",
        )
        session.add(sig)
        await session.flush()

        tp = PGSignalTakeProfitORM(
            signal_id="fk-cascade-001",
            tp_id="TP1",
            position_ratio=Decimal("0.5"),
            risk_reward=Decimal("1.5"),
            price_level=Decimal("51500"),
            status="PENDING",
        )
        session.add(tp)
        await session.commit()

    # Delete the signal, TP should cascade
    async with pg_session_maker() as session:
        from sqlalchemy import delete as sa_delete
        await session.execute(sa_delete(PGSignalORM).where(PGSignalORM.signal_id == "fk-cascade-001"))
        await session.commit()

    async with pg_session_maker() as session:
        from sqlalchemy import select
        remaining = (await session.execute(
            select(PGSignalTakeProfitORM).where(PGSignalTakeProfitORM.signal_id == "fk-cascade-001")
        )).scalars().all()
        assert len(remaining) == 0
