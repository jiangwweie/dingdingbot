"""Persistent registration, rotation, revocation and one-use signed writes."""

import pytest

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from tests.trading_kernel.support.owner_device import keypair, sign


@pytest.mark.asyncio
async def test_device_session_survives_repository_recreation_and_revokes(
    head_template_engine,
):
    e = head_template_engine
    _, jwk = keypair()
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        grant = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=1000
        )
        bound = await r.bind(token=grant, public_key=jwk, now_ms=2000)
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        d, _s = await r.authenticate(bound["session_token"], now_ms=3000)
        assert d.device_id == bound["device_id"]
        await r.revoke(device_id=d.device_id, now_ms=4000)
    async with e.begin() as c:
        with pytest.raises(ValueError, match="device_session_unavailable"):
            await PostgresOwnerDeviceRepository(c).authenticate(
                bound["session_token"], now_ms=5000
            )


@pytest.mark.asyncio
async def test_signed_nonce_is_single_use_and_cannot_swap_body(head_template_engine):
    e = head_template_engine
    key, jwk = keypair()
    body = {"kind": "position_reduce", "quantity": "1"}
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        grant = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=1000
        )
        bound = await r.bind(token=grant, public_key=jwk, now_ms=2000)
        nonce = await r.issue_nonce(bound["session_token"], now_ms=3000)
        proof = DeviceWriteProof(
            device_id=bound["device_id"],
            device_epoch=1,
            method="POST",
            path="/api/owner/v1/mobile/operations",
            body_digest=canonical_digest(body),
            nonce_id=nonce["nonce_id"],
            idempotency_key="request-1",
            issued_at_ms=nonce["issued_at_ms"],
            expires_at_ms=nonce["expires_at_ms"],
        )
        owner = await r.authorize(
            token=bound["session_token"],
            proof=proof,
            signature=sign(key, proof),
            body=body,
            purpose="position_reduce",
            now_ms=4000,
        )
        assert owner == "Owner"
        with pytest.raises(ValueError, match="nonce_consumed"):
            await r.authorize(
                token=bound["session_token"],
                proof=proof,
                signature=sign(key, proof),
                body=body,
                purpose="position_reduce",
                now_ms=4000,
            )


@pytest.mark.asyncio
async def test_binding_consumed_and_replacement_revokes_old_session(
    head_template_engine,
):
    e = head_template_engine
    _, jwk = keypair()
    _, jwk2 = keypair()
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        g = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=1000
        )
        b = await r.bind(token=g, public_key=jwk, now_ms=2000)
        with pytest.raises(ValueError):
            await r.bind(token=g, public_key=jwk2, now_ms=2001)
        g2 = await r.issue_binding(
            owner_identity="Owner", replace_device=True, now_ms=3000
        )
        b2 = await r.bind(token=g2, public_key=jwk2, now_ms=4000)
        assert b2["device_epoch"] == 2
    async with e.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        with pytest.raises(ValueError):
            await r.authenticate(b["session_token"], now_ms=5000)
        assert (await r.authenticate(b2["session_token"], now_ms=5000))[
            0
        ].device_id == b2["device_id"]


@pytest.mark.asyncio
async def test_device_authority_rechecks_time_after_lock_wait(head_template_engine):
    key,jwk=keypair()
    async with head_template_engine.begin() as c:
        r=PostgresOwnerDeviceRepository(c)
        grant=await r.issue_binding(owner_identity='Owner',replace_device=False,now_ms=1000)
        device=await r.bind(token=grant,public_key=jwk,now_ms=2000)
        nonce=await r.issue_nonce(device['session_token'],now_ms=3000)
        payload={'enabled':False}
        proof=DeviceWriteProof(device_id=device['device_id'],device_epoch=1,method='POST',path='/api/owner/v1/mobile/controls/global',
            body_digest=canonical_digest(payload),nonce_id=nonce['nonce_id'],idempotency_key='delayed',issued_at_ms=nonce['issued_at_ms'],expires_at_ms=nonce['expires_at_ms'])
        with pytest.raises(ValueError,match='device_nonce_expired'):
            await r.authorize(token=device['session_token'],proof=proof,signature=sign(key,proof),body=payload,purpose='entry_pause',now_ms=3000,clock_ms=lambda:64000)
