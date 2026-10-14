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
from src.trading_kernel.application.ports import (
    SelectionJobRecord,
    SelectionPersistenceConflict,
    UnitOfWorkFactory,
)
from src.trading_kernel.domain.dynamic_selection_numeric import (
    DynamicSelectionNumericError,
)
from src.trading_kernel.domain.dynamic_selection_timing import (
    build_generic_selection_period,
)
from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
    GenericSelectionSnapshotV1,
    compute_generic_selection,
)
from src.trading_kernel.domain.generic_selection_jobs import (
    GENERIC_SOURCE_MAX_ATTEMPTS,
    GENERIC_SOURCE_RETRY_BACKOFF_MS,
    GenericSelectionSourceTemporarilyUnavailable,
    SelectionJobLease,
    selection_job_identity,
)
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionMemberWindow,
)
from src.trading_kernel.domain.instrument_selection import (
    HOUR_MS,
    SelectionAttemptOutcome,
    SelectionJobFailure,
    SelectionSnapshot,
    SelectionSourceIntegrityError,
    SelectionSourceWindow,
    SorDynamicSelectionSpecV0,
    build_sor_dynamic_selection_period,
    run_sor_dynamic_selection_v0,
)

DEFAULT_SELECTION_CONCURRENCY = 6
DEFAULT_SELECTION_LEASE_MS = 120_000


class RunInstrumentSelectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    period_anchor_ms: int
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
        "EXPIRED",
        "SUPERSEDED",
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

    if request.selection_spec_id=="SOR_1H_OR_ATR_DYNAMIC_V1":
        return await _run_orb_selection_once(uow_factory=uow_factory,market_source=market_source,request=request,clock_ms=clock_ms)
    if request.selection_epoch_id != "sor-v0":
        return await _run_generic_selection_once(uow_factory=uow_factory, market_source=market_source, request=request, clock_ms=clock_ms)

    period = build_sor_dynamic_selection_period(
        session_start_ms=request.period_anchor_ms
    )
    claimed_at_ms = clock_ms()
    async with uow_factory() as uow:
        spec = await uow.instrument_selection.get_active_spec(request.selection_spec_id)
        if not isinstance(spec,SorDynamicSelectionSpecV0):
            raise SelectionPersistenceConflict("legacy SOR request cannot consume another Selection family")
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
    claim: SelectionJobLease,
    outcome: SelectionAttemptOutcome,
    reason_code: str,
    source_member_count: int,
    completed_at_ms: int,
    source_digest: str | None = None,
    next_retry_at_ms: int | None = None,
) -> None:
    async with uow_factory() as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim,
            outcome=outcome,
            reason_code=reason_code[:512],
            source_member_count=source_member_count,
            source_digest=source_digest,
            completed_at_ms=completed_at_ms,
            next_retry_at_ms=next_retry_at_ms,
        )


