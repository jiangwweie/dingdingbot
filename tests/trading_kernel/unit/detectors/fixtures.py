from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.market import (
    ClosedCandle,
    ComparativeStrengthMember,
    ComparativeStrengthSnapshot,
    MarketSnapshot,
)


NOW_MS = 1_800_000_000_000
BTC = "binance-usdm:BTCUSDT:perpetual"
ETH = "binance-usdm:ETHUSDT:perpetual"
SOL = "binance-usdm:SOLUSDT:perpetual"
AVAX = "binance-usdm:AVAXUSDT:perpetual"
OP = "binance-usdm:OPUSDT:perpetual"
SUI = "binance-usdm:SUIUSDT:perpetual"


def cpm_long_snapshot() -> MarketSnapshot:
    one_hour: list[ClosedCandle] = []
    for index in range(20):
        close = Decimal("100") + Decimal(index) * Decimal("0.2")
        one_hour.append(
            _candle(
                index=index,
                count=21,
                duration_ms=3_600_000,
                open_=close,
                high=close + Decimal("0.2"),
                low=close - Decimal("0.2"),
                close=close,
            )
        )
    one_hour.append(
        _candle(
            index=20,
            count=21,
            duration_ms=3_600_000,
            open_=Decimal("103.5"),
            high=Decimal("105.2"),
            low=Decimal("102"),
            close=Decimal("105"),
        )
    )
    return snapshot(candles_1h=tuple(one_hour), candles_4h=_up_context_4h())


def cpm_flat_snapshot() -> MarketSnapshot:
    return snapshot(
        candles_1h=_flat_candles(21, 3_600_000),
        candles_4h=_flat_candles(21, 14_400_000),
    )


def mpg_long_snapshot(
    *,
    candidate_rank: int = 1,
    candidate_return_pct: Decimal = Decimal("8"),
    comparative_valid_until_ms: int = NOW_MS + 3_600_000,
) -> MarketSnapshot:
    one_hour: list[ClosedCandle] = []
    for index in range(16):
        close = Decimal("100") + Decimal(index) * Decimal("0.35")
        one_hour.append(
            _candle(
                index=index,
                count=17,
                duration_ms=3_600_000,
                open_=close,
                high=close + Decimal("0.3"),
                low=close - Decimal("0.3"),
                close=close,
            )
        )
    one_hour.append(
        _candle(
            index=16,
            count=17,
            duration_ms=3_600_000,
            open_=Decimal("105.4"),
            high=Decimal("107.2"),
            low=Decimal("105"),
            close=Decimal("107"),
        )
    )
    peer_rank = 2 if candidate_rank == 1 else 1
    comparative = ComparativeStrengthSnapshot(
        strategy_group_id="MPG-001",
        timeframe="1h",
        lookback_bars=8,
        trigger_candle_close_time_ms=NOW_MS,
        members=(
            ComparativeStrengthMember(
                exchange_instrument_id=SOL,
                return_pct=candidate_return_pct,
                rank=candidate_rank,
            ),
            ComparativeStrengthMember(
                exchange_instrument_id=ETH,
                return_pct=Decimal("6"),
                rank=peer_rank,
            ),
        ),
        observed_at_ms=NOW_MS,
        valid_until_ms=comparative_valid_until_ms,
        source_ref="pg:comparative:mpg:test",
    )
    return snapshot(
        exchange_instrument_id=SOL,
        candles_1h=tuple(one_hour),
        candles_4h=_up_context_4h(),
        comparative_strength=comparative,
    )


def mpg_flat_snapshot() -> MarketSnapshot:
    return snapshot(
        exchange_instrument_id=SOL,
        candles_1h=_flat_candles(17, 3_600_000),
        candles_4h=_up_context_4h(),
    )


def mi_long_snapshot(
    *,
    candidate_rank: int = 1,
    candidate_return_pct: Decimal | None = None,
) -> MarketSnapshot:
    candles: list[ClosedCandle] = []
    for index in range(14):
        close = Decimal("100") + Decimal(index) * Decimal("0.45")
        candles.append(
            _candle(
                index=index,
                count=14,
                duration_ms=3_600_000,
                open_=close,
                high=close + Decimal("0.4"),
                low=close - Decimal("0.3"),
                close=close,
            )
        )
    start = candles[-13].close
    end = candles[-1].close
    actual_return = ((end - start) / start) * Decimal("100")
    peer_rank = 2 if candidate_rank == 1 else 1
    comparative = ComparativeStrengthSnapshot(
        strategy_group_id="MI-001",
        timeframe="1h",
        lookback_bars=12,
        trigger_candle_close_time_ms=NOW_MS,
        members=(
            ComparativeStrengthMember(
                exchange_instrument_id=ETH,
                return_pct=(
                    actual_return
                    if candidate_return_pct is None
                    else candidate_return_pct
                ),
                rank=candidate_rank,
            ),
            ComparativeStrengthMember(
                exchange_instrument_id=SOL,
                return_pct=Decimal("2"),
                rank=peer_rank,
            ),
        ),
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 3_600_000,
        source_ref="pg:comparative:mi:test",
    )
    return snapshot(candles_1h=tuple(candles), comparative_strength=comparative)


