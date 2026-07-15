from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.strategy_runtime_service import (
    StrategyRuntimeError,
    StrategyRuntimeInstanceService,
)
from src.application.owner_trial_flow import BoundedLiveTrialAuthorization
from src.domain.brc_admission import (
    AdmissionExecutionMode,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    StrategyFamilyVersion,
    TrialEnv,
    TrialStage,
)
from src.domain.experimental_runtime_profile_proposal import (
    build_experimental_runtime_profile_proposal,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeEvent,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
    StrategyRuntimePolicySnapshot,
)
from src.domain.strategy_runtime_live_enablement import (
    build_strategy_runtime_live_enablement_preview,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateInput,
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
    evaluate_strategy_runtime_promotion_gate,
)
from src.domain.strategy_runtime_safety_readiness import (
    evaluate_strategy_runtime_safety_readiness,
)
from src.domain.strategy_semantics import initial_strategy_semantics_catalog
from src.infrastructure.pg_models import (
    PGStrategyRuntimeEventORM,
    PGStrategyRuntimeInstanceORM,
)
from src.infrastructure.pg_strategy_runtime_repository import PgStrategyRuntimeRepository
from src.application.readmodels.strategy_runtime_watcher_identity import (
    WatcherCandidateLaneKey,
)
from src.interfaces import api as api_module
from src.interfaces.api_trading_console import (
    StrategyRuntimeWatcherCandidatePageRequest,
    StrategyRuntimeLiveEnablementMutationRequest,
    apply_strategy_runtime_live_enablement_mutation,
    get_strategy_runtime,
    list_strategy_runtimes,
    watcher_active_candidate_runtime_page,
)


NOW_MS = 1780496665000


