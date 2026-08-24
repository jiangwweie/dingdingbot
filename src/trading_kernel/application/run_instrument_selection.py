"""One bounded Selection Plane run ending at a durable Snapshot or failure."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.market_ports import (
    InstrumentSelectionMarketSource,
    SelectionKlineRequest,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.instrument_selection import (
    HOUR_MS,
    SelectionAttemptOutcome,
    SelectionJobClaim,
    SelectionJobFailure,
    SelectionSnapshot,
    SelectionSourceIntegrityError,
    SelectionSourceWindow,
    build_sor_dynamic_selection_period,
    run_sor_dynamic_selection_v0,
)

DEFAULT_SELECTION_CONCURRENCY = 6
DEFAULT_SELECTION_LEASE_MS = 120_000


class RunInstrumentSelectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    session_start_ms: int
    worker_id: str
    max_concurrency: int = DEFAULT_SELECTION_CONCURRENCY
    lease_duration_ms: int = DEFAULT_SELECTION_LEASE_MS

    @field_validator("selection_spec_id", "worker_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection Runner identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_bounds(self) -> RunInstrumentSelectionRequest:
        if not 1 <= self.max_concurrency <= 24:
            raise ValueError("Selection concurrency must be between 1 and 24")
        if self.lease_duration_ms <= 0:
            raise ValueError("Selection lease duration must be positive")
        return self


class RunInstrumentSelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: Literal[
        "SNAPSHOT_READY",
        "ALREADY_READY",
        "SOURCE_FAILED",
        "COMPUTE_FAILED",
    ]
    selection_job_id: str
    selection_snapshot_id: str | None = None
    ready_count: int | None = None
    selected_count: int | None = None
    reason_code: str | None = None


async def run_instrument_selection_once(
    *,
    uow_factory: UnitOfWorkFactory,
    market_source: InstrumentSelectionMarketSource,
    request: RunInstrumentSelectionRequest,
    clock_ms: Callable[[], int],
) -> RunInstrumentSelectionResult:
    """Claim, read the full panel outside PG, compute, and atomically persist."""

    period = build_sor_dynamic_selection_period(
        session_start_ms=request.session_start_ms
    )
    claimed_at_ms = clock_ms()
    async with uow_factory() as uow:
        spec = await uow.instrument_selection.get_active_spec(request.selection_spec_id)
        claim_or_snapshot = await uow.instrument_selection.claim_selection_job(
            spec=spec,
            period=period,
            worker_id=request.worker_id,
            now_ms=claimed_at_ms,
            lease_duration_ms=request.lease_duration_ms,
        )
    if isinstance(claim_or_snapshot, SelectionSnapshot):
        return RunInstrumentSelectionResult(
            outcome="ALREADY_READY",
            selection_job_id=(
                f"selection-job:{spec.selection_spec_id}:{period.session_start_ms}"
            ),
            selection_snapshot_id=claim_or_snapshot.selection_snapshot_id,
            ready_count=claim_or_snapshot.ready_count,
            selected_count=claim_or_snapshot.selected_count,
        )
    if isinstance(claim_or_snapshot, SelectionJobFailure):
        return RunInstrumentSelectionResult(
            outcome=claim_or_snapshot.outcome,
            selection_job_id=claim_or_snapshot.selection_job_id,
            reason_code=claim_or_snapshot.reason_code,
        )
    claim = claim_or_snapshot

    source_windows, source_errors = await _read_source_windows(
        market_source=market_source,
        candidate_ids=spec.candidate_exchange_instrument_ids,
        window_start_ms=period.session_start_ms - 23 * HOUR_MS,
        feature_cutoff_at_ms=period.feature_cutoff_at_ms,
        max_concurrency=request.max_concurrency,
    )
    source_observed_at_ms = clock_ms()
    if source_errors:
        reason = _source_failure_reason(source_errors)
        await _persist_failure(
            uow_factory=uow_factory,
            claim=claim,
            outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code=reason,
            source_member_count=len(source_windows),
            completed_at_ms=source_observed_at_ms,
        )
        return _failure_result(claim, "SOURCE_FAILED", reason)

    try:
        computation = run_sor_dynamic_selection_v0(
            spec=spec,
            period=period,
            source_windows=tuple(source_windows.values()),
            decision_at_ms=source_observed_at_ms,
            source_observed_at_ms=source_observed_at_ms,
            created_at_ms=source_observed_at_ms,
        )
    except SelectionSourceIntegrityError as exc:
        reason = f"SOURCE_INTEGRITY:{type(exc).__name__}:{exc}"
        await _persist_failure(
            uow_factory=uow_factory,
            claim=claim,
            outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code=reason,
            source_member_count=len(source_windows),
            completed_at_ms=clock_ms(),
        )
        return _failure_result(claim, "SOURCE_FAILED", reason)
    except (ArithmeticError, ValueError) as exc:
        reason = f"COMPUTE_REJECTED:{type(exc).__name__}:{exc}"
        await _persist_failure(
            uow_factory=uow_factory,
            claim=claim,
            outcome=SelectionAttemptOutcome.COMPUTE_FAILED,
            reason_code=reason,
            source_member_count=len(source_windows),
            completed_at_ms=clock_ms(),
        )
        return _failure_result(claim, "COMPUTE_FAILED", reason)

    completed_at_ms = clock_ms()
    async with uow_factory() as uow:
        await uow.instrument_selection.complete_selection_snapshot(
            claim=claim,
            computation=computation,
            completed_at_ms=completed_at_ms,
        )
    return RunInstrumentSelectionResult(
        outcome="SNAPSHOT_READY",
        selection_job_id=claim.selection_job_id,
        selection_snapshot_id=computation.snapshot.selection_snapshot_id,
        ready_count=computation.snapshot.ready_count,
        selected_count=computation.snapshot.selected_count,
    )


async def _read_source_windows(
    *,
    market_source: InstrumentSelectionMarketSource,
    candidate_ids: tuple[str, ...],
    window_start_ms: int,
    feature_cutoff_at_ms: int,
    max_concurrency: int,
) -> tuple[dict[str, SelectionSourceWindow], dict[str, Exception]]:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def read_one(
        exchange_instrument_id: str,
    ) -> tuple[str, SelectionSourceWindow | Exception]:
        try:
            async with semaphore:
                klines = await market_source.fetch_selection_klines(
                    SelectionKlineRequest(
                        exchange_instrument_id=exchange_instrument_id,
                        input_window_start_ms=window_start_ms,
                        feature_cutoff_at_ms=feature_cutoff_at_ms,
                    )
                )
            return (
                exchange_instrument_id,
                SelectionSourceWindow(
                    exchange_instrument_id=exchange_instrument_id,
                    input_window_start_ms=window_start_ms,
                    feature_cutoff_at_ms=feature_cutoff_at_ms,
                    klines=klines,
                ),
            )
        # This is the explicit source-failure boundary: venue libraries expose
        # transport and parse failures through several unrelated subclasses.
        except Exception as exc:  # noqa: BLE001
            return exchange_instrument_id, exc

    results = await asyncio.gather(*(read_one(item) for item in candidate_ids))
    windows: dict[str, SelectionSourceWindow] = {}
    errors: dict[str, Exception] = {}
    for instrument_id, result in results:
        if isinstance(result, Exception):
            errors[instrument_id] = result
        else:
            windows[instrument_id] = result
    return windows, errors


async def _persist_failure(
    *,
    uow_factory: UnitOfWorkFactory,
    claim: SelectionJobClaim,
    outcome: SelectionAttemptOutcome,
    reason_code: str,
    source_member_count: int,
    completed_at_ms: int,
) -> None:
    async with uow_factory() as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim,
            outcome=outcome,
            reason_code=reason_code[:512],
            source_member_count=source_member_count,
            source_digest=None,
            completed_at_ms=completed_at_ms,
        )


def _source_failure_reason(errors: dict[str, Exception]) -> str:
    first_instrument = min(errors)
    failure = errors[first_instrument]
    return f"SOURCE_MEMBER_FAILED:{first_instrument}:{type(failure).__name__}"[:512]


def _failure_result(
    claim: SelectionJobClaim,
    outcome: Literal["SOURCE_FAILED", "COMPUTE_FAILED"],
    reason_code: str,
) -> RunInstrumentSelectionResult:
    return RunInstrumentSelectionResult(
        outcome=outcome,
        selection_job_id=claim.selection_job_id,
        reason_code=reason_code,
    )
