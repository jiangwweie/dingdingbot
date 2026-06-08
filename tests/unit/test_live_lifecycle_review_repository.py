from __future__ import annotations

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.infrastructure.pg_live_lifecycle_review_repository import PgLiveLifecycleReviewRepository
from src.infrastructure.pg_models import PGBrcLiveLifecycleReviewORM


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcLiveLifecycleReviewORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgLiveLifecycleReviewRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _record(review_id: str = "live-review-auth-1-pending-open") -> BrcLiveLifecycleReviewRecord:
    return BrcLiveLifecycleReviewRecord(
        review_id=review_id,
        authorization_id="auth-1",
        carrier_id="MR-001-live-readonly-v0",
        strategy_family_id="MR-001",
        symbol="ETH/USDT:USDT",
        side="long",
        quantity="0.014",
        max_notional="25",
        leverage="1",
        max_attempts=1,
        lifecycle_status="protected_open",
        review_status="pending_open",
        final_gate_result="passed",
        protection_status="matched_tp_sl",
        execution_intent_id="intent-1",
        entry_order_id="entry-1",
        entry_exchange_order_id="exchange-entry-1",
        tp_order_ids=["tp-1"],
        tp_exchange_order_ids=["exchange-tp-1"],
        sl_order_id="sl-1",
        sl_exchange_order_id="exchange-sl-1",
        tp_price="1700",
        sl_trigger="1670",
        owner_risk_acceptance="owner_accepted_l3_bounded_live",
        hard_gates_passed=True,
        evidence_refs=["/tmp/evidence.json"],
        metadata={"source": "unit-test"},
        created_at_ms=1780496664000,
        updated_at_ms=1780496664000,
    )


@pytest.mark.asyncio
async def test_live_lifecycle_review_repository_appends_and_lists(repo):
    saved = await repo.append(_record())

    latest = await repo.get_latest(authorization_id="auth-1")
    listed = await repo.list(symbol="ETH/USDT:USDT", limit=10)

    assert saved.review_id == "live-review-auth-1-pending-open"
    assert latest.review_id == saved.review_id
    assert listed[0].review_status == "pending_open"
    assert listed[0].places_order is False
    assert listed[0].mutates_exchange is False
    assert listed[0].grants_trading_permission is False
    assert listed[0].frontend_action_enabled is False


def test_live_lifecycle_review_record_rejects_action_authority():
    payload = _record().model_dump()
    payload["places_order"] = True

    with pytest.raises(ValidationError):
        BrcLiveLifecycleReviewRecord(**payload)
