"""Application service for B0 strategy-runtime promotion gate previews."""

from __future__ import annotations

from src.domain.strategy_runtime_promotion_gate import (
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateInput,
    StrategyRuntimePromotionGateResult,
    StrategyRuntimePromotionScope,
    StrategySemanticsConfirmationFacts,
    evaluate_strategy_runtime_promotion_gate,
)
from src.domain.strategy_semantics import (
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class StrategyRuntimePromotionGateServiceError(ValueError):
    """Raised when a promotion gate preview cannot be built."""


class StrategyRuntimePromotionGateService:
    """Preview promotion readiness by strategy family/version.

    This service is read-only and non-executing. It does not create
    SignalEvaluation, OrderCandidate, ExecutionIntent, local orders, runtime
    mutations, or exchange requests.
    """

    def __init__(
        self,
        *,
        catalog: StrategySemanticsCatalog | None = None,
    ) -> None:
        self._catalog = catalog or initial_strategy_semantics_catalog()

    def preview(
        self,
        *,
        strategy_family_id: str,
        strategy_family_version_id: str,
        scope: StrategyRuntimePromotionScope = (
            StrategyRuntimePromotionScope.CONTROLLED_RUNTIME_EXECUTION
        ),
        semantic_confirmations: StrategySemanticsConfirmationFacts | None = None,
        runtime_confirmations: RuntimeExecutionConfirmationFacts | None = None,
        first_real_submit_confirmations: FirstRealSubmitConfirmationFacts | None = None,
    ) -> StrategyRuntimePromotionGateResult:
        try:
            binding = self._catalog.get_binding(
                strategy_family_id=strategy_family_id,
                strategy_family_version_id=strategy_family_version_id,
            )
        except KeyError as exc:
            raise StrategyRuntimePromotionGateServiceError(
                "strategy semantics binding not found for promotion gate: "
                f"{strategy_family_id}:{strategy_family_version_id}"
            ) from exc
        return evaluate_strategy_runtime_promotion_gate(
            StrategyRuntimePromotionGateInput(
                binding=binding,
                scope=scope,
                semantic_confirmations=(
                    semantic_confirmations or StrategySemanticsConfirmationFacts()
                ),
                runtime_confirmations=(
                    runtime_confirmations or RuntimeExecutionConfirmationFacts()
                ),
                first_real_submit_confirmations=(
                    first_real_submit_confirmations
                    or FirstRealSubmitConfirmationFacts()
                ),
            )
        )
