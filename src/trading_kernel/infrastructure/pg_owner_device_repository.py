"""Persistent single-Owner device registration and one-use request proof."""

from __future__ import annotations

import secrets
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import (
    DEVICE_IDLE_MS,
    DeviceRegistration,
    DeviceSession,
    DeviceWriteProof,
    renewed_expiry,
    require_device_write,
)
from src.trading_kernel.infrastructure.owner_device_credentials import (
    public_key_thumbprint,
    token_digest,
    verify_device_signature,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_binding_grants as grants,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_registrations as devices,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_sessions as sessions,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_write_evidence as writes,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_request_nonces as nonces,
)


class PostgresOwnerDeviceRepository:
    def __init__(self, connection: AsyncConnection):
        self.c = connection

    async def _lock(self) -> None:
        await self.c.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock(hashtextextended('brc-owner-device',0))"
            )
        )

    async def issue_binding(
        self, *, owner_identity: str, replace_device: bool, now_ms: int
    ) -> str:
        """Administrative-only caller; API role cannot INSERT grants."""
        if not owner_identity.strip() or now_ms <= 0:
            raise ValueError("binding_identity_invalid")
        await self._lock()
        token = secrets.token_urlsafe(32)
        await self.c.execute(
            sa.insert(grants).values(
                grant_id=secrets.token_hex(16),
                token_digest=token_digest(token),
                owner_identity=owner_identity,
                replace_device=replace_device,
                issued_at_ms=now_ms,
                expires_at_ms=now_ms + 600000,
            )
        )
        return token

    async def bind(
        self, *, token: str, public_key: dict[str, str], now_ms: int
    ) -> dict[str, Any]:
        digest = public_key_thumbprint(public_key)
        await self._lock()
        grant = (
            (
                await self.c.execute(
                    sa.select(grants)
                    .where(grants.c.token_digest == token_digest(token))
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            grant is None
            or grant["consumed_at_ms"] is not None
            or not grant["issued_at_ms"] <= now_ms < grant["expires_at_ms"]
        ):
            raise ValueError("binding_unavailable")
        current = (
            (
                await self.c.execute(
                    sa.select(devices)
                    .where(
                        devices.c.owner_identity == grant["owner_identity"],
                        devices.c.revoked_at_ms.is_(None),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if current is not None and not grant["replace_device"]:
            raise ValueError("active_device_exists")
        if current is not None:
            await self.revoke(device_id=current["device_id"], now_ms=now_ms)
        epoch = (
            int(
                await self.c.scalar(
                    sa.select(sa.func.coalesce(sa.func.max(devices.c.epoch), 0)).where(
                        devices.c.owner_identity == grant["owner_identity"]
                    )
                )
                or 0
            )
            + 1
        )
        did = secrets.token_hex(16)
        sid = secrets.token_hex(16)
        bearer = secrets.token_urlsafe(32)
        await self.c.execute(
            sa.insert(devices).values(
                device_id=did,
                owner_identity=grant["owner_identity"],
                epoch=epoch,
                public_key=public_key,
                key_digest=digest,
                registered_at_ms=now_ms,
            )
        )
        await self.c.execute(
            sa.insert(sessions).values(
                session_id=sid,
                device_id=did,
                device_epoch=epoch,
                token_digest=token_digest(bearer),
                issued_at_ms=now_ms,
                last_seen_at_ms=now_ms,
                expires_at_ms=now_ms + DEVICE_IDLE_MS,
            )
        )
        await self.c.execute(
            sa.update(grants)
            .where(grants.c.grant_id == grant["grant_id"])
            .values(consumed_at_ms=now_ms)
        )
        return {
            "device_id": did,
            "device_epoch": epoch,
            "session_token": bearer,
            "key_digest": digest,
            "expires_at_ms": now_ms + DEVICE_IDLE_MS,
        }

    async def authenticate(
        self, token: str, *, now_ms: int, lock: bool = False
    ) -> tuple[DeviceRegistration, DeviceSession]:
        query = sa.select(sessions).where(
            sessions.c.token_digest == token_digest(token)
        )
        if lock:
            query = query.with_for_update()
        raw = (await self.c.execute(query)).mappings().one_or_none()
        if raw is None:
            raise ValueError("device_session_unavailable")
        row = (
            (
                await self.c.execute(
                    sa.select(devices).where(devices.c.device_id == raw["device_id"])
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise ValueError("device_session_unavailable")
        device = DeviceRegistration.model_validate(
            {k: row[k] for k in DeviceRegistration.model_fields}
        )
        session = DeviceSession.model_validate(
            {k: raw[k] for k in DeviceSession.model_fields}
        )
        if (
            device.revoked_at_ms is not None
            or session.revoked_at_ms is not None
            or session.device_epoch != device.epoch
            or not session.issued_at_ms <= now_ms < session.expires_at_ms
            or session.last_seen_at_ms > now_ms
        ):
            raise ValueError("device_session_unavailable")
        return device, session

    async def renew(self, token: str, *, now_ms: int) -> int:
        _, s = await self.authenticate(token, now_ms=now_ms, lock=True)
        expiry = renewed_expiry(s, now_ms=now_ms)
        if expiry != s.expires_at_ms:
            await self.c.execute(
                sa.update(sessions)
                .where(sessions.c.session_id == s.session_id)
                .values(last_seen_at_ms=now_ms, expires_at_ms=expiry)
            )
        return expiry

    async def issue_nonce(self, token: str, *, now_ms: int) -> dict[str, Any]:
        _, s = await self.authenticate(token, now_ms=now_ms, lock=True)
        outstanding = int(
            await self.c.scalar(
                sa.select(sa.func.count())
                .select_from(nonces)
                .where(
                    nonces.c.session_id == s.session_id,
                    nonces.c.consumed_at_ms.is_(None),
                    nonces.c.expires_at_ms > now_ms,
                )
            )
            or 0
        )
        if outstanding >= 16:
            raise ValueError("nonce_limit")
        nid = secrets.token_hex(32)
        await self.c.execute(
            sa.insert(nonces).values(
                nonce_id=nid,
                session_id=s.session_id,
                issued_at_ms=now_ms,
                expires_at_ms=now_ms + 60000,
            )
        )
        return {
            "nonce_id": nid,
            "issued_at_ms": now_ms,
            "expires_at_ms": now_ms + 60000,
        }

    async def authorize(
        self,
        *,
        token: str,
        proof: DeviceWriteProof,
        signature: str,
        body: dict,
        purpose: str,
        now_ms: int,
        allow_idempotent_replay: bool = False,
    ) -> str:
        # Serialize revocation with all new accepted intents. No network I/O.
        await self._lock()
        d, s = await self.authenticate(token, now_ms=now_ms, lock=True)
        require_device_write(
            registration=d, session=s, proof=proof, purpose=purpose, now_ms=now_ms
        )
        if canonical_digest(body) != proof.body_digest:
            raise ValueError("request_body_mismatch")
        nonce = (
            (
                await self.c.execute(
                    sa.select(nonces)
                    .where(nonces.c.nonce_id == proof.nonce_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if nonce is None or nonce["session_id"] != s.session_id:
            raise ValueError("nonce_unavailable")
        if (
            nonce["issued_at_ms"] != proof.issued_at_ms
            or nonce["expires_at_ms"] != proof.expires_at_ms
        ):
            raise ValueError("nonce_terms_mismatch")
        verify_device_signature(d.public_key, proof, signature)
        if nonce["consumed_at_ms"] is not None:
            if (
                allow_idempotent_replay
                and nonce["request_digest"]
                == canonical_digest(proof.model_dump(mode="json"))
                and nonce["idempotency_key"] == proof.idempotency_key
            ):
                return d.owner_identity
            raise ValueError("nonce_consumed")
        await self.c.execute(
            sa.update(nonces)
            .where(nonces.c.nonce_id == proof.nonce_id)
            .values(
                consumed_at_ms=now_ms,
                request_digest=canonical_digest(proof.model_dump(mode="json")),
                idempotency_key=proof.idempotency_key,
            )
        )
        await self.c.execute(
            sa.insert(writes).values(
                evidence_id=canonical_digest(proof.model_dump(mode="json")),
                authorization_id=None,
                device_id=d.device_id,
                device_epoch=d.epoch,
                owner_identity=d.owner_identity,
                purpose=purpose,
                idempotency_key=proof.idempotency_key,
                proof=proof.model_dump(mode="json"),
                signature=signature,
                payload=body,
                body_digest=proof.body_digest,
                authorized_at_ms=now_ms,
            )
        )
        return d.owner_identity

    async def link_authorization(
        self,
        *,
        proof: DeviceWriteProof,
        owner_identity: str,
        authorization_id: str | None,
    ) -> None:
        if authorization_id is None:
            return
        row = (
            (
                await self.c.execute(
                    sa.select(writes)
                    .where(
                        writes.c.evidence_id
                        == canonical_digest(proof.model_dump(mode="json"))
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["owner_identity"] != owner_identity:
            raise ValueError("device_authorization_evidence_missing")
        if (
            row["authorization_id"] is not None
            and row["authorization_id"] != authorization_id
        ):
            raise ValueError("device_authorization_evidence_conflict")
        await self.c.execute(
            sa.update(writes)
            .where(writes.c.evidence_id == row["evidence_id"])
            .values(authorization_id=authorization_id)
        )
        from src.trading_kernel.infrastructure.owner_device_authorization_evidence import (
            trusted_owner_authorization_matches,
        )

        if not await trusted_owner_authorization_matches(self.c, authorization_id):
            raise ValueError("device_authorization_source_mismatch")

    async def revoke(self, *, device_id: str, now_ms: int) -> None:
        await self._lock()
        await self.c.execute(
            sa.update(devices)
            .where(devices.c.device_id == device_id, devices.c.revoked_at_ms.is_(None))
            .values(revoked_at_ms=now_ms)
        )
        await self.c.execute(
            sa.update(sessions)
            .where(
                sessions.c.device_id == device_id, sessions.c.revoked_at_ms.is_(None)
            )
            .values(revoked_at_ms=now_ms)
        )
