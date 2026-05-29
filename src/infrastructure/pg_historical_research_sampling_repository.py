"""PG repository for historical research sampling runs."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.historical_research_sampling import (
    HistoricalResearchSamplingPoint,
    HistoricalResearchSamplingRun,
    HistoricalResearchSamplingStatus,
    HistoricalResearchSamplingSummary,
    compute_sampling_summary,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcHistoricalResearchSamplingPointORM,
    PGBrcHistoricalResearchSamplingRunORM,
)


class PgHistoricalResearchSamplingRepository:
    """Persistence for compact historical sampling coverage metadata."""

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

    async def create_sampling_run(
        self,
        run: HistoricalResearchSamplingRun,
    ) -> HistoricalResearchSamplingRun:
        payload = run.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalResearchSamplingRunORM,
                    run.run_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalResearchSamplingRunORM(run_id=run.run_id)
                    session.add(row)
                self._apply_run_payload(row, payload)
                await session.flush()
                return self._to_run(row)

    async def record_sampling_point(
        self,
        point: HistoricalResearchSamplingPoint,
    ) -> HistoricalResearchSamplingPoint:
        payload = point.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalResearchSamplingPointORM,
                    point.point_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalResearchSamplingPointORM(point_id=point.point_id)
                    session.add(row)
                self._apply_point_payload(row, payload)
                await session.flush()
                return self._to_point(row)

    async def complete_sampling_run(
        self,
        *,
        run_id: str,
        summary: HistoricalResearchSamplingSummary,
        updated_at_ms: int,
        status: HistoricalResearchSamplingStatus = HistoricalResearchSamplingStatus.COMPLETED,
    ) -> HistoricalResearchSamplingRun:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalResearchSamplingRunORM,
                    run_id,
                    with_for_update=True,
                )
                if row is None:
                    raise ValueError(f"sampling run not found: {run_id}")
                row.status = status.value
                row.summary_json = summary.model_dump(mode="json")
                row.updated_at_ms = updated_at_ms
                await session.flush()
                return self._to_run(row)

    async def get_sampling_run(self, run_id: str) -> Optional[HistoricalResearchSamplingRun]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcHistoricalResearchSamplingRunORM, run_id)
            return self._to_run(row) if row is not None else None

    async def list_sampling_runs(self, *, limit: int = 100) -> list[HistoricalResearchSamplingRun]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcHistoricalResearchSamplingRunORM)
                .order_by(PGBrcHistoricalResearchSamplingRunORM.created_at_ms.desc())
                .limit(limit)
            )
            return [self._to_run(row) for row in result.scalars().all()]

    async def list_sampling_points(self, run_id: str) -> list[HistoricalResearchSamplingPoint]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcHistoricalResearchSamplingPointORM)
                .where(PGBrcHistoricalResearchSamplingPointORM.run_id == run_id)
                .order_by(
                    PGBrcHistoricalResearchSamplingPointORM.symbol.asc(),
                    PGBrcHistoricalResearchSamplingPointORM.timestamp_ms.asc(),
                )
            )
            return [self._to_point(row) for row in result.scalars().all()]

    async def get_sampling_summary(self, run_id: str) -> Optional[HistoricalResearchSamplingSummary]:
        run = await self.get_sampling_run(run_id)
        if run is None:
            return None
        if run.summary_json:
            return HistoricalResearchSamplingSummary.model_validate(run.summary_json)
        points = await self.list_sampling_points(run_id)
        return compute_sampling_summary(run_id=run_id, points=points)

    @staticmethod
    def _apply_run_payload(row: PGBrcHistoricalResearchSamplingRunORM, payload: dict) -> None:
        row.strategy_family_id = payload["strategy_family_id"]
        row.strategy_family_version_id = payload["strategy_family_version_id"]
        row.playbook_id = payload.get("playbook_id")
        row.dataset_ids_json = list(payload["dataset_ids"])
        row.symbols_json = list(payload["symbols"])
        row.primary_timeframe = payload["primary_timeframe"]
        row.context_timeframes_json = list(payload["context_timeframes"])
        row.start_time_ms = payload["start_time_ms"]
        row.end_time_ms = payload["end_time_ms"]
        row.sampling_method = payload["sampling_method"]
        row.sampling_interval_bars = payload["sampling_interval_bars"]
        row.sample_limit = payload["sample_limit"]
        row.status = payload["status"]
        row.summary_json = dict(payload["summary_json"])
        row.created_at_ms = payload["created_at_ms"]
        row.updated_at_ms = payload["updated_at_ms"]
        row.notes = payload["notes"]

    @staticmethod
    def _apply_point_payload(row: PGBrcHistoricalResearchSamplingPointORM, payload: dict) -> None:
        row.run_id = payload["run_id"]
        row.symbol = payload["symbol"]
        row.timestamp_ms = payload["timestamp_ms"]
        row.primary_timeframe = payload["primary_timeframe"]
        row.context_timeframes_json = list(payload["context_timeframes"])
        row.point_status = payload["point_status"]
        row.market_snapshot_status = payload["market_snapshot_status"]
        row.signal_input_status = payload["signal_input_status"]
        row.data_quality_status = payload["data_quality_status"]
        row.missing_fields_json = list(payload["missing_fields"])
        row.stale_fields_json = list(payload["stale_fields"])
        row.warnings_json = list(payload["warnings"])
        row.atr_available = payload["atr_available"]
        row.candle_context_available = payload["candle_context_available"]
        row.input_contract_valid = payload["input_contract_valid"]
        row.failure_reason = payload.get("failure_reason")
        row.created_at_ms = payload["created_at_ms"]

    @staticmethod
    def _to_run(row: PGBrcHistoricalResearchSamplingRunORM) -> HistoricalResearchSamplingRun:
        return HistoricalResearchSamplingRun(
            run_id=row.run_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            playbook_id=row.playbook_id,
            dataset_ids=list(row.dataset_ids_json or []),
            symbols=list(row.symbols_json or []),
            primary_timeframe=row.primary_timeframe,
            context_timeframes=list(row.context_timeframes_json or []),
            start_time_ms=row.start_time_ms,
            end_time_ms=row.end_time_ms,
            sampling_method=row.sampling_method,
            sampling_interval_bars=row.sampling_interval_bars,
            sample_limit=row.sample_limit,
            status=row.status,
            summary_json=dict(row.summary_json or {}),
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            notes=row.notes,
        )

    @staticmethod
    def _to_point(row: PGBrcHistoricalResearchSamplingPointORM) -> HistoricalResearchSamplingPoint:
        return HistoricalResearchSamplingPoint(
            point_id=row.point_id,
            run_id=row.run_id,
            symbol=row.symbol,
            timestamp_ms=row.timestamp_ms,
            primary_timeframe=row.primary_timeframe,
            context_timeframes=list(row.context_timeframes_json or []),
            point_status=row.point_status,
            market_snapshot_status=row.market_snapshot_status,
            signal_input_status=row.signal_input_status,
            data_quality_status=row.data_quality_status,
            missing_fields=list(row.missing_fields_json or []),
            stale_fields=list(row.stale_fields_json or []),
            warnings=list(row.warnings_json or []),
            atr_available=row.atr_available,
            candle_context_available=row.candle_context_available,
            input_contract_valid=row.input_contract_valid,
            failure_reason=row.failure_reason,
            created_at_ms=row.created_at_ms,
        )
