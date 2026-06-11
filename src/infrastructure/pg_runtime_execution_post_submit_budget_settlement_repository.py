"""PG repository for post-submit runtime budget settlement records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_post_submit_budget_settlement import (
    RuntimeExecutionPostSubmitBudgetSettlement,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionPostSubmitBudgetSettlementORM,
)


class PgRuntimeExecutionPostSubmitBudgetSettlementRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        settlement: RuntimeExecutionPostSubmitBudgetSettlement,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(settlement))
            await session.commit()
        return settlement

    async def get(
        self,
        settlement_id: str,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionPostSubmitBudgetSettlementORM,
                settlement_id,
            )
            return self._to_domain(row) if row is not None else None

    async def get_by_authorization_id(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement | None:
        async with self._session_maker() as session:
            query = await session.execute(
                select(PGRuntimeExecutionPostSubmitBudgetSettlementORM)
                .where(
                    PGRuntimeExecutionPostSubmitBudgetSettlementORM
                    .authorization_id
                    == authorization_id
                )
                .order_by(
                    PGRuntimeExecutionPostSubmitBudgetSettlementORM
                    .created_at_ms
                    .desc()
                )
                .limit(1)
            )
            row = query.scalar_one_or_none()
            return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_orm(
        settlement: RuntimeExecutionPostSubmitBudgetSettlement,
    ) -> PGRuntimeExecutionPostSubmitBudgetSettlementORM:
        return PGRuntimeExecutionPostSubmitBudgetSettlementORM(
            settlement_id=settlement.settlement_id,
            accounting_id=settlement.accounting_id,
            authorization_id=settlement.authorization_id,
            execution_intent_id=settlement.execution_intent_id,
            runtime_instance_id=settlement.runtime_instance_id,
            reservation_id=settlement.reservation_id,
            mutation_id=settlement.mutation_id,
            attempt_outcome_policy_id=settlement.attempt_outcome_policy_id,
            status=settlement.status.value,
            runtime_status_before=settlement.runtime_status_before.value,
            runtime_status_after=settlement.runtime_status_after.value,
            budget_action=(
                settlement.budget_action.value
                if settlement.budget_action is not None
                else None
            ),
            outcome_kind=settlement.outcome_kind,
            budget_reservation_amount=settlement.budget_reservation_amount,
            budget_release_amount=settlement.budget_release_amount,
            budget_reserved_before=settlement.budget_reserved_before,
            budget_reserved_after=settlement.budget_reserved_after,
            budget_remaining_before=settlement.budget_remaining_before,
            budget_remaining_after=settlement.budget_remaining_after,
            attempts_used_before=settlement.attempts_used_before,
            attempts_used_after=settlement.attempts_used_after,
            attempts_remaining_before=settlement.attempts_remaining_before,
            attempts_remaining_after=settlement.attempts_remaining_after,
            blockers_json=list(settlement.blockers),
            warnings_json=list(settlement.warnings),
            runtime_state_mutated=settlement.runtime_state_mutated,
            runtime_budget_mutated=settlement.runtime_budget_mutated,
            attempt_counter_mutated=settlement.attempt_counter_mutated,
            attempt_already_consumed=settlement.attempt_already_consumed,
            budget_released=settlement.budget_released,
            budget_consumption_recorded=settlement.budget_consumption_recorded,
            reserved_budget_remains_held=settlement.reserved_budget_remains_held,
            requires_reconciliation_before_retry=(
                settlement.requires_reconciliation_before_retry
            ),
            blocks_new_entries_until_resolved=(
                settlement.blocks_new_entries_until_resolved
            ),
            not_execution_authority=settlement.not_execution_authority,
            execution_intent_status_changed=(
                settlement.execution_intent_status_changed
            ),
            order_created=settlement.order_created,
            order_cancelled=settlement.order_cancelled,
            position_closed=settlement.position_closed,
            exchange_called=settlement.exchange_called,
            exchange_order_submitted=settlement.exchange_order_submitted,
            order_lifecycle_called=settlement.order_lifecycle_called,
            owner_bounded_execution_called=settlement.owner_bounded_execution_called,
            withdrawal_instruction_created=(
                settlement.withdrawal_instruction_created
            ),
            transfer_instruction_created=settlement.transfer_instruction_created,
            payload_json=settlement.model_dump(mode="json"),
            metadata_json=dict(settlement.metadata),
            created_at_ms=settlement.created_at_ms,
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionPostSubmitBudgetSettlementORM,
    ) -> RuntimeExecutionPostSubmitBudgetSettlement:
        return RuntimeExecutionPostSubmitBudgetSettlement.model_validate(
            dict(row.payload_json or {})
        )
