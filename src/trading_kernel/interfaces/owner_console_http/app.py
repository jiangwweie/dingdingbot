"""FastAPI application factory for the read-only Owner Console."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import ccxt.async_support as ccxt_async
import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.owner_console.causality import ContradictoryFacts
from src.trading_kernel.application.owner_console.programmatic_review import (
    ProgrammaticReviewContradiction,
)
from src.trading_kernel.application.owner_console.signals import (
    SignalFactsContradiction,
    SignalNotFound,
)
from src.trading_kernel.application.owner_console.strategies import (
    StrategyFactsContradiction,
)
from src.trading_kernel.application.owner_console.trades import (
    TradeFactsContradiction,
)
from src.trading_kernel.application.owner_control import (
    OwnerControlBlocked,
    OwnerControlConflict,
)
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)
from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData
from src.trading_kernel.infrastructure.pg_owner_control import (
    create_owner_control_engine,
)
from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
    owner_read_transaction,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    LoginThrottled,
    OwnerAuthService,
)
from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    OwnerConsoleSettings,
    OwnerControlUnavailable,
    current_time_ms,
    require_authenticated,
)
from src.trading_kernel.interfaces.owner_console_http.errors import (
    OwnerResourceNotFound,
    PublicMarketFailure,
    UnauthorizedError,
    error_response,
    unauthorized_response,
)
from src.trading_kernel.interfaces.owner_console_http.routes.auth import (
    router as auth_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.controls import (
    router as controls_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.market import (
    router as market_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.overview import (
    router as overview_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.review import (
    router as review_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.signals import (
    router as signals_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.strategies import (
    router as strategies_router,
)
from src.trading_kernel.interfaces.owner_console_http.routes.tickets import (
    router as tickets_router,
)

_API_PREFIX = "/api/owner/v1"
_LOGIN_PATH = f"{_API_PREFIX}/auth/login"


def create_owner_console_app(
    settings: OwnerConsoleSettings,
    *,
    engine: AsyncEngine | None = None,
    control_engine: AsyncEngine | None = None,
    market_data: OwnerMarketData | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> FastAPI:
    """Create an inert app; external resources begin only in its lifespan."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        read_engine: AsyncEngine | None = None
        write_engine: AsyncEngine | None = None
        public_market_data: OwnerMarketData | None = None
        primary_error: BaseException | None = None
        try:
            read_engine = (
                engine
                if engine is not None
                else create_owner_read_engine(settings.database_dsn)
            )
            public_market_data = (
                market_data
                if market_data is not None
                else _build_owner_market_data(settings)
            )
            write_engine = (
                control_engine
                if control_engine is not None
                else (
                    None
                    if settings.control_database_dsn is None
                    else create_owner_control_engine(settings.control_database_dsn)
                )
            )
            app.state.owner_console_settings = settings
            app.state.owner_console_engine = read_engine
            app.state.owner_market_data = public_market_data
            app.state.owner_control_engine = write_engine
            app.state.owner_auth_service = OwnerAuthService(settings.auth)
            app.state.owner_clock_ms = (
                clock_ms if clock_ms is not None else current_time_ms
            )
            await _verify_startup_read_transaction(read_engine)
            yield
        except BaseException as error:
            primary_error = error
            raise
        finally:
            await _cleanup_lifespan_resources(
                engine=read_engine,
                control_engine=write_engine,
                market_data=public_market_data,
                primary_error=primary_error,
            )

    app = FastAPI(lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(controls_router)
    app.include_router(overview_router)
    app.include_router(signals_router)
    app.include_router(tickets_router)
    app.include_router(strategies_router)
    app.include_router(review_router)
    app.include_router(market_router)
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

    @app.get("/healthz")
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
        schema_revision = await connection.scalar(
            sa.text("SELECT version_num FROM alembic_version")
        )
    if read_only != "on" or isolation != "repeatable read" or statement_timeout != "3s":
        raise RuntimeError("Owner Console read transaction verification failed")
    if schema_revision != CURRENT_SCHEMA_REVISION:
        raise RuntimeError("Owner Console schema revision differs")


def _build_owner_market_data(settings: OwnerConsoleSettings) -> OwnerMarketData:
    timeout_ms = max(1, int(settings.market_timeout_seconds * 1_000))
    exchange = ccxt_async.binanceusdm(
        {
            "enableRateLimit": True,
            "timeout": timeout_ms,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    )
    return OwnerMarketData(
        CcxtBinancePublicMarketSource(
            exchange=exchange,
            timeout_seconds=settings.market_timeout_seconds,
        )
    )


async def _cleanup_lifespan_resources(
    *,
    engine: AsyncEngine | None,
    control_engine: AsyncEngine | None,
    market_data: OwnerMarketData | None,
    primary_error: BaseException | None,
) -> None:
    failures: list[tuple[str, BaseException]] = []
    for name, cleanup in (
        ("engine dispose", None if engine is None else engine.dispose),
        (
            "control engine dispose",
            None if control_engine is None else control_engine.dispose,
        ),
        ("public market close", None if market_data is None else market_data.close),
    ):
        if cleanup is None:
            continue
        try:
            await cleanup()
        except BaseException as cleanup_error:  # noqa: BLE001 - cleanup must be complete
            failures.append((name, cleanup_error))

    if not failures:
        return
    if primary_error is not None:
        for name, cleanup_failure in failures:
            primary_error.add_note(
                f"Owner Console cleanup {name} failed: {cleanup_failure!r}"
            )
        return
    first_name, first_error = failures[0]
    first_error.add_note(f"Owner Console cleanup first failed step: {first_name}")
    for name, cleanup_failure in failures[1:]:
        first_error.add_note(
            f"Owner Console cleanup {name} also failed: {cleanup_failure!r}"
        )
    raise first_error


def _register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UnauthorizedError, _handle_unauthorized)
    app.add_exception_handler(InvalidCredentials, _handle_invalid_credentials)
    app.add_exception_handler(LoginThrottled, _handle_login_throttled)
    app.add_exception_handler(SignalNotFound, _handle_not_found)
    app.add_exception_handler(OwnerResourceNotFound, _handle_not_found)
    app.add_exception_handler(ContradictoryFacts, _handle_contradictory_facts)
    app.add_exception_handler(
        SignalFactsContradiction,
        _handle_contradictory_facts,
    )
    app.add_exception_handler(
        TradeFactsContradiction,
        _handle_contradictory_facts,
    )
    app.add_exception_handler(
        StrategyFactsContradiction,
        _handle_contradictory_facts,
    )
    app.add_exception_handler(
        ProgrammaticReviewContradiction,
        _handle_contradictory_facts,
    )
    app.add_exception_handler(asyncio.TimeoutError, _handle_query_timeout)
    app.add_exception_handler(SqlAlchemyTimeoutError, _handle_query_timeout)
    app.add_exception_handler(PublicMarketFailure, _handle_market_failure)
    app.add_exception_handler(OwnerControlConflict, _handle_control_conflict)
    app.add_exception_handler(OwnerControlBlocked, _handle_control_blocked)
    app.add_exception_handler(OwnerControlUnavailable, _handle_control_unavailable)


async def _handle_control_conflict(_: Request, error: Exception) -> JSONResponse:
    return error_response(status_code=409, code="control_conflict", message=str(error))


async def _handle_control_blocked(_: Request, error: Exception) -> JSONResponse:
    return error_response(status_code=422, code="control_blocked", message=str(error))


async def _handle_control_unavailable(_: Request, __: Exception) -> JSONResponse:
    return error_response(
        status_code=503,
        code="control_unavailable",
        message="Owner control is temporarily unavailable",
    )


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
    return error_response(
        status_code=404, code="not_found", message="Resource not found"
    )


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
