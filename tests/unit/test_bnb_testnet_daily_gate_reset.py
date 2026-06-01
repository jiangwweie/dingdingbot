from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.testnet_daily_gate_reset import (
    BNB_TESTNET_CARRIER_ID,
    BNB_TESTNET_PROFILE,
    BNB_TESTNET_SYMBOL,
    DailyGateResetRefusal,
    DailyGateResetRequest,
    build_bnb_testnet_daily_gate_reset_plan,
)
from src.infrastructure.pg_models import PGDailyRiskStatsAggregateORM
from src.infrastructure.pg_testnet_daily_gate_reset import PgTestnetDailyGateResetRepository


STATS_DATE = date(2026, 6, 1)


@pytest_asyncio.fixture()
async def session_maker():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGDailyRiskStatsAggregateORM.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


def _request(**overrides) -> DailyGateResetRequest:
    data = {
        "profile_name": BNB_TESTNET_PROFILE,
        "trading_env": "testnet",
        "exchange_testnet": True,
        "symbol": BNB_TESTNET_SYMBOL,
        "carrier_id": BNB_TESTNET_CARRIER_ID,
        "stats_date": STATS_DATE,
    }
    data.update(overrides)
    return DailyGateResetRequest(**data)


def test_daily_counter_reset_refuses_live_mode():
    with pytest.raises(DailyGateResetRefusal, match="refuse_live_trading_env"):
        build_bnb_testnet_daily_gate_reset_plan(
            _request(trading_env="live", exchange_testnet=False)
        )


def test_daily_counter_reset_refuses_missing_profile():
    with pytest.raises(DailyGateResetRefusal, match="refuse_missing_profile"):
        build_bnb_testnet_daily_gate_reset_plan(_request(profile_name=None))


def test_daily_counter_reset_refuses_broad_or_unknown_profile():
    with pytest.raises(DailyGateResetRefusal, match="refuse_unapproved_profile"):
        build_bnb_testnet_daily_gate_reset_plan(_request(profile_name="runtime-default"))


def test_daily_counter_reset_refuses_exchange_testnet_false():
    with pytest.raises(DailyGateResetRefusal, match="refuse_exchange_testnet"):
        build_bnb_testnet_daily_gate_reset_plan(_request(exchange_testnet=False))


def test_daily_counter_reset_builds_only_strategy_trial_bnb_profile_scope():
    plan = build_bnb_testnet_daily_gate_reset_plan(_request())

    assert plan.scope_key == "runtime_profile:strategy_trial_bnb_testnet_runtime"
    assert plan.scope_classification == "strategy_trial_bnb_profile_counter"
    assert plan.live_ready is False
    assert plan.execution_permission_granted is False
    assert plan.order_permission_granted is False


@pytest.mark.asyncio
async def test_testnet_profile_scoped_counter_can_be_reset_safely(session_maker):
    plan = build_bnb_testnet_daily_gate_reset_plan(_request())
    async with session_maker() as session:
        async with session.begin():
            session.add(
                PGDailyRiskStatsAggregateORM(
                    scope_key=plan.scope_key,
                    stats_date=STATS_DATE,
                    realized_pnl=Decimal("-0.0099"),
                    trade_count=1,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                PGDailyRiskStatsAggregateORM(
                    scope_key="runtime:default",
                    stats_date=STATS_DATE,
                    realized_pnl=Decimal("-10"),
                    trade_count=7,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )

    result = await PgTestnetDailyGateResetRepository(session_maker).reset_trade_count(plan)

    assert result.row_found is True
    assert result.trade_count_before == 1
    assert result.trade_count_after == 0
    assert result.realized_pnl_before.quantize(Decimal("0.0001")) == Decimal("-0.0099")
    assert result.realized_pnl_after.quantize(Decimal("0.0001")) == Decimal("-0.0099")
    assert result.live_ready is False
    assert result.execution_permission_granted is False
    assert result.order_permission_granted is False

    async with session_maker() as session:
        rows = (
            await session.execute(
                select(PGDailyRiskStatsAggregateORM).order_by(
                    PGDailyRiskStatsAggregateORM.scope_key
                )
            )
        ).scalars().all()
    by_scope = {row.scope_key: row for row in rows}
    assert by_scope["runtime_profile:strategy_trial_bnb_testnet_runtime"].trade_count == 0
    assert by_scope["runtime:default"].trade_count == 7
