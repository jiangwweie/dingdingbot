from __future__ import annotations

from fastapi.testclient import TestClient

from src.interfaces.operator_auth import create_password_hash


def _configure_auth(monkeypatch):
    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("pw"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")


def _totp() -> str:
    from src.interfaces.operator_auth import _hotp
    import time

    return _hotp("JBSWY3DPEHPK3PXP", int(time.time() // 30))


def test_brc_console_requires_session(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        response = client.get("/api/brc/dashboard")
        assert response.status_code == 401


def test_brc_console_dashboard_is_human_readable_after_login(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "owner", "password": "pw", "totp_code": _totp()},
        )
        assert login.status_code == 200

        response = client.get("/api/brc/dashboard")
        assert response.status_code == 200
        payload = response.json()
        assert payload["live_ready"] is False
        assert payload["current_stage"]
        assert "Risk Envelope" in payload["terminology"]
        assert "现在能不能做？" in payload["owner_questions"]


def test_legacy_research_and_config_routes_are_not_mounted(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert client.get("/api/research/jobs").status_code == 404
        assert client.get("/api/v1/config").status_code == 404
