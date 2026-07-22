"""MI-001 long twelve-hour momentum-impulse detector."""

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


class MILongDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        candles = snapshot.candles_1h
        if len(candles) < 13:
            return invalid_result(
                self._contract,
                "mi_invalid_insufficient_candles",
            )

        latest = candles[-1]
        lookback = candles[-13]
        impulse_return_pct = (
            (latest.close - lookback.close) / lookback.close
        ) * Decimal("100")
        impulse_confirmed = impulse_return_pct >= Decimal("3")
        local_facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="impulse_confirmed",
                value=impulse_confirmed,
                satisfied=impulse_confirmed,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="impulse_invalidation_reference",
                value=str(lookback.close),
                satisfied=True,
            ),
        )
        if not impulse_confirmed:
            return computed_result(
                self._contract,
                snapshot,
                triggered=False,
                reason_code="mi_no_action_impulse_below_threshold",
                facts=local_facts,
            )

        comparative = snapshot.comparative_strength
        invalid_reason = _comparative_invalid_reason(snapshot)
        if invalid_reason is not None:
            return invalid_result(self._contract, invalid_reason)
        if comparative is None:
            raise AssertionError("validated comparative snapshot disappeared")
        try:
            member = comparative.member(snapshot.exchange_instrument_id)
        except KeyError:
            return invalid_result(
                self._contract,
                "mi_invalid_comparative_strength_member_missing",
            )
        if member.return_pct != impulse_return_pct:
            return invalid_result(
                self._contract,
                "mi_invalid_comparative_return_mismatch",
            )
        relative_strength_confirmed = member.rank == 1
        facts = (
            local_facts[0],
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="relative_strength_confirmed",
                value=relative_strength_confirmed,
                satisfied=relative_strength_confirmed,
                observed_at_ms=comparative.observed_at_ms,
                valid_until_ms=comparative.valid_until_ms,
            ),
            local_facts[1],
        )
        return computed_result(
            self._contract,
            snapshot,
            triggered=relative_strength_confirmed,
            reason_code=(
                "mi_long_momentum_impulse"
                if relative_strength_confirmed
                else "mi_no_action_relative_strength_not_confirmed"
            ),
            facts=facts,
        )


def _comparative_invalid_reason(snapshot: MarketSnapshot) -> str | None:
    comparative = snapshot.comparative_strength
    if comparative is None:
        return "mi_invalid_comparative_strength_missing"
    if (
        comparative.strategy_group_id != "MI-001"
        or comparative.timeframe != "1h"
        or comparative.lookback_bars != 12
        or comparative.trigger_candle_close_time_ms
        != snapshot.trigger_candle_close_time_ms
    ):
        return "mi_invalid_comparative_strength_scope"
    if (
        comparative.observed_at_ms > snapshot.trigger_candle_close_time_ms
        or comparative.valid_until_ms <= snapshot.trigger_candle_close_time_ms
    ):
        return "mi_invalid_comparative_strength_stale"
    return None
