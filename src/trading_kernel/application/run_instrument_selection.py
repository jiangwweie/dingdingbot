"""One bounded Selection Plane run ending at a durable Snapshot or failure."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import DecimalException
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.market_ports import (
    GenericSelectionKlineRequest,
    InstrumentSelectionMarketSource,
    SelectionKlineRequest,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.dynamic_selection_numeric import (
    DynamicSelectionNumericError,
)
from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
    GenericSelectionSnapshotV1,
    compute_generic_selection,
)
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionMemberWindow,
)
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
    selection_job_identity,
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
    selection_epoch_id: str = "sor-v0"

    @field_validator("selection_spec_id", "worker_id", "selection_epoch_id", mode="before")
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
        "NOT_DUE",
        "NOT_INSTALLED",
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

    if request.selection_epoch_id != "sor-v0":
        return await _run_generic_selection_once(uow_factory=uow_factory, market_source=market_source, request=request, clock_ms=clock_ms)

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
    source_digest: str | None = None,
) -> None:
    async with uow_factory() as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim,
            outcome=outcome,
            reason_code=reason_code[:512],
            source_member_count=source_member_count,
            source_digest=source_digest,
            completed_at_ms=completed_at_ms,
        )


async def _run_generic_selection_once(
    *, uow_factory: UnitOfWorkFactory, market_source: InstrumentSelectionMarketSource,
    request: RunInstrumentSelectionRequest, clock_ms: Callable[[], int],
) -> RunInstrumentSelectionResult:
    job_id = selection_job_identity(request.selection_spec_id, request.session_start_ms, request.selection_epoch_id)
    async with uow_factory() as uow:
        try:
            spec = await uow.instrument_selection.get_generic_spec(request.selection_spec_id)
        except LookupError:
            return RunInstrumentSelectionResult(outcome="NOT_INSTALLED", selection_job_id=job_id)
        claimed = await uow.instrument_selection.claim_generic_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=request.selection_epoch_id, feature_cutoff_at_ms=request.session_start_ms,
            worker_id=request.worker_id, now_ms=clock_ms(), lease_duration_ms=request.lease_duration_ms)
        if claimed is None:
            return RunInstrumentSelectionResult(outcome="NOT_DUE", selection_job_id=job_id)
        if isinstance(claimed, GenericSelectionSnapshotV1):
            return RunInstrumentSelectionResult(outcome="ALREADY_READY", selection_job_id=job_id,
                selection_snapshot_id=claimed.selection_snapshot_id, ready_count=claimed.ready_count, selected_count=len(claimed.selected_members))
        if isinstance(claimed, SelectionJobFailure):
            return RunInstrumentSelectionResult(outcome=claimed.outcome, selection_job_id=job_id, reason_code=claimed.reason_code)
        claim = claimed
        predecessor = None if claim.predecessor_snapshot_id is None else await uow.instrument_selection.get_generic_snapshot(claim.predecessor_snapshot_id)
        product_profiles = await uow.instrument_selection.get_selection_product_profiles(spec.selection_spec_id)
    windows: dict[str, GenericSelectionMemberWindow] = {}
    errors: dict[str, Exception] = {}
    try:
        qualifications = await market_source.fetch_generic_selection_qualifications(
            event_spec_id=spec.event_spec_id, product_profiles=product_profiles, observed_at_ms=clock_ms())
        if tuple(sorted(q.product_profile.exchange_instrument_id for q in qualifications)) != spec.candidate_ids:
            raise SelectionSourceIntegrityError("Generic qualification requires exact Candidate24")
        qualification_by_member = {q.product_profile.exchange_instrument_id: q for q in qualifications}
        semaphore = asyncio.Semaphore(request.max_concurrency)

        async def read_one(member: str) -> None:
            try:
                async with semaphore:
                    candles = await market_source.fetch_generic_selection_klines(GenericSelectionKlineRequest.model_validate({
                        "exchange_instrument_id": member, "feature_cutoff_at_ms": request.session_start_ms, "expected_bars": spec.window_bars,
                    }))
                if len(candles) != spec.window_bars or candles[-1].close_time_ms != request.session_start_ms:
                    raise SelectionSourceIntegrityError("Generic member window is incomplete at cutoff")
                windows[member] = GenericSelectionMemberWindow(exchange_instrument_id=member, candles=candles,
                    qualification=qualification_by_member[member])
            except Exception as exc:  # noqa: BLE001 - explicit transport/source boundary
                errors[member] = exc

        await asyncio.gather(*(read_one(member) for member in spec.candidate_ids))
        if errors:
            raise SelectionSourceIntegrityError(_source_failure_reason(errors))
        observed_at_ms = clock_ms()
        source = GenericSelectionInput(spec=spec, selection_epoch_id=request.selection_epoch_id,
            feature_cutoff_at_ms=request.session_start_ms, decision_at_ms=request.session_start_ms,
            source_observed_at_ms=observed_at_ms, committed_at_ms=observed_at_ms,
            member_windows=tuple(windows[m] for m in spec.candidate_ids), predecessor_snapshot=predecessor)
    except Exception as exc:  # noqa: BLE001 - no source failure may become EMPTY
        reason = _source_failure_reason(errors) if errors else f"SOURCE_INTEGRITY:{type(exc).__name__}"
        await _persist_failure(uow_factory=uow_factory, claim=claim, outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code=reason, source_member_count=len(windows), completed_at_ms=clock_ms())
        return _failure_result(claim, "SOURCE_FAILED", reason)
    try:
        snapshot = compute_generic_selection(source)
    except (DynamicSelectionNumericError, DecimalException) as exc:
        reason = f"COMPUTE_UNDEFINED:{type(exc).__name__}:{exc}"[:512]
        await _persist_failure(uow_factory=uow_factory, claim=claim, outcome=SelectionAttemptOutcome.COMPUTE_FAILED,
            reason_code=reason, source_member_count=24, completed_at_ms=clock_ms(), source_digest=source.source_semantic_digest)
        return _failure_result(claim, "COMPUTE_FAILED", reason)
    async with uow_factory() as uow:
        completed_at_ms = clock_ms()
        snapshot = snapshot.model_copy(update={"committed_at_ms": completed_at_ms})
        await uow.instrument_selection.complete_generic_selection_snapshot(claim=claim, snapshot=snapshot,
            source_observed_at_ms=source.source_observed_at_ms, completed_at_ms=completed_at_ms)
    return RunInstrumentSelectionResult(outcome="SNAPSHOT_READY", selection_job_id=job_id,
        selection_snapshot_id=snapshot.selection_snapshot_id, ready_count=snapshot.ready_count, selected_count=len(snapshot.selected_members))


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
