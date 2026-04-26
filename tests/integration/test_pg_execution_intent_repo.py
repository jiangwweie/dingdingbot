"""PG integration tests for PgExecutionIntentRepository.

Covers: save/get round trip, list by status, list_unfinished,
signal_payload JSONB round trip, strategy_payload JSONB round trip,
blocked/failed fields, unique order_id/exchange_order_id, status check constraint.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, OrderStrategy, SignalResult
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_models import PGExecutionIntentORM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STRATEGY = OrderStrategy(
    id="test-strategy",
    name="Test Strategy",
    tp_levels=2,
    tp_ratios=[Decimal("0.6"), Decimal("0.4")],
    tp_targets=[Decimal("1.5"), Decimal("3.0")],
)


def _signal(**overrides) -> SignalResult:
    defaults = dict(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        direction=Direction.LONG,
        entry_price=Decimal("50000"),
        suggested_stop_loss=Decimal("49000"),
        suggested_position_size=Decimal("0.001"),
        current_leverage=10,
        tags=[],
        risk_reward_info="Risk 1% = 50 USDT",
        strategy_name="pinbar",
        score=0.8,
    )
    defaults.update(overrides)
    return SignalResult(**defaults)


def make_intent(**overrides) -> ExecutionIntent:
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    defaults = dict(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        signal=_signal(),
        status=ExecutionIntentStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return ExecutionIntent(**defaults)


# ---------------------------------------------------------------------------
# 1. save / get round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_get_round_trip(intent_repo: PgExecutionIntentRepository):
    intent = make_intent()
    await intent_repo.save(intent)

    loaded = await intent_repo.get(intent.id)

    assert loaded is not None
    assert loaded.id == intent.id
    assert loaded.signal_id == intent.signal_id
    assert loaded.status == intent.status
    assert loaded.signal.symbol == intent.signal.symbol
    assert loaded.signal.entry_price == intent.signal.entry_price
    assert loaded.signal.score == intent.signal.score
    assert loaded.created_at == intent.created_at
    assert loaded.updated_at == intent.updated_at


# ---------------------------------------------------------------------------
# 2. list(status=...) filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_status(intent_repo: PgExecutionIntentRepository):
    pending = make_intent(status=ExecutionIntentStatus.PENDING)
    submitted = make_intent(status=ExecutionIntentStatus.SUBMITTED)
    failed = make_intent(status=ExecutionIntentStatus.FAILED)

    await intent_repo.save(pending)
    await intent_repo.save(submitted)
    await intent_repo.save(failed)

    only_pending = await intent_repo.list(status=ExecutionIntentStatus.PENDING)
    assert len(only_pending) == 1
    assert only_pending[0].id == pending.id

    only_submitted = await intent_repo.list(status=ExecutionIntentStatus.SUBMITTED)
    assert len(only_submitted) == 1
    assert only_submitted[0].id == submitted.id

    all_intents = await intent_repo.list()
    assert len(all_intents) == 3


# ---------------------------------------------------------------------------
# 3. list_unfinished() returns only non-terminal intents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_unfinished(intent_repo: PgExecutionIntentRepository):
    # Non-terminal
    pending = make_intent(status=ExecutionIntentStatus.PENDING)
    submitted = make_intent(status=ExecutionIntentStatus.SUBMITTED)
    protecting = make_intent(status=ExecutionIntentStatus.PROTECTING)
    partial = make_intent(status=ExecutionIntentStatus.PARTIALLY_PROTECTED)

    # Terminal
    blocked = make_intent(status=ExecutionIntentStatus.BLOCKED)
    failed = make_intent(status=ExecutionIntentStatus.FAILED)
    completed = make_intent(status=ExecutionIntentStatus.COMPLETED)

    for i in (pending, submitted, protecting, partial, blocked, failed, completed):
        await intent_repo.save(i)

    unfinished = await intent_repo.list_unfinished()
    unfinished_ids = {x.id for x in unfinished}

    assert pending.id in unfinished_ids
    assert submitted.id in unfinished_ids
    assert protecting.id in unfinished_ids
    assert partial.id in unfinished_ids

    assert blocked.id not in unfinished_ids
    assert failed.id not in unfinished_ids
    assert completed.id not in unfinished_ids


# ---------------------------------------------------------------------------
# 4. signal_payload JSONB round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_payload_jsonb_round_trip(intent_repo: PgExecutionIntentRepository):
    signal = _signal(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        direction=Direction.SHORT,
        entry_price=Decimal("3200.50"),
        suggested_stop_loss=Decimal("3350"),
        suggested_position_size=Decimal("0.5"),
        current_leverage=20,
        tags=[{"name": "EMA", "value": "Bearish"}, {"name": "MTF", "value": "Confirmed"}],
        risk_reward_info="Risk 2% = 75 USDT",
        strategy_name="engulfing",
        score=0.65,
    )
    intent = make_intent(signal=signal)
    await intent_repo.save(intent)

    loaded = await intent_repo.get(intent.id)

    assert loaded is not None
    s = loaded.signal
    assert s.symbol == "ETH/USDT:USDT"
    assert s.timeframe == "1h"
    assert s.direction == Direction.SHORT
    assert s.entry_price == Decimal("3200.50")
    assert s.suggested_stop_loss == Decimal("3350")
    assert s.suggested_position_size == Decimal("0.5")
    assert s.current_leverage == 20
    assert len(s.tags) == 2
    assert s.tags[0] == {"name": "EMA", "value": "Bearish"}
    assert s.risk_reward_info == "Risk 2% = 75 USDT"
    assert s.strategy_name == "engulfing"
    assert s.score == 0.65


# ---------------------------------------------------------------------------
# 5. strategy_payload JSONB round trip (with and without strategy)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_payload_round_trip(intent_repo: PgExecutionIntentRepository):
    intent_with = make_intent(strategy=_STRATEGY)
    await intent_repo.save(intent_with)

    loaded = await intent_repo.get(intent_with.id)
    assert loaded is not None
    assert loaded.strategy is not None
    assert loaded.strategy.id == "test-strategy"
    assert loaded.strategy.name == "Test Strategy"
    assert loaded.strategy.tp_levels == 2
    assert loaded.strategy.tp_ratios == [Decimal("0.6"), Decimal("0.4")]
    assert loaded.strategy.tp_targets == [Decimal("1.5"), Decimal("3.0")]


@pytest.mark.asyncio
async def test_strategy_payload_none_round_trip(intent_repo: PgExecutionIntentRepository):
    intent_no_strategy = make_intent(strategy=None)
    await intent_repo.save(intent_no_strategy)

    loaded = await intent_repo.get(intent_no_strategy.id)
    assert loaded is not None
    assert loaded.strategy is None


# ---------------------------------------------------------------------------
# 6. blocked / failed fields round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_fields_round_trip(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(
        status=ExecutionIntentStatus.BLOCKED,
        blocked_reason="DAILY_LOSS_LIMIT",
        blocked_message="Daily loss limit exceeded: 500 USDT",
    )
    await intent_repo.save(intent)

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.BLOCKED
    assert loaded.blocked_reason == "DAILY_LOSS_LIMIT"
    assert loaded.blocked_message == "Daily loss limit exceeded: 500 USDT"


@pytest.mark.asyncio
async def test_failed_fields_round_trip(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(
        status=ExecutionIntentStatus.FAILED,
        failed_reason="INSUFFICIENT_MARGIN",
    )
    await intent_repo.save(intent)

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.FAILED
    assert loaded.failed_reason == "INSUFFICIENT_MARGIN"


# ---------------------------------------------------------------------------
# 7. unique order_id / exchange_order_id (partial unique index)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_order_id_violates_unique(
    intent_repo: PgExecutionIntentRepository,
    pg_session_maker: async_sessionmaker[AsyncSession],
):
    shared_order_id = "order-123"

    intent_a = make_intent(
        status=ExecutionIntentStatus.SUBMITTED,
        order_id=shared_order_id,
    )
    await intent_repo.save(intent_a)

    intent_b = make_intent(
        status=ExecutionIntentStatus.SUBMITTED,
        order_id=shared_order_id,
    )
    # save uses merge (upsert by PK), so it will not violate the unique index
    # because intent_b has a different PK. Insert directly via ORM to trigger the constraint.
    from sqlalchemy.exc import IntegrityError

    orm_b = PgExecutionIntentRepository._to_orm(intent_b)
    async with pg_session_maker() as session:
        session.add(orm_b)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_duplicate_exchange_order_id_violates_unique(
    intent_repo: PgExecutionIntentRepository,
    pg_session_maker: async_sessionmaker[AsyncSession],
):
    shared_exchange_id = "ex-order-999"

    intent_a = make_intent(
        status=ExecutionIntentStatus.SUBMITTED,
        exchange_order_id=shared_exchange_id,
    )
    await intent_repo.save(intent_a)

    intent_b = make_intent(
        status=ExecutionIntentStatus.SUBMITTED,
        exchange_order_id=shared_exchange_id,
    )
    from sqlalchemy.exc import IntegrityError

    orm_b = PgExecutionIntentRepository._to_orm(intent_b)
    async with pg_session_maker() as session:
        session.add(orm_b)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_multiple_null_order_id_allowed(
    intent_repo: PgExecutionIntentRepository,
):
    # Partial unique index: NULL order_id should not conflict
    a = make_intent(order_id=None)
    b = make_intent(order_id=None)
    await intent_repo.save(a)
    await intent_repo.save(b)

    loaded_a = await intent_repo.get(a.id)
    loaded_b = await intent_repo.get(b.id)
    assert loaded_a is not None
    assert loaded_b is not None
    assert loaded_a.order_id is None
    assert loaded_b.order_id is None


# ---------------------------------------------------------------------------
# 8. status check constraint — invalid value raises IntegrityError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_status_check_constraint(
    pg_session_maker: async_sessionmaker[AsyncSession],
):
    from sqlalchemy.exc import IntegrityError

    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    orm = PGExecutionIntentORM(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        symbol="BTC/USDT:USDT",
        status="INVALID_STATUS",
        signal_payload=_signal().model_dump(mode="json"),
        created_at=now,
        updated_at=now,
    )
    async with pg_session_maker() as session:
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# ---------------------------------------------------------------------------
# 9. update_status round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_to_submitted(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(status=ExecutionIntentStatus.PENDING)
    await intent_repo.save(intent)

    await intent_repo.update_status(
        intent_id=intent.id,
        status=ExecutionIntentStatus.SUBMITTED,
        order_id="order-001",
        exchange_order_id="ex-order-001",
    )

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.SUBMITTED
    assert loaded.order_id == "order-001"
    assert loaded.exchange_order_id == "ex-order-001"


@pytest.mark.asyncio
async def test_update_status_to_blocked(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(status=ExecutionIntentStatus.PENDING)
    await intent_repo.save(intent)

    await intent_repo.update_status(
        intent_id=intent.id,
        status=ExecutionIntentStatus.BLOCKED,
        blocked_reason="DAILY_LOSS_LIMIT",
        blocked_message="Daily loss exceeded",
    )

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.BLOCKED
    assert loaded.blocked_reason == "DAILY_LOSS_LIMIT"
    assert loaded.blocked_message == "Daily loss exceeded"


@pytest.mark.asyncio
async def test_update_status_to_failed(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(status=ExecutionIntentStatus.PENDING)
    await intent_repo.save(intent)

    await intent_repo.update_status(
        intent_id=intent.id,
        status=ExecutionIntentStatus.FAILED,
        failed_reason="EXCHANGE_ERROR",
    )

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.FAILED
    assert loaded.failed_reason == "EXCHANGE_ERROR"


# ---------------------------------------------------------------------------
# 10. get_by_signal_id / get_by_order_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_signal_id(intent_repo: PgExecutionIntentRepository):
    signal_id = str(uuid4())
    intent = make_intent(signal_id=signal_id)
    await intent_repo.save(intent)

    loaded = await intent_repo.get_by_signal_id(signal_id)
    assert loaded is not None
    assert loaded.id == intent.id

    assert await intent_repo.get_by_signal_id("no-such-signal") is None


@pytest.mark.asyncio
async def test_get_by_order_id(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(
        status=ExecutionIntentStatus.SUBMITTED,
        order_id="order-lookup-001",
    )
    await intent_repo.save(intent)

    loaded = await intent_repo.get_by_order_id("order-lookup-001")
    assert loaded is not None
    assert loaded.id == intent.id

    assert await intent_repo.get_by_order_id("no-such-order") is None


# ---------------------------------------------------------------------------
# 11. save upsert semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_upsert(intent_repo: PgExecutionIntentRepository):
    intent = make_intent(status=ExecutionIntentStatus.PENDING)
    await intent_repo.save(intent)

    updated = make_intent(
        id=intent.id,
        signal_id=intent.signal_id,
        signal=intent.signal,
        status=ExecutionIntentStatus.SUBMITTED,
        created_at=intent.created_at,
        updated_at=intent.updated_at,
    )
    await intent_repo.save(updated)

    loaded = await intent_repo.get(intent.id)
    assert loaded is not None
    assert loaded.status == ExecutionIntentStatus.SUBMITTED
