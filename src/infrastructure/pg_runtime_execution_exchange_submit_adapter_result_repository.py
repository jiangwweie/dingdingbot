"""PG repository for runtime exchange-submit adapter result locks."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_exchange_submit_adapter_result import (
    RuntimeExecutionExchangeSubmitAdapterResult,
    RuntimeExecutionExchangeSubmitAdapterResultStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeSubmitAdapterResultORM,
)


class PgRuntimeExecutionExchangeSubmitAdapterResultRepository:
    """Persist runtime exchange-submit lock/result rows.

    The unique ``authorization_id`` constraint is the duplicate-submit lock for
    the exchange-submit boundary. A second call for the same authorization
    returns the existing row instead of attempting exchange submit again.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def acquire_exchange_submit_lock(
        self,
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> tuple[bool, RuntimeExecutionExchangeSubmitAdapterResult]:
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

    async def complete_exchange_submit_result(
        self,
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> RuntimeExecutionExchangeSubmitAdapterResult:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeSubmitAdapterResultORM,
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
    ) -> Optional[RuntimeExecutionExchangeSubmitAdapterResult]:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeSubmitAdapterResultORM,
                adapter_result_id,
            )
            return self._to_domain(row) if row else None

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionExchangeSubmitAdapterResult]:
        async with self._session_maker() as session:
            return await self._get_by_authorization_id_in_session(
                session,
                authorization_id,
            )

    async def _get_by_authorization_id_in_session(
        self,
        session: AsyncSession,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionExchangeSubmitAdapterResult]:
        result = await session.execute(
            select(PGRuntimeExecutionExchangeSubmitAdapterResultORM).where(
                PGRuntimeExecutionExchangeSubmitAdapterResultORM.authorization_id
                == authorization_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> PGRuntimeExecutionExchangeSubmitAdapterResultORM:
        ids = result.semantic_ids
        return PGRuntimeExecutionExchangeSubmitAdapterResultORM(
            adapter_result_id=result.adapter_result_id,
            enablement_decision_id=result.enablement_decision_id,
            gate_id=result.gate_id,
            submit_preview_id=result.submit_preview_id,
            binding_id=result.binding_id,
            local_registration_adapter_result_id=(
                result.local_registration_adapter_result_id
            ),
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
            local_order_ids_json=list(result.local_order_ids),
            entry_order_id=result.entry_order_id,
            protection_order_ids_json=list(result.protection_order_ids),
            submit_request_previews_json=list(result.submit_request_previews),
            submit_request_count=result.submit_request_count,
            entry_submit_request_count=result.entry_submit_request_count,
            protection_submit_request_count=result.protection_submit_request_count,
            blockers_json=list(result.blockers),
            warnings_json=list(result.warnings),
            order_lifecycle_submit_enabled=result.order_lifecycle_submit_enabled,
            exchange_submit_adapter_enabled=result.exchange_submit_adapter_enabled,
            exchange_submit_action_authorized=(
                result.exchange_submit_action_authorized
            ),
            exchange_submit_action_authorization_id=(
                result.exchange_submit_action_authorization_id
            ),
            duplicate_submit_lock_acquired=result.duplicate_submit_lock_acquired,
            exchange_submit_adapter_implemented=(
                result.exchange_submit_adapter_implemented
            ),
            order_lifecycle_submit_called=result.order_lifecycle_submit_called,
            execution_intent_status_changed=result.execution_intent_status_changed,
            exchange_order_submitted=result.exchange_order_submitted,
            exchange_called=result.exchange_called,
            owner_bounded_execution_called=result.owner_bounded_execution_called,
            withdrawal_or_transfer_created=result.withdrawal_or_transfer_created,
            created_at_ms=result.created_at_ms,
            metadata_json=dict(result.metadata),
        )

    @staticmethod
    def _update_orm(
        row: PGRuntimeExecutionExchangeSubmitAdapterResultORM,
        result: RuntimeExecutionExchangeSubmitAdapterResult,
    ) -> None:
        updated = (
            PgRuntimeExecutionExchangeSubmitAdapterResultRepository._to_orm(
                result
            )
        )
        for prop in (
            PGRuntimeExecutionExchangeSubmitAdapterResultORM
            .__mapper__
            .column_attrs
        ):
            setattr(row, prop.key, getattr(updated, prop.key))

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionExchangeSubmitAdapterResultORM,
    ) -> RuntimeExecutionExchangeSubmitAdapterResult:
        return RuntimeExecutionExchangeSubmitAdapterResult(
            adapter_result_id=row.adapter_result_id,
            enablement_decision_id=row.enablement_decision_id,
            gate_id=row.gate_id,
            submit_preview_id=row.submit_preview_id,
            binding_id=row.binding_id,
            local_registration_adapter_result_id=(
                row.local_registration_adapter_result_id
            ),
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
            status=RuntimeExecutionExchangeSubmitAdapterResultStatus(row.status),
            symbol=row.symbol,
            local_order_ids=list(row.local_order_ids_json or []),
            entry_order_id=row.entry_order_id,
            protection_order_ids=list(row.protection_order_ids_json or []),
            submit_request_previews=list(row.submit_request_previews_json or []),
            submit_request_count=row.submit_request_count,
            entry_submit_request_count=row.entry_submit_request_count,
            protection_submit_request_count=row.protection_submit_request_count,
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            order_lifecycle_submit_enabled=row.order_lifecycle_submit_enabled,
            exchange_submit_adapter_enabled=row.exchange_submit_adapter_enabled,
            exchange_submit_action_authorized=row.exchange_submit_action_authorized,
            exchange_submit_action_authorization_id=(
                row.exchange_submit_action_authorization_id
            ),
            duplicate_submit_lock_acquired=row.duplicate_submit_lock_acquired,
            exchange_submit_adapter_implemented=(
                row.exchange_submit_adapter_implemented
            ),
            order_lifecycle_submit_called=row.order_lifecycle_submit_called,
            execution_intent_status_changed=row.execution_intent_status_changed,
            exchange_order_submitted=row.exchange_order_submitted,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            withdrawal_or_transfer_created=row.withdrawal_or_transfer_created,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
