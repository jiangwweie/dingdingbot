"""Real local PG routes use independent trusted registration, never TOTP."""

import base64
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.owner_device_credentials import (
    write_proof_message,
)
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.owner_console_http.routes.mobile import router


def enc(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.mark.asyncio
async def test_mobile_bind_control_and_replay_requires_device_proof(
    head_template_engine,
):
    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="mobile-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
    async with e.begin() as c:
        await c.execute(
            sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true")
        )
    key = ec.generate_private_key(ec.SECP256R1())
    p = key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": enc(p.x.to_bytes(32, "big")),
        "y": enc(p.y.to_bytes(32, "big")),
    }
    async with e.begin() as c:
        grant = await PostgresOwnerDeviceRepository(c).issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=2000
        )
    app = FastAPI()
    app.state.owner_console_settings = SimpleNamespace(
        public_host="owner.test",
        public_origin="https://owner.test",
        owner_policy_id="policy-main",
        account_id="mobile-account",
        venue_id="binance-usdm",
    )
    app.state.owner_control_engine = e
    app.state.owner_clock_ms = lambda: 3000
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://owner.test"
    ) as client:
        assert (await client.get("/api/owner/v1/mobile/controls")).status_code == 401
        bound = await client.post(
            "/api/owner/v1/mobile/devices/bind",
            json={"token": grant, "public_key": jwk},
            headers={"origin": "https://owner.test"},
        )
        assert bound.status_code == 200, bound.text
        assert (
            "HttpOnly" in bound.headers["set-cookie"]
            and "Secure" in bound.headers["set-cookie"]
        )
        s = (await client.get("/api/owner/v1/mobile/session")).json()
        controls = (await client.get("/api/owner/v1/mobile/controls")).json()
        assert controls["global"]["new_entry_submit_enabled"] is True
        nonce = (
            await client.post(
                "/api/owner/v1/mobile/nonces", headers={"origin": "https://owner.test"}
            )
        ).json()
        payload = {
            "owner_policy_id": "policy-main",
            "enabled": False,
            "expected_version": controls["global"]["policy_version"],
        }
        proof = DeviceWriteProof(
            device_id=s["device_id"],
            device_epoch=s["device_epoch"],
            method="POST",
            path="/api/owner/v1/mobile/controls/global",
            body_digest=canonical_digest(payload),
            nonce_id=nonce["nonce_id"],
            idempotency_key="mobile-resume-1",
            issued_at_ms=nonce["issued_at_ms"],
            expires_at_ms=nonce["expires_at_ms"],
        )
        a, b = decode_dss_signature(
            key.sign(write_proof_message(proof), ec.ECDSA(hashes.SHA256()))
        )
        signature = enc(a.to_bytes(32, "big") + b.to_bytes(32, "big"))
        body = {
            "proof": proof.model_dump(mode="json"),
            "signature": signature,
            "payload": payload,
        }
        result = await client.post(
            proof.path, json=body, headers={"origin": "https://owner.test"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["enabled"] is False
        replay = await client.post(
            proof.path, json=body, headers={"origin": "https://owner.test"}
        )
        assert replay.status_code == 200
        assert replay.json() == result.json()
        receipt = await client.get("/api/owner/v1/mobile/requests/mobile-resume-1")
        assert receipt.json() == {"state": "completed", "result": result.json()}
        assert (
            await client.get("/api/owner/v1/mobile/requests/not-submitted")
        ).json() == {"state": "pending"}
        unused = (
            await client.post(
                "/api/owner/v1/mobile/nonces", headers={"origin": "https://owner.test"}
            )
        ).json()
        app.state.owner_clock_ms = lambda: 64000
        not_accepted = await client.get(
            "/api/owner/v1/mobile/requests/not-submitted",
            params={"nonce_id": unused["nonce_id"]},
        )
        assert not_accepted.json() == {"state": "not_accepted"}
        app.state.owner_clock_ms = lambda: 3000
        wrong = await client.post(
            "/api/owner/v1/mobile/nonces", headers={"origin": "https://other.test"}
        )
        assert wrong.status_code == 403


@pytest.mark.asyncio
async def test_mobile_orders_distinguishes_empty_missing_and_stale(
    head_template_engine,
):
    from tests.trading_kernel.support.lifecycle import (
        reach_position_protected,
        registered_sor_long_ticket,
    )

    e = head_template_engine
    ticket = registered_sor_long_ticket()
    app = FastAPI()
    app.state.owner_console_settings = SimpleNamespace(
        public_host="owner.test",
        public_origin="https://owner.test",
        owner_policy_id="policy-main",
        account_id=ticket.identity.netting_domain.account_id,
        venue_id="binance-usdm",
    )
    app.state.owner_control_engine = e
    app.state.owner_clock_ms = lambda: 3000
    app.include_router(router)
    from tests.trading_kernel.support.owner_device import keypair

    _, jwk = keypair()
    async with e.begin() as c:
        grant = await PostgresOwnerDeviceRepository(c).issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=1000
        )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://owner.test"
    ) as client:
        result = await client.post(
            "/api/owner/v1/mobile/devices/bind",
            json={"token": grant, "public_key": jwk},
            headers={"origin": "https://owner.test"},
        )
        assert result.status_code == 200
        empty_orders = await client.get("/api/owner/v1/mobile/orders")
        assert empty_orders.status_code == 200
        assert (
            empty_orders.json()["status"] == "ready"
            and empty_orders.json()["items"] == []
        )
        await reach_position_protected(e, ticket)
        missing = await client.get("/api/owner/v1/mobile/orders")
        assert missing.status_code == 200 and missing.json()["status"] == "unavailable"
        assert missing.json()["unavailable_ticket_ids"] == [ticket.identity.ticket_id]
        from src.trading_kernel.infrastructure.pg_management_repository import (
            PostgresManagementRepository,
        )

        async with e.begin() as c:
            await PostgresManagementRepository(c).save_coverage(
                ticket.identity.ticket_id,
                complete=True,
                reason=None,
                current_complete=True,
                attribution_complete=True,
                through_ms=3000,
                observed_at_ms=3000,
            )
        available = await client.get("/api/owner/v1/mobile/orders")
        assert available.json()["status"] == "ready"
        app.state.owner_clock_ms = lambda: 34001
        stale = await client.get("/api/owner/v1/mobile/orders")
        assert stale.json()["status"] == "unavailable"


