from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import pytest

from src.application.bounded_risk_campaign_service import (
    AttemptCloseRecord,
    AttemptOpenRecord,
    BoundedRiskCampaignService,
    BrcRuleViolation,
)
from src.domain.bounded_risk_campaign import (
    BrcAttemptStatus,
    BrcCampaignStatus,
    BrcDecisionResult,
    BrcReviewDecision,
    CampaignOutcome,
    MockPnlSource,
)


ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"


class InMemoryBrcRepo:
    def __init__(self) -> None:
        self.campaign = None
        self.switches = []
        self.events = []
        self.mock_pnl_events = []
        self.operator_actions = {}
        self.review_decisions = []
        self.llm_intents = {}
        self.workflow_runs = {}

    async def initialize(self) -> None:
        return None

    async def get_current_campaign(self):
        if self.campaign is None or self.campaign.status.value == "ended":
            return None
        return self.campaign

    async def get_latest_campaign(self):
        return self.campaign

    async def save_campaign(self, campaign):
        self.campaign = campaign
        return campaign

    async def append_switch_decision(self, decision):
        self.switches.append(decision)
        return decision

    async def append_campaign_event(
        self,
        *,
        campaign_id: str,
        event_type: str,
        occurred_at_ms: int,
        symbol: Optional[str] = None,
        attempt_id: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        row = {
            "campaign_id": campaign_id,
            "sequence_number": len(self.events) + 1,
            "event_type": event_type,
            "symbol": symbol,
            "attempt_id": attempt_id,
            "reason": reason,
            "metadata": dict(metadata or {}),
            "occurred_at_ms": occurred_at_ms,
        }
        self.events.append(row)
        return row

    async def append_mock_pnl_event(self, event):
        self.mock_pnl_events.append(event)
        return event

    async def list_switch_decisions(self, campaign_id: str):
        return [item for item in self.switches if item.campaign_id == campaign_id]

    async def list_campaign_events(self, campaign_id: str):
        return [item for item in self.events if item["campaign_id"] == campaign_id]

    async def list_mock_pnl_events(self, campaign_id: str):
        return [item for item in self.mock_pnl_events if item.campaign_id == campaign_id]

    async def save_operator_action(self, action):
        self.operator_actions[action.action_id] = action
        return action

    async def get_operator_action(self, action_id: str):
        return self.operator_actions.get(action_id)

    async def list_operator_actions(self, *, campaign_id: Optional[str] = None, limit: int = 50):
        actions = list(self.operator_actions.values())
        if campaign_id is not None:
            actions = [action for action in actions if action.campaign_id == campaign_id]
        actions.sort(key=lambda action: action.created_at_ms, reverse=True)
        return actions[:limit]

    async def append_review_decision(self, decision):
        self.review_decisions.append(decision)
        return decision

    async def get_latest_review_decision(self):
        if not self.review_decisions:
            return None
        return sorted(self.review_decisions, key=lambda item: item.created_at_ms, reverse=True)[0]

    async def list_review_decisions(self, *, campaign_id: Optional[str] = None, limit: int = 50):
        decisions = list(self.review_decisions)
        if campaign_id is not None:
            decisions = [decision for decision in decisions if decision.campaign_id == campaign_id]
        decisions.sort(key=lambda item: item.created_at_ms, reverse=True)
        return decisions[:limit]

    async def save_llm_intent(self, intent):
        self.llm_intents[intent.intent_id] = intent
        return intent

    async def get_llm_intent(self, intent_id: str):
        return self.llm_intents.get(intent_id)

    async def list_llm_intents(self, *, limit: int = 50, action: Optional[str] = None):
        intents = list(self.llm_intents.values())
        if action is not None:
            intents = [intent for intent in intents if intent.action.value == action]
        intents.sort(key=lambda item: item.created_at_ms, reverse=True)
        return intents[:limit]

    async def save_workflow_run(self, run):
        self.workflow_runs[run.workflow_run_id] = run
        return run

    async def get_workflow_run(self, workflow_run_id: str):
        return self.workflow_runs.get(workflow_run_id)

    async def list_workflow_runs(self, *, limit: int = 50, status: Optional[str] = None):
        runs = list(self.workflow_runs.values())
        if status is not None:
            runs = [run for run in runs if run.status.value == status]
        runs.sort(key=lambda item: item.created_at_ms, reverse=True)
        return runs[:limit]


async def _campaign_service():
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
async def test_brc_switch_records_inferred_fields_and_does_not_reset_pnl():
    service, repo = await _campaign_service()
    decision = await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized controlled rehearsal",
        evidence_refs=["docs/adr/0012-bounded-risk-campaign-system.md"],
    )

    assert decision.decision_result == BrcDecisionResult.ALLOWED
    assert decision.campaign_pnl_at_switch == Decimal("0")
    assert decision.inferred_fields["loss_counter_reset"] is False
    assert repo.campaign.current_playbook_id == "PB-004-BRC-CONTROLLED-TESTNET"


