"""Claim and observe at most one due runtime scope."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    advance_strategy_universe,
)
from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.application.project_shadow_outcome import (
    project_claimed_shadow_outcome,
)


class ObservationWorkerStatus(StrEnum):
    NO_WORK = "no_work"
    OBSERVED = "observed"
    RETRY_SCHEDULED = "retry_scheduled"
    SHADOW_COMPLETED = "shadow_completed"
    SHADOW_RETRY_SCHEDULED = "shadow_retry_scheduled"


class ObservationWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_id: str
    runtime_commit: str
    schema_revision: str
    now_ms: int
    lease_until_ms: int
    timeout_seconds: float
    retry_interval_ms: int

    @field_validator(
        "worker_id",
        "runtime_commit",
        "schema_revision",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("observation worker identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> ObservationWorkerRequest:
        if self.now_ms <= 0 or self.lease_until_ms <= self.now_ms:
            raise ValueError("observation worker lease must end after its tick")
        if self.timeout_seconds <= 0 or self.retry_interval_ms <= 0:
            raise ValueError("observation timeout and retry interval must be positive")
        return self


class ObservationWorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ObservationWorkerStatus
    runtime_scope_id: str | None = None
    trigger_candle_close_time_ms: int | None = None
    observation_status: ObservationStatus | None = None
    detail: str | None = None
    shadow_outcome_id: str | None = None


async def run_observation_worker_once(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    request: ObservationWorkerRequest,
) -> ObservationWorkerResult:
    async with uow_factory() as uow:
        claim = await uow.signals.claim_next_observation_scope(
            worker_id=request.worker_id,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
        )
    if claim is None:
        return await _run_one_due_shadow(
            uow_factory,
            market_source,
            request,
        )

    try:
        observation = await asyncio.wait_for(
            observe_strategy_scope(
                uow_factory,
                market_source,
                ObservationRequest(
                    runtime_scope_id=claim.runtime_scope_id,
                    runtime_commit=request.runtime_commit,
                    schema_revision=request.schema_revision,
                    trigger_candle_close_time_ms=(
                        claim.trigger_candle_close_time_ms
                    ),
                    observation_generation=claim.observation_generation,
                    attempted_at_ms=request.now_ms,
                ),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - observation failure must retain retry authority.
        async with uow_factory() as uow:
            await uow.signals.schedule_observation_scope(
                runtime_scope_id=claim.runtime_scope_id,
                worker_id=request.worker_id,
                observation_generation=claim.observation_generation,
                due_at_ms=request.now_ms + request.retry_interval_ms,
            )
        return ObservationWorkerResult(
            status=ObservationWorkerStatus.RETRY_SCHEDULED,
            runtime_scope_id=claim.runtime_scope_id,
            trigger_candle_close_time_ms=claim.trigger_candle_close_time_ms,
            detail=type(exc).__name__,
        )

    interval_ms = 900_000 if claim.timeframe == "15m" else 3_600_000
    retry = (
        observation.status is ObservationStatus.INVALID
        and observation.detector_reason == "market_snapshot_unavailable"
    )
    due_at_ms = (
        request.now_ms + request.retry_interval_ms
        if retry
        else claim.trigger_candle_close_time_ms + interval_ms
    )
    activation_universe_version_id: str | None = None
    async with uow_factory() as uow:
        await uow.signals.schedule_observation_scope(
            runtime_scope_id=claim.runtime_scope_id,
            worker_id=request.worker_id,
            observation_generation=claim.observation_generation,
            due_at_ms=due_at_ms,
        )
        if observation.status is ObservationStatus.WARMED:
            scope = await uow.signals.get_runtime_scope(
                claim.runtime_scope_id
            )
            if scope is None:
                raise RuntimeError(
                    "warmed observation scope authority disappeared"
                )
            activation_universe_version_id = scope.universe_version_id
    if activation_universe_version_id is not None:
        async with uow_factory() as uow:
            await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=activation_universe_version_id,
                    attempted_at_ms=request.now_ms,
                ),
            )
    return ObservationWorkerResult(
        status=(
            ObservationWorkerStatus.RETRY_SCHEDULED
            if retry
            else ObservationWorkerStatus.OBSERVED
        ),
        runtime_scope_id=claim.runtime_scope_id,
        trigger_candle_close_time_ms=claim.trigger_candle_close_time_ms,
        observation_status=observation.status,
        detail=observation.detector_reason,
    )


async def _run_one_due_shadow(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    request: ObservationWorkerRequest,
) -> ObservationWorkerResult:
    """Project at most one completed read-only horizon on an idle tick."""

    async with uow_factory() as uow:
        claim = await uow.shadow_outcomes.claim_one_due(
            worker_id=request.worker_id,
            now_ms=request.now_ms,
            lease_until_ms=request.lease_until_ms,
        )
    if claim is None:
        return ObservationWorkerResult(status=ObservationWorkerStatus.NO_WORK)

    limit = _shadow_candle_limit(claim.timeframe)
    try:
        candles = await asyncio.wait_for(
            market_source.fetch_closed_candles(
                ClosedCandleRequest(
                    exchange_instrument_id=claim.exchange_instrument_id,
                    timeframe=claim.timeframe,
                    limit=limit,
                    closed_at_ms=claim.horizon_end_ms,
                )
            ),
            timeout=request.timeout_seconds,
        )
        await project_claimed_shadow_outcome(
            uow_factory,
            claim,
            candles,
            worker_id=request.worker_id,
            completed_at_ms=request.now_ms,
        )
    except Exception as exc:  # noqa: BLE001 - source failure retains retry authority.
        async with uow_factory() as uow:
            await uow.shadow_outcomes.release_expired_claim(
                spec=claim,
                worker_id=request.worker_id,
            )
        return ObservationWorkerResult(
            status=ObservationWorkerStatus.SHADOW_RETRY_SCHEDULED,
            detail=type(exc).__name__,
            shadow_outcome_id=claim.shadow_outcome_id,
        )
    return ObservationWorkerResult(
        status=ObservationWorkerStatus.SHADOW_COMPLETED,
        shadow_outcome_id=claim.shadow_outcome_id,
    )


def _shadow_candle_limit(timeframe: str) -> int:
    if timeframe == "1h":
        return 24
    if timeframe == "15m":
        return 96
    raise ValueError("Shadow Outcome supports only 1h and 15m")
