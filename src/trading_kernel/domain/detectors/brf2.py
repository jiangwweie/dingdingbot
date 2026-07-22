"""BRF2-001 short bear-rally-failure detector."""

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


class BRF2ShortDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        one_hour = snapshot.candles_1h
        four_hour = snapshot.candles_4h
        if len(one_hour) < 12:
            return invalid_result(
                self._contract,
                "brf2_invalid_insufficient_1h_candles",
            )
        if len(four_hour) < 2:
            return invalid_result(
                self._contract,
                "brf2_invalid_missing_4h_context",
            )

        latest = one_hour[-1]
        previous = one_hour[-2]
        lookback = one_hour[-9:-1]
        rally_low = min(item.low for item in lookback)
        rally_high = max(item.high for item in (*lookback, latest))
        rally_pct = _pct(rally_high - rally_low, rally_low)
        latest_range = max(latest.high - latest.low, Decimal("0"))
        upper_wick = max(
            latest.high - max(latest.open, latest.close),
            Decimal("0"),
        )
        upper_wick_ratio = (
            upper_wick / latest_range
            if latest_range > Decimal("0")
            else Decimal("0")
        )
        close_reversal_pct = _pct(latest.high - latest.close, latest.high)
        htf_net_pct = _pct(
            four_hour[-1].close - four_hour[0].close,
            four_hour[0].close,
        )
        strong_uptrend_disable = htf_net_pct >= Decimal("3.0")
        rally_extension_confirmed = rally_pct >= Decimal("2.0")
        rejection_confirmed = (
            upper_wick_ratio >= Decimal("0.30")
            and close_reversal_pct >= Decimal("0.40")
            and latest.close < latest.open
            and latest.close <= previous.close
        )
        rally_failure_confirmed = (
            rally_extension_confirmed and rejection_confirmed
        )
        short_side_not_disabled = not strong_uptrend_disable
        triggered = rally_failure_confirmed and short_side_not_disabled
        facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="rally_failure_confirmed",
                value=rally_failure_confirmed,
                satisfied=rally_failure_confirmed,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="short_side_not_disabled",
                value=short_side_not_disabled,
                satisfied=short_side_not_disabled,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="rally_high_reference",
                value=str(rally_high),
                satisfied=True,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="strong_uptrend_disable",
                value=strong_uptrend_disable,
                satisfied=strong_uptrend_disable,
            ),
        )
        if strong_uptrend_disable:
            reason = "brf2_no_action_strong_uptrend_disable"
        elif not rally_extension_confirmed:
            reason = "brf2_no_action_no_rally_extension"
        elif not rejection_confirmed:
            reason = "brf2_no_action_no_rejection_close"
        else:
            reason = "brf2_short_bear_rally_failure"
        return computed_result(
            self._contract,
            snapshot,
            triggered=triggered,
            reason_code=reason,
            facts=facts,
        )


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")