@pytest.mark.asyncio
async def test_brc_attempt_sequence_and_third_attempt_block():
    service, _ = await _campaign_service()
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized controlled rehearsal",
        evidence_refs=["evidence"],
    )
    first = await service.arm_attempt(symbol=ETH, reason="eth")
    assert first.status == BrcAttemptStatus.ARMED
    await service.record_attempt_entry(
        symbol=ETH,
        record=AttemptOpenRecord(
            intent_id="intent-eth",
            signal_id="sig-eth",
            amount=Decimal("0.01"),
            notional=Decimal("21"),
        ),
    )
    await service.record_attempt_close(
        symbol=ETH,
        record=AttemptCloseRecord(close_order_id="close-eth", exchange_order_id="ex-eth"),
    )
    second = await service.arm_attempt(symbol=BTC, reason="btc")
    assert second.symbol == BTC
    await service.record_attempt_entry(
        symbol=BTC,
        record=AttemptOpenRecord(
            intent_id="intent-btc",
            signal_id="sig-btc",
            amount=Decimal("0.002"),
            notional=Decimal("155"),
        ),
    )
    await service.record_attempt_close(
        symbol=BTC,
        record=AttemptCloseRecord(close_order_id="close-btc", exchange_order_id="ex-btc"),
    )

    with pytest.raises(BrcRuleViolation, match="third attempt"):
        await service.arm_attempt(symbol=ETH, reason="third")


@pytest.mark.asyncio
async def test_brc_mock_profit_and_loss_states_block_switch_reset():
    service, _ = await _campaign_service()
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized controlled rehearsal",
        evidence_refs=["evidence"],
    )
    profit = await service.inject_mock_pnl(
        amount=Decimal("120"),
        source=MockPnlSource.TESTNET_MOCK,
        reason="mock profit branch",
    )
    assert profit.triggered_state == BrcCampaignStatus.PROFIT_PROTECT
    assert (await service.require_current_campaign()).status == BrcCampaignStatus.PROFIT_PROTECT

    loss = await service.inject_mock_pnl(
        amount=Decimal("-240"),
        source=MockPnlSource.TESTNET_MOCK,
        reason="mock loss branch",
    )
    assert loss.triggered_state == BrcCampaignStatus.LOSS_LOCKED
    assert (await service.require_current_campaign()).realized_pnl == Decimal("-120")
    decision = await service.switch_playbook(
        new_playbook_id="PB-000-OBSERVE-ONLY",
        reason_category="loss_response",
        reason_text="try to reset",
        evidence_refs=["evidence"],
    )
    assert decision.decision_result == BrcDecisionResult.BLOCKED
    assert "loss_locked" in decision.blocked_reason
    assert (await service.require_current_campaign()).realized_pnl == Decimal("-120")


@pytest.mark.asyncio
async def test_brc_finalize_requires_loss_locked_and_closed_attempts():
    service, _ = await _campaign_service()
    with pytest.raises(BrcRuleViolation, match="loss-locked"):
        await service.finalize(
            outcome=CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED,
            reason="premature",
            final_flat=True,
        )


