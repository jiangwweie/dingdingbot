"""Exact WebCrypto P-256 request proofs; no network or exchange credentials."""

from __future__ import annotations

import base64
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof


def token_digest(token: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise ValueError("invalid_device_token")
    return "sha256:" + hashlib.sha256(token.encode("ascii")).hexdigest()


def _decode(s: str, *, size: int) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", s):
        raise ValueError("invalid_device_key_encoding")
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (ValueError, TypeError):
        raise ValueError("invalid_device_key_encoding") from None
    if len(raw) != size:
        raise ValueError("invalid_device_key_size")
    return raw


def _public_key(jwk: dict[str, str]) -> ec.EllipticCurvePublicKey:
    if (
        set(jwk) != {"kty", "crv", "x", "y"}
        or jwk["kty"] != "EC"
        or jwk["crv"] != "P-256"
    ):
        raise ValueError("invalid_device_public_key")
    try:
        return ec.EllipticCurvePublicNumbers(
            int.from_bytes(_decode(jwk["x"], size=32), "big"),
            int.from_bytes(_decode(jwk["y"], size=32), "big"),
            ec.SECP256R1(),
        ).public_key()
    except ValueError:
        raise ValueError("invalid_device_public_key") from None


def public_key_thumbprint(jwk: dict[str, str]) -> str:
    _public_key(jwk)
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def write_proof_message(proof: DeviceWriteProof) -> bytes:
    # Explicit ordered vector avoids differences in JSON object ordering. Integers
    # are small epoch/revision values; the financial body is independently hashed.
    return json.dumps(
        [
            "brc-owner-device-v1",
            proof.device_id,
            proof.device_epoch,
            proof.method,
            proof.path,
            proof.body_digest,
            proof.nonce_id,
            proof.idempotency_key,
            proof.issued_at_ms,
            proof.expires_at_ms,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def verify_device_signature(
    jwk: dict[str, str], proof: DeviceWriteProof, signature: str
) -> None:
    key = _public_key(jwk)
    raw = _decode(signature, size=64)
    der = encode_dss_signature(
        int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")
    )
    try:
        key.verify(der, write_proof_message(proof), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise ValueError("invalid_device_signature") from None
