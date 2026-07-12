from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from src.infrastructure.binance_usdm_historical_candle_source import (
    BinanceUsdMPublicHistoricalCandleSource,
)


def _row(open_ms: int) -> list[object]:
    return [
        open_ms,
        "100",
        "101",
        "99",
        "100.5",
        "1234",
        open_ms + 3_599_999,
        "0",
        1,
        "0",
        "0",
        "0",
    ]


def test_public_source_paginates_deduplicates_and_keeps_only_closed_rows() -> None:
    calls: list[dict[str, list[str]]] = []

    def requester(url: str, timeout_seconds: float):
        assert timeout_seconds == 7
        query = parse_qs(urlparse(url).query)
        calls.append(query)
        start = int(query["startTime"][0])
        if len(calls) == 1:
            return [_row(start), _row(start + 3_600_000)]
        if len(calls) == 2:
            return [_row(start), _row(start + 3_600_000)]
        return []

    source = BinanceUsdMPublicHistoricalCandleSource(
        timeout_seconds=7,
        page_limit=2,
        requester=requester,
    )
    rows = source.fetch_closed_candles(
        symbol="BTCUSDT",
        timeframe="1h",
        start_time_ms=1_000,
        end_time_ms=10_801_000,
    )

    assert [item["open_time_ms"] for item in rows] == [
        1_000,
        3_601_000,
        7_201_000,
    ]
    assert all(int(item["close_time_ms"]) <= 10_801_000 for item in rows)
    assert calls[0]["symbol"] == ["BTCUSDT"]
    assert calls[0]["interval"] == ["1h"]
    assert calls[1]["startTime"] == ["7201000"]


def test_public_source_rejects_unsupported_timeframe_before_network() -> None:
    called = False

    def requester(url: str, timeout_seconds: float):
        nonlocal called
        called = True
        return []

    source = BinanceUsdMPublicHistoricalCandleSource(requester=requester)

    try:
        source.fetch_closed_candles(
            symbol="BTCUSDT",
            timeframe="2h",
            start_time_ms=1,
            end_time_ms=2,
        )
    except ValueError as exc:
        assert str(exc) == "unsupported_binance_timeframe:2h"
    else:
        raise AssertionError("unsupported timeframe must fail")
    assert called is False


def test_public_source_stops_before_next_cursor_would_exceed_end_time() -> None:
    calls = 0

    def requester(url: str, timeout_seconds: float):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("requester must not receive startTime greater than endTime")
        query = parse_qs(urlparse(url).query)
        start = int(query["startTime"][0])
        return [_row(start), _row(start + 3_600_000)]

    source = BinanceUsdMPublicHistoricalCandleSource(
        page_limit=2,
        requester=requester,
    )
    rows = source.fetch_closed_candles(
        symbol="BTCUSDT",
        timeframe="1h",
        start_time_ms=1_000,
        end_time_ms=7_200_500,
    )

    assert calls == 1
    assert [item["open_time_ms"] for item in rows] == [1_000]
