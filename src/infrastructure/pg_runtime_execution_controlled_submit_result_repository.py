"""PG repository for runtime controlled-submit boundary results."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflightStatus,
    RuntimeExecutionControlledSubmitResult,
    RuntimeExecutionControlledSubmitResultStatus,
)
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreviewVerdict
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionControlledSubmitResultORM


class PgRuntimeExecutionControlledSubmitResultRepository:
    """Persist disabled/blocked/not-implemented controlled-submit results."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        result: RuntimeExecutionControlledSubmitResult,
    ) -> RuntimeExecutionControlledSubmitResult:
        async with self._session_maker() as session:
            session.add(self._to_orm(result))
            await session.commit()
        return result

    async def get(
        self,
        result_id: str,
    ) -> Optional[RuntimeExecutionControlledSubmitResult]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionControlledSubmitResultORM, result_id)
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        result: RuntimeExecutionControlledSubmitResult,
    ) -> PGRuntimeExecutionControlledSubmitResultORM:
        return PGRuntimeExecutionControlledSubmitResultORM(
            result_id=result.result_id,
            plan_id=result.plan_id,
            preflight_id=result.preflight_id,
            authorization_id=result.authorization_id,
            execution_intent_id=result.execution_intent_id,
            preflight_status=result.preflight_status.value,
            final_gate_verdict=result.final_gate_verdict.value,
            status=result.status.value,
            blockers_json=list(result.blockers),
            warnings_json=list(result.warnings),
            submit_enabled=result.submit_enabled,
            submit_executed=result.submit_executed,
            order_created=result.order_created,
            exchange_called=result.exchange_called,
            owner_bounded_execution_called=result.owner_bounded_execution_called,
            order_lifecycle_called=result.order_lifecycle_called,
            created_at_ms=result.created_at_ms,
            metadata_json=dict(result.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionControlledSubmitResultORM,
    ) -> RuntimeExecutionControlledSubmitResult:
        return RuntimeExecutionControlledSubmitResult(
            result_id=row.result_id,
            plan_id=row.plan_id,
            preflight_id=row.preflight_id,
            authorization_id=row.authorization_id,
            execution_intent_id=row.execution_intent_id,
            preflight_status=RuntimeExecutionControlledSubmitPreflightStatus(
                row.preflight_status
            ),
            final_gate_verdict=RuntimeFinalGatePreviewVerdict(row.final_gate_verdict),
            status=RuntimeExecutionControlledSubmitResultStatus(row.status),
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            submit_enabled=row.submit_enabled,
            submit_executed=row.submit_executed,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
