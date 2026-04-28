"""PostgreSQL historical kline repository."""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import KlineData
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.logger import logger
from src.infrastructure.pg_models import PGKlineORM


class PgHistoricalDataRepository:
    """PostgreSQL implementation of the historical kline cache."""

    TIMEFRAME_MINUTES = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
        "1d": 1440, "1w": 10080,
    }

    def __init__(
        self,
        exchange_gateway: Optional[ExchangeGateway] = None,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._gateway = exchange_gateway
        self._session_maker = session_maker or get_pg_session_maker()
        self._semaphore = asyncio.Semaphore(5)

    async def initialize(self) -> None:
        await init_pg_core_db()
        logger.info("PgHistoricalDataRepository initialized")

    async def close(self) -> None:
        return None

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[KlineData]:
        async with self._semaphore:
            async with self._session_maker() as session:
                klines = await self._query_klines_from_db(
                    session, symbol, timeframe, start_time, end_time, limit
                )

            need_fallback = (
                self._gateway is not None
                and (
                    len(klines) == 0
                    or (start_time and end_time and len(klines) < limit)
                    or (not start_time and not end_time and len(klines) < limit)
                )
            )
            if need_fallback:
                fetched = await self._fetch_from_exchange(symbol, timeframe, start_time, end_time, limit)
                if fetched:
                    klines = fetched

            klines.sort(key=lambda item: item.timestamp)
            return klines[:limit]

    async def _query_klines_from_db(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        start_time: Optional[int],
        end_time: Optional[int],
        limit: int,
    ) -> List[KlineData]:
        conditions = [PGKlineORM.symbol == symbol, PGKlineORM.timeframe == timeframe]
        if start_time:
            conditions.append(PGKlineORM.timestamp >= start_time)
        if end_time:
            conditions.append(PGKlineORM.timestamp <= end_time)
        stmt = (
            select(PGKlineORM)
            .where(*conditions)
            .order_by(PGKlineORM.timestamp.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        klines = [self._orm_to_domain(row) for row in rows]
        klines.reverse()
        return klines

    async def _fetch_from_exchange(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int],
        end_time: Optional[int],
        limit: int,
    ) -> List[KlineData]:
        if self._gateway is None:
            logger.warning("No exchange gateway configured, cannot fetch from exchange")
            return []
        klines = await self._gateway.fetch_historical_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=start_time,
        )
        if start_time and end_time:
            klines = [k for k in klines if start_time <= k.timestamp <= end_time]
        elif start_time:
            klines = [k for k in klines if k.timestamp >= start_time]
        elif end_time:
            klines = [k for k in klines if k.timestamp <= end_time]
        if klines:
            await self._save_klines(klines)
        return klines

    async def _save_klines(self, klines: List[KlineData]) -> None:
        if not klines:
            return
        async with self._session_maker() as session:
            for kline in klines:
                stmt = (
                    pg_insert(PGKlineORM)
                    .values(
                        symbol=kline.symbol,
                        timeframe=kline.timeframe,
                        timestamp=kline.timestamp,
                        open=kline.open,
                        high=kline.high,
                        low=kline.low,
                        close=kline.close,
                        volume=kline.volume,
                        is_closed=kline.is_closed,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            PGKlineORM.symbol,
                            PGKlineORM.timeframe,
                            PGKlineORM.timestamp,
                        ]
                    )
                )
                await session.execute(stmt)
            await session.commit()

    async def get_klines_aligned(
        self,
        symbol: str,
        main_tf: str,
        higher_tf: str,
        start_time: int,
        end_time: int,
    ) -> Tuple[List[KlineData], Dict[int, KlineData]]:
        main_klines, higher_klines = await asyncio.gather(
            self.get_klines(symbol, main_tf, start_time, end_time, limit=5000),
            self.get_klines(symbol, higher_tf, start_time, end_time, limit=5000),
        )
        higher_map = {k.timestamp: k for k in higher_klines}
        aligned = {}
        for main_k in main_klines:
            for higher_ts in sorted(higher_map.keys(), reverse=True):
                if higher_ts <= main_k.timestamp:
                    aligned[main_k.timestamp] = higher_map[higher_ts]
                    break
        return main_klines, aligned

    def _orm_to_domain(self, orm: PGKlineORM) -> KlineData:
        return KlineData(
            symbol=orm.symbol,
            timeframe=orm.timeframe,
            timestamp=orm.timestamp,
            open=orm.open,
            high=orm.high,
            low=orm.low,
            close=orm.close,
            volume=orm.volume,
            is_closed=orm.is_closed,
        )

    async def get_kline_range(self, symbol: str, timeframe: str) -> Tuple[Optional[int], Optional[int]]:
        async with self._session_maker() as session:
            row = (await session.execute(
                select(func.min(PGKlineORM.timestamp), func.max(PGKlineORM.timestamp))
                .where(PGKlineORM.symbol == symbol, PGKlineORM.timeframe == timeframe)
            )).first()
            return (row[0], row[1]) if row else (None, None)

    async def count_klines(self, symbol: str, timeframe: str) -> int:
        async with self._session_maker() as session:
            return int((await session.execute(
                select(func.count()).select_from(PGKlineORM)
                .where(PGKlineORM.symbol == symbol, PGKlineORM.timeframe == timeframe)
            )).scalar_one() or 0)
