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
        purpose=operation["kind"],
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


async def setup_operation(e):
    from src.trading_kernel.infrastructure.pg_owner_device_repository import PostgresOwnerDeviceRepository
    from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
    from tests.trading_kernel.support.lifecycle import registered_sor_long_ticket, reach_position_protected
    from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
    import base64

    from cryptography.hazmat.primitives.asymmetric import ec

    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    key = ec.generate_private_key(ec.SECP256R1())
    k = key.public_key().public_numbers()
    enc = lambda n: (
        base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()
    )
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        g = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=5000
        )
        b = await r.bind(
            token=g,
            public_key={"kty": "EC", "crv": "P-256", "x": enc(k.x), "y": enc(k.y)},
            now_ms=5001,
        )
    async with PostgresKernelUnitOfWork(e) as u:
        a = await u.aggregates.get(t.identity.ticket_id)
        p = preview_owner_reduction(
            aggregate=a,
            facts=facts(a, observed_at_ms=6000, valid_until_ms=9000),
            requested_quantity=a.position_qty / 2,
            quantity_step=D(".0001"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            now_ms=6000,
        )
    return t, b, p, key


def preview(a=None):
    from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
    a = a or aggregate()
    return preview_owner_reduction(aggregate=a, facts=facts(a), requested_quantity=a.position_qty/2,
        quantity_step=D(".0001"), minimum_quantity=D(".0001"), minimum_notional=D(1), now_ms=3000)
