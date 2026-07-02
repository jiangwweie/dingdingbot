"""PG repository for runtime-native protection plan audit records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlan,
    RuntimeExecutionProtectionPlanStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionProtectionPlanORM


class PgRuntimeExecutionProtectionPlanRepository:
    """Persist runtime-native protection plan audit facts."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        plan: RuntimeExecutionProtectionPlan,
    ) -> RuntimeExecutionProtectionPlan:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(plan))
            await session.commit()
        return plan

    async def get(
        self,
        protection_plan_id: str,
    ) -> Optional[RuntimeExecutionProtectionPlan]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionProtectionPlanORM, protection_plan_id)
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        plan: RuntimeExecutionProtectionPlan,
    ) -> PGRuntimeExecutionProtectionPlanORM:
        ids = plan.semantic_ids
        return PGRuntimeExecutionProtectionPlanORM(
            protection_plan_id=plan.protection_plan_id,
            protection_plan_preview_id=plan.protection_plan_preview_id,
            execution_intent_id=plan.execution_intent_id,
            runtime_execution_intent_draft_id=plan.runtime_execution_intent_draft_id,
            source_type=plan.source_type,
            source_id=plan.source_id,
            runtime_instance_id=ids.runtime_instance_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=plan.status.value,
            symbol=plan.symbol,
            side=plan.side,
            proposed_quantity=plan.proposed_quantity,
            intended_notional=plan.intended_notional,
            entry_price_reference=plan.entry_price_reference,
            requires_protection=plan.requires_protection,
            stop_reference=plan.stop_reference,
            stop_price_reference=plan.stop_price_reference,
            take_profit_references_json=list(plan.take_profit_references),
            risk_preview_json=dict(plan.risk_preview),
            protection_preview_json=dict(plan.protection_preview),
            blockers_json=list(plan.blockers),
            warnings_json=list(plan.warnings),
            protection_plan_recorded=plan.protection_plan_recorded,
            not_order=plan.not_order,
            not_exchange_payload=plan.not_exchange_payload,
            execution_intent_status_changed=plan.execution_intent_status_changed,
            order_created=plan.order_created,
            exchange_called=plan.exchange_called,
            owner_bounded_execution_called=plan.owner_bounded_execution_called,
            order_lifecycle_called=plan.order_lifecycle_called,
            created_at_ms=plan.created_at_ms,
            metadata_json=dict(plan.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionProtectionPlanORM,
    ) -> RuntimeExecutionProtectionPlan:
        return RuntimeExecutionProtectionPlan(
            protection_plan_id=row.protection_plan_id,
            protection_plan_preview_id=row.protection_plan_preview_id,
            execution_intent_id=row.execution_intent_id,
            runtime_execution_intent_draft_id=row.runtime_execution_intent_draft_id,
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
            status=RuntimeExecutionProtectionPlanStatus(row.status),
            symbol=row.symbol,
            side=row.side,
            proposed_quantity=row.proposed_quantity,
            intended_notional=row.intended_notional,
            entry_price_reference=row.entry_price_reference,
            requires_protection=row.requires_protection,
            stop_reference=row.stop_reference,
            stop_price_reference=row.stop_price_reference,
            take_profit_references=list(row.take_profit_references_json or []),
            risk_preview=dict(row.risk_preview_json or {}),
            protection_preview=dict(row.protection_preview_json or {}),
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            protection_plan_recorded=row.protection_plan_recorded,
            not_order=row.not_order,
            not_exchange_payload=row.not_exchange_payload,
            execution_intent_status_changed=row.execution_intent_status_changed,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