@pytest.mark.asyncio
async def test_repeated_same_state_has_explicit_no_change_receipt(head_template_engine):
    from src.trading_kernel.infrastructure.pg_models import owner_device_write_evidence
    from tests.trading_kernel.support.owner_device import keypair, sign

    e = head_template_engine
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="mobile-account",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
    key, jwk = keypair()
    async with e.begin() as c:
        grant = await PostgresOwnerDeviceRepository(c).issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=2000
        )
    app = FastAPI()
    app.state.owner_console_settings = SimpleNamespace(
        public_host="owner.test",
        public_origin="https://owner.test",
        owner_policy_id="policy-main",
        account_id="mobile-account",
        venue_id="binance-usdm",
    )
    app.state.owner_control_engine = e
    app.state.owner_clock_ms = lambda: 3000
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://owner.test"
    ) as client:
        bind = (
            await client.post(
                "/api/owner/v1/mobile/devices/bind",
                json={"token": grant, "public_key": jwk},
                headers={"origin": "https://owner.test"},
            )
        ).json()
        controls = (await client.get("/api/owner/v1/mobile/controls")).json()
        nonce = (
            await client.post(
                "/api/owner/v1/mobile/nonces", headers={"origin": "https://owner.test"}
            )
        ).json()
        payload = {
            "owner_policy_id": "policy-main",
            "enabled": False,
            "expected_version": controls["global"]["policy_version"],
        }
        proof = DeviceWriteProof(
            device_id=bind["device_id"],
            device_epoch=1,
            method="POST",
            path="/api/owner/v1/mobile/controls/global",
            body_digest=canonical_digest(payload),
            nonce_id=nonce["nonce_id"],
            idempotency_key="no-change-1",
            issued_at_ms=nonce["issued_at_ms"],
            expires_at_ms=nonce["expires_at_ms"],
        )
        body = {
            "proof": proof.model_dump(mode="json"),
            "signature": sign(key, proof),
            "payload": payload,
        }
        result = await client.post(
            proof.path, json=body, headers={"origin": "https://owner.test"}
        )
        assert result.status_code == 200, result.text
        async with e.connect() as c:
            receipt = (
                (await c.execute(sa.select(owner_device_write_evidence)))
                .mappings()
                .one()
            )
            assert (
                receipt["result_kind"] == "no_change"
                and receipt["result_payload"] == result.json()
            )
        assert (
            await client.post(
                proof.path, json=body, headers={"origin": "https://owner.test"}
            )
        ).json() == result.json()


