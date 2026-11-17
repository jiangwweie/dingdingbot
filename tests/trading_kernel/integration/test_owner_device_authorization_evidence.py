"""Stored device proof must authorize the exact action, target and body."""

import hashlib
import json

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.owner_device_authorization_evidence import (
    trusted_owner_authorization_matches,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_authorizations,
    owner_device_write_evidence,
)
from src.trading_kernel.infrastructure.pg_owner_device_repository import (
    PostgresOwnerDeviceRepository,
)
from tests.trading_kernel.support.owner_device import keypair, sign


@pytest.mark.asyncio
@pytest.mark.parametrize("alteration", [None, "target", "purpose", "body", "signature"])
async def test_authorization_requires_exact_signed_source(
    head_template_engine, alteration
):
    key, jwk = keypair()
    payload = {
        "owner_policy_id": "policy-main",
        "enabled": False,
        "expected_version": 1,
    }
    async with head_template_engine.begin() as c:
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
            path="/api/owner/v1/mobile/controls/global",
            body_digest=canonical_digest(payload),
            nonce_id=nonce["nonce_id"],
            idempotency_key="signed-pause",
            issued_at_ms=nonce["issued_at_ms"],
            expires_at_ms=nonce["expires_at_ms"],
        )
        await r.authorize(
            token=bound["session_token"],
            proof=proof,
            signature=sign(key, proof),
            body=payload,
            purpose="entry_pause",
            now_ms=4000,
        )
        await c.execute(
            sa.insert(owner_authorizations).values(
                authorization_id="auth-1",
                purpose="entry_resume" if alteration == "purpose" else "entry_pause",
                owner_identity="Owner",
                authentication_strength="trusted_device_session",
                request_digest="sha256:"
                + hashlib.sha256(
                    json.dumps(
                        {
                            "purpose": "entry_pause",
                            "expected_version": 1,
                            "reason": "Owner mobile control",
                            "idempotency_key": "signed-pause",
                            "target_scope": {"owner_policy_id": "policy-main"},
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
                target_scope={
                    "owner_policy_id": "wrong"
                    if alteration == "target"
                    else "policy-main"
                },
                idempotency_key="signed-pause",
                authorized_at_ms=4000,
            )
        )
        # Simulate corrupt provenance at insertion boundary, not an approved link.
        values = {"authorization_id": "auth-1", "result_kind": "authorized"}
        if alteration == "body":
            values["payload"] = {**payload, "enabled": True}
        if alteration == "signature":
            values["signature"] = "A" * 86
        if alteration in {"body", "signature"}:
            from sqlalchemy.exc import DBAPIError

            with pytest.raises(DBAPIError, match="immutable"):
                async with c.begin_nested():
                    await c.execute(
                        sa.update(owner_device_write_evidence).values(**values)
                    )
        else:
            await c.execute(sa.update(owner_device_write_evidence).values(**values))
        assert await trusted_owner_authorization_matches(c, "auth-1") is (
            alteration is None
        )
        if alteration is None:
            await r.revoke(device_id=bound["device_id"], now_ms=5000)
            # Revocation forbids new writes but retains proof of historical intent.
            assert await trusted_owner_authorization_matches(c, "auth-1")


@pytest.mark.asyncio
async def test_device_registration_key_is_immutable_and_only_revoke_column_changes(
    head_template_engine,
):
    from sqlalchemy.exc import DBAPIError

    from src.trading_kernel.infrastructure.pg_models import owner_device_registrations
    from tests.trading_kernel.support.owner_device import keypair

    _, jwk = keypair()
    _, other = keypair()
    async with head_template_engine.begin() as c:
        r = PostgresOwnerDeviceRepository(c)
        grant = await r.issue_binding(
            owner_identity="Owner", replace_device=False, now_ms=1000
        )
        bound = await r.bind(token=grant, public_key=jwk, now_ms=2000)
        with pytest.raises(DBAPIError, match="immutable"):
            async with c.begin_nested():
                await c.execute(
                    sa.update(owner_device_registrations)
                    .where(owner_device_registrations.c.device_id == bound["device_id"])
                    .values(public_key=other)
                )
        await r.revoke(device_id=bound["device_id"], now_ms=3000)
        with pytest.raises(DBAPIError, match="immutable"):
            async with c.begin_nested():
                await c.execute(
                    sa.update(owner_device_registrations)
                    .where(owner_device_registrations.c.device_id == bound["device_id"])
                    .values(revoked_at_ms=None)
                )
