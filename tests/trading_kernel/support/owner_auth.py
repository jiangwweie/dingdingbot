"""Shared local-only authentication fixtures."""
from argon2 import PasswordHasher

from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings

PASSWORD = "correct horse"
TOTP_SEED = "JBSWY3DPEHPK3PXP"
SIGNING_KEY = "test-signing-key-with-enough-random-looking-material"
BASE_MS = 1_800_000_000_000
IDLE_MS = 60_000
ABSOLUTE_MS = 5 * IDLE_MS
FAILURE_WINDOW_MS = 15 * 60_000
PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)
PASSWORD_HASH = PASSWORD_HASHER.hash(PASSWORD)
WRONG_COST_PASSWORD_HASH = PasswordHasher(
    time_cost=1,
    memory_cost=8192,
    parallelism=1,
    hash_len=32,
    salt_len=16,
).hash(PASSWORD)


def auth_settings(**overrides: object) -> OwnerAuthSettings:
    values: dict[str, object] = {
        "username": "owner",
        "password_hash": PASSWORD_HASH,
        "totp_seed": TOTP_SEED,
        "session_signing_key": SIGNING_KEY,
        "idle_timeout_ms": IDLE_MS,
        "absolute_timeout_ms": ABSOLUTE_MS,
    }
    values.update(overrides)
    return OwnerAuthSettings(**values)  # type: ignore[arg-type]