@pytest.mark.asyncio
async def test_binding_failure_limit_persists_and_cannot_be_bypassed_by_new_token(
    head_template_engine,
):
    from tests.trading_kernel.support.owner_device import keypair

    e = head_template_engine
    _, jwk = keypair()
    app = FastAPI()
    app.state.owner_console_settings = SimpleNamespace(
        public_host="owner.test", public_origin="https://owner.test"
    )
    app.state.owner_control_engine = e
    now = [1000]
    app.state.owner_clock_ms = lambda: now[0]
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://owner.test"
    ) as client:
        for _ in range(5):
            failed = await client.post(
                "/api/owner/v1/mobile/devices/bind",
                json={"token": "A" * 43, "public_key": jwk},
                headers={"origin": "https://owner.test"},
            )
            assert failed.status_code == 403
            now[0] += 1
        limited = await client.post(
            "/api/owner/v1/mobile/devices/bind",
            json={"token": "B" * 43, "public_key": jwk},
            headers={"origin": "https://owner.test"},
        )
        assert limited.status_code == 429
        async with e.begin() as c:
            grant = await PostgresOwnerDeviceRepository(c).issue_binding(
                owner_identity="Owner", replace_device=False, now_ms=now[0]
            )
        assert (
            await client.post(
                "/api/owner/v1/mobile/devices/bind",
                json={"token": grant, "public_key": jwk},
                headers={"origin": "https://owner.test"},
            )
        ).status_code == 429
        now[0] += 900001
        async with e.begin() as c:
            grant = await PostgresOwnerDeviceRepository(c).issue_binding(
                owner_identity="Owner", replace_device=False, now_ms=now[0]
            )
        assert (
            await client.post(
                "/api/owner/v1/mobile/devices/bind",
                json={"token": grant, "public_key": jwk},
                headers={"origin": "https://owner.test"},
            )
        ).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('submitted',[False,True,'pending'])
async def test_rebound_owner_can_resolve_old_session_request_without_erasing_accepted_intent(head_template_engine,submitted):
    from tests.trading_kernel.support.owner_device import keypair, sign
    e=head_template_engine;key,jwk=keypair();_,new_jwk=keypair()
    async with PostgresKernelUnitOfWork(e) as u:
        await seed_runtime_authority(u,RuntimeAuthoritySeedRequest(account_id='mobile-account',runtime_commit='a'*40,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=1000))
    async with e.begin() as c:
        grant=await PostgresOwnerDeviceRepository(c).issue_binding(owner_identity='Owner',replace_device=False,now_ms=2000)
    app=FastAPI();app.state.owner_console_settings=SimpleNamespace(public_host='owner.test',public_origin='https://owner.test',owner_policy_id='policy-main',account_id='mobile-account',venue_id='binance-usdm')
    app.state.owner_control_engine=e;now=[3000];app.state.owner_clock_ms=lambda:now[0];app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='https://owner.test') as client:
        old=(await client.post('/api/owner/v1/mobile/devices/bind',json={'token':grant,'public_key':jwk},headers={'origin':'https://owner.test'})).json()
        nonce=(await client.post('/api/owner/v1/mobile/nonces',headers={'origin':'https://owner.test'})).json()
        controls=(await client.get('/api/owner/v1/mobile/controls')).json()
        p={'owner_policy_id':'policy-main','enabled':False,'expected_version':controls['global']['policy_version']}
        proof=DeviceWriteProof(device_id=old['device_id'],device_epoch=old['device_epoch'],method='POST',path='/api/owner/v1/mobile/controls/global',body_digest=canonical_digest(p),nonce_id=nonce['nonce_id'],idempotency_key='before-rebind',issued_at_ms=nonce['issued_at_ms'],expires_at_ms=nonce['expires_at_ms'])
        if submitted=='pending':
            async with e.begin() as c:
                await PostgresOwnerDeviceRepository(c).authorize(token=client.cookies.get('__Host-brc_device_session'),proof=proof,
                    signature=sign(key,proof),body=p,purpose='entry_pause',now_ms=now[0])
        elif submitted:
            response=await client.post(proof.path,json={'proof':proof.model_dump(mode='json'),'signature':sign(key,proof),'payload':p},headers={'origin':'https://owner.test'})
            assert response.status_code==200
        now[0]=4000
        async with e.begin() as c:
            grant=await PostgresOwnerDeviceRepository(c).issue_binding(owner_identity='Owner',replace_device=True,now_ms=now[0])
        rebound=await client.post('/api/owner/v1/mobile/devices/bind',json={'token':grant,'public_key':new_jwk},headers={'origin':'https://owner.test'})
        assert rebound.status_code==200
        receipt=await client.get('/api/owner/v1/mobile/requests/before-rebind',params={'nonce_id':nonce['nonce_id']})
        assert receipt.json()['state']==('pending' if submitted=='pending' else 'completed' if submitted else 'not_accepted')