def _runtime(**overrides) -> StrategyRuntimeInstance:
    values = {
        "runtime_instance_id": "strategy-runtime-1",
        "trial_binding_id": "binding-1",
        "admission_decision_id": "decision-1",
        "strategy_family_id": "family-1",
        "strategy_family_version_id": "version-1",
        "owner_risk_acceptance_id": "risk-1",
        "carrier_id": "carrier-1",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "status": StrategyRuntimeInstanceStatus.DRAFT,
        "boundary": StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=Decimal("25"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("25"),
            total_budget=Decimal("100"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("2"),
            requires_protection=True,
            requires_review=True,
        ),
        "policy_snapshot": StrategyRuntimePolicySnapshot(
            playbook_id="PB-1",
            playbook_snapshot={"id": "PB-1"},
            admission_execution_mode="owner_confirm_each_entry",
        ),
        "execution_enabled": False,
        "shadow_mode": True,
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
        "metadata": {"source": "unit-test"},
    }
    values.update(overrides)
    return StrategyRuntimeInstance(**values)


def _binding() -> AdmissionTrialBinding:
    return AdmissionTrialBinding(
        binding_id="binding-1",
        admission_decision_id="decision-1",
        owner_risk_acceptance_id="risk-1",
        trial_constraint_snapshot_id="constraint-1",
        strategy_family_version_id="version-1",
        playbook_id="PB-1",
        playbook_catalog_snapshot_json={"id": "PB-1"},
        trial_env=TrialEnv.TESTNET,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        execution_mode=AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
        binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
        campaign_id=None,
        runtime_carrier_id=None,
        created_by_operation_id="operation-1",
        created_by_preflight_id="preflight-1",
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _version() -> StrategyFamilyVersion:
    return StrategyFamilyVersion(
        strategy_family_version_id="version-1",
        strategy_family_id="family-1",
        version=1,
        hypothesis="shadow runtime test",
        supported_symbols=["ETH/USDT:USDT"],
        supported_timeframes=["1h"],
        created_at_ms=NOW_MS,
    )


class _FakeRuntimeRepo:
    def __init__(self) -> None:
        self.items: dict[str, StrategyRuntimeInstance] = {}
        self.events = []

    async def initialize(self) -> None:
        return None

    async def create(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        self.items[runtime.runtime_instance_id] = runtime
        return runtime

    async def get(self, runtime_instance_id: str):
        return self.items.get(runtime_instance_id)

    async def list(self, *, status=None, limit=100):
        items = list(self.items.values())
        if status is not None:
            items = [item for item in items if item.status == status]
        return items[:limit]

    async def update_status(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        self.items[runtime.runtime_instance_id] = runtime
        return runtime

    async def record_event(self, event):
        self.events.append(event)
        return event

    async def find_by_trial_binding_id(self, trial_binding_id: str):
        for item in self.items.values():
            if item.trial_binding_id == trial_binding_id:
                return item
        return None


class _FakeAdmissionRepo:
    async def get_admission_trial_binding(self, binding_id: str):
        if binding_id == "binding-1":
            return _binding()
        return None

    async def get_strategy_family_version(self, strategy_family_version_id: str):
        if strategy_family_version_id == "version-1":
            return _version()
        return None


class _ProfileAdmissionRepo:
    async def get_admission_trial_binding(self, binding_id: str):
        if binding_id != "binding-cpm-profile":
            return None
        return AdmissionTrialBinding(
            binding_id="binding-cpm-profile",
            admission_decision_id="decision-cpm-profile",
            owner_risk_acceptance_id="risk-cpm-profile",
            trial_constraint_snapshot_id="constraint-cpm-profile",
            strategy_family_version_id="CPM-RO-001-v0",
            playbook_id="PB-CPM",
            playbook_catalog_snapshot_json={"id": "PB-CPM"},
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            execution_mode=AdmissionExecutionMode.AUTO_WITHIN_BUDGET,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            campaign_id=None,
            runtime_carrier_id=None,
            created_by_operation_id="operation-cpm-profile",
            created_by_preflight_id="preflight-cpm-profile",
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
        )

    async def get_strategy_family_version(self, strategy_family_version_id: str):
        if strategy_family_version_id != "CPM-RO-001-v0":
            return None
        return StrategyFamilyVersion(
            strategy_family_version_id="CPM-RO-001-v0",
            strategy_family_id="CPM-RO-001",
            version=1,
            hypothesis="CPM controlled-subaccount profile confirmation test",
            supported_symbols=["BNB/USDT:USDT"],
            supported_timeframes=["1h", "4h"],
            created_at_ms=NOW_MS,
        )


def _semantic_confirmed() -> StrategySemanticsConfirmationFacts:
    return StrategySemanticsConfirmationFacts(
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
    )


def _runtime_confirmed() -> RuntimeExecutionConfirmationFacts:
    return RuntimeExecutionConfirmationFacts(
        runtime_profile_confirmed=True,
        owner_confirmation_mode_confirmed=True,
        symbol_side_boundary_confirmed=True,
        max_loss_budget_confirmed=True,
        max_notional_boundary_confirmed=True,
        max_active_positions_boundary_confirmed=True,
        max_leverage_boundary_confirmed=True,
        margin_usage_boundary_confirmed=True,
        liquidation_buffer_boundary_confirmed=True,
        protection_readiness_source_confirmed=True,
        stale_fact_behavior_confirmed=True,
        attempt_consumption_rule_confirmed=True,
        budget_reservation_rule_confirmed=True,
        trusted_active_position_source_confirmed=True,
        trusted_account_fact_source_confirmed=True,
    )


def test_strategy_runtime_creation_and_boundary_calculations():
    runtime = _runtime()

    assert runtime.status == StrategyRuntimeInstanceStatus.DRAFT
    assert runtime.attempts_remaining == 2
    assert runtime.budget_remaining == Decimal("75")
    assert runtime.execution_enabled is False
    assert runtime.shadow_mode is True


def test_strategy_runtime_rejects_execution_enabled():
    with pytest.raises(ValueError, match="cannot enable execution"):
        _runtime(execution_enabled=True)


def test_strategy_runtime_can_enable_live_execution_with_audit_metadata():
    runtime = _runtime(status=StrategyRuntimeInstanceStatus.ACTIVE)

    live = runtime.enable_live_execution(
        now_ms=NOW_MS + 1,
        mutation_id="live-enable-mutation-1",
        owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
    )

    assert live.execution_enabled is True
    assert live.shadow_mode is False
    assert live.updated_at_ms == NOW_MS + 1
    assert live.metadata["live_runtime_enablement_mutation_id"] == (
        "live-enable-mutation-1"
    )
    assert live.metadata["creates_execution_intent"] is False
    assert live.metadata["order_created"] is False
    assert live.metadata["exchange_called"] is False
    assert live.metadata["owner_bounded_execution_called"] is False
    assert live.metadata["order_lifecycle_called"] is False


def test_strategy_runtime_invalid_transition_rejected():
    runtime = _runtime(status=StrategyRuntimeInstanceStatus.REVOKED)

    with pytest.raises(ValueError, match="invalid runtime status transition"):
        runtime.transition_to(StrategyRuntimeInstanceStatus.ACTIVE, now_ms=NOW_MS + 1)


@pytest.mark.parametrize(
    "terminal_status",
    [
        StrategyRuntimeInstanceStatus.REVIEWED,
        StrategyRuntimeInstanceStatus.EXHAUSTED,
        StrategyRuntimeInstanceStatus.CLOSED,
    ],
)
def test_strategy_runtime_terminal_statuses_cannot_reactivate(terminal_status):
    runtime = _runtime(status=terminal_status)

    with pytest.raises(ValueError, match="invalid runtime status transition"):
        runtime.transition_to(StrategyRuntimeInstanceStatus.ACTIVE, now_ms=NOW_MS + 1)


def test_strategy_runtime_paused_runtime_can_reactivate():
    runtime = _runtime(status=StrategyRuntimeInstanceStatus.ACTIVE)

    paused = runtime.transition_to(StrategyRuntimeInstanceStatus.PAUSED, now_ms=NOW_MS + 1)
    active = paused.transition_to(StrategyRuntimeInstanceStatus.ACTIVE, now_ms=NOW_MS + 2)

    assert paused.status == StrategyRuntimeInstanceStatus.PAUSED
    assert active.status == StrategyRuntimeInstanceStatus.ACTIVE
    assert active.execution_enabled is False
    assert active.shadow_mode is True


def test_strategy_runtime_boundary_rejects_attempt_overuse():
    with pytest.raises(ValueError, match="attempts_used cannot exceed"):
        StrategyRuntimeBoundary(max_attempts=1, attempts_used=2)


def test_strategy_runtime_budget_remaining_is_none_without_total_budget():
    runtime = _runtime(
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            max_notional_per_attempt=Decimal("25"),
            total_budget=None,
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
        )
    )

    assert runtime.budget_remaining is None


def test_strategy_runtime_rejects_symbol_outside_boundary():
    with pytest.raises(ValueError, match="runtime symbol must be allowed"):
        _runtime(
            symbol="BTC/USDT:USDT",
            boundary=StrategyRuntimeBoundary(
                max_attempts=1,
                allowed_symbols=["ETH/USDT:USDT"],
                allowed_sides=["long"],
            ),
        )


def test_strategy_runtime_rejects_side_outside_boundary():
    with pytest.raises(ValueError, match="runtime side must be allowed"):
        _runtime(
            side="short",
            boundary=StrategyRuntimeBoundary(
                max_attempts=1,
                allowed_symbols=["ETH/USDT:USDT"],
                allowed_sides=["long"],
            ),
        )


@pytest.mark.asyncio
async def test_service_creates_draft_from_trial_binding_without_mutating_binding():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )

    runtime = await service.create_draft_from_trial_binding(
        "binding-1",
        side="long",
        max_attempts=2,
        max_notional_per_attempt=Decimal("10"),
        total_budget=Decimal("20"),
    )

    assert runtime.status == StrategyRuntimeInstanceStatus.DRAFT
    assert runtime.trial_binding_id == "binding-1"
    assert runtime.strategy_family_id == "family-1"
    assert runtime.strategy_family_version_id == "version-1"
    assert runtime.owner_risk_acceptance_id == "risk-1"
    assert runtime.execution_enabled is False
    assert runtime.shadow_mode is True
    assert runtime_repo.events[-1].event_type == "created"
    assert _binding().binding_status == AdmissionTrialBindingStatus.BINDING_RESERVED


@pytest.mark.asyncio
async def test_service_creates_shadow_runtime_from_confirmed_profile_proposal():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_ProfileAdmissionRepo(),
    )
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="BNB/USDT:USDT",
        side="long",
    )
    proposal = proposal.model_copy(
        update={
            "boundary": proposal.boundary.model_copy(
                update={
                    "attempts_used": 3,
                    "budget_reserved": Decimal("1.23"),
                }
            )
        }
    )
    confirmation = StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id="promotion-confirmation-runtime-profile-1",
        runtime_instance_id="strategy-runtime-profile-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        runtime_profile_proposal_snapshot=proposal,
        reason="Owner/Codex confirms CPM controlled-subaccount profile proposal.",
        created_at_ms=NOW_MS,
    )

    runtime = await service.create_draft_from_profile_confirmation(
        "binding-cpm-profile",
        confirmation=confirmation,
    )

    assert runtime.runtime_instance_id == "strategy-runtime-profile-1"
    assert runtime.status == StrategyRuntimeInstanceStatus.DRAFT
    assert runtime.strategy_family_id == "CPM-RO-001"
    assert runtime.symbol == "BNB/USDT:USDT"
    assert runtime.side == "long"
    assert runtime.boundary.max_attempts == 3
    assert runtime.boundary.attempts_used == 0
    assert runtime.boundary.attempts_remaining == 3
    assert runtime.boundary.budget_reserved == Decimal("0")
    assert runtime.boundary.total_budget == Decimal("9.00")
    assert runtime.boundary.max_notional_per_attempt == Decimal("10.00")
    assert runtime.boundary.max_leverage == Decimal("1")
    assert runtime.boundary.max_margin_per_attempt == Decimal("10.00")
    assert runtime.boundary.min_liquidation_stop_buffer == Decimal("25")
    assert runtime.execution_enabled is False
    assert runtime.shadow_mode is True
    assert runtime.metadata["confirmation_id"] == (
        "promotion-confirmation-runtime-profile-1"
    )
    assert runtime.metadata["creates_execution_intent"] is False
    assert runtime.metadata["order_created"] is False
    assert runtime.metadata["exchange_called"] is False
    assert runtime_repo.events[-1].event_type == "created_from_profile_confirmation"
    assert runtime_repo.events[-1].metadata["creates_execution_intent"] is False
    assert runtime_repo.events[-1].metadata["order_created"] is False
    assert runtime_repo.events[-1].metadata["exchange_called"] is False


