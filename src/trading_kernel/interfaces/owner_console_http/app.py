"""FastAPI application factory for the read-only Owner Console."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.owner_console.causality import ContradictoryFacts
from src.trading_kernel.application.owner_console.signals import SignalNotFound
from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
    owner_read_transaction,
)
from src.trading_kernel.infrastructure.production_runtime import (
    build_binance_usdm_market_source,
)
from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    LoginThrottled,
    OwnerAuthService,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    OwnerConsoleSettings,
    current_time_ms,
    require_authenticated,
)
from src.trading_kernel.interfaces.owner_console_http.errors import (
    PublicMarketFailure,
    UnauthorizedError,
    error_response,
    unauthorized_response,
)
from src.trading_kernel.interfaces.owner_console_http.routes.auth import (
    router as auth_router,
)

_API_PREFIX = "/api/owner/v1"
_LOGIN_PATH = f"{_API_PREFIX}/auth/login"


def create_owner_console_app(
    settings: OwnerConsoleSettings,
    *,
    engine: AsyncEngine | None = None,
    market_data: OwnerMarketData | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> FastAPI:
    """Create an inert app; external resources begin only in its lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        read_engine = (
            engine
            if engine is not None
            else create_owner_read_engine(settings.database_dsn)
        )
        public_market_data = (
            market_data
            if market_data is not None
            else OwnerMarketData(build_binance_usdm_market_source())
        )
        app.state.owner_console_settings = settings
        app.state.owner_console_engine = read_engine
        app.state.owner_market_data = public_market_data
        app.state.owner_auth_service = OwnerAuthService(settings.auth)
        app.state.owner_clock_ms = clock_ms if clock_ms is not None else current_time_ms
        try:
            await _verify_startup_read_transaction(cast(AsyncEngine, read_engine))
            yield
        finally:
            await read_engine.dispose()
            await public_market_data.close()

    app = FastAPI(lifespan=lifespan)
    app.include_router(auth_router)
    _register_error_handlers(app)

    @app.middleware("http")
    async def require_owner_session(request: Request, call_next: Any) -> Response:
        if (
            request.url.path.startswith(f"{_API_PREFIX}/")
            and request.url.path != _LOGIN_PATH
        ):
            try:
                await require_authenticated(request)
            except UnauthorizedError:
                return unauthorized_response()
        return await call_next(request)

    @app.get("/healthz", include_in_schema=False)
    async def healthz(request: Request) -> Response:
        if not _is_unix_socket_request(request):
            return Response(status_code=404)
        return JSONResponse({"status": "ok"})

    return app


async def _verify_startup_read_transaction(engine: AsyncEngine) -> None:
    async with owner_read_transaction(engine) as connection:
        read_only = await connection.scalar(sa.text("SHOW transaction_read_only"))
        isolation = await connection.scalar(sa.text("SHOW transaction_isolation"))
        statement_timeout = await connection.scalar(sa.text("SHOW statement_timeout"))
    if (
        read_only != "on"
        or isolation != "repeatable read"
        or statement_timeout != "3s"
    ):
        raise RuntimeError("Owner Console read transaction verification failed")


def _register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnauthorizedError, _handle_unauthorized)
    app.add_exception_handler(InvalidCredentials, _handle_invalid_credentials)
    app.add_exception_handler(LoginThrottled, _handle_login_throttled)
    app.add_exception_handler(SignalNotFound, _handle_not_found)
    app.add_exception_handler(ContradictoryFacts, _handle_contradictory_facts)
    app.add_exception_handler(asyncio.TimeoutError, _handle_query_timeout)
    app.add_exception_handler(SqlAlchemyTimeoutError, _handle_query_timeout)
    app.add_exception_handler(PublicMarketFailure, _handle_market_failure)


async def _handle_unauthorized(_: Request, __: Exception) -> JSONResponse:
    return unauthorized_response()


async def _handle_invalid_credentials(_: Request, __: Exception) -> JSONResponse:
    return unauthorized_response()


async def _handle_login_throttled(_: Request, __: Exception) -> JSONResponse:
    return error_response(
        status_code=429,
        code="login_throttled",
        message="Authentication temporarily unavailable",
    )


async def _handle_not_found(_: Request, __: Exception) -> JSONResponse:
    return error_response(status_code=404, code="not_found", message="Resource not found")


async def _handle_contradictory_facts(_: Request, __: Exception) -> JSONResponse:
    return error_response(
        status_code=409,
        code="contradictory_facts",
        message="Current facts are contradictory",
    )


async def _handle_query_timeout(_: Request, __: Exception) -> JSONResponse:
    return error_response(
        status_code=503,
        code="query_timeout",
        message="Read query timed out",
    )


async def _handle_market_failure(_: Request, __: Exception) -> JSONResponse:
    return error_response(
        status_code=502,
        code="market_data_unavailable",
        message="Public market data is unavailable",
    )


def _is_unix_socket_request(request: Request) -> bool:
    server = request.scope.get("server")
    return (
        isinstance(server, (list, tuple))
        and len(server) == 2
        and isinstance(server[0], str)
        and server[0].startswith("/")
        and server[1] is None
    )
