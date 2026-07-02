"""Observe-only PatternResult to StrategySignalV2 adapter.

This adapter is intentionally pure: it does not calculate sizing, perform
permission checks, call risk, create OrderStrategy, or dispatch execution.
"""

from __future__ import annotations

from dataclasses import is_dataclass, asdict
from typing import Any, Optional, Sequence

from src.domain.models import FilterResult, KlineData, PatternResult
from src.domain.strategy_contract_v2 import (
    EntryPolicy,
    EntryPolicyKind,
    LifecycleExitPolicy,
    LifecycleExitPolicyKind,
    RequiredHistory,
    StopPolicy,
    StopPolicyKind,
    StrategyFamily,
    StrategySignalV2,
    TakeProfitPolicy,
    TakeProfitPolicyKind,
)


class PatternResultToStrategySignalV2Adapter:
    """Map local pattern detections to the StrategySignalV2 contract."""

    def __init__(self, adapter_version: str = "v1") -> None:
        self._adapter_version = adapter_version

    def adapt(
        self,
        *,
        pattern: PatternResult,
        kline: KlineData,
        filter_results: Optional[Sequence[tuple[str, Any]]] = None,
        source_context_id: Optional[str] = None,
        adapter_version: Optional[str] = None,
    ) -> StrategySignalV2:
        """Create an observe-only StrategySignalV2 from a PatternResult."""
        version = adapter_version or self._adapter_version
        strategy_name = self._normalize_strategy_name(pattern.strategy_name)
        return StrategySignalV2(
            strategy_id=f"{strategy_name}_{version}",
            strategy_family=StrategyFamily.PATTERN,
            symbol=kline.symbol,
            timeframe=kline.timeframe,
            direction=pattern.direction,
            entry_policy=EntryPolicy(
                kind=EntryPolicyKind.MARKET_AFTER_CONFIRMED_CLOSE,
                trigger="pattern_confirmed",
                parameters={"pattern_strategy": strategy_name},
            ),
            stop_policy=StopPolicy(
                kind=StopPolicyKind.NONE,
                required=False,
                risk_notes=(
                    "observe_only_adapter: no formal stop semantics are derived "
                    "from PatternResult.details"
                ),
            ),
            take_profit_policy=TakeProfitPolicy(
                kind=TakeProfitPolicyKind.MULTI_TP_RR,
                levels=[],
            ),
            lifecycle_exit_policy=LifecycleExitPolicy(
                kind=LifecycleExitPolicyKind.NONE,
            ),
            required_history=RequiredHistory(
                same_timeframe_bars=self._required_history_bars(strategy_name),
            ),
            score=pattern.score,
            metadata={
                "adapter": "PatternResultToStrategySignalV2Adapter",
                "adapter_version": version,
                "observe_only": True,
                "tp_policy_note": "derived_later; no TP execution semantics created by adapter",
                "pattern_details": dict(pattern.details or {}),
                "filter_results": self._serialize_filter_results(filter_results or []),
                "kline_timestamp": kline.timestamp,
            },
            created_at_ms=kline.timestamp,
            source_context_id=source_context_id,
        )

    @staticmethod
    def _normalize_strategy_name(strategy_name: str) -> str:
        return strategy_name.strip().lower().replace(" ", "_")

    @staticmethod
    def _required_history_bars(strategy_name: str) -> int:
        if strategy_name == "engulfing":
            return 2
        return 1

    @classmethod
    def _serialize_filter_results(
        cls,
        filter_results: Sequence[tuple[str, Any]],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for name, result in filter_results:
            serialized.append(
                {
                    "name": name,
                    "result": cls._serialize_filter_result(result),
                }
            )
        return serialized

    @staticmethod
    def _serialize_filter_result(result: Any) -> dict[str, Any]:
        if isinstance(result, FilterResult):
            return {
                "passed": result.passed,
                "reason": result.reason,
                "metadata": result.metadata,
            }
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json")
        if is_dataclass(result):
            return asdict(result)
        if isinstance(result, dict):
            return result
        return {"value": str(result)}
