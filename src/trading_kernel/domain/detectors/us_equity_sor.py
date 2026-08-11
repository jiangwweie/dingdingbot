"""Regular-session 30-minute opening-range detector for TradFi equity perps."""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise

from src.trading_kernel.domain.detector import (
    DetectorResult,
    DetectorStatus,
    computed_result,
    fact_snapshot,
    invalid_result,
    validate_snapshot_scope,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract

_BAR_MS = 900_000
_ENTRY_WINDOW_END_BARS = 10
_ATR_PERIOD = 14
_STOP_ATR_BUFFER = Decimal("0.10")
_MAX_STOP_ATR = Decimal("1.25")


class USEquitySORDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        product = snapshot.product_session
        if product is None:
            return invalid_result(self._contract, "us_sor_product_session_missing")
        if (
            product.observed_at_ms > snapshot.trigger_candle_close_time_ms
            or product.valid_until_ms <= snapshot.trigger_candle_close_time_ms
        ):
            return invalid_result(self._contract, "us_sor_product_session_stale")
        if product.product_status != "active":
            return invalid_result(self._contract, "us_sor_product_unavailable")
        if product.session_state != "regular":
            return DetectorResult(
                event_spec_id=self._contract.event_spec_id,
                status=DetectorStatus.NOT_TRIGGERED,
                occurred_at_ms=None,
                reason_code="us_sor_outside_regular_session",
            )
        if not product.usable_for_regular_observation(
            snapshot.trigger_candle_close_time_ms
        ):
            return invalid_result(self._contract, "us_sor_product_session_invalid")
        regular_open_ms = product.regular_session_open_ms
        regular_close_ms = product.regular_session_close_ms
        assert regular_open_ms is not None
        assert regular_close_ms is not None
        trigger_ms = snapshot.trigger_candle_close_time_ms
        if not (
            regular_open_ms + 2 * _BAR_MS < trigger_ms
            <= min(
                regular_open_ms + _ENTRY_WINDOW_END_BARS * _BAR_MS,
                regular_close_ms - _BAR_MS,
            )
        ):
            return DetectorResult(
                event_spec_id=self._contract.event_spec_id,
                status=DetectorStatus.NOT_TRIGGERED,
                occurred_at_ms=None,
                reason_code="us_sor_outside_entry_window",
            )
        regular = tuple(
            candle
            for candle in snapshot.candles_15m
            if regular_open_ms <= candle.open_time_ms
            and candle.close_time_ms <= trigger_ms
        )
        if len(regular) < 3 or regular[-1].close_time_ms != trigger_ms:
            return invalid_result(self._contract, "us_sor_regular_candles_missing")
        if any(
            candle.open_time_ms != regular_open_ms + index * _BAR_MS
            or candle.close_time_ms != regular_open_ms + (index + 1) * _BAR_MS
            for index, candle in enumerate(regular)
        ):
            return invalid_result(self._contract, "us_sor_regular_candle_sequence")
        if len(snapshot.candles_15m) < _ATR_PERIOD + 1:
            return invalid_result(self._contract, "us_sor_atr_window_missing")

        opening_range = regular[:2]
        previous = regular[-2]
        latest = regular[-1]
        range_high = max(item.high for item in opening_range)
        range_low = min(item.low for item in opening_range)
        atr = _atr(snapshot.candles_15m[-(_ATR_PERIOD + 1) :])
        if self._contract.position_side == "long":
            edge_crossed = previous.close <= range_high and latest.close > range_high
            edge_fact = "breakout_edge_crossed_us_v1"
            lifecycle_fact = "opening_range_high_reference_us_v1"
            lifecycle_value = range_high
            initial_stop = min(range_high, latest.low) - atr * _STOP_ATR_BUFFER
            stop_distance = latest.close - initial_stop
            reason = "us_sor_regular_breakout"
        else:
            edge_crossed = previous.close >= range_low and latest.close < range_low
            edge_fact = "breakdown_edge_crossed_us_v1"
            lifecycle_fact = "opening_range_low_reference_us_v1"
            lifecycle_value = range_low
            initial_stop = max(range_low, latest.high) + atr * _STOP_ATR_BUFFER
            stop_distance = initial_stop - latest.close
            reason = "us_sor_regular_breakdown"
        if not edge_crossed:
            reason = "us_sor_opening_range_intact"
        stop_eligible = (
            initial_stop > 0
            and stop_distance > 0
            and stop_distance <= atr * _MAX_STOP_ATR
        )
        triggered = edge_crossed and stop_eligible
        if edge_crossed and not stop_eligible:
            reason = "us_sor_stop_distance_exceeded"
        facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="regular_session_confirmed_us_v1",
                value=True,
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="opening_range_defined_us_v1",
                value=True,
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name=edge_fact,
                value=edge_crossed,
                satisfied=edge_crossed,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name=lifecycle_fact,
                value=str(lifecycle_value),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="initial_stop_reference_us_v1",
                value=str(initial_stop),
                satisfied=stop_eligible,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="regular_session_open_ms_us_v1",
                value=str(regular_open_ms),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="session_exit_deadline_ms_us_v1",
                value=str(regular_close_ms - _BAR_MS),
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


def _atr(candles: tuple[ClosedCandle, ...]) -> Decimal:
    true_ranges = tuple(
        max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        for previous, current in pairwise(candles)
    )
    return sum(true_ranges, Decimal(0)) / Decimal(len(true_ranges))
