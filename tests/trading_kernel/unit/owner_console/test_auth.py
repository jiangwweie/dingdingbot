import asyncio
from collections.abc import Callable
from typing import Any

import anyio
import pyotp
import pytest
from argon2 import PasswordHasher
from itsdangerous import URLSafeSerializer
from pydantic import ValidationError

from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    LoginThrottled,
    OwnerAuthService,
    OwnerAuthSettings,
)

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


def totp_code(now_ms: int = BASE_MS) -> str:
    return pyotp.TOTP(TOTP_SEED, interval=30).at(now_ms // 1000)


async def login(
    service: OwnerAuthService,
    *,
    now_ms: int = BASE_MS,
    username: str = "owner",
    password: str = PASSWORD,
    code: str | None = None,
    source_ip: str = "127.0.0.1",
) -> Any:
    return await service.login(
        username=username,
        password=password,
        totp_code=totp_code(now_ms) if code is None else code,
        source_ip=source_ip,
        now_ms=now_ms,
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"username": " "},
        {"username": "x" * 257},
        {"password_hash": "not-an-argon2id-hash"},
        {"password_hash": WRONG_COST_PASSWORD_HASH},
        {"totp_seed": "not base32!"},
        {"session_signing_key": "\t"},
        {"session_signing_key": "x" * 1025},
        {"idle_timeout_ms": 0},
        {"absolute_timeout_ms": IDLE_MS - 1},
    ),
)
def test_settings_fail_closed_without_rendering_secrets(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError) as error:
        auth_settings(**overrides)

    rendered = str(error.value)
    assert PASSWORD_HASH not in rendered
    assert SIGNING_KEY not in rendered


@pytest.mark.parametrize(
    ("username", "password", "code"),
    (
        ("other", PASSWORD, totp_code()),
        ("owner", "wrong", totp_code()),
        ("owner", PASSWORD, "000000"),
    ),
)
async def test_auth_factor_failures_are_indistinguishable_and_offload_once(
    monkeypatch: pytest.MonkeyPatch,
    username: str,
    password: str,
    code: str,
) -> None:
    service = OwnerAuthService(auth_settings())
    real_run_sync = anyio.to_thread.run_sync
    calls = 0

    async def counted_run_sync(
        func: Callable[..., object],
        *args: object,
        **kwargs: Any,
    ) -> object:
        nonlocal calls
        calls += 1
        return await real_run_sync(func, *args, **kwargs)

    monkeypatch.setattr(anyio.to_thread, "run_sync", counted_run_sync)

    with pytest.raises(InvalidCredentials) as error:
        await login(
            service,
            username=username,
            password=password,
            code=code,
        )

    assert str(error.value) == "authentication failed"
    assert calls == 1


async def test_concurrent_successful_logins_leave_exactly_one_active_session() -> None:
    service = OwnerAuthService(auth_settings())

    sessions = await asyncio.gather(*(login(service) for _ in range(4)))
    active = [
        await service.validate_cookie(session.cookie, now_ms=BASE_MS + 1)
        for session in sessions
    ]

    assert active.count(True) == 1
    assert active.count(False) == 3


async def test_cookie_payload_is_only_session_id_and_bad_cookies_are_generic() -> None:
    service = OwnerAuthService(auth_settings())
    session = await login(service)
    serializer = URLSafeSerializer(
        SIGNING_KEY,
        salt="brc-owner-console-session-v1",
    )

    payload = serializer.loads(session.cookie)
    assert isinstance(payload, str)
    assert len(payload) == 43
    for sensitive in ("owner", PASSWORD_HASH, TOTP_SEED, SIGNING_KEY, "127.0.0.1"):
        assert sensitive not in session.cookie

    pivot = len(session.cookie) // 2
    replacement = "A" if session.cookie[pivot] != "A" else "B"
    tampered = session.cookie[:pivot] + replacement + session.cookie[pivot + 1 :]
    for invalid in ("", "not-a-cookie", tampered, serializer.dumps({"session_id": payload})):
        assert await service.validate_cookie(invalid, now_ms=BASE_MS + 1) is False


