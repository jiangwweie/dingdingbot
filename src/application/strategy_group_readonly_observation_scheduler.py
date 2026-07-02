"""Cron-ready read-only strategy group observation runner.

This module evaluates the MI/CPM observation candidates against a read-only
closed-candle market source and persists observe-only evidence to PG. It does
not start runtime, create execution intents, grant permissions, or touch order
paths.
"""

from __future__ import annotations

import time
from inspect import isawaitable
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, Field

from src.application.runtime_strategy_signal_scheduler_planning_service import (
    RuntimeStrategySignalSchedulerPlanningResult,
)
from src.application.strategy_group_live_readonly_observation import (
    StrategyGroupLiveReadOnlyObservationResponse,
    StrategyGroupObservationRecord,
    StrategyGroupMarketBarSource,
    build_strategy_group_live_readonly_observation_v1,
)
from src.domain.strategy_family_signal import StrategyFamilySignalInput
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.infrastructure.binance_public_kline_market_source import BinancePublicKlineMarketSource
from src.infrastructure.local_sqlite_observation_market_source import LocalSqliteObservationMarketSource
from src.infrastructure.pg_strategy_group_observation_repository import PgStrategyGroupObservationRepository


ObservationSourceName = Literal["live_market", "local_sqlite_read_only"]
ObservationWriteAction = Literal["inserted", "skipped_duplicate", "failed"]
ShadowPlanningAction = Literal[
    "not_requested",
    "runtime_resolver_missing",
    "signal_input_snapshot_missing",
    "runtime_not_resolved",
    "blocked",
    "observe_only",
    "explicit_enable_required",
    "planner_blocked",
    "shadow_candidate_created",
    "failed",
]


