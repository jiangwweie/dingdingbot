"""PG repository for runtime attempt reservation audit records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_attempt_reservation import (
    RuntimeExecutionAttemptReservation,
    RuntimeExecutionAttemptReservationStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionAttemptReservationORM


class PgRuntimeExecutionAttemptReservationRepository:
    """Persist pending runtime attempt/budget reservation audit facts."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        reservation: RuntimeExecutionAttemptReservation,
    ) -> RuntimeExecutionAttemptReservation:
        async with self._session_maker() as session:
            session.add(self._to_orm(reservation))
            await session.commit()
        return reservation

    async def get(
        self,
        reservation_id: str,
    ) -> Optional[RuntimeExecutionAttemptReservation]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionAttemptReservationORM, reservation_id)
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        reservation: RuntimeExecutionAttemptReservation,
    ) -> PGRuntimeExecutionAttemptReservationORM:
        ids = reservation.semantic_ids
        return PGRuntimeExecutionAttemptReservationORM(
            reservation_id=reservation.reservation_id,
            reservation_preview_id=reservation.reservation_preview_id,
            preflight_id=reservation.preflight_id,
            authorization_id=reservation.authorization_id,
            execution_intent_id=reservation.execution_intent_id,
            runtime_instance_id=reservation.runtime_instance_id,
            source_id=reservation.source_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=reservation.status.value,
            symbol=reservation.symbol,
            side=reservation.side,
            proposed_quantity=reservation.proposed_quantity,
            intended_notional=reservation.intended_notional,
            attempts_used_before=reservation.attempts_used_before,
            attempts_remaining_before=reservation.attempts_remaining_before,
            attempts_remaining_after=reservation.attempts_remaining_after,
            max_attempts=reservation.max_attempts,
            budget_remaining_before=reservation.budget_remaining_before,
            budget_remaining_after=reservation.budget_remaining_after,
            max_notional_per_attempt=reservation.max_notional_per_attempt,
            total_budget=reservation.total_budget,
            max_active_positions=reservation.max_active_positions,
            blockers_json=list(reservation.blockers),
            warnings_json=list(reservation.warnings),
            reservation_recorded=reservation.reservation_recorded,
            runtime_mutation_pending=reservation.runtime_mutation_pending,
            runtime_budget_mutated=reservation.runtime_budget_mutated,
            attempt_consumed=reservation.attempt_consumed,
            execution_intent_status_changed=reservation.execution_intent_status_changed,
            order_created=reservation.order_created,
            exchange_called=reservation.exchange_called,
            owner_bounded_execution_called=reservation.owner_bounded_execution_called,
            order_lifecycle_called=reservation.order_lifecycle_called,
            created_at_ms=reservation.created_at_ms,
            metadata_json=dict(reservation.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionAttemptReservationORM,
    ) -> RuntimeExecutionAttemptReservation:
        return RuntimeExecutionAttemptReservation(
            reservation_id=row.reservation_id,
            reservation_preview_id=row.reservation_preview_id,
            preflight_id=row.preflight_id,
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
            status=RuntimeExecutionAttemptReservationStatus(row.status),
            symbol=row.symbol,
            side=row.side,
            proposed_quantity=row.proposed_quantity,
            intended_notional=row.intended_notional,
            attempts_used_before=row.attempts_used_before,
            attempts_remaining_before=row.attempts_remaining_before,
            attempts_remaining_after=row.attempts_remaining_after,
            max_attempts=row.max_attempts,
            budget_remaining_before=row.budget_remaining_before,
            budget_remaining_after=row.budget_remaining_after,
            max_notional_per_attempt=row.max_notional_per_attempt,
            total_budget=row.total_budget,
            max_active_positions=row.max_active_positions,
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            reservation_recorded=row.reservation_recorded,
            runtime_mutation_pending=row.runtime_mutation_pending,
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
