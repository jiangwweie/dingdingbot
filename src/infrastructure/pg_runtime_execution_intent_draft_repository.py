"""PG repository for non-executable runtime ExecutionIntent drafts."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
    RuntimeExecutionPlanStatus,
)
from src.domain.runtime_final_gate_preview import RuntimeFinalGatePreviewVerdict
from src.domain.signal_evaluation import (
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGRuntimeExecutionIntentDraftORM


class PgRuntimeExecutionIntentDraftRepository:
    """Persist non-executable runtime intent draft audit records."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        draft: RuntimeExecutionIntentDraft,
    ) -> RuntimeExecutionIntentDraft:
        async with self._session_maker() as session:
            session.add(self._to_orm(draft))
            await session.commit()
        return draft

    async def get(self, draft_id: str) -> Optional[RuntimeExecutionIntentDraft]:
        async with self._session_maker() as session:
            row = await session.get(PGRuntimeExecutionIntentDraftORM, draft_id)
            return self._to_domain(row) if row else None

    async def list_for_order_candidate(
        self,
        order_candidate_id: str,
        *,
        limit: int = 20,
    ) -> list[RuntimeExecutionIntentDraft]:
        async with self._session_maker() as session:
            stmt = (
                select(PGRuntimeExecutionIntentDraftORM)
                .where(
                    PGRuntimeExecutionIntentDraftORM.order_candidate_id
                    == order_candidate_id
                )
                .order_by(PGRuntimeExecutionIntentDraftORM.created_at_ms.desc())
                .limit(max(limit, 0))
            )
            result = await session.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_orm(
        draft: RuntimeExecutionIntentDraft,
    ) -> PGRuntimeExecutionIntentDraftORM:
        ids = draft.semantic_ids
        return PGRuntimeExecutionIntentDraftORM(
            draft_id=draft.draft_id,
            plan_id=draft.plan_id,
            runtime_instance_id=draft.runtime_instance_id,
            order_candidate_id=draft.order_candidate_id,
            signal_evaluation_id=draft.signal_evaluation_id,
            trial_binding_id=ids.trial_binding_id,
            strategy_family_id=ids.strategy_family_id,
            strategy_family_version_id=ids.strategy_family_version_id,
            status=draft.status.value,
            symbol=draft.symbol,
            side=draft.side,
            candidate_order_type=draft.candidate_order_type,
            proposed_quantity=draft.proposed_quantity,
            intended_notional=draft.intended_notional,
            entry_price_reference=draft.entry_price_reference,
            risk_preview_json=draft.risk_preview.model_dump(mode="json"),
            protection_preview_json=draft.protection_preview.model_dump(mode="json"),
            owner_reviewed=draft.owner_reviewed,
            owner_confirmed_for_intent=draft.owner_confirmed_for_intent,
            source_plan_status=draft.source_plan_status.value,
            final_gate_verdict=draft.final_gate_verdict.value,
            blockers_json=list(draft.blockers),
            warnings_json=list(draft.warnings),
            owner_confirmation_required=draft.owner_confirmation_required,
            dry_run=draft.dry_run,
            preview_only=draft.preview_only,
            not_order=draft.not_order,
            not_execution_intent=draft.not_execution_intent,
            execution_intent_repository_write_enabled=(
                draft.execution_intent_repository_write_enabled
            ),
            execution_intent_created=draft.execution_intent_created,
            order_created=draft.order_created,
            exchange_called=draft.exchange_called,
            created_at_ms=draft.created_at_ms,
            metadata_json=dict(draft.metadata),
        )

    @staticmethod
    def _to_domain(
        row: PGRuntimeExecutionIntentDraftORM,
    ) -> RuntimeExecutionIntentDraft:
        return RuntimeExecutionIntentDraft(
            draft_id=row.draft_id,
            plan_id=row.plan_id,
            runtime_instance_id=row.runtime_instance_id,
            order_candidate_id=row.order_candidate_id,
            signal_evaluation_id=row.signal_evaluation_id,
            semantic_ids=BrcSemanticIds(
                runtime_instance_id=row.runtime_instance_id,
                trial_binding_id=row.trial_binding_id,
                strategy_family_id=row.strategy_family_id,
                strategy_family_version_id=row.strategy_family_version_id,
                signal_evaluation_id=row.signal_evaluation_id,
                order_candidate_id=row.order_candidate_id,
            ),
            status=RuntimeExecutionIntentDraftStatus(row.status),
            symbol=row.symbol,
            side=row.side,
            candidate_order_type=row.candidate_order_type,
            proposed_quantity=row.proposed_quantity,
            intended_notional=row.intended_notional,
            entry_price_reference=row.entry_price_reference,
            risk_preview=OrderCandidateRiskPreview.model_validate(
                row.risk_preview_json or {}
            ),
            protection_preview=OrderCandidateProtectionPreview.model_validate(
                row.protection_preview_json or {}
            ),
            owner_reviewed=row.owner_reviewed,
            owner_confirmed_for_intent=row.owner_confirmed_for_intent,
            source_plan_status=RuntimeExecutionPlanStatus(row.source_plan_status),
            final_gate_verdict=RuntimeFinalGatePreviewVerdict(row.final_gate_verdict),
            blockers=list(row.blockers_json or []),
            warnings=list(row.warnings_json or []),
            owner_confirmation_required=row.owner_confirmation_required,
            dry_run=row.dry_run,
            preview_only=row.preview_only,
            not_order=row.not_order,
            not_execution_intent=row.not_execution_intent,
            execution_intent_repository_write_enabled=(
                row.execution_intent_repository_write_enabled
            ),
            execution_intent_created=row.execution_intent_created,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
