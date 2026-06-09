"""PG repository for runtime submit authorization audit records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionSubmitAuthorizationORM


class PgRuntimeExecutionSubmitAuthorizationRepository:
    """Persist Owner submit authorization records for runtime intents."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        authorization: RuntimeExecutionSubmitAuthorization,
    ) -> RuntimeExecutionSubmitAuthorization:
        async with self._session_maker() as session:
            session.add(self._to_orm(authorization))
            await session.commit()
        return authorization

    async def get(
        self,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionSubmitAuthorization]:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionSubmitAuthorizationORM,
                authorization_id,
            )
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        authorization: RuntimeExecutionSubmitAuthorization,
    ) -> PGRuntimeExecutionSubmitAuthorizationORM:
        ids = authorization.semantic_ids
        return PGRuntimeExecutionSubmitAuthorizationORM(
            authorization_id=authorization.authorization_id,
            execution_intent_id=authorization.execution_intent_id,
            runtime_execution_intent_draft_id=authorization.runtime_execution_intent_draft_id,
            source_type=authorization.source_type,
            source_id=authorization.source_id,
            runtime_instance_id=ids.runtime_instance_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=authorization.status.value,
            symbol=authorization.symbol,
            side=authorization.side,
            owner_confirmed_for_submit=authorization.owner_confirmed_for_submit,
            owner_submit_authorized=authorization.owner_submit_authorized,
            submit_executed=authorization.submit_executed,
            order_created=authorization.order_created,
            exchange_called=authorization.exchange_called,
            owner_bounded_execution_called=authorization.owner_bounded_execution_called,
            order_lifecycle_called=authorization.order_lifecycle_called,
            created_at_ms=authorization.created_at_ms,
            metadata_json=dict(authorization.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionSubmitAuthorizationORM,
    ) -> RuntimeExecutionSubmitAuthorization:
        return RuntimeExecutionSubmitAuthorization(
            authorization_id=row.authorization_id,
            execution_intent_id=row.execution_intent_id,
            runtime_execution_intent_draft_id=row.runtime_execution_intent_draft_id,
            source_type=row.source_type,
            source_id=row.source_id,
            status=RuntimeExecutionSubmitAuthorizationStatus(row.status),
            semantic_ids=BrcSemanticIds(
                runtime_instance_id=row.runtime_instance_id,
                trial_binding_id=row.trial_binding_id,
                strategy_family_id=row.strategy_family_id,
                strategy_family_version_id=row.strategy_family_version_id,
                signal_evaluation_id=row.signal_evaluation_id,
                order_candidate_id=row.order_candidate_id,
            ),
            symbol=row.symbol,
            side=row.side,
            owner_confirmed_for_submit=row.owner_confirmed_for_submit,
            owner_submit_authorized=row.owner_submit_authorized,
            submit_executed=row.submit_executed,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
