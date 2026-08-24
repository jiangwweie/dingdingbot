"""Independent persistent ticks for Selection and Materialization planes."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditSource,
    CoordinateSelectionMaterializationRequest,
    MaterializationDisposition,
    complete_pending_authority_gap_audit,
    coordinate_selection_materialization_once,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.application.market_ports import InstrumentSelectionMarketSource
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.instrument_selection import DAY_MS, HOUR_MS
from src.trading_kernel.domain.selection_authority import (
    MaterializationGenerationClaimStatus,
)


class SelectionRuntimeStatus(StrEnum):
    NOT_DUE = "not_due"
    SNAPSHOT_READY = "snapshot_ready"
    ALREADY_READY = "already_ready"
    SOURCE_FAILED = "source_failed"
    COMPUTE_FAILED = "compute_failed"


class MaterializationRuntimeStatus(StrEnum):
    NOT_DUE = "not_due"
    ADVANCED = "advanced"
    WAITING = "waiting"
    BLOCKED = "blocked"


class SelectionRuntimeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_spec_id: str
    strategy_group_id: str
    worker_id: str
    now_ms: int
    max_concurrency: int = 6
    lease_duration_ms: int = 30_000

    @field_validator("selection_spec_id", "strategy_group_id", "worker_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection runtime identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_request(self) -> SelectionRuntimeRequest:
        if (
            self.now_ms <= 0
            or not 1 <= self.max_concurrency <= 24
            or self.lease_duration_ms <= 0
        ):
            raise ValueError("Selection runtime bounds are invalid")
        return self


class SelectionRuntimeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SelectionRuntimeStatus
    session_start_ms: int | None = None
    selection_job_id: str | None = None
    selection_snapshot_id: str | None = None
    reason_code: str | None = None


class MaterializationRuntimeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MaterializationRuntimeStatus
    session_start_ms: int | None = None
    disposition: MaterializationDisposition | None = None
    selection_authority_id: str | None = None
    materialization_generation_id: str | None = None
    entry_vacuum_id: str | None = None
    authority_gap_audit_id: str | None = None
    reason_code: str | None = None


def current_sor_selection_session_start_ms(now_ms: int) -> int | None:
    """Return today's UTC SOR Session only after its 01:00 decision boundary."""

    if now_ms <= 0:
        raise ValueError("Selection runtime time must be positive")
    session_start_ms = (now_ms // DAY_MS) * DAY_MS
    if now_ms < session_start_ms + HOUR_MS:
        return None
    return session_start_ms


async def run_selection_runtime_once(
    *,
    uow_factory: UnitOfWorkFactory,
    market_source: InstrumentSelectionMarketSource,
    request: SelectionRuntimeRequest,
    clock_ms: Callable[[], int],
) -> SelectionRuntimeResult:
    session_start_ms = current_sor_selection_session_start_ms(request.now_ms)
    if session_start_ms is None:
        return SelectionRuntimeResult(status=SelectionRuntimeStatus.NOT_DUE)
    result = await run_instrument_selection_once(
        uow_factory=uow_factory,
        market_source=market_source,
        request=RunInstrumentSelectionRequest(
            selection_spec_id=request.selection_spec_id,
            session_start_ms=session_start_ms,
            worker_id=request.worker_id,
            max_concurrency=request.max_concurrency,
        ),
        clock_ms=clock_ms,
    )
    return SelectionRuntimeResult(
        status=SelectionRuntimeStatus(result.outcome.lower()),
        session_start_ms=session_start_ms,
        selection_job_id=result.selection_job_id,
        selection_snapshot_id=result.selection_snapshot_id,
        reason_code=result.reason_code,
    )


async def run_materialization_runtime_once(
    *,
    uow_factory: UnitOfWorkFactory,
    audit_source: AuthorityGapAuditSource,
    request: SelectionRuntimeRequest,
    clock_ms: Callable[[], int],
) -> MaterializationRuntimeResult:
    session_start_ms = current_sor_selection_session_start_ms(request.now_ms)
    if session_start_ms is None:
        return MaterializationRuntimeResult(
            status=MaterializationRuntimeStatus.NOT_DUE
        )
    async with uow_factory() as uow:
        drain = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id=request.strategy_group_id,
                selection_spec_id=request.selection_spec_id,
                now_ms=request.now_ms,
            ),
        )
    if not (
        drain.status is VacuumDrainStatus.NO_VACUUM
        or (
            drain.status is VacuumDrainStatus.WAITING_LIFECYCLE
            and str(drain.reason_code or "").startswith("VACUUM_STATE:")
        )
    ):
        return _runtime_result_from_vacuum_drain(
            session_start_ms=session_start_ms,
            drain_status=drain.status,
            entry_vacuum_id=drain.entry_vacuum_id,
            selection_authority_id=drain.selection_authority_id,
            reason_code=drain.reason_code,
        )
    async with uow_factory() as uow:
        generation_claim = (
            await uow.instrument_selection.claim_materialization_generation(
                selection_spec_id=request.selection_spec_id,
                session_start_ms=session_start_ms,
                worker_id=request.worker_id,
                now_ms=request.now_ms,
                lease_duration_ms=request.lease_duration_ms,
            )
        )
    if (
        generation_claim.status
        is MaterializationGenerationClaimStatus.LEASE_HELD
    ):
        return MaterializationRuntimeResult(
            status=MaterializationRuntimeStatus.WAITING,
            session_start_ms=session_start_ms,
            materialization_generation_id=(
                None
                if generation_claim.generation is None
                else generation_claim.generation.materialization_generation_id
            ),
            reason_code="MATERIALIZATION_LEASE_HELD",
        )
    claimed_generation_id = (
        generation_claim.generation.materialization_generation_id
        if generation_claim.status
        is MaterializationGenerationClaimStatus.CLAIMED
        and generation_claim.generation is not None
        else None
    )
    try:
        result = await coordinate_selection_materialization_once(
            uow_factory=uow_factory,
            request=CoordinateSelectionMaterializationRequest(
                selection_spec_id=request.selection_spec_id,
                strategy_group_id=request.strategy_group_id,
                session_start_ms=session_start_ms,
                worker_id=request.worker_id,
            ),
            clock_ms=clock_ms,
        )
    finally:
        if claimed_generation_id is not None:
            async with uow_factory() as uow:
                await uow.instrument_selection.release_materialization_generation_lease(
                    materialization_generation_id=claimed_generation_id,
                    worker_id=request.worker_id,
                )
    if (
        result.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
        and result.authority_gap_audit_id is not None
    ):
        result = await complete_pending_authority_gap_audit(
            uow_factory=uow_factory,
            audit_source=audit_source,
            authority_gap_audit_id=result.authority_gap_audit_id,
            clock_ms=clock_ms,
        )
    if result.disposition is MaterializationDisposition.BLOCKED:
        status = MaterializationRuntimeStatus.BLOCKED
    elif result.disposition in {
        MaterializationDisposition.NOT_DUE,
        MaterializationDisposition.WAITING_SELECTION,
        MaterializationDisposition.WAITING_VACUUM,
        MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC,
        MaterializationDisposition.LONG_WARMING,
        MaterializationDisposition.SHORT_WARMING,
        MaterializationDisposition.GAP_AUDIT_PENDING,
    }:
        status = MaterializationRuntimeStatus.WAITING
    else:
        status = MaterializationRuntimeStatus.ADVANCED
    return MaterializationRuntimeResult(
        status=status,
        session_start_ms=session_start_ms,
        disposition=result.disposition,
        selection_authority_id=result.selection_authority_id,
        materialization_generation_id=result.materialization_generation_id,
        entry_vacuum_id=result.entry_vacuum_id,
        authority_gap_audit_id=result.authority_gap_audit_id,
        reason_code=result.reason_code,
    )


