from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, OrderRole, OrderStatus, OrderType
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResultStatus,
    build_runtime_execution_order_lifecycle_adapter_lock_result,
    build_runtime_execution_order_lifecycle_adapter_registration_failure_result,
    build_runtime_execution_order_lifecycle_adapter_result,
    build_runtime_execution_orders_for_registration,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionLocalOrderRegistrationDraft,
    RuntimeExecutionOrderRegistrationDraftPreview,
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)
from src.infrastructure.pg_models import (
    PGRuntimeExecutionOrderLifecycleAdapterResultORM,
)
from src.infrastructure.pg_runtime_execution_order_lifecycle_adapter_result_repository import (
    PgRuntimeExecutionOrderLifecycleAdapterResultRepository,
)


NOW_MS = 1781090000000


class _DraftRepo:
    async def get(self, draft_id: str):
        raise AssertionError("draft repository should not be used in this test")


class _Lifecycle:
    def __init__(self, *, fail_on_role: OrderRole | None = None) -> None:
        self.calls = []
        self.fail_on_role = fail_on_role

    async def register_created_order(self, order, *, metadata=None):
        self.calls.append({"order": order, "metadata": metadata or {}})
        if order.order_role == self.fail_on_role:
            raise RuntimeError(f"register_failed_for_{order.order_role.value.lower()}")
        return order


class _AdapterResultRepo:
    def __init__(self) -> None:
        self.stored = None
        self.acquire_calls = 0
        self.complete_calls = 0

    async def acquire_registration_lock(self, result):
        self.acquire_calls += 1
        if self.stored is None:
            self.stored = result
            return True, result
        return False, self.stored

    async def complete_registration(self, result):
        self.complete_calls += 1
        self.stored = result
        return result


def _registration_preview() -> RuntimeExecutionOrderRegistrationDraftPreview:
    semantic_ids = BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        signal_evaluation_id="signal-eval-1",
        order_candidate_id="candidate-1",
    )
    entry_id = "runtime-order-draft-auth-1-entry"
    return RuntimeExecutionOrderRegistrationDraftPreview(
        registration_preview_id="registration-preview-1",
        adapter_preview_id="adapter-preview-1",
        handoff_draft_id="handoff-1",
        preflight_id="preflight-1",
        authorization_id="auth-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        source_type="brc_runtime_order_candidate",
        source_id="candidate-1",
        semantic_ids=semantic_ids,
        status=(
            RuntimeExecutionOrderRegistrationDraftPreviewStatus
            .INPUTS_READY_REGISTRATION_DRAFT_ONLY
        ),
        symbol="BNB/USDT:USDT",
        side="long",
        local_order_registration_drafts=[
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id=entry_id,
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.MARKET,
                order_role=OrderRole.ENTRY,
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=False,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
            RuntimeExecutionLocalOrderRegistrationDraft(
                local_order_draft_id="runtime-order-draft-auth-1-sl",
                signal_id="signal-eval-1",
                symbol="BNB/USDT:USDT",
                direction=Direction.LONG,
                order_type=OrderType.STOP_MARKET,
                order_role=OrderRole.SL,
                trigger_price=Decimal("587.50"),
                requested_qty=Decimal("0.016"),
                status=OrderStatus.CREATED,
                created_at=NOW_MS,
                updated_at=NOW_MS,
                reduce_only=True,
                parent_local_order_draft_id=entry_id,
                runtime_instance_id="runtime-1",
                trial_binding_id="binding-1",
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
                signal_evaluation_id="signal-eval-1",
                order_candidate_id="candidate-1",
            ),
        ],
        registration_draft_count=2,
        entry_registration_draft_count=1,
        protection_registration_draft_count=1,
        created_at_ms=NOW_MS,
    )


def _service_with_preview(
    preview,
    lifecycle=None,
    adapter_result_repo=None,
) -> RuntimeExecutionIntentAdapterService:
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        order_lifecycle_service=lifecycle,
        order_lifecycle_adapter_result_repository=adapter_result_repo,
    )

    async def _preview_for_authorization(authorization_id: str):
        assert authorization_id == preview.authorization_id
        return preview

    service.order_registration_draft_preview_for_authorization = (  # type: ignore[method-assign]
        _preview_for_authorization
    )
    return service


