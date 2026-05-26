from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.bounded_risk_campaign import (
    BrcOperatorAction,
    BrcOperatorActionLedger,
    BrcOperatorDecisionResult,
)
from src.infrastructure.pg_brc_campaign_repository import PgBrcCampaignRepository
from src.infrastructure.pg_models import PGBrcOperatorActionORM


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcOperatorActionORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgBrcCampaignRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _action(action_id: str = "brc-op-test") -> BrcOperatorActionLedger:
    return BrcOperatorActionLedger(
        action_id=action_id,
        campaign_id="brc-campaign",
        plan_id="brc-plan",
        source_text="帮我看下一轮能不能开",
        draft_action=BrcOperatorAction.READ_NEXT_ELIGIBILITY,
        http_method="GET",
        endpoint_path="/api/runtime/test/brc/next-eligibility",
        executable=True,
        decision_result=BrcOperatorDecisionResult.PLANNED,
        plan_json={
            "plan_id": "brc-plan",
            "source_text": "帮我看下一轮能不能开",
            "draft": {
                "source_text": "帮我看下一轮能不能开",
                "action": "read_next_eligibility",
                "confidence": "0.88",
                "http_method": "GET",
                "endpoint_path": "/api/runtime/test/brc/next-eligibility",
                "mutation_intended": False,
                "executable_without_owner_confirmation": True,
                "owner_confirmation_required": False,
                "blocked_reason": None,
                "live_ready": False,
            },
            "steps": [
                {
                    "step_id": "step-1",
                    "action": "read_next_eligibility",
                    "http_method": "GET",
                    "endpoint_path": "/api/runtime/test/brc/next-eligibility",
                    "mutation_intended": False,
                    "owner_confirmation_required": True,
                }
            ],
            "executable": True,
            "confirmation_phrase": "CONFIRM_READ_ONLY_BRC",
            "blocked_reason": None,
            "live_ready": False,
        },
        created_at_ms=1770000000000,
    )


@pytest.mark.asyncio
async def test_operator_action_repository_saves_updates_and_lists(repo):
    planned = await repo.save_operator_action(_action())

    assert planned.action_id == "brc-op-test"
    assert planned.decision_result == BrcOperatorDecisionResult.PLANNED

    executed = planned.model_copy(
        update={
            "decision_result": BrcOperatorDecisionResult.EXECUTED,
            "confirmation_matched": True,
            "confirmed_by": "owner",
            "result_json": {"action": "read_next_eligibility"},
            "result_summary_json": {"mutation_executed": False},
            "executed_at_ms": 1770000000100,
        }
    )
    await repo.save_operator_action(executed)

    loaded = await repo.get_operator_action("brc-op-test")
    listed = await repo.list_operator_actions(campaign_id="brc-campaign", limit=10)

    assert loaded.decision_result == BrcOperatorDecisionResult.EXECUTED
    assert loaded.confirmation_matched is True
    assert loaded.result_json["action"] == "read_next_eligibility"
    assert listed[0].action_id == "brc-op-test"
