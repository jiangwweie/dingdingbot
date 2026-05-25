from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.campaign_state_service import (
    CAMPAIGN_STATE_BLOCK_REASON,
    CAMPAIGN_STATE_SCOPE_KEY,
    CampaignRuntimeEvent,
    CampaignRuntimeState,
    CampaignStateService,
    CampaignTransitionInput,
    CampaignTransitionTrigger,
    get_campaign_transition_table,
    replay_campaign_transitions,
)
from src.infrastructure.pg_campaign_state_repository import PgCampaignStateRepository
from src.infrastructure.pg_models import (
    PGRuntimeCampaignStateORM,
    PGRuntimeCampaignStateTransitionORM,
)
from src.infrastructure.repository_ports import CampaignStateSnapshot
from src.infrastructure.repository_ports import CampaignStateTransitionLog


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


class _LedgerCampaignRepo(_CampaignRepo):
    def __init__(self) -> None:
        super().__init__()
        self.transitions: list[CampaignStateTransitionLog] = []

    async def record_transition(
        self,
        transition: CampaignStateTransitionLog,
    ) -> CampaignStateTransitionLog:
        persisted = CampaignStateTransitionLog(
            scope_key=transition.scope_key,
            sequence_number=len(self.transitions) + 1,
            previous_status=transition.previous_status,
            target_status=transition.target_status,
            next_status=transition.next_status,
            trigger=transition.trigger,
            reason=transition.reason,
            updated_by=transition.updated_by,
            occurred_at_ms=transition.occurred_at_ms,
            accepted=transition.accepted,
            rule_reason_code=transition.rule_reason_code,
            rejection_reason=transition.rejection_reason,
            active_strategy_contract_id=transition.active_strategy_contract_id,
            active_session_id=transition.active_session_id,
            metadata=dict(transition.metadata or {}),
            source="test",
        )
        self.transitions.append(persisted)
        return persisted

    async def set_state_with_transition(self, **kwargs):
        transition = kwargs.pop("transition")
        snapshot = await self.set_state(**kwargs)
        persisted = await self.record_transition(transition)
        return snapshot, persisted

    async def list_transitions(self, scope_key: str, *, limit: int = 500):
        return [
            transition
            for transition in self.transitions
            if transition.scope_key == scope_key
        ][:limit]


