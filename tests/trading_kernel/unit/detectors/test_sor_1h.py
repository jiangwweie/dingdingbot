from decimal import Decimal

import pytest

from src.trading_kernel.domain.detector import DetectorStatus, detector_for
from src.trading_kernel.domain.exit_policy import (
    registered_event_exit_bindings,
    registered_exit_profiles,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.orb_session_selection import ORB_EVENT_SPEC_IDS
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

D = 1_704_067_200_000
H = 3_600_000


def candle(i: int, close: int, high: int = 105, low: int = 95) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=D + i * H,
        close_time_ms=D + (i + 1) * H,
        open=Decimal(100),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(100),
    )


@pytest.mark.parametrize(
    "event,side,latest,stop,reclaim",
    [
        (ORB_EVENT_SPEC_IDS[0], "long", 106, "95", "105"),
        (ORB_EVENT_SPEC_IDS[1], "short", 94, "105", "95"),
    ],
)
def test_hourly_orb_both_sides_emit_new_facts_with_original_exit_clock(
    event, side, latest, stop, reclaim
):
    c = strategy_contract_for(event)
    snapshot = MarketSnapshot(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        trigger_candle_close_time_ms=D + 2 * H,
        candles_1h=(
            candle(0, 100),
            candle(1, latest, max(106, latest), min(94, latest)),
        ),
    )
    r = detector_for(event).evaluate(snapshot)
    assert r.status is DetectorStatus.TRIGGERED and r.occurred_at_ms == D + 2 * H
    assert r.facts_by_name[c.protection_reference_fact].value == stop
    assert r.facts_by_name[c.pre_tp1_reclaim_reference_fact].value == reclaim
    assert {f.fact_definition_id for f in r.facts} == {
        f.fact_definition_id for f in c.required_facts
    }
    binding = next(
        b for b in registered_event_exit_bindings() if b.event_spec_id == event
    )
    profile = next(
        p
        for p in registered_exit_profiles()
        if p.exit_profile_id == binding.exit_profile_id
    )
    assert profile.position_side == side and profile.runner.timeframe == "15m"
    assert profile.time_stop.max_holding_bars == 96
    assert all("_1h_" in f.fact_definition_id for f in r.facts)


@pytest.mark.parametrize("event", ORB_EVENT_SPEC_IDS)
def test_one_hour_opening_range_is_readonly_preparation_not_a_signal(event):
    c = strategy_contract_for(event)
    r = detector_for(event).evaluate(
        MarketSnapshot(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            trigger_candle_close_time_ms=D + H,
            candles_1h=(candle(0, 100),),
        )
    )
    assert r.status is DetectorStatus.NOT_TRIGGERED and r.occurred_at_ms is None
    assert len(r.facts) == len(c.required_facts)
    assert not r.facts_by_name["entry_hour_eligible_1h_v1"].value


@pytest.mark.parametrize(
    "defect", ["gap", "duplicate", "non_hour", "midnight", "missing", "old_15m"]
)
def test_hourly_orb_rejects_incomplete_wrong_clock_and_cross_session_paths(defect):
    bars = (candle(0, 100), candle(1, 106, 106, 95))
    now = D + 2 * H
    if defect == "gap":
        bars = (bars[0], candle(2, 106, 106, 95))
        now = D + 3 * H
    if defect == "duplicate":
        bars = (bars[0], bars[0])
        now = D + H
    if defect == "non_hour":
        now += 1
    if defect == "midnight":
        now = D + 24 * H
    if defect == "missing":
        bars = ()
    kwargs = {"candles_15m": bars} if defect == "old_15m" else {"candles_1h": bars}
    if defect == "duplicate":
        with pytest.raises(ValueError, match="ordered and unique"):
            MarketSnapshot(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                trigger_candle_close_time_ms=now,
                **kwargs,
            )
        return
    r = detector_for(ORB_EVENT_SPEC_IDS[0]).evaluate(
        MarketSnapshot(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            trigger_candle_close_time_ms=now,
            **kwargs,
        )
    )
    assert r.status is DetectorStatus.INVALID and not r.facts
