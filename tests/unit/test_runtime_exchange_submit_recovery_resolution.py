from __future__ import annotations

import importlib.util
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
from src.domain.runtime_execution_exchange_submit_recovery_resolution import (
    RuntimeExecutionExchangeSubmitRecoveryResolutionStatus,
)
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM,
)
from src.infrastructure.pg_runtime_execution_exchange_submit_recovery_resolution_repository import (
    PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository,
)


NOW_MS = 1781090000000


class _DraftRepo:
    async def get(self, draft_id: str):
        raise AssertionError("draft repository should not be used")


class _ExecutionRecoveryRepo:
    def __init__(self, task: dict | None) -> None:
        self.tasks = {}
        if task is not None:
            self.tasks[task["id"]] = dict(task)
        self.mark_resolved_calls = []

    async def get(self, task_id):
        return self.tasks.get(task_id)

    async def create_task(self, **kwargs):
        raise AssertionError("create_task should not be used")

    async def mark_resolved(self, task_id, resolved_at, error_message=None):
        self.mark_resolved_calls.append(
            {
                "task_id": task_id,
                "resolved_at": resolved_at,
                "error_message": error_message,
            }
        )
        self.tasks[task_id]["status"] = "resolved"
        self.tasks[task_id]["resolved_at"] = resolved_at


class _ResolutionRepo:
    def __init__(self) -> None:
        self.records = {}
        self.create_calls = []

    async def create(self, resolution):
        self.records[resolution.recovery_task_id] = resolution
        self.create_calls.append(resolution)
        return resolution

    async def get_by_recovery_task_id(self, recovery_task_id):
        return self.records.get(recovery_task_id)


def _recovery_task(**overrides):
    task = {
        "id": "rt_ex_submit_recovery_test",
        "intent_id": "intent-1",
        "symbol": "BNB/USDT:USDT",
        "recovery_type": "exchange_submit_protection_fail",
        "related_order_id": "runtime-order-draft-auth-1-sl",
        "related_exchange_order_id": "ex-runtime-order-draft-auth-1-entry",
        "error_message": "rejected runtime-order-draft-auth-1-sl",
        "status": "pending",
        "context_payload": {
            "authorization_id": "auth-1",
            "execution_result_id": "runtime-exchange-submit-execution-result-auth-1",
            "runtime_instance_id": "runtime-1",
            "source_type": "brc_runtime_order_candidate",
            "source_id": "candidate-1",
            "entry_order_id": "runtime-order-draft-auth-1-entry",
            "entry_exchange_order_id": "ex-runtime-order-draft-auth-1-entry",
            "failed_protection_order_id": "runtime-order-draft-auth-1-sl",
            "failed_reason": "rejected runtime-order-draft-auth-1-sl",
            "block_new_entries_until_resolved": True,
            "require_owner_recovery_review": True,
            "require_reduce_only_recovery_mode": True,
            "require_reconciliation_before_retry": True,
            "consume_attempt_on_any_fill": True,
            "hold_or_reconcile_budget_until_position_resolved": True,
        },
    }
    task.update(overrides)
    return task


def _service(*, recovery_repo, resolution_repo):
    return RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftRepo(),
        execution_recovery_repository=recovery_repo,
        exchange_submit_recovery_resolution_repository=resolution_repo,
    )


@pytest.mark.asyncio
async def test_exchange_submit_recovery_resolution_blocks_without_owner_confirmations():
    recovery_repo = _ExecutionRecoveryRepo(_recovery_task())
    resolution_repo = _ResolutionRepo()
    service = _service(
        recovery_repo=recovery_repo,
        resolution_repo=resolution_repo,
    )

    resolution = await service.record_exchange_submit_recovery_resolution(
        "rt_ex_submit_recovery_test",
        owner_operator_id="owner",
        reason="reviewed but not fully confirmed",
        owner_confirmed_recovery_resolved=True,
    )

    assert resolution.status == (
        RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.BLOCKED
    )
    assert "owner_reconciliation_review_confirmation_missing" in resolution.blockers
    assert "owner_no_unprotected_position_confirmation_missing" in resolution.blockers
    assert recovery_repo.mark_resolved_calls == []
    assert resolution_repo.create_calls == [resolution]
    assert resolution.exchange_called is False
    assert resolution.order_lifecycle_submit_called is False
    assert resolution.execution_intent_status_changed is False


