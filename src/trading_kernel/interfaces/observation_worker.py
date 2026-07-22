"""Claim and observe at most one due runtime scope."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.market_ports import PublicMarketSource
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory


class ObservationWorkerStatus(StrEnum):
    NO_WORK = "no_work"
    OBSERVED = "observed"
    RETRY_SCHEDULED = "retry_scheduled"


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
    def _validate_window(self) -> "ObservationWorkerRequest":
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
        return ObservationWorkerResult(status=ObservationWorkerStatus.NO_WORK)

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
                ),
            ),
            timeout=request.timeout_seconds,
        )
    except Exception as exc:
        async with uow_factory() as uow:
            await uow.signals.schedule_observation_scope(
                runtime_scope_id=claim.runtime_scope_id,
                worker_id=request.worker_id,
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
    async with uow_factory() as uow:
        await uow.signals.schedule_observation_scope(
            runtime_scope_id=claim.runtime_scope_id,
            worker_id=request.worker_id,
            due_at_ms=due_at_ms,
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
