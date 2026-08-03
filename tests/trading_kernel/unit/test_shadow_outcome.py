from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeSpec,
    evaluate_fixed_horizon_excursion,
)


def test_fixed_horizon_excursion_projects_long_mfe_and_mae_in_r() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long", entry_reference_price=Decimal(100), initial_stop_price=Decimal(95)),
        (_candle(close_time_ms=2, high=Decimal(110), low=Decimal(97)),),
    )

    assert projection.evaluation_kind == "fixed_horizon_excursion_v1"
    assert projection.max_favorable_price == Decimal(110)
    assert projection.max_adverse_price == Decimal(97)
    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal("0.6")


def test_fixed_horizon_excursion_projects_short_mfe_and_mae_in_r() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="short", entry_reference_price=Decimal(100), initial_stop_price=Decimal(105)),
        (_candle(close_time_ms=2, high=Decimal(103), low=Decimal(90)),),
    )

    assert projection.evaluation_kind == "fixed_horizon_excursion_v1"
    assert projection.max_favorable_price == Decimal(90)
    assert projection.max_adverse_price == Decimal(103)
    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal("0.6")


def test_fixed_horizon_excursion_uses_only_closed_candles_inside_horizon() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long", horizon_start_ms=2, horizon_end_ms=3),
        (
            _candle(close_time_ms=2, high=Decimal(140), low=Decimal(60)),
            _candle(close_time_ms=3, high=Decimal(110), low=Decimal(97)),
            _candle(close_time_ms=4, high=Decimal(130), low=Decimal(70)),
        ),
    )

    assert projection.max_favorable_price == Decimal(110)
    assert projection.max_adverse_price == Decimal(97)
    assert projection.observed_through_ms == 3


def test_fixed_horizon_excursion_reports_zero_for_unreached_adverse_move() -> None:
    projection = evaluate_fixed_horizon_excursion(
        _spec(position_side="long"),
        (
            _candle(
                close_time_ms=2,
                high=Decimal(110),
                low=Decimal(101),
                open_price=Decimal(101),
                close_price=Decimal(101),
            ),
        ),
    )

    assert projection.mfe_r == Decimal(2)
    assert projection.mae_r == Decimal(0)


def test_fixed_horizon_excursion_requires_positive_risk_distance() -> None:
    with pytest.raises(ValueError, match="risk distance"):
        _spec(
            position_side="long",
            entry_reference_price=Decimal(100),
            initial_stop_price=Decimal(100),
        )


def _spec(
    *,
    position_side: str,
    entry_reference_price: Decimal = Decimal(100),
    initial_stop_price: Decimal = Decimal(95),
    horizon_start_ms: int = 1,
    horizon_end_ms: int = 2,
) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id="shadow:test",
        admission_decision_id="admission:test",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side=position_side,
        timeframe="1h",
        entry_reference_price=entry_reference_price,
        initial_stop_price=initial_stop_price,
        horizon_start_ms=horizon_start_ms,
        horizon_end_ms=horizon_end_ms,
        created_at_ms=1,
    )


def _candle(
    *,
    close_time_ms: int,
    high: Decimal,
    low: Decimal,
    open_price: Decimal = Decimal(100),
    close_price: Decimal = Decimal(100),
) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=close_time_ms - 1,
        close_time_ms=close_time_ms,
        open=open_price,
        high=high,
        low=low,
        close=close_price,
        volume=Decimal(1),
    )
