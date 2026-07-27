from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.domain.universe_projection import (
    build_rsr_projection,
    linear_quantile,
    sample_stddev,
)


EVENT_SPEC_ID = "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"


def test_rsr_projection_ranks_exact_universe_deterministically() -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    candidates = {
        member.exchange_instrument_id: _candles(
            count=744,
            duration_ms=3_600_000,
            slope=Decimal(index + 1) / Decimal("1000"),
            quote_volume_multiplier=Decimal("1.2"),
        )
        for index, member in enumerate(universe.candidate_members)
    }
    references_1h = {
        member.exchange_instrument_id: _candles(
            count=744,
            duration_ms=3_600_000,
            slope=Decimal("0.0005"),
            quote_volume_multiplier=Decimal("1.1"),
        )
        for member in universe.reference_members
    }
    references_4h = {
        member.exchange_instrument_id: _candles(
            count=200,
            duration_ms=14_400_000,
            slope=Decimal("0.01"),
            quote_volume_multiplier=Decimal("1"),
        )
        for member in universe.reference_members
    }

    first = build_rsr_projection(
        universe=universe,
        candidate_candles_1h=candidates,
        reference_candles_1h=references_1h,
        reference_candles_4h=references_4h,
    )
    second = build_rsr_projection(
        universe=universe,
        candidate_candles_1h=dict(reversed(tuple(candidates.items()))),
        reference_candles_1h=references_1h,
        reference_candles_4h=references_4h,
    )

    assert first == second
    assert first.regime_eligible is True
    assert [member.exchange_instrument_id for member in first.top_two] == [
        "binance-usdm:SOXLUSDT:perpetual",
        "binance-usdm:AVGOUSDT:perpetual",
    ]
    assert all(member.relative_strength_24h > 0 for member in first.top_two)
    assert all(member.relative_strength_72h > 0 for member in first.top_two)
    assert first.projection_run_id.startswith("projection:")


def test_rsr_projection_requires_complete_quote_volume_and_membership() -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    candidates = {
        member.exchange_instrument_id: _candles(
            count=744,
            duration_ms=3_600_000,
            slope=Decimal("0.01"),
            quote_volume_multiplier=Decimal("1"),
        )
        for member in universe.candidate_members
    }
    first_id = universe.candidate_members[0].exchange_instrument_id
    broken = candidates[first_id][-1].model_copy(update={"quote_volume": None})
    candidates[first_id] = (*candidates[first_id][:-1], broken)
    references_1h = {
        member.exchange_instrument_id: _candles(
            count=744,
            duration_ms=3_600_000,
            slope=Decimal("0.001"),
            quote_volume_multiplier=Decimal("1"),
        )
        for member in universe.reference_members
    }
    references_4h = {
        member.exchange_instrument_id: _candles(
            count=200,
            duration_ms=14_400_000,
            slope=Decimal("0.01"),
            quote_volume_multiplier=Decimal("1"),
        )
        for member in universe.reference_members
    }

    with pytest.raises(ValueError, match="requires quote volume"):
        build_rsr_projection(
            universe=universe,
            candidate_candles_1h=candidates,
            reference_candles_1h=references_1h,
            reference_candles_4h=references_4h,
        )


def test_decimal_statistics_are_exact_and_use_sample_stddev() -> None:
    assert linear_quantile(
        (Decimal("0"), Decimal("10")),
        Decimal("0.35"),
    ) == Decimal("3.50")
    assert sample_stddev((Decimal("1"), Decimal("3"))) == Decimal(2).sqrt()


def _candles(
    *,
    count: int,
    duration_ms: int,
    slope: Decimal,
    quote_volume_multiplier: Decimal,
) -> tuple[ClosedCandle, ...]:
    start_ms = 1_700_000_000_000
    candles = []
    for index in range(count):
        close = Decimal("100") + slope * Decimal(index)
        quote_volume = (
            Decimal("100")
            if index < count - 24
            else Decimal("100") * quote_volume_multiplier
        )
        candles.append(
            ClosedCandle(
                open_time_ms=start_ms + index * duration_ms,
                close_time_ms=start_ms + (index + 1) * duration_ms,
                open=close - Decimal("0.01"),
                high=close + Decimal("0.1"),
                low=close - Decimal("0.1"),
                close=close,
                volume=Decimal("10"),
                quote_volume=quote_volume,
            )
        )
    return tuple(candles)
