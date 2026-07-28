from __future__ import annotations

import pytest

from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    ComparativeUniverseProjection,
    build_comparative_universe_projection,
    comparative_member_set_digest,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    ETH,
    NOW_MS,
    OP,
    SOL,
    mpg_long_snapshot,
)

MEMBERS = tuple(sorted((ETH, OP, SOL)))


def test_projection_binds_exact_members_close_and_canonical_digest() -> None:
    candles = mpg_long_snapshot().candles_1h

    projection = build_comparative_universe_projection(
        event_spec_id="event_spec:MPG-001:MPG-LONG:v2",
        universe_version_id="universe:mpg:v1",
        strategy_group_id="MPG-001",
        exchange_instrument_ids=MEMBERS,
        closed_bar_time_ms=NOW_MS,
        lookback_bars=8,
        freshness_window_ms=3_600_000,
        member_windows=tuple(
            ComparativeMemberWindow(
                exchange_instrument_id=member,
                candles_1h=candles,
            )
            for member in reversed(MEMBERS)
        ),
    )

    assert projection.member_set_digest == comparative_member_set_digest(MEMBERS)
    assert tuple(
        window.exchange_instrument_id for window in projection.member_windows
    ) == MEMBERS
    assert tuple(
        member.exchange_instrument_id
        for member in projection.comparative_strength.members
    ) == MEMBERS
    assert projection.closed_bar_time_ms == NOW_MS
    assert projection.candles_for(SOL) == candles


@pytest.mark.parametrize("invalid_case", ("missing_member", "wrong_close"))
def test_projection_rejects_incomplete_or_mixed_close_windows(
    invalid_case: str,
) -> None:
    candles = mpg_long_snapshot().candles_1h
    windows = tuple(
        ComparativeMemberWindow(
            exchange_instrument_id=member,
            candles_1h=(
                candles[:-1] if invalid_case == "wrong_close" else candles
            ),
        )
        for member in MEMBERS
        if invalid_case != "missing_member" or member != OP
    )

    with pytest.raises(ValueError):
        build_comparative_universe_projection(
            event_spec_id="event_spec:MPG-001:MPG-LONG:v2",
            universe_version_id="universe:mpg:v1",
            strategy_group_id="MPG-001",
            exchange_instrument_ids=MEMBERS,
            closed_bar_time_ms=NOW_MS,
            lookback_bars=8,
            freshness_window_ms=3_600_000,
            member_windows=windows,
        )


def test_projection_model_rejects_member_digest_drift() -> None:
    candles = mpg_long_snapshot().candles_1h
    valid = build_comparative_universe_projection(
        event_spec_id="event_spec:MPG-001:MPG-LONG:v2",
        universe_version_id="universe:mpg:v1",
        strategy_group_id="MPG-001",
        exchange_instrument_ids=MEMBERS,
        closed_bar_time_ms=NOW_MS,
        lookback_bars=8,
        freshness_window_ms=3_600_000,
        member_windows=tuple(
            ComparativeMemberWindow(
                exchange_instrument_id=member,
                candles_1h=candles,
            )
            for member in MEMBERS
        ),
    )

    with pytest.raises(ValueError, match="member digest"):
        ComparativeUniverseProjection.model_validate(
            {
                **valid.model_dump(mode="python"),
                "member_set_digest": "sha256:" + ("0" * 64),
            }
        )
