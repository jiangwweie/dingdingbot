"""PG repository for SignalEvaluation / OrderCandidate shadow records."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
    OrderCandidateStatus,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGOrderCandidateORM, PGSignalEvaluationORM


class PgSignalEvaluationRepository:
    """Persistence for shadow-only SignalEvaluation and OrderCandidate records."""

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

    async def create_signal_evaluation(
        self,
        evaluation: SignalEvaluation,
    ) -> SignalEvaluation:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._evaluation_to_orm(evaluation)
                session.add(row)
                await session.flush()
                return self._evaluation_to_domain(row)

    async def get_signal_evaluation(
        self,
        signal_evaluation_id: str,
    ) -> Optional[SignalEvaluation]:
        async with self._session_maker() as session:
            row = await session.get(PGSignalEvaluationORM, signal_evaluation_id)
            return self._evaluation_to_domain(row) if row is not None else None

    async def list_signal_evaluations(
        self,
        *,
        runtime_instance_id: Optional[str] = None,
        trial_binding_id: Optional[str] = None,
        strategy_family_id: Optional[str] = None,
        strategy_family_version_id: Optional[str] = None,
        status: Optional[SignalEvaluationStatus] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[SignalEvaluation]:
        async with self._session_maker() as session:
            stmt = select(PGSignalEvaluationORM)
            if runtime_instance_id is not None:
                stmt = stmt.where(PGSignalEvaluationORM.runtime_instance_id == runtime_instance_id)
            if trial_binding_id is not None:
                stmt = stmt.where(PGSignalEvaluationORM.trial_binding_id == trial_binding_id)
            if strategy_family_id is not None:
                stmt = stmt.where(PGSignalEvaluationORM.strategy_family_id == strategy_family_id)
            if strategy_family_version_id is not None:
                stmt = stmt.where(
                    PGSignalEvaluationORM.strategy_family_version_id == strategy_family_version_id
                )
            if status is not None:
                stmt = stmt.where(PGSignalEvaluationORM.status == status.value)
            if symbol is not None:
                stmt = stmt.where(PGSignalEvaluationORM.symbol == symbol)
            stmt = stmt.order_by(PGSignalEvaluationORM.updated_at_ms.desc()).limit(max(limit, 0))
            result = await session.execute(stmt)
            return [self._evaluation_to_domain(row) for row in result.scalars().all()]

    async def update_signal_evaluation_status(
        self,
        evaluation: SignalEvaluation,
    ) -> SignalEvaluation:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGSignalEvaluationORM,
                    evaluation.signal_evaluation_id,
                )
                if row is None:
                    raise ValueError(f"signal evaluation not found: {evaluation.signal_evaluation_id}")
                updated = self._evaluation_to_orm(evaluation)
                for key in [
                    "status",
                    "decision",
                    "reason_codes_json",
                    "rationale",
                    "evidence_snapshot_json",
                    "policy_snapshot_json",
                    "expires_at_ms",
                    "updated_at_ms",
                    "metadata_json",
                ]:
                    setattr(row, key, getattr(updated, key))
                await session.flush()
                return self._evaluation_to_domain(row)

    async def create_order_candidate(self, candidate: OrderCandidate) -> OrderCandidate:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._candidate_to_orm(candidate)
                session.add(row)
                await session.flush()
                return self._candidate_to_domain(row)

    async def get_order_candidate(
        self,
        order_candidate_id: str,
    ) -> Optional[OrderCandidate]:
        async with self._session_maker() as session:
            row = await session.get(PGOrderCandidateORM, order_candidate_id)
            return self._candidate_to_domain(row) if row is not None else None

    async def list_order_candidates(
        self,
        *,
        runtime_instance_id: Optional[str] = None,
        trial_binding_id: Optional[str] = None,
        strategy_family_id: Optional[str] = None,
        strategy_family_version_id: Optional[str] = None,
        signal_evaluation_id: Optional[str] = None,
        status: Optional[OrderCandidateStatus] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[OrderCandidate]:
        async with self._session_maker() as session:
            stmt = select(PGOrderCandidateORM)
            if runtime_instance_id is not None:
                stmt = stmt.where(PGOrderCandidateORM.runtime_instance_id == runtime_instance_id)
            if trial_binding_id is not None:
                stmt = stmt.where(PGOrderCandidateORM.trial_binding_id == trial_binding_id)
            if strategy_family_id is not None:
                stmt = stmt.where(PGOrderCandidateORM.strategy_family_id == strategy_family_id)
            if strategy_family_version_id is not None:
                stmt = stmt.where(
                    PGOrderCandidateORM.strategy_family_version_id == strategy_family_version_id
                )
            if signal_evaluation_id is not None:
                stmt = stmt.where(PGOrderCandidateORM.signal_evaluation_id == signal_evaluation_id)
            if status is not None:
                stmt = stmt.where(PGOrderCandidateORM.status == status.value)
            if symbol is not None:
                stmt = stmt.where(PGOrderCandidateORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderCandidateORM.updated_at_ms.desc()).limit(max(limit, 0))
            result = await session.execute(stmt)
            return [self._candidate_to_domain(row) for row in result.scalars().all()]

    async def update_order_candidate_status(
        self,
        candidate: OrderCandidate,
    ) -> OrderCandidate:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGOrderCandidateORM, candidate.order_candidate_id)
                if row is None:
                    raise ValueError(f"order candidate not found: {candidate.order_candidate_id}")
                updated = self._candidate_to_orm(candidate)
                for key in [
                    "status",
                    "risk_preview_json",
                    "protection_preview_json",
                    "rationale",
                    "evidence_refs_json",
                    "updated_at_ms",
                    "expires_at_ms",
                    "metadata_json",
                ]:
                    setattr(row, key, getattr(updated, key))
                await session.flush()
                return self._candidate_to_domain(row)

    @staticmethod
    def _evaluation_to_orm(evaluation: SignalEvaluation) -> PGSignalEvaluationORM:
        payload = evaluation.model_dump(mode="json")
        return PGSignalEvaluationORM(
            signal_evaluation_id=payload["signal_evaluation_id"],
            runtime_instance_id=payload.get("runtime_instance_id"),
            trial_binding_id=payload.get("trial_binding_id"),
            strategy_family_id=payload.get("strategy_family_id"),
            strategy_family_version_id=payload.get("strategy_family_version_id"),
            source_signal_id=payload.get("source_signal_id"),
            symbol=payload["symbol"],
            side=payload["side"],
            status=payload["status"],
            decision=payload["decision"],
            reason_codes_json=list(payload["reason_codes"]),
            rationale=payload["rationale"],
            evidence_snapshot_json=dict(payload["evidence_snapshot"]),
            policy_snapshot_json=dict(payload["policy_snapshot"]),
            evaluated_at_ms=payload["evaluated_at_ms"],
            expires_at_ms=payload.get("expires_at_ms"),
            shadow_mode=payload["shadow_mode"],
            execution_enabled=payload["execution_enabled"],
            not_order=payload["not_order"],
            not_execution_intent=payload["not_execution_intent"],
            created_at_ms=payload["created_at_ms"],
            updated_at_ms=payload["updated_at_ms"],
            metadata_json=dict(payload["metadata"]),
        )

    @staticmethod
    def _evaluation_to_domain(row: PGSignalEvaluationORM) -> SignalEvaluation:
        return SignalEvaluation(
            signal_evaluation_id=row.signal_evaluation_id,
            runtime_instance_id=row.runtime_instance_id,
            trial_binding_id=row.trial_binding_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            source_signal_id=row.source_signal_id,
            symbol=row.symbol,
            side=row.side,
            status=SignalEvaluationStatus(row.status),
            decision=SignalEvaluationDecision(row.decision),
            reason_codes=list(row.reason_codes_json or []),
            rationale=row.rationale,
            evidence_snapshot=dict(row.evidence_snapshot_json or {}),
            policy_snapshot=dict(row.policy_snapshot_json or {}),
            evaluated_at_ms=row.evaluated_at_ms,
            expires_at_ms=row.expires_at_ms,
            shadow_mode=row.shadow_mode,
            execution_enabled=row.execution_enabled,
            not_order=row.not_order,
            not_execution_intent=row.not_execution_intent,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            metadata=dict(row.metadata_json or {}),
        )

    @staticmethod
    def _candidate_to_orm(candidate: OrderCandidate) -> PGOrderCandidateORM:
        payload = candidate.model_dump(mode="json")
        return PGOrderCandidateORM(
            order_candidate_id=payload["order_candidate_id"],
            signal_evaluation_id=payload["signal_evaluation_id"],
            runtime_instance_id=payload.get("runtime_instance_id"),
            trial_binding_id=payload.get("trial_binding_id"),
            strategy_family_id=payload.get("strategy_family_id"),
            strategy_family_version_id=payload.get("strategy_family_version_id"),
            symbol=payload["symbol"],
            side=payload["side"],
            status=payload["status"],
            candidate_order_type=payload["candidate_order_type"],
            proposed_quantity=candidate.proposed_quantity,
            intended_notional=candidate.intended_notional,
            entry_price_reference=candidate.entry_price_reference,
            risk_preview_json=dict(payload["risk_preview"]),
            protection_preview_json=dict(payload["protection_preview"]),
            rationale=payload["rationale"],
            evidence_refs_json=list(payload["evidence_refs"]),
            shadow_mode=payload["shadow_mode"],
            execution_enabled=payload["execution_enabled"],
            candidate_executable=payload["candidate_executable"],
            not_order=payload["not_order"],
            not_execution_intent=payload["not_execution_intent"],
            created_at_ms=payload["created_at_ms"],
            updated_at_ms=payload["updated_at_ms"],
            expires_at_ms=payload.get("expires_at_ms"),
            metadata_json=dict(payload["metadata"]),
        )

    @staticmethod
    def _candidate_to_domain(row: PGOrderCandidateORM) -> OrderCandidate:
        return OrderCandidate(
            order_candidate_id=row.order_candidate_id,
            signal_evaluation_id=row.signal_evaluation_id,
            runtime_instance_id=row.runtime_instance_id,
            trial_binding_id=row.trial_binding_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            symbol=row.symbol,
            side=row.side,
            status=OrderCandidateStatus(row.status),
            candidate_order_type=row.candidate_order_type,
            proposed_quantity=row.proposed_quantity,
            intended_notional=row.intended_notional,
            entry_price_reference=row.entry_price_reference,
            risk_preview=OrderCandidateRiskPreview.model_validate(row.risk_preview_json or {}),
            protection_preview=OrderCandidateProtectionPreview.model_validate(
                row.protection_preview_json or {}
            ),
            rationale=row.rationale,
            evidence_refs=list(row.evidence_refs_json or []),
            shadow_mode=row.shadow_mode,
            execution_enabled=row.execution_enabled,
            candidate_executable=row.candidate_executable,
            not_order=row.not_order,
            not_execution_intent=row.not_execution_intent,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            expires_at_ms=row.expires_at_ms,
            metadata=dict(row.metadata_json or {}),
        )
