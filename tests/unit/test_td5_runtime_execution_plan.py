from __future__ import annotations

import importlib.util
import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, SignalResult
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPlanStatus,
    RuntimeExecutionControlledSubmitPreflightStatus,
    RuntimeExecutionControlledSubmitResultStatus,
)
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionIntentCreationPreviewStatus,
    RuntimeExecutionIntentSourceType,
    RuntimeExecutionSubmitReadinessStatus,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreviewStatus,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanStatus,
    RuntimeExecutionProtectionPlanPreviewStatus,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffStatus,
)
from src.domain.runtime_execution_order_lifecycle_adapter import (
    RuntimeExecutionOrderLifecycleAdapterPreview,
    RuntimeExecutionOrderLifecycleAdapterPreviewStatus,
)
from src.domain.runtime_execution_order_registration_draft import (
    RuntimeExecutionOrderRegistrationDraftPreviewStatus,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservationStatus,
    RuntimeExecutionAttemptReservationPreviewStatus,
)
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_plan import RuntimeExecutionPlanStatus
from src.domain.runtime_execution_plan import RuntimeExecutionIntentDraftStatus
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.interfaces import api as api_module
from src.interfaces.api_trading_console import (
    record_runtime_execution_intent_for_draft,
    record_runtime_execution_intent_draft_for_order_candidate,
    record_runtime_execution_attempt_reservation_for_authorization,
    apply_runtime_execution_attempt_mutation_for_reservation,
    runtime_execution_order_lifecycle_adapter_preview_for_authorization,
    runtime_execution_order_registration_draft_preview_for_authorization,
    record_runtime_execution_order_lifecycle_handoff_draft_for_authorization,
    record_runtime_execution_protection_plan_for_intent,
    record_runtime_execution_submit_authorization_for_intent,
    runtime_execution_controlled_submit_for_authorization,
    runtime_execution_controlled_submit_plan_for_authorization,
    runtime_execution_controlled_submit_preflight_for_authorization,
    runtime_execution_attempt_reservation_preview_for_authorization,
    runtime_execution_protection_plan_preview_for_intent,
    runtime_execution_submit_adapter_preview_for_authorization,
    runtime_execution_submit_rehearsal_for_authorization,
    runtime_execution_submit_readiness_for_intent,
    runtime_execution_intent_adapter_preview_for_draft,
    runtime_execution_intent_draft_for_order_candidate,
    runtime_execution_plan_for_order_candidate,
)
from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_models import (
    PGExecutionIntentORM,
    PGRuntimeExecutionAttemptMutationORM,
    PGRuntimeExecutionAttemptReservationORM,
    PGRuntimeExecutionControlledSubmitResultORM,
    PGRuntimeExecutionIntentDraftORM,
    PGRuntimeExecutionOrderLifecycleHandoffDraftORM,
    PGRuntimeExecutionProtectionPlanORM,
    PGRuntimeExecutionSubmitAuthorizationORM,
)
from src.infrastructure.pg_runtime_execution_attempt_reservation_repository import (
    PgRuntimeExecutionAttemptReservationRepository,
)
from src.infrastructure.pg_runtime_execution_attempt_mutation_repository import (
    PgRuntimeExecutionAttemptMutationRepository,
)
from src.infrastructure.pg_runtime_execution_protection_plan_repository import (
    PgRuntimeExecutionProtectionPlanRepository,
)
from src.infrastructure.pg_runtime_execution_order_lifecycle_handoff_repository import (
    PgRuntimeExecutionOrderLifecycleHandoffRepository,
)
from src.infrastructure.pg_runtime_execution_controlled_submit_result_repository import (
    PgRuntimeExecutionControlledSubmitResultRepository,
)
from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
    PgRuntimeExecutionIntentDraftRepository,
)
from src.infrastructure.pg_runtime_execution_submit_authorization_repository import (
    PgRuntimeExecutionSubmitAuthorizationRepository,
)


NOW_MS = 1780496665000


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-1",
        trial_binding_id="binding-1",
        admission_decision_id="admission-1",
        strategy_family_id="family-1",
        strategy_family_version_id="version-1",
        symbol="BNB/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=2,
            attempts_used=0,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("20"),
            allowed_symbols=["BNB/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("2"),
            max_margin_per_attempt=Decimal("5"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
            requires_review=True,
        ),
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _candidate(**overrides) -> OrderCandidate:
    values = {
        "order_candidate_id": "candidate-1",
        "signal_evaluation_id": "evaluation-1",
        "runtime_instance_id": "runtime-1",
        "trial_binding_id": "binding-1",
        "strategy_family_id": "family-1",
        "strategy_family_version_id": "version-1",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "candidate_order_type": "market",
        "proposed_quantity": Decimal("0.01"),
        "intended_notional": Decimal("6"),
        "entry_price_reference": Decimal("600"),
        "risk_preview": OrderCandidateRiskPreview(
            intended_notional=Decimal("6"),
            proposed_quantity=Decimal("0.01"),
            leverage=Decimal("1"),
            margin_required=Decimal("3"),
            liquidation_price_reference=Decimal("500"),
            liquidation_stop_buffer=Decimal("25"),
        ),
        "protection_preview": OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="bounded_loss_reference",
            stop_price_reference=Decimal("594"),
        ),
        "rationale": "small risk-capital chain integrity candidate",
        "created_at_ms": NOW_MS,
        "updated_at_ms": NOW_MS,
    }
    values.update(overrides)
    return OrderCandidate(**values)


def _signal() -> SignalResult:
    return SignalResult(
        symbol="BNB/USDT:USDT",
        timeframe="1m",
        direction=Direction.LONG,
        entry_price=Decimal("600"),
        suggested_stop_loss=Decimal("590"),
        suggested_position_size=Decimal("0.01"),
        current_leverage=1,
        tags=[],
        risk_reward_info="adapter source metadata roundtrip",
        status="PENDING",
        strategy_name="brc_runtime_order_candidate_adapter_test",
    )


def _planning_service(
    *,
    active_positions=None,
    intent_draft_repository=None,
    candidate=None,
) -> RuntimeExecutionPlanningService:
    runtime = _runtime()
    candidate = candidate or _candidate()

    class _RuntimeService:
        async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
            assert runtime_instance_id == runtime.runtime_instance_id
            return runtime

    class _SignalService:
        async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
            assert order_candidate_id == candidate.order_candidate_id
            return candidate

    class _PositionSource:
        async def list_active(self, *, symbol: str | None = None, limit: int = 100):
            assert symbol == runtime.symbol
            return list(active_positions or [])

    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=_SignalService(),
        active_position_source=_PositionSource(),
    )
    return RuntimeExecutionPlanningService(
        runtime_service=_RuntimeService(),
        signal_evaluation_service=_SignalService(),
        final_gate_preview_service=final_gate,
        intent_draft_repository=intent_draft_repository,
    )


async def _repo_engine(*tables):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in tables:
            await conn.run_sync(table.create)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_runtime_execution_plan_requires_owner_review_before_intent_draft():
    service = _planning_service(active_positions=[])

    plan = await service.plan_order_candidate(order_candidate_id="candidate-1")

    assert plan.status == RuntimeExecutionPlanStatus.OWNER_REVIEW_REQUIRED
    assert plan.owner_confirmation_required is True
    assert plan.not_execution_intent is True
    assert plan.execution_intent_created is False
    assert plan.order_created is False
    assert "owner_review_required" in plan.final_gate_preview.blockers


async def test_runtime_execution_plan_can_be_ready_for_intent_draft_after_owner_review():
    service = _planning_service(active_positions=[])

    plan = await service.plan_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
    )

    assert plan.status == RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
    assert plan.final_gate_preview.blockers == []
    assert plan.entry_price_reference == Decimal("600")
    assert plan.risk_preview.intended_notional == Decimal("6")
    assert plan.risk_preview.leverage == Decimal("1")
    assert plan.protection_preview.requires_protection is True
    assert plan.protection_preview.stop_reference == "bounded_loss_reference"
    assert plan.submit_enabled is False
    assert plan.exchange_called is False


async def test_runtime_execution_plan_blocks_when_active_position_capacity_exhausted():
    service = _planning_service(active_positions=[object()])

    plan = await service.plan_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
    )

    assert plan.status == RuntimeExecutionPlanStatus.BLOCKED
    assert "active_position_capacity_exhausted" in plan.final_gate_preview.blockers
    assert plan.execution_intent_created is False


async def test_runtime_execution_intent_draft_requires_explicit_owner_confirmation():
    service = _planning_service(active_positions=[])

    draft = await service.intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=False,
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.OWNER_CONFIRMATION_REQUIRED
    assert draft.source_plan_status == RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
    assert draft.not_execution_intent is True
    assert draft.execution_intent_repository_write_enabled is False
    assert draft.execution_intent_created is False
    assert draft.order_created is False


async def test_runtime_execution_intent_draft_can_be_ready_without_creating_intent():
    service = _planning_service(active_positions=[])

    draft = await service.intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.owner_confirmed_for_intent is True
    assert draft.entry_price_reference == Decimal("600")
    assert draft.risk_preview.intended_notional == Decimal("6")
    assert draft.protection_preview.requires_protection is True
    assert draft.execution_intent_created is False
    assert draft.exchange_called is False


async def test_runtime_execution_intent_draft_stays_blocked_when_plan_blocked():
    service = _planning_service(active_positions=[object()])

    draft = await service.intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.BLOCKED
    assert "active_position_capacity_exhausted" in draft.blockers
    assert draft.execution_intent_created is False


def test_runtime_execution_intent_draft_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-048_create_runtime_execution_intent_drafts.py"
    )
    spec = importlib.util.spec_from_file_location("td5_runtime_draft_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_intent_drafts")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_intent_drafts")
                    }
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_intent_drafts")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "draft_id" in columns
    assert "execution_intent_repository_write_enabled" in columns
    assert "execution_intent_created" in columns
    assert "order_created" in columns
    assert "exchange_called" in columns


def test_execution_intent_source_metadata_migration_adds_nullable_columns():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-049_add_execution_intent_source_metadata.py"
    )
    spec = importlib.util.spec_from_file_location("td5_intent_source_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> tuple[set[str], set[str]]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    sync_conn.exec_driver_sql(
                        """
                        CREATE TABLE execution_intents (
                            id VARCHAR(128) PRIMARY KEY,
                            signal_id VARCHAR(128) NOT NULL,
                            symbol VARCHAR(128) NOT NULL,
                            status VARCHAR(32) NOT NULL,
                            signal_payload JSON NOT NULL,
                            created_at INTEGER NOT NULL,
                            updated_at INTEGER NOT NULL
                        )
                        """
                    )
                    migration.upgrade()
                    inspector = inspect(sync_conn)
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("execution_intents")
                    }
                    indexes = {
                        index["name"]
                        for index in inspector.get_indexes("execution_intents")
                    }
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    downgraded_columns = {
                        column["name"]
                        for column in inspector.get_columns("execution_intents")
                    }
                    assert "source_type" not in downgraded_columns
                    assert "runtime_execution_intent_draft_id" not in downgraded_columns
                    return columns, indexes
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns, indexes = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "source_type" in columns
    assert "source_id" in columns
    assert "source_payload" in columns
    assert "runtime_execution_intent_draft_id" in columns
    assert "idx_execution_intents_source" in indexes
    assert "idx_execution_intents_runtime_draft" in indexes


