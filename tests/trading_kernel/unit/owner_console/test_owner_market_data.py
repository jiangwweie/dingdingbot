from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_console.models import CandleQuery
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData


class FakeClosedCandleSource:
    def __init__(self, candles: tuple[object, ...]) -> None:
        self.candles = candles
        self.requests: list[object] = []
        self.close_calls = 0

    async def fetch_closed_candles(self, request: object) -> tuple[object, ...]:
        self.requests.append(request)
        return self.candles

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_owner_market_data_returns_closed_string_candles() -> None:
    source = FakeClosedCandleSource(
        candles=(
            closed_candle(
                open_time_ms=100,
                close_time_ms=200,
                close="101.2500",
            ),
        )
    )
    market = OwnerMarketData(source)

    series = await market.read_candles(
        CandleQuery(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            timeframe="15m",
            limit=300,
            closed_at_ms=200,
        )
    )

    assert series.candles[0].model_dump(mode="json") == {
        "open_time_ms": 100,
        "close_time_ms": 200,
        "open": "100.0000",
        "high": "102.0000",
        "low": "99.0000",
        "close": "101.2500",
        "volume": "10.0000",
    }
    assert source.requests[0].exchange_instrument_id == "binance-usdm:BTCUSDT:perpetual"
    assert source.requests[0].timeframe == "15m"
    assert source.requests[0].limit == 300
    assert source.requests[0].closed_at_ms == 200
    assert source.requests[0].since_ms is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"timeframe": "4h"}, "Input should be '15m' or '1h'"),
        ({"limit": 0}, "greater than or equal to 1"),
        ({"limit": 501}, "less than or equal to 500"),
        ({"closed_at_ms": 0}, "greater than 0"),
        ({"exchange_instrument_id": "   "}, "instrument must be non-blank"),
    ),
)
def test_candle_query_rejects_out_of_contract_bounds(
    kwargs: dict[str, object],
    message: str,
) -> None:
    values = {
        "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
        "timeframe": "15m",
        "closed_at_ms": 200,
    }
    values.update(kwargs)

    with pytest.raises(ValidationError, match=message):
        CandleQuery(**values)


def test_candle_query_defaults_to_300_rows() -> None:
    query = CandleQuery(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        timeframe="1h",
        closed_at_ms=200,
    )

    assert query.limit == 300


@pytest.mark.asyncio
async def test_owner_market_data_rejects_malformed_or_contradictory_candles() -> None:
    malformed_source = FakeClosedCandleSource(candles=(object(),))
    future_source = FakeClosedCandleSource(
        candles=(closed_candle(open_time_ms=100, close_time_ms=201),)
    )
    query = CandleQuery(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        timeframe="15m",
        closed_at_ms=200,
    )

    with pytest.raises(ValueError, match="malformed"):
        await OwnerMarketData(malformed_source).read_candles(query)
    with pytest.raises(ValueError, match="after requested closed_at_ms"):
        await OwnerMarketData(future_source).read_candles(query)


@pytest.mark.asyncio
async def test_owner_market_data_closes_the_public_source_once() -> None:
    source = FakeClosedCandleSource(candles=())
    market = OwnerMarketData(source)

    await market.close()
    await market.close()

    assert source.close_calls == 1


def closed_candle(
    *,
    open_time_ms: int,
    close_time_ms: int,
    close: str = "101.0000",
) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=Decimal("100.0000"),
        high=Decimal("102.0000"),
        low=Decimal("99.0000"),
        close=Decimal(close),
        volume=Decimal("10.0000"),
    )
