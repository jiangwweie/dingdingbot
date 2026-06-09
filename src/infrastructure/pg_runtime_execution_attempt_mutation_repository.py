"""PG repository for runtime attempt mutation audit records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutation,
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservationStatus,
)
from src.domain.strategy_runtime import StrategyRuntimeInstanceStatus
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionAttemptMutationORM


class PgRuntimeExecutionAttemptMutationRepository:
    """Persist runtime attempt/budget mutation audit facts."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        mutation: RuntimeExecutionAttemptMutation,
    ) -> RuntimeExecutionAttemptMutation:
        async with self._session_maker() as session:
            session.add(self._to_orm(mutation))
            await session.commit()
        return mutation

    async def get(
        self,
        mutation_id: str,
    ) -> Optional[RuntimeExecutionAttemptMutation]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionAttemptMutationORM, mutation_id)
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        mutation: RuntimeExecutionAttemptMutation,
    ) -> PGRuntimeExecutionAttemptMutationORM:
        ids = mutation.semantic_ids
        return PGRuntimeExecutionAttemptMutationORM(
            mutation_id=mutation.mutation_id,
            reservation_id=mutation.reservation_id,
            reservation_preview_id=mutation.reservation_preview_id,
            authorization_id=mutation.authorization_id,
            execution_intent_id=mutation.execution_intent_id,
            runtime_instance_id=mutation.runtime_instance_id,
            source_id=mutation.source_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=mutation.status.value,
            runtime_status_before=mutation.runtime_status_before.value,
            runtime_status_after=mutation.runtime_status_after.value,
            symbol=mutation.symbol,
            side=mutation.side,
            proposed_quantity=mutation.proposed_quantity,
            intended_notional=mutation.intended_notional,
            attempts_used_before=mutation.attempts_used_before,
            attempts_used_after=mutation.attempts_used_after,
            attempts_remaining_before=mutation.attempts_remaining_before,
            attempts_remaining_after=mutation.attempts_remaining_after,
            max_attempts=mutation.max_attempts,
            budget_reserved_before=mutation.budget_reserved_before,
            budget_reserved_after=mutation.budget_reserved_after,
            budget_remaining_before=mutation.budget_remaining_before,
            budget_remaining_after=mutation.budget_remaining_after,
            reservation_budget_remaining_after=mutation.reservation_budget_remaining_after,
            max_notional_per_attempt=mutation.max_notional_per_attempt,
            total_budget=mutation.total_budget,
            max_active_positions=mutation.max_active_positions,
            blockers_json=list(mutation.blockers),
            warnings_json=list(mutation.warnings),
            reservation_status=mutation.reservation_status.value,
            reservation_recorded=mutation.reservation_recorded,
            runtime_mutation_pending_before=mutation.runtime_mutation_pending_before,
            runtime_budget_mutated=mutation.runtime_budget_mutated,
            attempt_consumed=mutation.attempt_consumed,
            execution_intent_status_changed=mutation.execution_intent_status_changed,
            order_created=mutation.order_created,
            exchange_called=mutation.exchange_called,
            owner_bounded_execution_called=mutation.owner_bounded_execution_called,
            order_lifecycle_called=mutation.order_lifecycle_called,
            created_at_ms=mutation.created_at_ms,
            metadata_json=dict(mutation.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionAttemptMutationORM,
    ) -> RuntimeExecutionAttemptMutation:
        return RuntimeExecutionAttemptMutation(
            mutation_id=row.mutation_id,
            reservation_id=row.reservation_id,
            reservation_preview_id=row.reservation_preview_id,
            authorization_id=row.authorization_id,
            execution_intent_id=row.execution_intent_id,
            runtime_instance_id=row.runtime_instance_id,
            source_id=row.source_id,
            semantic_ids=BrcSemanticIds(
                runtime_instance_id=row.runtime_instance_id,
                trial_binding_id=row.trial_binding_id,
                strategy_family_id=row.strategy_family_id,
                strategy_family_version_id=row.strategy_family_version_id,
                signal_evaluation_id=row.signal_evaluation_id,
                order_candidate_id=row.order_candidate_id,
            ),
            status=RuntimeExecutionAttemptMutationStatus(row.status),
            runtime_status_before=StrategyRuntimeInstanceStatus(row.runtime_status_before),
            runtime_status_after=StrategyRuntimeInstanceStatus(row.runtime_status_after),
            symbol=row.symbol,
            side=row.side,
            proposed_quantity=row.proposed_quantity,
            intended_notional=row.intended_notional,
            attempts_used_before=row.attempts_used_before,
            attempts_used_after=row.attempts_used_after,
            attempts_remaining_before=row.attempts_remaining_before,
            attempts_remaining_after=row.attempts_remaining_after,
            max_attempts=row.max_attempts,
            budget_reserved_before=row.budget_reserved_before,
            budget_reserved_after=row.budget_reserved_after,
            budget_remaining_before=row.budget_remaining_before,
            budget_remaining_after=row.budget_remaining_after,
            reservation_budget_remaining_after=row.reservation_budget_remaining_after,
            max_notional_per_attempt=row.max_notional_per_attempt,
            total_budget=row.total_budget,
            max_active_positions=row.max_active_positions,
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            reservation_status=RuntimeExecutionAttemptReservationStatus(
                row.reservation_status
            ),
            reservation_recorded=row.reservation_recorded,
            runtime_mutation_pending_before=row.runtime_mutation_pending_before,
            runtime_budget_mutated=row.runtime_budget_mutated,
            attempt_consumed=row.attempt_consumed,
            execution_intent_status_changed=row.execution_intent_status_changed,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