def test_source_native_execution_intent_migration_relaxes_legacy_signal_columns():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-050_make_execution_intents_source_native.py"
    )
    spec = importlib.util.spec_from_file_location("td5_source_native_intent_migration", migration_path)
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
                    sync_conn.exec_driver_sql(
                        """
                        CREATE TABLE execution_intents (
                            id VARCHAR(64) PRIMARY KEY,
                            signal_id VARCHAR(64) NOT NULL,
                            symbol VARCHAR(64) NOT NULL,
                            status VARCHAR(32) NOT NULL,
                            signal_payload JSON NOT NULL,
                            created_at INTEGER NOT NULL,
                            updated_at INTEGER NOT NULL,
                            CONSTRAINT ck_execution_intents_status CHECK (
                                status IN ('pending', 'blocked', 'submitted', 'failed',
                                'protecting', 'partially_protected', 'completed')
                            )
                        )
                        """
                    )
                    migration.upgrade()
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO execution_intents (
                            id, signal_id, symbol, status, signal_payload, created_at, updated_at
                        ) VALUES (
                            'intent-source-native', NULL, 'BNB/USDT:USDT', 'recorded', NULL, 1, 1
                        )
                        """
                    )
                    inspector = inspect(sync_conn)
                    nullable_columns = {
                        column["name"]
                        for column in inspector.get_columns("execution_intents")
                        if column["nullable"]
                    }
                    return nullable_columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    nullable_columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "signal_id" in nullable_columns
    assert "signal_payload" in nullable_columns


def test_runtime_execution_submit_authorization_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-051_create_runtime_execution_submit_authorizations.py"
    )
    spec = importlib.util.spec_from_file_location("td5_submit_auth_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_submit_authorizations")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_submit_authorizations")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_submit_authorizations (
                            authorization_id,
                            execution_intent_id,
                            status,
                            symbol,
                            owner_confirmed_for_submit,
                            owner_submit_authorized,
                            submit_executed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'auth-1',
                            'intent-1',
                            'approved_pending_controlled_submit',
                            'BNB/USDT:USDT',
                            1,
                            1,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_submit_authorizations")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "authorization_id" in columns
    assert "execution_intent_id" in columns
    assert "owner_submit_authorized" in columns
    assert "submit_executed" in columns
    assert "order_created" in columns
    assert "exchange_called" in columns


def test_runtime_execution_controlled_submit_result_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-052_create_runtime_execution_controlled_submit_results.py"
    )
    spec = importlib.util.spec_from_file_location("td5_controlled_submit_result_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_controlled_submit_results")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_controlled_submit_results")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_controlled_submit_results (
                            result_id,
                            plan_id,
                            authorization_id,
                            execution_intent_id,
                            status,
                            blockers,
                            warnings,
                            submit_enabled,
                            submit_executed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'result-1',
                            'plan-1',
                            'auth-1',
                            'intent-1',
                            'submit_adapter_not_enabled',
                            '[]',
                            '[]',
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_controlled_submit_results")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "result_id" in columns
    assert "authorization_id" in columns


def test_runtime_execution_controlled_submit_result_preflight_fact_migration():
    base_migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-052_create_runtime_execution_controlled_submit_results.py"
    )
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-053_add_controlled_submit_preflight_facts.py"
    )
    base_spec = importlib.util.spec_from_file_location("td5_controlled_submit_result_base", base_migration_path)
    spec = importlib.util.spec_from_file_location("td5_controlled_submit_result_preflight", migration_path)
    assert base_spec is not None and base_spec.loader is not None
    assert spec is not None and spec.loader is not None
    base_migration = importlib.util.module_from_spec(base_spec)
    migration = importlib.util.module_from_spec(spec)
    base_spec.loader.exec_module(base_migration)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                base_old_op = base_migration.op
                old_op = migration.op
                operations = Operations(MigrationContext.configure(sync_conn))
                base_migration.op = operations
                migration.op = operations
                try:
                    base_migration.upgrade()
                    migration.upgrade()
                    inspector = inspect(sync_conn)
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_controlled_submit_results")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_controlled_submit_results (
                            result_id,
                            plan_id,
                            preflight_id,
                            authorization_id,
                            execution_intent_id,
                            preflight_status,
                            final_gate_verdict,
                            status,
                            blockers,
                            warnings,
                            submit_enabled,
                            submit_executed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'result-1',
                            'plan-1',
                            'preflight-1',
                            'auth-1',
                            'intent-1',
                            'ready_for_controlled_submit_adapter',
                            'PASS',
                            'submit_adapter_not_enabled',
                            '[]',
                            '[]',
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    downgraded_columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_controlled_submit_results")
                    }
                    assert "preflight_id" not in downgraded_columns
                    base_migration.downgrade()
                    return columns
                finally:
                    base_migration.op = base_old_op
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "preflight_id" in columns
    assert "preflight_status" in columns
    assert "final_gate_verdict" in columns


def test_runtime_execution_controlled_submit_result_order_lifecycle_disabled_migration():
    base_migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-052_create_runtime_execution_controlled_submit_results.py"
    )
    preflight_migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-053_add_controlled_submit_preflight_facts.py"
    )
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-10-066_add_order_lifecycle_adapter_disabled_submit_status.py"
    )
    base_spec = importlib.util.spec_from_file_location(
        "td5_controlled_submit_result_base_066",
        base_migration_path,
    )
    preflight_spec = importlib.util.spec_from_file_location(
        "td5_controlled_submit_result_preflight_066",
        preflight_migration_path,
    )
    spec = importlib.util.spec_from_file_location(
        "td5_controlled_submit_result_order_lifecycle_disabled",
        migration_path,
    )
    assert base_spec is not None and base_spec.loader is not None
    assert preflight_spec is not None and preflight_spec.loader is not None
    assert spec is not None and spec.loader is not None
    base_migration = importlib.util.module_from_spec(base_spec)
    preflight_migration = importlib.util.module_from_spec(preflight_spec)
    migration = importlib.util.module_from_spec(spec)
    base_spec.loader.exec_module(base_migration)
    preflight_spec.loader.exec_module(preflight_migration)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                base_old_op = base_migration.op
                preflight_old_op = preflight_migration.op
                old_op = migration.op
                operations = Operations(MigrationContext.configure(sync_conn))
                base_migration.op = operations
                preflight_migration.op = operations
                migration.op = operations
                try:
                    base_migration.upgrade()
                    preflight_migration.upgrade()
                    migration.upgrade()
                    inspector = inspect(sync_conn)
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_controlled_submit_results")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_controlled_submit_results (
                            result_id,
                            plan_id,
                            preflight_id,
                            authorization_id,
                            execution_intent_id,
                            preflight_status,
                            final_gate_verdict,
                            status,
                            blockers,
                            warnings,
                            submit_enabled,
                            order_lifecycle_adapter_enabled,
                            submit_executed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'result-order-lifecycle-disabled',
                            'plan-1',
                            'preflight-1',
                            'auth-1',
                            'intent-1',
                            'ready_for_controlled_submit_adapter',
                            'PASS',
                            'order_lifecycle_adapter_disabled',
                            '["order_lifecycle_adapter_disabled"]',
                            '[]',
                            1,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    sync_conn.exec_driver_sql(
                        """
                        UPDATE runtime_execution_controlled_submit_results
                        SET status = 'submit_adapter_not_enabled',
                            submit_enabled = 0
                        WHERE result_id = 'result-order-lifecycle-disabled'
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    downgraded_columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_controlled_submit_results")
                    }
                    assert "order_lifecycle_adapter_enabled" not in downgraded_columns
                    preflight_migration.downgrade()
                    base_migration.downgrade()
                    return columns
                finally:
                    base_migration.op = base_old_op
                    preflight_migration.op = preflight_old_op
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "order_lifecycle_adapter_enabled" in columns


