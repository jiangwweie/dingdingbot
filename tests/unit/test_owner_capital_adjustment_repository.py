from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.owner_capital_adjustment import (
    OwnerCapitalAdjustmentRecord,
    OwnerCapitalAdjustmentType,
)
from src.infrastructure.pg_models import PGOwnerCapitalAdjustmentORM
from src.infrastructure.pg_owner_capital_adjustment_repository import (
    PgOwnerCapitalAdjustmentRepository,
)


NOW_MS = 1781000000000


@pytest_asyncio.fixture()
async def owner_capital_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGOwnerCapitalAdjustmentORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgOwnerCapitalAdjustmentRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_capital_adjustment_repository_roundtrip(owner_capital_repo):
    record = OwnerCapitalAdjustmentRecord(
        adjustment_id="owner-withdrawal-repo-1",
        adjustment_type=OwnerCapitalAdjustmentType.OWNER_MANUAL_WITHDRAWAL,
        amount=Decimal("30"),
        reason="Owner manually withdrew profit outside the system.",
        occurred_at_ms=NOW_MS,
        recorded_by="owner",
        evidence_refs=["owner-note://repo-withdrawal-1"],
        metadata={"source": "unit-test"},
    )

    saved = await owner_capital_repo.append(record)
    loaded = await owner_capital_repo.get("owner-withdrawal-repo-1")
    listed = await owner_capital_repo.list(currency="USDT")

    assert saved.adjustment_id == record.adjustment_id
    assert loaded is not None
    assert loaded.adjustment_type == OwnerCapitalAdjustmentType.OWNER_MANUAL_WITHDRAWAL
    assert loaded.amount == Decimal("30.000000000000000000")
    assert loaded.evidence_refs == ["owner-note://repo-withdrawal-1"]
    assert listed[0].adjustment_id == "owner-withdrawal-repo-1"
    assert loaded.withdrawal_instruction_created is False
    assert loaded.transfer_instruction_created is False
    assert loaded.order_instruction_created is False
    assert loaded.exchange_called is False
    assert loaded.mutates_runtime_budget is False
    assert loaded.mutates_strategy_pnl is False
    assert loaded.creates_risk_event is False
