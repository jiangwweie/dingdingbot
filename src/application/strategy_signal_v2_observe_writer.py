"""Observe-only writer for StrategySignalV2 shadow snapshots."""

from __future__ import annotations

import time
from typing import Any, Optional, Sequence

from src.application.pattern_strategy_signal_adapter import (
    PatternResultToStrategySignalV2Adapter,
)
from src.domain.models import KlineData, SignalAttempt
from src.infrastructure.logger import logger
from src.infrastructure.strategy_signal_v2_observe_sink import StrategySignalV2ObserveSink


class PatternStrategySignalObserveWriter:
    """Write StrategySignalV2 snapshots for pattern attempts without affecting flow."""

    def __init__(
        self,
        *,
        adapter: Optional[PatternResultToStrategySignalV2Adapter] = None,
        sink: Optional[StrategySignalV2ObserveSink] = None,
        schema_version: str = "v1",
    ) -> None:
        self._adapter = adapter or PatternResultToStrategySignalV2Adapter()
        self._sink = sink or StrategySignalV2ObserveSink()
        self._schema_version = schema_version

    def write_observations(
        self,
        *,
        kline: KlineData,
        attempts: Sequence[SignalAttempt],
        source_context_id: Optional[str] = None,
        adapter_version: Optional[str] = None,
    ) -> None:
        """Write snapshots for SIGNAL_FIRED/FILTERED attempts with PatternResult.

        All failures are warning-only and never raised to callers.
        """
        for attempt in attempts:
            if attempt.pattern is None:
                continue
            if attempt.final_result not in {"SIGNAL_FIRED", "FILTERED"}:
                continue

            snapshot = self._build_snapshot(
                kline=kline,
                attempt=attempt,
                source_context_id=source_context_id,
                adapter_version=adapter_version,
            )
            try:
                self._sink.write(snapshot)
            except Exception as exc:
                logger.warning(
                    "StrategySignalV2 observe sink write failed: "
                    f"symbol={kline.symbol}, timeframe={kline.timeframe}, "
                    f"strategy_name={attempt.strategy_name}, error={exc}"
                )

    def _build_snapshot(
        self,
        *,
        kline: KlineData,
        attempt: SignalAttempt,
        source_context_id: Optional[str],
        adapter_version: Optional[str],
    ) -> dict[str, Any]:
        base = {
            "schema": "strategy_signal_v2",
            "schema_version": self._schema_version,
            "observe_only": True,
            "adapter": "PatternResultToStrategySignalV2Adapter",
            "adapter_version": adapter_version or getattr(self._adapter, "_adapter_version", "unknown"),
            "created_at_ms": int(time.time() * 1000),
            "source_context_id": source_context_id,
            "attempt_context": self._attempt_context(kline, attempt),
        }

        try:
            strategy_signal = self._adapter.adapt(
                pattern=attempt.pattern,
                kline=kline,
                filter_results=attempt.filter_results,
                source_context_id=source_context_id,
                adapter_version=adapter_version,
            )
        except Exception as exc:
            logger.warning(
                "StrategySignalV2 observe adapter failed: "
                f"symbol={kline.symbol}, timeframe={kline.timeframe}, "
                f"strategy_name={attempt.strategy_name}, error={exc}"
            )
            return {
                **base,
                "adapter_status": "failed",
                "error": self._bounded_error(exc),
            }

        return {
            **base,
            "adapter_status": "ok",
            "strategy_signal_v2": strategy_signal.model_dump(mode="json"),
        }

    @staticmethod
    def _attempt_context(kline: KlineData, attempt: SignalAttempt) -> dict[str, Any]:
        return {
            "symbol": kline.symbol,
            "timeframe": kline.timeframe,
            "strategy_name": attempt.strategy_name,
            "final_result": attempt.final_result,
            "kline_timestamp": attempt.kline_timestamp,
        }

    @staticmethod
    def _bounded_error(exc: Exception, limit: int = 300) -> str:
        message = f"{type(exc).__name__}: {exc}"
        return message[:limit]
