from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.exit_regime import FOUR_HOURS_MS, BtcMa50Snapshot
from src.trading_kernel.domain.market import ClosedCandle


def candles(close=100):
    return tuple(
        ClosedCandle(
            open_time_ms=(i + 1) * FOUR_HOURS_MS,
            close_time_ms=(i + 2) * FOUR_HOURS_MS,
            open=D(close if i == 49 else 90),
            high=D(close if i == 49 else 90),
            low=D(close if i == 49 else 90),
            close=D(close if i == 49 else 90),
            volume=D(1),
        )
        for i in range(50)
    )


def test_strict_closed_btc_average_includes_latest_bar():
    now = 51 * FOUR_HOURS_MS + 500
    snap = BtcMa50Snapshot.create(candles=candles(), observed_at_ms=now)
    assert snap.latest_close == 100
    assert snap.sma50 == D("90.2")
    assert snap.allowed_at(now)
    assert not snap.allowed_at(52 * FOUR_HOURS_MS)
    assert not BtcMa50Snapshot.create(
        candles=candles(90), observed_at_ms=now
    ).allowed_at(now)


@pytest.mark.parametrize("bad", ["short", "gap", "duplicate", "future", "unaligned"])
def test_incomplete_protocol_windows_never_authorize(bad):
    rows = list(candles())
    now = 51 * FOUR_HOURS_MS + 500
    if bad == "short":
        rows = rows[:-1]
    if bad == "gap":
        rows.pop(5)
    if bad == "duplicate":
        rows[5] = rows[4]
    if bad == "future":
        now -= FOUR_HOURS_MS
    if bad == "unaligned":
        rows[0] = rows[0].model_copy(update={"open_time_ms": rows[0].open_time_ms + 1})
    with pytest.raises(ValueError):
        BtcMa50Snapshot.create(candles=tuple(rows), observed_at_ms=now)
