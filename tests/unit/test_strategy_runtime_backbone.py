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
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeEvent,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
    StrategyRuntimePolicySnapshot,
)
from src.infrastructure.pg_models import (
    PGStrategyRuntimeEventORM,
    PGStrategyRuntimeInstanceORM,
)
from src.infrastructure.pg_strategy_runtime_repository import PgStrategyRuntimeRepository
from src.interfaces import api as api_module
from src.interfaces.api_trading_console import (
    get_strategy_runtime,
    list_strategy_runtimes,
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
                created_at_ms=NOW_MS + 2,
            )
        )
        assert event.runtime_instance_id == found.runtime_instance_id
        async with session_maker() as session:
            count = await session.scalar(select(PGStrategyRuntimeEventORM))
            assert count is not None
    finally:
        await engine.dispose()


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
