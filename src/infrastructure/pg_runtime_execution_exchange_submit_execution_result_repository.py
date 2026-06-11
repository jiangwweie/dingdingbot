"""PG repository for runtime exchange-submit execution result locks."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_exchange_submit_execution_result import (
    RuntimeExecutionExchangeSubmitExecutionResult,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionExchangeSubmitExecutionResultORM,
)


class PgRuntimeExecutionExchangeSubmitExecutionResultRepository:
    """Persist runtime exchange-submit execution lock/result rows.

    The unique ``authorization_id`` constraint is the durable replay key. Once
    a lock/result exists for an authorization, repeated calls return that row
    instead of reaching the exchange-submit adapter again.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def acquire_exchange_submit_execution_lock(
        self,
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> tuple[bool, RuntimeExecutionExchangeSubmitExecutionResult]:
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

    async def complete_exchange_submit_execution_result(
        self,
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeSubmitExecutionResultORM,
                result.execution_result_id,
            )
            if row is None:
                session.add(self._to_orm(result))
            else:
                self._update_orm(row, result)
            await session.commit()
        return result

    async def get(
        self,
        execution_result_id: str,
    ) -> Optional[RuntimeExecutionExchangeSubmitExecutionResult]:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionExchangeSubmitExecutionResultORM,
                execution_result_id,
            )
            return self._to_domain(row) if row else None

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionExchangeSubmitExecutionResult]:
        async with self._session_maker() as session:
            return await self._get_by_authorization_id_in_session(
                session,
                authorization_id,
            )

    async def _get_by_authorization_id_in_session(
        self,
        session: AsyncSession,
        authorization_id: str,
    ) -> Optional[RuntimeExecutionExchangeSubmitExecutionResult]:
        query = await session.execute(
            select(PGRuntimeExecutionExchangeSubmitExecutionResultORM).where(
                PGRuntimeExecutionExchangeSubmitExecutionResultORM.authorization_id
                == authorization_id
            )
        )
        row = query.scalar_one_or_none()
        return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> PGRuntimeExecutionExchangeSubmitExecutionResultORM:
        ids = result.semantic_ids
        return PGRuntimeExecutionExchangeSubmitExecutionResultORM(
            execution_result_id=result.execution_result_id,
            enablement_decision_id=result.enablement_decision_id,
            packet_preview_id=result.packet_preview_id,
            binding_id=result.binding_id,
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
            exchange_submit_action_authorization_id=(
                result.exchange_submit_action_authorization_id
            ),
            local_order_ids_json=list(result.local_order_ids),
            entry_order_id=result.entry_order_id,
            protection_order_ids_json=list(result.protection_order_ids),
            submitted_orders_json=[
                order.model_dump(mode="json")
                for order in result.submitted_orders
            ],
            submitted_local_order_ids_json=list(result.submitted_local_order_ids),
            submitted_exchange_order_ids_json=list(
                result.submitted_exchange_order_ids
            ),
            entry_exchange_order_id=result.entry_exchange_order_id,
            protection_exchange_order_ids_json=list(
                result.protection_exchange_order_ids
            ),
            failed_local_order_id=result.failed_local_order_id,
            failed_order_role=result.failed_order_role,
            failed_reason=result.failed_reason,
            exchange_submit_execution_enabled=(
                result.exchange_submit_execution_enabled
            ),
            execution_mode=result.execution_mode.value,
            exchange_call_count=result.exchange_call_count,
            order_lifecycle_submit_call_count=(
                result.order_lifecycle_submit_call_count
            ),
            blockers_json=list(result.blockers),
            warnings_json=list(result.warnings),
            real_exchange_submit_adapter_executed=(
                result.real_exchange_submit_adapter_executed
            ),
            exchange_order_submitted=result.exchange_order_submitted,
            exchange_called=result.exchange_called,
            order_lifecycle_submit_called=result.order_lifecycle_submit_called,
            execution_intent_status_changed=result.execution_intent_status_changed,
            owner_bounded_execution_called=result.owner_bounded_execution_called,
            withdrawal_or_transfer_created=result.withdrawal_or_transfer_created,
            created_at_ms=result.created_at_ms,
            metadata_json=dict(result.metadata),
            payload_json=result.model_dump(mode="json"),
        )

    @staticmethod
    def _update_orm(
        row: PGRuntimeExecutionExchangeSubmitExecutionResultORM,
        result: RuntimeExecutionExchangeSubmitExecutionResult,
    ) -> None:
        updated = (
            PgRuntimeExecutionExchangeSubmitExecutionResultRepository._to_orm(
                result
            )
        )
        for prop in (
            PGRuntimeExecutionExchangeSubmitExecutionResultORM
            .__mapper__
            .column_attrs
        ):
            setattr(row, prop.key, getattr(updated, prop.key))

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionExchangeSubmitExecutionResultORM,
    ) -> RuntimeExecutionExchangeSubmitExecutionResult:
        return RuntimeExecutionExchangeSubmitExecutionResult.model_validate(
            row.payload_json
        )
