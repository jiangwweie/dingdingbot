"""PG repository for runtime attempt/budget outcome policy evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_attempt_outcome_policy import (
    RuntimeExecutionAttemptOutcomePolicy,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionAttemptOutcomePolicyORM


class PgRuntimeExecutionAttemptOutcomePolicyRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        policy: RuntimeExecutionAttemptOutcomePolicy,
    ) -> RuntimeExecutionAttemptOutcomePolicy:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(policy))
            await session.commit()
        return policy

    async def get(
        self,
        policy_id: str,
    ) -> RuntimeExecutionAttemptOutcomePolicy | None:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionAttemptOutcomePolicyORM, policy_id)
            if row is None:
                return None
            return RuntimeExecutionAttemptOutcomePolicy.model_validate(
                dict(row.payload_json or {})
            )

    @staticmethod
    def _to_orm(
        policy: RuntimeExecutionAttemptOutcomePolicy,
    ) -> PGRuntimeExecutionAttemptOutcomePolicyORM:
        return PGRuntimeExecutionAttemptOutcomePolicyORM(
            policy_id=policy.policy_id,
            reservation_id=policy.reservation_id,
            reservation_preview_id=policy.reservation_preview_id,
            mutation_id=policy.mutation_id,
            authorization_id=policy.authorization_id,
            execution_intent_id=policy.execution_intent_id,
            runtime_instance_id=policy.runtime_instance_id,
            source_id=policy.source_id,
            status=policy.status.value,
            outcome_kind=policy.outcome_kind.value,
            budget_action=policy.budget_action.value,
            symbol=policy.symbol,
            side=policy.side,
            any_fill=policy.any_fill,
            partial_fill=policy.partial_fill,
            submitted_to_exchange=policy.submitted_to_exchange,
            protection_creation_failed=policy.protection_creation_failed,
            attempt_should_be_consumed=policy.attempt_should_be_consumed,
            budget_release_allowed=policy.budget_release_allowed,
            budget_consumption_confirmed=policy.budget_consumption_confirmed,
            reserved_budget_should_remain_held=(
                policy.reserved_budget_should_remain_held
            ),
            requires_reconciliation_before_retry=(
                policy.requires_reconciliation_before_retry
            ),
            requires_owner_recovery_review=policy.requires_owner_recovery_review,
            requires_reduce_only_recovery_mode=(
                policy.requires_reduce_only_recovery_mode
            ),
            blocks_new_entries_until_resolved=(
                policy.blocks_new_entries_until_resolved
            ),
            budget_reservation_basis=policy.budget_reservation_basis,
            budget_reservation_amount=policy.budget_reservation_amount,
            budget_reserved_before=policy.budget_reserved_before,
            budget_reserved_after=policy.budget_reserved_after,
            runtime_state_mutated=policy.runtime_state_mutated,
            attempt_counter_mutated=policy.attempt_counter_mutated,
            budget_released=policy.budget_released,
            execution_intent_status_changed=(
                policy.execution_intent_status_changed
            ),
            order_created=policy.order_created,
            order_cancelled=policy.order_cancelled,
            position_closed=policy.position_closed,
            exchange_called=policy.exchange_called,
            exchange_order_submitted=policy.exchange_order_submitted,
            owner_bounded_execution_called=policy.owner_bounded_execution_called,
            order_lifecycle_called=policy.order_lifecycle_called,
            withdrawal_instruction_created=policy.withdrawal_instruction_created,
            transfer_instruction_created=policy.transfer_instruction_created,
            blockers_json=list(policy.blockers),
            warnings_json=list(policy.warnings),
            payload_json=policy.model_dump(mode="json"),
            created_at_ms=policy.created_at_ms,
        )