async def test_idle_slides_but_idle_and_absolute_boundaries_expire() -> None:
    sliding = OwnerAuthService(auth_settings())
    session = await login(sliding)

    for elapsed_ms in (
        IDLE_MS - 1,
        2 * (IDLE_MS - 1),
        3 * (IDLE_MS - 1),
        4 * (IDLE_MS - 1),
        5 * (IDLE_MS - 1),
        ABSOLUTE_MS - 1,
    ):
        assert await sliding.validate_cookie(
            session.cookie,
            now_ms=BASE_MS + elapsed_ms,
        )
    assert not await sliding.validate_cookie(
        session.cookie,
        now_ms=BASE_MS + ABSOLUTE_MS,
    )

    idle = OwnerAuthService(auth_settings())
    idle_session = await login(idle)
    assert not await idle.validate_cookie(
        idle_session.cookie,
        now_ms=BASE_MS + IDLE_MS,
    )


async def test_logout_is_idempotent_and_process_restart_has_no_session() -> None:
    settings = auth_settings()
    service = OwnerAuthService(settings)
    session = await login(service)

    restarted = OwnerAuthService(settings)
    assert not await restarted.session_status(session.cookie, now_ms=BASE_MS + 1)

    await service.logout(session.cookie)
    await service.logout(session.cookie)
    await service.logout("malformed")
    assert not await service.session_status(session.cookie, now_ms=BASE_MS + 1)


async def test_normalized_identity_throttles_then_resets_at_cooldown_boundary() -> None:
    service = OwnerAuthService(auth_settings())
    source_ip = "203.0.113.8"
    variants = ("Owner", " OWNER ", "ＯＷＮＥＲ", "oWnEr", "owner")

    for offset, username in enumerate(variants):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                username=username,
                password="wrong",
                source_ip=source_ip,
                now_ms=BASE_MS + offset,
            )

    with pytest.raises(LoginThrottled) as error:
        await login(
            service,
            source_ip=source_ip,
            now_ms=BASE_MS + 5,
        )
    assert str(error.value) == "authentication unavailable"

    cooldown_boundary = BASE_MS + 4 + FAILURE_WINDOW_MS
    session = await login(
        service,
        source_ip=source_ip,
        now_ms=cooldown_boundary,
    )
    assert await service.validate_cookie(
        session.cookie,
        now_ms=cooldown_boundary + 1,
    )

    with pytest.raises(InvalidCredentials):
        await login(
            service,
            password="wrong",
            source_ip=source_ip,
            now_ms=cooldown_boundary + 2,
        )


async def test_failures_at_window_boundary_do_not_accumulate() -> None:
    service = OwnerAuthService(auth_settings())
    source_ip = "198.51.100.7"

    for offset in range(4):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                password="wrong",
                source_ip=source_ip,
                now_ms=BASE_MS + offset,
            )

    for now_ms in (BASE_MS + FAILURE_WINDOW_MS, BASE_MS + FAILURE_WINDOW_MS + 1):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                password="wrong",
                source_ip=source_ip,
                now_ms=now_ms,
            )


async def test_unique_expired_failure_keys_are_purged_globally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OwnerAuthService(auth_settings())

    async def reject_password(*args: object, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(anyio.to_thread, "run_sync", reject_password)
    for attempt in range(1024):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                username=f"attacker-{attempt}",
                source_ip="192.0.2.10",
                now_ms=BASE_MS,
            )

    with pytest.raises(InvalidCredentials):
        await login(
            service,
            username="fresh-attacker",
            source_ip="192.0.2.10",
            now_ms=BASE_MS + FAILURE_WINDOW_MS,
        )

    assert len(service._failures) == 1


@pytest.mark.parametrize("initial_failures", (4, 5))
async def test_live_failure_state_survives_unique_identity_churn(
    monkeypatch: pytest.MonkeyPatch,
    initial_failures: int,
) -> None:
    service = OwnerAuthService(auth_settings())
    target_username = f"target-{initial_failures}"
    source_ip = "192.0.2.11"

    async def reject_password(*args: object, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(anyio.to_thread, "run_sync", reject_password)
    for attempt in range(initial_failures):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                username=target_username,
                source_ip=source_ip,
                now_ms=BASE_MS + attempt,
            )

    for attempt in range(4096):
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                username=f"churn-{attempt}",
                source_ip=source_ip,
                now_ms=BASE_MS + 10,
            )

    if initial_failures == 4:
        with pytest.raises(InvalidCredentials):
            await login(
                service,
                username=target_username,
                source_ip=source_ip,
                now_ms=BASE_MS + 20,
            )

    with pytest.raises(LoginThrottled):
        await login(
            service,
            username=target_username,
            source_ip=source_ip,
            now_ms=BASE_MS + 21,
        )
