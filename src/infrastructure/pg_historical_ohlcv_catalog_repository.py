"""PG-backed historical OHLCV catalog and bar access for BRC research."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.historical_ohlcv import HistoricalOhlcvBar, HistoricalOhlcvDatasetMetadata
from src.domain.models import KlineData
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGBrcHistoricalOhlcvDatasetORM, PGKlineORM


class PgHistoricalOhlcvCatalogRepository:
    """Metadata catalog plus minimal historical OHLCV bar queries.

    Bar storage reuses the existing PG `klines` table instead of introducing a
    parallel BRC bars table.
    """

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def upsert_dataset_metadata(
        self,
        metadata: HistoricalOhlcvDatasetMetadata,
    ) -> HistoricalOhlcvDatasetMetadata:
        payload = metadata.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalOhlcvDatasetORM,
                    metadata.dataset_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalOhlcvDatasetORM(dataset_id=metadata.dataset_id)
                    session.add(row)
                self._apply_dataset_payload(row, payload)
                await session.flush()
                return self._to_dataset_metadata(row)

    async def get_dataset_metadata(
        self,
        dataset_id: str,
    ) -> Optional[HistoricalOhlcvDatasetMetadata]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcHistoricalOhlcvDatasetORM, dataset_id)
            return self._to_dataset_metadata(row) if row is not None else None

    async def list_datasets(
        self,
        *,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> list[HistoricalOhlcvDatasetMetadata]:
        conditions = []
        if symbol is not None:
            conditions.append(PGBrcHistoricalOhlcvDatasetORM.symbol == symbol)
        if timeframe is not None:
            conditions.append(PGBrcHistoricalOhlcvDatasetORM.timeframe == timeframe)
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcHistoricalOhlcvDatasetORM)
                .where(*conditions)
                .order_by(
                    PGBrcHistoricalOhlcvDatasetORM.symbol.asc(),
                    PGBrcHistoricalOhlcvDatasetORM.timeframe.asc(),
                    PGBrcHistoricalOhlcvDatasetORM.start_time_ms.asc(),
                )
            )
            return [self._to_dataset_metadata(row) for row in result.scalars().all()]

    async def upsert_bars(self, bars: list[HistoricalOhlcvBar]) -> int:
        inserted = 0
        async with self._session_maker() as session:
            async with session.begin():
                for bar in bars:
                    exists = await session.execute(
                        select(PGKlineORM.id)
                        .where(
                            PGKlineORM.symbol == bar.symbol,
                            PGKlineORM.timeframe == bar.timeframe,
                            PGKlineORM.timestamp == bar.open_time_ms,
                        )
                        .limit(1)
                    )
                    if exists.scalar_one_or_none() is not None:
                        continue
                    row = PGKlineORM(
                        symbol=bar.symbol,
                        timeframe=bar.timeframe,
                        timestamp=bar.open_time_ms,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        is_closed=True,
                        created_at=bar.created_at_ms,
                    )
                    session.add(row)
                    inserted += 1
                await session.flush()
        return inserted

    async def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 5000,
    ) -> list[HistoricalOhlcvBar]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGKlineORM)
                .where(
                    PGKlineORM.symbol == symbol,
                    PGKlineORM.timeframe == timeframe,
                    PGKlineORM.timestamp >= start_time_ms,
                    PGKlineORM.timestamp <= end_time_ms,
                )
                .order_by(PGKlineORM.timestamp.asc())
                .limit(limit)
            )
            return [self._to_bar(row) for row in result.scalars().all()]

    async def fetch_recent_bars_ending_at(
        self,
        *,
        symbol: str,
        timeframe: str,
        timestamp_ms: int,
        limit: int,
    ) -> list[HistoricalOhlcvBar]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGKlineORM)
                .where(
                    PGKlineORM.symbol == symbol,
                    PGKlineORM.timeframe == timeframe,
                    PGKlineORM.timestamp <= timestamp_ms,
                )
                .order_by(PGKlineORM.timestamp.desc())
                .limit(limit)
            )
            rows = list(result.scalars().all())
            rows.reverse()
            return [self._to_bar(row) for row in rows]

    async def fetch_klines(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 5000,
    ) -> list[KlineData]:
        bars = await self.fetch_bars(
            symbol=symbol,
            timeframe=timeframe,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
            limit=limit,
        )
        return [self._bar_to_kline(bar) for bar in bars]

    @staticmethod
    def _apply_dataset_payload(row: PGBrcHistoricalOhlcvDatasetORM, payload: dict) -> None:
        row.source = payload["source"]
        row.market = payload["market"]
        row.symbol = payload["symbol"]
        row.timeframe = payload["timeframe"]
        row.start_time_ms = payload["start_time_ms"]
        row.end_time_ms = payload["end_time_ms"]
        row.row_count = payload["row_count"]
        row.storage_kind = payload["storage_kind"]
        row.storage_ref = payload["storage_ref"]
        row.timezone = payload["timezone"]
        row.data_quality_status = payload["data_quality_status"]
        row.missing_intervals_json = list(payload["missing_intervals"])
        row.created_at_ms = payload["created_at_ms"]
        row.updated_at_ms = payload["updated_at_ms"]
        row.notes = payload["notes"]

    @staticmethod
    def _to_dataset_metadata(row: PGBrcHistoricalOhlcvDatasetORM) -> HistoricalOhlcvDatasetMetadata:
        return HistoricalOhlcvDatasetMetadata(
            dataset_id=row.dataset_id,
            source=row.source,
            market=row.market,
            symbol=row.symbol,
            timeframe=row.timeframe,
            start_time_ms=row.start_time_ms,
            end_time_ms=row.end_time_ms,
            row_count=row.row_count,
            storage_kind=row.storage_kind,
            storage_ref=row.storage_ref,
            timezone=row.timezone,
            data_quality_status=row.data_quality_status,
            missing_intervals=list(row.missing_intervals_json or []),
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            notes=row.notes,
        )

    @staticmethod
    def _to_bar(row: PGKlineORM) -> HistoricalOhlcvBar:
        return HistoricalOhlcvBar(
            source="pg_klines",
            market="historical",
            symbol=row.symbol,
            timeframe=row.timeframe,
            open_time_ms=row.timestamp,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            quote_volume=None,
            close_time_ms=None,
            created_at_ms=row.created_at,
        )

    @staticmethod
    def _bar_to_kline(bar: HistoricalOhlcvBar) -> KlineData:
        return KlineData(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            timestamp=bar.open_time_ms,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            is_closed=True,
        )
