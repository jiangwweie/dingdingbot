"""Cron-ready read-only strategy group observation runner.

This module evaluates the MI/CPM observation candidates against a read-only
closed-candle market source and persists observe-only evidence to PG. It does
not start runtime, create execution intents, grant permissions, or touch order
paths.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.application.strategy_group_live_readonly_observation import (
    StrategyGroupLiveReadOnlyObservationResponse,
    StrategyGroupObservationRecord,
    StrategyGroupMarketBarSource,
    build_strategy_group_live_readonly_observation_v1,
)
from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
from src.infrastructure.local_sqlite_observation_market_source import LocalSqliteObservationMarketSource
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository


ObservationSourceName = Literal["live_market", "local_sqlite_fallback"]
ObservationWriteAction = Literal["inserted", "skipped_duplicate", "failed"]


class ScheduledObservationCandidateResult(BaseModel):
    candidate_id: str
    strategy_group_id: str | None = None
    strategy_family_version_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    signal_type: str | None = None
    market_bar_timestamp_ms: int | None = None
    market_bar_close: str | None = None
    market_source: str | None = None
    source_type: str | None = None
    record_id: str | None = None
    existing_record_id: str | None = None
    action: ObservationWriteAction
    reason: str | None = None
    runtime_signal_planning_readiness: dict = Field(default_factory=dict)
    not_order: bool = True
    not_execution_intent: bool = True
    no_execution_permission: bool = True
    no_order_permission: bool = True
    no_runtime_start: bool = True


class ScheduledReadonlyObservationRunResult(BaseModel):
    runner: str = "scheduled_readonly_strategy_group_observation_v0"
    source_requested: ObservationSourceName
    market_source: str
    source_type: str
    sink: str = "pg_brc_strategy_group_observations"
    candidates_evaluated: int
    inserted_count: int
    skipped_duplicate_count: int
    failed_count: int
    candidate_results: list[ScheduledObservationCandidateResult] = Field(default_factory=list)
    input_source_summary: dict = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(
        default_factory=lambda: {
            "no_trial_start": True,
            "no_execution_intent": True,
            "no_order_permission": True,
            "no_runtime_start": True,
            "no_exchange_write": True,
        }
    )


async def run_scheduled_readonly_observation_once(
    *,
    source_name: ObservationSourceName = "live_market",
    market_source: StrategyGroupMarketBarSource | None = None,
    repository: PgStrategyGroupObservationRepository | None = None,
) -> ScheduledReadonlyObservationRunResult:
    """Run one scheduled/cron-ready observation cycle with PG idempotency."""

    source = market_source or build_observation_market_source(source_name)
    repo = repository or PgStrategyGroupObservationRepository()
    await repo.initialize()

    preview = build_strategy_group_live_readonly_observation_v1(market_source=source)
    candidate_results: list[ScheduledObservationCandidateResult] = []

    for record in preview.current_signals:
        candidate_results.append(await _record_if_new(repo, record))

    inserted = sum(1 for result in candidate_results if result.action == "inserted")
    skipped = sum(1 for result in candidate_results if result.action == "skipped_duplicate")
    failed = sum(1 for result in candidate_results if result.action == "failed")
    source_id = getattr(source, "source_id", "unknown_market_source")
    source_type = getattr(source, "source_type", preview.input_source_summary.get("source_type", "read_only_market_source"))
    return ScheduledReadonlyObservationRunResult(
        source_requested=source_name,
        market_source=source_id,
        source_type=source_type,
        candidates_evaluated=len(preview.candidates),
        inserted_count=inserted,
        skipped_duplicate_count=skipped,
        failed_count=failed,
        candidate_results=candidate_results,
        input_source_summary=dict(preview.input_source_summary),
    )


def build_observation_market_source(source_name: ObservationSourceName) -> StrategyGroupMarketBarSource:
    if source_name == "live_market":
        return BinancePublicKlineMarketSource()
    return LocalSqliteObservationMarketSource()


async def _record_if_new(
    repo: PgStrategyGroupObservationRepository,
    record: StrategyGroupObservationRecord,
) -> ScheduledObservationCandidateResult:
    try:
        existing = await repo.find_by_observation_identity(
            candidate_id=record.candidate_id,
            symbol=record.symbol,
            side=record.side,
            market_bar_timestamp_ms=record.market_bar_timestamp_ms,
        )
        if existing is not None:
            return _candidate_result(
                record,
                action="skipped_duplicate",
                existing_record_id=existing.record_id,
                reason="same_candidate_symbol_side_closed_bar_already_recorded",
            )

        recorded = await repo.record(record)
        return _candidate_result(recorded, action="inserted")
    except Exception as exc:  # pragma: no cover - defensive PG/network boundary.
        return _candidate_result(
            record,
            action="failed",
            reason=f"{type(exc).__name__}: {str(exc)[:240]}",
        )


def _candidate_result(
    record: StrategyGroupObservationRecord,
    *,
    action: ObservationWriteAction,
    existing_record_id: str | None = None,
    reason: str | None = None,
) -> ScheduledObservationCandidateResult:
    return ScheduledObservationCandidateResult(
        candidate_id=record.candidate_id,
        strategy_group_id=record.strategy_group_id,
        strategy_family_version_id=record.strategy_family_version_id,
        symbol=record.symbol,
        side=record.side,
        signal_type=record.signal_type,
        market_bar_timestamp_ms=record.market_bar_timestamp_ms,
        market_bar_close=record.market_bar_close,
        market_source=record.market_source,
        source_type=record.source_type,
        record_id=record.record_id,
        existing_record_id=existing_record_id,
        action=action,
        reason=reason,
        runtime_signal_planning_readiness=dict(
            record.runtime_signal_planning_readiness
        ),
        not_order=record.not_order,
        not_execution_intent=record.not_execution_intent,
        no_execution_permission=record.no_execution_permission,
        no_order_permission=record.no_order_permission,
        no_runtime_start=record.no_runtime_start,
    )
