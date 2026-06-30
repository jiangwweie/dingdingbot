"""Read-only local SQLite closed-candle source for strategy group observation."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

from src.application.strategy_group_live_readonly_observation import (
    LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE,
    RecentCandle,
)


_SAMPLE_FALLBACK_SYMBOLS = {
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "ETH/USDT:USDT",
    "BTC/USDT:USDT",
    "AVAX/USDT:USDT",
    "XRP/USDT:USDT",
    "ADA/USDT:USDT",
    "LINK/USDT:USDT",
}


class _LocalSqliteObservationDataUnavailable(RuntimeError):
    """Local read-only observation data is absent or insufficient."""


class LocalSqliteObservationMarketSource:
    """Read closed candles from the local research SQLite database.

    The source opens SQLite in read-only mode and does not call exchange APIs,
    runtime services, order repositories, or execution paths.
    """

    source_id = "local_sqlite_v3_dev_closed_klines_read_only"
    source_type = LOCAL_SQLITE_READ_ONLY_SOURCE_TYPE

    def __init__(self, db_path: str | Path = "data/v3_dev.db") -> None:
        self._db_path = Path(db_path)
        self.fallback_used = False

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        if limit <= 0:
            return []
        try:
            if timeframe == "4h":
                return self._latest_4h_from_1h(symbol=symbol, limit=limit)
            return self._latest_from_db(symbol=symbol, timeframe=timeframe, limit=limit)
        except (FileNotFoundError, _LocalSqliteObservationDataUnavailable):
            fallback = self._sample_fallback(symbol=symbol, timeframe=timeframe, limit=limit)
            if fallback:
                self.fallback_used = True
                return fallback
            raise

    def _latest_from_db(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        if not self._db_path.exists():
            raise FileNotFoundError(f"local SQLite market database not found: {self._db_path}")
        uri = f"file:{self._db_path.resolve()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM klines
                WHERE symbol = ? AND timeframe = ? AND is_closed = 1
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (symbol, timeframe, limit),
            ).fetchall()
        candles = [
            RecentCandle(
                open_time_ms=int(row[0]),
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
            for row in reversed(rows)
        ]
        if len(candles) < limit:
            raise _LocalSqliteObservationDataUnavailable(
                f"insufficient closed candles for {symbol} {timeframe}: {len(candles)} < {limit}"
            )
        return candles

    def _latest_4h_from_1h(self, *, symbol: str, limit: int) -> list[RecentCandle]:
        one_hour = self._latest_from_db(symbol=symbol, timeframe="1h", limit=limit * 4)
        buckets: list[list[RecentCandle]] = []
        for index in range(0, len(one_hour), 4):
            bucket = one_hour[index : index + 4]
            if len(bucket) == 4:
                buckets.append(bucket)
        return [
            RecentCandle(
                open_time_ms=bucket[0].open_time_ms,
                open=bucket[0].open,
                high=max(item.high for item in bucket),
                low=min(item.low for item in bucket),
                close=bucket[-1].close,
                volume=sum((item.volume for item in bucket), Decimal("0")),
            )
            for bucket in buckets[-limit:]
        ]

    def _sample_fallback(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        if symbol not in _SAMPLE_FALLBACK_SYMBOLS:
            return []
        from src.application.strategy_group_live_readonly_observation import (
            SampleStrategyGroupMarketBarSource,
        )

        return SampleStrategyGroupMarketBarSource().latest_closed_candles(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