@pytest.mark.asyncio
async def test_service_blocks_profile_confirmation_without_snapshot():
    service = StrategyRuntimeInstanceService(
        runtime_repository=_FakeRuntimeRepo(),
        admission_repository=_ProfileAdmissionRepo(),
    )
    confirmation = StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id="promotion-confirmation-no-profile",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        reason="Missing profile proposal should block runtime draft creation.",
        created_at_ms=NOW_MS,
    )

    with pytest.raises(StrategyRuntimeError, match="proposal snapshot is required"):
        await service.create_draft_from_profile_confirmation(
            "binding-cpm-profile",
            confirmation=confirmation,
        )


@pytest.mark.asyncio
async def test_service_lifecycle_transitions_do_not_create_execution_side_effects():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )
    runtime = await service.create_draft_from_trial_binding("binding-1", side="long")

    active = await service.activate_runtime(runtime.runtime_instance_id)
    paused = await service.pause_runtime(runtime.runtime_instance_id)
    revoked = await service.revoke_runtime(runtime.runtime_instance_id)

    assert active.status == StrategyRuntimeInstanceStatus.ACTIVE
    assert active.execution_enabled is False
    assert active.shadow_mode is True
    assert paused.status == StrategyRuntimeInstanceStatus.PAUSED
    assert revoked.status == StrategyRuntimeInstanceStatus.REVOKED
    assert all(event.metadata["execution_enabled"] is False for event in runtime_repo.events)
    assert all(event.metadata["shadow_mode"] is True for event in runtime_repo.events)


