from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.interfaces.operator_auth import create_password_hash


BNB = "BNB/USDT:USDT"


def _configure_auth(monkeypatch):
    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("pw"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")


def _totp() -> str:
    from src.interfaces.operator_auth import _hotp

    return _hotp("JBSWY3DPEHPK3PXP", int(time.time() // 30))


def _login(client: TestClient):
    return client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "pw", "totp_code": _totp()},
    )


def _config_provider():
    return SimpleNamespace(
        resolved_config=SimpleNamespace(
            profile_name="strategy_trial_bnb_testnet_runtime",
            environment=SimpleNamespace(exchange_testnet=True, trading_env="testnet"),
            market=SimpleNamespace(symbols=[BNB]),
        )
    )


class _FakeGks:
    def is_active(self):
        return False


class _FakeStartupGuard:
    def is_armed(self):
        return True


class _FakeOrder:
    def __init__(
        self,
        order_id: str,
        role: str,
        exchange_order_id: str,
        *,
        parent_order_id: str | None = "entry-1",
        status: str = "OPEN",
    ) -> None:
        self.id = order_id
        self.signal_id = "signal-1"
        self.symbol = BNB
        self.direction = "LONG"
        self.order_type = "STOP_MARKET" if role == "SL" else "LIMIT"
        self.order_role = role
        self.status = status
        self.price = Decimal("638.57") if role == "TP1" else None
        self.trigger_price = Decimal("625.92") if role == "SL" else None
        self.requested_qty = Decimal("0.01")
        self.filled_qty = Decimal("0")
        self.average_exec_price = None
        self.reduce_only = role in {"TP1", "SL"}
        self.exchange_order_id = exchange_order_id
        self.parent_order_id = parent_order_id
        self.oco_group_id = None
        self.exit_reason = None
        self.filled_at = None
        self.created_at = 1780496662000
        self.updated_at = 1780496663000


class _FakeOrderRepo:
    def __init__(self, orders):
        self.orders = list(orders)

    async def get_orders(self, symbol=None, limit=100, offset=0):
        items = [item for item in self.orders if symbol is None or item.symbol == symbol]
        return {"items": items[offset : offset + limit], "total": len(items)}

    async def get_open_orders(self, symbol=None):
        return [
            item for item in self.orders
            if (symbol is None or item.symbol == symbol) and item.status == "OPEN"
        ]


class _FakePositionRepo:
    async def list_active(self, *, symbol=None, limit=200):
        return []


class _FakeIntentRepo:
    async def list(self):
        return []

    async def list_unfinished(self):
        return []


class _FakeRecoveryRepo:
    async def list_blocking(self):
        return [{"id": "recovery-1", "status": "pending", "symbol": BNB}]


class _FakeAuditRepository:
    async def query(self, query):
        return [
            SimpleNamespace(
                id="audit-1",
                order_id="sl-1",
                signal_id="signal-1",
                old_status=None,
                new_status="OPEN",
                event_type="ORDER_CONFIRMED",
                triggered_by="SYSTEM",
                metadata={"safe": True},
                created_at=1780496663000,
            )
        ]


class _FakeAuditLogger:
    def __init__(self):
        self._repository = _FakeAuditRepository()


class _FakeBrcService:
    async def list_review_decisions(self, *, campaign_id=None, limit=50):
        return [
            SimpleNamespace(
                review_id="review-1",
                campaign_id="campaign-1",
                decision="executed",
                metadata_json={"authorization_id": "auth-1"},
                created_at_ms=1780496664000,
            )
        ]


class _FakeSignalRepo:
    async def get_signals(self, symbol=None, limit=100):
        return {
            "data": [
                {
                    "id": "signal-1",
                    "symbol": BNB,
                    "direction": "LONG",
                    "strategy_name": "MI-001",
                    "created_at": 1780496600000,
                }
            ]
        }


class _FakeOwnerTrialFlowService:
    async def current(self, *, carrier_id: str):
        return SimpleNamespace(
            authorization_status="owner_live_authorized_pending_final_preflight",
            carrier={"carrier_id": carrier_id, "symbol": BNB, "side": "long"},
            live_authorization={
                "authorization_id": "auth-1",
                "carrier_id": carrier_id,
                "strategy_family_id": "MI-001",
                "symbol": BNB,
                "side": "long",
                "max_notional": "20",
                "quantity": "0.01",
                "leverage": "1",
                "status": "owner_live_authorized_pending_final_preflight",
                "live_ready": False,
                "order_permission_granted": False,
                "execution_permission_granted": False,
                "consumed": True,
            },
        )


class _FakeExchangeGateway:
    def __init__(self, *, positions=None, normal_orders=None, stop_orders=None):
        self._positions = [] if positions is None else list(positions)
        self._normal_orders = [] if normal_orders is None else list(normal_orders)
        self._stop_orders = (
            [
                {
                    "id": "4000001470395922",
                    "symbol": BNB,
                    "type": "market",
                    "side": "sell",
                    "status": "open",
                    "amount": "0.01",
                    "info": {
                        "stopPrice": "625.92",
                        "reduceOnly": True,
                        "positionSide": "LONG",
                    },
                }
            ]
            if stop_orders is None
            else list(stop_orders)
        )
        self.open_order_calls = []
        self.position_calls = []
        self.account_snapshot_calls = 0
        self.place_calls = 0
        self.cancel_calls = 0

    def get_account_snapshot(self):  # pragma: no cover - guarded by tests
        self.account_snapshot_calls += 1
        raise AssertionError("default trading-console read models must not read exchange account snapshots")

    async def fetch_positions(self, symbol=None):
        self.position_calls.append(symbol)
        return self._positions

    async def fetch_open_orders(self, symbol, params=None):
        self.open_order_calls.append((symbol, params))
        if params == {"stop": True}:
            return self._stop_orders
        return self._normal_orders

    async def place_order(self, *_args, **_kwargs):  # pragma: no cover
        self.place_calls += 1
        raise AssertionError("trading-console read models must not place orders")

    async def cancel_order(self, *_args, **_kwargs):  # pragma: no cover
        self.cancel_calls += 1
        raise AssertionError("trading-console read models must not cancel orders")


def _patch_deps(monkeypatch, *, exchange=None):
    from src.interfaces import api as api_module

    monkeypatch.setattr(api_module, "get_runtime_context", lambda: object())
    monkeypatch.setattr(api_module, "_runtime_config_provider", _config_provider())
    monkeypatch.setattr(api_module, "_account_getter", lambda: None)
    monkeypatch.setattr(api_module, "_exchange_gateway", exchange)
    monkeypatch.setattr(
        api_module,
        "_order_repo",
        _FakeOrderRepo(
            [
                _FakeOrder("entry-1", "ENTRY", "91085295446", parent_order_id=None, status="FILLED"),
                _FakeOrder("tp-1", "TP1", "91085295597"),
                _FakeOrder("sl-1", "SL", "4000001470395922"),
            ]
        ),
    )
    monkeypatch.setattr(api_module, "_position_repo", _FakePositionRepo())
    monkeypatch.setattr(api_module, "_execution_intent_repo", _FakeIntentRepo())
    monkeypatch.setattr(api_module, "_execution_recovery_repo", _FakeRecoveryRepo())
    monkeypatch.setattr(api_module, "_audit_logger", _FakeAuditLogger())
    monkeypatch.setattr(api_module, "_signal_repo", _FakeSignalRepo())
    monkeypatch.setattr(api_module, "_brc_campaign_service", _FakeBrcService())
    monkeypatch.setattr(
        api_module,
        "_owner_trial_flow_service",
        _FakeOwnerTrialFlowService(),
        raising=False,
    )
    monkeypatch.setattr(api_module, "_global_kill_switch_service", _FakeGks())
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", _FakeStartupGuard())


def test_trading_console_requires_operator_session(monkeypatch):
    _configure_auth(monkeypatch)
    from src.interfaces.api import app

    with TestClient(app) as client:
        response = client.get("/api/trading-console/dashboard-state")

    assert response.status_code == 401


def test_trading_console_router_is_get_only():
    from fastapi.routing import APIRoute

    from src.interfaces.api_trading_console import router

    routes = [
        route for route in router.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/trading-console")
    ]

    assert routes
    for route in routes:
        assert route.methods == {"GET"}


def test_trading_console_action_apis_are_absent(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        assert client.post("/api/trading-console/order-ledger").status_code == 405
        for endpoint in [
            "/api/trading-console/execute",
            "/api/trading-console/cancel-order",
            "/api/trading-console/replace-order",
            "/api/trading-console/flatten-position",
            "/api/trading-console/retry-protection",
            "/api/trading-console/recovery-tasks/retry",
            "/api/trading-console/authorizations/auth-1/void",
        ]:
            assert client.post(endpoint).status_code == 404, endpoint
            assert client.delete(endpoint).status_code == 404, endpoint


def test_trading_console_default_does_not_call_exchange(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/dashboard-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "dashboard_state"
    assert payload["freshness_status"] == "not_live_connected"
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["starts_runtime"] is False
    assert payload["no_action_guarantee"]["grants_auto_execution"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.account_snapshot_calls == 0
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_order_ledger_records_orphan_protection_warning_without_stopping(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/order-ledger?include_exchange=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "order_ledger"
    warnings = {item["code"] for item in payload["warnings"]}
    assert "pg_open_protection_without_pg_position" in warnings
    assert "exchange_orphan_reduce_only_order" in warnings
    assert payload["data"]["classification_counts"]["orphan_protection"] >= 1
    assert (BNB, None) in exchange.open_order_calls
    assert (BNB, {"stop": True}) in exchange.open_order_calls
    assert exchange.account_snapshot_calls == 1
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_exchange_flat_pg_open_protection_state_blocks_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(positions=[], normal_orders=[], stop_orders=[])
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        execution = client.get("/api/trading-console/execution-control-state?include_exchange=true")
        protection = client.get("/api/trading-console/protection-health?include_exchange=true")

    assert execution.status_code == 200
    execution_payload = execution.json()
    warning_codes = {item["code"] for item in execution_payload["warnings"]}
    blocker_codes = {item["code"] for item in execution_payload["blockers"]}
    assert "pg_open_protection_without_pg_position" in warning_codes
    assert "pg_protection_missing_on_exchange" in warning_codes
    assert "protection_state_degraded" in blocker_codes
    assert execution_payload["data"]["hard_gate"]["status"] == "blocked"
    assert execution_payload["data"]["execution_preview"]["status"] == "not_available"
    assert execution_payload["no_action_guarantee"]["places_order"] is False
    assert execution_payload["no_action_guarantee"]["cancels_order"] is False
    assert execution_payload["no_action_guarantee"]["flattens_position"] is False
    assert execution_payload["no_action_guarantee"]["retries_protection"] is False

    assert protection.status_code == 200
    protection_payload = protection.json()
    assert protection_payload["data"]["status"] == "orphaned"
    assert protection_payload["data"]["actions_exposed"] == []
    assert "retry_protection" in protection_payload["data"]["deferred_actions"]
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_execution_control_blocks_consumed_authorization_but_stays_read_only(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/execution-control-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "execution_control_state"
    blocker_codes = {item["code"] for item in payload["blockers"]}
    assert "authorization_not_actionable" in blocker_codes
    assert "protection_state_degraded" in blocker_codes
    assert payload["data"]["hard_gate"]["status"] == "blocked"
    assert payload["data"]["execution_preview"]["status"] == "not_available"
    assert payload["data"]["deferred_execute_endpoint"] is True
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["retries_protection"] is False


def test_review_and_order_models_mark_untracked_cost_fields_unavailable(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        ledger = client.get("/api/trading-console/order-ledger")
        review = client.get("/api/trading-console/review-state")

    assert ledger.status_code == 200
    ledger_payload = ledger.json()
    assert ledger_payload["data"]["unavailable_fields"] == {
        "client_order_id": "not_available",
        "fees": "not_available",
        "funding": "not_available",
        "slippage": "not_available",
    }
    assert review.status_code == 200
    review_payload = review.json()
    assert review_payload["data"]["unavailable_fields"]["fee"] == "not_available"
    assert review_payload["data"]["unavailable_fields"]["fee_asset"] == "not_available"
    assert review_payload["data"]["unavailable_fields"]["funding"] == "not_available"
    assert review_payload["data"]["unavailable_fields"]["slippage"] == "not_available"


def test_audit_chain_masks_raw_payloads_and_exposes_relationship_ids(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/audit-chain?order_id=sl-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["raw_payload_policy"] == "masked_or_omitted"
    assert payload["data"]["orders"]
    assert payload["data"]["orders"][0]["order_id"] in {"entry-1", "sl-1"}
    rendered = response.text.lower()
    assert "api_key" not in rendered
    assert "secret" not in rendered
    assert "totp" not in rendered


def test_all_trading_console_read_model_endpoints_return_envelopes(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces.api import app

    endpoints = [
        "/api/trading-console/dashboard-state",
        "/api/trading-console/account-risk",
        "/api/trading-console/order-ledger",
        "/api/trading-console/protection-health",
        "/api/trading-console/recovery-exception-state",
        "/api/trading-console/authorization-state",
        "/api/trading-console/execution-control-state",
        "/api/trading-console/review-state",
        "/api/trading-console/audit-chain?authorization_id=auth-1",
        "/api/trading-console/carrier-availability",
        "/api/trading-console/signal-marker-feed",
        "/api/trading-console/api-classification",
    ]

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, endpoint
            payload = response.json()
            assert payload["source"] == "trading_console_read_model_v1"
            assert payload["live_ready"] is False
            assert payload["no_action_guarantee"]["places_order"] is False
            assert payload["no_action_guarantee"]["cancels_order"] is False
            assert payload["no_action_guarantee"]["replaces_order"] is False
            assert payload["no_action_guarantee"]["flattens_position"] is False
            assert payload["no_action_guarantee"]["retries_protection"] is False
            assert payload["no_action_guarantee"]["starts_runtime"] is False
            assert payload["no_action_guarantee"]["grants_auto_execution"] is False
            assert payload["no_action_guarantee"]["mutates_pg"] is False
