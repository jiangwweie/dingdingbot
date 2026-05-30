from __future__ import annotations

import asyncio
import json
import time
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
        self.arm_calls: list[dict[str, str]] = []

    def is_armed(self) -> bool:
        return self._armed

    def manual_arm(self, *, reason, updated_by):
        self.arm_calls.append({"reason": reason, "updated_by": updated_by})
        self._armed = True
        return SimpleNamespace(
            armed=True,
            reason=reason,
            updated_by=updated_by,
            source="manual_arm",
        )


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

    async def list_workflow_runs(self, *, limit: int = 50, status=None):
        return []

    async def list_review_decisions(self, *, campaign_id=None, limit: int = 50):
        return []

    async def create_campaign(self, *args, **kwargs):  # pragma: no cover - should never be called
        self.mutation_calls += 1
        raise AssertionError("readiness must not mutate campaigns")


class _FakePositionRepo:
    def __init__(self, positions=None) -> None:
        self._positions = list(positions or [])

    async def list_active(self, *, symbol=None, limit: int = 20):
        if symbol is None:
            return self._positions[:limit]
        return [item for item in self._positions if getattr(item, "symbol", None) == symbol][:limit]


class _FakeOrderRepo:
    def __init__(self, orders=None) -> None:
        self._orders = list(orders or [])

    async def get_open_orders(self, symbol=None):
        if symbol is None:
            return self._orders
        return [item for item in self._orders if getattr(item, "symbol", None) == symbol]


class _FakePosition:
    def __init__(self, symbol: str = "ETH/USDT:USDT") -> None:
        self.position_id = "pos_unit"
        self.symbol = symbol
        self.quantity = "0.01"


class _FakeOrder:
    def __init__(self, symbol: str = "ETH/USDT:USDT") -> None:
        self.order_id = "ord_unit"
        self.symbol = symbol
        self.status = "OPEN"


class _FakeExchangeGateway:
    def __init__(
        self,
        *,
        positions=None,
        open_orders=None,
        recent_orders=None,
        recent_fills=None,
        account_snapshot=None,
    ) -> None:
        self.positions = list(positions or [])
        self.open_orders = list(open_orders or [])
        self.recent_orders = list(recent_orders or [])
        self.recent_fills = list(recent_fills or [])
        self.account_snapshot = account_snapshot
        self.position_symbols: list[str] = []
        self.open_order_calls: list[tuple[str, dict | None]] = []
        self.account_snapshot_calls = 0

    async def fetch_positions(self, symbol=None):
        self.position_symbols.append(symbol)
        return [item for item in self.positions if getattr(item, "symbol", item.get("symbol") if isinstance(item, dict) else None) == symbol]

    async def fetch_open_orders(self, symbol, params=None):
        self.open_order_calls.append((symbol, params))
        return [item for item in self.open_orders if item.get("symbol") == symbol]

    async def fetch_orders(self, symbol, limit=20):
        return [item for item in self.recent_orders if item.get("symbol") == symbol][:limit]

    async def fetch_my_trades(self, symbol, limit=20):
        return [item for item in self.recent_fills if item.get("symbol") == symbol][:limit]

    def get_account_snapshot(self):
        self.account_snapshot_calls += 1
        return self.account_snapshot

    async def fetch_account_balance(self):  # pragma: no cover - must not be called by account facts
        raise AssertionError("account facts must use cached AccountSnapshot only")

    async def place_order(self, *_args, **_kwargs):  # pragma: no cover - must never be called
        raise AssertionError("account facts must not place orders")

    async def cancel_order(self, *_args, **_kwargs):  # pragma: no cover - must never be called
        raise AssertionError("account facts must not cancel orders")


class _EmptyPositionRepo:
    async def list_active(self, *, symbol=None, limit: int = 20):
        return []


class _EmptyOrderRepo:
    async def get_open_orders(self, symbol=None):
        return []


