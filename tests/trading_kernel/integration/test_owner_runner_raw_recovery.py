"""Real PG Runner state traverses raw readers, signed mobile intent and dispatch."""

from decimal import Decimal as D

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.advance_owner_position_operation import (
    advance_owner_position_operation,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.command_dispatch import dispatch_for_ticket
from tests.trading_kernel.support.lifecycle import (
    reach_runner_protected,
    registered_sor_long_ticket,
)
from tests.trading_kernel.support.mobile_owner import mobile_client
from tests.trading_kernel.support.owner_device import sign
from tests.trading_kernel.support.owner_raw_protocol import RawOwnerProtocol


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', [None, 'missing_stop'])
async def test_runner_raw_preview_reduction_and_restart_continue_automation(head_template_engine, fault):
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_runner_protected(e, t)
    factory = lambda: PostgresKernelUnitOfWork(e)
    async with factory() as u:
        before = await u.aggregates.get(t.identity.ticket_id)
        assert before.status.value == 'runner_protected'
        assert before.tp1_exchange_order_id is None and before.tp1_filled_qty > 0
    async with e.begin() as c:
        await c.execute(sa.update(runtime_capabilities_current).where(
            runtime_capabilities_current.c.capability_key == 'exchange_commands').values(
                certification={'product_id': 'brc-app-manual-v1', 'owner_cooperation': 'owner-cooperation-v1'}))
    from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
    async with factory() as u:
        await u.signals.upsert_instrument_rules(venue_id=t.identity.netting_domain.venue_id,
            exchange_instrument_id=t.identity.netting_domain.exchange_instrument_id,
            quantity_step=D('.0001'), price_tick=D('.1'), min_quantity=D('.0001'), min_notional=D(1),
            exchange_max_leverage=10, maintenance_margin_brackets=(MaintenanceMarginBracket(
                bracket_id='test:1', notional_floor=D(0), notional_cap=None,
                maintenance_margin_rate=D('.004'), maintenance_amount=D(0)),),
            maintenance_margin_brackets_digest='sha256:'+'5'*64,
            notional_coefficient=D(1), notional_coefficient_certified=True,
            observed_at_ms=5000, valid_until_ms=100000)
    source = RawOwnerProtocol(e, before.position_qty)
    source.fault = fault
    async with mobile_client(e, at_ms=6000) as (client, app, key, device):
        app.state.owner_console_settings.account_id = t.identity.netting_domain.account_id
        result = await client.post('/api/owner/v1/mobile/operations/preview',
            json={'kind': 'position_reduce', 'ticket_id': t.identity.ticket_id,
                  'quantity': str(before.position_qty / 2), 'idempotency_key': 'runner-preview'},
            headers={'origin': 'https://owner.test'})
        assert result.status_code == 200, result.text
        op = result.json()
        async def tick(at):
            source.at = at
            return await advance_owner_position_operation(factory, source, now_ms=at,
                timeout_seconds=2, runtime_commit='kernel-test-head', schema_revision=CURRENT_SCHEMA_REVISION)
        outcome = await tick(7000)
        async with factory() as u:
            op = await u.owner_position_operations.get(op['operation_id'])
        if fault:
            assert outcome == 'rejected' and op['completed_at_ms'] is not None
            assert op['first_blocker'].startswith('preview:owner_stop_snapshot')
            assert not source.writes
            async with factory() as u:
                assert not [c for c in await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
                    if c.kind is K.OWNER_REDUCE]
            return
        assert outcome == 'previewed', op['first_blocker']
        assert op['payload']['preview']['continue_runner']
        assert D(op['payload']['preview']['source_tp_filled_quantity']) == before.tp1_filled_qty
        app.state.owner_clock_ms = lambda: 7100
        nonce = (await client.post('/api/owner/v1/mobile/nonces', json={},
            headers={'origin': 'https://owner.test'})).json()
        payload = {'operation_id': op['operation_id'], 'ticket_id': t.identity.ticket_id,
            'expected_version': op['version']}
        proof = DeviceWriteProof(device_id=device['device_id'], device_epoch=device['device_epoch'],
            method='POST', path='/api/owner/v1/mobile/operations/submit', body_digest=canonical_digest(payload),
            nonce_id=nonce['nonce_id'], idempotency_key='runner-submit',
            issued_at_ms=nonce['issued_at_ms'], expires_at_ms=nonce['expires_at_ms'])
        response = await client.post(proof.path,
            json={'proof': proof.model_dump(mode='json'), 'signature': sign(key, proof), 'payload': payload},
            headers={'origin': 'https://owner.test'})
        assert response.status_code == 200, response.text
        assert response.json()['state'] == 'accepted'
        for at in range(8000, 15000, 1000):
            outcome = await tick(at)
            async with factory() as u:
                commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
                pending = [c for c in commands if c.status.value == 'prepared']
            for _ in pending:
                source.at = at + 100
                await dispatch_for_ticket(e, source, t.identity.ticket_id, now_ms=source.at)
            if outcome == 'completed':
                break
        async with factory() as u:
            after = await u.aggregates.get(t.identity.ticket_id)
            op = await u.owner_position_operations.get(op['operation_id'])
            commands = await u.exchange_commands.list_for_ticket(t.identity.ticket_id)
            assert outcome == 'completed' and op['state'] == 'runner_continuing', op['first_blocker']
            assert op['completed_at_ms'] is not None
            assert after.status.value == 'runner_protected' and after.management_mode.value == 'AUTO'
            assert after.tp1_filled_qty == before.tp1_filled_qty
            assert after.position_qty == source.quantity < before.position_qty
            assert after.protected_qty == after.position_qty and after.active_stop_close_position
            assert len([c for c in commands if c.kind is K.OWNER_REDUCE]) == 1
        assert await tick(16000) is None
        assert len([r for r in source.writes if r.kind is K.OWNER_REDUCE]) == 1