def test_orders_status_migration_allows_created_local_order_status():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-10-067_allow_created_order_status.py"
    )
    spec = importlib.util.spec_from_file_location(
        "td5_orders_allow_created_status",
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

    async def _run() -> list[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                operations = Operations(MigrationContext.configure(sync_conn))
                migration.op = operations
                try:
                    sync_conn.exec_driver_sql(
                        """
                        CREATE TABLE orders (
                            id TEXT NOT NULL PRIMARY KEY,
                            status TEXT NOT NULL DEFAULT 'PENDING',
                            CONSTRAINT check_orders_status CHECK (
                                status IN (
                                    'PENDING',
                                    'OPEN',
                                    'PARTIALLY_FILLED',
                                    'FILLED',
                                    'CANCELED',
                                    'REJECTED',
                                    'EXPIRED'
                                )
                            )
                        )
                        """
                    )
                    migration.upgrade()
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO orders (id, status)
                        VALUES
                            ('created-local-order', 'CREATED'),
                            ('submitted-order', 'SUBMITTED'),
                            ('pending-order', 'PENDING')
                        """
                    )
                    rows = sync_conn.exec_driver_sql(
                        "SELECT status FROM orders ORDER BY id"
                    ).fetchall()
                    statuses = [str(row[0]) for row in rows]
                    sync_conn.exec_driver_sql("UPDATE orders SET status = 'PENDING'")
                    migration.downgrade()
                    return statuses
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    statuses = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert statuses == ["CREATED", "PENDING", "SUBMITTED"]


def test_runtime_execution_intent_draft_candidate_snapshot_migration():
    base_migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-048_create_runtime_execution_intent_drafts.py"
    )
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-054_add_runtime_intent_draft_candidate_snapshots.py"
    )
    base_spec = importlib.util.spec_from_file_location("td5_runtime_draft_base", base_migration_path)
    spec = importlib.util.spec_from_file_location("td5_runtime_draft_snapshots", migration_path)
    assert base_spec is not None and base_spec.loader is not None
    assert spec is not None and spec.loader is not None
    base_migration = importlib.util.module_from_spec(base_spec)
    migration = importlib.util.module_from_spec(spec)
    base_spec.loader.exec_module(base_migration)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                base_old_op = base_migration.op
                old_op = migration.op
                operations = Operations(MigrationContext.configure(sync_conn))
                base_migration.op = operations
                migration.op = operations
                try:
                    base_migration.upgrade()
                    migration.upgrade()
                    inspector = inspect(sync_conn)
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_intent_drafts")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_intent_drafts (
                            draft_id,
                            plan_id,
                            runtime_instance_id,
                            order_candidate_id,
                            signal_evaluation_id,
                            status,
                            symbol,
                            side,
                            candidate_order_type,
                            proposed_quantity,
                            intended_notional,
                            entry_price_reference,
                            risk_preview,
                            protection_preview,
                            owner_reviewed,
                            owner_confirmed_for_intent,
                            source_plan_status,
                            final_gate_verdict,
                            blockers,
                            warnings,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'draft-1',
                            'plan-1',
                            'runtime-1',
                            'candidate-1',
                            'evaluation-1',
                            'ready_for_intent_creation',
                            'BNB/USDT:USDT',
                            'long',
                            'market',
                            0.01,
                            6,
                            600,
                            '{}',
                            '{}',
                            1,
                            1,
                            'ready_for_intent_draft',
                            'PASS',
                            '[]',
                            '[]',
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    downgraded_columns = {
                        column["name"]
                        for column in inspect(sync_conn).get_columns("runtime_execution_intent_drafts")
                    }
                    assert "risk_preview" not in downgraded_columns
                    base_migration.downgrade()
                    return columns
                finally:
                    base_migration.op = base_old_op
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "entry_price_reference" in columns
    assert "risk_preview" in columns
    assert "protection_preview" in columns


def test_runtime_execution_attempt_reservation_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-055_create_runtime_execution_attempt_reservations.py"
    )
    spec = importlib.util.spec_from_file_location("td5_attempt_reservation_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_attempt_reservations")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_attempt_reservations")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_attempt_reservations (
                            reservation_id,
                            reservation_preview_id,
                            preflight_id,
                            authorization_id,
                            execution_intent_id,
                            runtime_instance_id,
                            status,
                            symbol,
                            side,
                            intended_notional,
                            attempts_used_before,
                            attempts_remaining_before,
                            attempts_remaining_after,
                            max_attempts,
                            budget_remaining_before,
                            budget_remaining_after,
                            max_active_positions,
                            blockers,
                            warnings,
                            reservation_recorded,
                            runtime_mutation_pending,
                            runtime_budget_mutated,
                            attempt_consumed,
                            execution_intent_status_changed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'reservation-1',
                            'reservation-preview-1',
                            'preflight-1',
                            'auth-1',
                            'intent-1',
                            'runtime-1',
                            'pending_runtime_mutation',
                            'BNB/USDT:USDT',
                            'long',
                            6,
                            0,
                            2,
                            1,
                            2,
                            20,
                            14,
                            1,
                            '[]',
                            '[]',
                            1,
                            1,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_attempt_reservations")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "reservation_id" in columns
    assert "runtime_mutation_pending" in columns
    assert "runtime_budget_mutated" in columns
    assert "attempt_consumed" in columns
    assert "order_created" in columns
    assert "exchange_called" in columns


def test_runtime_execution_attempt_mutation_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-056_create_runtime_execution_attempt_mutations.py"
    )
    spec = importlib.util.spec_from_file_location("td5_attempt_mutation_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_attempt_mutations")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_attempt_mutations")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_attempt_mutations (
                            mutation_id,
                            reservation_id,
                            reservation_preview_id,
                            authorization_id,
                            execution_intent_id,
                            runtime_instance_id,
                            status,
                            runtime_status_before,
                            runtime_status_after,
                            symbol,
                            side,
                            intended_notional,
                            attempts_used_before,
                            attempts_used_after,
                            attempts_remaining_before,
                            attempts_remaining_after,
                            max_attempts,
                            budget_reserved_before,
                            budget_reserved_after,
                            budget_remaining_before,
                            budget_remaining_after,
                            max_active_positions,
                            blockers,
                            warnings,
                            reservation_status,
                            reservation_recorded,
                            runtime_mutation_pending_before,
                            runtime_budget_mutated,
                            attempt_consumed,
                            execution_intent_status_changed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'mutation-1',
                            'reservation-1',
                            'reservation-preview-1',
                            'auth-1',
                            'intent-1',
                            'runtime-1',
                            'applied',
                            'active',
                            'active',
                            'BNB/USDT:USDT',
                            'long',
                            6,
                            0,
                            1,
                            2,
                            1,
                            2,
                            0,
                            6,
                            20,
                            14,
                            1,
                            '[]',
                            '[]',
                            'pending_runtime_mutation',
                            1,
                            1,
                            1,
                            1,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_attempt_mutations")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "mutation_id" in columns
    assert "budget_reserved_before" in columns
    assert "budget_reserved_after" in columns
    assert "runtime_budget_mutated" in columns
    assert "attempt_consumed" in columns
    assert "order_created" in columns
    assert "exchange_called" in columns


def test_runtime_execution_protection_plan_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-057_create_runtime_execution_protection_plans.py"
    )
    spec = importlib.util.spec_from_file_location("td5_protection_plan_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_protection_plans")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns("runtime_execution_protection_plans")
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_protection_plans (
                            protection_plan_id,
                            protection_plan_preview_id,
                            execution_intent_id,
                            status,
                            symbol,
                            side,
                            proposed_quantity,
                            intended_notional,
                            entry_price_reference,
                            requires_protection,
                            stop_reference,
                            stop_price_reference,
                            take_profit_references,
                            risk_preview,
                            protection_preview,
                            blockers,
                            warnings,
                            protection_plan_recorded,
                            not_order,
                            not_exchange_payload,
                            execution_intent_status_changed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'protection-plan-1',
                            'protection-preview-1',
                            'intent-1',
                            'ready_for_submit_adapter',
                            'BNB/USDT:USDT',
                            'long',
                            0.01,
                            6,
                            600,
                            1,
                            'explicit_stop_price',
                            594,
                            '[{"id":"TP1","price":"660","position_ratio":"1"}]',
                            '{}',
                            '{}',
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
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_protection_plans")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "protection_plan_id" in columns
    assert "stop_price_reference" in columns
    assert "take_profit_references" in columns
    assert "not_exchange_payload" in columns
    assert "order_created" in columns
    assert "exchange_called" in columns


def test_runtime_execution_order_lifecycle_handoff_migration_creates_and_downgrades_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-06-09-058_create_runtime_order_lifecycle_handoff_drafts.py"
    )
    spec = importlib.util.spec_from_file_location("td5_order_lifecycle_handoff_migration", migration_path)
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
                    inspector = inspect(sync_conn)
                    assert inspector.has_table("runtime_execution_order_lifecycle_handoff_drafts")
                    columns = {
                        column["name"]
                        for column in inspector.get_columns(
                            "runtime_execution_order_lifecycle_handoff_drafts"
                        )
                    }
                    sync_conn.exec_driver_sql(
                        """
                        INSERT INTO runtime_execution_order_lifecycle_handoff_drafts (
                            handoff_draft_id,
                            preflight_id,
                            authorization_id,
                            execution_intent_id,
                            attempt_mutation_id,
                            protection_plan_id,
                            runtime_instance_id,
                            source_type,
                            source_id,
                            status,
                            symbol,
                            side,
                            direction,
                            entry_order_type,
                            entry_order_role,
                            requested_qty,
                            intended_notional,
                            entry_price_reference,
                            stop_price_reference,
                            take_profit_references,
                            entry_order_draft,
                            protection_order_drafts,
                            blockers,
                            warnings,
                            preflight_status,
                            attempt_mutation_status,
                            protection_plan_status,
                            order_lifecycle_method,
                            handoff_draft_recorded,
                            requires_order_lifecycle_adapter,
                            order_lifecycle_adapter_implemented,
                            execution_intent_status_changed,
                            order_created,
                            exchange_called,
                            owner_bounded_execution_called,
                            order_lifecycle_called,
                            created_at_ms,
                            metadata
                        ) VALUES (
                            'handoff-1',
                            'preflight-1',
                            'auth-1',
                            'intent-1',
                            'mutation-1',
                            'protection-plan-1',
                            'runtime-1',
                            'brc_runtime_order_candidate',
                            'candidate-1',
                            'ready_for_order_lifecycle_adapter',
                            'BNB/USDT:USDT',
                            'long',
                            'LONG',
                            'MARKET',
                            'ENTRY',
                            0.01,
                            6,
                            600,
                            594,
                            '[{"id":"TP1","price":"660","position_ratio":"1"}]',
                            '{"symbol":"BNB/USDT:USDT"}',
                            '[{"order_role":"SL"}]',
                            '[]',
                            '[]',
                            'ready_for_controlled_submit_adapter',
                            'applied',
                            'ready_for_submit_adapter',
                            'register_created_order',
                            1,
                            1,
                            0,
                            0,
                            0,
                            0,
                            0,
                            0,
                            1,
                            '{}'
                        )
                        """
                    )
                    migration.downgrade()
                    inspector = inspect(sync_conn)
                    assert not inspector.has_table("runtime_execution_order_lifecycle_handoff_drafts")
                    return columns
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    columns = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "handoff_draft_id" in columns
    assert "attempt_mutation_id" in columns
    assert "protection_plan_id" in columns
    assert "entry_order_draft" in columns
    assert "protection_order_drafts" in columns
    assert "order_model_drafts" in columns
    assert "order_lifecycle_adapter_implemented" in columns
    assert "order_lifecycle_called" in columns


async def test_runtime_execution_intent_draft_repository_roundtrips_non_executable_draft():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionIntentDraftORM.__table__)
    repo = PgRuntimeExecutionIntentDraftRepository(session_maker=session_maker)
    try:
        draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        saved = await repo.create(draft)
        loaded = await repo.get(saved.draft_id)
        listed = await repo.list_for_order_candidate("candidate-1")

        assert loaded is not None
        assert loaded.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
        assert loaded.entry_price_reference == Decimal("600")
        assert loaded.risk_preview.intended_notional == Decimal("6")
        assert loaded.risk_preview.leverage == Decimal("1")
        assert loaded.protection_preview.requires_protection is True
        assert loaded.protection_preview.stop_reference == "bounded_loss_reference"
        assert loaded.execution_intent_repository_write_enabled is False
        assert loaded.execution_intent_created is False
        assert loaded.order_created is False
        assert listed[0].draft_id == saved.draft_id
    finally:
        await engine.dispose()


async def test_execution_intent_repository_roundtrips_additive_runtime_source_metadata():
    engine, session_maker = await _repo_engine(PGExecutionIntentORM.__table__)
    repo = PgExecutionIntentRepository(session_maker=session_maker)
    try:
        intent = ExecutionIntent(
            id="intent-source-1",
            signal_id="legacy-signal-placeholder-1",
            signal=_signal(),
            status=ExecutionIntentStatus.PENDING,
            source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
            source_id="candidate-1",
            source_payload={
                "runtime_instance_id": "runtime-1",
                "order_candidate_id": "candidate-1",
            },
            runtime_execution_intent_draft_id="runtime-intent-draft-candidate-1",
            runtime_instance_id="runtime-1",
            trial_binding_id="binding-1",
            strategy_family_id="family-1",
            strategy_family_version_id="version-1",
            signal_evaluation_id="evaluation-1",
            order_candidate_id="candidate-1",
        )

        await repo.save(intent)
        loaded = await repo.get("intent-source-1")

        assert loaded is not None
        assert loaded.source_type == "brc_runtime_order_candidate"
        assert loaded.source_id == "candidate-1"
        assert loaded.source_payload == {
            "runtime_instance_id": "runtime-1",
            "order_candidate_id": "candidate-1",
        }
        assert loaded.runtime_execution_intent_draft_id == "runtime-intent-draft-candidate-1"
        assert loaded.order_candidate_id == "candidate-1"
    finally:
        await engine.dispose()


async def test_execution_intent_repository_roundtrips_source_native_recorded_intent():
    engine, session_maker = await _repo_engine(PGExecutionIntentORM.__table__)
    repo = PgExecutionIntentRepository(session_maker=session_maker)
    try:
        intent = ExecutionIntent(
            id="intent-source-native-1",
            symbol="BNB/USDT:USDT",
            status=ExecutionIntentStatus.RECORDED,
            source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
            source_id="candidate-1",
            source_payload={"submit_authorized": False},
            runtime_execution_intent_draft_id="runtime-intent-draft-candidate-1",
            runtime_instance_id="runtime-1",
            trial_binding_id="binding-1",
            strategy_family_id="family-1",
            strategy_family_version_id="version-1",
            signal_evaluation_id="evaluation-1",
            order_candidate_id="candidate-1",
        )

        await repo.save(intent)
        loaded = await repo.get("intent-source-native-1")

        assert loaded is not None
        assert loaded.status == ExecutionIntentStatus.RECORDED
        assert loaded.signal_id is None
        assert loaded.signal is None
        assert loaded.symbol == "BNB/USDT:USDT"
        assert loaded.source_type == "brc_runtime_order_candidate"
        assert loaded.source_payload == {"submit_authorized": False}
        assert loaded.order_id is None
        assert loaded.exchange_order_id is None
    finally:
        await engine.dispose()


async def test_service_records_runtime_execution_intent_draft_without_creating_intent():
    class _DraftRepo:
        def __init__(self):
            self.items = []

        async def create(self, draft):
            self.items.append(draft)
            return draft

    repo = _DraftRepo()
    service = _planning_service(active_positions=[], intent_draft_repository=repo)

    draft = await service.record_intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert repo.items == [draft]
    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.execution_intent_created is False
    assert draft.order_created is False


async def test_runtime_execution_intent_adapter_preview_is_owner_gated_and_non_executing():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    preview = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
    )

    result = await preview.preview_from_draft(draft.draft_id)

    assert result.status == RuntimeExecutionIntentCreationPreviewStatus.READY_FOR_OWNER_GATED_CREATION
    assert result.source_type == RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE
    assert result.source_id == "candidate-1"
    assert result.runtime_execution_intent_draft_id == draft.draft_id
    assert result.source_payload["runtime_instance_id"] == "runtime-1"
    assert result.source_payload["entry_price_reference"] == "600"
    assert result.source_payload["risk_preview"]["intended_notional"] == "6"
    assert result.source_payload["risk_preview"]["leverage"] == "1"
    assert result.source_payload["protection_preview"]["requires_protection"] is True
    assert result.source_payload["protection_preview"]["stop_reference"] == "bounded_loss_reference"
    assert result.requires_owner_gated_creation is True
    assert result.compatibility_signal_result_created is False
    assert result.execution_intent_repository_write_enabled is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.not_execution_intent is True


async def test_runtime_execution_intent_adapter_preview_blocks_unconfirmed_draft():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=False,
    )

    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
    )

    result = await service.preview_from_draft(draft.draft_id)

    assert result.status == RuntimeExecutionIntentCreationPreviewStatus.BLOCKED
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_runtime_execution_intent_adapter_creates_recorded_source_native_intent_only():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )

    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    assert intent_repo.items == [intent]
    assert intent.status == ExecutionIntentStatus.RECORDED
    assert intent.signal is None
    assert intent.signal_id is None
    assert intent.symbol == "BNB/USDT:USDT"
    assert intent.source_type == "brc_runtime_order_candidate"
    assert intent.source_id == "candidate-1"
    assert intent.source_payload["entry_price_reference"] == "600"
    assert intent.source_payload["risk_preview"]["intended_notional"] == "6"
    assert intent.source_payload["protection_preview"]["stop_reference"] == "bounded_loss_reference"
    assert intent.source_payload["submit_authorized"] is False
    assert intent.source_payload["order_created"] is False
    assert intent.source_payload["exchange_called"] is False
    assert intent.order_id is None
    assert intent.exchange_order_id is None


async def test_runtime_execution_intent_adapter_refuses_to_create_from_unconfirmed_draft():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=False,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )

    with pytest.raises(ValueError, match="not ready"):
        await service.create_recorded_intent_from_draft(draft.draft_id)

    assert intent_repo.items == []


async def test_runtime_execution_submit_readiness_requires_owner_submit_authorization():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    readiness = await service.submit_readiness_for_intent(intent.id)

    assert readiness.status == RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED
    assert readiness.execution_intent_id == intent.id
    assert readiness.source_type == "brc_runtime_order_candidate"
    assert readiness.source_id == "candidate-1"
    assert readiness.side == "long"
    assert readiness.blockers == []
    assert readiness.requires_owner_submit_authorization is True
    assert readiness.submit_authorized is False
    assert readiness.order_created is False
    assert readiness.exchange_called is False
    assert readiness.owner_bounded_execution_called is False
    assert readiness.order_lifecycle_called is False


async def test_runtime_execution_protection_plan_preview_accepts_bounded_loss_stop_without_order():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    preview = await service.protection_plan_preview_for_intent(intent.id)

    assert preview.status == RuntimeExecutionProtectionPlanPreviewStatus.READY_FOR_SUBMIT_ADAPTER
    assert preview.blockers == []
    assert "take_profit_or_exit_policy_snapshot_missing" in preview.warnings
    assert preview.entry_price_reference == Decimal("600")
    assert preview.risk_preview["intended_notional"] == "6"
    assert preview.protection_preview["stop_reference"] == "bounded_loss_reference"
    assert preview.not_order is True
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_protection_plan_preview_can_be_ready_from_candidate_prices():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    preview = await service.protection_plan_preview_for_intent(intent.id)

    assert preview.status == RuntimeExecutionProtectionPlanPreviewStatus.READY_FOR_SUBMIT_ADAPTER
    assert preview.blockers == []
    assert preview.stop_price_reference == Decimal("594")
    assert preview.take_profit_references == [
        {"id": "TP1", "price": "660", "position_ratio": "1"}
    ]
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_protection_plan_records_ready_candidate_prices():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    protection_repo = _ProtectionPlanRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        protection_plan_repository=protection_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    plan = await service.record_protection_plan_for_intent(intent.id)

    assert protection_repo.items == [plan]
    assert plan.status == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
    assert plan.blockers == []
    assert plan.stop_price_reference == Decimal("594")
    assert plan.take_profit_references == [
        {"id": "TP1", "price": "660", "position_ratio": "1"}
    ]
    assert plan.protection_plan_recorded is True
    assert plan.not_order is True
    assert plan.not_exchange_payload is True
    assert plan.execution_intent_status_changed is False
    assert plan.order_created is False
    assert plan.exchange_called is False
    assert plan.owner_bounded_execution_called is False
    assert plan.order_lifecycle_called is False


async def test_runtime_execution_protection_plan_records_bounded_loss_stop_without_order():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    protection_repo = _ProtectionPlanRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        protection_plan_repository=protection_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    plan = await service.record_protection_plan_for_intent(intent.id)

    assert plan.status == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
    assert plan.blockers == []
    assert plan.stop_price_reference == Decimal("594")
    assert plan.protection_plan_recorded is True
    assert plan.not_order is True
    assert plan.not_exchange_payload is True
    assert plan.order_created is False
    assert plan.exchange_called is False
    assert plan.owner_bounded_execution_called is False
    assert plan.order_lifecycle_called is False


async def test_runtime_execution_protection_plan_repository_roundtrips_ready_plan():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionProtectionPlanORM.__table__)
    repo = PgRuntimeExecutionProtectionPlanRepository(session_maker=session_maker)
    try:
        candidate = _candidate(
            protection_preview=OrderCandidateProtectionPreview(
                requires_protection=True,
                stop_reference="explicit_stop_price",
                stop_price_reference=Decimal("594"),
                take_profit_references=[
                    {"id": "TP1", "price": "660", "position_ratio": "1"}
                ],
            )
        )
        draft = await _planning_service(
            active_positions=[],
            candidate=candidate,
        ).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=_IntentRecorder(),
            protection_plan_repository=repo,
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)

        saved = await service.record_protection_plan_for_intent(intent.id)
        loaded = await repo.get(saved.protection_plan_id)

        assert loaded is not None
        assert loaded.status == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
        assert loaded.stop_price_reference == Decimal("594")
        assert loaded.take_profit_references == [
            {"id": "TP1", "price": "660", "position_ratio": "1"}
        ]
        assert loaded.protection_preview["stop_reference"] == "explicit_stop_price"
        assert loaded.not_order is True
        assert loaded.not_exchange_payload is True
        assert loaded.order_created is False
        assert loaded.exchange_called is False
    finally:
        await engine.dispose()


async def test_runtime_execution_submit_readiness_blocks_legacy_signal_projection():
    intent = ExecutionIntent(
        id="intent-legacy-runtime-bad",
        symbol="BNB/USDT:USDT",
        signal_id="signal-legacy-bad",
        signal=_signal(),
        status=ExecutionIntentStatus.RECORDED,
        source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
        source_id="candidate-1",
        source_payload={"side": "long", "submit_authorized": False},
        runtime_execution_intent_draft_id="runtime-intent-draft-candidate-1",
        runtime_instance_id="runtime-1",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )
    readiness = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({}),
        intent_repository=_IntentRecorder([intent]),
    )

    result = await readiness.submit_readiness_for_intent(intent.id)

    assert result.status == RuntimeExecutionSubmitReadinessStatus.BLOCKED
    assert "legacy_signal_projection_present" in result.blockers
    assert result.submit_authorized is False
    assert result.exchange_called is False


async def test_runtime_execution_submit_authorization_repository_roundtrips_non_submitting_record():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionSubmitAuthorizationORM.__table__)
    repo = PgRuntimeExecutionSubmitAuthorizationRepository(session_maker=session_maker)
    try:
        draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        intent_repo = _IntentRecorder()
        auth_repo = _SubmitAuthorizationRecorder()
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=intent_repo,
            submit_authorization_repository=auth_repo,
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)
        authorization = await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )

        saved = await repo.create(authorization)
        loaded = await repo.get(saved.authorization_id)

        assert loaded is not None
        assert loaded.status == (
            RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
        )
        assert loaded.owner_submit_authorized is True
        assert loaded.submit_executed is False
        assert loaded.order_created is False
        assert loaded.exchange_called is False
        assert loaded.owner_bounded_execution_called is False
        assert loaded.order_lifecycle_called is False
        assert loaded.execution_intent_id == intent.id
    finally:
        await engine.dispose()


async def test_runtime_execution_submit_authorization_requires_explicit_owner_confirmation():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)

    with pytest.raises(ValueError, match="owner_submit_confirmation_required"):
        await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=False,
        )

    assert auth_repo.items == []


async def test_runtime_execution_submit_authorization_refuses_blocked_readiness():
    intent = ExecutionIntent(
        id="intent-legacy-runtime-bad",
        symbol="BNB/USDT:USDT",
        signal_id="signal-legacy-bad",
        signal=_signal(),
        status=ExecutionIntentStatus.RECORDED,
        source_type=RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE.value,
        source_id="candidate-1",
        source_payload={"side": "long", "submit_authorized": False},
        runtime_execution_intent_draft_id="runtime-intent-draft-candidate-1",
        runtime_instance_id="runtime-1",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({}),
        intent_repository=_IntentRecorder([intent]),
        submit_authorization_repository=auth_repo,
    )

    with pytest.raises(ValueError, match="not ready"):
        await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )

    assert auth_repo.items == []


async def test_runtime_execution_controlled_submit_plan_is_ready_without_submitting():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    plan = await service.controlled_submit_plan_for_authorization(authorization.authorization_id)

    assert plan.status == RuntimeExecutionControlledSubmitPlanStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert plan.authorization_id == authorization.authorization_id
    assert plan.execution_intent_id == intent.id
    assert plan.symbol == "BNB/USDT:USDT"
    assert plan.side == "long"
    assert plan.candidate_order_type == "market"
    assert plan.proposed_quantity == Decimal("0.01")
    assert plan.intended_notional == Decimal("6")
    assert plan.blockers == []
    assert plan.requires_final_gate_execution_check is True
    assert plan.owner_submit_authorized is True
    assert plan.submit_executed is False
    assert plan.order_created is False
    assert plan.exchange_called is False
    assert plan.owner_bounded_execution_called is False
    assert plan.order_lifecycle_called is False


async def test_runtime_execution_controlled_submit_plan_blocks_mismatched_authorization():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    mismatched = authorization.model_copy(update={"source_id": "other-candidate"})
    auth_repo.items = [mismatched]

    plan = await service.controlled_submit_plan_for_authorization(mismatched.authorization_id)

    assert plan.status == RuntimeExecutionControlledSubmitPlanStatus.BLOCKED
    assert "source_id_mismatch" in plan.blockers
    assert plan.submit_executed is False
    assert plan.order_created is False
    assert plan.exchange_called is False


async def test_runtime_execution_controlled_submit_preflight_reruns_runtime_final_gate():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    final_gate = _FinalGatePreviewLookup(
        _planning_service(active_positions=[])._final_gate_preview_service.preview(
            runtime=_runtime(),
            candidate=_candidate(),
            active_positions_count=0,
            owner_reviewed=True,
        )
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=final_gate,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    preflight = await service.controlled_submit_preflight_for_authorization(
        authorization.authorization_id
    )

    assert preflight.status == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert preflight.final_gate_verdict.value == "PASS"
    assert preflight.blockers == []
    assert final_gate.calls == [
        {
            "order_candidate_id": "candidate-1",
            "active_positions_count": None,
            "owner_reviewed": True,
        }
    ]
    assert preflight.submit_executed is False
    assert preflight.order_created is False
    assert preflight.exchange_called is False
    assert preflight.owner_bounded_execution_called is False
    assert preflight.order_lifecycle_called is False


async def test_runtime_execution_controlled_submit_preflight_blocks_final_gate_block():
    final_gate = _FinalGatePreviewLookup(
        _planning_service(active_positions=[object()])._final_gate_preview_service.preview(
            runtime=_runtime(),
            candidate=_candidate(),
            active_positions_count=1,
            owner_reviewed=True,
        )
    )
    # Build the recorded chain from a ready draft, then force the execution-time
    # final gate to block. This isolates submit-time drift from draft creation.
    ready_draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({ready_draft.draft_id: ready_draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=final_gate,
    )
    intent = await service.create_recorded_intent_from_draft(ready_draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    preflight = await service.controlled_submit_preflight_for_authorization(
        authorization.authorization_id
    )

    assert preflight.status == RuntimeExecutionControlledSubmitPreflightStatus.BLOCKED
    assert "runtime_final_gate_execution_check_not_passed" in preflight.blockers
    assert "active_position_capacity_exhausted" in preflight.blockers
    assert preflight.submit_executed is False
    assert preflight.order_created is False
    assert preflight.exchange_called is False


async def test_runtime_execution_submit_adapter_preview_inputs_ready_for_dry_run_only():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    preview = await service.controlled_submit_adapter_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == (
        RuntimeExecutionSubmitAdapterPreviewStatus
        .INPUTS_READY_ADAPTER_NOT_IMPLEMENTED
    )
    assert preview.blockers == []
    assert preview.submit_adapter_implemented is False
    assert "take_profit_or_exit_policy_snapshot_missing" in preview.warnings
    assert preview.entry_price_reference == Decimal("600")
    assert preview.risk_preview["intended_notional"] == "6"
    assert preview.protection_preview["stop_reference"] == "bounded_loss_reference"
    assert preview.attempt_reservation_preview.status == (
        RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
    )
    assert preview.attempt_reservation_preview.attempts_remaining_before == 2
    assert preview.attempt_reservation_preview.attempts_remaining_after == 1
    assert preview.attempt_reservation_preview.budget_remaining_before == Decimal("20")
    assert preview.attempt_reservation_preview.budget_remaining_after == Decimal("14")
    assert preview.runtime_budget_mutated is False
    assert preview.attempt_consumed is False
    assert preview.execution_intent_status_changed is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_submit_rehearsal_requires_local_order_binding_repository():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    with pytest.raises(
        RuntimeError,
        match="runtime_execution_order_lifecycle_adapter_result_repository_unavailable",
    ):
        await service.submit_rehearsal_for_authorization(
            authorization.authorization_id
        )


async def test_runtime_execution_submit_rehearsal_blocks_final_gate_drift():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_blocked_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    with pytest.raises(
        RuntimeError,
        match="runtime_execution_order_lifecycle_adapter_result_repository_unavailable",
    ):
        await service.submit_rehearsal_for_authorization(
            authorization.authorization_id
        )

    preflight = await service.controlled_submit_preflight_for_authorization(
        authorization.authorization_id
    )
    assert preflight.status == RuntimeExecutionControlledSubmitPreflightStatus.BLOCKED
    assert "runtime_final_gate_execution_check_not_passed" in preflight.blockers
    assert "active_position_capacity_exhausted" in preflight.blockers
    assert preflight.order_created is False
    assert preflight.exchange_called is False
    assert runtime_service.runtime.boundary.attempts_used == 0
    assert runtime_service.events == []


async def test_runtime_execution_attempt_reservation_preview_checks_budget_without_mutation():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    preview = await service.attempt_reservation_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
    assert preview.attempts_used_before == 0
    assert preview.attempts_remaining_before == 2
    assert preview.attempts_remaining_after == 1
    assert preview.budget_remaining_before == Decimal("20")
    assert preview.budget_remaining_after == Decimal("14")
    assert "max_loss_reference_missing_using_intended_notional_budget_reservation" in (
        preview.warnings
    )
    assert preview.metadata["budget_reservation_basis"] == "intended_notional_fallback"
    assert preview.metadata["budget_reservation_amount"] == "6"
    assert preview.reservation_recorded is False
    assert preview.runtime_budget_mutated is False
    assert preview.attempt_consumed is False
    assert preview.order_created is False
    assert preview.exchange_called is False


async def test_runtime_execution_attempt_reservation_is_recorded_as_pending_without_mutation():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )

    assert reservation_repo.items == [reservation]
    assert reservation.status == RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
    assert reservation.reservation_recorded is True
    assert reservation.runtime_mutation_pending is True
    assert reservation.runtime_budget_mutated is False
    assert reservation.attempt_consumed is False
    assert reservation.execution_intent_status_changed is False
    assert reservation.order_created is False
    assert reservation.exchange_called is False
    assert reservation.owner_bounded_execution_called is False
    assert reservation.order_lifecycle_called is False
    assert reservation.attempts_remaining_before == 2
    assert reservation.attempts_remaining_after == 1
    assert reservation.budget_remaining_before == Decimal("20")
    assert reservation.budget_remaining_after == Decimal("14")
    assert "max_loss_reference_missing_using_intended_notional_budget_reservation" in (
        reservation.warnings
    )
    assert reservation.metadata["budget_reservation_basis"] == "intended_notional_fallback"
    assert reservation.metadata["budget_reservation_amount"] == "6"


async def test_runtime_execution_attempt_reservation_repository_roundtrips_pending_record():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionAttemptReservationORM.__table__)
    repo = PgRuntimeExecutionAttemptReservationRepository(session_maker=session_maker)
    try:
        draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=_IntentRecorder(),
            submit_authorization_repository=_SubmitAuthorizationRecorder(),
            attempt_reservation_repository=repo,
            final_gate_preview_service=_ready_final_gate_lookup(),
            runtime_service=_RuntimeLookup(),
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)
        authorization = await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )

        saved = await service.record_attempt_reservation_for_authorization(
            authorization.authorization_id
        )
        loaded = await repo.get(saved.reservation_id)

        assert loaded is not None
        assert loaded.status == RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
        assert loaded.reservation_preview_id == saved.reservation_preview_id
        assert loaded.execution_intent_id == intent.id
        assert loaded.runtime_instance_id == "runtime-1"
        assert loaded.intended_notional == Decimal("6")
        assert loaded.attempts_remaining_before == 2
        assert loaded.attempts_remaining_after == 1
        assert loaded.budget_remaining_before == Decimal("20")
        assert loaded.budget_remaining_after == Decimal("14")
        assert loaded.reservation_recorded is True
        assert loaded.runtime_mutation_pending is True
        assert loaded.runtime_budget_mutated is False
        assert loaded.attempt_consumed is False
        assert loaded.order_created is False
        assert loaded.exchange_called is False
        assert loaded.owner_bounded_execution_called is False
        assert loaded.order_lifecycle_called is False
    finally:
        await engine.dispose()


async def test_runtime_execution_attempt_mutation_applies_runtime_budget_and_attempt_state():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )

    mutation = await service.apply_attempt_mutation_for_reservation(
        reservation.reservation_id
    )

    assert mutation_repo.items == [mutation]
    assert mutation.status == RuntimeExecutionAttemptMutationStatus.APPLIED
    assert mutation.runtime_budget_mutated is True
    assert mutation.attempt_consumed is True
    assert mutation.execution_intent_status_changed is False
    assert mutation.order_created is False
    assert mutation.exchange_called is False
    assert mutation.owner_bounded_execution_called is False
    assert mutation.order_lifecycle_called is False
    assert mutation.attempts_used_before == 0
    assert mutation.attempts_used_after == 1
    assert mutation.attempts_remaining_before == 2
    assert mutation.attempts_remaining_after == 1
    assert mutation.budget_reserved_before == Decimal("0")
    assert mutation.budget_reserved_after == Decimal("6")
    assert mutation.budget_remaining_before == Decimal("20")
    assert mutation.budget_remaining_after == Decimal("14")
    assert mutation.reservation_budget_remaining_after == Decimal("14")
    assert "max_loss_reference_missing_using_intended_notional_budget_reservation" in (
        mutation.warnings
    )
    assert mutation.metadata["budget_reservation_basis"] == "intended_notional_fallback"
    assert mutation.metadata["budget_reservation_amount"] == "6"
    assert runtime_service.runtime.boundary.attempts_used == 1
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("6")
    assert runtime_service.runtime.budget_remaining == Decimal("14")
    assert runtime_service.events[-1].metadata["order_created"] is False
    assert runtime_service.events[-1].metadata["exchange_called"] is False


async def test_runtime_execution_attempt_budget_prefers_max_loss_reference_over_notional():
    candidate = _candidate(
        risk_preview=OrderCandidateRiskPreview(
            intended_notional=Decimal("6"),
            proposed_quantity=Decimal("0.01"),
            max_loss_reference=Decimal("2"),
            leverage=Decimal("1"),
            margin_required=Decimal("3"),
            liquidation_price_reference=Decimal("500"),
            liquidation_stop_buffer=Decimal("25"),
        ),
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    preview = await service.attempt_reservation_preview_for_authorization(
        authorization.authorization_id
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    mutation = await service.apply_attempt_mutation_for_reservation(
        reservation.reservation_id
    )

    assert preview.budget_remaining_before == Decimal("20")
    assert preview.budget_remaining_after == Decimal("18")
    assert preview.metadata["budget_reservation_basis"] == "max_loss_reference"
    assert preview.metadata["budget_reservation_amount"] == "2"
    assert reservation.budget_remaining_after == Decimal("18")
    assert reservation.metadata["budget_reservation_basis"] == "max_loss_reference"
    assert mutation.status == RuntimeExecutionAttemptMutationStatus.APPLIED
    assert mutation.budget_reserved_after == Decimal("2")
    assert mutation.budget_remaining_after == Decimal("18")
    assert mutation.metadata["budget_reservation_basis"] == "max_loss_reference"
    assert mutation.metadata["budget_reservation_amount"] == "2"
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("2")
    assert runtime_service.runtime.budget_remaining == Decimal("18")


async def test_runtime_execution_attempt_mutation_blocks_stale_runtime_state_without_mutation():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    runtime_service.runtime = _runtime().model_copy(
        update={
            "boundary": _runtime().boundary.model_copy(
                update={"attempts_used": 1, "budget_reserved": Decimal("6")}
            )
        }
    )

    mutation = await service.apply_attempt_mutation_for_reservation(
        reservation.reservation_id
    )

    assert mutation.status == RuntimeExecutionAttemptMutationStatus.BLOCKED
    assert "runtime_attempt_state_drift" in mutation.blockers
    assert "runtime_budget_state_drift" in mutation.blockers
    assert mutation.runtime_budget_mutated is False
    assert mutation.attempt_consumed is False
    assert mutation.order_created is False
    assert mutation.exchange_called is False
    assert runtime_service.runtime.boundary.attempts_used == 1
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("6")
    assert runtime_service.events == []


async def test_runtime_execution_attempt_mutation_repository_roundtrips_applied_record():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionAttemptMutationORM.__table__)
    repo = PgRuntimeExecutionAttemptMutationRepository(session_maker=session_maker)
    try:
        draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        reservation_repo = _AttemptReservationRecorder()
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=_IntentRecorder(),
            submit_authorization_repository=_SubmitAuthorizationRecorder(),
            attempt_reservation_repository=reservation_repo,
            attempt_mutation_repository=repo,
            final_gate_preview_service=_ready_final_gate_lookup(),
            runtime_service=_RuntimeMutator(),
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)
        authorization = await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )
        reservation = await service.record_attempt_reservation_for_authorization(
            authorization.authorization_id
        )

        saved = await service.apply_attempt_mutation_for_reservation(
            reservation.reservation_id
        )
        loaded = await repo.get(saved.mutation_id)

        assert loaded is not None
        assert loaded.status == RuntimeExecutionAttemptMutationStatus.APPLIED
        assert loaded.reservation_id == reservation.reservation_id
        assert loaded.runtime_budget_mutated is True
        assert loaded.attempt_consumed is True
        assert loaded.budget_reserved_before == Decimal("0")
        assert loaded.budget_reserved_after == Decimal("6")
        assert loaded.budget_remaining_after == Decimal("14")
        assert loaded.order_created is False
        assert loaded.exchange_called is False
        assert loaded.owner_bounded_execution_called is False
        assert loaded.order_lifecycle_called is False
    finally:
        await engine.dispose()


async def test_runtime_execution_order_lifecycle_handoff_records_ready_adapter_input_without_order():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    protection_repo = _ProtectionPlanRecorder()
    handoff_repo = _OrderLifecycleHandoffRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        protection_plan_repository=protection_repo,
        order_lifecycle_handoff_repository=handoff_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeMutator(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    await service.record_protection_plan_for_intent(intent.id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    await service.apply_attempt_mutation_for_reservation(reservation.reservation_id)

    handoff = await service.record_order_lifecycle_handoff_draft_for_authorization(
        authorization.authorization_id
    )

    assert handoff_repo.items == [handoff]
    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert handoff.blockers == []
    assert handoff.symbol == "BNB/USDT:USDT"
    assert handoff.direction == Direction.LONG
    assert handoff.entry_order_type.value == "MARKET"
    assert handoff.requested_qty == Decimal("0.01")
    assert handoff.stop_price_reference == Decimal("594")
    assert handoff.take_profit_references == [
        {"id": "TP1", "price": "660", "position_ratio": "1"}
    ]
    assert handoff.entry_order_draft["symbol"] == "BNB/USDT:USDT"
    assert handoff.entry_order_draft["requested_qty"] == "0.01"
    assert handoff.entry_order_draft["order_role"] == "ENTRY"
    assert {draft["order_role"] for draft in handoff.protection_order_drafts} == {
        "SL",
        "TP1",
    }
    assert len(handoff.order_model_drafts) == 3
    assert handoff.order_model_drafts[0]["local_order_draft_id"].endswith("-entry")
    assert len(handoff.order_model_drafts[0]["local_order_draft_id"]) <= 64
    assert handoff.order_model_drafts[0]["signal_id"] == "evaluation-1"
    assert handoff.order_model_drafts[0]["status"] == "CREATED"
    assert handoff.order_model_drafts[0]["runtime_instance_id"] == "runtime-1"
    assert handoff.order_model_drafts[0]["persisted"] is False
    assert handoff.order_model_drafts[1]["parent_local_order_draft_id"] == (
        handoff.order_model_drafts[0]["local_order_draft_id"]
    )
    assert len(handoff.order_model_drafts[1]["local_order_draft_id"]) <= 64
    assert len(handoff.order_model_drafts[1]["parent_local_order_draft_id"]) <= 64
    assert handoff.order_model_drafts[1]["reduce_only"] is True
    assert handoff.order_model_drafts[1]["order_lifecycle_called"] is False
    assert handoff.order_model_drafts[1]["exchange_called"] is False
    assert handoff.handoff_draft_recorded is True
    assert handoff.requires_order_lifecycle_adapter is True
    assert handoff.order_lifecycle_adapter_implemented is False
    assert handoff.execution_intent_status_changed is False
    assert handoff.order_created is False
    assert handoff.exchange_called is False
    assert handoff.owner_bounded_execution_called is False
    assert handoff.order_lifecycle_called is False


@pytest.mark.asyncio
async def test_order_lifecycle_handoff_aligns_quantities_to_trusted_market_step():
    candidate = _candidate(
        proposed_quantity=Decimal("0.0752842"),
        intended_notional=Decimal("6"),
        entry_price_reference=Decimal("600"),
        risk_preview=OrderCandidateRiskPreview(
            intended_notional=Decimal("6"),
            proposed_quantity=Decimal("0.0752842"),
            leverage=Decimal("1"),
            margin_required=Decimal("3"),
            liquidation_price_reference=Decimal("0"),
            liquidation_stop_buffer=Decimal("130"),
        ),
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="bounded_loss_reference",
            stop_price_reference=Decimal("594"),
        ),
    )
    trusted_facts = _TrustedSubmitFactsLookup(
        market_rule_metadata={
            "min_qty": "0.01",
            "step_size": "0.01",
            "price_precision": "0.01",
        }
    )

    _service, _authorization, handoff, _repo = await _order_lifecycle_handoff_setup(
        candidate=candidate,
        trusted_submit_facts_repository=trusted_facts,
    )

    assert handoff.status == (
        RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    )
    assert handoff.blockers == []
    assert handoff.requested_qty == Decimal("0.07")
    assert handoff.entry_order_draft["requested_qty"] == "0.07"
    assert {draft["requested_qty"] for draft in handoff.protection_order_drafts} == {
        "0.07"
    }
    assert {draft["requested_qty"] for draft in handoff.order_model_drafts} == {
        "0.07"
    }
    assert any(
        warning.startswith("order_lifecycle_quantity_step_aligned:")
        and ":from=0.0752842:to=0.07:step=0.01" in warning
        for warning in handoff.warnings
    )
    assert handoff.metadata["market_quantity_step_alignment"] == {
        "source": "trusted_submit_fact_market_rule",
        "step_size": "0.01",
        "min_qty": "0.01",
        "aligned": True,
    }
    assert trusted_facts.lookups == [f"trusted-submit-facts-{handoff.execution_intent_id}"]


async def test_runtime_execution_order_lifecycle_handoff_blocks_when_protection_plan_blocked():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    protection_repo = _ProtectionPlanRecorder()
    handoff_repo = _OrderLifecycleHandoffRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        protection_plan_repository=protection_repo,
        order_lifecycle_handoff_repository=handoff_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeMutator(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    await service.record_protection_plan_for_intent(intent.id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    await service.apply_attempt_mutation_for_reservation(reservation.reservation_id)

    handoff = await service.record_order_lifecycle_handoff_draft_for_authorization(
        authorization.authorization_id
    )

    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert handoff.blockers == []
    assert handoff.stop_price_reference == Decimal("594")
    assert handoff.order_lifecycle_adapter_implemented is False
    assert handoff.order_created is False
    assert handoff.exchange_called is False
    assert handoff.owner_bounded_execution_called is False
    assert handoff.order_lifecycle_called is False


async def test_runtime_execution_order_lifecycle_handoff_repository_roundtrips_ready_draft():
    engine, session_maker = await _repo_engine(
        PGRuntimeExecutionOrderLifecycleHandoffDraftORM.__table__
    )
    repo = PgRuntimeExecutionOrderLifecycleHandoffRepository(session_maker=session_maker)
    try:
        candidate = _candidate(
            protection_preview=OrderCandidateProtectionPreview(
                requires_protection=True,
                stop_reference="explicit_stop_price",
                stop_price_reference=Decimal("594"),
                take_profit_references=[
                    {"id": "TP1", "price": "660", "position_ratio": "1"}
                ],
            )
        )
        draft = await _planning_service(
            active_positions=[],
            candidate=candidate,
        ).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        reservation_repo = _AttemptReservationRecorder()
        mutation_repo = _AttemptMutationRecorder()
        protection_repo = _ProtectionPlanRecorder()
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=_IntentRecorder(),
            submit_authorization_repository=_SubmitAuthorizationRecorder(),
            attempt_reservation_repository=reservation_repo,
            attempt_mutation_repository=mutation_repo,
            protection_plan_repository=protection_repo,
            order_lifecycle_handoff_repository=repo,
            final_gate_preview_service=_ready_final_gate_lookup(),
            runtime_service=_RuntimeMutator(),
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)
        await service.record_protection_plan_for_intent(intent.id)
        authorization = await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )
        reservation = await service.record_attempt_reservation_for_authorization(
            authorization.authorization_id
        )
        await service.apply_attempt_mutation_for_reservation(reservation.reservation_id)

        saved = await service.record_order_lifecycle_handoff_draft_for_authorization(
            authorization.authorization_id
        )
        saved_again = await service.record_order_lifecycle_handoff_draft_for_authorization(
            authorization.authorization_id
        )
        loaded = await repo.get(saved.handoff_draft_id)

        assert saved_again.handoff_draft_id == saved.handoff_draft_id
        assert saved_again.order_created is False
        assert saved_again.exchange_called is False
        assert saved_again.order_lifecycle_called is False
        assert loaded is not None
        assert loaded.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
        assert loaded.execution_intent_id == intent.id
        assert loaded.attempt_mutation_id.startswith("runtime-attempt-mutation-")
        assert loaded.protection_plan_id == f"runtime-protection-plan-{intent.id}"
        assert loaded.entry_order_draft["order_role"] == "ENTRY"
        assert loaded.protection_order_drafts[0]["order_role"] == "SL"
        assert loaded.order_model_drafts[0]["signal_id"] == "evaluation-1"
        assert loaded.order_model_drafts[0]["status"] == "CREATED"
        assert loaded.order_model_drafts[0]["persisted"] is False
        assert len(loaded.order_model_drafts[0]["local_order_draft_id"]) <= 64
        assert loaded.order_model_drafts[1]["parent_local_order_draft_id"] == (
            loaded.order_model_drafts[0]["local_order_draft_id"]
        )
        assert len(loaded.order_model_drafts[1]["local_order_draft_id"]) <= 64
        assert len(loaded.order_model_drafts[1]["parent_local_order_draft_id"]) <= 64
        assert loaded.stop_price_reference == Decimal("594")
        assert loaded.order_lifecycle_adapter_implemented is False
        assert loaded.order_created is False
        assert loaded.exchange_called is False
        assert loaded.owner_bounded_execution_called is False
        assert loaded.order_lifecycle_called is False
    finally:
        await engine.dispose()


async def test_runtime_execution_order_lifecycle_adapter_preview_inputs_ready_but_disabled():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    service, authorization, handoff, _handoff_repo = await _order_lifecycle_handoff_setup(
        candidate=candidate
    )

    preview = await service.order_lifecycle_adapter_preview_for_authorization(
        authorization.authorization_id
    )

    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert preview.status == (
        RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
    )
    assert preview.blockers == []
    assert preview.handoff_draft_id == handoff.handoff_draft_id
    assert preview.order_model_draft_count == 3
    assert preview.entry_order_model_draft_count == 1
    assert preview.protection_order_model_draft_count == 2
    assert preview.order_model_drafts[0]["order_role"] == "ENTRY"
    assert preview.order_model_drafts[0]["status"] == "CREATED"
    assert preview.order_model_drafts[0]["persisted"] is False
    assert preview.requires_local_order_registration is True
    assert preview.local_order_registration_enabled is False
    assert preview.order_lifecycle_adapter_implemented is False
    assert preview.local_order_registration_executed is False
    assert preview.execution_intent_status_changed is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_order_lifecycle_adapter_preview_inputs_ready_but_disabled_from_default_candidate():
    service, authorization, handoff, _handoff_repo = await _order_lifecycle_handoff_setup()

    preview = await service.order_lifecycle_adapter_preview_for_authorization(
        authorization.authorization_id
    )

    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert preview.status == (
        RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
    )
    assert preview.blockers == []
    assert preview.local_order_registration_enabled is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_order_registration_draft_preview_materializes_typed_drafts_without_registration():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    service, authorization, handoff, _handoff_repo = await _order_lifecycle_handoff_setup(
        candidate=candidate
    )

    preview = await service.order_registration_draft_preview_for_authorization(
        authorization.authorization_id
    )

    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert preview.status == (
        RuntimeExecutionOrderRegistrationDraftPreviewStatus
        .INPUTS_READY_REGISTRATION_DRAFT_ONLY
    )
    assert preview.blockers == []
    assert preview.registration_draft_count == 3
    assert preview.entry_registration_draft_count == 1
    assert preview.protection_registration_draft_count == 2
    entry = preview.local_order_registration_drafts[0]
    stop = preview.local_order_registration_drafts[1]
    tp1 = preview.local_order_registration_drafts[2]
    assert entry.order_role.value == "ENTRY"
    assert entry.reduce_only is False
    assert entry.parent_local_order_draft_id is None
    assert entry.persisted is False
    assert entry.not_order is True
    assert stop.order_role.value == "SL"
    assert stop.reduce_only is True
    assert stop.trigger_price == Decimal("594")
    assert stop.parent_local_order_draft_id == entry.local_order_draft_id
    assert tp1.order_role.value == "TP1"
    assert tp1.price == Decimal("660")
    assert preview.local_order_registration_enabled is False
    assert preview.order_lifecycle_adapter_implemented is False
    assert preview.order_objects_constructed is False
    assert preview.local_order_registration_executed is False
    assert preview.execution_intent_status_changed is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_runtime_execution_order_lifecycle_adapter_preview_rejects_execution_artifacts():
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    _service, _authorization, handoff, _handoff_repo = await _order_lifecycle_handoff_setup(
        candidate=candidate
    )

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionOrderLifecycleAdapterPreview(
            adapter_preview_id="bad-preview",
            handoff_draft_id=handoff.handoff_draft_id,
            preflight_id=handoff.preflight_id,
            authorization_id=handoff.authorization_id,
            execution_intent_id=handoff.execution_intent_id,
            runtime_instance_id=handoff.runtime_instance_id,
            source_type=handoff.source_type,
            source_id=handoff.source_id,
            semantic_ids=handoff.semantic_ids,
            status=(
                RuntimeExecutionOrderLifecycleAdapterPreviewStatus
                .INPUTS_READY_REGISTRATION_NOT_ENABLED
            ),
            symbol=handoff.symbol,
            side=handoff.side,
            entry_order_draft=handoff.entry_order_draft,
            protection_order_drafts=handoff.protection_order_drafts,
            order_model_drafts=[
                {**handoff.order_model_drafts[0], "exchange_order_id": "binance-123"}
            ],
            order_model_draft_count=1,
            entry_order_model_draft_count=1,
            protection_order_model_draft_count=0,
            created_at_ms=NOW_MS,
        )


async def test_runtime_execution_controlled_submit_result_defaults_to_adapter_disabled():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    result = await service.controlled_submit_for_authorization(authorization.authorization_id)

    assert result.status == RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_ENABLED
    assert result.preflight_status == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert result.final_gate_verdict.value == "PASS"
    assert "controlled_submit_adapter_disabled" in result.blockers
    assert result.submit_enabled is False
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.owner_bounded_execution_called is False
    assert result.order_lifecycle_called is False


async def test_runtime_execution_controlled_submit_result_repository_roundtrips_disabled_result():
    engine, session_maker = await _repo_engine(PGRuntimeExecutionControlledSubmitResultORM.__table__)
    repo = PgRuntimeExecutionControlledSubmitResultRepository(session_maker=session_maker)
    try:
        draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
        intent_repo = _IntentRecorder()
        auth_repo = _SubmitAuthorizationRecorder()
        service = RuntimeExecutionIntentAdapterService(
            draft_repository=_DraftLookup({draft.draft_id: draft}),
            intent_repository=intent_repo,
            submit_authorization_repository=auth_repo,
            final_gate_preview_service=_ready_final_gate_lookup(),
        )
        intent = await service.create_recorded_intent_from_draft(draft.draft_id)
        authorization = await service.create_submit_authorization_for_intent(
            intent.id,
            owner_confirmed_for_submit=True,
        )
        result = await service.controlled_submit_for_authorization(authorization.authorization_id)

        saved = await repo.create(result)
        loaded = await repo.get(saved.result_id)

        assert loaded is not None
        assert loaded.status == RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_ENABLED
        assert loaded.preflight_id == result.preflight_id
        assert loaded.preflight_status == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
        assert loaded.final_gate_verdict.value == "PASS"
        assert "controlled_submit_adapter_disabled" in loaded.blockers
        assert loaded.submit_enabled is False
        assert loaded.submit_executed is False
        assert loaded.order_created is False
        assert loaded.exchange_called is False
        assert loaded.owner_bounded_execution_called is False
        assert loaded.order_lifecycle_called is False
    finally:
        await engine.dispose()


async def test_runtime_execution_controlled_submit_result_is_recorded_for_audit():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    result_repo = _ControlledSubmitResultRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        controlled_submit_result_repository=result_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    result = await service.record_controlled_submit_result_for_authorization(
        authorization.authorization_id
    )

    assert result_repo.items == [result]
    assert result.status == RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_ENABLED
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_runtime_execution_controlled_submit_result_blocks_enabled_until_submit_adapter_implemented():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    result = await service.controlled_submit_for_authorization(
        authorization.authorization_id,
        submit_enabled=True,
    )

    assert result.status == (
        RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_IMPLEMENTED
    )
    assert "controlled_submit_adapter_not_implemented" in result.blockers
    assert result.submit_enabled is True
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.owner_bounded_execution_called is False
    assert result.order_lifecycle_called is False


async def test_runtime_execution_controlled_submit_result_blocks_when_plan_blocked():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    auth_repo.items = [authorization.model_copy(update={"source_id": "other-candidate"})]

    result = await service.controlled_submit_for_authorization(authorization.authorization_id)

    assert result.status == RuntimeExecutionControlledSubmitResultStatus.BLOCKED
    assert "controlled_submit_preflight_not_ready" in result.blockers
    assert "controlled_submit_plan_not_ready" in result.blockers
    assert "source_id_mismatch" in result.blockers
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False


async def test_runtime_execution_controlled_submit_result_blocks_final_gate_drift():
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    auth_repo = _SubmitAuthorizationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
        submit_authorization_repository=auth_repo,
        final_gate_preview_service=_blocked_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    result = await service.controlled_submit_for_authorization(authorization.authorization_id)

    assert result.status == RuntimeExecutionControlledSubmitResultStatus.BLOCKED
    assert result.preflight_status == RuntimeExecutionControlledSubmitPreflightStatus.BLOCKED
    assert result.final_gate_verdict.value == "BLOCK"
    assert "controlled_submit_preflight_not_ready" in result.blockers
    assert "runtime_final_gate_execution_check_not_passed" in result.blockers
    assert "active_position_capacity_exhausted" in result.blockers
    assert "controlled_submit_adapter_disabled" not in result.blockers
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False


def test_runtime_execution_intent_adapter_rejects_legacy_signal_projection():
    from src.domain.runtime_execution_intent_adapter import (
        RuntimeExecutionIntentCreationPreview,
    )

    draft = asyncio.run(
        _planning_service(active_positions=[]).intent_draft_for_order_candidate(
            order_candidate_id="candidate-1",
            owner_reviewed=True,
            owner_confirmed_for_intent=True,
        )
    )

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionIntentCreationPreview(
            adapter_preview_id="adapter-preview-bad",
            runtime_execution_intent_draft_id=draft.draft_id,
            source_id="candidate-1",
            source_payload={"signal_result": {"id": "legacy-fake"}},
            status=RuntimeExecutionIntentCreationPreviewStatus.READY_FOR_OWNER_GATED_CREATION,
            semantic_ids=draft.semantic_ids,
            symbol=draft.symbol,
            side=draft.side,
            candidate_order_type=draft.candidate_order_type,
            created_at_ms=NOW_MS,
        )


def test_runtime_execution_plan_rejects_execution_fields_in_metadata():
    preview = _planning_service(active_positions=[])._final_gate_preview_service.preview(
        runtime=_runtime(),
        candidate=_candidate(),
        active_positions_count=0,
        owner_reviewed=True,
    )

    from src.domain.runtime_execution_plan import RuntimeExecutionPlan

    with pytest.raises(ValueError, match="forbidden execution field"):
        RuntimeExecutionPlan(
            plan_id="runtime-plan-candidate-1",
            runtime_instance_id="runtime-1",
            order_candidate_id="candidate-1",
            signal_evaluation_id="evaluation-1",
            semantic_ids=_candidate().semantic_ids,
            status=RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT,
            symbol="BNB/USDT:USDT",
            side="long",
            candidate_order_type="market",
            final_gate_preview=preview,
            created_at_ms=NOW_MS,
            metadata={"execution_intent_id": "not-allowed"},
        )


async def test_trading_console_runtime_execution_plan_endpoint_is_get_only(monkeypatch):
    service = _planning_service(active_positions=[])
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_planning_service",
        service,
        raising=False,
    )

    plan = await runtime_execution_plan_for_order_candidate(
        "candidate-1",
        active_positions_count=None,
        owner_reviewed=True,
    )

    assert plan.status == RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
    assert plan.not_order is True
    assert plan.not_execution_intent is True
    assert plan.execution_intent_created is False
    assert plan.order_created is False


async def test_trading_console_runtime_execution_intent_draft_endpoint_is_get_only(monkeypatch):
    service = _planning_service(active_positions=[])
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_planning_service",
        service,
        raising=False,
    )

    draft = await runtime_execution_intent_draft_for_order_candidate(
        "candidate-1",
        active_positions_count=None,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.not_order is True
    assert draft.not_execution_intent is True
    assert draft.execution_intent_repository_write_enabled is False
    assert draft.execution_intent_created is False
    assert draft.order_created is False


async def test_trading_console_records_runtime_execution_intent_draft_without_execution(monkeypatch):
    class _DraftRepo:
        async def create(self, draft):
            return draft

    service = _planning_service(active_positions=[], intent_draft_repository=_DraftRepo())
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_planning_service",
        service,
        raising=False,
    )

    draft = await record_runtime_execution_intent_draft_for_order_candidate(
        "candidate-1",
        active_positions_count=None,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )

    assert draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
    assert draft.not_execution_intent is True
    assert draft.execution_intent_repository_write_enabled is False
    assert draft.execution_intent_created is False
    assert draft.order_created is False
    assert draft.exchange_called is False


async def test_trading_console_runtime_execution_intent_adapter_preview_endpoint_is_non_executing(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_intent_adapter_preview_for_draft(draft.draft_id)

    assert preview.status == RuntimeExecutionIntentCreationPreviewStatus.READY_FOR_OWNER_GATED_CREATION
    assert preview.source_type == RuntimeExecutionIntentSourceType.BRC_RUNTIME_ORDER_CANDIDATE
    assert preview.source_id == "candidate-1"
    assert preview.compatibility_signal_result_created is False
    assert preview.execution_intent_created is False
    assert preview.order_created is False
    assert preview.exchange_called is False


async def test_trading_console_records_source_native_runtime_execution_intent_without_submit(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    intent = await record_runtime_execution_intent_for_draft(draft.draft_id)

    assert intent.status == ExecutionIntentStatus.RECORDED
    assert intent.signal is None
    assert intent.signal_id is None
    assert intent.source_type == "brc_runtime_order_candidate"
    assert intent.source_payload["submit_authorized"] is False
    assert intent.order_id is None
    assert intent.exchange_order_id is None


async def test_trading_console_runtime_execution_submit_readiness_endpoint_is_non_submitting(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    readiness = await runtime_execution_submit_readiness_for_intent(intent.id)

    assert readiness.status == RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED
    assert readiness.submit_authorized is False
    assert readiness.order_created is False
    assert readiness.exchange_called is False
    assert readiness.owner_bounded_execution_called is False
    assert readiness.order_lifecycle_called is False


async def test_trading_console_runtime_execution_protection_plan_preview_endpoint_is_non_executing(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_repo = _IntentRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=intent_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_protection_plan_preview_for_intent(intent.id)

    assert preview.status == RuntimeExecutionProtectionPlanPreviewStatus.READY_FOR_SUBMIT_ADAPTER
    assert preview.blockers == []
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_trading_console_records_runtime_execution_protection_plan_without_order(
    monkeypatch,
):
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    protection_repo = _ProtectionPlanRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        protection_plan_repository=protection_repo,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    plan = await record_runtime_execution_protection_plan_for_intent(intent.id)

    assert protection_repo.items == [plan]
    assert plan.status == RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER
    assert plan.stop_price_reference == Decimal("594")
    assert plan.not_order is True
    assert plan.not_exchange_payload is True
    assert plan.execution_intent_status_changed is False
    assert plan.order_created is False
    assert plan.exchange_called is False
    assert plan.owner_bounded_execution_called is False
    assert plan.order_lifecycle_called is False


async def test_trading_console_records_runtime_execution_submit_authorization_without_submit(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    authorization = await record_runtime_execution_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )

    assert authorization.status == (
        RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
    )
    assert authorization.owner_submit_authorized is True
    assert authorization.submit_executed is False
    assert authorization.order_created is False
    assert authorization.exchange_called is False
    assert authorization.owner_bounded_execution_called is False
    assert authorization.order_lifecycle_called is False


async def test_trading_console_runtime_execution_controlled_submit_plan_endpoint_is_non_executing(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    plan = await runtime_execution_controlled_submit_plan_for_authorization(
        authorization.authorization_id
    )

    assert plan.status == RuntimeExecutionControlledSubmitPlanStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert plan.submit_executed is False
    assert plan.order_created is False
    assert plan.exchange_called is False
    assert plan.owner_bounded_execution_called is False
    assert plan.order_lifecycle_called is False


async def test_trading_console_runtime_execution_controlled_submit_preflight_endpoint_is_non_executing(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    final_gate = _FinalGatePreviewLookup(
        _planning_service(active_positions=[])._final_gate_preview_service.preview(
            runtime=_runtime(),
            candidate=_candidate(),
            active_positions_count=0,
            owner_reviewed=True,
        )
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=final_gate,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preflight = await runtime_execution_controlled_submit_preflight_for_authorization(
        authorization.authorization_id
    )

    assert preflight.status == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert preflight.submit_executed is False
    assert preflight.order_created is False
    assert preflight.exchange_called is False
    assert preflight.owner_bounded_execution_called is False
    assert preflight.order_lifecycle_called is False


async def test_trading_console_runtime_execution_submit_adapter_preview_endpoint_is_non_executing(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_submit_adapter_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == (
        RuntimeExecutionSubmitAdapterPreviewStatus
        .INPUTS_READY_ADAPTER_NOT_IMPLEMENTED
    )
    assert preview.blockers == []
    assert preview.submit_adapter_implemented is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_trading_console_runtime_execution_submit_rehearsal_endpoint_is_non_mutating(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await runtime_execution_submit_rehearsal_for_authorization(
            authorization.authorization_id
        )
    assert exc_info.value.status_code == 503
    assert (
        "runtime_execution_order_lifecycle_adapter_result_repository_unavailable"
        in str(exc_info.value.detail)
    )
    assert runtime_service.runtime.boundary.attempts_used == 0
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("0")
    assert runtime_service.events == []


async def test_trading_console_runtime_execution_attempt_reservation_preview_endpoint_is_non_mutating(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_attempt_reservation_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == RuntimeExecutionAttemptReservationPreviewStatus.READY_TO_RESERVE_ATTEMPT
    assert preview.attempts_remaining_before == 2
    assert preview.attempts_remaining_after == 1
    assert preview.budget_remaining_after == Decimal("14")
    assert preview.reservation_recorded is False
    assert preview.runtime_budget_mutated is False
    assert preview.attempt_consumed is False
    assert preview.order_created is False
    assert preview.exchange_called is False


async def test_trading_console_records_runtime_execution_attempt_reservation_without_mutation(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeLookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    reservation = await record_runtime_execution_attempt_reservation_for_authorization(
        authorization.authorization_id
    )

    assert reservation_repo.items == [reservation]
    assert reservation.status == RuntimeExecutionAttemptReservationStatus.PENDING_RUNTIME_MUTATION
    assert reservation.reservation_recorded is True
    assert reservation.runtime_mutation_pending is True
    assert reservation.runtime_budget_mutated is False
    assert reservation.attempt_consumed is False
    assert reservation.execution_intent_status_changed is False
    assert reservation.order_created is False
    assert reservation.exchange_called is False
    assert reservation.owner_bounded_execution_called is False
    assert reservation.order_lifecycle_called is False


async def test_trading_console_applies_runtime_execution_attempt_mutation_without_order(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    runtime_service = _RuntimeMutator()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=runtime_service,
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    mutation = await apply_runtime_execution_attempt_mutation_for_reservation(
        reservation.reservation_id
    )

    assert mutation_repo.items == [mutation]
    assert mutation.status == RuntimeExecutionAttemptMutationStatus.APPLIED
    assert mutation.runtime_budget_mutated is True
    assert mutation.attempt_consumed is True
    assert mutation.execution_intent_status_changed is False
    assert mutation.order_created is False
    assert mutation.exchange_called is False
    assert mutation.owner_bounded_execution_called is False
    assert mutation.order_lifecycle_called is False
    assert runtime_service.runtime.boundary.attempts_used == 1
    assert runtime_service.runtime.boundary.budget_reserved == Decimal("6")
    assert runtime_service.runtime.budget_remaining == Decimal("14")


async def test_trading_console_records_runtime_execution_order_lifecycle_handoff_without_order(
    monkeypatch,
):
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    protection_repo = _ProtectionPlanRecorder()
    handoff_repo = _OrderLifecycleHandoffRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        protection_plan_repository=protection_repo,
        order_lifecycle_handoff_repository=handoff_repo,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeMutator(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    await service.record_protection_plan_for_intent(intent.id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    await service.apply_attempt_mutation_for_reservation(reservation.reservation_id)
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    handoff = await record_runtime_execution_order_lifecycle_handoff_draft_for_authorization(
        authorization.authorization_id
    )

    assert handoff_repo.items == [handoff]
    assert handoff.status == RuntimeExecutionOrderLifecycleHandoffStatus.READY_FOR_ORDER_LIFECYCLE_ADAPTER
    assert handoff.entry_order_draft["order_role"] == "ENTRY"
    assert handoff.protection_order_drafts[0]["order_role"] == "SL"
    assert handoff.order_model_drafts[0]["status"] == "CREATED"
    assert handoff.order_model_drafts[0]["persisted"] is False
    assert handoff.order_lifecycle_adapter_implemented is False
    assert handoff.execution_intent_status_changed is False
    assert handoff.order_created is False
    assert handoff.exchange_called is False
    assert handoff.owner_bounded_execution_called is False
    assert handoff.order_lifecycle_called is False


async def test_trading_console_runtime_execution_order_lifecycle_adapter_preview_is_non_executing(
    monkeypatch,
):
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    service, authorization, _handoff, _handoff_repo = await _order_lifecycle_handoff_setup(
        candidate=candidate
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_order_lifecycle_adapter_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == (
        RuntimeExecutionOrderLifecycleAdapterPreviewStatus.INPUTS_READY_REGISTRATION_NOT_ENABLED
    )
    assert preview.local_order_registration_enabled is False
    assert preview.order_lifecycle_adapter_implemented is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_trading_console_runtime_execution_order_registration_draft_preview_is_non_executing(
    monkeypatch,
):
    candidate = _candidate(
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="explicit_stop_price",
            stop_price_reference=Decimal("594"),
            take_profit_references=[
                {"id": "TP1", "price": "660", "position_ratio": "1"}
            ],
        )
    )
    service, authorization, _handoff, _handoff_repo = await _order_lifecycle_handoff_setup(
        candidate=candidate
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    preview = await runtime_execution_order_registration_draft_preview_for_authorization(
        authorization.authorization_id
    )

    assert preview.status == (
        RuntimeExecutionOrderRegistrationDraftPreviewStatus
        .INPUTS_READY_REGISTRATION_DRAFT_ONLY
    )
    assert preview.registration_draft_count == 3
    assert preview.entry_registration_draft_count == 1
    assert preview.protection_registration_draft_count == 2
    assert preview.local_order_registration_enabled is False
    assert preview.order_lifecycle_adapter_implemented is False
    assert preview.order_objects_constructed is False
    assert preview.local_order_registration_executed is False
    assert preview.order_created is False
    assert preview.exchange_called is False
    assert preview.owner_bounded_execution_called is False
    assert preview.order_lifecycle_called is False


async def test_trading_console_runtime_execution_controlled_submit_endpoint_is_disabled_by_default(
    monkeypatch,
):
    draft = await _planning_service(active_positions=[]).intent_draft_for_order_candidate(
        order_candidate_id="candidate-1",
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        controlled_submit_result_repository=_ControlledSubmitResultRecorder(),
        final_gate_preview_service=_ready_final_gate_lookup(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    monkeypatch.setattr(
        api_module,
        "_runtime_execution_intent_adapter_service",
        service,
        raising=False,
    )

    result = await runtime_execution_controlled_submit_for_authorization(
        authorization.authorization_id
    )

    assert result.status == RuntimeExecutionControlledSubmitResultStatus.SUBMIT_ADAPTER_NOT_ENABLED
    assert result.preflight_status == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
    assert result.final_gate_verdict.value == "PASS"
    assert result.submit_executed is False
    assert result.order_created is False
    assert result.exchange_called is False
    assert result.owner_bounded_execution_called is False
    assert result.order_lifecycle_called is False


class _DraftLookup:
    def __init__(self, items):
        self.items = items

    async def get(self, draft_id: str):
        return self.items.get(draft_id)


class _RuntimeLookup:
    def __init__(self, runtime=None):
        self.runtime = runtime or _runtime()

    async def get_runtime(self, runtime_instance_id: str):
        assert runtime_instance_id == self.runtime.runtime_instance_id
        return self.runtime


class _RuntimeMutator(_RuntimeLookup):
    def __init__(self, runtime=None):
        super().__init__(runtime=runtime)
        self.events = []

    async def apply_runtime_attempt_mutation(
        self,
        *,
        previous_runtime,
        updated_runtime,
        mutation,
    ):
        assert previous_runtime.runtime_instance_id == self.runtime.runtime_instance_id
        assert updated_runtime.runtime_instance_id == self.runtime.runtime_instance_id
        self.runtime = updated_runtime
        self.events.append(
            type(
                "_Event",
                (),
                {
                    "metadata": {
                        "mutation_id": mutation.mutation_id,
                        "order_created": mutation.order_created,
                        "exchange_called": mutation.exchange_called,
                    }
                },
            )()
        )
        return self.runtime


class _FinalGatePreviewLookup:
    def __init__(self, preview):
        self.preview = preview
        self.calls = []

    async def preview_order_candidate(
        self,
        order_candidate_id: str,
        *,
        active_positions_count=None,
        owner_reviewed=False,
        metadata=None,
    ):
        self.calls.append(
            {
                "order_candidate_id": order_candidate_id,
                "active_positions_count": active_positions_count,
                "owner_reviewed": owner_reviewed,
            }
        )
        assert metadata is not None
        return self.preview


def _ready_final_gate_lookup() -> _FinalGatePreviewLookup:
    return _FinalGatePreviewLookup(
        _planning_service(active_positions=[])._final_gate_preview_service.preview(
            runtime=_runtime(),
            candidate=_candidate(),
            active_positions_count=0,
            owner_reviewed=True,
        )
    )


def _blocked_final_gate_lookup() -> _FinalGatePreviewLookup:
    return _FinalGatePreviewLookup(
        _planning_service(active_positions=[object()])._final_gate_preview_service.preview(
            runtime=_runtime(),
            candidate=_candidate(),
            active_positions_count=1,
            owner_reviewed=True,
        )
    )


async def _order_lifecycle_handoff_setup(
    *,
    candidate=None,
    trusted_submit_facts_repository=None,
):
    candidate = candidate or _candidate()
    draft = await _planning_service(
        active_positions=[],
        candidate=candidate,
    ).intent_draft_for_order_candidate(
        order_candidate_id=candidate.order_candidate_id,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    reservation_repo = _AttemptReservationRecorder()
    mutation_repo = _AttemptMutationRecorder()
    protection_repo = _ProtectionPlanRecorder()
    handoff_repo = _OrderLifecycleHandoffRecorder()
    service = RuntimeExecutionIntentAdapterService(
        draft_repository=_DraftLookup({draft.draft_id: draft}),
        intent_repository=_IntentRecorder(),
        submit_authorization_repository=_SubmitAuthorizationRecorder(),
        attempt_reservation_repository=reservation_repo,
        attempt_mutation_repository=mutation_repo,
        protection_plan_repository=protection_repo,
        order_lifecycle_handoff_repository=handoff_repo,
        trusted_submit_facts_repository=trusted_submit_facts_repository,
        final_gate_preview_service=_ready_final_gate_lookup(),
        runtime_service=_RuntimeMutator(),
    )
    intent = await service.create_recorded_intent_from_draft(draft.draft_id)
    await service.record_protection_plan_for_intent(intent.id)
    authorization = await service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    reservation = await service.record_attempt_reservation_for_authorization(
        authorization.authorization_id
    )
    await service.apply_attempt_mutation_for_reservation(reservation.reservation_id)
    handoff = await service.record_order_lifecycle_handoff_draft_for_authorization(
        authorization.authorization_id
    )
    return service, authorization, handoff, handoff_repo


class _IntentRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, intent_id: str):
        for item in self.items:
            if item.id == intent_id:
                return item
        return None

    async def save(self, intent):
        self.items.append(intent)


class _SubmitAuthorizationRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, authorization_id: str):
        for item in self.items:
            if item.authorization_id == authorization_id:
                return item
        return None

    async def create(self, authorization):
        self.items.append(authorization)
        return authorization


class _ControlledSubmitResultRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, result_id: str):
        for item in self.items:
            if item.result_id == result_id:
                return item
        return None

    async def create(self, result):
        self.items.append(result)
        return result


class _AttemptReservationRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, reservation_id: str):
        for item in self.items:
            if item.reservation_id == reservation_id:
                return item
        return None

    async def create(self, reservation):
        self.items.append(reservation)
        return reservation


class _AttemptMutationRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, mutation_id: str):
        for item in self.items:
            if item.mutation_id == mutation_id:
                return item
        return None

    async def create(self, mutation):
        self.items.append(mutation)
        return mutation


class _ProtectionPlanRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, protection_plan_id: str):
        for item in self.items:
            if item.protection_plan_id == protection_plan_id:
                return item
        return None

    async def create(self, plan):
        self.items.append(plan)
        return plan


class _OrderLifecycleHandoffRecorder:
    def __init__(self, items=None):
        self.items = list(items or [])

    async def get(self, handoff_draft_id: str):
        for item in self.items:
            if item.handoff_draft_id == handoff_draft_id:
                return item
        return None

    async def create(self, draft):
        self.items.append(draft)
        return draft


class _TrustedSubmitFactsLookup:
    def __init__(self, *, market_rule_metadata):
        self.market_rule_metadata = dict(market_rule_metadata)
        self.lookups = []

    async def get(self, trusted_submit_fact_snapshot_id: str):
        self.lookups.append(trusted_submit_fact_snapshot_id)
        return SimpleNamespace(
            market_rule_source=SimpleNamespace(
                metadata=dict(self.market_rule_metadata),
            ),
        )
