"""PG repository for runtime OrderLifecycle adapter result locks."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_order_lifecycle_adapter_result import (
    RuntimeExecutionOrderLifecycleAdapterResult,
    RuntimeExecutionOrderLifecycleAdapterResultStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionOrderLifecycleAdapterResultORM,
)


class PgRuntimeExecutionOrderLifecycleAdapterResultRepository:
    """Persist runtime local-order registration lock/result rows.

    The unique ``authorization_id`` constraint is the duplicate-submit lock.
    A second call for the same authorization returns the existing row instead
    of registering local orders again.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def acquire_registration_lock(
        self,
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> tuple[bool, RuntimeExecutionOrderLifecycleAdapterResult]:
        async with self._session_maker() as session:
            session.add(self._to_orm(result))
            try:
                await session.commit()
                return True, result
            except IntegrityError:
                await session.rollback()
                existing = await self._get_by_authorization_id_in_session(
                    session,
                    result.authorization_id,
                )
                if existing is None:
                    raise
                return False, existing

    async def complete_registration(
        self,
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> RuntimeExecutionOrderLifecycleAdapterResult:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionOrderLifecycleAdapterResultORM,
                result.adapter_result_id,
            )
            if row is None:
                session.add(self._to_orm(result))
            else:
                self._update_orm(row, result)
            await session.commit()
        return result

    async def get(
        self,
        adapter_result_id: str,
    ) -> Optional[RuntimeExecutionOrderLifecycleAdapterResult]:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionOrderLifecycleAdapterResultORM,
                adapter_result_id,
            )
            return self._to_domain(row) if row else None

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionOrderLifecycleAdapterResult]:
        async with self._session_maker() as session:
            return await self._get_by_authorization_id_in_session(
                session,
                authorization_id,
            )

    async def _get_by_authorization_id_in_session(
        self,
        session: AsyncSession,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionOrderLifecycleAdapterResult]:
        result = await session.execute(
            select(PGRuntimeExecutionOrderLifecycleAdapterResultORM).where(
                PGRuntimeExecutionOrderLifecycleAdapterResultORM.authorization_id
                == authorization_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> PGRuntimeExecutionOrderLifecycleAdapterResultORM:
        ids = result.semantic_ids
        return PGRuntimeExecutionOrderLifecycleAdapterResultORM(
            adapter_result_id=result.adapter_result_id,
            registration_preview_id=result.registration_preview_id,
            adapter_preview_id=result.adapter_preview_id,
            handoff_draft_id=result.handoff_draft_id,
            preflight_id=result.preflight_id,
            authorization_id=result.authorization_id,
            execution_intent_id=result.execution_intent_id,
            runtime_instance_id=result.runtime_instance_id,
            source_type=result.source_type,
            source_id=result.source_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=result.status.value,
            symbol=result.symbol,
            side=result.side,
            local_order_ids_json=list(result.local_order_ids),
            entry_order_ids_json=list(result.entry_order_ids),
            protection_order_ids_json=list(result.protection_order_ids),
            registered_order_count=result.registered_order_count,
            blockers_json=list(result.blockers),
            warnings_json=list(result.warnings),
            order_lifecycle_adapter_enabled=result.order_lifecycle_adapter_enabled,
            local_order_registration_enabled=result.local_order_registration_enabled,
            duplicate_submit_lock_acquired=result.duplicate_submit_lock_acquired,
            order_objects_constructed=result.order_objects_constructed,
            local_order_registration_executed=result.local_order_registration_executed,
            execution_intent_status_changed=result.execution_intent_status_changed,
            exchange_order_submitted=result.exchange_order_submitted,
            exchange_called=result.exchange_called,
            owner_bounded_execution_called=result.owner_bounded_execution_called,
            order_lifecycle_called=result.order_lifecycle_called,
            withdrawal_or_transfer_created=result.withdrawal_or_transfer_created,
            created_at_ms=result.created_at_ms,
            metadata_json=dict(result.metadata),
        )

    @staticmethod
    def _update_orm(
        row: PGRuntimeExecutionOrderLifecycleAdapterResultORM,
        result: RuntimeExecutionOrderLifecycleAdapterResult,
    ) -> None:
        updated = PgRuntimeExecutionOrderLifecycleAdapterResultRepository._to_orm(
            result
        )
        for prop in PGRuntimeExecutionOrderLifecycleAdapterResultORM.__mapper__.column_attrs:
            setattr(row, prop.key, getattr(updated, prop.key))

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionOrderLifecycleAdapterResultORM,
    ) -> RuntimeExecutionOrderLifecycleAdapterResult:
        return RuntimeExecutionOrderLifecycleAdapterResult(
            adapter_result_id=row.adapter_result_id,
            registration_preview_id=row.registration_preview_id,
            adapter_preview_id=row.adapter_preview_id,
            handoff_draft_id=row.handoff_draft_id,
            preflight_id=row.preflight_id,
            authorization_id=row.authorization_id,
            execution_intent_id=row.execution_intent_id,
            runtime_instance_id=row.runtime_instance_id,
            source_type=row.source_type,
            source_id=row.source_id,
            semantic_ids=BrcSemanticIds(
                runtime_instance_id=row.runtime_instance_id,
                trial_binding_id=row.trial_binding_id,
                strategy_family_id=row.strategy_family_id,
                strategy_family_version_id=row.strategy_family_version_id,
                signal_evaluation_id=row.signal_evaluation_id,
                order_candidate_id=row.order_candidate_id,
            ),
            status=RuntimeExecutionOrderLifecycleAdapterResultStatus(row.status),
            symbol=row.symbol,
            side=row.side,
            local_order_ids=list(row.local_order_ids_json or []),
            entry_order_ids=list(row.entry_order_ids_json or []),
            protection_order_ids=list(row.protection_order_ids_json or []),
            registered_order_count=row.registered_order_count,
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            order_lifecycle_adapter_enabled=row.order_lifecycle_adapter_enabled,
            local_order_registration_enabled=row.local_order_registration_enabled,
            duplicate_submit_lock_acquired=row.duplicate_submit_lock_acquired,
            order_objects_constructed=row.order_objects_constructed,
            local_order_registration_executed=row.local_order_registration_executed,
            execution_intent_status_changed=row.execution_intent_status_changed,
            exchange_order_submitted=row.exchange_order_submitted,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            withdrawal_or_transfer_created=row.withdrawal_or_transfer_created,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
