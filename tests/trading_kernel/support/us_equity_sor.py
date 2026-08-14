from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.product import ProductSessionSnapshot

BAR_MS = 900_000
REGULAR_OPEN_MS = 1_800_000_000_000
REGULAR_CLOSE_MS = REGULAR_OPEN_MS + 23_400_000
AAPL = "binance-usdm:AAPLUSDT:perpetual"


def make_us_equity_sor_candle(
    index: int,
    *,
    close: str,
    open_: str = "100",
    high: str = "101",
    low: str = "99",
) -> ClosedCandle:
    open_time_ms = REGULAR_OPEN_MS - 12 * BAR_MS + index * BAR_MS
    return ClosedCandle(
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + BAR_MS,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(1000),
    )


def make_us_equity_sor_snapshot(
    *,
    side: str,
    session_state: str = "regular",
    valid_until_ms: int | None = None,
    wide_stop: bool = False,
) -> MarketSnapshot:
    premarket = tuple(
        make_us_equity_sor_candle(index, close="100") for index in range(12)
    )
    opening = (
        make_us_equity_sor_candle(12, close="100", high="102", low="99"),
        make_us_equity_sor_candle(13, close="101", high="103", low="100"),
    )
    if side == "long":
        trigger = make_us_equity_sor_candle(
            14,
            close="104",
            open_="103",
            high="105",
            low="95" if wide_stop else "102",
        )
    else:
        trigger = make_us_equity_sor_candle(
            14,
            close="98",
            open_="99",
            high="106" if wide_stop else "100",
            low="97",
        )
    trigger_ms = trigger.close_time_ms
    return MarketSnapshot(
        exchange_instrument_id=AAPL,
        trigger_candle_close_time_ms=trigger_ms,
        candles_15m=(*premarket, *opening, trigger),
        product_session=ProductSessionSnapshot(
            exchange_instrument_id=AAPL,
            product_family="tradfi_equity_perpetual",
            product_status="active",
            session_state=session_state,
            regular_session_open_ms=REGULAR_OPEN_MS,
            regular_session_close_ms=REGULAR_CLOSE_MS,
            observed_at_ms=trigger_ms - 1,
            valid_until_ms=(
                trigger_ms + BAR_MS if valid_until_ms is None else valid_until_ms
            ),
            source_ref="binance:tradingSchedule:test",
        ),
    )
