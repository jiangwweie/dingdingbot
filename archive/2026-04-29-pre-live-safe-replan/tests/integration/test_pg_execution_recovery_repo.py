"""PG integration tests for PgExecutionRecoveryRepository.

Covers: create/get round trip, get_by_intent_id, list_active filtering,
list_blocking, mark_resolved, mark_retrying, mark_failed, delete,
context_payload JSONB round trip, CheckConstraint violations.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, SignalResult
from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository
from src.infrastructure.pg_models import PGExecutionRecoveryTaskORM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _create_intent(intent_repo) -> str:
    """Insert a prerequisite execution intent and return its id."""
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    intent = ExecutionIntent(
        id=str(uuid4()),
        signal_id=str(uuid4()),
        signal=_signal(),
        status=ExecutionIntentStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    await intent_repo.save(intent)
    return intent.id


# ---------------------------------------------------------------------------
# 1. create_task / get round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_get_round_trip(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())

    await recovery_repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        related_order_id="order-001",
        related_exchange_order_id="ex-order-001",
        error_message="SL order rejected by exchange",
    )

    result = await recovery_repo.get(task_id)

    assert result is not None
    assert result["id"] == task_id
    assert result["intent_id"] == intent_id
    assert result["symbol"] == "BTC/USDT:USDT"
    assert result["recovery_type"] == "replace_sl_failed"
    assert result["status"] == "pending"
    assert result["related_order_id"] == "order-001"
    assert result["related_exchange_order_id"] == "ex-order-001"
    assert result["error_message"] == "SL order rejected by exchange"
    assert result["retry_count"] == 0
    assert result["next_retry_at"] is None
    assert result["context_payload"] is None
    assert result["resolved_at"] is None
    assert result["created_at"] > 0
    assert result["updated_at"] > 0


@pytest.mark.asyncio
async def test_get_nonexistent_returns_none(
    recovery_repo: PgExecutionRecoveryRepository,
):
    assert await recovery_repo.get("no-such-id") is None


# ---------------------------------------------------------------------------
# 2. get_by_intent_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_intent_id(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())

    await recovery_repo.create_task(
        task_id=task_id,
        intent_id=intent_id,
        symbol="ETH/USDT:USDT",
        recovery_type="replace_sl_failed",
    )

    result = await recovery_repo.get_by_intent_id(intent_id)

    assert result is not None
    assert result["id"] == task_id
    assert result["intent_id"] == intent_id


@pytest.mark.asyncio
async def test_get_by_intent_id_not_found(
    recovery_repo: PgExecutionRecoveryRepository,
):
    assert await recovery_repo.get_by_intent_id("no-such-intent") is None


# ---------------------------------------------------------------------------
# 3. list_active — status + next_retry_at filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_active_filters_by_status_and_next_retry_at(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    # Create 4 intents (one per task)
    intent_id_1 = await _create_intent(intent_repo)
    intent_id_2 = await _create_intent(intent_repo)
    intent_id_3 = await _create_intent(intent_repo)
    intent_id_4 = await _create_intent(intent_repo)

    # pending, next_retry_at=NULL -> active
    await recovery_repo.create_task(
        task_id="task-pending", intent_id=intent_id_1,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )

    # retrying, next_retry_at in the past -> active
    await recovery_repo.create_task(
        task_id="task-retrying-past", intent_id=intent_id_2,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    await recovery_repo.mark_retrying(
        task_id="task-retrying-past", retry_count=1, next_retry_at=now - 1000,
    )

    # retrying, next_retry_at in the future -> NOT active
    await recovery_repo.create_task(
        task_id="task-retrying-future", intent_id=intent_id_3,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    await recovery_repo.mark_retrying(
        task_id="task-retrying-future", retry_count=1, next_retry_at=now + 60000,
    )

    # resolved -> NOT active
    await recovery_repo.create_task(
        task_id="task-resolved", intent_id=intent_id_4,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    await recovery_repo.mark_resolved(task_id="task-resolved", resolved_at=now)

    active = await recovery_repo.list_active(now_ms=now)
    active_ids = {t["id"] for t in active}

    assert "task-pending" in active_ids
    assert "task-retrying-past" in active_ids
    assert "task-retrying-future" not in active_ids
    assert "task-resolved" not in active_ids


# ---------------------------------------------------------------------------
# 4. list_blocking — only status matters, ignores next_retry_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_blocking_ignores_next_retry_at(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    intent_id_1 = await _create_intent(intent_repo)
    intent_id_2 = await _create_intent(intent_repo)
    intent_id_3 = await _create_intent(intent_repo)

    # pending -> blocking
    await recovery_repo.create_task(
        task_id="blk-pending", intent_id=intent_id_1,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )

    # retrying with future next_retry_at -> still blocking
    await recovery_repo.create_task(
        task_id="blk-retrying", intent_id=intent_id_2,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    await recovery_repo.mark_retrying(
        task_id="blk-retrying", retry_count=2, next_retry_at=now + 60000,
    )

    # resolved -> NOT blocking
    await recovery_repo.create_task(
        task_id="blk-resolved", intent_id=intent_id_3,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    await recovery_repo.mark_resolved(task_id="blk-resolved", resolved_at=now)

    blocking = await recovery_repo.list_blocking()
    blocking_ids = {t["id"] for t in blocking}

    assert "blk-pending" in blocking_ids
    assert "blk-retrying" in blocking_ids
    assert "blk-resolved" not in blocking_ids


# ---------------------------------------------------------------------------
# 5. mark_resolved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_resolved(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())
    resolved_at = int(datetime.now(timezone.utc).timestamp() * 1000)

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
        error_message="original error",
    )

    await recovery_repo.mark_resolved(
        task_id=task_id, resolved_at=resolved_at,
        error_message="resolved with note",
    )

    result = await recovery_repo.get(task_id)
    assert result["status"] == "resolved"
    assert result["resolved_at"] == resolved_at
    assert result["error_message"] == "resolved with note"


# ---------------------------------------------------------------------------
# 6. mark_retrying
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_retrying(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())
    next_retry = int(datetime.now(timezone.utc).timestamp() * 1000) + 30000

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )

    await recovery_repo.mark_retrying(
        task_id=task_id, retry_count=3, next_retry_at=next_retry,
        error_message="retry attempt 3 failed",
    )

    result = await recovery_repo.get(task_id)
    assert result["status"] == "retrying"
    assert result["retry_count"] == 3
    assert result["next_retry_at"] == next_retry
    assert result["error_message"] == "retry attempt 3 failed"


# ---------------------------------------------------------------------------
# 7. mark_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_failed(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )

    await recovery_repo.mark_failed(
        task_id=task_id, error_message="max retries exceeded",
    )

    result = await recovery_repo.get(task_id)
    assert result["status"] == "failed"
    assert result["error_message"] == "max retries exceeded"


# ---------------------------------------------------------------------------
# 8. delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )
    assert await recovery_repo.get(task_id) is not None

    await recovery_repo.delete(task_id)
    assert await recovery_repo.get(task_id) is None


# ---------------------------------------------------------------------------
# 9. context_payload JSONB round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_payload_jsonb_round_trip(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())
    payload = {
        "sl_order_id": "order-sl-001",
        "original_sl_price": "49000",
        "attempted_sl_price": "48500",
        "nested": {"key": "value", "list": [1, 2, 3]},
    }

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
        context_payload=payload,
    )

    result = await recovery_repo.get(task_id)
    assert result["context_payload"] == payload


@pytest.mark.asyncio
async def test_context_payload_none_by_default(
    recovery_repo: PgExecutionRecoveryRepository,
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    task_id = str(uuid4())

    await recovery_repo.create_task(
        task_id=task_id, intent_id=intent_id,
        symbol="BTC/USDT:USDT", recovery_type="replace_sl_failed",
    )

    result = await recovery_repo.get(task_id)
    assert result["context_payload"] is None


# ---------------------------------------------------------------------------
# 10. CheckConstraint violations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_recovery_type_check_constraint(
    pg_session_maker: async_sessionmaker[AsyncSession],
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orm = PGExecutionRecoveryTaskORM(
        id=str(uuid4()),
        intent_id=intent_id,
        symbol="BTC/USDT:USDT",
        recovery_type="invalid_type",
        status="pending",
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    async with pg_session_maker() as session:
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_invalid_status_check_constraint(
    pg_session_maker: async_sessionmaker[AsyncSession],
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orm = PGExecutionRecoveryTaskORM(
        id=str(uuid4()),
        intent_id=intent_id,
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="invalid_status",
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    async with pg_session_maker() as session:
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_negative_retry_count_check_constraint(
    pg_session_maker: async_sessionmaker[AsyncSession],
    intent_repo,
):
    intent_id = await _create_intent(intent_repo)
    now = int(datetime.now(timezone.utc).timestamp() * 1000)

    orm = PGExecutionRecoveryTaskORM(
        id=str(uuid4()),
        intent_id=intent_id,
        symbol="BTC/USDT:USDT",
        recovery_type="replace_sl_failed",
        status="pending",
        retry_count=-1,
        created_at=now,
        updated_at=now,
    )
    async with pg_session_maker() as session:
        session.add(orm)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()