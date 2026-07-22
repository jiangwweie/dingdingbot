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

        opening_range = candles[:4]
        latest = candles[-1]
        previous = candles[-2]
        range_high = max(item.high for item in opening_range)
        range_low = min(item.low for item in opening_range)
        breakout = latest.close > range_high and latest.close >= previous.close
        breakdown = latest.close < range_low and latest.close <= previous.close
        if self._contract.event_id == "SOR-LONG":
            triggered = breakout
            event_fact = "breakout_confirmed"
            reference_fact = "opening_range_low_reference"
            reference_value = range_low
            reason = (
                "sor_opening_range_breakout"
                if triggered
                else "sor_no_action_opening_range_intact"
            )
        else:
            triggered = breakdown
            event_fact = "breakdown_confirmed"
            reference_fact = "opening_range_high_reference"
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
                fact_name="opening_range_defined",
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
                fact_name=reference_fact,
                value=str(reference_value),
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
