"""PG repository for runtime OrderLifecycle handoff draft audit records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.models import Direction, OrderRole, OrderType
from src.domain.runtime_execution_attempt_mutation import (
    RuntimeExecutionAttemptMutationStatus,
)
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_order_lifecycle_handoff import (
    RuntimeExecutionOrderLifecycleHandoffDraft,
    RuntimeExecutionOrderLifecycleHandoffStatus,
)
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionOrderLifecycleHandoffDraftORM


class PgRuntimeExecutionOrderLifecycleHandoffRepository:
    """Persist runtime-native OrderLifecycle handoff draft facts.

    These rows are adapter input drafts only. They do not create orders or call
    OrderLifecycle.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        draft: RuntimeExecutionOrderLifecycleHandoffDraft,
    ) -> RuntimeExecutionOrderLifecycleHandoffDraft:
        async with self._session_maker() as session:
            session.add(self._to_orm(draft))
            await session.commit()
        return draft

    async def get(
        self,
        handoff_draft_id: str,
    ) -> Optional[RuntimeExecutionOrderLifecycleHandoffDraft]:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionOrderLifecycleHandoffDraftORM,
                handoff_draft_id,
            )
            return self._to_domain(row) if row else None

    @staticmethod
    def _to_orm(
        draft: RuntimeExecutionOrderLifecycleHandoffDraft,
    ) -> PGRuntimeExecutionOrderLifecycleHandoffDraftORM:
        ids = draft.semantic_ids
        return PGRuntimeExecutionOrderLifecycleHandoffDraftORM(
            handoff_draft_id=draft.handoff_draft_id,
            preflight_id=draft.preflight_id,
            authorization_id=draft.authorization_id,
            execution_intent_id=draft.execution_intent_id,
            attempt_mutation_id=draft.attempt_mutation_id,
            protection_plan_id=draft.protection_plan_id,
            runtime_instance_id=draft.runtime_instance_id,
            source_type=draft.source_type,
            source_id=draft.source_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            signal_evaluation_id=ids.signal_evaluation_id,
            order_candidate_id=ids.order_candidate_id,
            status=draft.status.value,
            symbol=draft.symbol,
            side=draft.side,
            direction=draft.direction.value,
            entry_order_type=draft.entry_order_type.value,
            entry_order_role=draft.entry_order_role.value,
            requested_qty=draft.requested_qty,
            intended_notional=draft.intended_notional,
            entry_price_reference=draft.entry_price_reference,
            stop_price_reference=draft.stop_price_reference,
            take_profit_references_json=list(draft.take_profit_references),
            entry_order_draft_json=dict(draft.entry_order_draft),
            protection_order_drafts_json=list(draft.protection_order_drafts),
            order_model_drafts_json=list(draft.order_model_drafts),
            blockers_json=list(draft.blockers),
            warnings_json=list(draft.warnings),
            preflight_status=draft.preflight_status.value,
            attempt_mutation_status=draft.attempt_mutation_status.value,
            protection_plan_status=draft.protection_plan_status.value,
            order_lifecycle_method=draft.order_lifecycle_method,
            handoff_draft_recorded=draft.handoff_draft_recorded,
            requires_order_lifecycle_adapter=draft.requires_order_lifecycle_adapter,
            order_lifecycle_adapter_implemented=draft.order_lifecycle_adapter_implemented,
            execution_intent_status_changed=draft.execution_intent_status_changed,
            order_created=draft.order_created,
            exchange_called=draft.exchange_called,
            owner_bounded_execution_called=draft.owner_bounded_execution_called,
            order_lifecycle_called=draft.order_lifecycle_called,
            created_at_ms=draft.created_at_ms,
            metadata_json=dict(draft.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionOrderLifecycleHandoffDraftORM,
    ) -> RuntimeExecutionOrderLifecycleHandoffDraft:
        return RuntimeExecutionOrderLifecycleHandoffDraft(
            handoff_draft_id=row.handoff_draft_id,
            preflight_id=row.preflight_id,
            authorization_id=row.authorization_id,
            execution_intent_id=row.execution_intent_id,
            attempt_mutation_id=row.attempt_mutation_id,
            protection_plan_id=row.protection_plan_id,
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
            status=RuntimeExecutionOrderLifecycleHandoffStatus(row.status),
            symbol=row.symbol,
            side=row.side,
            direction=Direction(row.direction),
            entry_order_type=OrderType(row.entry_order_type),
            entry_order_role=OrderRole(row.entry_order_role),
            requested_qty=row.requested_qty,
            intended_notional=row.intended_notional,
            entry_price_reference=row.entry_price_reference,
            stop_price_reference=row.stop_price_reference,
            take_profit_references=list(row.take_profit_references_json or []),
            entry_order_draft=dict(row.entry_order_draft_json or {}),
            protection_order_drafts=list(row.protection_order_drafts_json or []),
            order_model_drafts=list(row.order_model_drafts_json or []),
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            preflight_status=RuntimeExecutionControlledSubmitPreflightStatus(
                row.preflight_status
            ),
            attempt_mutation_status=RuntimeExecutionAttemptMutationStatus(
                row.attempt_mutation_status
            ),
            protection_plan_status=RuntimeExecutionProtectionPlanStatus(
                row.protection_plan_status
            ),
            order_lifecycle_method=row.order_lifecycle_method,
            handoff_draft_recorded=row.handoff_draft_recorded,
            requires_order_lifecycle_adapter=row.requires_order_lifecycle_adapter,
            order_lifecycle_adapter_implemented=row.order_lifecycle_adapter_implemented,
            execution_intent_status_changed=row.execution_intent_status_changed,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
