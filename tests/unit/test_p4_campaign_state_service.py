from __future__ import annotations

import pytest

from src.application.campaign_state_service import (
    CAMPAIGN_STATE_BLOCK_REASON,
    CAMPAIGN_STATE_SCOPE_KEY,
    CampaignRuntimeEvent,
    CampaignStateService,
)
from src.infrastructure.repository_ports import CampaignStateSnapshot


class _CampaignRepo:
    def __init__(self) -> None:
        self.snapshot: CampaignStateSnapshot | None = None
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def get_state(self, scope_key: str):
        return self.snapshot if self.snapshot and self.snapshot.scope_key == scope_key else None

    async def set_state(
        self,
        *,
        scope_key: str,
        status: str,
        reason: str | None,
        updated_by: str,
        updated_at_ms: int,
        active_strategy_contract_id: str | None,
        active_session_id: str | None,
    ):
        self.snapshot = CampaignStateSnapshot(
            scope_key=scope_key,
            status=status,
            reason=reason,
            updated_by=updated_by,
            updated_at_ms=updated_at_ms,
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            source="test",
        )
        return self.snapshot


@pytest.mark.asyncio
async def test_initialize_creates_observe_state_and_blocks_entries():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    decision = await service.evaluate_new_entry(symbol="ETH/USDT:USDT")

    assert repo.initialized
    assert service.get_state().scope_key == CAMPAIGN_STATE_SCOPE_KEY
    assert service.get_state().status == "observe"
    assert not decision.allowed_new_entry
    assert decision.reason == CAMPAIGN_STATE_BLOCK_REASON


@pytest.mark.asyncio
async def test_armed_state_allows_entries():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(status="armed", reason="owner arm", updated_by="owner")
    decision = await service.evaluate_new_entry(
        symbol="ETH/USDT:USDT",
        strategy_contract_id="strategy-test",
    )

    assert decision.allowed_new_entry
    assert decision.state == "armed"


@pytest.mark.asyncio
async def test_invalid_hard_lock_to_armed_transition_is_rejected():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(status="hard_locked", reason="risk", updated_by="owner")

    with pytest.raises(ValueError, match="Invalid campaign state transition"):
        await service.set_state(status="armed", reason="bad", updated_by="owner")


@pytest.mark.asyncio
async def test_missing_repository_is_fail_closed():
    service = CampaignStateService(repository=None)

    await service.initialize()
    decision = await service.evaluate_new_entry(symbol="ETH/USDT:USDT")

    assert service.get_state().status == "hard_locked"
    assert not decision.allowed_new_entry
    assert decision.reason == CAMPAIGN_STATE_BLOCK_REASON


@pytest.mark.asyncio
async def test_runtime_events_advance_campaign_state_machine():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(status="armed", reason="owner arm", updated_by="owner")
    profit_state = await service.apply_runtime_event(
        event=CampaignRuntimeEvent.PROFIT_PROTECT_TRIGGERED,
        reason="profit threshold reached",
    )
    closed_state = await service.apply_runtime_event(
        event=CampaignRuntimeEvent.POSITION_CLOSED,
        reason="runtime close completed",
    )

    assert profit_state.status == "profit_protect"
    assert closed_state.status == "closed"
    assert closed_state.updated_by == "runtime"


@pytest.mark.asyncio
async def test_stop_loss_event_locks_new_entries_until_closed():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(status="armed", reason="owner arm", updated_by="owner")
    loss_state = await service.apply_runtime_event(
        event="stop_loss_filled",
        reason="exchange stop filled",
    )
    decision = await service.evaluate_new_entry(symbol="ETH/USDT:USDT")

    assert loss_state.status == "loss_locked"
    assert not decision.allowed_new_entry
    assert decision.reason == CAMPAIGN_STATE_BLOCK_REASON
