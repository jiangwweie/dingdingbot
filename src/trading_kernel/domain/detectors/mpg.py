"""MPG-001 long momentum-persistence detector."""

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


class MPGLongDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        scope_error = validate_snapshot_scope(self._contract, snapshot)
        if scope_error is not None:
            return invalid_result(self._contract, scope_error)
        one_hour = snapshot.candles_1h
        four_hour = snapshot.candles_4h
        if len(one_hour) < 16:
            return invalid_result(
                self._contract,
                "mpg_invalid_insufficient_1h_candles",
            )
        if len(four_hour) < 4:
            return invalid_result(
                self._contract,
                "mpg_invalid_insufficient_4h_candles",
            )

        latest = one_hour[-1]
        lookback = one_hour[-9:-1]
        floor_lookback = one_hour[-6:-1]
        one_hour_net_pct = _pct(
            latest.close - lookback[0].close,
            lookback[0].close,
        )
        four_hour_net_pct = _pct(
            four_hour[-1].close - four_hour[0].close,
            four_hour[0].close,
        )
        previous_range_high = max(item.high for item in lookback)
        momentum_floor = min(item.low for item in floor_lookback)
        higher_closes = _count_higher_closes(one_hour[-5:])
        momentum_confirmed = (
            four_hour_net_pct >= Decimal("0.8")
            and one_hour_net_pct >= Decimal("1.0")
            and latest.close > previous_range_high
            and latest.close > latest.open
            and higher_closes >= 3
        )
        local_facts = (
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="momentum_persistence_confirmed",
                value=momentum_confirmed,
                satisfied=momentum_confirmed,
            ),
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="momentum_floor_reference",
                value=str(momentum_floor),
                satisfied=True,
            ),
        )
        if not momentum_confirmed:
            return computed_result(
                self._contract,
                snapshot,
                triggered=False,
                reason_code="mpg_no_action_momentum_persistence_not_confirmed",
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
                "mpg_invalid_comparative_strength_member_missing",
            )
        leader_confirmed = member.rank == 1 and member.return_pct > Decimal("0")
        facts = (
            local_facts[0],
            fact_snapshot(
                self._contract,
                snapshot,
                fact_name="leader_strength_confirmed",
                value=leader_confirmed,
                satisfied=leader_confirmed,
                observed_at_ms=comparative.observed_at_ms,
                valid_until_ms=comparative.valid_until_ms,
            ),
            local_facts[1],
        )
        return computed_result(
            self._contract,
            snapshot,
            triggered=leader_confirmed,
            reason_code=(
                "mpg_long_momentum_persistence"
                if leader_confirmed
                else "mpg_no_action_leader_strength_not_confirmed"
            ),
            facts=facts,
        )


def _comparative_invalid_reason(snapshot: MarketSnapshot) -> str | None:
    comparative = snapshot.comparative_strength
    if comparative is None:
        return "mpg_invalid_comparative_strength_missing"
    if (
        comparative.strategy_group_id != "MPG-001"
        or comparative.timeframe != "1h"
        or comparative.lookback_bars != 8
        or comparative.trigger_candle_close_time_ms
        != snapshot.trigger_candle_close_time_ms
    ):
        return "mpg_invalid_comparative_strength_scope"
    if (
        comparative.observed_at_ms > snapshot.trigger_candle_close_time_ms
        or comparative.valid_until_ms <= snapshot.trigger_candle_close_time_ms
    ):
        return "mpg_invalid_comparative_strength_stale"
    return None


def _count_higher_closes(candles) -> int:
    return sum(
        1
        for previous, current in zip(candles, candles[1:])
        if current.close > previous.close
    )


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")