async def _run_generic_selection_once(
    *, uow_factory: UnitOfWorkFactory, market_source: InstrumentSelectionMarketSource,
    request: RunInstrumentSelectionRequest, clock_ms: Callable[[], int],
) -> RunInstrumentSelectionResult:
    job_id = selection_job_identity(request.selection_spec_id, request.period_anchor_ms, request.selection_epoch_id)
    async with uow_factory() as uow:
        try:
            spec = await uow.instrument_selection.get_generic_spec(request.selection_spec_id)
        except LookupError:
            return RunInstrumentSelectionResult(outcome="NOT_INSTALLED", selection_job_id=job_id)
        claimed = await uow.instrument_selection.claim_generic_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=request.selection_epoch_id, feature_cutoff_at_ms=request.period_anchor_ms,
            worker_id=request.worker_id, now_ms=clock_ms(), lease_duration_ms=request.lease_duration_ms)
        if claimed is None:
            terminal = await uow.instrument_selection.get_selection_job(
                selection_spec_id=spec.selection_spec_id,
                selection_epoch_id=request.selection_epoch_id,
                period_anchor_ms=request.period_anchor_ms,
            )
            if terminal is not None and terminal.state == "EXPIRED":
                return RunInstrumentSelectionResult(
                    outcome="EXPIRED",
                    selection_job_id=job_id,
                    reason_code=terminal.first_blocker,
                )
            if terminal is not None and terminal.state == "SUPERSEDED":
                return RunInstrumentSelectionResult(
                    outcome="SUPERSEDED",
                    selection_job_id=job_id,
                    reason_code=terminal.first_blocker,
                )
            return RunInstrumentSelectionResult(outcome="NOT_DUE", selection_job_id=job_id)
        if isinstance(claimed, GenericSelectionSnapshotV1):
            return RunInstrumentSelectionResult(outcome="ALREADY_READY", selection_job_id=job_id,
                selection_snapshot_id=claimed.selection_snapshot_id, ready_count=claimed.ready_count, selected_count=len(claimed.selected_members))
        if isinstance(claimed, SelectionJobFailure):
            return RunInstrumentSelectionResult(outcome=claimed.outcome, selection_job_id=job_id, reason_code=claimed.reason_code)
        claim = claimed
        predecessor = None if claim.predecessor_snapshot_id is None else await uow.instrument_selection.get_generic_snapshot(claim.predecessor_snapshot_id)
        product_profiles = await uow.instrument_selection.get_selection_product_profiles(spec.selection_spec_id)
    period_expires_at_ms = build_generic_selection_period(
        feature_cutoff_at_ms=request.period_anchor_ms,
        cadence_hours=spec.cadence_hours,
    ).period_expires_at_ms
    windows: dict[str, GenericSelectionMemberWindow] = {}
    errors: dict[str, Exception] = {}
    source: GenericSelectionInput | None = None
    source_expired_at_ms: int | None = None
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
                        "exchange_instrument_id": member, "feature_cutoff_at_ms": request.period_anchor_ms, "expected_bars": spec.window_bars,
                    }))
                if len(candles) != spec.window_bars or candles[-1].close_time_ms != request.period_anchor_ms:
                    raise SelectionSourceIntegrityError("Generic member window is incomplete at cutoff")
                windows[member] = GenericSelectionMemberWindow(exchange_instrument_id=member, candles=candles,
                    qualification=qualification_by_member[member])
            except Exception as exc:  # noqa: BLE001 - explicit transport/source boundary
                errors[member] = exc

        await asyncio.gather(*(read_one(member) for member in spec.candidate_ids))
        if errors:
            raise SelectionSourceIntegrityError(_source_failure_reason(errors))
        observed_at_ms = clock_ms()
        if observed_at_ms >= period_expires_at_ms:
            source_expired_at_ms = observed_at_ms
        else:
            source = GenericSelectionInput(spec=spec, selection_epoch_id=request.selection_epoch_id,
                feature_cutoff_at_ms=request.period_anchor_ms, decision_at_ms=request.period_anchor_ms,
                source_observed_at_ms=observed_at_ms, committed_at_ms=observed_at_ms,
                member_windows=tuple(windows[m] for m in spec.candidate_ids), predecessor_snapshot=predecessor)
    except Exception as exc:  # noqa: BLE001 - no source failure may become EMPTY
        reason = _source_failure_reason(errors) if errors else f"SOURCE_INTEGRITY:{type(exc).__name__}"
        failed_at_ms = clock_ms()
        if failed_at_ms >= period_expires_at_ms:
            return await _expire_generic_selection_run(
                uow_factory=uow_factory, request=request, now_ms=failed_at_ms,
            )
        transient = (
            isinstance(exc, (TimeoutError, ConnectionError, GenericSelectionSourceTemporarilyUnavailable))
            or bool(errors) and all(isinstance(error, (TimeoutError, ConnectionError, GenericSelectionSourceTemporarilyUnavailable)) for error in errors.values())
        )
        retry_after = max((error.retry_after_ms or 0 for error in (
            (exc,) if not errors else tuple(errors.values())
        ) if isinstance(error, GenericSelectionSourceTemporarilyUnavailable)), default=0)
        retry_delay_ms = max(GENERIC_SOURCE_RETRY_BACKOFF_MS,retry_after)
        retry_at_ms = (
            failed_at_ms + retry_delay_ms
            if transient and claim.attempt_number < GENERIC_SOURCE_MAX_ATTEMPTS
            and failed_at_ms + retry_delay_ms < period_expires_at_ms
            else None
        )
        await _persist_failure(uow_factory=uow_factory, claim=claim, outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code=reason, source_member_count=len(windows), completed_at_ms=failed_at_ms,
            next_retry_at_ms=retry_at_ms)
        return _failure_result(claim, "SOURCE_FAILED", reason)
    if source_expired_at_ms is not None:
        return await _expire_generic_selection_run(
            uow_factory=uow_factory, request=request, now_ms=source_expired_at_ms,
        )
    assert source is not None
    try:
        snapshot = compute_generic_selection(source)
    except (DynamicSelectionNumericError, DecimalException) as exc:
        reason = f"COMPUTE_UNDEFINED:{type(exc).__name__}:{exc}"[:512]
        failed_at_ms = clock_ms()
        if failed_at_ms >= period_expires_at_ms:
            return await _expire_generic_selection_run(
                uow_factory=uow_factory, request=request, now_ms=failed_at_ms,
            )
        await _persist_failure(uow_factory=uow_factory, claim=claim, outcome=SelectionAttemptOutcome.COMPUTE_FAILED,
            reason_code=reason, source_member_count=24, completed_at_ms=failed_at_ms, source_digest=source.source_semantic_digest)
        return _failure_result(claim, "COMPUTE_FAILED", reason)
    async with uow_factory() as uow:
        completed_at_ms = clock_ms()
        if completed_at_ms >= period_expires_at_ms:
            await uow.instrument_selection.claim_generic_selection_job(
                selection_spec_id=request.selection_spec_id,
                selection_epoch_id=request.selection_epoch_id,
                feature_cutoff_at_ms=request.period_anchor_ms,
                worker_id=request.worker_id,
                now_ms=completed_at_ms,
                lease_duration_ms=request.lease_duration_ms,
            )
            terminal = await uow.instrument_selection.get_selection_job(
                selection_spec_id=request.selection_spec_id,
                selection_epoch_id=request.selection_epoch_id,
                period_anchor_ms=request.period_anchor_ms,
            )
            return _generic_elapsed_result(job_id, terminal)
        snapshot = snapshot.model_copy(update={"committed_at_ms": completed_at_ms})
        await uow.instrument_selection.complete_generic_selection_snapshot(claim=claim, snapshot=snapshot,
            source_observed_at_ms=source.source_observed_at_ms, completed_at_ms=completed_at_ms)
    return RunInstrumentSelectionResult(outcome="SNAPSHOT_READY", selection_job_id=job_id,
        selection_snapshot_id=snapshot.selection_snapshot_id, ready_count=snapshot.ready_count, selected_count=len(snapshot.selected_members))