def test_registration_preview_maps_to_order_objects_with_runtime_semantics():
    preview = _registration_preview()

    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )

    assert [order.id for order in orders] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert orders[0].status == OrderStatus.CREATED
    assert orders[0].exchange_order_id is None
    assert orders[0].runtime_instance_id == "runtime-1"
    assert orders[0].strategy_family_version_id == "CPM-001-v0"
    assert orders[0].order_candidate_id == "candidate-1"
    assert orders[1].order_role == OrderRole.SL
    assert orders[1].reduce_only is True
    assert orders[1].parent_order_id == "runtime-order-draft-auth-1-entry"


@pytest.mark.asyncio
async def test_adapter_result_default_disabled_does_not_call_lifecycle():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1"
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .ORDER_LIFECYCLE_ADAPTER_DISABLED
    )
    assert result.blockers == ["order_lifecycle_adapter_disabled"]
    assert result.order_objects_constructed is False
    assert result.local_order_registration_executed is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False
    assert lifecycle.calls == []


@pytest.mark.asyncio
async def test_adapter_result_requires_duplicate_submit_lock_before_registration():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=False,
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .DUPLICATE_SUBMIT_LOCK_REQUIRED
    )
    assert result.blockers == ["persistent_duplicate_submit_lock_required"]
    assert lifecycle.calls == []
    assert result.exchange_called is False


@pytest.mark.asyncio
async def test_adapter_result_registers_created_local_orders_when_explicitly_enabled():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    service = _service_with_preview(preview, lifecycle=lifecycle)

    result = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert result.blockers == []
    assert result.order_objects_constructed is True
    assert result.local_order_registration_executed is True
    assert result.order_lifecycle_called is True
    assert result.exchange_called is False
    assert result.execution_intent_status_changed is False
    assert result.entry_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert result.protection_order_ids == ["runtime-order-draft-auth-1-sl"]
    assert [call["order"].id for call in lifecycle.calls] == result.local_order_ids
    assert all(
        call["metadata"]["exchange_called"] is False for call in lifecycle.calls
    )


def test_runtime_source_native_execution_intent_remains_recorded_after_local_registration_result():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS,
    )
    intent = ExecutionIntent(
        id=preview.execution_intent_id,
        symbol=preview.symbol,
        status=ExecutionIntentStatus.RECORDED,
        source_type=preview.source_type,
        source_id=preview.source_id,
        source_payload={"submit_authorized": False},
        runtime_execution_intent_draft_id="draft-1",
        runtime_instance_id=preview.runtime_instance_id,
        trial_binding_id=preview.semantic_ids.trial_binding_id,
        strategy_family_id=preview.semantic_ids.strategy_family_id,
        strategy_family_version_id=preview.semantic_ids.strategy_family_version_id,
        signal_evaluation_id=preview.semantic_ids.signal_evaluation_id,
        order_candidate_id=preview.semantic_ids.order_candidate_id,
    )

    assert result.status == (
        RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert result.execution_intent_status_changed is False
    assert intent.status == ExecutionIntentStatus.RECORDED
    assert intent.order_id is None
    assert intent.exchange_order_id is None
    assert result.exchange_called is False
    assert result.exchange_order_submitted is False


def test_adapter_registration_failure_result_records_partial_local_state():
    preview = _registration_preview()
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )

    result = build_runtime_execution_order_lifecycle_adapter_registration_failure_result(
        registration_preview=preview,
        attempted_orders=orders,
        registered_orders=[orders[0]],
        failed_order=orders[1],
        failure_reason="RuntimeError",
        failure_message="register_failed_for_sl",
        now_ms=NOW_MS,
    )

    assert (
        result.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .LOCAL_ORDER_REGISTRATION_FAILED
    )
    assert result.local_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert result.entry_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert result.protection_order_ids == []
    assert result.registered_order_count == 1
    assert "local_order_registration_failed" in result.blockers
    assert "protection_order_registration_failed" in result.blockers
    assert (
        "entry_order_registered_without_registered_protection_order"
        in result.warnings
    )
    assert result.order_objects_constructed is True
    assert result.local_order_registration_executed is True
    assert result.order_lifecycle_called is True
    assert result.exchange_called is False
    assert result.exchange_order_submitted is False
    assert result.execution_intent_status_changed is False
    assert result.metadata["failed_local_order_id"] == "runtime-order-draft-auth-1-sl"
    assert result.metadata["requires_manual_review_before_retry"] is True


