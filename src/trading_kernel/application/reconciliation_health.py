"""Bounded waiting and recovery visibility in the existing Monitor projection."""

from __future__ import annotations

from src.trading_kernel.application.ports import (
    KernelUnitOfWork,
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.domain.aggregate import AggregateStatus

CLOSURE_WAIT_MS = 300_000


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
            review = await uow.reviews.get_for_ticket(ticket_id)
            await resolve_reconciliation_wait(uow, key=key, now_ms=now_ms,
                economics_complete=review is not None and review.metrics.get("economics_completeness") == "complete")
            return
    previous = await uow.monitors.get(key)
    if previous is not None and previous.last_checked_at_ms is not None and now_ms < previous.last_checked_at_ms:
        return
    first = (
        now_ms
        if previous is None or previous.owner_status is MonitorOwnerStatus.COMPLETED
        else previous.first_wait_at_ms or previous.updated_at_ms
    )
    if key.startswith("reconciliation-closure:"):
        allowed_delay_ms = CLOSURE_WAIT_MS
    # First occurrence is never escalated; repeated real observations are required.
    delayed = (
        previous is not None
        and previous.owner_status is not MonitorOwnerStatus.COMPLETED
        and (previous.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
             or now_ms - first >= allowed_delay_ms)
    )
    state = MonitorStateRecord(
        monitor_key=key,
        owner_status=MonitorOwnerStatus.NEEDS_INTERVENTION
        if delayed
        else MonitorOwnerStatus.PROCESSING,
        summary=reason,
        intervention="工程排查；不手动平仓或修改数据库" if delayed else "none",
        ticket_id=ticket_id,
        first_wait_at_ms=first,
        last_checked_at_ms=now_ms,
        escalated_at_ms=(previous.escalated_at_ms or previous.updated_at_ms)
        if delayed and previous is not None and previous.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
        else now_ms if delayed else None,
        updated_at_ms=(previous.updated_at_ms if previous is not None
            and previous.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION else now_ms)
            if delayed else first,
    )
    await uow.monitors.save_if_changed(state)


async def resolve_reconciliation_wait(
    uow: KernelUnitOfWork, *, key: str, now_ms: int,
    economics_complete: bool = True,
) -> None:
    previous = await uow.monitors.get(key)
    if (
        previous is not None
        and (previous.owner_status is not MonitorOwnerStatus.COMPLETED
            or economics_complete and previous.summary == "trade_closed_economics_incomplete")
    ):
        await uow.monitors.save_if_changed(
            previous.model_copy(
                update={
                    "owner_status": MonitorOwnerStatus.COMPLETED,
                    "summary": "review_economics_completed" if economics_complete and previous.summary == "trade_closed_economics_incomplete"
                    else "reconciliation_progress_restored" if economics_complete else "trade_closed_economics_incomplete",
                    "intervention": "none",
                    "updated_at_ms": now_ms,
                    "last_checked_at_ms": now_ms,
                    "resolved_at_ms": now_ms,
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
            if now_ms - candidate.last_progress_at_ms >= CLOSURE_WAIT_MS:
                await record_reconciliation_wait(
                    uow,
                    key=key,
                    reason=f"closure_wait:{candidate.status}",
                    now_ms=now_ms,
                    allowed_delay_ms=CLOSURE_WAIT_MS,
                    ticket_id=candidate.ticket_id,
                )
