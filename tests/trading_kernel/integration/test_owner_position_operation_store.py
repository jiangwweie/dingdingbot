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


@pytest.mark.asyncio
async def test_finished_reduction_releases_adjustment_but_keeps_audit(head_template_engine):
    from tests.trading_kernel.support.owner_reduction import accept_signed_operation
    from src.trading_kernel.domain.owner_reduction import OwnerReductionState, OwnerReductionPhase
    e = head_template_engine
    _t, b, p, key = await setup(e)
    async with e.begin() as c:
        r = PostgresOwnerPositionOperations(c)
        op = await r.create_preview(preview=p, owner_identity='Owner', device_id=b['device_id'],
            device_epoch=1, idempotency_key='preview-done', now_ms=6000)
        op, _ = await accept_signed_operation(c, b, key, op, now_ms=6001)
        s = OwnerReductionState.model_validate(op['payload']['reduction_state']).model_copy(update={
            'phase': OwnerReductionPhase.WAIT_PRICE, 'actual_reduction_quantity': p.reduction_quantity,
            'reduction_observed_at_ms': 6002})
        done = await r.save_state(operation_id=op['operation_id'], expected_version=op['version'],
            state=s, reason='actual_reduction_verified', next_check_at_ms=6002, now_ms=6002)
        assert done['completed_at_ms'] == 6002
        assert await r.active_for_ticket(p.ticket_id) is None
        assert (await r.get(op['operation_id']))['payload']['reduction_state']['actual_reduction_quantity'] == str(p.reduction_quantity)


@pytest.mark.asyncio
async def test_send_gate_honours_revocation_and_stale_operation_facts(head_template_engine):
    from src.trading_kernel.domain.commands import ExchangeCommand,ExchangeCommandKind as K,ExchangeCommandStatus as S,OrderCommandPayload
    from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
    from tests.trading_kernel.support.owner_reduction import accept_signed_operation
    import sqlalchemy as sa
    e=head_template_engine
    _t,b,p,key=await setup(e)
    async with e.begin() as c:
        r=PostgresOwnerPositionOperations(c)
        row=await r.create_preview(preview=p,owner_identity='Owner',device_id=b['device_id'],device_epoch=1,idempotency_key='send-gate',now_ms=6000)
        row,_=await accept_signed_operation(c,b,key,row,now_ms=6001)
        await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands').values(
            certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
        cid='owner-gated-command'
        from src.trading_kernel.infrastructure.pg_repositories import PostgresAggregateRepository
        a=await PostgresAggregateRepository(c).get(p.ticket_id)
        command=ExchangeCommand(command_id=cid,ticket_identity=a.identity,management_revision=a.management_revision,kind=K.OWNER_REDUCE,
            generation=1,idempotency_key=cid,venue_client_order_id='owner-gated-client',payload=OrderCommandPayload(side='sell',quantity=p.reduction_quantity,
            order_type='market',reduce_only=True,owner_operation_id=row['operation_id']),status=S.PREPARED,created_at_ms=6000,deadline_at_ms=30000)
        f=facts(a,observed_at_ms=6000,valid_until_ms=9000,tp_state='cancelled')
        row=await r.transition(operation_id=row['operation_id'],expected_version=row['version'],state='reduction_pending',
            payload={**row['payload'],'prepared_command_ids':[cid],'facts':f.model_dump(mode='json'),'protection_close_position':True},
            reason=None,now_ms=6002)
        assert await r.command_send_blocker(command,a,now_ms=6003) is None
        assert await r.command_send_blocker(command,a,now_ms=12000)=='owner_operation_facts_stale'
        await PostgresOwnerDeviceRepository(c).revoke(device_id=b['device_id'],now_ms=6004)
        assert await r.command_send_blocker(command,a,now_ms=6005)=='owner_operation_authority_revoked'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,preview_terms,current,proposed,reason',[
    ('manual_tp_set',{'price':D(63000),'quantity':D('.0002')},D(64000),D(63000),'owner_tp_target_crossed'),
    ('protection_tighten',{'price':D(59500)},D(59400),D(59500),'owner_new_stop_crossed'),
])
async def test_real_send_gate_rechecks_proposed_instruction_price(head_template_engine,kind,preview_terms,current,proposed,reason):
    from src.trading_kernel.domain.owner_position_operation import preview_position_operation
    from src.trading_kernel.domain.commands import ExchangeCommand,ExchangeCommandKind as K,ExchangeCommandStatus as S,OrderCommandPayload
    from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
    from tests.trading_kernel.support.owner_reduction import accept_signed_operation
    import sqlalchemy as sa
    e=head_template_engine;_t,b,_p,key=await setup(e)
    async with PostgresKernelUnitOfWork(e) as u:a=await u.aggregates.get(_t.identity.ticket_id)
    p=preview_position_operation(aggregate=a,facts=facts(a,observed_at_ms=6000,valid_until_ms=9000),kind=kind,
        quantity_step=D('.0001'),price_tick=D('.1'),minimum_quantity=D('.0001'),minimum_notional=D(1),now_ms=6000,**preview_terms)
    async with e.begin() as c:
        r=PostgresOwnerPositionOperations(c)
        row=await r.create_preview(preview=p,owner_identity='Owner',device_id=b['device_id'],device_epoch=1,idempotency_key='send-price',now_ms=6000)
        row,_=await accept_signed_operation(c,b,key,row,now_ms=6001)
        await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands')
            .values(certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
        conditional=kind=='protection_tighten'
        payload=OrderCommandPayload(side='sell',quantity=a.position_qty if conditional else p.quantity,reduce_only=True,
            order_type='stop_market' if conditional else 'limit',stop_price=proposed if conditional else None,
            limit_price=None if conditional else proposed,time_in_force=None if conditional else 'GTC',owner_operation_id=row['operation_id'],
            replaces_exchange_order_id=a.active_stop_exchange_order_id if conditional else None,source_watermark_ms=7000 if conditional else None)
        command=ExchangeCommand(command_id='proposed',ticket_identity=a.identity,management_revision=a.management_revision,
            kind=K.REPLACE_PROTECTION if conditional else K.TAKE_PROFIT,generation=1,idempotency_key='proposed',venue_client_order_id='proposed-client',
            payload=payload,status=S.PREPARED,created_at_ms=7000,deadline_at_ms=30000)
        await r.transition(operation_id=row['operation_id'],expected_version=row['version'],state='tp_pending',
            payload={**row['payload'],'prepared_command_ids':['proposed'],'facts':facts(a,current_price=current,
                observed_at_ms=7000,valid_until_ms=10000).model_dump(mode='json')},reason=None,now_ms=7000)
        assert await r.command_send_blocker(command,a,now_ms=7100)==reason
