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

    async def initialize(self) -> None:
        return None

    async def get_current_campaign(self):
        if self.campaign is None or self.campaign.status.value == "ended":
            return None
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
