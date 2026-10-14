"""Independent hourly Session ORB; preparation never claims a future cross."""

from __future__ import annotations

from pydantic import JsonValue

from src.trading_kernel.domain.detector import (
    DetectorResult,
    computed_result,
    fact_snapshot,
    invalid_result,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.orb_session_selection import ORB_EVENT_SPEC_IDS
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract

H = 3_600_000
DAY = 24 * H


class SorHourlyDetector:
    def __init__(self, contract: RegisteredStrategyContract) -> None:
        if (
            contract.event_spec_id not in ORB_EVENT_SPEC_IDS
            or contract.strategy_group_id != "SOR-1H-001"
            or contract.timeframe != "1h"
        ):
            raise ValueError("hourly ORB Detector rejects another strategy or clock")
        self._contract = contract
        self.event_spec_id = contract.event_spec_id

    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult:
        c = self._contract
        now = snapshot.trigger_candle_close_time_ms
        d = now // DAY * DAY
        bars = snapshot.candles_1h
        if (
            now % H
            or not bars
            or not d + H <= now < d + DAY
            or len(bars) != (now - d) // H
            or any(
                b.open_time_ms != d + i * H or b.close_time_ms != d + (i + 1) * H
                for i, b in enumerate(bars)
            )
        ):
            return invalid_result(c, "sor_1h_invalid_session_path")
        high, low = bars[0].high, bars[0].low
        if high <= low:
            return invalid_result(c, "sor_1h_invalid_opening_range")
        eligible = len(bars) >= 2
        long = c.position_side == "long"
        crossed = eligible and (
            (bars[-2].close <= high and bars[-1].close > high)
            if long
            else (bars[-2].close >= low and bars[-1].close < low)
        )
        values: tuple[tuple[str, JsonValue, bool], ...] = (
            ("opening_range_defined_1h_v1", True, True),
            ("entry_hour_eligible_1h_v1", eligible, eligible),
            (
                ("breakout" if long else "breakdown") + "_edge_crossed_1h_v1",
                crossed,
                crossed,
            ),
            (
                "opening_range_" + ("low" if long else "high") + "_reference_1h_v1",
                str(low if long else high),
                True,
            ),
            (
                "opening_range_" + ("high" if long else "low") + "_reference_1h_v1",
                str(high if long else low),
                True,
            ),
            ("session_start_ms_1h_v1", str(d), True),
            ("session_end_ms_1h_v1", str(d + DAY), True),
        )
        facts = tuple(
            fact_snapshot(c, snapshot, fact_name=name, value=value, satisfied=satisfied)
            for name, value, satisfied in values
        )
        return computed_result(
            c,
            snapshot,
            triggered=crossed,
            facts=facts,
            reason_code="sor_1h_" + ("breakout" if long else "breakdown")
            if crossed
            else "sor_1h_opening_range_prepared"
            if not eligible
            else "sor_1h_no_hourly_cross",
        )
