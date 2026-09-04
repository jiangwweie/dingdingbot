from decimal import Decimal

import pytest

from research.multi_strategy_selection.context_features import (
    ContextFeatureError,
    HourlyClose,
    compute_market_context,
    directional_efficiency_24h,
)


def _history(symbol: str, cutoff: int, drift: Decimal) -> tuple[HourlyClose, ...]:
    return tuple(
        HourlyClose(
            symbol=symbol,
            close_time_ms=cutoff - (24 - index) * 3_600_000,
            close=Decimal(100) + drift * index,
        )
        for index in range(25)
    )


def test_market_context_requires_complete_24_member_point_in_time_state() -> None:
    cutoff = 2_000_000_000_000
    histories = {
        f"S{index:02d}": _history(f"S{index:02d}", cutoff, Decimal(index + 1) / 100)
        for index in range(24)
    }

    result = compute_market_context(histories, cutoff_ms=cutoff)

    assert result.valid_candidate_count == 24
    assert result.valid_pair_count == 276
    assert result.missing_pair_count == 0
    assert Decimal(0) <= result.market_breadth_24h <= Decimal(1)


def test_market_context_rejects_future_or_incomplete_input() -> None:
    cutoff = 2_000_000_000_000
    histories = {
        f"S{index:02d}": _history(f"S{index:02d}", cutoff, Decimal("0.1"))
        for index in range(24)
    }
    histories["S00"] = (*histories["S00"], HourlyClose(symbol="S00", close_time_ms=cutoff + 1, close=Decimal(200)))
    with pytest.raises(ContextFeatureError, match="future"):
        compute_market_context(histories, cutoff_ms=cutoff)

    del histories["S23"]
    with pytest.raises(ContextFeatureError, match="24"):
        compute_market_context(histories, cutoff_ms=cutoff)


def test_cpm_directional_efficiency_uses_exact_24h_path() -> None:
    cutoff = 2_000_000_000_000
    values = _history("BTCUSDT", cutoff, Decimal(1))
    assert directional_efficiency_24h(values, cutoff_ms=cutoff) == Decimal(1)
