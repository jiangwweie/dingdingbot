"""Local P-256 browser-key fixtures; no production credentials."""

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from src.trading_kernel.infrastructure.owner_device_credentials import (
    write_proof_message,
)


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def keypair():
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_numbers()
    return key, {
        "kty": "EC",
        "crv": "P-256",
        "x": encode(public.x.to_bytes(32, "big")),
        "y": encode(public.y.to_bytes(32, "big")),
    }


def sign(key, proof) -> str:
    a, b = decode_dss_signature(
        key.sign(write_proof_message(proof), ec.ECDSA(hashes.SHA256()))
    )
    return encode(a.to_bytes(32, "big") + b.to_bytes(32, "big"))
