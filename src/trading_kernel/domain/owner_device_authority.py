"""Single-Owner browser registration authority; no credential generation or I/O."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEVICE_IDLE_MS = 180 * 86400000
DEVICE_RENEW_INTERVAL_MS = 7 * 86400000
DEVICE_OPERATION_PURPOSES = frozenset(
    {
        "entry_pause",
        "entry_resume",
        "strategy_pause",
        "strategy_resume",
        "position_reduce",
        "position_close",
        "protection_tighten",
        "manual_tp_set",
        "manual_tp_cancel",
    }
)


class DeviceRegistration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    device_id: str = Field(min_length=1, max_length=160)
    owner_identity: str = Field(min_length=1, max_length=96)
    epoch: int = Field(gt=0)
    public_key: dict[str, str]
    registered_at_ms: int = Field(gt=0)
    revoked_at_ms: int | None = Field(default=None, gt=0)


class DeviceSession(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    session_id: str = Field(min_length=1, max_length=160)
    device_id: str = Field(min_length=1, max_length=160)
    device_epoch: int = Field(gt=0)
    token_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    issued_at_ms: int = Field(gt=0)
    last_seen_at_ms: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)
    revoked_at_ms: int | None = Field(default=None, gt=0)


class DeviceWriteProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    device_id: str = Field(min_length=1, max_length=160)
    device_epoch: int = Field(gt=0)
    method: Literal["POST", "PUT", "DELETE"]
    path: str = Field(pattern=r"^/api/owner/v1/mobile/[A-Za-z0-9_/-]+$", max_length=512)
    body_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    nonce_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=160)
    issued_at_ms: int = Field(gt=0)
    expires_at_ms: int = Field(gt=0)


def require_device_write(
    *,
    registration: DeviceRegistration,
    session: DeviceSession,
    proof: DeviceWriteProof,
    purpose: str,
    now_ms: int,
) -> None:
    if purpose not in DEVICE_OPERATION_PURPOSES:
        raise ValueError("device_purpose_forbidden")
    if (
        registration.revoked_at_ms is not None
        or session.revoked_at_ms is not None
        or registration.registered_at_ms > now_ms
        or session.issued_at_ms > now_ms
        or session.last_seen_at_ms > now_ms
        or session.expires_at_ms <= now_ms
    ):
        raise ValueError("device_session_unavailable")
    if (
        registration.device_id != session.device_id
        or proof.device_id != registration.device_id
        or proof.device_epoch != registration.epoch
        or session.device_epoch != registration.epoch
    ):
        raise ValueError("device_epoch_or_identity_mismatch")
    if (
        not proof.issued_at_ms <= now_ms < proof.expires_at_ms
        or proof.expires_at_ms - proof.issued_at_ms > 60000
    ):
        raise ValueError("device_nonce_expired")


def renewed_expiry(session: DeviceSession, *, now_ms: int) -> int:
    if (
        session.revoked_at_ms is not None
        or not session.last_seen_at_ms <= now_ms < session.expires_at_ms
    ):
        raise ValueError("device_session_unavailable")
    if now_ms - session.last_seen_at_ms >= DEVICE_RENEW_INTERVAL_MS:
        return now_ms + DEVICE_IDLE_MS
    return session.expires_at_ms
