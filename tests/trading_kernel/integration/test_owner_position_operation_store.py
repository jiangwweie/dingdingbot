from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.infrastructure.pg_owner_position_operations import (
    PostgresOwnerPositionOperations,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.owner_reduction import facts

KEY = {
    "kty": "EC",
    "crv": "P-256",
    "x": "axfR8uEsQkf4vOblY6RA8ncDfYEt6zOg9KE5RdiYwpY",
    "y": "T-NC4v4af5uO5-tKfA-eFivOM1drMV7Oy7ZAaDe_UfU",
}


async def setup(e):
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


@pytest.mark.asyncio
async def test_operation_idempotency_and_durable_revision(head_template_engine):
    e = head_template_engine
    _t, b, p, _key = await setup(e)
    async with e.begin() as c:
        r = PostgresOwnerPositionOperations(c)
        op = await r.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=b["device_id"],
            device_epoch=1,
            idempotency_key="preview-1",
            now_ms=6000,
        )
        again = await r.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=b["device_id"],
            device_epoch=1,
            idempotency_key="preview-1",
            now_ms=6000,
        )
        assert again["operation_id"] == op["operation_id"]
        with pytest.raises(ValueError, match="idempotency_conflict"):
            await r.create_preview(
                preview=p.model_copy(update={"stop_price": D(59001)}),
                owner_identity="Owner",
                device_id=b["device_id"],
                device_epoch=1,
                idempotency_key="preview-1",
                now_ms=6000,
            )
    async with e.begin() as c:
        op2 = await PostgresOwnerPositionOperations(c).get(op["operation_id"])
        assert op2["payload"]["preview"]["reduction_quantity"] == str(
            p.reduction_quantity
        )
        assert op2["state"] == "previewed"


@pytest.mark.asyncio
async def test_submit_records_real_device_authority_but_not_exchange_command(
    head_template_engine,
):
    import sqlalchemy as sa

    from src.trading_kernel.infrastructure.pg_models import (
        exchange_commands,
        owner_authorizations,
    )

    e = head_template_engine
    _t, b, p, key = await setup(e)
    async with e.begin() as c:
        r = PostgresOwnerPositionOperations(c)
        op = await r.create_preview(
            preview=p,
            owner_identity="Owner",
            device_id=b["device_id"],
            device_epoch=1,
            idempotency_key="preview-1",
            now_ms=6000,
        )
        before = await c.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands)
        )
        from tests.trading_kernel.support.owner_reduction import accept_signed_operation

        accepted, proof = await accept_signed_operation(c, b, key, op, now_ms=7000)
        assert accepted["state"] == "accepted"
        auth = (
            (
                await c.execute(
                    sa.select(owner_authorizations).where(
                        owner_authorizations.c.authorization_id
                        == accepted["authorization_id"]
                    )
                )
            )
            .mappings()
            .one()
        )
        assert (
            auth["authentication_strength"] == "trusted_device_session"
            and auth["purpose"] == "position_reduce"
        )
        assert (
            await c.scalar(sa.select(sa.func.count()).select_from(exchange_commands))
            == before
        )
        again = await r.accept(
            operation_id=op["operation_id"],
            owner_identity="Owner",
            device_id=b["device_id"],
            device_epoch=1,
            idempotency_key="submit-1",
            now_ms=7100,
            proof=proof,
        )
        assert again["version"] == accepted["version"]
