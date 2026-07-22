"""Refuse Ticket issuance until a persisted action-time CapacityClaim exists."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.application.ingest_signal import (
    SignalAuthorityStatus,
    validate_signal_authority,
)
from src.trading_kernel.application.issue_ticket import (
    IssueTicketResult,
    IssueTicketStatus,
)
from src.trading_kernel.application.ports import KernelUnitOfWork


class IssueReadySignalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_owner: str
    runtime_commit: str
    schema_revision: str
    now_ms: int


async def issue_ready_signal(
    uow: KernelUnitOfWork,
    request: IssueReadySignalRequest,
) -> IssueTicketResult:
    signal = await uow.signals.get_next_ready(now_ms=request.now_ms)
    if signal is None:
        signal = await uow.signals.get_next_stale_ready(now_ms=request.now_ms)
        if signal is None:
            return IssueTicketResult(
                status=IssueTicketStatus.NO_READY_SIGNAL,
                ticket_id=None,
            )
    authority = await validate_signal_authority(
        uow,
        signal,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
        now_ms=request.now_ms,
    )
    if authority is not SignalAuthorityStatus.VALID:
        await uow.signals.save_readiness(
            runtime_scope_id=signal.runtime_scope_id,
            readiness_state="blocked",
            first_blocker=authority.value,
            signal_event_id=signal.signal_event_id,
            fact_summary={
                "fact_count": len(signal.facts),
                "fact_digest": signal.fact_digest,
            },
            updated_at_ms=request.now_ms,
        )
        return IssueTicketResult(
            status=IssueTicketStatus(authority.value),
            ticket_id=None,
        )
    return IssueTicketResult(
        status=IssueTicketStatus.CAPACITY_CLAIM_MISSING,
        ticket_id=None,
    )
