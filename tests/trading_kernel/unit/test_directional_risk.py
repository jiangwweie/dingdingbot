from decimal import Decimal

import pytest

from src.trading_kernel.domain.directional_risk import (
    DirectionalControl,
    DirectionalView,
    effective_directional_limit,
)


@pytest.mark.parametrize(
    ("view", "long", "short"),
    [
        ("unset", "0.04", "0.04"),
        ("neutral", "0.04", "0.04"),
        ("bullish", "0.04", "0.02"),
        ("bearish", "0.02", "0.04"),
    ],
)
def test_directional_presets_only_tighten(view, long, short):
    control = DirectionalControl(
        venue_id="binance-usdm",
        account_id="a",
        version=1,
        view=DirectionalView(view),
        effective_at_ms=1,
    )
    for side, limit in (("long", long), ("short", short)):
        assert effective_directional_limit(control, side, Decimal("0.04")) == Decimal(
            limit
        )
        assert effective_directional_limit(control, side, Decimal("0.01")) == Decimal(
            "0.01"
        )


def test_missing_or_pending_authority_is_not_neutral():
    with pytest.raises(ValueError, match="directional_control_missing"):
        effective_directional_limit(None, "long", Decimal("0.04"))
    pending = DirectionalControl(
        venue_id="binance-usdm",
        account_id="a",
        version=2,
        view="neutral",
        effective_at_ms=1,
        pending_view="bearish",
        pending_request_id="r",
        requested_at_ms=2,
    )
    with pytest.raises(ValueError, match="directional_transition_pending"):
        effective_directional_limit(pending, "long", Decimal("0.04"))
