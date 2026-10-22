"""Google browser redirects; tokens never leave the Owner API boundary."""

import logging
from typing import cast

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import Field

from src.trading_kernel.application.owner_console.models import FrozenModel
from src.trading_kernel.interfaces.owner_console_http.auth import InvalidCredentials
from src.trading_kernel.interfaces.owner_console_http.dependencies import get_settings
from src.trading_kernel.interfaces.owner_console_http.google_oidc import (
    FLOW_TTL_MS,
    GoogleBindingCandidate,
    GoogleOidcService,
)
from src.trading_kernel.interfaces.owner_console_http.routes.auth import (
    set_session_cookie,
)

router = APIRouter(prefix="/api/owner/v1/auth", tags=["authentication"])
_FLOW_COOKIE = "__Secure-brc_google_flow"
_FLOW_PATH = "/api/owner/v1/auth/google"
_LOGGER = logging.getLogger(__name__)


class AuthProviders(FrozenModel):
    google_login: bool
    google_binding: bool


class GoogleBindBody(FrozenModel):
    totp_code: str = Field(pattern=r"^\d{6}$")


class GoogleBindStart(FrozenModel):
    authorization_url: str


def _service(request: Request) -> GoogleOidcService:
    service = getattr(request.app.state, "owner_google_oidc", None)
    if service is None:
        raise InvalidCredentials
    return cast(GoogleOidcService, service)


def _headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _flow_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        _FLOW_COOKIE,
        value,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=FLOW_TTL_MS // 1000,
        path=_FLOW_PATH,
    )


def _host(request: Request) -> None:
    if (
        request.headers.get("host", "").split(":", 1)[0]
        != get_settings(request).public_host
    ):
        raise InvalidCredentials


@router.get("/providers")
async def providers(request: Request, response: Response) -> AuthProviders:
    _headers(response)
    settings = get_settings(request).google_oidc
    return AuthProviders(
        google_login=settings is not None and settings.owner_subject is not None,
        google_binding=settings is not None and settings.owner_subject is None,
    )


@router.get("/google/start")
async def google_start(request: Request) -> Response:
    _host(request)
    flow = await _service(request).begin("login")
    response = RedirectResponse(flow.authorization_url, status_code=303)
    _flow_cookie(response, flow.browser_cookie)
    return _headers(response)


@router.post("/google/bind/start")
async def google_bind_start(
    request: Request, body: GoogleBindBody, response: Response
) -> GoogleBindStart:
    _host(request)
    settings = get_settings(request)
    if request.headers.get("origin") != settings.public_origin:
        raise InvalidCredentials
    flow = await _service(request).begin(
        "bind",
        owner_cookie=request.cookies.get(settings.cookie_name),
        totp_code=body.totp_code,
    )
    _flow_cookie(response, flow.browser_cookie)
    _headers(response)
    return GoogleBindStart(authorization_url=flow.authorization_url)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    state: str = Query(default="", max_length=256),
    code: str = Query(default="", max_length=4096),
    error: str = Query(default="", max_length=256),
) -> Response:
    response = RedirectResponse("/trading/?google_result=error", status_code=303)
    try:
        _host(request)
        if error or not state or not code:
            raise InvalidCredentials
        result = await _service(request).complete(
            state, code, request.cookies.get(_FLOW_COOKIE)
        )
        response = RedirectResponse(
            "/trading/?google_result=" + ("success" if result.session else "binding"),
            status_code=303,
        )
        if result.session:
            _LOGGER.info("owner_google_auth result=login_verified")
            set_session_cookie(
                response, get_settings(request).cookie_name, result.session.cookie
            )
        else:
            _LOGGER.info("owner_google_auth result=binding_candidate_verified")
            return _headers(
                response
            )  # Keep browser binding cookie until the protected candidate is read.
    except InvalidCredentials:
        _LOGGER.info("owner_google_auth result=rejected")
    response.delete_cookie(
        _FLOW_COOKIE, path=_FLOW_PATH, secure=True, httponly=True, samesite="lax"
    )
    return _headers(response)


@router.get("/google/binding")
async def google_binding(
    request: Request, response: Response
) -> GoogleBindingCandidate:
    _headers(response)
    settings = get_settings(request)
    return await _service(request).binding_candidate(
        request.cookies.get(_FLOW_COOKIE), request.cookies.get(settings.cookie_name)
    )