@pytest.mark.asyncio
async def test_adapter_result_persistent_lock_replays_without_second_registration():
    preview = _registration_preview()
    lifecycle = _Lifecycle()
    adapter_result_repo = _AdapterResultRepo()
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
    )

    first = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
    )
    second = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
    )

    assert (
        first.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert second == first
    assert adapter_result_repo.acquire_calls == 2
    assert adapter_result_repo.complete_calls == 1
    assert [call["order"].id for call in lifecycle.calls] == first.local_order_ids


@pytest.mark.asyncio
async def test_adapter_result_records_protection_registration_failure_and_replays():
    preview = _registration_preview()
    lifecycle = _Lifecycle(fail_on_role=OrderRole.SL)
    adapter_result_repo = _AdapterResultRepo()
    service = _service_with_preview(
        preview,
        lifecycle=lifecycle,
        adapter_result_repo=adapter_result_repo,
    )

    first = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
    )
    second = await service.order_lifecycle_adapter_result_for_authorization(
        "auth-1",
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
    )

    assert (
        first.status
        == RuntimeExecutionOrderLifecycleAdapterResultStatus
        .LOCAL_ORDER_REGISTRATION_FAILED
    )
    assert second == first
    assert adapter_result_repo.acquire_calls == 2
    assert adapter_result_repo.complete_calls == 1
    assert [call["order"].id for call in lifecycle.calls] == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert first.local_order_ids == ["runtime-order-draft-auth-1-entry"]
    assert first.protection_order_ids == []
    assert "protection_order_registration_failed" in first.blockers
    assert first.exchange_called is False
    assert first.exchange_order_submitted is False
    assert first.execution_intent_status_changed is False


@pytest.mark.asyncio
async def test_adapter_result_does_not_acquire_persistent_lock_without_lifecycle_service():
    preview = _registration_preview()
    adapter_result_repo = _AdapterResultRepo()
    service = _service_with_preview(
        preview,
        lifecycle=None,
        adapter_result_repo=adapter_result_repo,
    )

    with pytest.raises(RuntimeError, match="order_lifecycle_service_unavailable"):
        await service.order_lifecycle_adapter_result_for_authorization(
            "auth-1",
            order_lifecycle_adapter_enabled=True,
            local_order_registration_enabled=True,
        )

    assert adapter_result_repo.acquire_calls == 0
    assert adapter_result_repo.complete_calls == 0
    assert adapter_result_repo.stored is None


@pytest.mark.asyncio
async def test_pg_adapter_result_repository_acquires_unique_authorization_lock():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGRuntimeExecutionOrderLifecycleAdapterResultORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionOrderLifecycleAdapterResultRepository(
        session_maker=session_maker
    )
    preview = _registration_preview()
    lock_result = build_runtime_execution_order_lifecycle_adapter_lock_result(
        registration_preview=preview,
        now_ms=NOW_MS,
    )

    acquired_first, stored_first = await repo.acquire_registration_lock(lock_result)
    acquired_second, stored_second = await repo.acquire_registration_lock(lock_result)
    orders = build_runtime_execution_orders_for_registration(
        registration_preview=preview
    )
    final_result = build_runtime_execution_order_lifecycle_adapter_result(
        registration_preview=preview,
        order_lifecycle_adapter_enabled=True,
        local_order_registration_enabled=True,
        duplicate_submit_lock_acquired=True,
        registered_orders=orders,
        now_ms=NOW_MS + 1,
    )
    await repo.complete_registration(final_result)
    loaded = await repo.get_by_authorization_id("auth-1")

    await engine.dispose()

    assert acquired_first is True
    assert stored_first.status == (
        RuntimeExecutionOrderLifecycleAdapterResultStatus
        .LOCAL_REGISTRATION_LOCK_ACQUIRED
    )
    assert acquired_second is False
    assert stored_second.adapter_result_id == lock_result.adapter_result_id
    assert loaded is not None
    assert loaded.status == (
        RuntimeExecutionOrderLifecycleAdapterResultStatus
        .REGISTERED_CREATED_LOCAL_ORDERS
    )
    assert loaded.local_order_ids == [
        "runtime-order-draft-auth-1-entry",
        "runtime-order-draft-auth-1-sl",
    ]
    assert loaded.exchange_called is False
    assert loaded.exchange_order_submitted is False


