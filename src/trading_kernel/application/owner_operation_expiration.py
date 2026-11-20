"""Expire only provably unstarted Owner commands; never infer unknown absence."""

from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.events import (
    OwnerOperationCommandObserved,
    OwnerPositionExitAborted,
    ProtectionReplacementRejected,
)
from src.trading_kernel.domain.reducer import reduce_event


async def expire_unstarted_owner_commands(
    uow, *, aggregate, commands, operation_id, now_ms, start_deadline_ms=None
):
    expired = [
        c
        for c in commands
        if c.status is S.PREPARED
        and min(c.deadline_at_ms, start_deadline_ms or c.deadline_at_ms) <= now_ms
        and getattr(c.payload, "owner_operation_id", None) == operation_id
    ]
    if not expired:
        return False
    for command in expired:
        await uow.exchange_commands.mark_prepared_superseded(
            command_id=command.command_id,
            observed_at_ms=now_ms,
            reason="owner_unstarted_window_expired",
        )
    event: (
        OwnerOperationCommandObserved
        | ProtectionReplacementRejected
        | OwnerPositionExitAborted
    )
    if (
        any(c.kind is K.REPLACE_PROTECTION for c in expired)
        and aggregate.protection_operation_id == operation_id
    ):
        event = ProtectionReplacementRejected(
            event_id=f"event:{aggregate.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=now_ms,
            reason="owner_protection_unstarted_window_expired",
        )
    elif (
        any(c.kind is K.EXIT for c in expired)
        and aggregate.protection_operation_id == operation_id
    ):
        event = OwnerPositionExitAborted(
            event_id=f"event:{aggregate.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=now_ms,
            operation_id=operation_id,
        )
    else:
        event = OwnerOperationCommandObserved(
            event_id=f"event:{aggregate.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=now_ms,
            operation_id=operation_id,
            command_id=expired[0].command_id,
            outcome={"unstarted_expired_command_ids": [c.command_id for c in expired]},
        )
    await uow.commit_reduction(
        event=event,
        reduction=reduce_event(aggregate, event),
        expected_version=aggregate.version,
    )
    return True