@pytest.mark.asyncio
async def test_service_enables_live_runtime_from_ready_preview_without_orders():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )
    runtime = await service.create_draft_from_trial_binding(
        "binding-1",
        side="long",
        max_attempts=3,
        max_notional_per_attempt=Decimal("10"),
        total_budget=Decimal("3"),
        max_leverage=Decimal("1"),
    )
    active = await service.activate_runtime(runtime.runtime_instance_id)
    active = active.model_copy(
        update={
            "boundary": active.boundary.model_copy(
                update={
                    "max_margin_per_attempt": Decimal("10"),
                    "min_liquidation_stop_buffer": Decimal("25"),
                }
            )
        }
    )
    runtime_repo.items[active.runtime_instance_id] = active
    preview = _ready_live_enablement_preview(active)

    mutation = await service.enable_live_runtime_from_preview(
        active.runtime_instance_id,
        preview=preview,
        owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
    )

    saved = runtime_repo.items[active.runtime_instance_id]
    assert mutation.runtime_state_mutated is True
    assert mutation.updated_runtime_snapshot is not None
    assert saved.execution_enabled is True
    assert saved.shadow_mode is False
    assert saved.metadata["live_runtime_enablement_mutation_id"] == mutation.mutation_id
    assert runtime_repo.events[-1].event_type == "live_runtime_enabled"
    assert runtime_repo.events[-1].metadata["runtime_state_mutated"] is True
    assert runtime_repo.events[-1].metadata["execution_intent_created"] is False
    assert runtime_repo.events[-1].metadata["order_created"] is False
    assert runtime_repo.events[-1].metadata["exchange_called"] is False
    assert runtime_repo.events[-1].metadata["owner_bounded_execution_called"] is False
    assert runtime_repo.events[-1].metadata["order_lifecycle_called"] is False


