from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.bounded_risk_campaign import BrcReviewDecision, BrcReviewDecisionRecord
from src.infrastructure.pg_brc_campaign_repository import PgBrcCampaignRepository
from src.infrastructure.pg_models import PGBrcReviewDecisionORM


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcReviewDecisionORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgBrcCampaignRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _decision(review_id: str = "brc-review-test") -> BrcReviewDecisionRecord:
    return BrcReviewDecisionRecord(
        review_id=review_id,
        campaign_id="brc-campaign",
        source_action_id="brc-op-test",
        decision=BrcReviewDecision.ACCEPTED,
        reason_text="BRC reviewed",
        next_recommended_task="BRC-R2-005",
        created_by="owner",
        created_at_ms=1770000000000,
        metadata_json={"source": "unit-test"},
    )


@pytest.mark.asyncio
async def test_review_storage_compatibility_repository_appends_and_lists_records(repo):
    saved = await repo.append_review_decision(_decision())

    latest = await repo.get_latest_review_decision()
    listed = await repo.list_review_decisions(campaign_id="brc-campaign", limit=10)

    assert saved.review_id == "brc-review-test"
    assert latest.review_id == saved.review_id
    assert PGBrcReviewDecisionORM.__tablename__ == "brc_review_decisions"
    assert listed[0].decision == BrcReviewDecision.ACCEPTED
    assert listed[0].real_live_authorized is False
    assert listed[0].withdrawal_authorized is False
    assert listed[0].strategy_execution_authorized is False