def mi_flat_snapshot() -> MarketSnapshot:
    return snapshot(candles_1h=_flat_candles(14, 3_600_000))


def sor_snapshot(*, side: str | None) -> MarketSnapshot:
    opening = (
        _candle_values(0, 5, 900_000, "100", "101", "99", "100"),
        _candle_values(1, 5, 900_000, "100", "102", "99", "101"),
        _candle_values(2, 5, 900_000, "101", "102", "98", "100"),
        _candle_values(3, 5, 900_000, "100", "101", "98", "100"),
    )
    if side == "long":
        trigger = _candle_values(4, 5, 900_000, "101", "104", "100", "103")
    elif side == "short":
        trigger = _candle_values(4, 5, 900_000, "99", "100", "96", "97")
    else:
        trigger = _candle_values(4, 5, 900_000, "100", "101", "99", "100")
    return snapshot(candles_15m=(*opening, trigger))


def brf2_short_snapshot(*, strong_uptrend: bool = False) -> MarketSnapshot:
    one_hour = (
        _candle_values(0, 12, 3_600_000, "101", "102", "99", "100"),
        _candle_values(1, 12, 3_600_000, "100", "103", "99", "102"),
        _candle_values(2, 12, 3_600_000, "102", "105", "101", "104"),
        _candle_values(3, 12, 3_600_000, "104", "106", "103", "105"),
        _candle_values(4, 12, 3_600_000, "105", "108", "104", "107"),
        _candle_values(5, 12, 3_600_000, "107", "109", "106", "108"),
        _candle_values(6, 12, 3_600_000, "108", "110", "107", "109"),
        _candle_values(7, 12, 3_600_000, "109", "111", "108", "110"),
        _candle_values(8, 12, 3_600_000, "110", "112", "109", "111"),
        _candle_values(9, 12, 3_600_000, "111", "113", "110", "112"),
        _candle_values(10, 12, 3_600_000, "112", "113", "109", "111"),
        _candle_values(11, 12, 3_600_000, "111", "114", "105", "106"),
    )
    if strong_uptrend:
        four_hour = (
            _candle_values(0, 4, 14_400_000, "100", "102", "99", "100"),
            _candle_values(1, 4, 14_400_000, "101", "104", "100", "103"),
            _candle_values(2, 4, 14_400_000, "103", "106", "102", "105"),
            _candle_values(3, 4, 14_400_000, "105", "108", "104", "107"),
        )
    else:
        four_hour = (
            _candle_values(0, 4, 14_400_000, "122", "123", "119", "120"),
            _candle_values(1, 4, 14_400_000, "120", "121", "117", "118"),
            _candle_values(2, 4, 14_400_000, "118", "119", "115", "116"),
            _candle_values(3, 4, 14_400_000, "116", "117", "113", "114"),
        )
    return snapshot(candles_1h=one_hour, candles_4h=four_hour)


def snapshot(
    *,
    exchange_instrument_id: str = ETH,
    candles_15m: tuple[ClosedCandle, ...] = (),
    candles_1h: tuple[ClosedCandle, ...] = (),
    candles_4h: tuple[ClosedCandle, ...] = (),
    comparative_strength: ComparativeStrengthSnapshot | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        exchange_instrument_id=exchange_instrument_id,
        trigger_candle_close_time_ms=NOW_MS,
        candles_15m=candles_15m,
        candles_1h=candles_1h,
        candles_4h=candles_4h,
        comparative_strength=comparative_strength,
    )


def flat_candles(count: int, duration_ms: int) -> tuple[ClosedCandle, ...]:
    return _flat_candles(count, duration_ms)


def _up_context_4h() -> tuple[ClosedCandle, ...]:
    candles: list[ClosedCandle] = []
    for index in range(21):
        close = Decimal("100") + Decimal(index) * Decimal("0.3")
        candles.append(
            _candle(
                index=index,
                count=21,
                duration_ms=14_400_000,
                open_=close,
                high=close + Decimal("0.2"),
                low=close - Decimal("0.2"),
                close=close,
            )
        )
    return tuple(candles)


def _flat_candles(count: int, duration_ms: int) -> tuple[ClosedCandle, ...]:
    return tuple(
        _candle_values(index, count, duration_ms, "100", "101", "99", "100")
        for index in range(count)
    )


def _candle_values(
    index: int,
    count: int,
    duration_ms: int,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> ClosedCandle:
    return _candle(
        index=index,
        count=count,
        duration_ms=duration_ms,
        open_=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def _candle(
    *,
    index: int,
    count: int,
    duration_ms: int,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
) -> ClosedCandle:
    close_time_ms = NOW_MS - (count - index - 1) * duration_ms
    return ClosedCandle(
        open_time_ms=close_time_ms - duration_ms,
        close_time_ms=close_time_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=Decimal("100"),
    )