@pytest.mark.asyncio
async def test_service_blocks_live_runtime_enablement_from_blocked_preview():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )
    runtime = await service.create_draft_from_trial_binding("binding-1", side="long")
    active = await service.activate_runtime(runtime.runtime_instance_id)
    blocked_preview = build_strategy_runtime_live_enablement_preview(
        runtime=active,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(active),
        promotion_gate_result=_promotion_gate(active, confirmed=False),
        current_head_deployed=False,
        owner_live_runtime_enablement_authorized=False,
        owner_real_submit_authorization_present=False,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=False,
        forbidden_execution_flags=[],
    )

    with pytest.raises(StrategyRuntimeError, match="live runtime enablement blocked"):
        await service.enable_live_runtime_from_preview(
            active.runtime_instance_id,
            preview=blocked_preview,
            owner_live_runtime_enablement_authorization_id="",
            owner_real_submit_authorization_id="",
        )

    saved = runtime_repo.items[active.runtime_instance_id]
    assert saved.execution_enabled is False
    assert saved.shadow_mode is True


@pytest.mark.asyncio
async def test_service_expired_or_revoked_runtime_cannot_activate():
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )
    runtime = await service.create_draft_from_trial_binding("binding-1", side="long")
    await service.expire_runtime(runtime.runtime_instance_id)

    with pytest.raises(StrategyRuntimeError, match="expired runtime cannot activate"):
        await service.activate_runtime(runtime.runtime_instance_id)