@pytest.mark.asyncio
async def test_exchange_submit_recovery_resolution_marks_existing_task_resolved():
    recovery_repo = _ExecutionRecoveryRepo(_recovery_task())
    resolution_repo = _ResolutionRepo()
    service = _service(
        recovery_repo=recovery_repo,
        resolution_repo=resolution_repo,
    )

    resolution = await service.record_exchange_submit_recovery_resolution(
        "rt_ex_submit_recovery_test",
        owner_operator_id="owner",
        reason="exchange position and open orders reviewed",
        owner_confirmed_recovery_resolved=True,
        owner_confirmed_reconciliation_reviewed=True,
        owner_confirmed_no_unprotected_position=True,
        owner_confirmed_no_unresolved_exchange_order=True,
        owner_confirmed_budget_reconciled_or_held=True,
        owner_confirmed_attempt_consumed_or_accounted=True,
        owner_confirmation_reference="manual-review-1",
        reconciliation_evidence_id="reconciliation-snapshot-1",
    )

    assert resolution.status == (
        RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.RESOLVED
    )
    assert resolution.recovery_task_marked_resolved is True
    assert resolution.blockers == []
    assert len(recovery_repo.mark_resolved_calls) == 1
    assert (
        recovery_repo.mark_resolved_calls[0]["task_id"]
        == "rt_ex_submit_recovery_test"
    )
    assert "owner recovery resolution recorded" in (
        recovery_repo.mark_resolved_calls[0]["error_message"]
    )
    assert recovery_repo.tasks["rt_ex_submit_recovery_test"]["status"] == "resolved"
    assert resolution_repo.create_calls == [resolution]
    assert resolution.exchange_called is False
    assert resolution.order_lifecycle_submit_called is False
    assert resolution.execution_intent_status_changed is False
    assert resolution.owner_bounded_execution_called is False


@pytest.mark.asyncio
async def test_exchange_submit_recovery_resolution_rejects_wrong_task_type():
    recovery_repo = _ExecutionRecoveryRepo(
        _recovery_task(recovery_type="replace_sl_failed")
    )
    resolution_repo = _ResolutionRepo()
    service = _service(
        recovery_repo=recovery_repo,
        resolution_repo=resolution_repo,
    )

    resolution = await service.record_exchange_submit_recovery_resolution(
        "rt_ex_submit_recovery_test",
        owner_operator_id="owner",
        reason="wrong type should not resolve",
        owner_confirmed_recovery_resolved=True,
        owner_confirmed_reconciliation_reviewed=True,
        owner_confirmed_no_unprotected_position=True,
        owner_confirmed_no_unresolved_exchange_order=True,
        owner_confirmed_budget_reconciled_or_held=True,
        owner_confirmed_attempt_consumed_or_accounted=True,
    )

    assert resolution.status == (
        RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.BLOCKED
    )
    assert "recovery_type_not_exchange_submit_protection_fail" in resolution.blockers
    assert recovery_repo.mark_resolved_calls == []


