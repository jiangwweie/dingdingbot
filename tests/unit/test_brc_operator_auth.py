from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.interfaces.operator_auth import (
    SESSION_COOKIE,
    create_password_hash,
    router,
    verify_totp,
)


def _totp(secret: str) -> str:
    from src.interfaces.operator_auth import _hotp
    import time

    return _hotp(secret, int(time.time() // 30))


def test_operator_auth_login_session_and_logout(monkeypatch):
    secret = "JBSWY3DPEHPK3PXP"
    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("correct horse"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", secret)
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_TTL_SECONDS", "3600")

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "correct horse", "totp_code": _totp(secret)},
        )
        assert response.status_code == 200
        assert response.json()["authenticated"] is True
        assert SESSION_COOKIE in response.cookies

        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["username"] == "owner"

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 200
        assert logout.json()["authenticated"] is False


def test_operator_auth_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("correct horse"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "wrong", "totp_code": "123456"},
        )
        assert response.status_code == 401


def test_operator_auth_missing_env_fails_closed(monkeypatch):
    for key in (
        "BRC_OPERATOR_USERNAME",
        "BRC_OPERATOR_PASSWORD_HASH",
        "BRC_OPERATOR_TOTP_SECRET",
        "BRC_OPERATOR_SESSION_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/auth/session")
        assert response.status_code == 503
        assert response.json()["detail"]["error_code"] == "BRC-AUTH-CONFIG-MISSING"


def test_totp_accepts_current_code_and_rejects_bad_code():
    secret = "JBSWY3DPEHPK3PXP"
    assert verify_totp(_totp(secret), secret)
    assert not verify_totp("000000", secret)