@pytest.mark.asyncio
async def test_brc_review_packet_summarizes_latest_finalized_campaign():
    service, _ = await _campaign_service()
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized controlled rehearsal",
        evidence_refs=["evidence"],
    )
    for symbol in (ETH, BTC):
        await service.arm_attempt(symbol=symbol, reason=symbol)
        await service.record_attempt_entry(
            symbol=symbol,
            record=AttemptOpenRecord(
                intent_id=f"intent-{symbol}",
                signal_id=f"sig-{symbol}",
                amount=Decimal("0.01"),
                notional=Decimal("21"),
            ),
        )
        await service.record_attempt_close(
            symbol=symbol,
            record=AttemptCloseRecord(close_order_id=f"close-{symbol}", exchange_order_id=None),
        )
    await service.inject_mock_pnl(
        amount=Decimal("120"),
        source=MockPnlSource.TESTNET_MOCK,
        reason="mock profit branch",
    )
    await service.inject_mock_pnl(
        amount=Decimal("-240"),
        source=MockPnlSource.TESTNET_MOCK,
        reason="mock loss branch",
    )
    await service.finalize(
        outcome=CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED,
        reason="complete",
        final_flat=True,
    )

    packet = await service.build_review_packet(final_inventory={"all_flat": True})

    assert packet.status == BrcCampaignStatus.ENDED
    assert packet.outcome == CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED
    assert packet.attempt_count == 2
    assert packet.profit_protect_triggered is True
    assert packet.loss_lock_triggered is True
    assert packet.all_attempts_closed is True
    assert packet.final_inventory_flat is True
    assert all(check.passed for check in packet.invariant_checks)
    assert packet.live_ready is False
    assert packet.withdrawal_executed is False


@pytest.mark.asyncio
async def test_brc_next_eligibility_requires_owner_review_after_loss_locked_outcome():
    service, _ = await _campaign_service()
    await service.switch_playbook(
        new_playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        reason_category="evidence_driven",
        reason_text="owner authorized controlled rehearsal",
        evidence_refs=["evidence"],
    )
    for symbol in (ETH, BTC):
        await service.arm_attempt(symbol=symbol, reason=symbol)
        await service.record_attempt_entry(
            symbol=symbol,
            record=AttemptOpenRecord(
                intent_id=f"intent-{symbol}",
                signal_id=f"sig-{symbol}",
                amount=Decimal("0.01"),
                notional=Decimal("21"),
            ),
        )
        await service.record_attempt_close(
            symbol=symbol,
            record=AttemptCloseRecord(close_order_id=f"close-{symbol}", exchange_order_id=None),
        )
    await service.inject_mock_pnl(
        amount=Decimal("-120"),
        source=MockPnlSource.TESTNET_MOCK,
        reason="mock loss branch",
    )
    await service.finalize(
        outcome=CampaignOutcome.ENDED_TESTNET_REHEARSAL_COMPLETE_LOSS_LOCKED,
        reason="complete",
        final_flat=True,
    )

    eligibility = await service.evaluate_next_campaign_eligibility(
        final_inventory={"all_flat": True},
    )

    assert eligibility.decision.value == "owner_review_required"
    assert eligibility.cooldown_required is True
    assert eligibility.next_campaign_allowed is False
    assert eligibility.recommended_playbook_id == "PB-000-OBSERVE-ONLY"


@pytest.mark.asyncio
async def test_brc_next_eligibility_blocks_when_inventory_is_not_flat():
    service, _ = await _campaign_service()

    eligibility = await service.evaluate_next_campaign_eligibility(
        final_inventory={"all_flat": False},
    )

    assert eligibility.decision.value == "blocked"
    assert "not flat" in eligibility.reason


@pytest.mark.asyncio
async def test_brc_operator_intent_draft_maps_text_to_read_only_action():
    service, _ = await _campaign_service()

    draft = service.draft_operator_intent(source_text="帮我看下一轮能不能开")

    assert draft.action.value == "read_next_eligibility"
    assert draft.endpoint_path == "/api/runtime/test/brc/next-eligibility"
    assert draft.mutation_intended is False
    assert draft.executable_without_owner_confirmation is True
    assert draft.live_ready is False