async def _expire_generic_selection_run(
    *, uow_factory: UnitOfWorkFactory, request: RunInstrumentSelectionRequest,
    now_ms: int,
) -> RunInstrumentSelectionResult:
    async with uow_factory() as uow:
        await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=request.selection_spec_id,
            selection_epoch_id=request.selection_epoch_id,
            feature_cutoff_at_ms=request.period_anchor_ms,
            worker_id=request.worker_id,
            now_ms=now_ms,
            lease_duration_ms=request.lease_duration_ms,
        )
        terminal = await uow.instrument_selection.get_selection_job(
            selection_spec_id=request.selection_spec_id,
            selection_epoch_id=request.selection_epoch_id,
            period_anchor_ms=request.period_anchor_ms,
        )
    return _generic_elapsed_result(
        selection_job_identity(request.selection_spec_id, request.period_anchor_ms, request.selection_epoch_id),
        terminal,
    )


def _generic_elapsed_result(job_id: str, terminal: SelectionJobRecord | None) -> RunInstrumentSelectionResult:
    if terminal is not None and terminal.state == "EXPIRED":
        return RunInstrumentSelectionResult(
            outcome="EXPIRED",
            selection_job_id=job_id,
            reason_code=terminal.first_blocker,
        )
    if terminal is not None and terminal.state == "SUPERSEDED":
        return RunInstrumentSelectionResult(
            outcome="SUPERSEDED",
            selection_job_id=job_id,
            reason_code=terminal.first_blocker,
        )
    return RunInstrumentSelectionResult(
        outcome="NOT_DUE", selection_job_id=job_id,
        reason_code="SELECTION_AUTHORITY_CHANGED_DURING_SOURCE_READ",
    )


def _source_failure_reason(errors: dict[str, Exception]) -> str:
    first_instrument = min(errors)
    failure = errors[first_instrument]
    # Only local invariant messages are safe; transport errors can contain URLs.
    detail = str(failure) if isinstance(failure, SelectionSourceIntegrityError) else ""
    if detail not in {
        "Generic raw Kline row is malformed", "Generic raw OHLCV must enter from decimal strings",
        "Generic raw Kline close boundary is invalid", "Generic raw Kline timestamp must be an exact integer",
        "Generic Selection source window is incomplete", "Generic Selection source has duplicate, future or irregular candles",
        "Generic member window is incomplete at cutoff",
    }:
        detail = ""
    suffix = ":" + detail if detail else ""
    return f"SOURCE_MEMBER_FAILED:{first_instrument}:{type(failure).__name__}{suffix}"[:512]


def _failure_result(
    claim: SelectionJobLease,
    outcome: Literal["SOURCE_FAILED", "COMPUTE_FAILED"],
    reason_code: str,
) -> RunInstrumentSelectionResult:
    return RunInstrumentSelectionResult(
        outcome=outcome,
        selection_job_id=claim.selection_job_id,
        reason_code=reason_code,
    )