@pytest.mark.asyncio
async def test_repository_persists_runtime_status_and_events():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGStrategyRuntimeInstanceORM.__table__.create)
        await conn.run_sync(PGStrategyRuntimeEventORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgStrategyRuntimeRepository(session_maker=session_maker)

    try:
        runtime = await repo.create(_runtime())
        reloaded = await repo.get(runtime.runtime_instance_id)
        assert reloaded is not None
        assert reloaded.runtime_instance_id == runtime.runtime_instance_id

        updated = runtime.transition_to(StrategyRuntimeInstanceStatus.ACTIVE, now_ms=NOW_MS + 1)
        await repo.update_status(updated)
        found = await repo.find_by_trial_binding_id("binding-1")
        assert found is not None
        assert found.status == StrategyRuntimeInstanceStatus.ACTIVE
        live = found.enable_live_execution(
            now_ms=NOW_MS + 2,
            mutation_id="live-enable-repo-mutation-1",
            owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
            owner_real_submit_authorization_id="owner-real-submit-auth-1",
        )
        await repo.update_status(live)
        live_reloaded = await repo.get(found.runtime_instance_id)
        assert live_reloaded is not None
        assert live_reloaded.execution_enabled is True
        assert live_reloaded.shadow_mode is False

        event = await repo.record_event(
            StrategyRuntimeEvent(
                event_id="event-1",
                runtime_instance_id=found.runtime_instance_id,
                event_type="status_transition",
                previous_status=StrategyRuntimeInstanceStatus.DRAFT,
                next_status=StrategyRuntimeInstanceStatus.ACTIVE,
                actor="unit-test",
                reason="repository test",
                metadata={"execution_enabled": False, "shadow_mode": True},
                created_at_ms=NOW_MS + 3,
            )
        )
        assert event.runtime_instance_id == found.runtime_instance_id
        async with session_maker() as session:
            count = await session.scalar(select(PGStrategyRuntimeEventORM))
            assert count is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_pages_only_active_candidate_runtime_identities():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGStrategyRuntimeInstanceORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgStrategyRuntimeRepository(session_maker=session_maker)
    try:
        for index in range(17):
            await repo.create(
                _runtime(
                    runtime_instance_id=f"runtime-{index:03d}",
                    trial_binding_id=f"binding-{index:03d}",
                    status=StrategyRuntimeInstanceStatus.ACTIVE,
                )
            )
        await repo.create(
            _runtime(
                runtime_instance_id="runtime-inactive",
                trial_binding_id="binding-inactive",
                status=StrategyRuntimeInstanceStatus.PAUSED,
            )
        )
        await repo.create(
            _runtime(
                runtime_instance_id="runtime-out-of-scope",
                trial_binding_id="binding-out-of-scope",
                strategy_family_id="other-family",
                status=StrategyRuntimeInstanceStatus.ACTIVE,
            )
        )
        lane = WatcherCandidateLaneKey(
            strategy_group_id="family-1",
            symbol="ETH/USDT:USDT",
            side="long",
        )

        first = await repo.list_watcher_candidate_identity_page(
            candidate_lane_keys=(lane,),
            after_runtime_instance_id=None,
            limit=16,
        )
        second = await repo.list_watcher_candidate_identity_page(
            candidate_lane_keys=(lane,),
            after_runtime_instance_id=first.next_cursor,
            limit=16,
        )

        ids = [item.runtime_instance_id for item in (*first.items, *second.items)]
        assert ids == [f"runtime-{index:03d}" for index in range(17)]
        assert first.has_more is True
        assert first.next_cursor == "runtime-015"
        assert second.has_more is False
        assert second.next_cursor is None
        assert first.excluded_active_count == 1
        assert first.excluded_active_sample_ids == ("runtime-out-of-scope",)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_watcher_candidate_page_endpoint_delegates_without_full_list(monkeypatch):
    expected = type("Page", (), {"marker": "bounded"})()

    class _Service:
        async def list_watcher_candidate_identity_page(self, **kwargs):
            assert kwargs["limit"] == 16
            assert kwargs["after_runtime_instance_id"] is None
            assert kwargs["candidate_lane_keys"][0].strategy_group_id == "family-1"
            return expected

        async def list_runtimes(self, **kwargs):
            raise AssertionError("full runtime list must not be called")

    async def _service():
        return _Service()

    monkeypatch.setattr(
        "src.interfaces.api_trading_console._strategy_runtime_service",
        _service,
    )
    result = await watcher_active_candidate_runtime_page(
        StrategyRuntimeWatcherCandidatePageRequest(
            candidate_lane_keys=(
                WatcherCandidateLaneKey(
                    strategy_group_id="family-1",
                    symbol="ETHUSDT",
                    side="long",
                ),
            )
        )
    )
    assert result is expected


def test_migration_creates_strategy_runtime_shadow_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-045_create_strategy_runtime_instances.py"
    )
    spec = importlib.util.spec_from_file_location("strategy_runtime_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    import asyncio

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "strategy_runtime_instances" in tables
    assert "strategy_runtime_events" in tables


def test_migration_065_only_relaxes_strategy_runtime_live_flags():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/"
        / "2026-06-10-065_relax_strategy_runtime_live_enablement_constraints.py"
    )
    text = migration_path.read_text(encoding="utf-8")

    assert 'revision: str = "065"' in text
    assert 'down_revision: Union[str, None] = "064"' in text
    assert "ck_strategy_runtime_instances_execution_disabled" in text
    assert "ck_strategy_runtime_instances_shadow_mode" in text
    assert "drop_constraint" in text
    assert "create_table" not in text
    assert "orders" not in text
    assert "exchange" not in text


