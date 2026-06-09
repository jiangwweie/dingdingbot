"""B0 strategy semantics to shadow OrderCandidate binding service.

The service is intentionally non-executing. It creates only shadow
OrderCandidate records through SignalEvaluationShadowService after strategy
semantics and RequiredFacts have passed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Protocol

from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
    SignalEvaluation,
)
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategyEvaluationContext,
    StrategyFactCheckStatus,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)
from src.domain.strategy_family_signal import (
    SignalType,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class StrategySemanticsBindingError(ValueError):
    """Raised when a strategy semantics binding cannot produce a shadow candidate."""


class StrategySemanticsShadowPort(Protocol):
    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime: Optional[StrategyRuntimeInstance] = None,
        metadata: Optional[dict] = None,
    ) -> SignalEvaluation:
        ...

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        ...

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
        metadata: Optional[dict] = None,
    ) -> OrderCandidate:
        ...


class StrategySemanticsShadowBindingService:
    """Create shadow OrderCandidates from explicit B0 strategy semantics."""

    def __init__(
        self,
        *,
        shadow_service: StrategySemanticsShadowPort,
        catalog: StrategySemanticsCatalog | None = None,
    ) -> None:
        self._shadow_service = shadow_service
        self._catalog = catalog or initial_strategy_semantics_catalog()

    async def create_semantic_order_candidate_from_strategy_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        context: StrategyEvaluationContext,
        runtime: StrategyRuntimeInstance | None = None,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> OrderCandidate:
        """Create a shadow candidate from a strategy output after B0 checks.

        The output is still evidence only. This method persists a shadow
        SignalEvaluation and then a shadow OrderCandidate; it never creates an
        ExecutionIntent or order.
        """

        if output.signal_type != SignalType.WOULD_ENTER:
            raise StrategySemanticsBindingError(
                "only WOULD_ENTER strategy outputs can be semantically bound "
                "to shadow OrderCandidate"
            )
        if output.not_order is not True or output.not_execution_intent is not True:
            raise StrategySemanticsBindingError(
                "strategy output must remain not_order and not_execution_intent"
            )
        _assert_context_matches_strategy_output(context, output)

        evaluation = await self._shadow_service.create_signal_evaluation_from_strategy_family_output(
            output,
            runtime=runtime,
            metadata={
                "adapter": "StrategySemanticsShadowBindingService",
                "source_strategy_signal_id": output.signal_id,
                "source_strategy_signal_mode": output.required_execution_mode,
                **(metadata or {}),
            },
        )
        return await self.create_semantic_order_candidate(
            signal_evaluation_id=evaluation.signal_evaluation_id,
            context=context,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            stop_price_reference=stop_price_reference,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            take_profit_references=take_profit_references,
            expires_at_ms=expires_at_ms,
            metadata={
                "source_strategy_signal_id": output.signal_id,
                "source_strategy_signal_type": output.signal_type.value,
                "source_strategy_required_execution_mode": output.required_execution_mode,
                **(metadata or {}),
            },
        )

    async def create_semantic_order_candidate(
        self,
        *,
        signal_evaluation_id: str,
        context: StrategyEvaluationContext,
        proposed_quantity: Decimal | None = None,
        intended_notional: Decimal | None = None,
        entry_price_reference: Decimal | None = None,
        stop_price_reference: Decimal | None = None,
        max_loss_reference: Decimal | None = None,
        leverage: Decimal | None = None,
        take_profit_references: list[dict] | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> OrderCandidate:
        evaluation = await self._shadow_service.get_signal_evaluation(
            signal_evaluation_id
        )
        binding = self._catalog.get_binding(
            strategy_family_id=_required_id(
                evaluation.strategy_family_id,
                "strategy_family_id",
            ),
            strategy_family_version_id=_required_id(
                evaluation.strategy_family_version_id,
                "strategy_family_version_id",
            ),
        )
        _assert_context_matches_evaluation(context, evaluation)

        if not binding.allows_shadow_order_candidate:
            raise StrategySemanticsBindingError(
                f"strategy binding is not order-candidate eligible: "
                f"{binding.candidate_mode.value}"
            )
        if evaluation.side not in binding.supported_sides:
            raise StrategySemanticsBindingError(
                f"evaluation side {evaluation.side} is not supported by "
                f"{binding.implementation_id}"
            )

        fact_check = binding.fact_check(context)
        if fact_check.status != StrategyFactCheckStatus.PASS:
            raise StrategySemanticsBindingError(
                "strategy RequiredFacts did not pass: "
                f"{fact_check.status.value}"
            )

        if binding.protection_policy.mandatory and stop_price_reference is None:
            raise StrategySemanticsBindingError(
                "concrete stop price reference is required before candidate binding"
            )

        candidate_order_type = binding.candidate_order_type()
        if candidate_order_type == "signal_only":
            raise StrategySemanticsBindingError(
                "signal-only strategy binding cannot produce an OrderCandidate"
            )

        risk_preview = OrderCandidateRiskPreview(
            intended_notional=intended_notional,
            proposed_quantity=proposed_quantity,
            max_loss_reference=max_loss_reference,
            leverage=leverage,
            notes=[
                "sizing is runtime/Owner bounded; strategy semantics do not authorize execution",
                f"semantic_binding={binding.implementation_id}",
            ],
        )
        protection_preview = OrderCandidateProtectionPreview(
            requires_protection=binding.protection_policy.mandatory,
            stop_reference=(
                binding.protection_policy.stop_policy.risk_notes
                or binding.protection_policy.stop_policy.kind.value
            ),
            stop_price_reference=stop_price_reference,
            take_profit_references=take_profit_references or [],
            notes=[
                "ProtectionPolicy bounds loss; ExitPolicy remains strategy-owned",
                *binding.protection_policy.notes,
            ],
        )
        semantic_metadata = {
            "source": "strategy_semantics_shadow_binding_service",
            "adapter_scope": "b0_shadow_only",
            "strategy_semantics": binding.semantic_snapshot(),
            "fact_check": fact_check.model_dump(mode="json"),
            "entry_policy": binding.entry_policy.model_dump(mode="json"),
            "protection_policy": binding.protection_policy.model_dump(mode="json"),
            "exit_policy": binding.exit_policy.model_dump(mode="json"),
            "right_tail_review_metrics": list(binding.review_metrics),
            "candidate_mode": StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED.value,
            **(metadata or {}),
        }
        return await self._shadow_service.create_order_candidate_from_signal_evaluation(
            evaluation.signal_evaluation_id,
            candidate_order_type=candidate_order_type,
            proposed_quantity=proposed_quantity,
            intended_notional=intended_notional,
            entry_price_reference=entry_price_reference,
            risk_preview=risk_preview,
            protection_preview=protection_preview,
            rationale=evaluation.rationale,
            evidence_refs=[
                evaluation.signal_evaluation_id,
                context.context_id,
                binding.implementation_id,
            ],
            expires_at_ms=expires_at_ms,
            metadata=semantic_metadata,
        )


def _required_id(value: str | None, field_name: str) -> str:
    if not value:
        raise StrategySemanticsBindingError(
            f"SignalEvaluation is missing {field_name}; cannot bind semantics"
        )
    return value


def _assert_context_matches_evaluation(
    context: StrategyEvaluationContext,
    evaluation: SignalEvaluation,
) -> None:
    mismatches: list[str] = []
    if context.strategy_family_id != evaluation.strategy_family_id:
        mismatches.append("strategy_family_id")
    if context.strategy_family_version_id != evaluation.strategy_family_version_id:
        mismatches.append("strategy_family_version_id")
    if context.symbol != evaluation.symbol:
        mismatches.append("symbol")
    if context.side != evaluation.side:
        mismatches.append("side")
    if mismatches:
        raise StrategySemanticsBindingError(
            "StrategyEvaluationContext does not match SignalEvaluation: "
            + ", ".join(mismatches)
        )


def _assert_context_matches_strategy_output(
    context: StrategyEvaluationContext,
    output: StrategyFamilySignalOutput,
) -> None:
    mismatches: list[str] = []
    if context.strategy_family_id != output.strategy_family_id:
        mismatches.append("strategy_family_id")
    if context.strategy_family_version_id != output.strategy_family_version_id:
        mismatches.append("strategy_family_version_id")
    if context.symbol != output.symbol:
        mismatches.append("symbol")
    if context.side != output.side.value:
        mismatches.append("side")
    if mismatches:
        raise StrategySemanticsBindingError(
            "StrategyEvaluationContext does not match StrategyFamilySignalOutput: "
            + ", ".join(mismatches)
        )
