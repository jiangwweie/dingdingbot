"""Shadow service for SignalEvaluation and OrderCandidate records."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Optional, Protocol

from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
    OrderCandidateStatus,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import SignalSide, StrategyFamilySignalOutput
from src.domain.strategy_runtime import StrategyRuntimeInstance


def _now_ms() -> int:
    return int(time.time() * 1000)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class SignalEvaluationShadowError(ValueError):
    """Raised when a shadow signal evaluation operation is invalid."""


class SignalEvaluationRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def create_signal_evaluation(
        self,
        evaluation: SignalEvaluation,
    ) -> SignalEvaluation:
        ...

    async def get_signal_evaluation(
        self,
        signal_evaluation_id: str,
    ) -> Optional[SignalEvaluation]:
        ...

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
        ...

    async def update_signal_evaluation_status(
        self,
        evaluation: SignalEvaluation,
    ) -> SignalEvaluation:
        ...

    async def create_order_candidate(self, candidate: OrderCandidate) -> OrderCandidate:
        ...

    async def get_order_candidate(
        self,
        order_candidate_id: str,
    ) -> Optional[OrderCandidate]:
        ...

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
        ...

    async def update_order_candidate_status(
        self,
        candidate: OrderCandidate,
    ) -> OrderCandidate:
        ...


class SignalEvaluationShadowService:
    """Application service for non-executing signal evaluation shadow records."""

    def __init__(self, *, repository: SignalEvaluationRepositoryPort) -> None:
        self._repository = repository

    async def initialize(self) -> None:
        await self._repository.initialize()

    async def create_signal_evaluation(
        self,
        *,
        symbol: str,
        side: str = "none",
        runtime: Optional[StrategyRuntimeInstance] = None,
        runtime_instance_id: Optional[str] = None,
        trial_binding_id: Optional[str] = None,
        strategy_family_id: Optional[str] = None,
        strategy_family_version_id: Optional[str] = None,
        source_signal_id: Optional[str] = None,
        decision: SignalEvaluationDecision = SignalEvaluationDecision.NO_ACTION,
        status: SignalEvaluationStatus = SignalEvaluationStatus.EVALUATED,
        reason_codes: Optional[list[str]] = None,
        rationale: str = "",
        evidence_snapshot: Optional[dict[str, Any]] = None,
        policy_snapshot: Optional[dict[str, Any]] = None,
        expires_at_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SignalEvaluation:
        runtime_ids = self._runtime_ids(runtime)
        now_ms = _now_ms()
        evaluation = SignalEvaluation(
            signal_evaluation_id=_id("signal-evaluation"),
            runtime_instance_id=runtime_instance_id or runtime_ids.get("runtime_instance_id"),
            trial_binding_id=trial_binding_id or runtime_ids.get("trial_binding_id"),
            strategy_family_id=strategy_family_id or runtime_ids.get("strategy_family_id"),
            strategy_family_version_id=(
                strategy_family_version_id or runtime_ids.get("strategy_family_version_id")
            ),
            source_signal_id=source_signal_id,
            symbol=symbol,
            side=self._normalize_side(side),
            status=status,
            decision=decision,
            reason_codes=reason_codes or [],
            rationale=rationale,
            evidence_snapshot=evidence_snapshot or {},
            policy_snapshot=policy_snapshot or {},
            evaluated_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            metadata={"source": "signal_evaluation_shadow_service", **(metadata or {})},
        )
        return await self._repository.create_signal_evaluation(evaluation)

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime: Optional[StrategyRuntimeInstance] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else str(output.side.value)
        decision = (
            SignalEvaluationDecision.CANDIDATE
            if side in {"long", "short"}
            else SignalEvaluationDecision.NO_ACTION
        )
        return await self.create_signal_evaluation(
            symbol=output.symbol,
            side=side,
            runtime=runtime,
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            decision=decision,
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evidence_snapshot=output.model_dump(mode="json"),
            policy_snapshot={
                "expected_risk_shape": str(output.expected_risk_shape),
                "required_execution_mode": output.required_execution_mode,
                "review_plan": output.review_plan.model_dump(mode="json"),
            },
            metadata={
                "adapter": "StrategyFamilySignalOutput",
                "adapter_scope": "shadow_only",
                **(metadata or {}),
            },
        )

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        evaluation = await self._repository.get_signal_evaluation(signal_evaluation_id)
        if evaluation is None:
            raise SignalEvaluationShadowError(
                f"signal evaluation not found: {signal_evaluation_id}"
            )
        return evaluation

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
        return await self._repository.list_signal_evaluations(
            runtime_instance_id=runtime_instance_id,
            trial_binding_id=trial_binding_id,
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            status=status,
            symbol=symbol,
            limit=limit,
        )

    async def create_order_candidate_from_signal_evaluation(
        self,
        signal_evaluation_id: str,
        *,
        candidate_order_type: str = "market",
        proposed_quantity: Optional[Decimal] = None,
        intended_notional: Optional[Decimal] = None,
        entry_price_reference: Optional[Decimal] = None,
        risk_preview: Optional[OrderCandidateRiskPreview] = None,
        protection_preview: Optional[OrderCandidateProtectionPreview] = None,
        rationale: str = "",
        evidence_refs: Optional[list[str]] = None,
        expires_at_ms: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> OrderCandidate:
        evaluation = await self.get_signal_evaluation(signal_evaluation_id)
        if evaluation.side not in {"long", "short"}:
            raise SignalEvaluationShadowError(
                "order candidate requires a directional signal evaluation"
            )
        now_ms = _now_ms()
        candidate = OrderCandidate(
            order_candidate_id=_id("order-candidate"),
            signal_evaluation_id=evaluation.signal_evaluation_id,
            runtime_instance_id=evaluation.runtime_instance_id,
            trial_binding_id=evaluation.trial_binding_id,
            strategy_family_id=evaluation.strategy_family_id,
            strategy_family_version_id=evaluation.strategy_family_version_id,
            symbol=evaluation.symbol,
            side=evaluation.side,
            candidate_order_type=candidate_order_type,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            risk_preview=risk_preview
            or OrderCandidateRiskPreview(
                intended_notional=intended_notional,
                proposed_quantity=proposed_quantity,
            ),
            protection_preview=protection_preview or OrderCandidateProtectionPreview(),
            rationale=rationale or evaluation.rationale,
            evidence_refs=evidence_refs or [evaluation.signal_evaluation_id],
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            metadata={
                "source_signal_evaluation_id": evaluation.signal_evaluation_id,
                "source": "signal_evaluation_shadow_service",
                **(metadata or {}),
            },
        )
        return await self._repository.create_order_candidate(candidate)

    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        candidate = await self._repository.get_order_candidate(order_candidate_id)
        if candidate is None:
            raise SignalEvaluationShadowError(f"order candidate not found: {order_candidate_id}")
        return candidate

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
        return await self._repository.list_order_candidates(
            runtime_instance_id=runtime_instance_id,
            trial_binding_id=trial_binding_id,
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            signal_evaluation_id=signal_evaluation_id,
            status=status,
            symbol=symbol,
            limit=limit,
        )

    async def update_signal_evaluation_status(
        self,
        signal_evaluation_id: str,
        status: SignalEvaluationStatus,
    ) -> SignalEvaluation:
        evaluation = await self.get_signal_evaluation(signal_evaluation_id)
        values = evaluation.model_dump()
        values["status"] = status
        values["updated_at_ms"] = _now_ms()
        return await self._repository.update_signal_evaluation_status(
            SignalEvaluation.model_validate(values)
        )

    async def update_order_candidate_status(
        self,
        order_candidate_id: str,
        status: OrderCandidateStatus,
    ) -> OrderCandidate:
        candidate = await self.get_order_candidate(order_candidate_id)
        values = candidate.model_dump()
        values["status"] = status
        values["updated_at_ms"] = _now_ms()
        return await self._repository.update_order_candidate_status(
            OrderCandidate.model_validate(values)
        )

    async def update_shadow_status(
        self,
        *,
        object_type: str,
        object_id: str,
        status: str,
    ) -> SignalEvaluation | OrderCandidate:
        if object_type == "signal_evaluation":
            return await self.update_signal_evaluation_status(
                object_id,
                SignalEvaluationStatus(status),
            )
        if object_type == "order_candidate":
            return await self.update_order_candidate_status(
                object_id,
                OrderCandidateStatus(status),
            )
        raise SignalEvaluationShadowError(f"unsupported shadow object type: {object_type}")

    @staticmethod
    def _runtime_ids(runtime: Optional[StrategyRuntimeInstance]) -> dict[str, Optional[str]]:
        if runtime is None:
            return {}
        return {
            "runtime_instance_id": runtime.runtime_instance_id,
            "trial_binding_id": runtime.trial_binding_id,
            "strategy_family_id": runtime.strategy_family_id,
            "strategy_family_version_id": runtime.strategy_family_version_id,
        }

    @staticmethod
    def _normalize_side(side: str) -> str:
        value = str(side).strip().lower()
        if value in {"long", "short", "none"}:
            return value
        raise SignalEvaluationShadowError(f"unsupported signal evaluation side: {side}")