@pytest.mark.asyncio
async def test_adapter_result_migration_creates_unique_authorization_lock_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-10-068_create_runtime_order_lifecycle_adapter_results.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_order_lifecycle_adapter_result_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        def upgrade(sync_conn):
            old_op = migration.op
            migration.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration.upgrade()
                inspector = inspect(sync_conn)
                assert inspector.has_table(
                    "runtime_execution_order_lifecycle_adapter_results"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_order_lifecycle_adapter_results"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_order_lifecycle_adapter_results"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_order_lifecycle_adapter_results (
                        adapter_result_id,
                        registration_preview_id,
                        adapter_preview_id,
                        handoff_draft_id,
                        preflight_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        side,
                        local_order_ids,
                        entry_order_ids,
                        protection_order_ids,
                        registered_order_count,
                        blockers,
                        warnings,
                        order_lifecycle_adapter_enabled,
                        local_order_registration_enabled,
                        duplicate_submit_lock_acquired,
                        order_objects_constructed,
                        local_order_registration_executed,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        order_lifecycle_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata
                    ) VALUES (
                        'adapter-result-1',
                        'registration-preview-1',
                        'adapter-preview-1',
                        'handoff-1',
                        'preflight-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'local_registration_lock_acquired',
                        'BNB/USDT:USDT',
                        'long',
                        '[]',
                        '[]',
                        '[]',
                        0,
                        '[]',
                        '[]',
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1781090000000,
                        '{}'
                    )
                    """
                )
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_order_lifecycle_adapter_results"
                )
                return columns, unique_constraints
            finally:
                migration.op = old_op

        columns, unique_constraints = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "adapter_result_id" in columns
    assert "authorization_id" in columns
    assert "duplicate_submit_lock_acquired" in columns
    assert "order_lifecycle_called" in columns
    assert "exchange_called" in columns
    assert "uq_rt_ol_adapter_result_authorization" in unique_constraints


@pytest.mark.asyncio
async def test_adapter_result_migration_069_allows_local_registration_failure_rows():
    migrations_dir = Path(__file__).resolve().parents[2] / "migrations/versions"
    migration_068_path = (
        migrations_dir
        / "2026-06-10-068_create_runtime_order_lifecycle_adapter_results.py"
    )
    migration_069_path = (
        migrations_dir
        / "2026-06-10-069_allow_adapter_registration_failure_results.py"
    )

    spec_068 = importlib.util.spec_from_file_location(
        "runtime_order_lifecycle_adapter_result_migration_068",
        migration_068_path,
    )
    spec_069 = importlib.util.spec_from_file_location(
        "runtime_order_lifecycle_adapter_result_migration_069",
        migration_069_path,
    )
    assert spec_068 is not None and spec_068.loader is not None
    assert spec_069 is not None and spec_069.loader is not None
    migration_068 = importlib.util.module_from_spec(spec_068)
    migration_069 = importlib.util.module_from_spec(spec_069)
    spec_068.loader.exec_module(migration_068)
    spec_069.loader.exec_module(migration_069)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        def upgrade(sync_conn):
            old_op_068 = migration_068.op
            old_op_069 = migration_069.op
            migration_068.op = Operations(MigrationContext.configure(sync_conn))
            migration_069.op = Operations(MigrationContext.configure(sync_conn))
            try:
                migration_068.upgrade()
                migration_069.upgrade()
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_order_lifecycle_adapter_results (
                        adapter_result_id,
                        registration_preview_id,
                        adapter_preview_id,
                        handoff_draft_id,
                        preflight_id,
                        authorization_id,
                        execution_intent_id,
                        runtime_instance_id,
                        source_type,
                        source_id,
                        status,
                        symbol,
                        side,
                        local_order_ids,
                        entry_order_ids,
                        protection_order_ids,
                        registered_order_count,
                        blockers,
                        warnings,
                        order_lifecycle_adapter_enabled,
                        local_order_registration_enabled,
                        duplicate_submit_lock_acquired,
                        order_objects_constructed,
                        local_order_registration_executed,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        order_lifecycle_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata
                    ) VALUES (
                        'adapter-result-failure-1',
                        'registration-preview-1',
                        'adapter-preview-1',
                        'handoff-1',
                        'preflight-1',
                        'auth-1',
                        'intent-1',
                        'runtime-1',
                        'brc_runtime_order_candidate',
                        'candidate-1',
                        'local_order_registration_failed',
                        'BNB/USDT:USDT',
                        'long',
                        '["runtime-order-draft-auth-1-entry"]',
                        '["runtime-order-draft-auth-1-entry"]',
                        '[]',
                        1,
                        '["local_order_registration_failed", "protection_order_registration_failed"]',
                        '["entry_order_registered_without_registered_protection_order"]',
                        1,
                        1,
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        1,
                        0,
                        1781090000000,
                        '{"recovery_status": "fail_closed_adapter_result_recorded"}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, registered_order_count "
                    "FROM runtime_execution_order_lifecycle_adapter_results"
                ).one()
                return row
            finally:
                migration_068.op = old_op_068
                migration_069.op = old_op_069

        row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert row[0] == "local_order_registration_failed"
    assert row[1] == 1
