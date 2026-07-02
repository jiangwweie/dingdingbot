"""PG repository for Owner-reviewed exchange-submit recovery resolution evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_exchange_submit_recovery_resolution import (
    RuntimeExecutionExchangeSubmitRecoveryResolution,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM,
)


class PgRuntimeExecutionExchangeSubmitRecoveryResolutionRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        resolution: RuntimeExecutionExchangeSubmitRecoveryResolution,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(resolution))
            await session.commit()
        return resolution

    async def get(
        self,
        resolution_id: str,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM,
                resolution_id,
            )
            return self._to_domain(row) if row else None

    async def get_by_recovery_task_id(
        self,
        recovery_task_id: str,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution | None:
        async with self._session_maker() as session:
            query = await session.execute(
                select(
                    PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM
                ).where(
                    PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM
                    .recovery_task_id
                    == recovery_task_id
                )
            )
            row = query.scalar_one_or_none()
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        resolution: RuntimeExecutionExchangeSubmitRecoveryResolution,
    ) -> PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM:
        return PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM(
            resolution_id=resolution.resolution_id,
            recovery_task_id=resolution.recovery_task_id,
            recovery_type=resolution.recovery_type,
            status=resolution.status.value,
            authorization_id=resolution.authorization_id,
            execution_result_id=resolution.execution_result_id,
            execution_intent_id=resolution.execution_intent_id,
            runtime_instance_id=resolution.runtime_instance_id,
            source_type=resolution.source_type,
            source_id=resolution.source_id,
            symbol=resolution.symbol,
            related_order_id=resolution.related_order_id,
            related_exchange_order_id=resolution.related_exchange_order_id,
            entry_order_id=resolution.entry_order_id,
            entry_exchange_order_id=resolution.entry_exchange_order_id,
            failed_protection_order_id=resolution.failed_protection_order_id,
            failed_reason=resolution.failed_reason,
            owner_operator_id=resolution.owner_operator_id,
            owner_confirmation_reference=(
                resolution.owner_confirmation_reference
            ),
            reason=resolution.reason,
            reconciliation_evidence_id=resolution.reconciliation_evidence_id,
            owner_confirmed_recovery_resolved=(
                resolution.owner_confirmed_recovery_resolved
            ),
            owner_confirmed_reconciliation_reviewed=(
                resolution.owner_confirmed_reconciliation_reviewed
            ),
            owner_confirmed_no_unprotected_position=(
                resolution.owner_confirmed_no_unprotected_position
            ),
            owner_confirmed_no_unresolved_exchange_order=(
                resolution.owner_confirmed_no_unresolved_exchange_order
            ),
            owner_confirmed_budget_reconciled_or_held=(
                resolution.owner_confirmed_budget_reconciled_or_held
            ),
            owner_confirmed_attempt_consumed_or_accounted=(
                resolution.owner_confirmed_attempt_consumed_or_accounted
            ),
            recovery_task_marked_resolved=(
                resolution.recovery_task_marked_resolved
            ),
            blockers_json=list(resolution.blockers),
            warnings_json=list(resolution.warnings),
            order_lifecycle_submit_called=(
                resolution.order_lifecycle_submit_called
            ),
            execution_intent_status_changed=(
                resolution.execution_intent_status_changed
            ),
            exchange_order_submitted=resolution.exchange_order_submitted,
            exchange_called=resolution.exchange_called,
            owner_bounded_execution_called=(
                resolution.owner_bounded_execution_called
            ),
            withdrawal_or_transfer_created=(
                resolution.withdrawal_or_transfer_created
            ),
            created_at_ms=resolution.created_at_ms,
            metadata_json=dict(resolution.metadata),
            payload_json=resolution.model_dump(mode="json"),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionExchangeSubmitRecoveryResolutionORM,
    ) -> RuntimeExecutionExchangeSubmitRecoveryResolution:
        return RuntimeExecutionExchangeSubmitRecoveryResolution.model_validate(
            row.payload_json
        )
