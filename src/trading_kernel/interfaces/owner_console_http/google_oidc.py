"""Bounded Google OIDC login; the existing Owner Session remains the authority."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode

import httpx
import jwt
from pydantic import ConfigDict, Field, SecretStr, field_validator

from src.trading_kernel.application.owner_console.models import FrozenModel
from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    LoginSession,
    OwnerAuthService,
)

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_KEYS = "https://www.googleapis.com/oauth2/v3/certs"
CALLBACK_PATH = "/api/owner/v1/auth/google/callback"
FLOW_TTL_MS = 10 * 60_000
MAX_FLOWS = 64


class GoogleOidcSettings(FrozenModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    client_id: str = Field(min_length=1, max_length=256)
    client_secret: SecretStr
    owner_email: str = Field(min_length=3, max_length=256)
    owner_subject: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("client_id", "owner_email", "owner_subject")
    @classmethod
    def require_trimmed_identity(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("OIDC identity must be nonblank and trimmed")
        return value

    @field_validator("client_secret")
    @classmethod
    def require_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("OIDC secret must be nonblank")
        return value


class GoogleBindingCandidate(FrozenModel):
    subject: str
    email: str


@dataclass(frozen=True)
class GoogleFlowStart:
    authorization_url: str
    browser_cookie: str = field(repr=False)


@dataclass(frozen=True)
class GoogleFlowResult:
    session: LoginSession | None = None


@dataclass(frozen=True)
class _Flow:
    purpose: Literal["login", "bind"]
    browser_cookie: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)
    issued_ms: int
    owner_cookie: str | None = field(default=None, repr=False)


class GoogleOidcService:
    def __init__(
        self,
        settings: GoogleOidcSettings,
        auth: OwnerAuthService,
        *,
        public_origin: str,
        clock_ms: Callable[[], int],
        client: httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self._auth = auth
        self._clock_ms = clock_ms
        self._client = client
        self._redirect_uri = public_origin + CALLBACK_PATH
        self._flows: dict[str, _Flow] = {}
        self._candidates: dict[str, tuple[GoogleBindingCandidate, _Flow]] = {}
        self._lock = asyncio.Lock()

    def _purge(self) -> None:
        now = self._clock_ms()
        self._flows = {
            k: v for k, v in self._flows.items() if 0 <= now - v.issued_ms < FLOW_TTL_MS
        }
        self._candidates = {
            k: v
            for k, v in self._candidates.items()
            if 0 <= now - v[1].issued_ms < FLOW_TTL_MS
        }

    async def begin(
        self,
        purpose: Literal["login", "bind"],
        *,
        owner_cookie: str | None = None,
        totp_code: str | None = None,
    ) -> GoogleFlowStart:
        if purpose == "login":
            if not self.settings.owner_subject:
                raise InvalidCredentials
        else:
            if self.settings.owner_subject or not await self._auth.validate_cookie(
                owner_cookie, now_ms=self._clock_ms()
            ):
                raise InvalidCredentials
            await self._auth.verify_step_up(totp_code or "", now_ms=self._clock_ms())
        state, browser_cookie = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        async with self._lock:
            self._purge()
            if len(self._flows) + len(self._candidates) >= MAX_FLOWS:
                raise InvalidCredentials
            self._flows[state] = _Flow(
                purpose, browser_cookie, nonce, verifier, self._clock_ms(), owner_cookie
            )
        return GoogleFlowStart(
            GOOGLE_AUTHORIZE
            + "?"
            + urlencode(
                {
                    "client_id": self.settings.client_id,
                    "redirect_uri": self._redirect_uri,
                    "response_type": "code",
                    "scope": "openid email",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "prompt": "select_account",
                }
            ),
            browser_cookie,
        )

    async def complete(
        self, state: str, code: str, browser_cookie: str | None
    ) -> GoogleFlowResult:
        async with self._lock:
            self._purge()
            flow = self._flows.get(state)
            if (
                flow is None
                or not browser_cookie
                or not secrets.compare_digest(browser_cookie, flow.browser_cookie)
            ):
                raise InvalidCredentials
            del self._flows[
                state
            ]  # One use, even when exchange or proof verification fails.
        try:
            token_response = await self._client.post(
                GOOGLE_TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret.get_secret_value(),
                    "redirect_uri": self._redirect_uri,
                    "code_verifier": flow.verifier,
                },
                timeout=5.0,
                follow_redirects=False,
            )
            token_response.raise_for_status()
            if len(token_response.content) > 65_536:
                raise InvalidCredentials
            token_payload = token_response.json()
            if not isinstance(token_payload, dict):
                raise InvalidCredentials
            token = token_payload.get("id_token")
            if not isinstance(token, str) or not 1 <= len(token) <= 16_384:
                raise InvalidCredentials
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise InvalidCredentials
            keys_response = await self._client.get(
                GOOGLE_KEYS, timeout=5.0, follow_redirects=False
            )
            keys_response.raise_for_status()
            if len(keys_response.content) > 65_536:
                raise InvalidCredentials
            key_payload = keys_response.json()
            if not isinstance(key_payload, dict) or not isinstance(
                key_payload.get("keys"), list
            ):
                raise InvalidCredentials
            matches = [
                key
                for key in key_payload["keys"]
                if isinstance(key, dict)
                and key.get("kid") == header["kid"]
                and key.get("kty") == "RSA"
                and key.get("alg", "RS256") == "RS256"
                and key.get("use", "sig") == "sig"
            ]
            if len(matches) != 1:
                raise InvalidCredentials
            claims = jwt.decode(
                token,
                jwt.PyJWK.from_dict(matches[0]).key,
                algorithms=["RS256"],
                audience=self.settings.client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "iat",
                        "exp",
                        "nonce",
                        "email",
                        "email_verified",
                    ],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            now = self._clock_ms() / 1000
            if (
                not 0 <= self._clock_ms() - flow.issued_ms < FLOW_TTL_MS
                or type(claims["exp"]) is not int
                or type(claims["iat"]) is not int
                or claims["exp"] <= now
                or claims["iat"] > now + 30
                or claims["exp"] <= claims["iat"]
                or now - claims["iat"] > 600
                or claims["nonce"] != flow.nonce
                or claims["email_verified"] is not True
                or claims["email"] != self.settings.owner_email
                or not isinstance(claims["sub"], str)
                or not 1 <= len(claims["sub"]) <= 255
                or (
                    claims.get("azp") is not None
                    and claims["azp"] != self.settings.client_id
                )
                or (
                    isinstance(claims["aud"], list)
                    and len(claims["aud"]) > 1
                    and claims.get("azp") != self.settings.client_id
                )
            ):
                raise InvalidCredentials
            if flow.purpose == "bind":
                if not await self._auth.validate_cookie(
                    flow.owner_cookie, now_ms=self._clock_ms()
                ):
                    raise InvalidCredentials
                candidate = GoogleBindingCandidate(
                    subject=claims["sub"], email=claims["email"]
                )
                async with self._lock:
                    self._purge()
                    self._candidates[browser_cookie] = (candidate, flow)
                return GoogleFlowResult()
            if not secrets.compare_digest(
                claims["sub"], self.settings.owner_subject or ""
            ):
                raise InvalidCredentials
            return GoogleFlowResult(
                await self._auth.issue_google_session(now_ms=self._clock_ms())
            )
        except (httpx.HTTPError, jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise InvalidCredentials from None

    async def binding_candidate(
        self, browser_cookie: str | None, owner_cookie: str | None
    ) -> GoogleBindingCandidate:
        async with self._lock:
            self._purge()
            item = self._candidates.get(browser_cookie or "")
        if (
            item is None
            or not owner_cookie
            or item[1].owner_cookie != owner_cookie
            or not await self._auth.validate_cookie(
                owner_cookie, now_ms=self._clock_ms()
            )
        ):
            raise InvalidCredentials
        return item[0]
