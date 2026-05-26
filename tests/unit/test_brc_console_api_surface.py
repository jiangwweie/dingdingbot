from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

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


def _login(client: TestClient):
    return client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "pw", "totp_code": _totp()},
    )


def _action(payload: dict, action_id: str) -> dict:
    for item in payload["available_actions"] + payload["disabled_actions"]:
        if item["action_id"] == action_id:
            return item
    raise AssertionError(f"action not found: {action_id}")


def _config_provider(*, profile: str = "brc_btc_eth_testnet_runtime", testnet: bool = True):
    return SimpleNamespace(
        resolved_config=SimpleNamespace(
            profile_name=profile,
            environment=SimpleNamespace(exchange_testnet=testnet),
            market=SimpleNamespace(symbols=["ETH/USDT:USDT", "BTC/USDT:USDT"]),
        )
    )


class _FakeGks:
    def __init__(self, *, active: bool = False) -> None:
        self._active = active

    def is_active(self) -> bool:
        return self._active


class _FakeStartupGuard:
    def __init__(self, *, armed: bool = True) -> None:
        self._armed = armed

    def is_armed(self) -> bool:
        return self._armed


class _FakeCampaign:
    campaign_id = "brc_unit_latest"
    status = SimpleNamespace(value="ended")
    outcome = SimpleNamespace(value="ended_testnet_rehearsal_complete_loss_locked")
    current_playbook_id = "PB-004-BRC-CONTROLLED-TESTNET"
    realized_pnl = Decimal("-120")
    attempt_count = 2
    risk_envelope = SimpleNamespace(
        max_attempts=2,
        profit_protect_trigger=Decimal("100"),
        max_campaign_loss=Decimal("120"),
    )
    finalized_at_ms = 123456


class _FakeBrcService:
    def __init__(self, campaign=None, review=None) -> None:
        self._campaign = campaign
        self._review = review
        self.mutation_calls = 0

    async def get_latest_campaign(self):
        return self._campaign

    async def get_latest_review_decision(self):
        return self._review

    async def list_operator_actions(self, *, campaign_id=None, limit: int = 50):
        return []

    async def create_campaign(self, *args, **kwargs):  # pragma: no cover - should never be called
        self.mutation_calls += 1
        raise AssertionError("readiness must not mutate campaigns")


def _patch_runtime(monkeypatch, *, campaign=None):
    from src.interfaces import api as api_module

    service = _FakeBrcService(campaign=campaign)
    monkeypatch.setattr(api_module, "get_runtime_context", lambda: object())
    monkeypatch.setattr(api_module, "_runtime_config_provider", _config_provider())
    monkeypatch.setattr(api_module, "_brc_campaign_service", service)
    monkeypatch.setattr(api_module, "_global_kill_switch_service", _FakeGks(active=False))
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", _FakeStartupGuard(armed=True))
    return service


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
        login = _login(client)
        assert login.status_code == 200

        response = client.get("/api/brc/dashboard")
        assert response.status_code == 200
        payload = response.json()
        assert payload["live_ready"] is False
        assert payload["current_stage"]
        assert "Risk Envelope" in payload["terminology"]
        assert "现在能不能做？" in payload["owner_questions"]


def test_brc_readiness_standalone_returns_owner_safe_summary(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces import api as api_module
    from src.interfaces.api import app

    monkeypatch.setattr(api_module, "get_runtime_context", lambda: None)
    monkeypatch.setattr(api_module, "_runtime_config_provider", None)
    monkeypatch.setattr(api_module, "_brc_campaign_service", None)

    with TestClient(app) as client:
        assert _login(client).status_code == 200

        response = client.get("/api/brc/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["mode"] == "standalone_console"
    assert _action(payload, "create_read_only_plan")["enabled"] is False
    assert _action(payload, "write_review_decision")["enabled"] is False
    assert "Standalone Console" in " ".join(payload["why"])


def test_brc_readiness_no_campaign_disables_review_only(monkeypatch):
    _configure_auth(monkeypatch)
    service = _patch_runtime(monkeypatch, campaign=None)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200

        response = client.get("/api/brc/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] in {"brc_ready", "testnet_ready"}
    assert _action(payload, "create_read_only_plan")["enabled"] is True
    assert _action(payload, "write_review_decision")["enabled"] is False
    assert payload["latest_campaign"] is None
    assert service.mutation_calls == 0


def test_brc_readiness_latest_campaign_enables_review_without_mutation(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    service = _patch_runtime(monkeypatch, campaign=_FakeCampaign())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200

        response = client.get("/api/brc/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_campaign"]["campaign_id"] == "brc_unit_latest"
    assert _action(payload, "write_review_decision")["enabled"] is True
    assert _action(payload, "run_controlled_testnet_workflow")["enabled"] is True
    assert service.mutation_calls == 0


def test_legacy_research_and_config_routes_are_not_mounted(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert client.get("/api/research/jobs").status_code == 404
        assert client.get("/api/v1/config").status_code == 404
