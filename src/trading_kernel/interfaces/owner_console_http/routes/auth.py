"""Cookie-only Owner authentication HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.interfaces.owner_console_http.dependencies import (
    get_auth_service,
    get_settings,
    trusted_source_ip,
)

router = APIRouter(prefix="/api/owner/v1/auth", tags=["authentication"])


class _LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1_024)
    totp_code: str = Field(pattern=r"^\d{6}$")


@router.post("/login", status_code=204)
async def login(request: Request, body: _LoginRequest) -> Response:
    """Verify JSON credentials and issue only the signed random Session ID."""

    settings = get_settings(request)
    session = await get_auth_service(request).login(
        username=body.username,
        password=body.password,
        totp_code=body.totp_code,
        source_ip=trusted_source_ip(request),
        now_ms=request.app.state.owner_clock_ms(),
    )
    response = Response(status_code=204)
    response.set_cookie(
        key=settings.cookie_name,
        value=session.cookie,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/owner/v1",
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    """Clear the matching in-memory Session and expire its cookie."""

    settings = get_settings(request)
    await get_auth_service(request).logout(request.cookies.get(settings.cookie_name))
    response = Response(status_code=204)
    response.delete_cookie(
        key=settings.cookie_name,
        path="/api/owner/v1",
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return response


@router.get("/session")
async def session() -> dict[str, bool]:
    """Expose only current authenticated status after cookie verification."""

    return {"authenticated": True}
