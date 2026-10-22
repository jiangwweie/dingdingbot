"""Google login security boundaries with signed local tokens and mocked HTTPS."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.trading_kernel.interfaces.owner_console_http.auth import (
    InvalidCredentials,
    OwnerAuthService,
)
from src.trading_kernel.interfaces.owner_console_http.google_oidc import (
    GoogleOidcService,
    GoogleOidcSettings,
)
from tests.trading_kernel.unit.owner_console.test_auth import (
    BASE_MS,
    PASSWORD,
    TOTP_SEED,
    auth_settings,
)


@pytest.fixture
def harness():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = [BASE_MS]
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test.apps.googleusercontent.com",
        "sub": "google-owner-123",
        "email": "owner@example.com",
        "email_verified": True,
        "iat": BASE_MS // 1000,
        "exp": BASE_MS // 1000 + 300,
    }
    requests = []
    nonce = [""]

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/token":
            payload = {**claims, "nonce": nonce[0]}
            token = jwt.encode(
                payload, key, algorithm="RS256", headers={"kid": "test-key"}
            )
            return httpx.Response(200, json={"id_token": token})
        return httpx.Response(
            200,
            json={
                "keys": [
                    jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
                    | {"kid": "test-key", "use": "sig", "alg": "RS256"}
                ]
            },
        )

    auth = OwnerAuthService(
        auth_settings(idle_timeout_ms=600_000, absolute_timeout_ms=900_000)
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    settings = GoogleOidcSettings(
        client_id="test.apps.googleusercontent.com",
        client_secret="TEST-SECRET",
        owner_email="owner@example.com",
        owner_subject="google-owner-123",
    )
    service = GoogleOidcService(
        settings,
        auth,
        public_origin="https://owner.example.test",
        clock_ms=lambda: now[0],
        client=client,
    )
    return service, auth, settings, client, claims, requests, nonce, now


async def begin(h, purpose="login", **kwargs):
    flow = await h[0].begin(purpose, **kwargs)
    params = parse_qs(urlparse(flow.authorization_url).query)
    h[6][0] = params["nonce"][0]
    return flow, params


async def test_google_login_uses_pkce_and_reuses_owner_session_authority(harness):
    h = harness
    flow, params = await begin(h)
    assert params["scope"] == ["openid email"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == [
        "https://owner.example.test/api/owner/v1/auth/google/callback"
    ]
    result = await h[0].complete(params["state"][0], "test-code", flow.browser_cookie)
    assert result.session is not None
    assert await h[1].validate_cookie(result.session.cookie, now_ms=BASE_MS)
    token_request = h[5][0]
    assert b"code_verifier=" in token_request.content
    assert "TEST-SECRET" not in flow.authorization_url
    with pytest.raises(InvalidCredentials):
        await h[0].complete(params["state"][0], "test-code", flow.browser_cookie)
    await h[3].aclose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("sub", "other-owner"),
        ("email", "other@example.com"),
        ("email_verified", "true"),
        ("iss", "https://evil.example"),
        ("aud", "other-client"),
        ("exp", BASE_MS // 1000 - 90),
        ("iat", BASE_MS // 1000 + 300),
        ("azp", "other-client"),
        ("aud", ["test.apps.googleusercontent.com", "other-client"]),
    ],
)
async def test_google_identity_claims_fail_closed(harness, field, value):
    h = harness
    h[4][field] = value
    flow, params = await begin(h)
    with pytest.raises(InvalidCredentials):
        await h[0].complete(params["state"][0], "test-code", flow.browser_cookie)
    await h[3].aclose()


@pytest.mark.parametrize("failure", ["cookie", "state", "nonce", "expired"])
async def test_callback_is_bound_to_original_browser_and_short_lived_flow(
    harness, failure
):
    h = harness
    flow, params = await begin(h)
    state, browser_cookie = params["state"][0], flow.browser_cookie
    if failure == "cookie":
        browser_cookie = "other-browser"
    elif failure == "state":
        state = "unknown-state"
    elif failure == "nonce":
        h[6][0] = "wrong-nonce"
    else:
        h[7][0] += 601_000
    with pytest.raises(InvalidCredentials):
        await h[0].complete(state, "test-code", browser_cookie)
    await h[3].aclose()


async def test_first_binding_requires_local_session_and_totp_and_does_not_create_google_session(
    harness,
):
    h = harness
    settings = h[2].model_copy(update={"owner_subject": None})
    service = GoogleOidcService(
        settings,
        h[1],
        public_origin="https://owner.example.test",
        clock_ms=lambda: h[7][0],
        client=h[3],
    )
    h = (service, *h[1:])
    with pytest.raises(InvalidCredentials):
        await begin(h)
    with pytest.raises(InvalidCredentials):
        await begin(h, "bind", owner_cookie="missing", totp_code="123456")
    local = await h[1].login(
        username="owner",
        password=PASSWORD,
        totp_code=pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1000),
        source_ip="local",
        now_ms=BASE_MS,
    )
    flow, params = await begin(
        h,
        "bind",
        owner_cookie=local.cookie,
        totp_code=pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1000),
    )
    result = await service.complete(
        params["state"][0], "test-code", flow.browser_cookie
    )
    assert result.session is None
    candidate = await service.binding_candidate(flow.browser_cookie, local.cookie)
    assert candidate.subject == "google-owner-123"
    assert candidate.email == "owner@example.com"
    await h[1].logout(local.cookie)
    with pytest.raises(InvalidCredentials):
        await service.binding_candidate(flow.browser_cookie, local.cookie)
    await h[3].aclose()


async def test_failed_google_exchange_never_leaks_tokens_or_creates_session(harness):
    h = harness
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, text="SECRET-TOKEN")
        )
    )
    service = GoogleOidcService(
        h[2],
        h[1],
        public_origin="https://owner.example.test",
        clock_ms=lambda: BASE_MS,
        client=client,
    )
    flow = await service.begin("login")
    state = parse_qs(urlparse(flow.authorization_url).query)["state"][0]
    with pytest.raises(InvalidCredentials) as error:
        await service.complete(state, "SECRET-CODE", flow.browser_cookie)
    assert "SECRET" not in str(error.value)
    await client.aclose()
    await h[3].aclose()


async def test_public_login_roundtrip_http_cookies_and_control_step_up(harness):
    from src.trading_kernel.interfaces.owner_console_http.app import (
        create_owner_console_app,
    )
    from src.trading_kernel.interfaces.owner_console_http.dependencies import (
        OwnerConsoleSettings,
    )

    h = harness
    settings = OwnerConsoleSettings(
        database_dsn="postgresql+asyncpg://unused",
        account_id="test",
        auth=auth_settings(),
        google_oidc=h[2],
        public_origin="https://owner.example.test",
        public_host="owner.example.test",
    )
    app = create_owner_console_app(settings)
    app.state.owner_console_settings = settings
    app.state.owner_auth_service = h[1]
    app.state.owner_clock_ms = lambda: BASE_MS
    app.state.owner_google_oidc = h[0]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://owner.example.test"
    ) as client:
        providers = await client.get("/api/owner/v1/auth/providers")
        assert providers.json() == {"google_login": True, "google_binding": False}
        assert (await client.get("/api/owner/v1/auth/session")).status_code == 401
        assert (
            await client.post(
                "/api/owner/v1/auth/google/bind/start", json={"totp_code": "123456"}
            )
        ).status_code == 401
        start = await client.get("/api/owner/v1/auth/google/start")
        assert start.status_code == 303
        assert "SameSite=lax" in start.headers["set-cookie"]
        assert (
            "HttpOnly" in start.headers["set-cookie"]
            and "Secure" in start.headers["set-cookie"]
        )
        params = parse_qs(urlparse(start.headers["location"]).query)
        h[6][0] = params["nonce"][0]
        callback = await client.get(
            "/api/owner/v1/auth/google/callback",
            params={"state": params["state"][0], "code": "secret-code"},
        )
        assert (
            callback.status_code == 303
            and callback.headers["location"] == "/trading/?google_result=success"
        )
        assert "SameSite=strict" in callback.headers["set-cookie"]
        assert callback.headers["referrer-policy"] == "no-referrer"
        assert (await client.get("/api/owner/v1/auth/session")).json() == {
            "authenticated": True
        }
        # Federated login does not satisfy a control action's TOTP step-up.
        denied = await client.post(
            "/api/owner/v1/controls/entry/resume",
            headers={"origin": "https://owner.example.test"},
            json={
                "expected_version": 1,
                "reason": "test",
                "idempotency_key": "test",
                "totp_code": None,
            },
        )
        assert denied.status_code == 403
        assert (await client.post("/api/owner/v1/auth/logout")).status_code == 204
        assert (await client.get("/api/owner/v1/auth/session")).status_code == 401
    await h[3].aclose()


async def test_callback_host_denial_and_google_error_never_issue_session(harness):
    from src.trading_kernel.interfaces.owner_console_http.app import (
        create_owner_console_app,
    )
    from src.trading_kernel.interfaces.owner_console_http.dependencies import (
        OwnerConsoleSettings,
    )

    h = harness
    settings = OwnerConsoleSettings(
        database_dsn="postgresql+asyncpg://unused",
        account_id="test",
        auth=auth_settings(),
        google_oidc=h[2],
        public_origin="https://owner.example.test",
        public_host="owner.example.test",
    )
    app = create_owner_console_app(settings)
    app.state.owner_console_settings = settings
    app.state.owner_auth_service = h[1]
    app.state.owner_google_oidc = h[0]
    app.state.owner_clock_ms = lambda: BASE_MS
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://owner.example.test"
    ) as client:
        denied = await client.get(
            "/api/owner/v1/auth/google/start", headers={"host": "evil.example"}
        )
        assert denied.status_code == 401
        callback = await client.get(
            "/api/owner/v1/auth/google/callback?error=access_denied&state=secret-state"
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "/trading/?google_result=error"
        assert (await client.get("/api/owner/v1/auth/session")).status_code == 401
        assert h[5] == []
    await h[3].aclose()


@pytest.mark.parametrize(
    "mutation",
    ["signature", "algorithm", "missing_nonce", "missing_exp", "unverified_email"],
)
async def test_signed_token_structure_and_signatures_are_enforced(harness, mutation):
    h = harness
    flow, params = await begin(h)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = {**h[4], "nonce": h[6][0]}
    if mutation == "missing_nonce":
        payload.pop("nonce")
    elif mutation == "missing_exp":
        payload.pop("exp")
    elif mutation == "unverified_email":
        payload["email_verified"] = False
    if mutation == "algorithm":
        token = jwt.encode(
            payload,
            "not-the-google-key-with-more-than-32-bytes",
            algorithm="HS256",
            headers={"kid": "test-key"},
        )
    else:
        token = jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})
    public_key = other_key if mutation == "signature" else key

    def handle(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"id_token": token})
        return httpx.Response(
            200,
            json={
                "keys": [
                    jwt.algorithms.RSAAlgorithm.to_jwk(
                        public_key.public_key(), as_dict=True
                    )
                    | {"kid": "test-key"}
                ]
            },
        )

    await h[3].aclose()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    h[0]._client = client
    with pytest.raises(InvalidCredentials):
        await h[0].complete(params["state"][0], "test-code", flow.browser_cookie)
    await client.aclose()


async def test_unconfigured_google_provider_keeps_original_login_available():
    from src.trading_kernel.interfaces.owner_console_http.app import (
        create_owner_console_app,
    )
    from src.trading_kernel.interfaces.owner_console_http.dependencies import (
        OwnerConsoleSettings,
    )

    settings = OwnerConsoleSettings(
        database_dsn="postgresql+asyncpg://unused",
        account_id="test",
        auth=auth_settings(),
    )
    app = create_owner_console_app(settings)
    app.state.owner_console_settings = settings
    app.state.owner_auth_service = OwnerAuthService(settings.auth)
    app.state.owner_clock_ms = lambda: BASE_MS
    app.state.owner_google_oidc = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://jiaoyingpan.cloud"
    ) as client:
        assert (await client.get("/api/owner/v1/auth/providers")).json() == {
            "google_login": False,
            "google_binding": False,
        }
        assert (await client.get("/api/owner/v1/auth/google/start")).status_code == 401
        login = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1000),
            },
        )
        assert login.status_code == 204
        assert (await client.get("/api/owner/v1/auth/session")).json() == {
            "authenticated": True
        }
