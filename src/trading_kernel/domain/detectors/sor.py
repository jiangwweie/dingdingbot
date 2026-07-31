"""SOR-001 event-specific four-bar 15m opening-range detectors."""

from __future__ import annotations

from src.trading_kernel.domain.detector import (
    DetectorResult,
    computed_result,
    fact_snapshot,
    invalid_result,
    validate_snapshot_scope,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract


class SORDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        candles = snapshot.candles_15m
        if len(candles) < 5:
            return invalid_result(
                self._contract,
                "sor_invalid_insufficient_15m_candles",
            )

        session_start_ms = (
            snapshot.trigger_candle_close_time_ms // 86_400_000
        ) * 86_400_000
        session_end_ms = session_start_ms + 86_400_000
        if (
            candles[0].open_time_ms != session_start_ms
            or any(
                candle.open_time_ms != session_start_ms + index * 900_000
                or candle.close_time_ms != session_start_ms + (index + 1) * 900_000
                for index, candle in enumerate(candles)
            )
        ):
            return invalid_result(
                self._contract,
                "sor_invalid_session_candle_sequence",
            )

        opening_range = candles[:4]
        latest = candles[-1]
        previous = candles[-2]
        range_high = max(item.high for item in opening_range)
        range_low = min(item.low for item in opening_range)
        breakout = previous.close <= range_high and latest.close > range_high
        breakdown = previous.close >= range_low and latest.close < range_low
        if self._contract.event_id == "SOR-LONG":
            triggered = breakout
            event_fact = "breakout_edge_crossed_v3"
            protection_fact = "opening_range_low_reference_v3"
            lifecycle_fact = "opening_range_high_reference_v3"
            reference_value = range_low
            reason = (
                "sor_opening_range_breakout"
                if triggered
                else "sor_no_action_opening_range_intact"
            )
        else:
            triggered = breakdown
            event_fact = "breakdown_edge_crossed_v3"
            protection_fact = "opening_range_high_reference_v3"
            lifecycle_fact = "opening_range_low_reference_v3"
            reference_value = range_high
            reason = (
                "sor_opening_range_breakdown"
                if triggered
                else "sor_no_action_opening_range_intact"
            )
        facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="opening_range_defined_v3",
                value=True,
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name=event_fact,
                value=triggered,
                satisfied=triggered,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name=lifecycle_fact,
                value=str(range_high if self._contract.position_side == "long" else range_low),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name=protection_fact,
                value=str(reference_value),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="session_start_ms_v3",
                value=str(session_start_ms),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="session_end_ms_v3",
                value=str(session_end_ms),
                satisfied=True,
            ),
        )
        return computed_result(
            self._contract,
            snapshot,
            triggered=triggered,
            reason_code=reason,
            facts=facts,
        )
