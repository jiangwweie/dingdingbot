"""Persist lifecycle-fact failures and automatic recovery as Owner-visible facts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
    RuntimeIncidentRecord,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)

if TYPE_CHECKING:
    from src.trading_kernel.application.ports import KernelUnitOfWork

_LIFECYCLE_FACT_INCIDENT_KINDS = (
    "lifecycle_facts_unavailable",
    "lifecycle_facts_contradictory",
)
_CONTRADICTORY_ERROR_TYPES = frozenset({"RuntimeError", "TypeError", "ValueError"})


async def record_lifecycle_facts_failure(
    uow: KernelUnitOfWork,
    *,
    ticket_id: str,
    error_type: str,
    now_ms: int,
    due_at_ms: int,
) -> None:
    """Fail closed for new account ENTRY while one protected Ticket lacks facts."""

    aggregate = await uow.aggregates.get_for_update(ticket_id)
    if aggregate is None or aggregate.status not in {
        AggregateStatus.POSITION_PROTECTED,
        AggregateStatus.RUNNER_PROTECTED,
    }:
        return
    contradictory = error_type in _CONTRADICTORY_ERROR_TYPES
    incident_kind = (
        "lifecycle_facts_contradictory"
        if contradictory
        else "lifecycle_facts_unavailable"
    )
    opposite_kind = (
        "lifecycle_facts_unavailable"
        if contradictory
        else "lifecycle_facts_contradictory"
    )
    opposite = await uow.incidents.get_open_for_ticket_kind(ticket_id, opposite_kind)
    if opposite is not None:
        await uow.incidents.resolve(opposite.incident_id, resolved_at_ms=now_ms)
    existing = await uow.incidents.get_open_for_ticket_kind(ticket_id, incident_kind)
    incident_id = f"incident:{ticket_id}:{incident_kind}:{now_ms}"
    if existing is None:
        domain = aggregate.identity.netting_domain
        await uow.incidents.add(
            RuntimeIncidentRecord(
                incident_id=incident_id,
                ticket_id=ticket_id,
                incident_kind=incident_kind,
                status="open",
                first_blocker=incident_kind,
                entry_block_scope=EntryBlockScope.ACCOUNT_CAPACITY,
                entry_block_key=canonical_entry_block_key(
                    EntryBlockScope.ACCOUNT_CAPACITY,
                    venue_id=domain.venue_id,
                    account_id=domain.account_id,
                ),
                details={
                    "error_type": error_type,
                    "aggregate_version": aggregate.version,
                },
                opened_at_ms=now_ms,
            )
        )
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=f"lifecycle-facts:{ticket_id}",
            owner_status=(
                MonitorOwnerStatus.NEEDS_INTERVENTION
                if contradictory
                else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE
            ),
            summary=f"{incident_kind}:{error_type}",
            intervention=(
                "Owner review required; new account ENTRY remains blocked"
                if contradictory
                else "automatic retry; new account ENTRY remains blocked"
            ),
            ticket_id=ticket_id,
            incident_id=existing.incident_id if existing is not None else incident_id,
            updated_at_ms=now_ms,
        )
    )
    await uow.aggregates.schedule_next_check(
        ticket_id,
        work_kind="lifecycle",
        due_at_ms=due_at_ms,
    )


async def resolve_lifecycle_facts_failure(
    uow: KernelUnitOfWork,
    *,
    ticket_id: str,
    now_ms: int,
) -> None:
    """Resolve only lifecycle-fact incidents after one successful exact read."""

    resolved = False
    for incident_kind in _LIFECYCLE_FACT_INCIDENT_KINDS:
        existing = await uow.incidents.get_open_for_ticket_kind(
            ticket_id,
            incident_kind,
        )
        if existing is not None:
            await uow.incidents.resolve(existing.incident_id, resolved_at_ms=now_ms)
            resolved = True
    if resolved:
        await uow.monitors.save_if_changed(
            MonitorStateRecord(
                monitor_key=f"lifecycle-facts:{ticket_id}",
                owner_status=MonitorOwnerStatus.PROCESSING,
                summary="lifecycle_facts:available",
                intervention="none",
                ticket_id=ticket_id,
                incident_id=None,
                updated_at_ms=now_ms,
            )
        )
