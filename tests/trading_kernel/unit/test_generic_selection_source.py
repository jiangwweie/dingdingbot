from decimal import Decimal, localcontext

import pytest

from src.trading_kernel.domain.generic_selection_source import GenericSelectionCandle
from tests.trading_kernel.support.generic_selection import HOUR, inputs


def test_generic_input_digest_includes_complete_ohlcv_not_only_close() -> None:
    source = inputs("CPM-RO-001")
    window = source.member_windows[0]
    candle = window.candles[0]
    for field in ("high", "base_volume", "quote_volume"):
        changed = candle.model_copy(update={field: getattr(candle, field) + Decimal(1)})
        other = type(window).model_validate(window.model_copy(update={"candles": (changed, *window.candles[1:])}).model_dump(mode="python"))
        assert other.closes == window.closes
        assert other.input_window_digest != window.input_window_digest


@pytest.mark.parametrize("defect", ["float", "future", "high", "volume"])
def test_hourly_candle_rejects_noncanonical_source(defect: str) -> None:
    payload = {"open_time_ms": HOUR, "close_time_ms": 2 * HOUR, "open": Decimal(1), "high": Decimal(2),
        "low": Decimal(1), "close": Decimal(2), "base_volume": Decimal(1), "quote_volume": Decimal(2)}
    if defect == "float": payload["close"] = 2.0
    elif defect == "future": payload["close_time_ms"] += 1
    elif defect == "high": payload["high"] = Decimal(1)
    else: payload["base_volume"] = Decimal(-1)
    with pytest.raises((ValueError, TypeError)):
        GenericSelectionCandle.model_validate(payload)


def test_unknown_qualification_is_not_an_empty_selection() -> None:
    window = inputs("CPM-RO-001").member_windows[0]
    payload = window.qualification.model_dump(mode="python")
    payload["venue_status"] = ""
    with pytest.raises(ValueError):
        type(window.qualification).model_validate(payload)


def test_raw_source_digest_is_independent_of_ambient_decimal_precision() -> None:
    window = inputs("CPM-RO-001").member_windows[0]
    other = window.model_copy(update={"candles": (window.candles[0].model_copy(update={
        "high": Decimal("200.123456789012345678901234567890123456789"),
    }), *window.candles[1:])})
    expected = other.input_window_digest
    with localcontext() as context:
        context.prec = 6
        assert other.input_window_digest == expected
    assert other.input_window_digest != window.input_window_digest