def _runtime_result_from_vacuum_drain(
    *,
    session_start_ms: int,
    drain_status: VacuumDrainStatus,
    entry_vacuum_id: str | None,
    selection_authority_id: str | None,
    reason_code: str | None,
) -> MaterializationRuntimeResult:
    if drain_status is VacuumDrainStatus.BLOCKED:
        status = MaterializationRuntimeStatus.BLOCKED
    elif drain_status in {
        VacuumDrainStatus.POSITION_FACTS_REQUIRED,
        VacuumDrainStatus.WAITING_COMMAND,
        VacuumDrainStatus.WAITING_UNKNOWN_OUTCOME,
        VacuumDrainStatus.WAITING_LIFECYCLE,
    }:
        status = MaterializationRuntimeStatus.WAITING
    else:
        status = MaterializationRuntimeStatus.ADVANCED
    if drain_status is VacuumDrainStatus.VALID_EMPTY_COMMITTED:
        disposition = MaterializationDisposition.VALID_EMPTY
    elif drain_status is VacuumDrainStatus.OWNER_PAUSED:
        disposition = MaterializationDisposition.OWNER_PAUSED
    else:
        disposition = MaterializationDisposition.WAITING_VACUUM
    return MaterializationRuntimeResult(
        status=status,
        session_start_ms=session_start_ms,
        disposition=disposition,
        selection_authority_id=selection_authority_id,
        entry_vacuum_id=entry_vacuum_id,
        reason_code=reason_code or drain_status.value,
    )
