from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pyotp
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import Message, Scope

from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData
from src.trading_kernel.interfaces.owner_console_http import app as app_module
from src.trading_kernel.interfaces.owner_console_http.app import (
    OwnerConsoleSettings,
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings

PASSWORD = "correct horse"
TOTP_SEED = "JBSWY3DPEHPK3PXP"
BASE_MS = 1_800_000_000_000
PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)
PASSWORD_HASH = PASSWORD_HASHER.hash(PASSWORD)


class _StartupTransaction:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _StartupConnection:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    async def execution_options(self, **_: object) -> _StartupConnection:
        return self

    async def begin(self) -> _StartupTransaction:
        return _StartupTransaction()

    async def execute(self, _: object) -> None:
        return None

    async def scalar(self, statement: object) -> str:
        return self._values[str(statement)]


class _ConnectionContext:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    async def __aenter__(self) -> _StartupConnection:
        return _StartupConnection(self._values)

    async def __aexit__(
        self,
        _type: object,
        _value: object,
        _traceback: object,
    ) -> None:
        return None


class _ReadOnlyEngine:
    def __init__(
        self,
        *,
        statement_timeout: str = "3s",
        dispose_error: BaseException | None = None,
    ) -> None:
        self.dispose_calls = 0
        self._dispose_error = dispose_error
        self._values = {
            "SHOW transaction_read_only": "on",
            "SHOW transaction_isolation": "repeatable read",
            "SHOW statement_timeout": statement_timeout,
        }

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self._values)

    async def dispose(self) -> None:
        self.dispose_calls += 1
        if self._dispose_error is not None:
            raise self._dispose_error


class _PublicMarketData:
    def __init__(self, *, close_error: BaseException | None = None) -> None:
        self.close_calls = 0
        self._close_error = close_error

    async def close(self) -> None:
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error


@pytest_asyncio.fixture
async def owner_console_app() -> AsyncIterator[FastAPI]:
    app = create_owner_console_app(
        OwnerConsoleSettings(
            database_dsn="postgresql+asyncpg://unused",
            account_id="owner-account",
            auth=OwnerAuthSettings(
                username="owner",
                password_hash=PASSWORD_HASH,
                totp_seed=TOTP_SEED,
                session_signing_key="test-signing-key-with-enough-random-looking-material",
            ),
        ),
        engine=cast(AsyncEngine, _ReadOnlyEngine()),
        market_data=cast(OwnerMarketData, _PublicMarketData()),
        clock_ms=lambda: BASE_MS,
    )
    async with app.router.lifespan_context(app):
        yield app


async def test_login_sets_strict_secure_http_only_cookie(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        response = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1_000),
            },
        )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "brc_owner_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie


async def test_unauthenticated_session_and_data_share_one_401_shape(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        session = await client.get("/api/owner/v1/auth/session")
        overview = await client.get("/api/owner/v1/overview")

    assert session.status_code == 401
    assert overview.status_code == 401
    assert session.json()["error"] == {
        "code": "unauthorized",
        "message": "Authentication required",
    }
    assert overview.json()["error"] == session.json()["error"]


async def test_session_and_logout_require_the_cookie_and_invalidate_it(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        login = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1_000),
            },
        )
        session = await client.get("/api/owner/v1/auth/session")
        logout = await client.post("/api/owner/v1/auth/logout")
        expired = await client.get("/api/owner/v1/auth/session")

    assert login.status_code == 204
    assert session.status_code == 200
    assert session.json() == {"authenticated": True}
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert expired.status_code == 401


async def test_healthz_is_available_only_on_the_unix_socket(
    owner_console_app: FastAPI,
) -> None:
    unix_status = await _asgi_status(
        owner_console_app,
        path="/healthz",
        server=("/tmp/brc-owner-console.sock", None),
    )
    tcp_status = await _asgi_status(
        owner_console_app,
        path="/healthz",
        server=("127.0.0.1", 8000),
    )

    assert unix_status == 200
    assert tcp_status == 404


async def test_lifespan_cleans_each_resource_when_startup_fails() -> None:
    engine = _ReadOnlyEngine(
        statement_timeout="1s",
        dispose_error=OSError("engine dispose failed"),
    )
    market_data = _PublicMarketData(close_error=OSError("market close failed"))
    app = create_owner_console_app(
        _settings(),
        engine=cast(AsyncEngine, engine),
        market_data=cast(OwnerMarketData, market_data),
    )

    with pytest.raises(RuntimeError, match="read transaction verification failed"):
        async with app.router.lifespan_context(app):
            pass

    assert engine.dispose_calls == 1
    assert market_data.close_calls == 1


async def test_lifespan_disposes_the_engine_when_market_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _ReadOnlyEngine()

    def raise_market_construction(_: OwnerConsoleSettings) -> OwnerMarketData:
        raise RuntimeError("market construction failed")

    monkeypatch.setattr(
        app_module,
        "_build_owner_market_data",
        raise_market_construction,
    )
    app = create_owner_console_app(
        _settings(),
        engine=cast(AsyncEngine, engine),
    )

    with pytest.raises(RuntimeError, match="market construction failed"):
        async with app.router.lifespan_context(app):
            pass

    assert engine.dispose_calls == 1


async def test_market_construction_uses_explicit_console_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(market_timeout_seconds=7.5)
    captured: list[dict[str, object]] = []

    class PublicExchange:
        def close(self) -> None:
            return None

    def build_exchange(config: dict[str, object]) -> PublicExchange:
        captured.append(config)
        return PublicExchange()

    monkeypatch.setattr(app_module.ccxt_async, "binanceusdm", build_exchange)
    market_data = app_module._build_owner_market_data(settings)
    await market_data.close()

    assert captured == [
        {
            "enableRateLimit": True,
            "timeout": 7_500,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    ]


async def _asgi_status(
    app: FastAPI,
    *,
    path: str,
    server: tuple[str, int | None],
) -> int:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        cast(
            Scope,
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"",
                "headers": [],
                "client": None,
                "server": server,
            },
        ),
        receive,
        send,
    )
    return next(
        cast(int, message["status"])
        for message in messages
        if message["type"] == "http.response.start"
    )


def _settings(**overrides: object) -> OwnerConsoleSettings:
    values: dict[str, object] = {
        "database_dsn": "postgresql+asyncpg://unused",
        "account_id": "owner-account",
        "auth": OwnerAuthSettings(
            username="owner",
            password_hash=PASSWORD_HASH,
            totp_seed=TOTP_SEED,
            session_signing_key="test-signing-key-with-enough-random-looking-material",
        ),
    }
    values.update(overrides)
    return OwnerConsoleSettings(**values)  # type: ignore[arg-type]