@pytest.mark.asyncio
async def test_pg_exchange_submit_recovery_resolution_repository_round_trips():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM.__table__.create
        )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    repo = PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository(
        session_maker=session_maker
    )

    service_resolution_repo = _ResolutionRepo()
    recovery_repo = _ExecutionRecoveryRepo(_recovery_task())
    service = _service(
        recovery_repo=recovery_repo,
        resolution_repo=service_resolution_repo,
    )
    resolution = await service.record_exchange_submit_recovery_resolution(
        "rt_ex_submit_recovery_test",
        owner_operator_id="owner",
        reason="exchange position and open orders reviewed",
        owner_confirmed_recovery_resolved=True,
        owner_confirmed_reconciliation_reviewed=True,
        owner_confirmed_no_unprotected_position=True,
        owner_confirmed_no_unresolved_exchange_order=True,
        owner_confirmed_budget_reconciled_or_held=True,
        owner_confirmed_attempt_consumed_or_accounted=True,
        reconciliation_evidence_id="reconciliation-snapshot-1",
    )

    await repo.create(resolution)
    loaded = await repo.get(resolution.resolution_id)
    by_task = await repo.get_by_recovery_task_id(resolution.recovery_task_id)

    await engine.dispose()

    assert loaded is not None
    assert loaded.status == (
        RuntimeExecutionExchangeSubmitRecoveryResolutionStatus.RESOLVED
    )
    assert by_task is not None
    assert by_task.resolution_id == resolution.resolution_id
    assert by_task.recovery_task_marked_resolved is True


@pytest.mark.asyncio
async def test_exchange_submit_recovery_resolution_migration_creates_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-11-077_create_runtime_exchange_submit_recovery_resolutions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "runtime_exchange_submit_recovery_resolution_migration",
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
                    "runtime_execution_exchange_submit_recovery_resolutions"
                )
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "runtime_execution_exchange_submit_recovery_resolutions"
                    )
                }
                unique_constraints = {
                    constraint["name"]
                    for constraint in inspector.get_unique_constraints(
                        "runtime_execution_exchange_submit_recovery_resolutions"
                    )
                }
                sync_conn.exec_driver_sql(
                    """
                    INSERT INTO runtime_execution_exchange_submit_recovery_resolutions (
                        resolution_id,
                        recovery_task_id,
                        recovery_type,
                        status,
                        execution_intent_id,
                        symbol,
                        owner_operator_id,
                        reason,
                        owner_confirmed_recovery_resolved,
                        owner_confirmed_reconciliation_reviewed,
                        owner_confirmed_no_unprotected_position,
                        owner_confirmed_no_unresolved_exchange_order,
                        owner_confirmed_budget_reconciled_or_held,
                        owner_confirmed_attempt_consumed_or_accounted,
                        recovery_task_marked_resolved,
                        blockers,
                        warnings,
                        order_lifecycle_submit_called,
                        execution_intent_status_changed,
                        exchange_order_submitted,
                        exchange_called,
                        owner_bounded_execution_called,
                        withdrawal_or_transfer_created,
                        created_at_ms,
                        metadata,
                        payload
                    ) VALUES (
                        'resolution-1',
                        'rt_ex_submit_recovery_test',
                        'exchange_submit_protection_fail',
                        'resolved',
                        'intent-1',
                        'BNB/USDT:USDT',
                        'owner',
                        'reviewed',
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        1,
                        '[]',
                        '[]',
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        1781090000000,
                        '{}',
                        '{}'
                    )
                    """
                )
                row = sync_conn.exec_driver_sql(
                    "SELECT status, recovery_task_marked_resolved "
                    "FROM runtime_execution_exchange_submit_recovery_resolutions"
                ).one()
                migration.downgrade()
                inspector = inspect(sync_conn)
                assert not inspector.has_table(
                    "runtime_execution_exchange_submit_recovery_resolutions"
                )
                return columns, unique_constraints, row
            finally:
                migration.op = old_op

        columns, unique_constraints, row = await conn.run_sync(upgrade)
    await engine.dispose()

    assert "resolution_id" in columns
    assert "recovery_task_id" in columns
    assert "owner_confirmed_no_unprotected_position" in columns
    assert "exchange_called" in columns
    assert "uq_rt_exchange_recovery_resolution_task" in unique_constraints
    assert row[0] == "resolved"
    assert row[1] == 1
