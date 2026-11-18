"""Hand a changed natural TP back to the lifecycle without abandoning sent writes."""

from decimal import Decimal

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import ExchangeCommand
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.events import (
    OwnerOperationCommandObserved,
    OwnerPositionExitAborted,
    ProtectionReplacementRejected,
)
from src.trading_kernel.domain.reducer import reduce_event


async def handoff_natural_tp(
    uow: KernelUnitOfWork, *, aggregate: TradeAggregate, row: dict, commands: tuple[ExchangeCommand,...],
    filled_quantity: Decimal, position_quantity: Decimal, now_ms: int
) -> bool:
    a = aggregate
    if a.management_mode.value != "AUTO":
        return False
    if a.tp1_exchange_order_id is None or filled_quantity <= Decimal(
        str(row["payload"]["preview"].get("source_tp_filled_quantity", 0))
    ):
        return False
    delta = filled_quantity - a.tp1_filled_qty
    if (
        delta < 0
        or filled_quantity > a.tp1_target_qty
        or position_quantity != a.position_qty - delta
    ):
        return False
    own = [
        c
        for c in commands
        if getattr(c.payload, "owner_operation_id", None) == row["operation_id"]
    ]
    if any(
        c.status in {S.CLAIMED, S.OUTCOME_UNKNOWN}
        or c.kind in {K.OWNER_REDUCE, K.TAKE_PROFIT, K.EXIT}
        and c.status in {S.ACCEPTED, S.RECONCILED_ACCEPTED}
        for c in own
    ):
        return False
    owned_exit = (
        a.status is AggregateStatus.EXIT_PENDING
        and a.protection_operation_id == row["operation_id"]
        and a.protection_return_status is not None
    )
    unstarted_protection = (
        a.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
        and a.protection_operation_id == row["operation_id"]
        and any(c.kind is K.REPLACE_PROTECTION and c.status is S.PREPARED for c in own)
    )
    if (
        a.protection_operation_id == row["operation_id"]
        and not owned_exit
        and not unstarted_protection
    ):
        return False
    for c in own:
        if c.status is S.PREPARED:
            await uow.exchange_commands.mark_prepared_superseded(
                command_id=c.command_id,
                observed_at_ms=now_ms,
                reason="natural_tp_won_owner_operation",
            )
    if unstarted_protection:
        aborted_stop = ProtectionReplacementRejected(
            event_id=f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
            ticket_id=a.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=now_ms,
            reason="natural_tp_won_before_owner_stop_sent",
        )
        reduced_stop = reduce_event(a, aborted_stop)
        await uow.commit_reduction(
            event=aborted_stop, reduction=reduced_stop, expected_version=a.version
        )
        a = reduced_stop.aggregate
    if owned_exit:
        aborted = OwnerPositionExitAborted(
            event_id=f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
            ticket_id=a.identity.ticket_id,
            sequence=a.last_event_sequence + 1,
            occurred_at_ms=now_ms,
            operation_id=row["operation_id"],
        )
        reduced = reduce_event(a, aborted)
        await uow.commit_reduction(
            event=aborted, reduction=reduced, expected_version=a.version
        )
        a = reduced.aggregate
    event = OwnerOperationCommandObserved(
        event_id=f"event:{a.identity.ticket_id}:{a.last_event_sequence + 1}",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=now_ms,
        operation_id=row["operation_id"],
        command_id=own[0].command_id if own else row["operation_id"],
        outcome={
            "handoff": "original_tp_fill",
            "filled_quantity": str(filled_quantity),
            "position_quantity": str(position_quantity),
        },
    )
    await uow.commit_reduction(
        event=event, reduction=reduce_event(a, event), expected_version=a.version
    )
    await uow.owner_position_operations.transition(
        operation_id=row["operation_id"],
        expected_version=row["version"],
        state="handed_to_lifecycle",
        payload={**row["payload"], "handoff_tp_filled_quantity": str(filled_quantity)},
        reason="natural_tp_won_owner_operation",
        now_ms=now_ms,
        completed=True,
    )
    return True