async def _run_orb_selection_once(*,uow_factory:UnitOfWorkFactory,market_source:InstrumentSelectionMarketSource,
    request:RunInstrumentSelectionRequest,clock_ms:Callable[[],int]) -> RunInstrumentSelectionResult:
    from src.trading_kernel.domain.orb_session_selection import (
        OrbSessionSelectionSnapshot,
        build_orb_session_period,
        compute_orb_selection,
    )
    period=build_orb_session_period(request.period_anchor_ms)
    job_id=selection_job_identity(request.selection_spec_id,request.period_anchor_ms,request.selection_epoch_id)
    now=clock_ms()
    if now>=period.trading_expires_at_ms:
        return RunInstrumentSelectionResult(outcome='EXPIRED',selection_job_id=job_id,reason_code='ORB_SESSION_EXPIRED')
    if now<period.feature_cutoff_at_ms:
        return RunInstrumentSelectionResult(outcome="NOT_DUE",selection_job_id=job_id)
    async with uow_factory() as uow:
        spec=await uow.instrument_selection.get_orb_spec(request.selection_spec_id)
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=request.selection_spec_id,
            selection_epoch_id=request.selection_epoch_id,session_start_ms=request.period_anchor_ms,
            worker_id=request.worker_id,now_ms=now,lease_duration_ms=request.lease_duration_ms)
    if claim is None:return RunInstrumentSelectionResult(outcome="NOT_DUE",selection_job_id=job_id)
    if isinstance(claim,OrbSessionSelectionSnapshot):
        return RunInstrumentSelectionResult(outcome="ALREADY_READY",selection_job_id=job_id,
            selection_snapshot_id=claim.selection_snapshot_id,ready_count=claim.ready_count,selected_count=claim.selected_count)
    if isinstance(claim,SelectionJobFailure):return RunInstrumentSelectionResult(outcome=claim.outcome,selection_job_id=claim.selection_job_id,reason_code=claim.reason_code)
    windows,errors=await _read_source_windows(market_source=market_source,candidate_ids=spec.candidate_ids,
        window_start_ms=period.session_start_ms-23*HOUR_MS,feature_cutoff_at_ms=period.feature_cutoff_at_ms,
        max_concurrency=request.max_concurrency)
    if clock_ms()>=period.trading_expires_at_ms:
        async with uow_factory() as uow:
            await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=request.selection_spec_id,
                selection_epoch_id=request.selection_epoch_id,session_start_ms=request.period_anchor_ms,
                worker_id=request.worker_id,now_ms=clock_ms(),lease_duration_ms=request.lease_duration_ms)
        return RunInstrumentSelectionResult(outcome='EXPIRED',selection_job_id=job_id,reason_code='ORB_SESSION_EXPIRED')
    if errors:
        await _persist_failure(uow_factory=uow_factory,claim=claim,outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code=_source_failure_reason(errors),source_member_count=len(windows),completed_at_ms=clock_ms())
        return RunInstrumentSelectionResult(outcome="SOURCE_FAILED",selection_job_id=job_id,reason_code=_source_failure_reason(errors))
    observed=clock_ms();completed=clock_ms()
    try:
        computation=compute_orb_selection(spec=spec,period=period,selection_epoch_id=request.selection_epoch_id,
            source_windows=tuple(windows[m] for m in spec.candidate_ids),decision_at_ms=claim.started_at_ms,
            source_observed_at_ms=observed,created_at_ms=completed)
    except (ArithmeticError,ValueError,SelectionSourceIntegrityError) as exc:
        outcome=SelectionAttemptOutcome.SOURCE_FAILED if isinstance(exc,SelectionSourceIntegrityError) else SelectionAttemptOutcome.COMPUTE_FAILED
        reason=('SOURCE_INTEGRITY:' if outcome is SelectionAttemptOutcome.SOURCE_FAILED else 'COMPUTE_REJECTED:')+type(exc).__name__
        await _persist_failure(uow_factory=uow_factory,claim=claim,outcome=outcome,reason_code=reason,
            source_member_count=len(windows),completed_at_ms=clock_ms())
        return RunInstrumentSelectionResult(outcome=outcome.value,selection_job_id=job_id,reason_code=reason)
    async with uow_factory() as uow:
        await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=computation,completed_at_ms=completed)
    return RunInstrumentSelectionResult(outcome="SNAPSHOT_READY",selection_job_id=job_id,
        selection_snapshot_id=computation.snapshot.selection_snapshot_id,ready_count=computation.snapshot.ready_count,
        selected_count=computation.snapshot.selected_count)
