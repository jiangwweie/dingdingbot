"""Owner Console settings and request-scoped authentication dependencies."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal, cast

from fastapi import Request
from pydantic import Field

from src.trading_kernel.application.owner_console.models import FrozenModel
from src.trading_kernel.interfaces.owner_console_http.auth import (
    OwnerAuthService,
    OwnerAuthSettings,
)
from src.trading_kernel.interfaces.owner_console_http.errors import UnauthorizedError


class OwnerConsoleSettings(FrozenModel):
    """Explicit Owner Console runtime inputs with no repository configuration read."""

    database_dsn: str = Field(min_length=1, repr=False)
    auth: OwnerAuthSettings
    venue_id: Literal["binance-usdm"] = "binance-usdm"
    account_id: str = Field(min_length=1)
    position_mode: Literal["independent_sides"] = "independent_sides"
    market_timeout_seconds: float = Field(default=5.0, gt=0)
    cookie_name: Literal["brc_owner_session"] = "brc_owner_session"


def current_time_ms() -> int:
    """Return the current wall-clock time only at the HTTP/application edge."""

    return int(time.time() * 1_000)


def get_settings(request: Request) -> OwnerConsoleSettings:
    """Read the explicit immutable settings installed by the app lifespan."""

    return cast(OwnerConsoleSettings, request.app.state.owner_console_settings)


def get_auth_service(request: Request) -> OwnerAuthService:
    """Read the single lifespan-owned authentication service."""

    return cast(OwnerAuthService, request.app.state.owner_auth_service)


async def require_authenticated(request: Request) -> None:
    """Require the sole signed Session cookie and expose no validation detail."""

    settings = get_settings(request)
    authenticated = await get_auth_service(request).validate_cookie(
        request.cookies.get(settings.cookie_name),
        now_ms=_clock_ms(request),
    )
    if not authenticated:
        raise UnauthorizedError


def trusted_source_ip(request: Request) -> str:
    """Use the direct peer only; forwarded headers are never credential input."""

    if request.client is None:
        return "unix-socket"
    return request.client.host


def _clock_ms(request: Request) -> int:
    return cast(Callable[[], int], request.app.state.owner_clock_ms)()