class RuntimeSignalShadowPlanningService(Protocol):
    async def plan_signal_input_if_ready(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        candidate_id: str | None = None,
        allow_shadow_candidate_creation: bool = False,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalSchedulerPlanningResult:
        ...


class ObservationRuntimeResolver(Protocol):
    async def resolve_runtime_for_signal(
        self,
        signal_input: StrategyFamilySignalInput,
        observation: StrategyGroupObservationRecord,
    ) -> StrategyRuntimeInstance | None:
        ...


class StrategyRuntimeListService(Protocol):
    async def list_runtimes(
        self,
        *,
        status: StrategyRuntimeInstanceStatus | None = None,
        limit: int = 100,
    ) -> list[StrategyRuntimeInstance]:
        ...


class StrategyRuntimeObservationResolutionError(RuntimeError):
    """Raised when a signal maps to more than one active shadow runtime."""


class StrategyRuntimeObservationResolver:
    """Resolve a scheduled observation signal to one trusted active runtime.

    This resolver is intentionally narrow: it only chooses an already-active
    shadow runtime for the observed strategy/version/symbol/side. Downstream
    scheduler and planning gates remain responsible for semantic readiness,
    attempts, budgets, active position facts, and protection facts.
    """

    def __init__(
        self,
        *,
        runtime_service: StrategyRuntimeListService,
        limit: int = 100,
        now_ms_source: Callable[[], int] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("runtime resolver limit must be positive")
        self._runtime_service = runtime_service
        self._limit = limit
        self._now_ms_source = now_ms_source or _now_ms

    async def resolve_runtime_for_signal(
        self,
        signal_input: StrategyFamilySignalInput,
        observation: StrategyGroupObservationRecord,
    ) -> StrategyRuntimeInstance | None:
        runtimes = await self._runtime_service.list_runtimes(
            status=StrategyRuntimeInstanceStatus.ACTIVE,
            limit=self._limit,
        )
        now_ms = self._now_ms_source()
        matches = [
            runtime
            for runtime in runtimes
            if _runtime_matches_observed_signal(
                runtime,
                signal_input,
                observation,
                now_ms=now_ms,
            )
        ]
        if len(matches) > 1:
            raise StrategyRuntimeObservationResolutionError(
                "multiple_matching_active_shadow_runtimes"
            )
        return matches[0] if matches else None


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
    shadow_planning_action: ShadowPlanningAction = "not_requested"
    shadow_planning_result: dict[str, Any] = Field(default_factory=dict)
    shadow_planning_blockers: list[str] = Field(default_factory=list)
    shadow_planning_warnings: list[str] = Field(default_factory=list)
    runtime_instance_id: str | None = None
    planner_call_performed: bool = False
    signal_evaluation_created: bool = False
    order_candidate_created: bool = False
    execution_intent_created: bool = False
    order_created: bool = False
    order_lifecycle_called: bool = False
    exchange_called: bool = False
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


def _now_ms() -> int:
    return int(time.time() * 1000)


async def run_scheduled_readonly_observation_once(
    *,
    source_name: ObservationSourceName = "live_market",
    market_source: StrategyGroupMarketBarSource | None = None,
    repository: PgStrategyGroupObservationRepository | None = None,
    runtime_resolver: ObservationRuntimeResolver
    | Callable[
        [StrategyFamilySignalInput, StrategyGroupObservationRecord],
        StrategyRuntimeInstance | None,
    ]
    | None = None,
    runtime_signal_planning_service: RuntimeSignalShadowPlanningService | None = None,
    allow_shadow_candidate_creation: bool = False,
) -> ScheduledReadonlyObservationRunResult:
    """Run one scheduled/cron-ready observation cycle with PG idempotency.

    When a runtime resolver and scheduler-planning service are injected, this
    can also hand the just-observed signal to the non-executing shadow planner.
    Without explicit injection it remains observation-only.
    """

    source = market_source or build_observation_market_source(source_name)
    repo = repository or PgStrategyGroupObservationRepository()
    await repo.initialize()

    preview = build_strategy_group_live_readonly_observation_v1(market_source=source)
    candidate_results: list[ScheduledObservationCandidateResult] = []

    for record in preview.current_signals:
        candidate_result = await _record_if_new(repo, record)
        candidate_result = await _with_shadow_planning_result(
            candidate_result,
            record,
            runtime_resolver=runtime_resolver,
            runtime_signal_planning_service=runtime_signal_planning_service,
            allow_shadow_candidate_creation=allow_shadow_candidate_creation,
        )
        candidate_results.append(candidate_result)

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


async def _with_shadow_planning_result(
    result: ScheduledObservationCandidateResult,
    record: StrategyGroupObservationRecord,
    *,
    runtime_resolver: ObservationRuntimeResolver
    | Callable[
        [StrategyFamilySignalInput, StrategyGroupObservationRecord],
        StrategyRuntimeInstance | None,
    ]
    | None,
    runtime_signal_planning_service: RuntimeSignalShadowPlanningService | None,
    allow_shadow_candidate_creation: bool,
) -> ScheduledObservationCandidateResult:
    if runtime_signal_planning_service is None:
        return result
    if not record.signal_input_snapshot:
        return result.model_copy(
            update={
                "shadow_planning_action": "signal_input_snapshot_missing",
                "shadow_planning_blockers": ["signal_input_snapshot_missing"],
            }
        )
    if runtime_resolver is None:
        return result.model_copy(
            update={
                "shadow_planning_action": "runtime_resolver_missing",
                "shadow_planning_blockers": ["runtime_resolver_missing"],
            }
        )

    signal_input = StrategyFamilySignalInput.model_validate(
        record.signal_input_snapshot
    )
    runtime = await _resolve_runtime(runtime_resolver, signal_input, record)
    if runtime is None:
        return result.model_copy(
            update={
                "shadow_planning_action": "runtime_not_resolved",
                "shadow_planning_blockers": ["runtime_not_resolved"],
            }
        )
    planning = await runtime_signal_planning_service.plan_signal_input_if_ready(
        signal_input,
        runtime=runtime,
        candidate_id=record.candidate_id,
        allow_shadow_candidate_creation=allow_shadow_candidate_creation,
        context_id=f"scheduled-observation:{record.record_id}",
        metadata={
            "scheduled_readonly_observation": True,
            "observation_id": record.record_id,
            "candidate_id": record.candidate_id,
            "market_bar_timestamp_ms": record.market_bar_timestamp_ms,
            "allow_shadow_candidate_creation": allow_shadow_candidate_creation,
        },
    )

    action = _planning_action(planning)
    return result.model_copy(
        update={
            "shadow_planning_action": action,
            "shadow_planning_result": planning.model_dump(mode="json"),
            "shadow_planning_blockers": list(planning.blockers),
            "shadow_planning_warnings": list(planning.warnings),
            "runtime_instance_id": planning.runtime_instance_id,
            "planner_call_performed": planning.planner_call_performed,
            "signal_evaluation_created": planning.signal_evaluation_created,
            "order_candidate_created": planning.order_candidate_created,
            "execution_intent_created": planning.execution_intent_created,
            "order_created": planning.order_created,
            "order_lifecycle_called": planning.order_lifecycle_called,
            "exchange_called": planning.exchange_called,
        }
    )


async def _resolve_runtime(
    resolver: ObservationRuntimeResolver
    | Callable[
        [StrategyFamilySignalInput, StrategyGroupObservationRecord],
        StrategyRuntimeInstance | None,
    ],
    signal_input: StrategyFamilySignalInput,
    record: StrategyGroupObservationRecord,
) -> StrategyRuntimeInstance | None:
    if callable(resolver):
        value = resolver(signal_input, record)
    else:
        value = resolver.resolve_runtime_for_signal(signal_input, record)
    if isawaitable(value):
        value = await value
    return value


def _planning_action(
    planning: RuntimeStrategySignalSchedulerPlanningResult,
) -> ShadowPlanningAction:
    value = planning.status.value
    if value in {
        "blocked",
        "observe_only",
        "explicit_enable_required",
        "planner_blocked",
        "shadow_candidate_created",
    }:
        return value  # type: ignore[return-value]
    return "failed"


def _runtime_matches_observed_signal(
    runtime: StrategyRuntimeInstance,
    signal_input: StrategyFamilySignalInput,
    observation: StrategyGroupObservationRecord,
    *,
    now_ms: int,
) -> bool:
    if runtime.status != StrategyRuntimeInstanceStatus.ACTIVE:
        return False
    if runtime.execution_enabled or not runtime.shadow_mode:
        return False
    if runtime.expires_at_ms is not None and runtime.expires_at_ms <= now_ms:
        return False
    if runtime.strategy_family_id != signal_input.strategy_family_id:
        return False
    if runtime.strategy_family_version_id != signal_input.strategy_family_version_id:
        return False
    if observation.strategy_family_version_id is not None and (
        runtime.strategy_family_version_id != observation.strategy_family_version_id
    ):
        return False
    if runtime.symbol != signal_input.symbol or runtime.symbol != observation.symbol:
        return False
    side = _observed_signal_side(signal_input, observation)
    if side and runtime.side.lower() != side:
        return False
    return True


def _observed_signal_side(
    signal_input: StrategyFamilySignalInput,
    observation: StrategyGroupObservationRecord,
) -> str:
    side = observation.side or signal_input.trial_constraints_snapshot.get("side") or ""
    return str(side).lower()
