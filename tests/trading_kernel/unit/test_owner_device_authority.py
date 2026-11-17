import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import (
    DEVICE_IDLE_MS,
    DeviceRegistration,
    DeviceSession,
    DeviceWriteProof,
    renewed_expiry,
    require_device_write,
)


def device():
    return DeviceRegistration(
        device_id="iphone-1",
        owner_identity="Owner",
        epoch=1,
        public_key={"kty": "EC", "crv": "P-256", "x": "x", "y": "y"},
        registered_at_ms=1000,
        revoked_at_ms=None,
    )


def session():
    return DeviceSession(
        session_id="session-1",
        device_id="iphone-1",
        device_epoch=1,
        token_digest="sha256:" + "a" * 64,
        issued_at_ms=1000,
        last_seen_at_ms=1000,
        expires_at_ms=1000 + DEVICE_IDLE_MS,
        revoked_at_ms=None,
    )


def proof():
    return DeviceWriteProof(
        device_id="iphone-1",
        device_epoch=1,
        method="POST",
        path="/api/owner/v1/mobile/operations",
        body_digest=canonical_digest({"qty": "1"}),
        nonce_id="nonce-1",
        idempotency_key="request-1",
        issued_at_ms=2000,
        expires_at_ms=62000,
    )


def test_exact_registered_device_can_authorize_only_supported_operations():
    require_device_write(
        registration=device(),
        session=session(),
        proof=proof(),
        purpose="position_reduce",
        now_ms=3000,
    )


@pytest.mark.parametrize(
    "purpose",
    [
        "selection_mode_change",
        "universe_configure",
        "risk_budget_increase",
        "withdraw",
        "exit_profile_bind",
    ],
)
def test_device_does_not_grant_other_owner_privileges(purpose):
    with pytest.raises(ValueError, match="purpose_forbidden"):
        require_device_write(
            registration=device(),
            session=session(),
            proof=proof(),
            purpose=purpose,
            now_ms=3000,
        )


@pytest.mark.parametrize("change", [{"revoked_at_ms": 2500}, {"epoch": 2}])
def test_revoked_or_replaced_device_cannot_write(change):
    with pytest.raises(ValueError):
        require_device_write(
            registration=device().model_copy(update=change),
            session=session(),
            proof=proof(),
            purpose="entry_resume",
            now_ms=3000,
        )


def test_session_revocation_and_expiry_are_not_bypassed_by_device_key():
    for s in [
        session().model_copy(update={"revoked_at_ms": 2500}),
        session().model_copy(update={"expires_at_ms": 2999}),
    ]:
        with pytest.raises(ValueError):
            require_device_write(
                registration=device(),
                session=s,
                proof=proof(),
                purpose="entry_resume",
                now_ms=3000,
            )


def test_nonce_expired_or_not_yet_issued_cannot_authorize():
    for now in [1999, 62000]:
        with pytest.raises(ValueError):
            require_device_write(
                registration=device(),
                session=session(),
                proof=proof(),
                purpose="entry_resume",
                now_ms=now,
            )


def test_active_use_extends_idle_expiry_without_absolute_forced_login():
    assert renewed_expiry(session(), now_ms=1001) == session().expires_at_ms
    now = 1000 + 8 * 86400000
    assert renewed_expiry(session(), now_ms=now) == now + DEVICE_IDLE_MS


def test_digest_and_path_are_exact():
    with pytest.raises(ValidationError):
        DeviceWriteProof(**(proof().model_dump() | {"body_digest": "not-a-digest"}))
    with pytest.raises(ValidationError):
        DeviceWriteProof(
            **(proof().model_dump() | {"path": "https://attacker.example"})
        )
