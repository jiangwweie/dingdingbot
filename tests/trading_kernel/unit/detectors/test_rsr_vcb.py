from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.detector import DetectorStatus, detector_for
from src.trading_kernel.domain.detectors.rsr_vcb import (
    build_vcb_armed_structure,
    evaluate_rsr_vcb_trigger,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot, RSRVCBContext
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.domain.universe_projection import (
    RSRProjectionMember,
    RSRUniverseProjection,
)


EVENT_SPEC_ID = "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"


def test_vcb_uses_shifted_width_history_and_full_closed_15m_trigger() -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    instrument_id = universe.candidate_members[0].exchange_instrument_id
    candles_1h = _compressed_hour_candles()
    as_of_ms = candles_1h[-1].close_time_ms
    member = RSRProjectionMember(
        exchange_instrument_id=instrument_id,
        return_24h=Decimal("0.08"),
        return_72h=Decimal("0.18"),
        relative_strength_24h=Decimal("0.05"),
        relative_strength_72h=Decimal("0.12"),
        volume_ratio_24h=Decimal("1.2"),
        trend_eligible=True,
        eligible=True,
        rank=1,
    )
    projection = RSRUniverseProjection(
        projection_run_id="projection:" + "1" * 64,
        event_spec_id=EVENT_SPEC_ID,
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        as_of_close_time_ms=as_of_ms,
        regime_eligible=True,
        reference_digest="sha256:" + "2" * 64,
        members=(member,),
        input_digest="sha256:" + "3" * 64,
    )

    armed = build_vcb_armed_structure(
        projection=projection,
        member=member,
        candles_1h=candles_1h,
    )

    assert armed is not None
    assert armed.compression_ratio <= Decimal("0.90")
    assert armed.breakout_boundary > 0
    trigger_candles = _trigger_candles(
        armed_at_ms=armed.armed_at_ms,
        boundary=armed.breakout_boundary,
    )
    trigger = evaluate_rsr_vcb_trigger(
        armed=armed,
        candles_15m=trigger_candles,
        candles_1h=candles_1h,
    )

    assert trigger is not None
    assert trigger.trigger_volume_ratio == Decimal("2")
    assert Decimal("0") < trigger.initial_stop_reference < trigger.trigger_close

    context = RSRVCBContext(
        universe_version_id=armed.universe_version_id,
        universe_digest=armed.universe_digest,
        projection_run_id=armed.projection_run_id,
        armed_structure_id=armed.armed_structure_id,
        rsr_rank=armed.rsr_rank,
        relative_strength_24h=armed.relative_strength_24h,
        relative_strength_72h=armed.relative_strength_72h,
        rsr_volume_ratio_24h=armed.rsr_volume_ratio_24h,
        regime_eligible=True,
        compression_ratio=armed.compression_ratio,
        breakout_boundary=armed.breakout_boundary,
        armed_at_ms=armed.armed_at_ms,
        trigger_volume_ratio=trigger.trigger_volume_ratio,
        initial_stop_reference=trigger.initial_stop_reference,
    )
    snapshot = MarketSnapshot(
        exchange_instrument_id=instrument_id,
        trigger_candle_close_time_ms=trigger.trigger_close_time_ms,
        candles_15m=trigger_candles,
        candles_1h=candles_1h,
        rsr_vcb=context,
    )
    result = detector_for(EVENT_SPEC_ID).evaluate(snapshot)

    assert result.status is DetectorStatus.TRIGGERED
    assert result.reason_code == "rsr_vcb_full_trigger_confirmed"
    assert result.facts_by_name[
        "breakout_initial_stop_reference"
    ].value == str(trigger.initial_stop_reference)


def test_trigger_requires_first_cross_bullish_close_and_volume() -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    instrument_id = universe.candidate_members[0].exchange_instrument_id
    candles_1h = _compressed_hour_candles()
    as_of_ms = candles_1h[-1].close_time_ms
    member = RSRProjectionMember(
        exchange_instrument_id=instrument_id,
        return_24h=Decimal("0.08"),
        return_72h=Decimal("0.18"),
        relative_strength_24h=Decimal("0.05"),
        relative_strength_72h=Decimal("0.12"),
        volume_ratio_24h=Decimal("1.2"),
        trend_eligible=True,
        eligible=True,
        rank=1,
    )
    projection = RSRUniverseProjection(
        projection_run_id="projection:" + "4" * 64,
        event_spec_id=EVENT_SPEC_ID,
        universe_version_id=universe.universe_version_id,
        universe_digest=universe.semantic_digest(),
        as_of_close_time_ms=as_of_ms,
        regime_eligible=True,
        reference_digest="sha256:" + "5" * 64,
        members=(member,),
        input_digest="sha256:" + "6" * 64,
    )
    armed = build_vcb_armed_structure(
        projection=projection,
        member=member,
        candles_1h=candles_1h,
    )
    assert armed is not None
    candles = _trigger_candles(
        armed_at_ms=armed.armed_at_ms,
        boundary=armed.breakout_boundary,
    )

    low_volume = candles[-1].model_copy(update={"quote_volume": Decimal("179")})
    assert evaluate_rsr_vcb_trigger(
        armed=armed,
        candles_15m=(*candles[:-1], low_volume),
        candles_1h=candles_1h,
    ) is None
    already_above = candles[-2].model_copy(
        update={
            "open": armed.breakout_boundary + Decimal("0.1"),
            "low": armed.breakout_boundary,
            "close": armed.breakout_boundary + Decimal("0.2"),
        }
    )
    assert evaluate_rsr_vcb_trigger(
        armed=armed,
        candles_15m=(*candles[:-2], already_above, candles[-1]),
        candles_1h=candles_1h,
    ) is None


def _compressed_hour_candles() -> tuple[ClosedCandle, ...]:
    duration_ms = 3_600_000
    start_ms = 1_700_000_000_000
    candles = []
    for index in range(260):
        base = Decimal("100") + Decimal(index) * Decimal("0.2")
        oscillation = (
            Decimal("4") if index % 2 == 0 else Decimal("-4")
        )
        close = (
            base + oscillation
            if index < 240
            else Decimal("152") + Decimal(index - 240) * Decimal("0.02")
        )
        candles.append(
            ClosedCandle(
                open_time_ms=start_ms + index * duration_ms,
                close_time_ms=start_ms + (index + 1) * duration_ms,
                open=close - Decimal("0.05"),
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=Decimal("10"),
                quote_volume=Decimal("100"),
            )
        )
    return tuple(candles)


def _trigger_candles(
    *,
    armed_at_ms: int,
    boundary: Decimal,
) -> tuple[ClosedCandle, ...]:
    duration_ms = 900_000
    start_ms = armed_at_ms - 21 * duration_ms
    candles = []
    for index in range(22):
        if index == 21:
            open_price = boundary - Decimal("0.2")
            close_price = boundary + Decimal("1")
            quote_volume = Decimal("200")
        else:
            open_price = boundary - Decimal("0.6")
            close_price = boundary - Decimal("0.4")
            quote_volume = Decimal("100")
        candles.append(
            ClosedCandle(
                open_time_ms=start_ms + index * duration_ms,
                close_time_ms=start_ms + (index + 1) * duration_ms,
                open=open_price,
                high=max(open_price, close_price) + Decimal("0.2"),
                low=min(open_price, close_price) - Decimal("0.2"),
                close=close_price,
                volume=Decimal("10"),
                quote_volume=quote_volume,
            )
        )
    return tuple(candles)
