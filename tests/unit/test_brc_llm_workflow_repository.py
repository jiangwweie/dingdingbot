from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.bounded_risk_campaign import (
    BrcLlmIntent,
    BrcLlmIntentAction,
    BrcOperatorDecisionResult,
    BrcWorkflowRun,
    BrcWorkflowStatus,
)
from src.infrastructure.pg_brc_campaign_repository import PgBrcCampaignRepository
from src.infrastructure.pg_models import PGBrcLlmIntentORM, PGBrcWorkflowRunORM


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcLlmIntentORM.__table__.create)
        await conn.run_sync(PGBrcWorkflowRunORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgBrcCampaignRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _intent() -> BrcLlmIntent:
    return BrcLlmIntent(
        intent_id="brc-llm-test",
        workflow_run_id="brc-wf-test",
        source_text="帮我准备下一轮 testnet 演练",
        action=BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL,
        confidence=Decimal("0.9"),
        reason_text="Owner asks for controlled testnet rehearsal",
        provider_name="fake",
        model_name="fake-model",
        raw_response_summary={"keys": ["action", "confidence", "reason_text"]},
        decision_result=BrcOperatorDecisionResult.PLANNED,
        created_at_ms=1770000000000,
    )


def _workflow() -> BrcWorkflowRun:
    return BrcWorkflowRun(
        workflow_run_id="brc-wf-test",
        llm_intent_id="brc-llm-test",
        source_text="帮我准备下一轮 testnet 演练",
        action=BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL,
        status=BrcWorkflowStatus.AWAITING_CONFIRMATION,
        confirmation_phrase_id="CONFIRM_BRC_TESTNET_REHEARSAL",
        workflow_state_json={"fact_source": "brc_pg_tables"},
        created_at_ms=1770000000000,
        updated_at_ms=1770000000000,
    )


@pytest.mark.asyncio
async def test_llm_intent_repository_appends_and_lists_without_secret(repo):
    saved = await repo.save_llm_intent(_intent())
    loaded = await repo.get_llm_intent(saved.intent_id)
    listed = await repo.list_llm_intents(limit=10, action="request_testnet_rehearsal")

    assert loaded.intent_id == saved.intent_id
    assert listed[0].action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL
    serialized = loaded.model_dump(mode="json")
    assert "api_key" not in str(serialized).lower()
    assert "secret" not in str(serialized).lower()


@pytest.mark.asyncio
async def test_workflow_run_repository_updates_and_lists(repo):
    saved = await repo.save_workflow_run(_workflow())
    completed = saved.model_copy(
        update={
            "status": BrcWorkflowStatus.COMPLETED,
            "confirmation_matched": True,
            "confirmed_by": "owner",
            "result_json": {"ok": True},
            "result_summary_json": {"mutation_executed": True},
            "mutation_executed": True,
            "updated_at_ms": 1770000000100,
            "completed_at_ms": 1770000000100,
        }
    )
    await repo.save_workflow_run(completed)

    loaded = await repo.get_workflow_run(saved.workflow_run_id)
    listed = await repo.list_workflow_runs(limit=10, status="completed")

    assert loaded.status == BrcWorkflowStatus.COMPLETED
    assert loaded.withdrawal_executed is False
    assert loaded.live_ready is False
    assert listed[0].workflow_run_id == saved.workflow_run_id
