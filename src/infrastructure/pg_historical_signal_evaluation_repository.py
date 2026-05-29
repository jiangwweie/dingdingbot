"""PG repository for compact historical signal evaluation experiments."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.historical_signal_evaluation import (
    HistoricalForwardOutcome,
    HistoricalRegimeSplitComparisonReport,
    HistoricalSignalEvaluationOwnerReport,
    HistoricalSignalEvaluationRun,
    HistoricalSignalEvaluationStatus,
    HistoricalSignalEvaluationSummary,
    HistoricalSignalOutputRecord,
    compute_historical_signal_summary,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcHistoricalForwardOutcomeORM,
    PGBrcHistoricalRegimeSplitReportORM,
    PGBrcHistoricalSignalEvaluationRunORM,
    PGBrcHistoricalSignalOutputORM,
)


class PgHistoricalSignalEvaluationRepository:
    """Persistence for historical StrategyFamilySignalOutput review metadata."""

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

    async def create_evaluation_run(
        self,
        run: HistoricalSignalEvaluationRun,
    ) -> HistoricalSignalEvaluationRun:
        payload = run.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalSignalEvaluationRunORM,
                    run.run_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalSignalEvaluationRunORM(run_id=run.run_id)
                    session.add(row)
                self._apply_run_payload(row, payload)
                await session.flush()
                return self._to_run(row)

    async def record_signal_output(
        self,
        record: HistoricalSignalOutputRecord,
    ) -> HistoricalSignalOutputRecord:
        payload = record.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalSignalOutputORM,
                    record.signal_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalSignalOutputORM(signal_id=record.signal_id)
                    session.add(row)
                self._apply_signal_output_payload(row, payload)
                await session.flush()
                return self._to_signal_output(row)

    async def record_forward_outcome(
        self,
        outcome: HistoricalForwardOutcome,
    ) -> HistoricalForwardOutcome:
        payload = outcome.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalForwardOutcomeORM,
                    outcome.outcome_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalForwardOutcomeORM(outcome_id=outcome.outcome_id)
                    session.add(row)
                self._apply_forward_outcome_payload(row, payload)
                await session.flush()
                return self._to_forward_outcome(row)

    async def complete_evaluation_run(
        self,
        *,
        run_id: str,
        summary: HistoricalSignalEvaluationSummary,
        updated_at_ms: int,
        status: HistoricalSignalEvaluationStatus = HistoricalSignalEvaluationStatus.COMPLETED,
    ) -> HistoricalSignalEvaluationRun:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalSignalEvaluationRunORM,
                    run_id,
                    with_for_update=True,
                )
                if row is None:
                    raise ValueError(f"historical signal evaluation run not found: {run_id}")
                row.status = status.value
                row.summary_json = summary.model_dump(mode="json")
                row.updated_at_ms = updated_at_ms
                await session.flush()
                return self._to_run(row)

    async def get_evaluation_run(self, run_id: str) -> Optional[HistoricalSignalEvaluationRun]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcHistoricalSignalEvaluationRunORM, run_id)
            return self._to_run(row) if row is not None else None

    async def save_owner_review_report(
        self,
        *,
        run_id: str,
        report: HistoricalSignalEvaluationOwnerReport,
        updated_at_ms: int,
    ) -> HistoricalSignalEvaluationOwnerReport:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalSignalEvaluationRunORM,
                    run_id,
                    with_for_update=True,
                )
                if row is None:
                    raise ValueError(f"historical signal evaluation run not found: {run_id}")
                row.owner_report_json = report.model_dump(mode="json")
                row.updated_at_ms = updated_at_ms
                await session.flush()
                return HistoricalSignalEvaluationOwnerReport.model_validate(row.owner_report_json)

    async def get_owner_review_report(self, run_id: str) -> Optional[HistoricalSignalEvaluationOwnerReport]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcHistoricalSignalEvaluationRunORM, run_id)
            if row is None or not row.owner_report_json:
                return None
            return HistoricalSignalEvaluationOwnerReport.model_validate(row.owner_report_json)

    async def save_regime_split_report(
        self,
        report: HistoricalRegimeSplitComparisonReport,
    ) -> HistoricalRegimeSplitComparisonReport:
        payload = report.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcHistoricalRegimeSplitReportORM,
                    report.comparison_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcHistoricalRegimeSplitReportORM(comparison_id=report.comparison_id)
                    session.add(row)
                row.strategy_family_id = payload["strategy_family_id"]
                row.child_run_ids_json = dict(payload["child_run_ids_by_window_name"])
                row.weighted_owner_verdict = payload["weighted_owner_verdict"]
                row.report_json = payload
                row.created_at_ms = payload["created_at_ms"]
                await session.flush()
                return HistoricalRegimeSplitComparisonReport.model_validate(row.report_json)

    async def get_regime_split_report(self, comparison_id: str) -> Optional[HistoricalRegimeSplitComparisonReport]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcHistoricalRegimeSplitReportORM, comparison_id)
            if row is None:
                return None
            return HistoricalRegimeSplitComparisonReport.model_validate(row.report_json)

    async def list_signal_outputs(self, run_id: str) -> list[HistoricalSignalOutputRecord]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcHistoricalSignalOutputORM)
                .where(PGBrcHistoricalSignalOutputORM.run_id == run_id)
                .order_by(
                    PGBrcHistoricalSignalOutputORM.symbol.asc(),
                    PGBrcHistoricalSignalOutputORM.timestamp_ms.asc(),
                )
            )
            return [self._to_signal_output(row) for row in result.scalars().all()]

    async def list_forward_outcomes(self, run_id: str) -> list[HistoricalForwardOutcome]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcHistoricalForwardOutcomeORM)
                .where(PGBrcHistoricalForwardOutcomeORM.run_id == run_id)
                .order_by(
                    PGBrcHistoricalForwardOutcomeORM.symbol.asc(),
                    PGBrcHistoricalForwardOutcomeORM.timestamp_ms.asc(),
                    PGBrcHistoricalForwardOutcomeORM.window_label.asc(),
                )
            )
            return [self._to_forward_outcome(row) for row in result.scalars().all()]

    async def get_evaluation_summary(self, run_id: str) -> Optional[HistoricalSignalEvaluationSummary]:
        run = await self.get_evaluation_run(run_id)
        if run is None:
            return None
        if run.summary_json:
            return HistoricalSignalEvaluationSummary.model_validate(run.summary_json)
        records = await self.list_signal_outputs(run_id)
        outcomes = await self.list_forward_outcomes(run_id)
        return compute_historical_signal_summary(
            run_id=run_id,
            signal_records=records,
            outcomes=outcomes,
        )

    @staticmethod
    def _apply_run_payload(row: PGBrcHistoricalSignalEvaluationRunORM, payload: dict) -> None:
        row.strategy_family_id = payload["strategy_family_id"]
        row.strategy_family_version_id = payload["strategy_family_version_id"]
        row.playbook_id = payload.get("playbook_id")
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
        row.owner_report_json = dict(payload.get("owner_report_json") or {})
        row.created_at_ms = payload["created_at_ms"]
        row.updated_at_ms = payload["updated_at_ms"]
        row.notes = payload["notes"]

    @staticmethod
    def _apply_signal_output_payload(row: PGBrcHistoricalSignalOutputORM, payload: dict) -> None:
        row.run_id = payload["run_id"]
        row.evaluation_id = payload["evaluation_id"]
        row.strategy_family_id = payload["strategy_family_id"]
        row.symbol = payload["symbol"]
        row.timestamp_ms = payload["timestamp_ms"]
        row.timeframe = payload["timeframe"]
        row.signal_type = payload["signal_type"]
        row.side = payload["side"]
        row.confidence = Decimal(str(payload["confidence"]))
        row.reason_codes_json = list(payload["reason_codes"])
        row.data_quality_status = payload["data_quality_status"]
        row.evidence_payload_json = dict(payload["evidence_payload"])
        row.review_plan_json = dict(payload["review_plan"])
        row.not_order = payload["not_order"]
        row.not_execution_intent = payload["not_execution_intent"]
        row.created_at_ms = payload["created_at_ms"]

    @staticmethod
    def _apply_forward_outcome_payload(row: PGBrcHistoricalForwardOutcomeORM, payload: dict) -> None:
        row.run_id = payload["run_id"]
        row.signal_id = payload["signal_id"]
        row.symbol = payload["symbol"]
        row.timestamp_ms = payload["timestamp_ms"]
        row.side = payload["side"]
        row.window_label = payload["window_label"]
        row.bars_ahead = payload["bars_ahead"]
        row.status = payload["status"]
        row.mfe_pct = _optional_decimal(payload.get("mfe_pct"))
        row.mae_pct = _optional_decimal(payload.get("mae_pct"))
        row.time_to_mfe_bars = payload.get("time_to_mfe_bars")
        row.time_to_mae_bars = payload.get("time_to_mae_bars")
        row.pain_before_profit_pct = _optional_decimal(payload.get("pain_before_profit_pct"))
        row.profit_giveback_pct = _optional_decimal(payload.get("profit_giveback_pct"))
        row.follow_through = payload["follow_through"]
        row.invalidation_hit = payload["invalidation_hit"]
        row.return_time_curve_json = list(payload["return_time_curve"])
        row.created_at_ms = payload["created_at_ms"]

    @staticmethod
    def _to_run(row: PGBrcHistoricalSignalEvaluationRunORM) -> HistoricalSignalEvaluationRun:
        return HistoricalSignalEvaluationRun(
            run_id=row.run_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            playbook_id=row.playbook_id,
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
    def _to_signal_output(row: PGBrcHistoricalSignalOutputORM) -> HistoricalSignalOutputRecord:
        return HistoricalSignalOutputRecord(
            run_id=row.run_id,
            signal_id=row.signal_id,
            evaluation_id=row.evaluation_id,
            strategy_family_id=row.strategy_family_id,
            symbol=row.symbol,
            timestamp_ms=row.timestamp_ms,
            timeframe=row.timeframe,
            signal_type=row.signal_type,
            side=row.side,
            confidence=row.confidence,
            reason_codes=list(row.reason_codes_json or []),
            data_quality_status=row.data_quality_status,
            evidence_payload=dict(row.evidence_payload_json or {}),
            review_plan=dict(row.review_plan_json or {}),
            not_order=row.not_order,
            not_execution_intent=row.not_execution_intent,
            created_at_ms=row.created_at_ms,
        )

    @staticmethod
    def _to_forward_outcome(row: PGBrcHistoricalForwardOutcomeORM) -> HistoricalForwardOutcome:
        return HistoricalForwardOutcome(
            outcome_id=row.outcome_id,
            run_id=row.run_id,
            signal_id=row.signal_id,
            symbol=row.symbol,
            timestamp_ms=row.timestamp_ms,
            side=row.side,
            window_label=row.window_label,
            bars_ahead=row.bars_ahead,
            status=row.status,
            mfe_pct=row.mfe_pct,
            mae_pct=row.mae_pct,
            time_to_mfe_bars=row.time_to_mfe_bars,
            time_to_mae_bars=row.time_to_mae_bars,
            pain_before_profit_pct=row.pain_before_profit_pct,
            profit_giveback_pct=row.profit_giveback_pct,
            follow_through=row.follow_through,
            invalidation_hit=row.invalidation_hit,
            return_time_curve=list(row.return_time_curve_json or []),
            created_at_ms=row.created_at_ms,
        )


def _optional_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    return Decimal(str(value))