@pytest_asyncio.fixture()
async def pg_campaign_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGRuntimeCampaignStateORM.__table__.create)
        await conn.run_sync(PGRuntimeCampaignStateTransitionORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgCampaignStateRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


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


def test_transition_table_exposes_required_campaign_paths():
    table = get_campaign_transition_table()
    keys = {(rule.current_state, rule.target_state, rule.trigger) for rule in table}

    assert (
        CampaignRuntimeState.OBSERVE,
        CampaignRuntimeState.ARMED,
        CampaignTransitionTrigger.OWNER_ARM,
    ) in keys
    assert (
        CampaignRuntimeState.ARMED,
        CampaignRuntimeState.PROFIT_PROTECT,
        CampaignTransitionTrigger.PROFIT_PROTECT_TRIGGERED,
    ) in keys
    assert (
        CampaignRuntimeState.HARD_LOCKED,
        CampaignRuntimeState.CLOSED,
        CampaignTransitionTrigger.POSITION_CLOSED,
    ) in keys
    assert any(rule.requires_flat_proof for rule in table)
    assert any(rule.requires_owner_review for rule in table)
    assert any(rule.allows_risk_reducing_close for rule in table)


def test_replay_campaign_transitions_proves_accepted_path():
    result = replay_campaign_transitions(
        initial_state="observe",
        transitions=[
            CampaignTransitionInput(
                target_state="armed",
                trigger="owner_arm",
                reason="owner arm",
                updated_by="owner",
                occurred_at_ms=1,
                active_strategy_contract_id="strategy-test",
                active_session_id="session-test",
                metadata={"symbol": "ETH/USDT:USDT"},
            ),
            CampaignTransitionInput(
                target_state="armed",
                trigger="entry_filled",
                reason="entry filled",
                updated_by="runtime",
                occurred_at_ms=2,
                metadata={"position_id": "pos-1", "signal_id": "sig-1"},
            ),
            CampaignTransitionInput(
                target_state="profit_protect",
                trigger="profit_protect_triggered",
                reason="profit threshold reached",
                updated_by="runtime",
                occurred_at_ms=3,
            ),
            CampaignTransitionInput(
                target_state="closed",
                trigger="position_closed",
                reason="runtime close flat",
                updated_by="runtime",
                occurred_at_ms=4,
            ),
            CampaignTransitionInput(
                target_state="observe",
                trigger="owner_review_reset",
                reason="owner reviewed final evidence",
                updated_by="owner",
                occurred_at_ms=5,
            ),
        ],
    )

    assert result.accepted
    assert result.final_state == CampaignRuntimeState.OBSERVE
    assert [record.sequence_number for record in result.records] == [1, 2, 3, 4, 5]
    assert result.records[1].metadata["position_id"] == "pos-1"
    assert result.records[3].rule_reason_code == "runtime_close_flat_proof"


def test_replay_campaign_transitions_stops_on_invalid_path():
    result = replay_campaign_transitions(
        initial_state="hard_locked",
        transitions=[
            CampaignTransitionInput(
                target_state="armed",
                trigger="owner_arm",
                reason="bad rearm",
                updated_by="owner",
                occurred_at_ms=1,
            ),
            CampaignTransitionInput(
                target_state="closed",
                trigger="position_closed",
                reason="should not be reached",
                updated_by="runtime",
                occurred_at_ms=2,
            ),
        ],
    )

    assert not result.accepted
    assert result.final_state == CampaignRuntimeState.HARD_LOCKED
    assert len(result.records) == 1
    assert "hard_locked->armed via owner_arm" in (result.rejection_reason or "")


@pytest.mark.asyncio
async def test_runtime_event_from_observe_cannot_arm_campaign():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()

    with pytest.raises(ValueError, match="observe->armed via entry_filled"):
        await service.apply_runtime_event(
            event=CampaignRuntimeEvent.ENTRY_FILLED,
            reason="unexpected fill without owner arm",
        )

    assert service.get_state().status == "observe"
    assert service.get_transition_audit_records()[-1].accepted is False


@pytest.mark.asyncio
async def test_runtime_transition_audit_records_context_metadata():
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(
        status="armed",
        reason="owner arm",
        updated_by="owner",
        active_strategy_contract_id="strategy-test",
        active_session_id="session-test",
        symbol="ETH/USDT:USDT",
        profile_id="phase5-testnet",
    )
    await service.apply_runtime_event(
        event=CampaignRuntimeEvent.ENTRY_FILLED,
        reason="entry filled",
        position_id="pos-1",
        signal_id="sig-1",
        order_id="order-1",
    )

    records = service.get_transition_audit_records()
    assert records[0].rule_reason_code == "owner_arm_to_bounded_session"
    assert records[0].metadata["symbol"] == "ETH/USDT:USDT"
    assert records[1].rule_reason_code == "entry_filled_state_retained"
    assert records[1].metadata["position_id"] == "pos-1"
    assert records[1].to_log_dict()["next_state"] == "armed"


@pytest.mark.asyncio
async def test_transition_ledger_records_success_and_rejection_for_replay():
    repo = _LedgerCampaignRepo()
    service = CampaignStateService(repository=repo)

    await service.initialize()
    await service.set_state(status="armed", reason="owner arm", updated_by="owner")
    await service.set_state(status="hard_locked", reason="risk", updated_by="owner")

    with pytest.raises(ValueError, match="hard_locked->armed via owner_arm"):
        await service.set_state(status="armed", reason="bad rearm", updated_by="owner")

    transitions = await service.get_transition_ledger()
    evidence = await service.build_replay_evidence()

    assert [transition.sequence_number for transition in transitions] == [1, 2, 3]
    assert transitions[-1].accepted is False
    assert evidence.accepted
    assert evidence.matches_snapshot
    assert evidence.replay_final_state == CampaignRuntimeState.HARD_LOCKED
    assert evidence.rejected_transition_count == 1


@pytest.mark.asyncio
async def test_pg_campaign_transition_ledger_replays_to_snapshot(pg_campaign_repo):
    service = CampaignStateService(repository=pg_campaign_repo)

    await service.initialize()
    await service.set_state(status="armed", reason="owner arm", updated_by="owner")
    await service.apply_runtime_event(
        event=CampaignRuntimeEvent.PROFIT_PROTECT_TRIGGERED,
        reason="profit threshold reached",
        position_id="pos-1",
        signal_id="sig-1",
    )

    transitions = await pg_campaign_repo.list_transitions(CAMPAIGN_STATE_SCOPE_KEY)
    evidence = await service.build_replay_evidence()

    assert [transition.sequence_number for transition in transitions] == [1, 2]
    assert transitions[1].metadata["position_id"] == "pos-1"
    assert evidence.accepted
    assert evidence.matches_snapshot
    assert evidence.replay_final_state == CampaignRuntimeState.PROFIT_PROTECT
