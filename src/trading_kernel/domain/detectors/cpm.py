"""CPM-RO-001 long pullback-reclaim detector."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.detector import (
    DetectorResult,
    computed_result,
    fact_snapshot,
    invalid_result,
    validate_snapshot_scope,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract


class CPMLongDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        one_hour = snapshot.candles_1h
        four_hour = snapshot.candles_4h
        if len(one_hour) < 21 or len(four_hour) < 21:
            return invalid_result(
                self._contract,
                "cpm_invalid_insufficient_candles",
            )

        latest_1h = one_hour[-1]
        previous_1h = one_hour[-2]
        latest_4h = four_hour[-1]
        previous_4h = four_hour[-2]
        sma20_1h = _sma(tuple(item.close for item in one_hour[-20:]))
        sma20_4h = _sma(tuple(item.close for item in four_hour[-20:]))
        htf_trend_intact = (
            latest_4h.close > sma20_4h
            and latest_4h.close >= previous_4h.close
        )
        lookback = one_hour[-21:-1]
        lookback_high = max(item.high for item in lookback)
        lookback_low = min(item.low for item in lookback)
        pullback_depth_pct = (
            (lookback_high - lookback_low) / lookback_high
        ) * Decimal("100")
        pullback_depth_normal = (
            Decimal("0.5") <= pullback_depth_pct <= Decimal("8.0")
        )
        reclaim_confirmed = (
            latest_1h.close > sma20_1h
            and latest_1h.close > previous_1h.high
        )
        triggered = (
            htf_trend_intact
            and pullback_depth_normal
            and reclaim_confirmed
        )
        facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="htf_trend_intact",
                value=htf_trend_intact,
                satisfied=htf_trend_intact,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="reclaim_confirmed",
                value=reclaim_confirmed,
                satisfied=reclaim_confirmed,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="pullback_low_reference",
                value=str(lookback_low),
                satisfied=True,
            ),
        )
        if not htf_trend_intact:
            reason = "cpm_no_action_trend_ambiguous"
        elif not pullback_depth_normal:
            reason = "cpm_no_action_no_pullback"
        elif not reclaim_confirmed:
            reason = "cpm_no_action_no_reclaim"
        else:
            reason = "cpm_long_pullback_reclaim"
        return computed_result(
            self._contract,
            snapshot,
            triggered=triggered,
            reason_code=reason,
            facts=facts,
        )


def _sma(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))
