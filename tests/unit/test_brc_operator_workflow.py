from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import pytest

from src.application.bounded_risk_campaign_service import BoundedRiskCampaignService, BrcRuleViolation
from src.application.brc_operator_workflow import (
    READ_ONLY_CONFIRMATION,
    TESTNET_REHEARSAL_CONFIRMATION,
    BrcOperatorWorkflow,
)
from src.domain.bounded_risk_campaign import (
    BrcLlmIntentAction,
    BrcWorkflowStatus,
)
from tests.unit.test_brc_campaign_service import InMemoryBrcRepo


class FakeProvider:
    provider_name = "fake_llm"
    model_name = "fake-model"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def classify(self, *, source_text: str) -> dict[str, Any]:
        return dict(self.payload)


async def _service():
    repo = InMemoryBrcRepo()
    service = BoundedRiskCampaignService(repo)
    await service.initialize()
    await service.create_campaign(
        bucket_id="bucket",
        authorized_amount=Decimal("500"),
        max_campaign_loss=Decimal("120"),
        profit_protect_trigger=Decimal("100"),
        reason="test",
    )
    return service, repo


@pytest.mark.asyncio
async def test_brc_llm_workflow_persists_intent_and_waits_for_confirmation():
    service, repo = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider(
            {
                "action": "read_next_eligibility",
                "confidence": "0.91",
                "reason_text": "Owner asks whether next campaign can open",
            }
        ),
    )

    run = await workflow.create_workflow(source_text="帮我看下一轮能不能开")

    assert run.status == BrcWorkflowStatus.AWAITING_CONFIRMATION
    assert run.confirmation_phrase_id == READ_ONLY_CONFIRMATION
    assert run.llm_intent_id in repo.llm_intents
    intent = repo.llm_intents[run.llm_intent_id]
    assert intent.action == BrcLlmIntentAction.READ_NEXT_ELIGIBILITY
    assert "api" not in str(intent.model_dump(mode="json")).lower()


@pytest.mark.asyncio
async def test_brc_llm_workflow_blocks_forbidden_live_text_before_provider():
    service, repo = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider({"action": "request_testnet_rehearsal", "confidence": "1", "reason_text": "x"}),
    )

    run = await workflow.create_workflow(source_text="帮我实盘自动下单")

    assert run.status == BrcWorkflowStatus.BLOCKED
    assert "forbidden intent token" in run.blocked_reason
    intent = repo.llm_intents[run.llm_intent_id]
    assert intent.action == BrcLlmIntentAction.UNKNOWN


@pytest.mark.asyncio
async def test_brc_llm_workflow_blocks_testnet_upgrade_without_explicit_source_text():
    service, repo = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider(
            {
                "action": "request_testnet_rehearsal",
                "confidence": "0.99",
                "reason_text": "LLM attempted to upgrade generic next-campaign text",
            }
        ),
    )

    run = await workflow.create_workflow(source_text="帮我看下一轮能不能开")

    assert run.status == BrcWorkflowStatus.BLOCKED
    assert "requires explicit Owner text" in run.blocked_reason
    intent = repo.llm_intents[run.llm_intent_id]
    assert intent.action == BrcLlmIntentAction.REQUEST_TESTNET_REHEARSAL
    assert intent.decision_result.value == "blocked"


@pytest.mark.asyncio
async def test_brc_llm_workflow_wrong_confirmation_blocks_run():
    service, _ = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider({"action": "read_evidence", "confidence": "0.9", "reason_text": "read evidence"}),
    )
    run = await workflow.create_workflow(source_text="给我证据包")

    with pytest.raises(BrcRuleViolation, match="confirmation phrase mismatch"):
        await workflow.confirm_workflow(
            workflow_run_id=run.workflow_run_id,
            confirmation_phrase="WRONG",
            confirmed_by="owner",
        )
    blocked = await workflow.get_workflow(run.workflow_run_id)
    assert blocked.status == BrcWorkflowStatus.BLOCKED


@pytest.mark.asyncio
async def test_brc_llm_workflow_confirmed_read_only_executes_without_mutation():
    service, _ = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider(
            {
                "action": "read_next_eligibility",
                "confidence": "0.9",
                "reason_text": "read next eligibility",
            }
        ),
    )
    run = await workflow.create_workflow(source_text="下一轮是否可以")

    completed = await workflow.confirm_workflow(
        workflow_run_id=run.workflow_run_id,
        confirmation_phrase=READ_ONLY_CONFIRMATION,
        confirmed_by="owner",
        final_inventory={"all_flat": True},
    )

    assert completed.status == BrcWorkflowStatus.COMPLETED
    assert completed.mutation_executed is False
    assert completed.withdrawal_executed is False
    assert completed.live_ready is False
    assert completed.result_json["eligibility"]["eligibility_result"] == "blocked"

    with pytest.raises(BrcRuleViolation, match="already completed"):
        await workflow.confirm_workflow(
            workflow_run_id=run.workflow_run_id,
            confirmation_phrase=READ_ONLY_CONFIRMATION,
            confirmed_by="owner",
            final_inventory={"all_flat": True},
        )


@pytest.mark.asyncio
async def test_brc_llm_workflow_rejects_invalid_testnet_executor_result():
    service, _ = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider(
            {
                "action": "request_testnet_rehearsal",
                "confidence": "0.92",
                "reason_text": "Owner asks for controlled testnet rehearsal",
            }
        ),
    )
    run = await workflow.create_workflow(source_text="准备下一轮 testnet 演练")

    async def executor(workflow_run_id: str) -> dict[str, Any]:
        return {"campaign_id": "brc-test", "final_inventory": {"all_flat": False}}

    with pytest.raises(BrcRuleViolation, match="final flat inventory"):
        await workflow.confirm_workflow(
            workflow_run_id=run.workflow_run_id,
            confirmation_phrase=TESTNET_REHEARSAL_CONFIRMATION,
            confirmed_by="owner",
            testnet_rehearsal_executor=executor,
        )


@pytest.mark.asyncio
async def test_brc_llm_workflow_confirmed_testnet_uses_fixed_executor():
    service, _ = await _service()
    workflow = BrcOperatorWorkflow(
        campaign_service=service,
        provider=FakeProvider(
            {
                "action": "request_testnet_rehearsal",
                "confidence": "0.92",
                "reason_text": "Owner asks for controlled testnet rehearsal",
            }
        ),
    )
    run = await workflow.create_workflow(source_text="准备下一轮 testnet 演练")
    called: list[str] = []

    async def executor(workflow_run_id: str) -> dict[str, Any]:
        called.append(workflow_run_id)
        return {"campaign_id": "brc-test", "final_inventory": {"all_flat": True}}

    completed = await workflow.confirm_workflow(
        workflow_run_id=run.workflow_run_id,
        confirmation_phrase=TESTNET_REHEARSAL_CONFIRMATION,
        confirmed_by="owner",
        testnet_rehearsal_executor=executor,
    )

    assert called == [run.workflow_run_id]
    assert completed.status == BrcWorkflowStatus.COMPLETED
    assert completed.mutation_executed is True
    assert completed.withdrawal_executed is False
    assert completed.live_ready is False
    assert "review_decision" not in completed.result_json