@pytest.mark.asyncio
async def test_brc_operator_intent_draft_blocks_unknown_text():
    service, _ = await _campaign_service()

    draft = service.draft_operator_intent(source_text="帮我直接开一单")

    assert draft.action.value == "unknown"
    assert draft.endpoint_path is None
    assert draft.executable_without_owner_confirmation is False
    assert "R2 only drafts read-only" in draft.blocked_reason


@pytest.mark.asyncio
async def test_brc_operator_execution_plan_requires_confirmation():
    service, _ = await _campaign_service()

    plan = service.build_operator_execution_plan(source_text="帮我看复盘报告")

    assert plan.executable is True
    assert plan.confirmation_phrase == "CONFIRM_READ_ONLY_BRC"
    assert plan.steps[0].owner_confirmation_required is True
    assert plan.steps[0].mutation_intended is False

    with pytest.raises(BrcRuleViolation, match="confirmation phrase mismatch"):
        await service.run_operator_read_action(
            source_text="帮我看复盘报告",
            confirmation_phrase="WRONG",
            final_inventory={"all_flat": True},
        )


@pytest.mark.asyncio
async def test_brc_operator_read_run_executes_only_read_action():
    service, repo = await _campaign_service()

    run = await service.run_operator_read_action(
        source_text="帮我看下一轮能不能开",
        confirmation_phrase="CONFIRM_READ_ONLY_BRC",
        final_inventory={"all_flat": True},
    )

    assert run.executed is True
    assert run.action.value == "read_next_eligibility"
    assert run.mutation_executed is False
    assert run.withdrawal_executed is False
    assert run.live_ready is False
    assert run.result["eligibility"]["decision"] == "blocked"
    action = next(iter(repo.operator_actions.values()))
    assert action.decision_result.value == "executed"
    assert action.confirmation_matched is True
    assert action.result_summary_json["mutation_executed"] is False


@pytest.mark.asyncio
async def test_brc_operator_plan_persists_and_canonical_run_uses_action_id():
    service, _ = await _campaign_service()

    action = await service.create_operator_action_plan(source_text="帮我看复盘报告")
    assert action.action_id.startswith("brc-op-")
    assert action.decision_result.value == "planned"
    assert action.plan_json["draft"]["action"] == "read_review_packet"

    run = await service.run_operator_action_by_id(
        action_id=action.action_id,
        confirmation_phrase="CONFIRM_READ_ONLY_BRC",
        final_inventory={"all_flat": True},
    )
    stored = await service.get_operator_action(action.action_id)

    assert run.executed is True
    assert stored.decision_result.value == "executed"
    assert stored.result_json["action"] == "read_review_packet"
    assert stored.mutation_executed is False
    assert stored.withdrawal_executed is False


@pytest.mark.asyncio
async def test_brc_operator_unknown_text_is_persisted_as_blocked():
    service, _ = await _campaign_service()

    action = await service.create_operator_action_plan(source_text="帮我直接开一单")

    assert action.executable is False
    assert action.decision_result.value == "blocked"
    assert action.draft_action.value == "unknown"
    with pytest.raises(BrcRuleViolation, match="already blocked"):
        await service.run_operator_action_by_id(
            action_id=action.action_id,
            confirmation_phrase="CONFIRM_READ_ONLY_BRC",
            final_inventory={"all_flat": True},
        )


@pytest.mark.asyncio
async def test_brc_review_decision_records_owner_decision_without_live_authority():
    service, repo = await _campaign_service()

    record = await service.record_review_decision(
        campaign_id=repo.campaign.campaign_id,
        decision=BrcReviewDecision.ACCEPTED,
        reason_text="BRC R2 reviewed",
        next_recommended_task="BRC-R2-005",
        created_by="owner",
        metadata={"source": "unit-test"},
    )
    latest = await service.get_latest_review_decision()
    listed = await service.list_review_decisions(campaign_id=repo.campaign.campaign_id)

    assert record.review_id.startswith("brc-review-")
    assert latest.review_id == record.review_id
    assert listed[0].decision == BrcReviewDecision.ACCEPTED
    assert record.testnet_only is True
    assert record.real_live_authorized is False
    assert record.withdrawal_authorized is False
    assert record.strategy_execution_authorized is False
