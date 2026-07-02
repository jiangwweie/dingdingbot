from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Annotated, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field


USERNAME_ENV = "BRC_OPERATOR_USERNAME"
PASSWORD_HASH_ENV = "BRC_OPERATOR_PASSWORD_HASH"
TOTP_SECRET_ENV = "BRC_OPERATOR_TOTP_SECRET"
SESSION_SECRET_ENV = "BRC_OPERATOR_SESSION_SECRET"
SESSION_TTL_ENV = "BRC_OPERATOR_SESSION_TTL_SECONDS"
SESSION_COOKIE = "brc_operator_session"
PASSWORD_ALGORITHM = "pbkdf2_sha256"
DEFAULT_PASSWORD_ITERATIONS = 210_000
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60

router = APIRouter(prefix="/api/auth", tags=["Operator Auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)
    totp_code: str = Field(min_length=6, max_length=8)


class SessionResponse(BaseModel):
    authenticated: bool
    username: Optional[str] = None
    expires_at_ms: Optional[int] = None
    current_stage: str = "BRC-R4 local operator console"
    next_recommended_step: str = "Use the console to review state, create an operator plan, then confirm explicitly."
    global_planning_stage: str = "Bounded Risk Campaign System mainline; live, withdrawal, strategy pool, and cloud hardening remain deferred."
    live_ready: bool = False


@dataclass(frozen=True)
class OperatorSession:
    username: str
    expires_at: int


@dataclass(frozen=True)
class _AuthConfig:
    username: str
    password_hash: str
    totp_secret: str
    session_secret: str
    ttl_seconds: int


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _load_auth_config() -> _AuthConfig:
    missing = [
        key
        for key in (USERNAME_ENV, PASSWORD_HASH_ENV, TOTP_SECRET_ENV, SESSION_SECRET_ENV)
        if not os.getenv(key)
    ]
    if missing:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "BRC-AUTH-CONFIG-MISSING",
                "message": "Operator auth is not configured. Required env vars are missing.",
                "missing": missing,
            },
        )
    ttl_text = os.getenv(SESSION_TTL_ENV, str(DEFAULT_SESSION_TTL_SECONDS)).strip()
    try:
        ttl_seconds = int(ttl_text)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Invalid BRC operator session TTL") from exc
    if ttl_seconds <= 0 or ttl_seconds > 7 * 24 * 60 * 60:
        raise HTTPException(status_code=503, detail="Invalid BRC operator session TTL")
    return _AuthConfig(
        username=os.environ[USERNAME_ENV],
        password_hash=os.environ[PASSWORD_HASH_ENV],
        totp_secret=os.environ[TOTP_SECRET_ENV],
        session_secret=os.environ[SESSION_SECRET_ENV],
        ttl_seconds=ttl_seconds,
    )


def create_password_hash(password: str, *, iterations: int = DEFAULT_PASSWORD_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(iterations),
            _b64url_encode(salt),
            _b64url_encode(digest),
        ]
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64url_decode(salt_text)
        expected = _b64url_decode(digest_text)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_otpauth_uri(*, username: str, secret: str, issuer: str = "BRC Operator Console") -> str:
    label = f"{issuer}:{username}"
    return (
        "otpauth://totp/"
        f"{quote(label)}?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def _hotp(secret: str, counter: int, digits: int = 6) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset : offset + 4], "big") & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def verify_totp(code: str, secret: str, *, now: Optional[int] = None, window: int = 1) -> bool:
    normalized_code = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(normalized_code) != 6:
        return False
    current = int((now if now is not None else time.time()) // 30)
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret, current + drift), normalized_code):
            return True
    return False


def _sign_payload(payload: dict, secret: str) -> str:
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(signature)}"


def _verify_token(token: str, secret: str) -> dict:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid operator session") from exc
    expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(signature)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid operator session") from exc
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid operator session")
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid operator session") from exc
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise HTTPException(status_code=401, detail="Operator session expired")
    return payload


def _issue_session(response: Response, *, username: str, config: _AuthConfig) -> SessionResponse:
    now = int(time.time())
    expires_at = now + config.ttl_seconds
    token = _sign_payload(
        {
            "sub": username,
            "iat": now,
            "exp": expires_at,
            "scope": "brc_operator_console",
        },
        config.session_secret,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=config.ttl_seconds,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
    )
    return SessionResponse(
        authenticated=True,
        username=username,
        expires_at_ms=expires_at * 1000,
    )


def require_operator_session(request: Request) -> OperatorSession:
    config = _load_auth_config()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Operator login required")
    payload = _verify_token(token, config.session_secret)
    username = str(payload.get("sub") or "")
    if not hmac.compare_digest(username, config.username):
        raise HTTPException(status_code=401, detail="Invalid operator session")
    return OperatorSession(username=username, expires_at=int(payload["exp"]))


OperatorSessionDependency = Annotated[OperatorSession, Depends(require_operator_session)]


@router.post("/login", response_model=SessionResponse)
async def login(body: LoginRequest, response: Response) -> SessionResponse:
    config = _load_auth_config()
    if not hmac.compare_digest(body.username, config.username):
        raise HTTPException(status_code=401, detail="Invalid username, password, or authenticator code")
    if not verify_password(body.password, config.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username, password, or authenticator code")
    if not verify_totp(body.totp_code, config.totp_secret):
        raise HTTPException(status_code=401, detail="Invalid username, password, or authenticator code")
    return _issue_session(response, username=config.username, config=config)


@router.post("/logout", response_model=SessionResponse)
async def logout(response: Response) -> SessionResponse:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return SessionResponse(authenticated=False)


@router.get("/session", response_model=SessionResponse)
async def session(session: OperatorSessionDependency) -> SessionResponse:
    return SessionResponse(
        authenticated=True,
        username=session.username,
        expires_at_ms=session.expires_at * 1000,
    )
