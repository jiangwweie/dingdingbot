"""Bounded waiting and recovery visibility in the existing Monitor projection."""

from __future__ import annotations

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.domain.aggregate import AggregateStatus


async def record_reconciliation_wait(
    uow: KernelUnitOfWork,
    *,
    key: str,
    reason: str,
    now_ms: int,
    allowed_delay_ms: int,
    ticket_id: str | None = None,
) -> None:
    if now_ms <= 0 or allowed_delay_ms <= 0:
        raise ValueError("reconciliation health windows must be positive")
    if ticket_id is not None:
        aggregate = await uow.aggregates.get_for_update(ticket_id)
        if aggregate is None:
            return
        if aggregate.status is AggregateStatus.TERMINAL:
            await resolve_reconciliation_wait(uow, key=key, now_ms=now_ms)
            return
    previous = await uow.monitors.get(key)
    first = (
        now_ms
        if previous is None or previous.owner_status is MonitorOwnerStatus.COMPLETED
        else previous.updated_at_ms
    )
    # First occurrence is never escalated; repeated real observations are required.
    delayed = (
        previous is not None
        and previous.owner_status is not MonitorOwnerStatus.COMPLETED
        and now_ms - first >= allowed_delay_ms
    )
    state = MonitorStateRecord(
        monitor_key=key,
        owner_status=MonitorOwnerStatus.NEEDS_INTERVENTION
        if delayed
        else MonitorOwnerStatus.PROCESSING,
        summary=reason,
        intervention="工程排查；不手动平仓或修改数据库" if delayed else "none",
        ticket_id=ticket_id,
        updated_at_ms=first,
    )
    if (
        previous is None
        or previous.owner_status != state.owner_status
        or previous.summary != state.summary
        or previous.intervention != state.intervention
    ):
        await uow.monitors.save_if_changed(state)


async def resolve_reconciliation_wait(
    uow: KernelUnitOfWork, *, key: str, now_ms: int
) -> None:
    previous = await uow.monitors.get(key)
    if (
        previous is not None
        and previous.owner_status is not MonitorOwnerStatus.COMPLETED
    ):
        await uow.monitors.save_if_changed(
            previous.model_copy(
                update={
                    "owner_status": MonitorOwnerStatus.COMPLETED,
                    "summary": "reconciliation_progress_restored",
                    "intervention": "none",
                    "updated_at_ms": now_ms,
                }
            )
        )


async def record_worker_retry(
    uow: KernelUnitOfWork, *, key: str, reason: str, now_ms: int, window_ms: int
) -> None:
    previous = await uow.monitors.get(key)
    repeated = (
        previous is not None
        and previous.owner_status is not MonitorOwnerStatus.COMPLETED
        and 0 <= now_ms - previous.updated_at_ms <= window_ms
    )
    await uow.monitors.save_if_changed(
        MonitorStateRecord(
            monitor_key=key,
            owner_status=MonitorOwnerStatus.NEEDS_INTERVENTION
            if repeated
            else MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
            summary=reason,
            intervention="工程排查；保留新开仓暂停" if repeated else "none",
            updated_at_ms=now_ms,
        )
    )


async def clear_worker_retry(
    uow: KernelUnitOfWork, *, key: str, now_ms: int, window_ms: int
) -> None:
    previous = await uow.monitors.get(key)
    if previous is not None and now_ms - previous.updated_at_ms > window_ms:
        await resolve_reconciliation_wait(uow, key=key, now_ms=now_ms)


async def observe_reconciliation_backlog(
    uow: KernelUnitOfWork, *, now_ms: int, budget_ms: int
) -> None:
    for candidate in await uow.aggregates.list_reconciliation_health_candidates():
        key = f"reconciliation-overdue:{candidate.ticket_id}"
        if now_ms - candidate.due_at_ms >= budget_ms:
            await record_reconciliation_wait(
                uow,
                key=key,
                reason="critical_reconciliation_overdue",
                now_ms=now_ms,
                allowed_delay_ms=budget_ms,
                ticket_id=candidate.ticket_id,
            )
        else:
            await resolve_reconciliation_wait(uow, key=key, now_ms=now_ms)
        if candidate.status in {"settlement_pending", "review_pending"}:
            key = f"reconciliation-closure:{candidate.ticket_id}"
            if now_ms - candidate.last_progress_at_ms >= budget_ms:
                await record_reconciliation_wait(
                    uow,
                    key=key,
                    reason=f"closure_wait:{candidate.status}",
                    now_ms=now_ms,
                    allowed_delay_ms=budget_ms,
                    ticket_id=candidate.ticket_id,
                )
