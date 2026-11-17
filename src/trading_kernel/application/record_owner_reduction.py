"""Record only exact accepted Owner close fills; never issue exchange commands."""

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.events import OwnerReductionRecorded
from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
from src.trading_kernel.domain.reducer import reduce_event


async def record_owner_reduction(
    uow: KernelUnitOfWork, *, proof: OwnerReductionProof, now_ms: int
) -> str:
    a = await uow.aggregates.get_for_update(proof.ticket_id)
    if (
        a is None
        or a.identity.netting_domain != proof.domain
        or not proof.observed_at_ms <= now_ms < proof.valid_until_ms
    ):
        raise ValueError("owner_reduction_source_mismatch")
    authorization = await uow.owner_controls.get_authorization(proof.authorization_id)
    if (
        authorization is None
        or authorization.purpose != "position_reduce"
        or authorization.authentication_strength != "trusted_device_session"
        or authorization.target_scope.get("ticket_id") != proof.ticket_id
        or authorization.target_scope.get("operation_id") != proof.operation_id
        or authorization.target_scope.get("management_revision")
        != a.management_revision
    ):
        raise ValueError("owner_reduction_authority_mismatch")
    command = await uow.exchange_commands.get(proof.command_id)
    if (
        command is None
        or command.ticket_identity != a.identity
        or command.kind is not ExchangeCommandKind.OWNER_REDUCE
        or command.status
        not in {
            ExchangeCommandStatus.ACCEPTED,
            ExchangeCommandStatus.RECONCILED_ACCEPTED,
        }
        or command.venue_client_order_id != proof.venue_client_order_id
        or not isinstance(command.payload, OrderCommandPayload)
        or command.payload.quantity != proof.requested_quantity
        or command.payload.owner_operation_id != proof.operation_id
    ):
        raise ValueError("owner_reduction_command_not_verified")
    rows = await uow.management.command_rows_for_order(
        proof.ticket_id, "regular", proof.exchange_order_id
    )
    if not any(
        r["command_id"] == proof.command_id
        and r["result_payload"].get("exchange_order_id") == proof.exchange_order_id
        for r in rows
    ):
        raise ValueError("owner_reduction_order_not_bound")
    # Idempotency is the persisted source event, not a price/quantity coincidence.
    prior = await uow.events.list_for_ticket(proof.ticket_id)
    previous = next(
        (
            x
            for x in prior
            if isinstance(x, OwnerReductionRecorded)
            and x.command_id == proof.command_id
        ),
        None,
    )
    if previous is not None:
        if previous.proof_digest != proof.digest():
            raise ValueError("owner_reduction_changed_proof")
        return "already_recorded"
    if a.position_qty != proof.source_quantity:
        raise ValueError("owner_reduction_position_changed")
    proof.require_source(a)
    event = OwnerReductionRecorded(
        event_id=f"event:{proof.ticket_id}:{a.last_event_sequence + 1}",
        ticket_id=proof.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=now_ms,
        operation_id=proof.operation_id,
        command_id=proof.command_id,
        exchange_order_id=proof.exchange_order_id,
        filled_quantity=proof.executed_quantity,
        average_fill_price=proof.average_price,
        remaining_quantity=proof.remaining_quantity,
        original_tp_order_id=proof.original_tp_order_id,
        original_tp_price=(
            None
            if proof.source_stage == "runner"
            else a.owner_reduction_context.original_tp_price
            if a.owner_reduction_context is not None
            else a.post_fill_exit_plan.tp_price
            if a.post_fill_exit_plan
            else a.ticket.take_profit_prices[0]
        ),
        protection_order_id=proof.protection_order_id,
        protection_price=proof.protection_price,
        proof_digest=proof.digest(),
        proof=proof,
    )
    await uow.commit_reduction(
        event=event, reduction=reduce_event(a, event), expected_version=a.version
    )
    return "recorded"
