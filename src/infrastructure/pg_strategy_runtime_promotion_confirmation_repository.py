"""PG repository for strategy-runtime promotion confirmation records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.experimental_runtime_profile_proposal import (
    ExperimentalRuntimeProfileProposal,
)
from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGStrategyRuntimePromotionConfirmationORM


class PgStrategyRuntimePromotionConfirmationRepository:
    """Append/read promotion-gate confirmation facts without execution authority."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def append(
        self,
        record: StrategyRuntimePromotionGateConfirmationRecord,
    ) -> StrategyRuntimePromotionGateConfirmationRecord:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._to_orm(record)
                session.add(row)
                await session.flush()
                return self._to_domain(row)

    async def get(
        self,
        confirmation_id: str,
    ) -> StrategyRuntimePromotionGateConfirmationRecord | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGStrategyRuntimePromotionConfirmationORM,
                confirmation_id,
            )
            return self._to_domain(row) if row is not None else None

    async def list(
        self,
        *,
        runtime_instance_id: str | None = None,
        strategy_family_id: str | None = None,
        strategy_family_version_id: str | None = None,
        scope: StrategyRuntimePromotionScope | None = None,
        limit: int = 50,
    ) -> list[StrategyRuntimePromotionGateConfirmationRecord]:
        async with self._session_maker() as session:
            stmt = select(PGStrategyRuntimePromotionConfirmationORM)
            if runtime_instance_id is not None:
                stmt = stmt.where(
                    PGStrategyRuntimePromotionConfirmationORM.runtime_instance_id
                    == runtime_instance_id
                )
            if strategy_family_id is not None:
                stmt = stmt.where(
                    PGStrategyRuntimePromotionConfirmationORM.strategy_family_id
                    == strategy_family_id
                )
            if strategy_family_version_id is not None:
                stmt = stmt.where(
                    PGStrategyRuntimePromotionConfirmationORM.strategy_family_version_id
                    == strategy_family_version_id
                )
            if scope is not None:
                stmt = stmt.where(
                    PGStrategyRuntimePromotionConfirmationORM.scope == scope.value
                )
            stmt = (
                stmt.order_by(
                    PGStrategyRuntimePromotionConfirmationORM.created_at_ms.desc(),
                    PGStrategyRuntimePromotionConfirmationORM.confirmation_id.desc(),
                )
                .limit(max(limit, 0))
            )
            result = await session.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]

    @staticmethod
    def _to_orm(
        record: StrategyRuntimePromotionGateConfirmationRecord,
    ) -> PGStrategyRuntimePromotionConfirmationORM:
        return PGStrategyRuntimePromotionConfirmationORM(
            confirmation_id=record.confirmation_id,
            runtime_instance_id=record.runtime_instance_id,
            strategy_family_id=record.strategy_family_id,
            strategy_family_version_id=record.strategy_family_version_id,
            scope=record.scope.value,
            semantic_confirmations_json=record.semantic_confirmations.model_dump(
                mode="json"
            ),
            runtime_confirmations_json=record.runtime_confirmations.model_dump(
                mode="json"
            ),
            first_real_submit_confirmations_json=(
                record.first_real_submit_confirmations.model_dump(mode="json")
            ),
            promotion_gate_result_snapshot_json=(
                record.promotion_gate_result_snapshot.model_dump(mode="json")
                if record.promotion_gate_result_snapshot is not None
                else None
            ),
            runtime_profile_proposal_snapshot_json=(
                record.runtime_profile_proposal_snapshot.model_dump(mode="json")
                if record.runtime_profile_proposal_snapshot is not None
                else None
            ),
            recorded_by=record.recorded_by,
            reason=record.reason,
            evidence_refs=list(record.evidence_refs),
            metadata_json=dict(record.metadata),
            records_promotion_gate_confirmation=(
                record.records_promotion_gate_confirmation
            ),
            not_execution_authority=record.not_execution_authority,
            execution_intent_created=record.execution_intent_created,
            order_created=record.order_created,
            exchange_called=record.exchange_called,
            owner_bounded_execution_called=record.owner_bounded_execution_called,
            order_lifecycle_called=record.order_lifecycle_called,
            runtime_mutation_created=record.runtime_mutation_created,
            withdrawal_instruction_created=record.withdrawal_instruction_created,
            transfer_instruction_created=record.transfer_instruction_created,
            created_at_ms=record.created_at_ms,
            updated_at_ms=record.created_at_ms,
        )

    @staticmethod
    def _to_domain(
        row: PGStrategyRuntimePromotionConfirmationORM,
    ) -> StrategyRuntimePromotionGateConfirmationRecord:
        result_snapshot = None
        if row.promotion_gate_result_snapshot_json is not None:
            result_snapshot = StrategyRuntimePromotionGateResult(
                **dict(row.promotion_gate_result_snapshot_json)
            )
        profile_proposal_snapshot = None
        if row.runtime_profile_proposal_snapshot_json is not None:
            profile_proposal_snapshot = ExperimentalRuntimeProfileProposal(
                **dict(row.runtime_profile_proposal_snapshot_json)
            )
        return StrategyRuntimePromotionGateConfirmationRecord(
            confirmation_id=row.confirmation_id,
            runtime_instance_id=row.runtime_instance_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            scope=StrategyRuntimePromotionScope(row.scope),
            semantic_confirmations=StrategySemanticsConfirmationFacts(
                **dict(row.semantic_confirmations_json or {})
            ),
            runtime_confirmations=RuntimeExecutionConfirmationFacts(
                **dict(row.runtime_confirmations_json or {})
            ),
            first_real_submit_confirmations=FirstRealSubmitConfirmationFacts(
                **dict(row.first_real_submit_confirmations_json or {})
            ),
            runtime_profile_proposal_snapshot=profile_proposal_snapshot,
            promotion_gate_result_snapshot=result_snapshot,
            recorded_by=row.recorded_by,
            reason=row.reason,
            evidence_refs=list(row.evidence_refs or []),
            created_at_ms=row.created_at_ms,
            metadata=dict(row.metadata_json or {}),
            records_promotion_gate_confirmation=(
                row.records_promotion_gate_confirmation
            ),
            not_execution_authority=row.not_execution_authority,
            execution_intent_created=row.execution_intent_created,
            order_created=row.order_created,
            exchange_called=row.exchange_called,
            owner_bounded_execution_called=row.owner_bounded_execution_called,
            order_lifecycle_called=row.order_lifecycle_called,
            runtime_mutation_created=row.runtime_mutation_created,
            withdrawal_instruction_created=row.withdrawal_instruction_created,
            transfer_instruction_created=row.transfer_instruction_created,
        )
