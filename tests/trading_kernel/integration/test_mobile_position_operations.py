"""Phone requests use server facts and signed receipts; fixture venue never sends orders."""
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient

from src.trading_kernel.application.advance_owner_position_operation import advance_owner_position_operation
from src.trading_kernel.application.owner_operation_facts import OwnerPositionObservation
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_signal_repository import PostgresSignalRepository
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.owner_console_http.routes.mobile import router,COOKIE
from tests.trading_kernel.support.owner_reduction import setup_operation,facts
from tests.trading_kernel.support.owner_device import sign


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,params',[
    ('position_reduce',{'quantity':'.0005'}),
    ('protection_tighten',{'price':'59500'}),
    ('manual_tp_set',{'price':'63000','quantity':'.0002'}),
    ('position_close',{}),
])
async def test_mobile_preview_submit_and_lost_response_receipt(head_template_engine,monkeypatch,kind,params):
    e=head_template_engine
    t,device,_p,key=await setup_operation(e)
    monkeypatch.setattr(PostgresSignalRepository,'get_instrument_rules',AsyncMock(return_value=SimpleNamespace(
        quantity_step=D('.0001'),min_quantity=D('.0001'),min_notional=D(1),price_tick=D('.1'))))
    app=FastAPI()
    app.state.owner_console_settings=SimpleNamespace(public_host='owner.test',public_origin='https://owner.test',
        venue_id=t.identity.netting_domain.venue_id,account_id=t.identity.netting_domain.account_id)
    app.state.owner_control_engine=e
    now=6500
    app.state.owner_clock_ms=lambda:now
    app.include_router(router)
    class Source:
        async def read_owner_position(self,*,aggregate,**kwargs):
            return OwnerPositionObservation(facts=facts(aggregate,observed_at_ms=7000,valid_until_ms=10000),
                protection_close_position=False,orders=())
    async with AsyncClient(transport=ASGITransport(app=app),base_url='https://owner.test') as client:
        client.cookies.set(COOKIE,device['session_token'],domain='owner.test',path='/')
        body={'ticket_id':t.identity.ticket_id,'kind':kind,'idempotency_key':'phone-preview',**params}
        assert (await client.post('/api/owner/v1/mobile/operations/preview',json=body,headers={'origin':'https://owner.test'})).status_code==409
        async with e.begin() as c:
            await c.execute(sa.update(runtime_capabilities_current).where(runtime_capabilities_current.c.capability_key=='exchange_commands').values(certification={'product_id':'brc-app-manual-v1','owner_cooperation':'owner-cooperation-v1'}))
        r=await client.post('/api/owner/v1/mobile/operations/preview',json=body,headers={'origin':'https://owner.test'})
        assert r.status_code==200,r.text
        op=r.json()
        factory=lambda:PostgresKernelUnitOfWork(e)
        assert await advance_owner_position_operation(factory,Source(),now_ms=7000,timeout_seconds=1,
            runtime_commit='kernel-test-head',schema_revision=CURRENT_SCHEMA_REVISION)=='previewed'
        ready=(await client.get('/api/owner/v1/mobile/operations/'+op['operation_id'])).json()
        assert ready['version']==2 and D(ready['preview']['source_quantity'])==t.quantity
        now=7100
        nonce=(await client.post('/api/owner/v1/mobile/nonces',json={},headers={'origin':'https://owner.test'})).json()
        payload={'operation_id':op['operation_id'],'ticket_id':t.identity.ticket_id,'expected_version':ready['version']}
        proof=DeviceWriteProof(device_id=device['device_id'],device_epoch=1,method='POST',path='/api/owner/v1/mobile/operations/submit',
            body_digest=canonical_digest(payload),nonce_id=nonce['nonce_id'],idempotency_key='phone-submit',
            issued_at_ms=nonce['issued_at_ms'],expires_at_ms=nonce['expires_at_ms'])
        packet={'proof':proof.model_dump(mode='json'),'signature':sign(key,proof),'payload':payload}
        response=await client.post(proof.path,json=packet,headers={'origin':'https://owner.test'})
        assert response.status_code==200,response.text
        assert response.json()['state']=='accepted'
        receipt=(await client.get('/api/owner/v1/mobile/requests/phone-submit?nonce_id='+nonce['nonce_id'])).json()
        assert receipt['state']=='completed' and receipt['result']==response.json()
        repeated=await client.post(proof.path,json=packet,headers={'origin':'https://owner.test'})
        assert repeated.status_code==200 and repeated.json()==response.json()
