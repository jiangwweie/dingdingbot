from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.entry_regime import BtcMa50Snapshot, evaluate_btc_ma50
from src.trading_kernel.domain.market import ClosedCandle

H = 14400000


def _snapshot(last=101):
    bars = []
    for i in range(50):
        price = Decimal(last if i == 49 else 100)
        bars.append(
            ClosedCandle(
                open_time_ms=(i + 1) * H,
                close_time_ms=(i + 2) * H,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal(1),
            )
        )
    return BtcMa50Snapshot(candles=tuple(bars), observed_at_ms=51 * H + 1000)


def test_ma50_includes_latest_closed_bar_and_strictly_requires_above() -> None:
    snapshot = _snapshot()
    assert snapshot.sma50 == Decimal("100.02")
    assert evaluate_btc_ma50(snapshot, now_ms=51 * H + 2000) == "allowed"
    assert (
        evaluate_btc_ma50(_snapshot(last=100), now_ms=51 * H + 2000)
        == "btc4h_not_above_ma50"
    )


def test_four_hour_boundary_cannot_use_previous_snapshot() -> None:
    assert evaluate_btc_ma50(_snapshot(), now_ms=52 * H) == "btc4h_facts_unavailable"
    assert evaluate_btc_ma50(None, now_ms=52 * H) == "btc4h_facts_unavailable"


@pytest.mark.parametrize("alteration", ["missing", "gap", "future", "unaligned"])
def test_regime_rejects_incomplete_or_future_window(alteration: str) -> None:
    data = _snapshot().model_dump(mode="python")
    bars = list(data["candles"])
    if alteration == "missing":
        bars.pop(5)
    if alteration == "gap":
        bars[5] = bars[4]
    if alteration == "future":
        data["observed_at_ms"] = 50 * H
    if alteration == "unaligned":
        bars[5] = {**bars[5], "open_time_ms": bars[5]["open_time_ms"] + 1}
    data["candles"] = bars
    with pytest.raises(ValidationError):
        BtcMa50Snapshot.model_validate(data)