class _FailingPositionRepo:
    async def list_active(self, *, symbol=None, limit: int = 20):
        raise RuntimeError("position db offline")


class _FailingOrderRepo:
    async def get_open_orders(self, symbol=None):
        raise RuntimeError("order db offline")


def _patch_runtime(
    monkeypatch,
    *,
    campaign=None,
    position_repo=None,
    order_repo=None,
    exchange_gateway=None,
    startup_guard=None,
):
    from src.interfaces import api as api_module

    service = _FakeBrcService(campaign=campaign)
    monkeypatch.setattr(api_module, "get_runtime_context", lambda: object())
    monkeypatch.setattr(api_module, "_runtime_config_provider", _config_provider())
    monkeypatch.setattr(api_module, "_brc_campaign_service", service)
    monkeypatch.setattr(api_module, "_global_kill_switch_service", _FakeGks(active=False))
    guard = startup_guard or _FakeStartupGuard(armed=True)
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", guard)
    monkeypatch.setattr(api_module, "_position_repo", position_repo or _EmptyPositionRepo())
    monkeypatch.setattr(api_module, "_order_repo", order_repo or _EmptyOrderRepo())
    monkeypatch.setattr(api_module, "_exchange_gateway", exchange_gateway)
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


def test_brc_operations_api_switch_playbook_flow(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces import api as api_module
    from src.interfaces.api import app
    from tests.unit.test_brc_operation_layer import _operation_service

    service, _, brc_repo, _ = asyncio.run(_operation_service())
    monkeypatch.setattr(api_module, "_brc_operation_service", service)
    monkeypatch.setattr(api_module, "_brc_campaign_service", getattr(service, "_brc"))

    with TestClient(app) as client:
        assert _login(client).status_code == 200

        capabilities = client.get("/api/brc/operations/capabilities")
        assert capabilities.status_code == 200
        capability_payload = capabilities.json()
        switch_capability = next(
            item for item in capability_payload["capabilities"] if item["operation_type"] == "switch_playbook"
        )
        assert switch_capability["executable_through_operation"] is True

        preflight = client.post(
            "/api/brc/operations/preflight",
            json={
                "operation_type": "switch_playbook",
                "requested_by": "owner",
                "input_params": {
                    "target_playbook_id": "PB-004-BRC-CONTROLLED-TESTNET",
                    "reason_text": "owner authorized controlled rehearsal",
                    "evidence_refs": ["evidence"],
                },
                "source": {"kind": "ui"},
            },
        )
        assert preflight.status_code == 200
        preflight_payload = preflight.json()
        assert preflight_payload["status"] == "awaiting_confirmation"

        confirmed = client.post(
            f"/api/brc/operations/{preflight_payload['operation_id']}/confirm",
            json={
                "preflight_id": preflight_payload["preflight_id"],
                "confirmation_phrase": "CONFIRM_SWITCH_PLAYBOOK",
                "idempotency_key": preflight_payload["idempotency_key"],
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "executed"
        assert brc_repo.campaign.current_playbook_id == "PB-004-BRC-CONTROLLED-TESTNET"

        repeated = client.post(
            f"/api/brc/operations/{preflight_payload['operation_id']}/confirm",
            json={
                "preflight_id": preflight_payload["preflight_id"],
                "confirmation_phrase": "CONFIRM_SWITCH_PLAYBOOK",
                "idempotency_key": preflight_payload["idempotency_key"],
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["status"] == "executed"
        assert len(brc_repo.switches) == 1

        get_result = client.get(f"/api/brc/operations/{preflight_payload['operation_id']}")
        assert get_result.status_code == 200
        assert get_result.json()["operation"]["status"] == "executed"

        listed = client.get("/api/brc/operations?limit=10")
        assert listed.status_code == 200
        assert listed.json()["operations"][0]["operation_id"] == preflight_payload["operation_id"]

        audit = client.get("/api/brc/audit-trail?limit=10")
        assert audit.status_code == 200
        audit_payload = audit.json()
        operation_items = [item for item in audit_payload["timeline"] if item["type"] == "operation"]
        assert operation_items[0]["id"] == preflight_payload["operation_id"]
        assert audit_payload["operation_results"][0]["campaign_refs"]


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


def test_brc_readiness_includes_owner_console_summaries(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_runtime(monkeypatch, campaign=_FakeCampaign())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["markets_summary"]["all_local_flat"] is True
    assert payload["playbook_summary"]["strategy_execution_enabled"] is False
    assert payload["parameter_summary"]["risk_envelope"]["max_attempts"] == 2
    assert payload["ai_investigator_summary"]["free_sql_enabled"] is False
    assert payload["environment_boundary"]["current"] == "simulation"
    assert payload["environment_boundary"]["future_live"]["display"] == "disabled_boundary"
    assert payload["runtime_state"] == "monitor"
    assert payload["risk_decision"] == "ALLOW_MONITOR"
    assert payload["risk_account_summary"]["risk_decision"] == "ALLOW_MONITOR"
    assert payload["strategy_playbook_summary"]["strategy_execution_enabled"] is False
    card = next(item for item in payload["action_cards"] if item["action_type"] == "testnet_rehearsal")
    assert card["authority_source"] == "application_preflight"
    assert card["fact_snapshot_id"]
    assert card["preflight_result_id"]
    assert card["idempotency_key"]
    assert card["expiry_time"]
    assert card["final_state_proof_required"] is True
    assert "live_trade" in card["blocked_next_states"]
    assert payload["global_cutoff_controls"][0]["action_type"] == "pause_new_entries"


def test_brc_readiness_attention_required_blocks_testnet_when_exposure_unknown(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    _patch_runtime(
        monkeypatch,
        campaign=_FakeCampaign(),
        position_repo=_FakePositionRepo([_FakePosition()]),
        order_repo=_FakeOrderRepo([_FakeOrder()]),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_state"] == "attention_required"
    assert payload["risk_decision"] == "ATTENTION_REQUIRED"
    assert payload["risk_account_summary"]["exposure_orders"]["unknown_exposure"] is True
    card = next(item for item in payload["action_cards"] if item["action_type"] == "testnet_rehearsal")
    assert card["enabled"] is False
    assert card["authority_source"] == "application_preflight"
    assert card["allowed_next_states"] == []


def test_startup_guard_readiness_arm_requires_runtime_guard(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    from src.interfaces import api as api_module
    from src.interfaces.api import app

    monkeypatch.setattr(api_module, "get_runtime_context", lambda: None)
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", None)

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/readiness/startup-guard/preflight-arm",
            json={"reason": "unit", "updated_by": "owner"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["runtime_bound"] is False
    assert payload["trial_started"] is False
    assert payload["execution_intent_created"] is False
    assert payload["order_created"] is False
    assert payload["next_checklist_verdict"] == "blocked_runtime_start_required"


def test_mi001_sol_owner_console_view_exposes_safe_mainline(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces import api as api_module
    from src.interfaces.api import app

    monkeypatch.setattr(api_module, "get_runtime_context", lambda: None)
    monkeypatch.setattr(api_module, "_global_kill_switch_service", _FakeGks(active=False))
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", None)

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/readiness/mi001-sol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["candidate"]["candidate_id"] == "MI-001-SOL-LONG"
    assert payload["candidate"]["symbol"] == "SOL/USDT:USDT"
    assert payload["candidate"]["side"] == "long"
    assert payload["evidence"]["signal_count"] == 8135
    assert payload["evidence"]["positive_rate_72h"] == "0.5175"
    assert payload["evidence"]["mean_7d"] == "4.7372"
    assert "no campaign replay" in payload["evidence"]["limitations"]
    assert payload["risk_policy"]["operation_layer_notional_cap"] == "18262.85481460"
    assert payload["readiness"]["verdict"] == "blocked_startup_guard_runtime_coupled"
    checks = {item["check"]: item for item in payload["readiness"]["checks"]}
    assert checks["PG registration"]["status"] == "pass"
    assert checks["Account facts"]["status"] == "pass"
    assert checks["Operation Layer notional cap"]["status"] == "pass"
    assert checks["Startup guard"]["blocking"] is True
    assert payload["startup_guard_action"]["endpoint"] == "/api/brc/readiness/startup-guard/preflight-arm"
    assert payload["startup_guard_action"]["enabled"] is False
    assert payload["startup_guard_action"]["does_not_start_trial"] is True
    assert payload["startup_guard_action"]["does_not_create_execution_intent"] is True
    assert payload["startup_guard_action"]["does_not_place_order"] is True
    assert payload["non_permissions"]["no_execution_permission"] is True
    assert payload["non_permissions"]["no_order_permission"] is True
    assert payload["non_permissions"]["no_runtime_start"] is True
    assert payload["non_permissions"]["no_leverage_change"] is True
    assert payload["non_permissions"]["no_automatic_trial_start"] is True
    disabled = payload["owner_actions"]["disabled_actions"]
    assert {item["action_id"] for item in disabled} >= {
        "start_trial",
        "place_order",
        "grant_execution_permission",
    }


def test_strategy_group_reviewability_api_exposes_safe_shelf(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/strategy-groups/reviewability")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert len(payload["primary_groups"]) == 6
    assert len(payload["secondary_groups"]) == 2
    assert {item["strategy_group_id"] for item in payload["primary_groups"]} == {
        "MI-001",
        "VI-001",
        "CPM-RO-001",
        "TB",
        "PC",
        "VB",
    }
    assert {item["strategy_group_id"] for item in payload["secondary_groups"]} == {
        "MR/RB",
        "Tier1-Data-Families",
    }

    mi = next(item for item in payload["primary_groups"] if item["strategy_group_id"] == "MI-001")
    assert "MI-001 SOL long" in mi["representative_candidates"]
    assert "MI-001 BNB long" in mi["representative_candidates"]
    assert "coverage repaired" in " ".join(mi["confidence_flags"]).lower()
    assert mi["live_readonly_observation_readiness"] == "live_readonly_observation_v1_evaluator_ready_requires_runner_binding"
    assert mi["no_execution_permission"] is True
    assert mi["no_order_permission"] is True
    assert mi["no_runtime_start"] is True

    bnb = next(item for item in payload["candidate_evidence"] if item["candidate_id"] == "MI-001-BNB-LONG")
    assert bnb["metrics"]["signal_count"] == "4166"
    assert "coverage_repaired_not_runtime_ready" in bnb["confidence_flags"]
    assert "2025 72h year split negative" in bnb["limitations"]

    cpm = next(item for item in payload["primary_groups"] if item["strategy_group_id"] == "CPM-RO-001")
    assert cpm["current_status"] == "owner_special_observation"
    assert "not_proven_alpha" in cpm["confidence_flags"]
    assert cpm["bounded_trial_readiness"] == "not_runtime_eligible_by_default"

    observation = payload["observation_chain_summary"]
    assert observation["can_record_metadata_and_evidence_without_orders"] is True
    assert observation["active_live_readonly_observation"] is False
    assert observation["strategy_specific_signal_evaluator_glue_wired"] is True
    assert observation["observation_v1_endpoint"] == "/api/brc/strategy-groups/live-readonly-observation/v1"
    assert observation["execution_intent_created"] is False
    assert observation["order_created"] is False
    assert payload["non_permissions"]["no_trial_start"] is True
    assert payload["non_permissions"]["no_execution_intent"] is True

    raw_payload = json.dumps(payload)
    assert "Start Trading" not in raw_payload
    assert "Place Order" not in raw_payload
    assert "Run Strategy" not in raw_payload
    assert "execution_permission_granted" not in raw_payload
    assert "order_permission_granted" not in raw_payload


def test_strategy_group_live_readonly_observation_v1_api_is_safe(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/strategy-groups/live-readonly-observation/v1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["live_observation_active"] is False
    candidate_ids = {item["candidate_id"] for item in payload["candidates"]}
    assert {"MI-001-SOL-LONG", "MI-001-BNB-LONG", "CPM-RO-001"} <= candidate_ids
    assert payload["runner_mapping"]["strategy_specific_signal_evaluator_glue_wired"] is True
    assert payload["non_permissions"]["no_execution_intent"] is True
    assert payload["non_permissions"]["no_order_permission"] is True

    raw_payload = json.dumps(payload)
    assert "Start Trading" not in raw_payload
    assert "Place Order" not in raw_payload
    assert "Run Strategy" not in raw_payload
    assert "execution_permission_granted" not in raw_payload
    assert "order_permission_granted" not in raw_payload


def test_mi001_sol_owner_console_view_marks_guard_action_enabled_when_runtime_ready(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    guard = _FakeStartupGuard(armed=False)
    _patch_runtime(monkeypatch, campaign=None, startup_guard=guard)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/readiness/mi001-sol")

    assert response.status_code == 200
    payload = response.json()
    assert payload["readiness"]["verdict"] == "blocked_startup_guard_runtime_coupled"
    assert payload["startup_guard_action"]["enabled"] is True
    action = next(
        item for item in payload["owner_actions"]["allowed_actions"]
        if item["action_id"] == "arm_startup_guard_preflight"
    )
    assert action["enabled"] is True
    assert action["endpoint"] == "/api/brc/readiness/startup-guard/preflight-arm"
    assert guard.arm_calls == []


def test_startup_guard_readiness_arm_requires_control_env(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.delenv("RUNTIME_CONTROL_API_ENABLED", raising=False)
    guard = _FakeStartupGuard(armed=False)
    _patch_runtime(monkeypatch, campaign=None, startup_guard=guard)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/readiness/startup-guard/preflight-arm",
            json={"reason": "unit", "updated_by": "owner"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["runtime_bound"] is True
    assert payload["runtime_control_api_enabled"] is False
    assert payload["armed_before"] is False
    assert payload["armed_after"] is False
    assert guard.arm_calls == []
    assert payload["execution_permission_granted"] is False
    assert payload["order_permission_granted"] is False


def test_startup_guard_readiness_arm_only_touches_guard(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    guard = _FakeStartupGuard(armed=False)
    service = _patch_runtime(monkeypatch, campaign=None, startup_guard=guard)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/readiness/startup-guard/preflight-arm",
            json={"reason": "MI-001 readiness", "updated_by": "owner"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "armed"
    assert payload["armed_before"] is False
    assert payload["armed_after"] is True
    assert payload["runtime_effect"] == "startup_guard_process_state_only"
    assert payload["next_checklist_verdict"] == "ready_for_trial_start_after_owner_approval"
    assert payload["trial_started"] is False
    assert payload["strategy_runtime_started"] is False
    assert payload["execution_intent_created"] is False
    assert payload["order_created"] is False
    assert payload["exchange_write_methods_called"] is False
    assert payload["execution_permission_granted"] is False
    assert payload["order_permission_granted"] is False
    assert guard.arm_calls == [{"reason": "MI-001 readiness", "updated_by": "owner"}]
    assert service.mutation_calls == 0


def test_brc_markets_orders_is_read_only_owner_summary(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_runtime(monkeypatch, campaign=None)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/markets-orders")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["source"] == "local_pg"
    assert payload["truth_level"] == "summary"
    assert payload["reconciliation_status"]["status"] == "not_available"
    assert payload["symbols"][0]["display_symbol"] == "ETHUSDT"
    assert payload["open_orders"] == []
    assert payload["active_positions"] == []
    assert payload["recent_orders"] == []
    assert payload["recent_fills"] == []
    assert any("not complete exchange account truth" in item for item in payload["limitations"])


def test_brc_account_facts_returns_local_pg_summary_without_mocking_history(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_runtime(
        monkeypatch,
        campaign=None,
        position_repo=_FakePositionRepo([_FakePosition("ETH/USDT:USDT")]),
        order_repo=_FakeOrderRepo([_FakeOrder("BTC/USDT:USDT")]),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/account/facts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["live_ready"] is False
    assert payload["source"] == "local_pg"
    assert payload["truth_level"] == "summary"
    assert payload["checked_sources"] == ["local_pg"]
    assert payload["mismatch_count"] == 0
    assert payload["unknown_unmanaged_counts"] == {"orders": 0, "positions": 0}
    assert payload["reconciliation_checked_at_ms"] == payload["generated_at_ms"]
    assert any(item.startswith("account_facts:local_pg:summary:") for item in payload["evidence_refs"])
    assert payload["source_snapshots"]["exchange_live"]["available"] is False
    assert payload["account_summary"]["active_position_count"] == 1
    assert payload["account_summary"]["open_order_count"] == 1
    assert payload["account_summary"]["complete_exchange_account_truth"] is False
    assert payload["account_summary"]["wallet_equity"] == "not_available"
    assert payload["account_summary"]["available_margin"] == "not_available"
    assert payload["recent_orders"] == []
    assert payload["recent_fills"] == []
    assert payload["unknown_or_unmanaged_orders"] == []
    assert payload["reconciliation_status"]["status"] == "not_available"
    assert payload["reconciliation_status"]["checked_sources"] == ["local_pg"]
    assert payload["connection_health"]["exchange_live_read"]["available"] is False


def test_brc_account_facts_maps_cached_account_snapshot_equity_without_balance_fetch(monkeypatch):
    _configure_auth(monkeypatch)
    snapshot = SimpleNamespace(
        total_balance=Decimal("1234.56"),
        available_balance=Decimal("987.65"),
        unrealized_pnl=Decimal("12.34"),
        positions=[],
        timestamp=int(time.time() * 1000),
    )
    gateway = _FakeExchangeGateway(account_snapshot=snapshot)
    _patch_runtime(
        monkeypatch,
        campaign=None,
        position_repo=_EmptyPositionRepo(),
        order_repo=_EmptyOrderRepo(),
        exchange_gateway=gateway,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/account/facts")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["account_summary"]
    assert summary["account_equity"] == "1234.56"
    assert summary["wallet_equity"] == "1234.56"
    assert summary["available_margin"] == "987.65"
    assert summary["account_equity_available"] is True
    assert summary["wallet_equity_available"] is True
    assert summary["available_margin_available"] is True
    assert summary["account_equity_source"] == "runtime_cached_account_snapshot"
    assert summary["account_equity_truth_level"] == "cached_exchange_read"
    assert summary["account_equity_read_method"] == "exchange_gateway.get_account_snapshot"
    assert payload["source_snapshots"]["runtime_account_snapshot"]["available"] is True
    assert payload["connection_health"]["account_equity_snapshot"]["available"] is True
    assert payload["connection_health"]["account_equity_snapshot"]["real_account_api_called_by_endpoint"] is False
    assert gateway.account_snapshot_calls == 1


def test_brc_account_facts_fail_closed_when_local_repositories_error(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_runtime(
        monkeypatch,
        campaign=None,
        position_repo=_FailingPositionRepo(),
        order_repo=_FailingOrderRepo(),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/account/facts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "unavailable"
    assert payload["truth_level"] == "unavailable"
    assert payload["connection_health"]["local_pg"]["available"] is False
    assert any("fail-closed" in item for item in payload["blockers"])


def test_brc_account_facts_returns_mixed_reconciled_when_exchange_testnet_matches_local(monkeypatch):
    _configure_auth(monkeypatch)
    local_position = _FakePosition("ETH/USDT:USDT")
    local_order = _FakeOrder("BTC/USDT:USDT")
    gateway = _FakeExchangeGateway(
        positions=[{"symbol": "ETH/USDT:USDT", "side": "long", "size": "0.01"}],
        open_orders=[{"id": "ord_unit", "symbol": "BTC/USDT:USDT", "status": "open", "type": "limit"}],
        recent_orders=[{"id": "recent-1", "symbol": "ETH/USDT:USDT", "status": "closed"}],
        recent_fills=[{"id": "fill-1", "symbol": "ETH/USDT:USDT"}],
    )
    _patch_runtime(
        monkeypatch,
        campaign=None,
        position_repo=_FakePositionRepo([local_position]),
        order_repo=_FakeOrderRepo([local_order]),
        exchange_gateway=gateway,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/account/facts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "mixed"
    assert payload["truth_level"] == "reconciled"
    assert payload["reconciliation_status"]["status"] == "clean"
    assert payload["reconciliation_status"]["checked_sources"] == ["local_pg", "exchange_testnet"]
    assert payload["recent_orders"][0]["id"] == "recent-1"
    assert payload["recent_fills"][0]["id"] == "fill-1"
    assert payload["unknown_or_unmanaged_orders"] == []
    assert payload["connection_health"]["exchange_testnet_read"]["available"] is True


def test_brc_account_facts_reconciliation_detects_unknown_exchange_order(monkeypatch):
    _configure_auth(monkeypatch)
    gateway = _FakeExchangeGateway(
        positions=[],
        open_orders=[{"id": "exchange-orphan", "symbol": "BTC/USDT:USDT", "status": "open"}],
    )
    _patch_runtime(
        monkeypatch,
        campaign=None,
        position_repo=_EmptyPositionRepo(),
        order_repo=_EmptyOrderRepo(),
        exchange_gateway=gateway,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/brc/account/facts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "mixed"
    assert payload["truth_level"] == "reconciled"
    assert payload["reconciliation_status"]["status"] == "mismatch"
    assert payload["mismatch_count"] == 1
    assert payload["unknown_unmanaged_counts"]["orders"] == 1
    assert payload["unknown_or_unmanaged_orders"][0]["record"]["id"] == "exchange-orphan"
    assert any(
        item["type"] == "exchange_order_missing_locally"
        for item in payload["reconciliation_status"]["mismatches"]
    )


def test_brc_account_facts_does_not_add_trading_endpoints(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_runtime(monkeypatch, campaign=None)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        assert client.post("/api/brc/account/orders/cancel").status_code == 404
        assert client.post("/api/brc/account/positions/flatten").status_code == 404
        assert client.post("/api/brc/account/runtime/stop").status_code == 404
        assert client.post("/api/brc/account/withdrawal").status_code == 404
        assert client.post("/api/brc/account/transfer").status_code == 404


def test_runtime_bound_evidence_smoke_payload_is_bounded():
    from scripts.brc_owner_console_smoke import run_runtime_bound_evidence_smoke

    payload = asyncio.run(run_runtime_bound_evidence_smoke())

    assert payload["mode"] == "runtime-bound-evidence"
    assert payload["safety_boundary"]["live_ready"] is False
    assert payload["safety_boundary"]["actual_flatten_executed"] is False
    assert payload["safety_boundary"]["order_cancel_executed"] is False
    assert payload["switch_playbook"]["confirm"]["status"] == "executed"
    assert payload["switch_playbook"]["preflight"]["idempotency_key_present"] is True
    assert payload["emergency_stop_runtime"]["does_not_flatten"] is True
    assert payload["emergency_stop_runtime"]["does_not_cancel_orders"] is True
    assert payload["emergency_flatten"]["preflight"]["dry_run_only"] is True
    assert payload["emergency_flatten"]["actual_flatten_executed"] is False
    assert payload["account_facts_summary"]["mismatch_count"] == 0


def test_tf001_carrier_decision_review_is_bounded_and_ready_for_full_chain():
    from scripts.brc_owner_console_smoke import run_tf001_carrier_decision_review

    payload = asyncio.run(run_tf001_carrier_decision_review())

    assert payload["mode"] == "tf001-carrier-decision-review"
    assert payload["decision"]["tf001_switch_playbook_ready"] is True
    assert payload["decision"]["tf001_monitor_carrier_ready"] is True
    assert payload["safety_boundary"]["live_ready"] is False
    assert payload["safety_boundary"]["strategy_execution_enabled"] is False
    assert payload["safety_boundary"]["order_cancel_executed"] is False
    assert payload["tf001_switch_playbook"]["preflight"]["known"] is True
    assert payload["tf001_switch_playbook"]["preflight"]["decision"] == "allow"
    assert payload["tf001_switch_playbook"]["blocked_reason"] is None
    assert payload["tf001_monitor_carrier"]["confirm"]["status"] == "noop"
    assert payload["campaign_playbook_after_review"] == "PB-000-OBSERVE-ONLY"


def test_tf001_carrier_full_chain_smoke_completes_bounded_trial_flow():
    from scripts.brc_owner_console_smoke import run_tf001_carrier_full_chain

    payload = asyncio.run(run_tf001_carrier_full_chain())

    assert payload["mode"] == "tf001-carrier-full-chain"
    assert payload["completed"] is True
    assert payload["stage_statuses"] == {
        "select_playbook": "executed",
        "confirm_selection": "executed",
        "monitor": "noop",
        "pause": "executed",
        "stop": "executed",
        "review": "executed",
    }
    assert payload["campaign_playbook_after_full_chain"] == "TF-001"
    assert payload["review_decision_count"] == 1
    assert payload["operation_list"]["all_chain_operations_listed"] is True
    assert payload["operations"]["switch_playbook"]["preflight_decision"] == "allow"
    assert payload["operations"]["switch_playbook"]["confirm_status"] == "executed"
    assert payload["operations"]["enter_strategy_or_monitor"]["confirm_status"] == "noop"
    assert payload["operations"]["emergency_stop_runtime"]["confirm_status"] == "executed"
    assert payload["operations"]["emergency_stop_runtime"]["does_not_flatten"] is True
    assert payload["operations"]["emergency_stop_runtime"]["does_not_cancel_orders"] is True
    assert payload["safety_boundary"]["live_ready"] is False
    assert payload["safety_boundary"]["strategy_execution_enabled"] is False
    assert payload["safety_boundary"]["actual_flatten_executed"] is False
    assert payload["safety_boundary"]["order_cancel_executed"] is False
    assert payload["safety_boundary"]["close_position_executed"] is False
    assert payload["safety_boundary"]["withdrawal_or_transfer_executed"] is False


def test_brc_audit_and_investigator_are_read_only(monkeypatch):
    _configure_auth(monkeypatch)
    service = _patch_runtime(monkeypatch, campaign=_FakeCampaign())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        audit = client.get("/api/brc/audit-trail")
        answer = client.post("/api/brc/investigator/ask", json={"question": "为什么 blocked？"})

    assert audit.status_code == 200
    assert audit.json()["live_ready"] is False
    assert answer.status_code == 200
    payload = answer.json()
    assert payload["live_ready"] is False
    assert payload["intent"] == "blocked_reason"
    assert payload["developer_details"]["free_sql_enabled"] is False
    assert service.mutation_calls == 0


def test_legacy_research_and_config_routes_are_not_mounted(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert client.get("/api/research/jobs").status_code == 404
        assert client.get("/api/v1/config").status_code == 404
