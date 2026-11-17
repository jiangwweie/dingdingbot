import base64

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.owner_device_credentials import (
    public_key_thumbprint,
    token_digest,
    verify_device_signature,
    write_proof_message,
)


def encode(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def signed():
    key = ec.generate_private_key(ec.SECP256R1())
    n = key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": encode(n.x.to_bytes(32, "big")),
        "y": encode(n.y.to_bytes(32, "big")),
    }
    p = DeviceWriteProof(
        device_id="d",
        device_epoch=1,
        method="POST",
        path="/api/owner/v1/mobile/operations",
        body_digest="sha256:" + "a" * 64,
        nonce_id="n",
        idempotency_key="k",
        issued_at_ms=1,
        expires_at_ms=60001,
    )
    der = key.sign(write_proof_message(p), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return jwk, p, encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def test_webcrypto_raw_p256_signature_is_accepted():
    jwk, p, s = signed()
    verify_device_signature(jwk, p, s)
    assert public_key_thumbprint(jwk).startswith("sha256:")


def test_body_or_operation_swap_is_rejected():
    jwk, p, s = signed()
    for field, value in [
        ("body_digest", "sha256:" + "b" * 64),
        ("idempotency_key", "other"),
        ("path", "/api/owner/v1/mobile/controls"),
    ]:
        with pytest.raises(ValueError):
            verify_device_signature(jwk, p.model_copy(update={field: value}), s)


@pytest.mark.parametrize("signature", ["", "bad", "a" * 85])
def test_invalid_signature_encoding_is_rejected(signature):
    jwk, p, _ = signed()
    with pytest.raises(ValueError):
        verify_device_signature(jwk, p, signature)


def test_private_key_or_other_curve_is_rejected():
    jwk, p, s = signed()
    for change in [{"d": "secret"}, {"crv": "P-384"}, {"x": "bad"}]:
        with pytest.raises(ValueError):
            verify_device_signature(jwk | change, p, s)


def test_random_token_digest_is_not_bearer_value():
    assert token_digest("a" * 43) != token_digest("b" * 43)
    assert "a" * 43 not in token_digest("a" * 43)
