"""Exact Owner reduction facts shared by unit and PG verification."""

from decimal import Decimal as D

from src.trading_kernel.domain.owner_reduction import OwnerReductionFacts
from src.trading_kernel.domain.trade_management import ManagementMode
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def aggregate():
    return position_protected_aggregate()


def facts(a=None, **changes):
    a = a or aggregate()
    values = {
        "ticket_id": a.identity.ticket_id,
        "management_revision": a.management_revision,
        "observed_at_ms": 3000,
        "valid_until_ms": 6000,
        "position_quantity": a.position_qty,
        "current_price": a.average_fill_price,
        "protection_order_id": a.active_stop_exchange_order_id,
        "protected_quantity": a.position_qty,
        "stop_price": a.active_stop_price,
        "tp_order_id": a.tp1_exchange_order_id,
        "tp_filled_quantity": a.tp1_filled_qty,
        "tp_state": "open",
        "reduction_state": "not_sent",
        "reduction_filled_quantity": D(0),
        "reduction_operation_id": "owner-reduce-1",
        "unresolved_other_command": False,
        "stop_triggered": False,
        "residual_orders": True,
        "management_mode": ManagementMode.AUTO,
    }
    return OwnerReductionFacts(**(values | changes))


async def accept_signed_operation(
    connection, device, key, operation, *, now_ms, idempotency_key="submit-1"
):
    """Exercise the same signed acceptance source as the mobile API."""
    from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
    from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
    from src.trading_kernel.infrastructure.pg_owner_device_repository import (
        PostgresOwnerDeviceRepository,
    )
    from src.trading_kernel.infrastructure.pg_owner_position_operations import (
        PostgresOwnerPositionOperations,
    )
    from tests.trading_kernel.support.owner_device import sign

    payload = {
        "operation_id": operation["operation_id"],
        "ticket_id": operation["ticket_id"],
        "expected_version": operation["version"],
    }
    repository = PostgresOwnerDeviceRepository(connection)
    nonce = await repository.issue_nonce(device["session_token"], now_ms=now_ms)
    proof = DeviceWriteProof(
        device_id=device["device_id"],
        device_epoch=device["device_epoch"],
        method="POST",
        path="/api/owner/v1/mobile/operations/submit",
        body_digest=canonical_digest(payload),
        nonce_id=nonce["nonce_id"],
        idempotency_key=idempotency_key,
        issued_at_ms=nonce["issued_at_ms"],
        expires_at_ms=nonce["expires_at_ms"],
    )
    await repository.authorize(
        token=device["session_token"],
        proof=proof,
        signature=sign(key, proof),
        body=payload,
        purpose="position_reduce",
        now_ms=now_ms,
    )
    accepted = await PostgresOwnerPositionOperations(connection).accept(
        operation_id=operation["operation_id"],
        owner_identity="Owner",
        device_id=device["device_id"],
        device_epoch=device["device_epoch"],
        idempotency_key=idempotency_key,
        proof=proof,
        now_ms=now_ms,
    )
    return accepted, proof
