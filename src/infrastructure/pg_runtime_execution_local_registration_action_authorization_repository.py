"""PG repository for runtime local-registration action authorization evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_local_registration_action_authorization import (
    RuntimeExecutionLocalRegistrationActionAuthorization,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionLocalRegistrationActionAuthorizationORM,
)


class PgRuntimeExecutionLocalRegistrationActionAuthorizationRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        authorization: RuntimeExecutionLocalRegistrationActionAuthorization,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(authorization))
            await session.commit()
        return authorization

    async def get(
        self,
        action_authorization_id: str,
    ) -> RuntimeExecutionLocalRegistrationActionAuthorization | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionLocalRegistrationActionAuthorizationORM,
                action_authorization_id,
            )
            if row is None:
                return None
            return RuntimeExecutionLocalRegistrationActionAuthorization.model_validate(
                dict(row.payload_json or {})
            )

    @staticmethod
    def _to_orm(
        authorization: RuntimeExecutionLocalRegistrationActionAuthorization,
    ) -> PGRuntimeExecutionLocalRegistrationActionAuthorizationORM:
        return PGRuntimeExecutionLocalRegistrationActionAuthorizationORM(
            action_authorization_id=authorization.action_authorization_id,
            authorization_id=authorization.authorization_id,
            execution_intent_id=authorization.execution_intent_id,
            runtime_instance_id=authorization.runtime_instance_id,
            source_type=authorization.source_type,
            source_id=authorization.source_id,
            status=authorization.status.value,
            symbol=authorization.symbol,
            side=authorization.side,
            trusted_submit_fact_snapshot_id=(
                authorization.trusted_submit_fact_snapshot_id
            ),
            submit_idempotency_policy_id=authorization.submit_idempotency_policy_id,
            attempt_outcome_policy_id=authorization.attempt_outcome_policy_id,
            protection_creation_failure_policy_id=(
                authorization.protection_creation_failure_policy_id
            ),
            owner_real_submit_authorization_id=(
                authorization.owner_real_submit_authorization_id
            ),
            order_lifecycle_adapter_enablement_id=(
                authorization.order_lifecycle_adapter_enablement_id
            ),
            local_order_registration_enablement_id=(
                authorization.local_order_registration_enablement_id
            ),
            deployment_readiness_evidence_id=(
                authorization.deployment_readiness_evidence_id
            ),
            registration_preview_id=authorization.registration_preview_id,
            adapter_preview_id=authorization.adapter_preview_id,
            handoff_draft_id=authorization.handoff_draft_id,
            entry_order_draft_id=authorization.entry_order_draft_id,
            local_order_draft_ids_json=list(authorization.local_order_draft_ids),
            protection_order_draft_ids_json=list(
                authorization.protection_order_draft_ids
            ),
            registration_draft_count=authorization.registration_draft_count,
            owner_confirmed_for_local_registration_action=(
                authorization.owner_confirmed_for_local_registration_action
            ),
            owner_operator_id=authorization.owner_operator_id,
            owner_confirmation_reference=authorization.owner_confirmation_reference,
            reason=authorization.reason,
            expires_at_ms=authorization.expires_at_ms,
            blockers_json=list(authorization.blockers),
            warnings_json=list(authorization.warnings),
            local_order_registration_executed=(
                authorization.local_order_registration_executed
            ),
            order_created=authorization.order_created,
            order_lifecycle_called=authorization.order_lifecycle_called,
            execution_intent_status_changed=(
                authorization.execution_intent_status_changed
            ),
            exchange_order_submitted=authorization.exchange_order_submitted,
            exchange_called=authorization.exchange_called,
            owner_bounded_execution_called=(
                authorization.owner_bounded_execution_called
            ),
            withdrawal_or_transfer_created=(
                authorization.withdrawal_or_transfer_created
            ),
            metadata_json=dict(authorization.metadata),
            payload_json=authorization.model_dump(mode="json"),
            created_at_ms=authorization.created_at_ms,
        )