@pytest.mark.asyncio
async def test_trading_console_runtime_endpoints_are_read_only_shadow_views(monkeypatch):
    runtime = _runtime(status=StrategyRuntimeInstanceStatus.ACTIVE)

    class _FakeService:
        async def list_runtimes(self, *, status=None, limit=100):
            assert limit == 100
            return [runtime]

        async def get_runtime(self, runtime_instance_id: str):
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    monkeypatch.setattr(api_module, "_strategy_runtime_service", _FakeService(), raising=False)

    listed = await list_strategy_runtimes(status=None, limit=100)
    detail = await get_strategy_runtime(runtime.runtime_instance_id)

    assert listed[0].execution_enabled is False
    assert listed[0].execution_mode == "shadow_disabled"
    assert listed[0].shadow_mode is True
    assert detail.boundary.attempts_remaining == 2


@pytest.mark.asyncio
async def test_trading_console_runtime_view_reports_live_enabled_execution_mode(monkeypatch):
    runtime = _runtime(status=StrategyRuntimeInstanceStatus.ACTIVE).enable_live_execution(
        now_ms=123,
        mutation_id="strategy-runtime-live-enable-unit",
        owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
    )

    class _FakeService:
        async def list_runtimes(self, *, status=None, limit=100):
            return [runtime]

        async def get_runtime(self, runtime_instance_id: str):
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    monkeypatch.setattr(api_module, "_strategy_runtime_service", _FakeService(), raising=False)

    listed = await list_strategy_runtimes(status=None, limit=100)
    detail = await get_strategy_runtime(runtime.runtime_instance_id)

    assert listed[0].execution_enabled is True
    assert listed[0].shadow_mode is False
    assert listed[0].execution_mode == "runtime_live_enabled"
    assert detail.execution_mode == "runtime_live_enabled"


@pytest.mark.asyncio
async def test_trading_console_applies_live_enablement_mutation_without_orders(monkeypatch):
    runtime_repo = _FakeRuntimeRepo()
    service = StrategyRuntimeInstanceService(
        runtime_repository=runtime_repo,
        admission_repository=_FakeAdmissionRepo(),
    )
    runtime = await service.create_draft_from_trial_binding(
        "binding-1",
        side="long",
        max_attempts=3,
        max_notional_per_attempt=Decimal("10"),
        total_budget=Decimal("3"),
        max_leverage=Decimal("1"),
    )
    active = await service.activate_runtime(runtime.runtime_instance_id)
    active = active.model_copy(
        update={
            "boundary": active.boundary.model_copy(
                update={
                    "max_margin_per_attempt": Decimal("10"),
                    "min_liquidation_stop_buffer": Decimal("25"),
                }
            )
        }
    )
    runtime_repo.items[active.runtime_instance_id] = active
    preview = _ready_live_enablement_preview(active)
    request = StrategyRuntimeLiveEnablementMutationRequest(
        preview=preview,
        owner_live_runtime_enablement_authorization_id="owner-live-runtime-auth-1",
        owner_real_submit_authorization_id="owner-real-submit-auth-1",
        actor="owner",
    )

    monkeypatch.setattr(api_module, "_strategy_runtime_service", service, raising=False)

    mutation = await apply_strategy_runtime_live_enablement_mutation(
        active.runtime_instance_id,
        request,
    )

    saved = runtime_repo.items[active.runtime_instance_id]
    assert mutation.status == "applied"
    assert mutation.runtime_state_mutated is True
    assert saved.execution_enabled is True
    assert saved.shadow_mode is False
    assert mutation.not_order_authority is True
    assert mutation.execution_intent_created is False
    assert mutation.order_created is False
    assert mutation.exchange_called is False
    assert mutation.owner_bounded_execution_called is False
    assert mutation.order_lifecycle_called is False
    assert runtime_repo.events[-1].event_type == "live_runtime_enabled"


