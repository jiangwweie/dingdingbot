"""PG repository for runtime submit outcome review evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_submit_outcome_review import (
    RuntimeExecutionSubmitOutcomeReview,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionSubmitOutcomeReviewORM


class PgRuntimeExecutionSubmitOutcomeReviewRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        review: RuntimeExecutionSubmitOutcomeReview,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(review))
            await session.commit()
        return review

    async def get(
        self,
        review_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionSubmitOutcomeReviewORM,
                review_id,
            )
            return self._to_domain(row) if row else None

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitOutcomeReview | None:
        async with self._session_maker() as session:
            query = await session.execute(
                select(PGRuntimeExecutionSubmitOutcomeReviewORM).where(
                    PGRuntimeExecutionSubmitOutcomeReviewORM.authorization_id
                    == authorization_id
                )
            )
            row = query.scalar_one_or_none()
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        review: RuntimeExecutionSubmitOutcomeReview,
    ) -> PGRuntimeExecutionSubmitOutcomeReviewORM:
        ids = review.semantic_ids
        return PGRuntimeExecutionSubmitOutcomeReviewORM(
            review_id=review.review_id,
            exchange_submit_execution_result_id=(
                review.exchange_submit_execution_result_id
            ),
            authorization_id=review.authorization_id,
            execution_intent_id=review.execution_intent_id,
            runtime_instance_id=review.runtime_instance_id,
            source_type=review.source_type,
            source_id=review.source_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            symbol=review.symbol,
            status=review.status.value,
            observed_outcome=review.observed_outcome.value,
            recommended_attempt_outcome_kind=(
                review.recommended_attempt_outcome_kind.value
                if review.recommended_attempt_outcome_kind is not None
                else None
            ),
            attempt_outcome_policy_ready=review.attempt_outcome_policy_ready,
            entry_order_id=review.entry_order_id,
            entry_order_status=review.entry_order_status,
            entry_requested_qty=review.entry_requested_qty,
            entry_filled_qty=review.entry_filled_qty,
            protection_order_ids_json=list(review.protection_order_ids),
            missing_order_ids_json=list(review.missing_order_ids),
            submitted_to_exchange=review.submitted_to_exchange,
            any_fill=review.any_fill,
            partial_fill=review.partial_fill,
            full_fill=review.full_fill,
            no_fill=review.no_fill,
            protection_creation_failed=review.protection_creation_failed,
            requires_reconciliation_before_retry=(
                review.requires_reconciliation_before_retry
            ),
            blocks_attempt_outcome_policy_until_resolved=(
                review.blocks_attempt_outcome_policy_until_resolved
            ),
            runtime_state_mutated=review.runtime_state_mutated,
            attempt_counter_mutated=review.attempt_counter_mutated,
            budget_released=review.budget_released,
            budget_consumed=review.budget_consumed,
            execution_intent_status_changed=(
                review.execution_intent_status_changed
            ),
            order_created=review.order_created,
            order_cancelled=review.order_cancelled,
            position_closed=review.position_closed,
            exchange_called=review.exchange_called,
            exchange_order_submitted=review.exchange_order_submitted,
            order_lifecycle_called=review.order_lifecycle_called,
            owner_bounded_execution_called=review.owner_bounded_execution_called,
            withdrawal_instruction_created=review.withdrawal_instruction_created,
            transfer_instruction_created=review.transfer_instruction_created,
            blockers_json=list(review.blockers),
            warnings_json=list(review.warnings),
            payload_json=review.model_dump(mode="json"),
            created_at_ms=review.created_at_ms,
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionSubmitOutcomeReviewORM,
    ) -> RuntimeExecutionSubmitOutcomeReview:
        return RuntimeExecutionSubmitOutcomeReview.model_validate(
            dict(row.payload_json or {})
        )
