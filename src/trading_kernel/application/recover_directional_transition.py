"""Finish one pending control after a separately resolved ENTRY's window closes."""

from __future__ import annotations

import asyncio

from src.trading_kernel.application.ports import (
    UnitOfWorkFactory,
    VenueTruthPort,
    VenueTruthRequest,
)
from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
from src.trading_kernel.domain.commands import ExchangeCommandStatus
from src.trading_kernel.domain.venue_truth import (
    VenueLookupStatus,
    order_identity_contradiction,
)


async def recover_directional_transition_once(
    uow_factory: UnitOfWorkFactory,
    venue: VenueTruthPort,
    *,
    now_ms: int,
    timeout_seconds: float,
    worker_id: str,
    runtime_commit: str,
    schema_revision: str,
) -> bool:
    async with uow_factory() as uow:
        command_id = await uow.directional_risk.next_resolved_send()
        if command_id is None:
            return False
        command = await uow.exchange_commands.get(command_id)
        expires = await uow.directional_risk.send_expiry(command_id)
    if command is None or expires is None or command.venue_client_order_id is None:
        raise RuntimeError("resolved ENTRY send authority has no exact command")
    if not await runtime_writer_is_certified(
        uow_factory,
        worker_id=worker_id,
        runtime_commit=runtime_commit,
        schema_revision=schema_revision,
        observed_at_ms=now_ms,
    ):
        return False
    domain = command.ticket_identity.netting_domain
    try:
        truth = await asyncio.wait_for(
            venue.lookup_command_truth(
                VenueTruthRequest(
                    command_id=command_id,
                    kind=command.kind,
                    venue_id=domain.venue_id,
                    account_id=domain.account_id,
                    exchange_instrument_id=domain.exchange_instrument_id,
                    position_side=domain.position_side,
                    venue_client_order_id=command.venue_client_order_id,
                    payload=command.payload,
                    observed_at_ms=now_ms,
                    entry_window_expires_at_ms=expires,
                )
            ),
            timeout=timeout_seconds,
        )
    except Exception:  # noqa: BLE001 - failed readonly proof leaves the control pending.
        return False
    if (
        truth.exchange_observed_at_ms is None
        or truth.exchange_observed_at_ms <= expires
    ):
        return False
    accepted = command.status in {
        ExchangeCommandStatus.ACCEPTED,
        ExchangeCommandStatus.RECONCILED_ACCEPTED,
    }
    if accepted:
        if truth.lookup_status is not VenueLookupStatus.VISIBLE or truth.order is None:
            return False
        if order_identity_contradiction(command, truth.order) is not None:
            return False
    elif (
        truth.lookup_status is not VenueLookupStatus.ABSENT
        or truth.position_quantity
        or truth.matching_fill_quantity
        or command.venue_client_order_id
        in (
            *truth.regular_open_client_order_ids,
            *truth.conditional_open_client_order_ids,
        )
    ):
        return False
    async with uow_factory() as uow:
        await uow.directional_risk.lock(domain.venue_id, domain.account_id)
        current = await uow.exchange_commands.get(command_id)
        if current is None or current.status != command.status:
            return False
        await uow.directional_risk.recover_resolved_sends(
            domain.venue_id,
            domain.account_id,
            command_id=command_id,
            exchange_time_ms=truth.exchange_observed_at_ms,
            observed_at_ms=now_ms,
        )
        await uow.directional_risk.progress(domain.venue_id, domain.account_id, now_ms)
    return True