def test_existing_bounded_live_trial_authorization_stays_single_use_metadata_only():
    authorization = BoundedLiveTrialAuthorization(
        authorization_id="auth-1",
        draft_id="draft-1",
        carrier_id="carrier-1",
        strategy_family_id="family-1",
        symbol="ETH/USDT:USDT",
        side="long",
        max_notional=Decimal("25"),
        quantity=Decimal("0.01"),
        leverage=Decimal("2"),
        protection_plan_type="single_tp_plus_sl",
        owner_live_authorized_by="owner",
        owner_live_authorized_at_ms=NOW_MS,
        linked_acknowledgement_id="ack-1",
        source_draft_id="draft-1",
        hard_blockers=[],
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )

    assert authorization.single_use is True
    assert authorization.execution_intent_created is False
    assert authorization.order_created is False
    assert authorization.next_executable is False
    assert authorization.metadata_only is True


def _ready_live_enablement_preview(runtime: StrategyRuntimeInstance):
    return build_strategy_runtime_live_enablement_preview(
        runtime=runtime,
        safety_readiness=evaluate_strategy_runtime_safety_readiness(runtime),
        promotion_gate_result=_promotion_gate(runtime, confirmed=True),
        current_head_deployed=True,
        owner_live_runtime_enablement_authorized=True,
        owner_real_submit_authorization_present=True,
        submit_technical_rehearsal_passed=True,
        submit_adapter_implemented=True,
        forbidden_execution_flags=[],
    )


def _promotion_gate(runtime: StrategyRuntimeInstance, *, confirmed: bool):
    binding = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
    )
    return evaluate_strategy_runtime_promotion_gate(
        StrategyRuntimePromotionGateInput(
            binding=binding,
            scope=StrategyRuntimePromotionScope.FIRST_REAL_SUBMIT_GATE_REVIEW,
            semantic_confirmations=(
                _semantic_confirmed() if confirmed else StrategySemanticsConfirmationFacts()
            ),
            runtime_confirmations=(
                _runtime_confirmed() if confirmed else RuntimeExecutionConfirmationFacts()
            ),
            first_real_submit_confirmations=(
                FirstRealSubmitConfirmationFacts(
                    budget_release_or_consume_rule_confirmed=True,
                    post_submit_budget_settlement_persistence_confirmed=True,
                    post_submit_budget_settlement_persistence_evidence_id=(
                        "runtime-post-submit-budget-settlement-persistence-084"
                    ),
                    attempt_outcome_policy_id="runtime-attempt-outcome-policy-test",
                    trusted_submit_fact_snapshot_id=(
                        "trusted-submit-facts-snapshot-test"
                    ),
                    submit_idempotency_policy_id=(
                        "runtime-submit-idempotency-policy-test"
                    ),
                    protection_creation_failure_policy_confirmed=True,
                    protection_creation_failure_policy_id=(
                        "runtime-protection-failure-policy-test"
                    ),
                    local_registration_enablement_decision_id=(
                        "runtime-local-registration-enable-test"
                    ),
                    exchange_submit_enablement_decision_id=(
                        "runtime-exchange-submit-enable-test"
                    ),
                    runtime_submit_rehearsal_id="runtime-submit-rehearsal-test",
                    deployment_readiness_evidence_id=(
                        "runtime-exchange-gateway-readiness-test"
                    ),
                    owner_real_submit_authorization_id=(
                        "owner-real-submit-authorization-test"
                    ),
                    duplicate_submit_policy_confirmed=True,
                    deployment_readiness_confirmed=True,
                    explicit_owner_real_submit_authorization=True,
                )
                if confirmed
                else FirstRealSubmitConfirmationFacts()
            ),
        )
    )
