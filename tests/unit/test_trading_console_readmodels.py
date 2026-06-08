from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.application.production_strategy_family_admission import (
    API_BACKED_AUTHORIZATION_OPERATION_CHAIN,
    REQUIRED_OWNER_SCOPE_FIELDS,
)
from src.interfaces.operator_auth import create_password_hash


BNB = "BNB/USDT:USDT"


def test_trading_console_live_read_only_exchange_env_allows_order_allowed_ceiling(monkeypatch):
    from src.interfaces.api_trading_console import _live_read_only_exchange_env_safe

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_API_" + "KEY", "masked-key")
    monkeypatch.setenv("EXCHANGE_API_" + "SEC" + "RET", "masked-value")

    assert _live_read_only_exchange_env_safe() is True


def test_trading_console_live_read_only_exchange_env_blocks_runtime_control(monkeypatch):
    from src.interfaces.api_trading_console import _live_read_only_exchange_env_safe

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("BRC_EXECUTION_PERMISSION_MAX", "order_allowed")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_API_" + "KEY", "masked-key")
    monkeypatch.setenv("EXCHANGE_API_" + "SEC" + "RET", "masked-value")

    assert _live_read_only_exchange_env_safe() is False


def _configure_auth(monkeypatch):
    # Importing the API composition root loads local dotenv files with override=True.
    # Keep test credentials authoritative even when an individual test imports app later.
    import src.interfaces.api  # noqa: F401

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


class _FakeAccountSnapshot:
    total_balance = Decimal("1000")
    available_balance = Decimal("800")
    unrealized_pnl = Decimal("0")
    timestamp = 1780496665000
    positions = []


class _FakeOrder:
    def __init__(
        self,
        order_id: str,
        role: str,
        exchange_order_id: str,
        *,
        parent_order_id: str | None = "entry-1",
        status: str = "OPEN",
        symbol: str = BNB,
    ) -> None:
        self.id = order_id
        self.signal_id = "signal-1"
        self.symbol = symbol
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


class _FakeActivePositionRepo:
    def __init__(self, *, symbol: str = BNB) -> None:
        self.symbol = symbol

    async def list_active(self, *, symbol=None, limit=200):
        return [
            SimpleNamespace(
                id="pos-signal-1",
                signal_id="signal-1",
                symbol=self.symbol,
                direction="LONG",
                entry_price=Decimal("630"),
                current_qty=Decimal("0.01"),
                watermark_price=Decimal("630"),
                realized_pnl=Decimal("0"),
                total_fees_paid=Decimal("0"),
                total_funding_paid=Decimal("0"),
                projected_exit_fills={},
                projected_exit_fees={},
                opened_at=1780496661000,
                closed_at=None,
                is_closed=False,
            )
        ]


class _FakeIntentRepo:
    def __init__(self, intents=None):
        self.intents = [] if intents is None else list(intents)

    async def list(self):
        return self.intents

    async def list_unfinished(self):
        return [
            item for item in self.intents
            if str(getattr(item, "status", "")).lower() not in {"completed", "failed", "canceled"}
        ]


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


def _patch_deps(
    monkeypatch,
    *,
    exchange=None,
    position_repo=None,
    order_repo=None,
    account_snapshot=None,
    intent_repo=None,
):
    from src.interfaces import api as api_module

    monkeypatch.setattr(api_module, "get_runtime_context", lambda: object())
    monkeypatch.setattr(api_module, "_runtime_config_provider", _config_provider())
    monkeypatch.setattr(api_module, "_account_getter", lambda: account_snapshot)
    monkeypatch.setattr(api_module, "_exchange_gateway", exchange)
    monkeypatch.setattr(
        api_module,
        "_order_repo",
        order_repo
        or _FakeOrderRepo(
            [
                _FakeOrder("entry-1", "ENTRY", "91085295446", parent_order_id=None, status="FILLED"),
                _FakeOrder("tp-1", "TP1", "91085295597"),
                _FakeOrder("sl-1", "SL", "4000001470395922"),
            ]
        ),
    )
    monkeypatch.setattr(api_module, "_position_repo", position_repo or _FakePositionRepo())
    monkeypatch.setattr(api_module, "_execution_intent_repo", intent_repo or _FakeIntentRepo())
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


def test_protection_health_counts_current_scope_active_protection_only(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(
        positions=[
            {
                "symbol": BNB,
                "side": "long",
                "contracts": "0.01",
                "entryPrice": "630",
                "leverage": "1",
            }
        ],
        normal_orders=[
            {
                "id": "91085295597",
                "symbol": BNB,
                "type": "limit",
                "side": "sell",
                "status": "open",
                "amount": "0.01",
                "price": "638.57",
                "info": {"reduceOnly": True, "positionSide": "LONG"},
            }
        ],
    )
    order_repo = _FakeOrderRepo(
        [
            _FakeOrder("entry-1", "ENTRY", "91085295446", parent_order_id=None, status="FILLED"),
            _FakeOrder("tp-1", "TP1", "91085295597"),
            _FakeOrder("sl-1", "SL", "4000001470395922"),
            _FakeOrder("entry-old", "ENTRY", "old-entry", parent_order_id=None, status="FILLED"),
            _FakeOrder("tp-old", "TP1", "old-tp", parent_order_id="entry-old", status="FILLED"),
            _FakeOrder("sl-old", "SL", "old-sl", parent_order_id="entry-old", status="CANCELED"),
        ]
    )
    order_repo.orders[-3].signal_id = "signal-old"
    order_repo.orders[-2].signal_id = "signal-old"
    order_repo.orders[-1].signal_id = "signal-old"
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        position_repo=_FakeActivePositionRepo(),
        order_repo=order_repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/protection-health?include_exchange=true")

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["status"] == "protected"
    assert data["tp_count"] == 1
    assert data["sl_count"] == 1
    assert len(data["current_scope_active_protection"]) == 2
    assert {item["order_id"] for item in data["current_scope_active_protection"]} == {"tp-1", "sl-1"}
    assert {item["order_id"] for item in data["historical_protection_orders"]} >= {"tp-old", "sl-old"}
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


def test_strategy_family_admission_state_maps_three_production_families_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/strategy-family-admission-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "strategy_family_admission_state"
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert payload["no_action_guarantee"]["starts_runtime"] is False
    assert payload["data"]["trading_console_authorization_readiness"]["frontend_action_enabled"] is False
    assert (
        payload["data"]["trading_console_authorization_readiness"]["action_enablement_source"]
        == "backend_actionable_only"
    )
    assert payload["data"]["official_action_api_inventory"]["trading_console_action_api_exposed"] is False
    assert payload["data"]["official_action_api_inventory"]["owner_trial_flow_supported_carrier_ids"] == [
        "MI-001-BNB-LONG",
        "TF-001-live-readonly-v0",
        "MR-001-live-readonly-v0",
        "MR-001-BTC-live-readonly-v0",
    ]
    standard = payload["data"]["candidate_pipeline_standard"]
    assert standard["version"] == "brc_strategy_family_action_candidate_standard_v0_1"
    levels = {item["level"]: item for item in standard["admission_levels"]}
    assert set(levels) == {"L0", "L1", "L2", "L3", "L4"}
    assert levels["L2"]["action_candidate_allowed"] is True
    assert levels["L2"]["live_action_allowed"] is False
    assert levels["L3"]["live_action_allowed"] is True
    assert standard["warning_hard_blocker_policy"]["weak_strategy_evidence_policy"] == (
        "warning_not_hard_blocker"
    )
    assert "weak strategy evidence" in standard["warning_hard_blocker_policy"]["warning_items"]
    assert "missing Owner execute authorization" in (
        standard["warning_hard_blocker_policy"]["hard_blockers_for_live_action"]
    )
    candidate_output = {item["family"]: item for item in payload["data"]["candidate_output"]}
    assert candidate_output["Trend"]["admission_level"] == "L3"
    assert candidate_output["Trend"]["candidate_state"] == "bounded_live_candidate"
    assert candidate_output["Trend"]["action_registry_supported"] is True
    assert candidate_output["Trend"]["frontend_action_enabled"] is False
    assert candidate_output["Trend"]["may_execute_live"] is False
    assert candidate_output["Volatility expansion"]["admission_level"] == "L2"
    assert candidate_output["Volatility expansion"]["candidate_state"] == "proposal"
    assert candidate_output["Mean reversion"]["admission_level"] == "L2"
    assert candidate_output["Mean reversion"]["candidate_state"] == "proposal"
    assert payload["data"]["api_backed_authorization_flow"]["status"] == (
        "operation_layer_metadata_flow_available"
    )
    assert payload["data"]["api_backed_authorization_flow"]["trading_console_direct_action_api"] is False
    assert payload["data"]["api_backed_authorization_flow"]["creates_execution_intent"] is False
    assert payload["data"]["api_backed_authorization_flow"]["places_order"] is False
    assert payload["data"]["api_backed_authorization_flow"]["operation_steps"][0]["operation_type"] == (
        "create_gated_trial_from_admission"
    )
    transition_by_name = {
        item["transition"]: item for item in payload["data"]["official_transition_readiness_matrix"]
    }
    assert transition_by_name["create_admission_request"]["status"] == "proposal_only"
    assert transition_by_name["create_admission_request"]["endpoint"] == (
        "POST /api/brc/admissions/requests"
    )
    assert "evidence_packet_id" in transition_by_name["create_admission_request"]["required_refs"]
    assert transition_by_name["create_owner_risk_acceptance"]["status"] == "proposal_only"
    assert transition_by_name["create_gated_trial_from_admission"]["status"] == (
        "metadata_available"
    )
    assert transition_by_name["create_gated_trial_from_admission"]["endpoint"] == (
        "POST /api/brc/operations/preflight"
    )
    assert transition_by_name["final_gate_dry_run"]["status"] == "blocked"
    assert transition_by_name["execute_authorization"]["status"] == "blocked"
    assert transition_by_name["execute_authorization"]["endpoint"] == (
        "POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
    )
    for item in transition_by_name.values():
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    assert payload["data"]["sprint_acceptance_verdict"]["status"] == (
        "in_progress_pass_with_constraint"
    )
    assert payload["data"]["sprint_acceptance_verdict"]["completed_family_count"] == 0
    assert payload["data"]["sprint_acceptance_verdict"]["actionable_family_count"] == 1
    assert payload["data"]["sprint_acceptance_verdict"]["frontend_action_enabled"] is False
    baseline = payload["data"]["production_baseline_context"]
    assert baseline["status"] == "historical_bnb_context_not_action_permission"
    assert baseline["prior_scoped_carrier_id"] == "MI-001-BNB-LONG"
    assert baseline["prior_symbol"] == "BNB/USDT:USDT"
    assert baseline["prior_side"] == "LONG"
    assert baseline["prior_quantity"] == "0.01"
    assert baseline["prior_live_evidence_status"] == (
        "owner_authorized_bnb_execute_and_closeout_evidence_present"
    )
    assert baseline["post_close_state_status"] == (
        "reported_flat_requires_fresh_pg_exchange_validation_before_new_action"
    )
    assert "cannot authorize new Trend" in baseline["reuse_policy"]
    assert "docs/ops/trading-console-backend-dependency-sync-v0.2.md#TC-BE-DEP-002-06" in (
        baseline["evidence_refs"]
    )
    assert baseline["reusable_for_strategy_family_authorization"] is False
    assert baseline["grants_execution_permission"] is False
    assert baseline["grants_order_permission"] is False
    assert baseline["frontend_action_enabled"] is False
    assert baseline["requires_fresh_pre_action_pg_evidence"] is True
    assert baseline["requires_fresh_pre_action_exchange_evidence"] is True
    assert baseline["creates_authorization"] is False
    assert baseline["creates_execution_intent"] is False
    assert baseline["starts_runtime"] is False
    assert baseline["starts_strategy_execution"] is False
    assert baseline["places_order"] is False
    assert baseline["mutates_pg"] is False
    assert baseline["exchange_write_action"] is False
    family_report_by_family = {
        item["family"]: item for item in payload["data"]["family_final_report_matrix"]
    }
    assert set(family_report_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in family_report_by_family.values():
        assert item["status"] == "PASS_WITH_CONSTRAINT"
        assert item["completed_work_status"] == "PASS_WITH_CONSTRAINT"
        assert item["strategy_group_carrier_mapping_status"] == "PASS_WITH_CONSTRAINT"
        assert item["admission_risk_control_status"] == "PASS_WITH_CONSTRAINT"
        assert item["trading_console_authorization_status"] == "PASS_WITH_CONSTRAINT"
        assert item["live_action_status"] == "BLOCKED"
        assert item["pg_exchange_evidence_status"] == "BLOCKED"
        assert item["blocker_count"] > 0
        assert "ActionCandidate" in item["bridge_methods"]
        assert "FinalGateDryRun" in item["bridge_methods"]
        assert f"family_completion_matrix:{item['family']}" in item["evidence_refs"]
        assert f"owner_review_handoff_matrix:{item['family']}" in item["evidence_refs"]
        assert f"production_action_decision_matrix:{item['family']}" in item["evidence_refs"]
        assert f"evidence_collection_summary_matrix:{item['family']}" in item["evidence_refs"]
        assert item["next_retry_conditions"]
        assert item["safety_flags"] == {
            "live_action_taken": False,
            "runtime_started": False,
            "backend_actionable": False,
            "frontend_action_enabled": False,
            "places_order": False,
            "mutates_pg": False,
            "exchange_write_action": False,
        }
        assert item["live_action_taken"] is False
        assert item["runtime_started"] is False
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    final_report = payload["data"]["final_report_package"]
    assert final_report["status"] == "PASS_WITH_CONSTRAINT"
    section_by_name = {item["section"]: item for item in final_report["sections"]}
    assert set(section_by_name) == {
        "completed_work_by_family",
        "strategy_group_carrier_mappings",
        "admission_risk_control_changes",
        "trading_console_authorization_readiness",
        "live_actions_taken",
        "pg_exchange_evidence",
        "blocker_records_and_bridge_artifacts",
        "tests_checks",
        "next_retry_conditions",
        "safety_proof",
    }
    assert section_by_name["completed_work_by_family"]["status"] == "PASS_WITH_CONSTRAINT"
    assert "family_completion_matrix" in section_by_name[
        "completed_work_by_family"
    ]["evidence_refs"]
    assert "family_final_report_matrix" in section_by_name[
        "completed_work_by_family"
    ]["evidence_refs"]
    assert "official_api_request_draft_matrix" in section_by_name[
        "trading_console_authorization_readiness"
    ]["evidence_refs"]
    assert "owner_review_handoff_matrix" in section_by_name[
        "trading_console_authorization_readiness"
    ]["evidence_refs"]
    assert "final_gate_readiness_matrix" in section_by_name[
        "trading_console_authorization_readiness"
    ]["evidence_refs"]
    assert "production_capital_boundary_matrix" in section_by_name[
        "admission_risk_control_changes"
    ]["evidence_refs"]
    assert "objective_acceptance_audit_matrix" in section_by_name[
        "blocker_records_and_bridge_artifacts"
    ]["evidence_refs"]
    assert "objective_acceptance_audit_matrix" in section_by_name[
        "tests_checks"
    ]["evidence_refs"]
    assert section_by_name["live_actions_taken"]["status"] == "BLOCKED"
    assert "live_actions_taken=[]" in section_by_name["live_actions_taken"]["evidence_refs"]
    assert "production_baseline_context" in section_by_name[
        "live_actions_taken"
    ]["evidence_refs"]
    assert "production_action_decision_matrix" in section_by_name[
        "live_actions_taken"
    ]["evidence_refs"]
    assert section_by_name["pg_exchange_evidence"]["status"] == "BLOCKED"
    assert "family_evidence_collection_matrix" in section_by_name[
        "pg_exchange_evidence"
    ]["evidence_refs"]
    assert "evidence_collection_summary_matrix" in section_by_name[
        "pg_exchange_evidence"
    ]["evidence_refs"]
    assert section_by_name["safety_proof"]["status"] == "PASS"
    assert "production_baseline_context" in section_by_name[
        "safety_proof"
    ]["evidence_refs"]
    assert final_report["live_actions_taken"] is False
    assert final_report["runtime_started"] is False
    assert final_report["pg_mutation"] is False
    assert final_report["exchange_write_action"] is False
    assert final_report["credentials_changed"] is False
    assert final_report["deploy_performed"] is False
    assert final_report["push_performed"] is False
    assert any(
        "test_production_strategy_family_admission.py" in command
        for command in final_report["required_validation_commands"]
    )
    audit_by_requirement = {
        item["requirement_id"]: item
        for item in payload["data"]["objective_acceptance_audit_matrix"]
    }
    assert set(audit_by_requirement) == {
        "strategy_family_scope",
        "production_baseline_context",
        "full_chain_per_family",
        "trading_console_authorization_path",
        "strategy_group_carrier_alignment",
        "admission_and_risk_control",
        "production_capital_boundary",
        "live_action_decision",
        "pg_exchange_evidence",
        "blocker_records_and_bridges",
        "final_report_package",
        "safety_proof",
    }
    assert audit_by_requirement["strategy_family_scope"]["status"] == "PASS"
    assert audit_by_requirement["production_baseline_context"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["trading_console_authorization_path"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["live_action_decision"]["status"] == "BLOCKED"
    assert audit_by_requirement["pg_exchange_evidence"]["status"] == "BLOCKED"
    assert audit_by_requirement["safety_proof"]["status"] == "PASS"
    assert "owner_review_handoff_matrix" in audit_by_requirement[
        "trading_console_authorization_path"
    ]["evidence_refs"]
    assert "production_baseline_context" in audit_by_requirement[
        "production_baseline_context"
    ]["evidence_refs"]
    assert "production_action_decision_matrix" in audit_by_requirement[
        "live_action_decision"
    ]["evidence_refs"]
    assert "live_actions_taken=[]" in audit_by_requirement[
        "live_action_decision"
    ]["evidence_refs"]
    assert audit_by_requirement["live_action_decision"]["blocker_ids"]
    for item in audit_by_requirement.values():
        assert item["next_retry_condition"]
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    completion_by_family = {
        item["family"]: item for item in payload["data"]["family_completion_matrix"]
    }
    assert set(completion_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert completion_by_family["Trend"]["completion_status"] == "actionable"
    assert completion_by_family["Trend"]["strategy_group"] == (
        "Major trend continuation / trend following"
    )
    assert completion_by_family["Trend"]["carrier_id"] == "TF-001-live-readonly-v0"
    assert "StrategyFamily" in completion_by_family["Trend"]["completed_stages"]
    assert "BoundedLiveAuthorization" in completion_by_family["Trend"]["blocked_stages"]
    assert "ActionCandidate" in completion_by_family["Trend"]["bridge_methods"]
    assert "FinalGateDryRun" in completion_by_family["Trend"]["bridge_methods"]
    assert completion_by_family["Volatility expansion"]["completion_status"] == "blocked"
    assert completion_by_family["Mean reversion"]["completion_status"] == "blocked"
    for item in completion_by_family.values():
        assert item["blocker_ids"]
        assert item["next_retry_conditions"]
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_execution_intent"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    risk_control_by_family = {
        item["family"]: item for item in payload["data"]["admission_risk_control_matrix"]
    }
    assert set(risk_control_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert risk_control_by_family["Trend"]["admission_level"] == (
        "Owner-confirmed action-capable carrier"
    )
    assert risk_control_by_family["Trend"]["scope_review_verdict"] == "not_provided"
    assert risk_control_by_family["Trend"]["risk_disclosure_status"] == "draft_for_owner_review"
    assert risk_control_by_family["Trend"]["budget_envelope_status"] == (
        "scope_incomplete_no_numbers_fabricated"
    )
    assert risk_control_by_family["Trend"]["authorization_draft_status"] == "scope_required"
    assert risk_control_by_family["Trend"]["bounded_live_authorization_status"] == (
        "blocked_scope_incomplete"
    )
    assert risk_control_by_family["Trend"]["action_api_status"] == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    assert risk_control_by_family["Trend"]["final_gate_status"] == "blocked"
    assert risk_control_by_family["Trend"]["final_gate_reason"] == "production_scope_incomplete"
    assert risk_control_by_family["Trend"]["protection_plan_status"] == (
        "draft_required_mandatory_tp_sl"
    )
    assert risk_control_by_family["Trend"]["review_contract_status"] == (
        "draft_no_action_evidence"
    )
    assert risk_control_by_family["Trend"]["audit_chain_status"] == (
        "gap_open_no_live_action_evidence"
    )
    for item in risk_control_by_family.values():
        assert item["blocker_ids"]
        assert item["next_retry_conditions"]
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    capital_boundary_by_family = {
        item["family"]: item for item in payload["data"]["production_capital_boundary_matrix"]
    }
    assert set(capital_boundary_by_family) == {
        "Trend",
        "Volatility expansion",
        "Mean reversion",
    }
    for item in capital_boundary_by_family.values():
        assert item["status"] == "scope_required"
        assert item["scope_review_verdict"] == "not_provided"
        assert item["required_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
        assert item["provided_scope_fields"] == []
        assert item["missing_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
        assert item["supported_symbols"]
        assert item["requested_symbol"] is None
        assert item["requested_quantity"] is None
        assert item["requested_max_notional"] is None
        assert item["numbers_source"] == "owner_scope_only_no_fabrication"
        assert item["scope_expansion_allowed"] is False
        assert item["symbol_expansion_allowed"] is False
        assert item["side_expansion_allowed"] is False
        assert item["quantity_expansion_allowed"] is False
        assert item["notional_expansion_allowed"] is False
        assert item["leverage_expansion_allowed"] is False
        assert item["max_attempts_expansion_allowed"] is False
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    full_chain_by_family = {}
    for item in payload["data"]["full_chain_evidence_matrix"]:
        full_chain_by_family.setdefault(item["family"], []).append(item)
        assert item["required_evidence_refs"]
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    assert len(payload["data"]["full_chain_evidence_matrix"]) == 30
    assert set(full_chain_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_chain = {item["stage"]: item for item in full_chain_by_family["Trend"]}
    assert [item["stage"] for item in full_chain_by_family["Trend"]] == [
        "StrategyFamily",
        "StrategyGroup",
        "Carrier",
        "RiskDisclosure",
        "AuthorizationDraft",
        "BoundedLiveAuthorization",
        "ExecutionIntent",
        "Entry",
        "TP/SL",
        "Review",
    ]
    assert trend_chain["AuthorizationDraft"]["status"] == "proposal_only_scope_required"
    assert trend_chain["AuthorizationDraft"]["bridge_method"] == "AuthorizationDraftProposal"
    assert "complete_owner_scope" in trend_chain["AuthorizationDraft"]["required_evidence_refs"]
    assert trend_chain["BoundedLiveAuthorization"]["status"] == (
        "blocked_scope_incomplete_or_unmatched"
    )
    assert "backend_final_gate_actionable_true" in (
        trend_chain["BoundedLiveAuthorization"]["required_evidence_refs"]
    )
    assert trend_chain["ExecutionIntent"]["status"] == "not_created"
    assert trend_chain["Entry"]["status"] == "not_executed"
    assert trend_chain["TP/SL"]["status"] == "draft_required_mandatory_tp_sl"
    assert trend_chain["Review"]["status"] == "review_contract_draft"
    pra_by_family = {
        item["family"]: item for item in payload["data"]["protection_review_audit_matrix"]
    }
    assert set(pra_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_pra = pra_by_family["Trend"]
    assert trend_pra["protection_status"] == "draft_required_mandatory_tp_sl"
    assert trend_pra["required_protection_components"] == ["TP", "SL"]
    assert "complete_matched_owner_scope" in trend_pra["missing_protection_fields"]
    assert "take_profit_price" in trend_pra["missing_protection_fields"]
    assert "stop_loss_price" in trend_pra["missing_protection_fields"]
    assert trend_pra["unavailable_protection_fields"]["take_profit_price"] == (
        "not_fabricated_by_read_model"
    )
    assert trend_pra["review_status"] == "draft_no_action_evidence"
    assert "entry_order" in trend_pra["review_required_evidence"]
    assert "entry_order" in trend_pra["review_missing_evidence"]
    assert "audit_log_events" in trend_pra["review_missing_evidence"]
    assert trend_pra["audit_status"] == "gap_open_no_live_action_evidence"
    assert "authorization_draft_proposal" in trend_pra["audit_present_evidence"]
    assert "post_action_review" in trend_pra["audit_missing_evidence"]
    assert trend_pra["audit_sources_required"] == [
        "audit_logs",
        "campaign_events",
        "operation_results",
    ]
    for item in pra_by_family.values():
        assert item["blocker_ids"]
        assert item["next_retry_conditions"]
        assert item["action_allowed"] is False
        assert item["creates_order"] is False
        assert item["records_review"] is False
        assert item["creates_execution_intent"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    retry_by_family = {}
    for item in payload["data"]["blocker_retry_matrix"]:
        retry_by_family.setdefault(item["family"], []).append(item)
        assert item["blocker_id"]
        assert item["stage"]
        assert item["blocked_path"]
        assert item["evidence"]
        assert item["next_retry_condition"]
        assert item["retry_requires"]
        assert item["retry_ready"] is False
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    assert len(payload["data"]["blocker_retry_matrix"]) == 19
    assert set(retry_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_retry_by_id = {
        item["blocker_id"]: item for item in retry_by_family["Trend"]
    }
    assert "BRC-PROD-ADMIT-20260604-TREND-001" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-SCOPE" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-ACTION-API" not in trend_retry_by_id
    assert trend_retry_by_id[
        "BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION"
    ]["bridge_method"] == "ProtectionPlanDraft"
    assert "take_profit_price defined by official service" in (
        trend_retry_by_id["BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION"][
            "retry_requires"
        ]
    )
    packet_by_family = {
        item["family"]: item for item in payload["data"]["owner_authorization_packet_matrix"]
    }
    assert set(packet_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_packet = packet_by_family["Trend"]
    assert trend_packet["status"] == "scope_required"
    assert trend_packet["owner_can_review"] is True
    assert trend_packet["owner_scope_verdict"] == "not_provided"
    assert trend_packet["risk_disclosure_status"] == "draft_for_owner_review"
    assert trend_packet["budget_envelope_status"] == "scope_incomplete_no_numbers_fabricated"
    assert trend_packet["authorization_draft_status"] == "scope_required"
    assert trend_packet["confirmation_phrase_required"] == "I ACCEPT BOUNDED PRODUCTION RISK"
    assert trend_packet["api_backed_flow_available"] is True
    assert trend_packet["api_request_draft_names"] == [
        "create_admission_evidence_packet",
        "create_owner_regime_input",
        "create_admission_request",
        "create_owner_risk_acceptance",
        "operation_preflight_create_gated_trial_from_admission",
    ]
    assert "POST /api/brc/admissions/requests" in trend_packet["draft_endpoints"]
    assert "POST /api/brc/operations/preflight" in trend_packet["draft_endpoints"]
    assert "evidence_packet_id" in trend_packet["unresolved_refs"]
    assert "owner_current_regime" in trend_packet["unresolved_refs"]
    assert "complete matched Owner scope" in trend_packet["required_before_submit"]
    for item in packet_by_family.values():
        assert item["not_authorization"] is True
        assert item["not_execution_permission"] is True
        assert item["not_order_permission"] is True
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    handoff_by_family = {
        item["family"]: item for item in payload["data"]["owner_review_handoff_matrix"]
    }
    assert set(handoff_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    trend_handoff = handoff_by_family["Trend"]
    assert trend_handoff["status"] == "review_ready_scope_required"
    assert trend_handoff["owner_can_review_risk_scope"] is True
    assert trend_handoff["owner_scope_verdict"] == "not_provided"
    assert trend_handoff["risk_disclosure_status"] == "draft_for_owner_review"
    assert "false continuation" in trend_handoff["risk_failure_modes"]
    assert trend_handoff["budget_envelope_status"] == (
        "scope_incomplete_no_numbers_fabricated"
    )
    assert trend_handoff["authorization_draft_status"] == "scope_required"
    assert trend_handoff["confirmation_phrase_required"] == (
        "I ACCEPT BOUNDED PRODUCTION RISK"
    )
    assert trend_handoff["read_only_review_endpoint"] == (
        "GET /api/trading-console/strategy-family-admission-state"
    )
    assert trend_handoff["api_backed_authorization_status"] == (
        "operation_layer_metadata_flow_available"
    )
    assert trend_handoff["operation_preflight_endpoint"] == (
        "POST /api/brc/operations/preflight"
    )
    assert trend_handoff["operation_confirm_endpoint"] == (
        "POST /api/brc/operations/{operation_id}/confirm"
    )
    assert trend_handoff["operation_step_count"] == len(API_BACKED_AUTHORIZATION_OPERATION_CHAIN)
    assert trend_handoff["first_operation_type"] == "create_gated_trial_from_admission"
    assert trend_handoff["last_operation_type"] == (
        "record_trial_trade_intent_from_signal_evaluation"
    )
    assert "POST /api/brc/admissions/requests" in trend_handoff["draft_endpoints"]
    assert "evidence_packet_id" in trend_handoff["unresolved_refs"]
    assert "complete matched Owner scope" in trend_handoff["required_before_submit"]
    assert trend_handoff["blocker_ids"]
    assert trend_handoff["next_retry_conditions"]
    for item in handoff_by_family.values():
        assert item["frontend_action_enabled"] is False
        assert item["action_enablement_source"] == "backend_actionable_only"
        assert item["not_authorization"] is True
        assert item["not_execution_permission"] is True
        assert item["not_order_permission"] is True
        assert item["read_model_submits_authorization"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    request_rows_by_family = {}
    for item in payload["data"]["official_api_request_draft_matrix"]:
        request_rows_by_family.setdefault(item["family"], []).append(item)
        assert item["status"] == "proposal_only_not_submitted"
        assert item["method"] == "POST"
        assert item["endpoint"].startswith("POST /api/brc/")
        assert item["owner_scope_verdict"] == "not_provided"
        assert item["required_before_submit"]
        assert item["payload_template_keys"]
        assert item["not_submitted"] is True
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["mutates_exchange"] is False
    assert len(payload["data"]["official_api_request_draft_matrix"]) == 15
    assert set(request_rows_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for items in request_rows_by_family.values():
        assert [item["draft_name"] for item in items] == [
            "create_admission_evidence_packet",
            "create_owner_regime_input",
            "create_admission_request",
            "create_owner_risk_acceptance",
            "operation_preflight_create_gated_trial_from_admission",
        ]
    trend_request_rows = {
        item["draft_name"]: item for item in request_rows_by_family["Trend"]
    }
    assert trend_request_rows["create_admission_request"]["endpoint"] == (
        "POST /api/brc/admissions/requests"
    )
    assert "evidence_packet_id" in trend_request_rows[
        "create_admission_request"
    ]["unresolved_refs"]
    assert "account_facts_snapshot_json" in trend_request_rows[
        "create_admission_request"
    ]["payload_template_keys"]
    assert trend_request_rows[
        "operation_preflight_create_gated_trial_from_admission"
    ]["endpoint"] == "POST /api/brc/operations/preflight"
    final_gate_by_family = {
        item["family"]: item for item in payload["data"]["final_gate_readiness_matrix"]
    }
    assert set(final_gate_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in final_gate_by_family.values():
        checks = {check["code"]: check for check in item["checks"]}
        assert item["status"] == "blocked"
        assert item["readiness_level"] == "scope_required"
        assert item["final_gate_endpoint"] == (
            "POST /api/brc/owner-trial-flow/live-execution-bridge/dry-run"
        )
        assert item["execute_endpoint"] == (
            "POST /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute"
        )
        assert item["final_gate_reason"] == "production_scope_incomplete"
        assert item["owner_scope_verdict"] == "not_provided"
        assert checks["owner_scope_complete"]["status"] == "block"
        assert checks["official_action_api_candidate_supported"]["status"] == (
            "pass" if item["family"] in {"Trend", "Mean reversion"} else "block"
        )
        assert checks["backend_final_gate_actionable"]["status"] == "block"
        assert "BoundedLiveAuthorization" in item["blocking_stages"]
        assert "ExecutionIntent" in item["blocking_stages"]
        assert "Entry" in item["blocking_stages"]
        assert item["blocker_ids"]
        assert item["next_retry_conditions"]
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    decision_by_family = {
        item["family"]: item for item in payload["data"]["production_action_decision_matrix"]
    }
    assert set(decision_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in decision_by_family.values():
        assert item["decision"] == "do_not_execute"
        assert item["selection_status"] == "not_selected_for_live_action"
        assert item["reason"] == "owner_scope_incomplete_or_unmatched"
        assert item["owner_scope_verdict"] == "not_provided"
        assert item["action_api_status"] == (
            "supported_by_current_official_action_api_but_not_actionable"
            if item["family"] in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        assert item["final_gate_reason"] == "production_scope_incomplete"
        assert "final_gate_actionable_true" in item["missing_evidence"]
        assert "execution_intent" in item["missing_evidence"]
        assert item["blocker_ids"]
        assert item["next_retry_conditions"]
        assert item["live_action_taken"] is False
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
    eligibility_by_family = {
        item["family"]: item for item in payload["data"]["live_action_eligibility_matrix"]
    }
    assert set(eligibility_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    for item in eligibility_by_family.values():
        checks = {check["code"]: check for check in item["checks"]}
        assert item["eligibility"] == "not_eligible"
        assert item["decision"] == "scope_incomplete_or_unmatched"
        assert checks["owner_scope_complete"]["status"] == "block"
        assert checks["official_action_api_candidate_supported"]["status"] == (
            "pass" if item["family"] in {"Trend", "Mean reversion"} else "block"
        )
        assert checks["backend_final_gate_actionable"]["status"] == "block"
        assert checks["pre_action_pg_snapshot"]["status"] == "required_before_live_action"
        assert checks["pre_action_exchange_snapshot"]["status"] == "required_before_live_action"
        assert checks["mandatory_tp_sl_plan"]["status"] == "draft_required"
        assert checks["execution_intent"]["status"] == "not_created"
        assert checks["review_contract"]["status"] == "draft_required"
        assert checks["audit_chain_ready"]["status"] == "block"
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["may_execute_live"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    assert payload["data"]["audit_chain_gap_report"]["bridge_method"] == "AuditChainGapReport"
    assert payload["data"]["audit_chain_gap_report"]["live_action_evidence_present"] is False
    assert payload["data"]["audit_chain_gap_report"]["places_order"] is False
    assert "execution_intent" in payload["data"]["audit_chain_gap_report"]["missing_evidence"]
    assert "audit_log_events" in payload["data"]["audit_chain_gap_report"]["missing_evidence"]
    evidence_keys = {
        (item["phase"], item["source_type"], item["source"])
        for item in payload["data"]["pg_exchange_evidence_matrix"]
    }
    assert ("pre_action", "pg_table", "orders") in evidence_keys
    assert ("pre_action", "pg_table", "positions") in evidence_keys
    assert ("post_action", "pg_table", "execution_intents") in evidence_keys
    assert ("pre_action", "exchange_read", "open_orders") in evidence_keys
    assert ("post_action", "exchange_read", "order_detail") in evidence_keys
    assert ("audit", "audit_source", "audit_logs") in evidence_keys
    assert len(payload["data"]["pg_exchange_evidence_matrix"]) == 27
    for item in payload["data"]["pg_exchange_evidence_matrix"]:
        assert item["status"] == "required_not_collected"
        assert item["collection_policy"] == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item["evidence_ref"] is None
        assert item["read_only"] is True
        assert item["mutates_pg"] is False
        assert item["exchange_write_action"] is False
        assert item["places_order"] is False
    family_evidence_keys = {
        (item["family"], item["phase"], item["source_type"], item["source"])
        for item in payload["data"]["family_evidence_collection_matrix"]
    }
    assert len(payload["data"]["family_evidence_collection_matrix"]) == 81
    assert ("Trend", "pre_action", "pg_table", "orders") in family_evidence_keys
    assert ("Trend", "post_action", "pg_table", "positions") in family_evidence_keys
    assert ("Trend", "pre_action", "exchange_read", "open_orders") in family_evidence_keys
    assert ("Trend", "post_action", "exchange_read", "order_detail") in family_evidence_keys
    assert ("Trend", "audit", "audit_source", "audit_logs") in family_evidence_keys
    assert ("Volatility expansion", "pre_action", "pg_table", "orders") in family_evidence_keys
    assert ("Mean reversion", "audit", "audit_source", "operation_results") in family_evidence_keys
    for item in payload["data"]["family_evidence_collection_matrix"]:
        assert item["status"] == "required_not_collected"
        assert item["collection_policy"] == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item["evidence_ref"] is None
        assert item["official_collection_path"]
        assert item["next_retry_condition"]
        assert item["read_only"] is True
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["exchange_write_action"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
        if item["phase"] == "pre_action":
            assert item["required_for_stage"] == "Entry"
        else:
            assert item["required_for_stage"] == "Review"
    evidence_summary_by_family = {
        item["family"]: item for item in payload["data"]["evidence_collection_summary_matrix"]
    }
    assert set(evidence_summary_by_family) == {
        "Trend",
        "Volatility expansion",
        "Mean reversion",
    }
    for item in evidence_summary_by_family.values():
        assert item["status"] == "blocked_required_not_collected"
        assert item["total_required"] == 27
        assert item["collected_count"] == 0
        assert item["required_not_collected_count"] == 27
        assert item["phase_counts"] == {"pre_action": 12, "post_action": 12, "audit": 3}
        assert item["source_type_counts"] == {
            "pg_table": 16,
            "exchange_read": 8,
            "audit_source": 3,
        }
        assert "official_action_service_pg_snapshot" in item["official_collection_paths"]
        assert "official_action_service_exchange_read_snapshot" in item[
            "official_collection_paths"
        ]
        assert "official_action_review_audit_chain" in item["official_collection_paths"]
        assert "pre_action:pg_table:orders" in item["missing_sources"]
        assert "post_action:exchange_read:order_detail" in item["missing_sources"]
        assert "audit:audit_source:audit_logs" in item["missing_sources"]
        assert item["collection_policy"] == "official_service_or_api_path_only_no_manual_pg_edits"
        assert item["next_retry_condition"]
        assert item["read_only"] is True
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["exchange_write_action"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    example_by_family = {
        item["family"]: item for item in payload["data"]["scoped_dry_run_examples"]
    }
    assert set(example_by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert example_by_family["Trend"]["owner_scope_query"]["symbol"] == "SOL/USDT:USDT"
    assert example_by_family["Trend"]["owner_scope_query"]["quantity"] == "0.1"
    assert example_by_family["Trend"]["expected_final_gate_reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert example_by_family["Trend"]["expected_action_api_status"] == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    assert example_by_family["Trend"]["expected_eligibility_decision"] == (
        "scope_complete_but_backend_final_gate_blocked"
    )
    assert example_by_family["Volatility expansion"]["owner_scope_query"]["strategy_family_id"] == (
        "VB-001-live-readonly-v0"
    )
    assert example_by_family["Mean reversion"]["owner_scope_query"]["carrier_id"] == (
        "MR-001-live-readonly-v0"
    )
    for item in example_by_family.values():
        assert item["expected_scope_verdict"] == "complete_dry_run_only"
        assert item["expected_authorization_draft_status"] == "scope_reviewed_dry_run_only"
        assert item["not_owner_authorization"] is True
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["starts_runtime"] is False
        assert item["starts_strategy_execution"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    assert payload["data"]["pre_execution_blocked_review"]["bridge_method"] == (
        "PreExecutionBlockedReview"
    )
    assert payload["data"]["pre_execution_blocked_review"]["blocked_reason"] == (
        "no_family_candidate_is_pre_execution_actionable"
    )
    assert payload["data"]["pre_execution_blocked_review"]["action_allowed"] is False
    assert payload["data"]["pre_execution_blocked_review"]["frontend_action_enabled"] is False
    assert payload["data"]["pre_execution_blocked_review"]["places_order"] is False
    assert payload["data"]["pre_execution_blocked_review"]["mutates_pg"] is False
    assert payload["data"]["pre_execution_blocked_review"]["unresolved_blocker_ids"]
    acceptance_by_item = {
        item["item"]: item for item in payload["data"]["acceptance_evidence_matrix"]
    }
    assert acceptance_by_item["strategy_families_have_concrete_candidates"]["status"] == "PASS"
    assert acceptance_by_item["strategy_group_carrier_mapping"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert acceptance_by_item["owner_risk_scope_review"]["status"] == "BLOCKED"
    assert "owner_review_handoff_matrix" in acceptance_by_item[
        "owner_risk_scope_review"
    ]["evidence_refs"]
    assert acceptance_by_item["api_backed_authorization_flow"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert "owner_review_handoff_matrix" in acceptance_by_item[
        "api_backed_authorization_flow"
    ]["evidence_refs"]
    assert acceptance_by_item[
        "frontend_action_disabled_until_backend_actionable"
    ]["status"] == "PASS"
    assert acceptance_by_item["production_capital_boundary"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert acceptance_by_item["official_action_api_candidate_support"]["status"] == "BLOCKED"
    assert acceptance_by_item["backend_final_gate_preflight"]["status"] == "BLOCKED"
    assert acceptance_by_item["pg_exchange_pre_post_evidence"]["status"] == "BLOCKED"
    assert acceptance_by_item["mandatory_tp_sl_protection"]["status"] == "DEFERRED"
    assert acceptance_by_item["review_audit_contract"]["status"] == "BLOCKED"
    assert acceptance_by_item["live_action_execution"]["status"] == "BLOCKED"
    assert "live_actions_taken=[]" in acceptance_by_item["live_action_execution"]["evidence_refs"]
    for item in acceptance_by_item.values():
        assert item["families"] == ["Trend", "Volatility expansion", "Mean reversion"]
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False
    bridge_statuses = {
        item["bridge_method"]: item for item in payload["data"]["bridge_artifact_statuses"]
    }
    assert set(bridge_statuses) == set(payload["data"]["bridge_artifacts"])
    assert bridge_statuses["TrendObservation"]["status"] == "present"
    assert bridge_statuses["TrendObservation"]["families"] == ["Trend"]
    assert bridge_statuses["StrategyGroupMappingProposal"]["status"] == "present"
    assert bridge_statuses["CarrierCandidate"]["status"] == "present"
    assert bridge_statuses["ActionCandidate"]["status"] == "blocked"
    assert bridge_statuses["BudgetEnvelopeDraft"]["status"] == "draft"
    assert bridge_statuses["FinalGateDryRun"]["status"] == "blocked"
    assert bridge_statuses["PreExecutionBlockedReview"]["status"] == "blocked"
    assert bridge_statuses["ProtectionPlanDraft"]["status"] == "draft"
    assert bridge_statuses["ReviewContract"]["status"] == "draft"
    assert bridge_statuses["AuditChainGapReport"]["status"] == "blocked"
    assert bridge_statuses["BudgetEnvelopeDraft"]["row_statuses"] == {
        "Trend": "scope_incomplete_no_numbers_fabricated",
        "Volatility expansion": "scope_incomplete_no_numbers_fabricated",
        "Mean reversion": "scope_incomplete_no_numbers_fabricated",
    }
    for item in bridge_statuses.values():
        assert item["action_allowed"] is False
        assert item["creates_authorization"] is False
        assert item["creates_execution_intent"] is False
        assert item["places_order"] is False
        assert item["mutates_pg"] is False

    by_family = {item["family"]: item for item in payload["data"]["families"]}
    assert set(by_family) == {"Trend", "Volatility expansion", "Mean reversion"}
    assert by_family["Trend"]["strategy_family_id"] == "TF-001-live-readonly-v0"
    assert by_family["Trend"]["classification"] == "actionable"
    assert by_family["Trend"]["strategy_group_mapping"]["bridge_method"] == (
        "StrategyGroupMappingProposal"
    )
    assert by_family["Trend"]["carrier_candidate"]["status"] == "registered_metadata_only"
    assert by_family["Trend"]["carrier_readiness_report"]["status"] == (
        "candidate_registered_not_actionable"
    )
    assert by_family["Trend"]["observation_bridge"]["bridge_method"] == "TrendObservation"
    assert by_family["Trend"]["observation_bridge"]["status"] == "observation_bridge_only"
    assert by_family["Trend"]["risk_disclosure_contract"]["bridge_method"] == "RiskDisclosureDraft"
    assert "false continuation" in by_family["Trend"]["risk_disclosure_contract"]["failure_modes"]
    assert by_family["Volatility expansion"]["strategy_family_id"] == "VB-001-live-readonly-v0"
    assert by_family["Volatility expansion"]["classification"] == "blocked"
    assert by_family["Volatility expansion"]["carrier_readiness_report"]["status"] == (
        "candidate_registered_not_actionable"
    )
    assert by_family["Volatility expansion"]["carrier_candidate"]["status"] == (
        "registered_metadata_only"
    )
    assert by_family["Volatility expansion"]["observation_bridge"]["bridge_method"] == (
        "CarrierReadinessReport"
    )
    assert by_family["Mean reversion"]["strategy_family_id"] == "MR-001-live-readonly-v0"
    assert by_family["Mean reversion"]["classification"] == "blocked"
    assert by_family["Mean reversion"]["observation_bridge"]["bridge_method"] == "CarrierCandidate"
    assert "liquidity wick" in by_family["Mean reversion"]["risk_disclosure_contract"]["failure_modes"]
    for item in by_family.values():
        assert item["backend_actionable"] is False
        assert item["frontend_action_enabled"] is False
        assert item["risk_disclosure_contract"]["status"] == "draft_for_owner_review"
        assert item["risk_disclosure_contract"]["family"] == item["family"]
        assert item["risk_disclosure_contract"]["owner_acknowledgement_required"] is True
        assert item["risk_disclosure_contract"]["not_authorization"] is True
        assert item["risk_disclosure_contract"]["not_execution_permission"] is True
        assert item["risk_disclosure_contract"]["not_order_permission"] is True
        assert item["authorization_draft_proposal"]["risk_disclosure_contract"]["not_authorization"] is True
        assert item["strategy_group_mapping"]["family"] == item["family"]
        assert item["strategy_group_mapping"]["carrier_id"] == item["carrier_id"]
        assert item["strategy_group_mapping"]["places_order"] is False
        assert item["strategy_group_mapping"]["mutates_pg"] is False
        assert item["carrier_candidate"]["bridge_method"] == "CarrierCandidate"
        assert item["carrier_candidate"]["family"] == item["family"]
        assert item["carrier_candidate"]["strategy_family_id"] == item["strategy_family_id"]
        assert item["carrier_candidate"]["carrier_id"] == item["carrier_id"]
        assert item["carrier_candidate"]["starts_runner"] is False
        assert item["carrier_candidate"]["creates_signal"] is False
        assert item["carrier_candidate"]["creates_trade_intent"] is False
        assert item["carrier_candidate"]["creates_execution_intent"] is False
        assert item["carrier_candidate"]["places_order"] is False
        assert item["carrier_candidate"]["mutates_pg"] is False
        assert item["carrier_candidate"]["blockers"]
        assert item["carrier_readiness_report"]["family"] == item["family"]
        assert item["carrier_readiness_report"]["carrier_id"] == item["carrier_id"]
        assert item["carrier_readiness_report"]["backend_actionable"] is False
        assert item["carrier_readiness_report"]["frontend_action_enabled"] is False
        assert item["carrier_readiness_report"]["places_order"] is False
        assert item["carrier_readiness_report"]["mutates_pg"] is False
        readiness_checks = {
            check["code"]: check for check in item["carrier_readiness_report"]["readiness_checks"]
        }
        assert readiness_checks["official_action_api_supported"]["status"] == (
            "pass" if item["family"] in {"Trend", "Mean reversion"} else "block"
        )
        assert readiness_checks["backend_actionable"]["status"] == "block"
        assert item["action_candidate"]["bridge_method"] == "ActionCandidate"
        assert item["action_candidate"]["family"] == item["family"]
        assert item["action_candidate"]["carrier_id"] == item["carrier_id"]
        assert item["action_candidate"]["status"] == (
            "supported_but_backend_not_actionable"
            if item["family"] in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        assert item["action_candidate"]["action_allowed"] is False
        assert item["action_candidate"]["backend_actionable"] is False
        assert item["action_candidate"]["frontend_action_enabled"] is False
        assert item["action_candidate"]["creates_authorization"] is False
        assert item["action_candidate"]["creates_execution_intent"] is False
        assert item["action_candidate"]["places_order"] is False
        assert item["action_candidate"]["mutates_pg"] is False
        assert "backend final gate returns actionable=true" in (
            item["action_candidate"]["required_before_action"]
        )
        assert item["observation_bridge"]["starts_runner"] is False
        assert item["observation_bridge"]["creates_signal"] is False
        assert item["observation_bridge"]["creates_trade_intent"] is False
        assert item["observation_bridge"]["creates_execution_intent"] is False
        assert item["observation_bridge"]["places_order"] is False
        assert item["observation_bridge"]["mutates_pg"] is False
        assert item["audit_chain_gap_report"]["family"] == item["family"]
        assert item["audit_chain_gap_report"]["bridge_method"] == "AuditChainGapReport"
        assert item["audit_chain_gap_report"]["live_action_evidence_present"] is False
        assert item["audit_chain_gap_report"]["creates_execution_intent"] is False
        assert item["audit_chain_gap_report"]["places_order"] is False
        assert item["audit_chain_gap_report"]["mutates_pg"] is False
        assert "post_action_review" in item["audit_chain_gap_report"]["missing_evidence"]
        assert item["pre_execution_blocked_review"]["bridge_method"] == (
            "PreExecutionBlockedReview"
        )
        assert item["pre_execution_blocked_review"]["family"] == item["family"]
        assert item["pre_execution_blocked_review"]["action_allowed"] is False
        assert item["pre_execution_blocked_review"]["frontend_action_enabled"] is False
        assert item["pre_execution_blocked_review"]["places_order"] is False
        assert item["pre_execution_blocked_review"]["mutates_pg"] is False
        pre_execution_checks = {
            check["code"]: check for check in item["pre_execution_blocked_review"]["checks"]
        }
        assert pre_execution_checks["backend_final_gate_actionable"]["status"] == "block"
        assert pre_execution_checks["mandatory_tp_sl_plan"]["status"] == "draft_required"
        assert item["admission_verdict"]["may_execute_live"] is False
        assert item["admission_verdict"]["frontend_action_enabled"] is False
        assert item["admission_verdict"]["remaining_requirements"]
        assert "quantity" in item["required_scope_missing"]
        assert item["budget_envelope_draft"]["bridge_method"] == "BudgetEnvelopeDraft"
        assert item["budget_envelope_draft"]["scope"] == {}
        assert item["budget_envelope_draft"]["provided_scope_fields"] == []
        assert item["budget_envelope_draft"]["missing_scope_fields"] == [
            "symbol",
            "side",
            "quantity",
            "max_notional",
            "leverage",
            "max_attempts",
            "protection_mode",
            "review_requirement",
        ]
        assert item["budget_envelope_draft"]["numbers_source"] == (
            "owner_scope_only_no_fabrication"
        )
        assert item["budget_envelope_draft"]["quantity"] is None
        assert item["budget_envelope_draft"]["max_notional"] is None
        assert item["budget_envelope_draft"]["action_allowed"] is False
        assert item["budget_envelope_draft"]["creates_authorization"] is False
        assert item["budget_envelope_draft"]["creates_execution_intent"] is False
        assert item["budget_envelope_draft"]["places_order"] is False
        assert item["budget_envelope_draft"]["mutates_pg"] is False
        budget_checks = {
            check["code"]: check for check in item["budget_envelope_draft"]["validation_checks"]
        }
        assert budget_checks["owner_scope_complete"]["status"] == "block"
        assert budget_checks["quantity_provided"]["status"] == "missing"
        assert item["execution_intent_state"] == "not_created"
        assert item["entry_state"] == "not_executed"
        assert item["protection_plan_state"] == "draft_required_mandatory_tp_sl"
        assert item["protection_plan_draft"]["bridge_method"] == "ProtectionPlanDraft"
        assert item["protection_plan_draft"]["status"] == "draft_required_mandatory_tp_sl"
        assert "complete_matched_owner_scope" in item["protection_plan_draft"]["missing_fields"]
        assert "take_profit_price" in item["protection_plan_draft"]["missing_fields"]
        assert item["protection_plan_draft"]["unavailable_fields"]["take_profit_price"] == (
            "not_fabricated_by_read_model"
        )
        assert item["protection_plan_draft"]["unavailable_fields"]["exchange_sl_order_id"] == (
            "not_created_by_read_model"
        )
        assert item["protection_plan_draft"]["action_allowed"] is False
        assert item["protection_plan_draft"]["creates_order"] is False
        assert item["protection_plan_draft"]["places_order"] is False
        assert item["protection_plan_draft"]["mutates_pg"] is False
        protection_checks = {
            check["code"]: check for check in item["protection_plan_draft"]["validation_checks"]
        }
        assert protection_checks["owner_scope_complete"]["status"] == "block"
        assert protection_checks["take_profit_defined"]["status"] == "missing"
        assert item["authorization_draft_proposal"]["not_authorization"] is True
        assert item["authorization_draft_proposal"]["protection_plan"]["action_allowed"] is False
        assert item["authorization_draft_proposal"]["not_execution_permission"] is True
        assert item["authorization_draft_proposal"]["not_order_permission"] is True
        assert item["action_api_compatibility"]["compatible"] is (
            item["family"] in {"Trend", "Mean reversion"}
        )
        assert item["review_contract"]["status"] == "draft_no_action_evidence"
        assert item["review_contract"]["bridge_method"] == "ReviewContract"
        assert item["review_contract"]["family"] == item["family"]
        assert "entry_order" in item["review_contract"]["required_evidence"]
        assert "entry_order" in item["review_contract"]["missing_evidence"]
        assert "audit_log_events" in item["review_contract"]["missing_evidence"]
        assert item["review_contract"]["promotion_allowed"] is False
        assert item["review_contract"]["records_review"] is False
        assert item["review_contract"]["places_order"] is False
        assert item["review_contract"]["mutates_pg"] is False
        assert item["authorization_draft_proposal"]["review_contract"]["promotion_allowed"] is False
        assert item["action_api_compatibility"]["status"] == (
            "supported_by_current_official_action_api_but_not_actionable"
            if item["family"] in {"Trend", "Mean reversion"}
            else "unsupported_by_current_official_action_api"
        )
        gate_blocker_ids = {record["id"] for record in item["gate_blocker_records"]}
        assert f"{item['blocker_record']['id']}-SCOPE" in gate_blocker_ids
        if item["family"] in {"Trend", "Mean reversion"}:
            assert f"{item['blocker_record']['id']}-ACTION-API" not in gate_blocker_ids
        else:
            assert f"{item['blocker_record']['id']}-ACTION-API" in gate_blocker_ids
        assert f"{item['blocker_record']['id']}-FINAL-GATE" in gate_blocker_ids
        assert f"{item['blocker_record']['id']}-EVIDENCE" in gate_blocker_ids
        assert f"{item['blocker_record']['id']}-PROTECTION" in gate_blocker_ids
        assert [draft["name"] for draft in item["api_request_drafts"]] == [
            "create_admission_evidence_packet",
            "create_owner_regime_input",
            "create_admission_request",
            "create_owner_risk_acceptance",
            "operation_preflight_create_gated_trial_from_admission",
        ]
        assert all(draft["not_submitted"] is True for draft in item["api_request_drafts"])
        assert all(draft["places_order"] is False for draft in item["api_request_drafts"])
        assert [stage["stage"] for stage in item["chain_stage_states"]] == [
            "StrategyFamily",
            "StrategyGroup",
            "Carrier",
            "RiskDisclosure",
            "AuthorizationDraft",
            "BoundedLiveAuthorization",
            "ExecutionIntent",
            "Entry",
            "TP/SL",
            "Review",
        ]
        assert item["pre_post_evidence_contract"]["mutation_allowed_by_read_model"] is False
        assert item["pre_post_evidence_contract"]["live_action_evidence_present"] is False
        assert "orders" in item["pre_post_evidence_contract"]["pre_action_pg_tables"]
        assert "open_orders" in item["pre_post_evidence_contract"]["pre_action_exchange_reads"]

    blocker_codes = {item["code"] for item in payload["blockers"]}
    assert "production_scope_incomplete" in blocker_codes
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_action_entry_readiness_exposes_generic_specs_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/action-entry-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "action_entry_readiness"
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert payload["no_action_guarantee"]["starts_runtime"] is False
    assert payload["data"]["owner_market_input"] == {
        "regime": "not_selected",
        "mapped_family": None,
        "symbol_preference": None,
        "side": None,
        "risk_tier": "tiny",
        "note": None,
        "source": "owner_input_query",
        "persisted": False,
    }
    budget = payload["data"]["budget_recommendation"]
    assert budget["risk_tier"]["tier"] == "tiny"
    assert budget["budget_envelope"]["status"] == "degraded_missing_account_facts"
    assert [item["symbol"] for item in budget["recommended_symbols"]] == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    assert budget["owner_selection"]["status"] == "not_provided"
    assert budget["budgeted_autonomy_enabled"] is False
    assert budget["action_allowed"] is False
    assert budget["no_action_guarantee"]["places_order"] is False

    adapter = payload["data"]["generic_final_gate_adapter_contract"]
    assert adapter["live_action_policy"] == "fail_closed_until_official_final_gate_passes"
    assert adapter["may_execute_live"] is False
    assert adapter["places_order"] is False
    assert "missing Owner execute authorization" in adapter["hard_blockers_for_live_action"]
    assert "weak strategy evidence" in adapter["warning_not_blocker"]

    specs = {item["family"]: item for item in payload["data"]["generic_action_specs"]}
    trend = specs["Trend"]
    assert trend["carrier_id"] == "TF-001-live-readonly-v0"
    assert trend["status"] == "valid_blocked_final_gate"
    assert trend["symbol"] == "SOL/USDT:USDT"
    assert trend["side"] == "long"
    assert trend["quantity"] == "0.1"
    assert trend["max_notional"] == "20"
    assert trend["leverage"] == "1"
    assert trend["max_attempts"] == 1
    assert trend["protection_mode"] == "single_tp_plus_sl"
    assert trend["budget_envelope_ref"] == "budget-envelope:read-only-recommendation"
    assert trend["sizing_source"] == "budget_envelope_recommendation"
    assert trend["budget_owner_confirmation_required"] is True
    assert trend["may_execute_live"] is False
    assert trend["frontend_action_enabled"] is False
    assert trend["places_order"] is False
    assert specs["Volatility expansion"]["status"] == "proposal_non_action"
    assert specs["Volatility expansion"]["action_registry_supported"] is False
    assert specs["Mean reversion"]["status"] == "proposal_non_action"
    assert specs["Mean reversion"]["action_registry_supported"] is True
    assert specs["Mean reversion"]["proposal_role"] == "range_candidate"
    assert specs["Mean reversion"]["market_regime"] == "mean_reversion"
    assert specs["Mean reversion"]["symbol"] == "ETH/USDT:USDT"
    assert specs["Mean reversion"]["side"] == "long"
    assert specs["Mean reversion"]["quantity"] is None
    assert specs["Mean reversion"]["target_notional_usdt"] == "22"
    assert specs["Mean reversion"]["computed_quantity"] is None
    assert specs["Mean reversion"]["max_notional"] == "25"
    assert specs["Mean reversion"]["recommended_quantity"] is None
    assert specs["Mean reversion"]["recommended_max_notional"] is None
    assert specs["Mean reversion"]["protection_mode"] == "single_tp_plus_sl"
    assert specs["Mean reversion"]["protection_template"]["mode"] == "single_tp_plus_sl"
    assert specs["Mean reversion"]["review_template"]["template_id"] == (
        "review-template:MR-001-live-readonly-v0"
    )
    assert specs["Mean reversion"]["may_execute_live"] is False
    assert specs["Mean reversion"]["frontend_action_enabled"] is False
    assert specs["Mean reversion"]["places_order"] is False

    payloads = {
        item["family"]: item for item in payload["data"]["action_entry_payload_contracts"]
    }
    assert payloads["Trend"]["contract_status"] == "ready_for_final_gate_adapter"
    assert payloads["Trend"]["required_owner_scope"]["symbol"] == "SOL/USDT:USDT"
    assert payloads["Trend"]["action_allowed"] is False
    assert payloads["Mean reversion"]["contract_status"] == "proposal_only"
    assert payloads["Mean reversion"]["required_owner_scope"]["symbol"] == "ETH/USDT:USDT"
    assert payloads["Mean reversion"]["required_owner_scope"]["quantity"] is None
    assert payloads["Mean reversion"]["required_owner_scope"]["target_notional_usdt"] == "22"
    assert payloads["Mean reversion"]["action_allowed"] is False

    action_entry = {
        item["family"]: item for item in payload["data"]["action_entry_output"]
    }
    assert action_entry["Trend"]["action_entry_state"] == (
        "ready_for_owner_scope_final_gate"
    )
    assert action_entry["Trend"]["frontend_action_enabled"] is False
    assert action_entry["Volatility expansion"]["action_entry_state"] == "proposal_only"
    assert action_entry["Mean reversion"]["action_entry_state"] == "proposal_only"

    selected = payload["data"]["selected_candidate"]
    assert selected["family"] == "Trend"
    assert selected["carrier_id"] == "TF-001-live-readonly-v0"
    assert selected["scope_review"]["verdict"] == "not_checked"
    risk_review = payload["data"]["risk_review"]
    assert risk_review["weak_strategy_evidence_policy"] == "warning_not_hard_blocker"
    assert "weak strategy evidence" in risk_review["warnings"]
    authorization_path = payload["data"]["authorization_draft_path"]
    assert authorization_path["status"] == "readiness_only_no_draft_created"
    assert authorization_path["official_service_path_available"] is True
    assert authorization_path["creates_authorization"] is False
    assert authorization_path["creates_execution_intent"] is False
    final_gate = payload["data"]["final_gate_result"]
    assert final_gate["status"] == "blocked_until_official_final_gate_passes"
    assert final_gate["may_execute_live"] is False
    assert final_gate["frontend_action_enabled"] is False
    action_state = payload["data"]["action_state"]
    assert action_state["enabled"] is False
    assert action_state["may_execute_live"] is False
    assert action_state["frontend_action_enabled"] is False
    assert action_state["places_order"] is False
    assert action_state["mutates_pg"] is False
    post_action_state = payload["data"]["post_action_state"]
    assert post_action_state["retry_safety"] == (
        "consumed_authorization_or_completed_intent_blocks_duplicate_execution"
    )
    assert post_action_state["status"] == "available"
    assert post_action_state["entry_order_count"] == 1
    assert post_action_state["protection_order_count"] == 2
    assert post_action_state["review_count"] == 1
    assert post_action_state["audit_event_count"] == 1
    assert post_action_state["summary"]["entry_orders"][0]["order_id"] == "entry-1"
    assert {
        item["order_id"] for item in post_action_state["summary"]["tp_sl_orders"]
    } == {"tp-1", "sl-1"}
    assert post_action_state["summary"]["reviews"][0]["review_id"] == "review-1"
    assert post_action_state["summary"]["audit_events"][0]["event_type"] == "ORDER_CONFIRMED"
    ledger = post_action_state["review_ledger"]
    assert ledger["ledger_version"] == "owner_bounded_review_ledger_v0"
    assert ledger["lifecycle_status"] == "protected_open_from_pg_orders"
    assert ledger["entry"]["status"] == "filled"
    assert ledger["entry"]["order_id"] == "entry-1"
    assert ledger["exit"]["status"] == "not_available"
    assert ledger["realized_pnl"]["status"] == "not_available"
    assert ledger["unrealized_pnl"]["status"] == "not_available"
    assert ledger["costs"]["fees"]["status"] == "not_available"
    assert ledger["costs"]["funding"]["status"] == "not_available"
    assert ledger["costs"]["slippage"]["status"] == "not_available"
    assert ledger["tp_sl_result"]["status"] == "protected_open"
    assert ledger["tp_sl_result"]["open_protection_order_count"] == 2
    assert ledger["review_decision"]["allowed_values"] == ["promote", "revise", "park"]
    assert ledger["hard_blockers"] == []
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_owner_action_flow_budget_ignores_historical_closed_orders(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(normal_orders=[], stop_orders=[])
    closed_orders = [
        _FakeOrder(
            "entry-closed",
            "ENTRY",
            "entry-exchange-1",
            parent_order_id=None,
            status="FILLED",
            symbol="SOL/USDT:USDT",
        ),
        _FakeOrder(
            "tp-closed",
            "TP1",
            "tp-exchange-1",
            status="FILLED",
            symbol="SOL/USDT:USDT",
        ),
        _FakeOrder(
            "sl-closed",
            "SL",
            "sl-exchange-1",
            status="CANCELED",
            symbol="SOL/USDT:USDT",
        ),
    ]
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo(closed_orders),
        account_snapshot=_FakeAccountSnapshot(),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "include_exchange": "true",
                "market_regime": "trend",
                "family": "Trend",
                "strategy_family_id": "TF-001-live-readonly-v0",
                "carrier_id": "TF-001-live-readonly-v0",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "quantity": "0.1",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    flow = response.json()["data"]["owner_action_flow"]
    assert flow["budget_summary"]["status"] == "available"
    assert flow["budget_summary"]["account_capacity_status"] == "available"
    assert flow["budget_summary"]["max_usable_notional"] == "150"
    assert "open orders reduce recommended usable budget" not in flow["budget_summary"]["warnings"]
    assert flow["budgeted_autonomy_v01"]["policy"]["daily_attempts"]["used"] == 0
    assert flow["budgeted_autonomy_v01"]["frontend_action_enabled"] is False
    assert flow["budgeted_autonomy_v01"]["places_order"] is False


def test_owner_action_flow_v01_attempts_ignore_prior_day_completed_intent(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(normal_orders=[], stop_orders=[])
    prior_day_ms = int(time.time() * 1000) - 2 * 24 * 60 * 60 * 1000
    intent_repo = _FakeIntentRepo(
        [
            SimpleNamespace(
                id="intent-prior-day",
                signal_id="signal-prior-day",
                symbol="SOL/USDT:USDT",
                status="completed",
                order_id="entry-prior-day",
                authorization_id="auth-prior-day",
                exchange_order_id="exchange-prior-day",
                blocked_reason=None,
                blocked_message=None,
                failed_reason=None,
                created_at=prior_day_ms,
                updated_at=prior_day_ms,
            )
        ]
    )
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo([]),
        intent_repo=intent_repo,
        account_snapshot=_FakeAccountSnapshot(),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "include_exchange": "true",
                "market_regime": "trend",
                "family": "Trend",
                "strategy_family_id": "TF-001-live-readonly-v0",
                "carrier_id": "TF-001-live-readonly-v0",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "quantity": "0.1",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    v01 = response.json()["data"]["owner_action_flow"]["budgeted_autonomy_v01"]
    assert v01["policy"]["daily_attempts"]["used"] == 0
    assert v01["policy"]["daily_attempts"]["remaining"] == 1
    assert v01["policy"]["daily_attempts"]["source"] == (
        "trading_console_selected_symbol_pg_intents_current_utc_day"
    )
    assert "BUDGETED-AUTONOMY-V01-DAILY-ATTEMPTS-EXHAUSTED" not in {
        item["id"] for item in v01["hard_blockers"]
    }
    assert v01["frontend_action_enabled"] is False
    assert v01["places_order"] is False


def test_owner_action_flow_accepts_owner_approved_custom_budget_envelope(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(normal_orders=[], stop_orders=[])
    window_start_ms = int(time.time() * 1000)
    prior_same_day_ms = window_start_ms - 1_000
    intent_repo = _FakeIntentRepo(
        [
            SimpleNamespace(
                id="intent-before-budget-window",
                signal_id="signal-before-budget-window",
                symbol="SOL/USDT:USDT",
                status="completed",
                order_id="entry-before-budget-window",
                authorization_id="auth-before-budget-window",
                exchange_order_id="exchange-before-budget-window",
                blocked_reason=None,
                blocked_message=None,
                failed_reason=None,
                created_at=prior_same_day_ms,
                updated_at=prior_same_day_ms,
            )
        ]
    )
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo([]),
        intent_repo=intent_repo,
        account_snapshot=_FakeAccountSnapshot(),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "include_exchange": "true",
                "market_regime": "trend",
                "family": "Trend",
                "strategy_family_id": "TF-001-live-readonly-v0",
                "carrier_id": "TF-001-live-readonly-v0",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "target_notional_usdt": "20",
                "current_price": "200",
                "min_notional": "5",
                "min_qty": "0.01",
                "qty_step": "0.01",
                "price_tick": "0.01",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
                "risk_tier": "custom",
                "custom_total_budget": "25",
                "custom_max_notional_per_action": "20",
                "custom_max_daily_loss": "1",
                "custom_capacity_fraction": "0.2",
                "custom_max_active_positions": "1",
                "custom_max_attempts": "1",
                "custom_max_leverage": "1",
                "custom_budget_authorization_id": "budget-envelope:owner-approved-test",
                "custom_attempt_window_start_ms": str(window_start_ms),
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["budget_recommendation"]["budget_envelope"]["envelope_id"] == (
        "budget-envelope:owner-approved-test"
    )
    assert data["budget_recommendation"]["owner_approved_budget_window"][
        "attempt_window_start_ms"
    ] == window_start_ms
    flow = data["owner_action_flow"]
    assert flow["budget_summary"]["status"] == "available"
    assert flow["budget_summary"]["recommended_total_budget"] == "25"
    assert flow["budget_summary"]["recommended_max_notional_per_action"] == "20"
    assert flow["budget_summary"]["owner_selection_status"] == "within_recommendation"
    proposal = flow["selected_action_proposal"]
    assert proposal["status"] == "valid_blocked_final_gate"
    assert proposal["target_notional_usdt"] == "20"
    assert proposal["computed_quantity"] == "0.1"
    assert proposal["estimated_notional_usdt"] == "20.0"
    assert "owner_max_notional_exceeds_budget_envelope" not in proposal["hard_blockers"]
    assert flow["budgeted_autonomy_v01"]["policy"]["budget"]["max_notional_per_action"] == "20"
    assert flow["budgeted_autonomy_v01"]["policy"]["daily_attempts"]["used"] == 0
    assert flow["budgeted_autonomy_v01"]["policy"]["daily_attempts"]["source"] == (
        "trading_console_selected_symbol_pg_intents_owner_budget_window"
    )
    assert flow["budgeted_autonomy_v01"]["frontend_action_enabled"] is False
    assert flow["budgeted_autonomy_v01"]["places_order"] is False


def test_budgeted_autonomy_runner_uses_selected_proposal_exact_quantity():
    from scripts.budgeted_autonomy_v01_cycle import _scope_from_selected_proposal

    scope = {
        "market_regime": "trend",
        "family": "Trend",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "carrier_id": "TF-001-live-readonly-v0",
        "symbol": "SOL/USDT:USDT",
        "side": "long",
        "quantity": "0.1",
        "max_notional": "20",
        "leverage": "1",
        "max_attempts": "1",
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
    }
    flow_body = {
        "data": {
            "owner_action_flow": {
                "selected_action_proposal": {
                    "family": "Trend",
                    "strategy_family_id": "TF-001-live-readonly-v0",
                    "carrier_id": "TF-001-live-readonly-v0",
                    "symbol": "SOL/USDT:USDT",
                    "side": "long",
                    "computed_quantity": "0.15",
                    "target_notional_usdt": "20",
                    "max_notional": "20",
                    "leverage": "1",
                    "max_attempts": 1,
                    "protection_mode": "single_tp_plus_sl",
                    "review_requirement": "post_action_review_required",
                }
            }
        }
    }

    selected = _scope_from_selected_proposal(flow_body, scope)

    assert selected["quantity"] == "0.15"
    assert selected["target_notional_usdt"] == "20"
    assert selected["carrier_id"] == "TF-001-live-readonly-v0"


def test_owner_action_flow_computes_mr_eth_quantity_from_target_notional(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "market_regime": "range",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "target_notional_usdt": "22",
                "current_price": "1681.64",
                "min_notional": "20",
                "min_qty": "0.001",
                "qty_step": "0.001",
                "price_tick": "0.01",
                "max_notional": "25",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    proposal = payload["data"]["owner_action_flow"]["selected_action_proposal"]
    assert proposal["carrier_id"] == "MR-001-live-readonly-v0"
    assert proposal["proposal_role"] == "range_candidate"
    assert proposal["target_notional_usdt"] == "22"
    assert proposal["computed_quantity"] == "0.014"
    assert proposal["quantity"] == "0.014"
    assert proposal["estimated_notional_usdt"] == "23.54296"
    assert proposal["status"] == "valid_blocked_final_gate"
    assert proposal["market_rule_snapshot"]["min_notional"] == "20"
    assert proposal["validation_result"]["entry_notional_valid"] is True
    assert proposal["validation_result"]["protection_notional_valid"] is True
    assert "computed_notional_exceeds_owner_max_notional" not in proposal["hard_blockers"]
    assert "computed_protection_notional_below_min_notional" not in proposal["hard_blockers"]
    assert proposal["backend_actionable"] is False
    assert proposal["frontend_action_enabled"] is False
    assert proposal["places_order"] is False


def test_owner_action_flow_wraps_action_entry_readiness_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    eth_orders = [
        _FakeOrder(
            "entry-1",
            "ENTRY",
            "91085295446",
            parent_order_id=None,
            status="FILLED",
            symbol="ETH/USDT:USDT",
        ),
        _FakeOrder("tp-1", "TP1", "91085295597", symbol="ETH/USDT:USDT"),
        _FakeOrder("sl-1", "SL", "4000001470395922", symbol="ETH/USDT:USDT"),
    ]
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo(eth_orders),
        position_repo=_FakeActivePositionRepo(symbol="ETH/USDT:USDT"),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "market_regime": "mean_reversion",
                "family": "Mean reversion",
                "strategy_family_id": "MR-001-live-readonly-v0",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "quantity": "0.01",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "owner_action_flow"
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    data = payload["data"]
    assert data["owner_market_input"]["mapped_family"] == "Mean reversion"
    selected = data["selected_candidate"]
    assert selected["family"] == "Mean reversion"
    assert selected["carrier_id"] == "MR-001-live-readonly-v0"
    assert selected["scope_review"]["verdict"] == "matched"
    assert selected["generic_action_spec"]["status"] == "invalid_blocked"
    assert selected["generic_action_spec"]["action_registry_supported"] is True
    assert selected["generic_action_spec"]["symbol"] == "ETH/USDT:USDT"
    assert (
        "target_notional_required_for_notional_sized_carrier"
        in selected["generic_action_spec"]["hard_blockers"]
    )
    assert data["action_state"]["enabled"] is False
    assert data["action_state"]["backend_actionable"] is False
    assert data["action_state"]["frontend_action_enabled"] is False
    assert data["action_state"]["places_order"] is False
    flow = data["owner_action_flow"]
    assert flow["status"] == "not_actionable"
    assert flow["unsafe_action_enabled"] is False
    assert flow["budget_summary"]["status"] == "degraded_missing_account_facts"
    assert flow["budget_summary"]["account_capacity_status"] == "degraded"
    assert flow["budget_summary"]["owner_selection_status"] == "within_recommendation"
    assert flow["budget_summary"]["selected_symbol"] == "ETH/USDT:USDT"
    assert flow["budget_summary"]["selected_max_notional"] == "20"
    assert [item["symbol"] for item in flow["budget_summary"]["recommended_symbols"]] == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    assert "account_equity" in flow["budget_summary"]["missing_facts"]
    assert flow["budget_summary"]["action_allowed"] is False
    assert flow["market_selection"]["selected_regime"] == "mean_reversion"
    assert flow["market_selection"]["mapped_family"] == "Mean reversion"
    assert flow["market_selection"]["range_candidate"]["carrier_id"] == (
        "MR-001-live-readonly-v0"
    )
    choices = {item["proposal_role"]: item for item in flow["market_selection"]["candidate_choices"]}
    assert choices["range_candidate"]["family"] == "Mean reversion"
    assert choices["range_candidate"]["recommended_quantity"] == "0.01"
    proposal = flow["selected_action_proposal"]
    assert proposal["proposal_role"] == "range_candidate"
    assert proposal["market_regime"] == "mean_reversion"
    assert proposal["owner_selection_status"] == "within_recommendation"
    assert proposal["owner_selected_scope"]["symbol"] == "ETH/USDT:USDT"
    assert proposal["recommended_quantity"] == "0.01"
    assert proposal["recommended_max_notional"] == "20"
    assert proposal["protection_template"]["mode"] == "single_tp_plus_sl"
    assert proposal["review_template"]["template_id"] == (
        "review-template:MR-001-live-readonly-v0"
    )
    assert proposal["backend_actionable"] is False
    assert proposal["frontend_action_enabled"] is False
    assert proposal["places_order"] is False
    autonomy_loop = flow["budgeted_autonomy_loop"]
    assert autonomy_loop["loop_version"] == "budgeted_autonomy_v0"
    assert autonomy_loop["outcome"] == "protected_open_review_pending"
    assert autonomy_loop["active_loop"] is True
    assert autonomy_loop["active_position_count"] == 1
    assert autonomy_loop["selected_candidate"] is None
    assert autonomy_loop["blocked_candidates"][0]["status"] == "blocked"
    assert autonomy_loop["blocked_candidates"][0]["blockers"][0]["id"] == (
        "BUDGETED-AUTONOMY-ACTIVE-POSITION"
    )
    assert autonomy_loop["action_allowed"] is False
    assert autonomy_loop["backend_actionable"] is False
    assert autonomy_loop["frontend_action_enabled"] is False
    assert autonomy_loop["auto_execution_enabled"] is False
    assert autonomy_loop["places_order"] is False
    assert autonomy_loop["mutates_pg"] is False
    autonomy_v01 = flow["budgeted_autonomy_v01"]
    assert autonomy_v01["loop_version"] == "budgeted_autonomy_v0_1"
    assert autonomy_v01["outcome"] == "protected_open_review_pending"
    assert autonomy_v01["policy"]["daily_attempts"]["allowed"] == 1
    assert autonomy_v01["policy"]["position_policy"]["single_position_default"] is True
    assert autonomy_v01["action_allowed"] is False
    assert autonomy_v01["places_order"] is False
    steps = {item["step"]: item for item in flow["flow_steps"]}
    assert set(steps) == {
        "market_input",
        "candidate_selection",
        "risk_disclosure",
        "budget_envelope",
        "authorization_draft",
        "final_gate",
        "action_state",
        "post_action_evidence",
        "budgeted_autonomy_loop",
        "budgeted_autonomy_v01",
    }
    assert steps["market_input"]["status"] == "ready"
    assert steps["candidate_selection"]["summary"] == (
        "MR-001-live-readonly-v0 / range_candidate"
    )
    assert steps["budget_envelope"]["status"] == "blocked"
    assert steps["action_state"]["status"] == "blocked"
    assert steps["budgeted_autonomy_loop"]["status"] == (
        "protected_open_review_pending"
    )
    assert steps["budgeted_autonomy_v01"]["status"] == (
        "protected_open_review_pending"
    )
    assert flow["timeline"]["entry_order_count"] == 1
    assert flow["timeline"]["protection_order_count"] == 2
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_owner_action_flow_include_exchange_marks_eth_pg_exchange_cleanup_needed(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(positions=[], normal_orders=[], stop_orders=[])
    eth_orders = [
        _FakeOrder(
            "entry-eth",
            "ENTRY",
            "entry-exchange-eth",
            parent_order_id=None,
            status="FILLED",
            symbol="ETH/USDT:USDT",
        ),
        _FakeOrder("tp-eth", "TP1", "tp-exchange-eth", symbol="ETH/USDT:USDT"),
        _FakeOrder("sl-eth", "SL", "sl-exchange-eth", symbol="ETH/USDT:USDT"),
    ]
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo(eth_orders),
        position_repo=_FakeActivePositionRepo(symbol="ETH/USDT:USDT"),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "include_exchange": "true",
                "market_regime": "mean_reversion",
                "family": "Mean reversion",
                "strategy_family_id": "MR-001-live-readonly-v0",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "target_notional_usdt": "16.8",
                "current_price": "1680",
                "min_notional": "5",
                "min_qty": "0.001",
                "qty_step": "0.001",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    post_action = data["post_action_state"]
    assert post_action["exchange_state"]["status"] == (
        "pg_open_exchange_flat_cleanup_needed"
    )
    flow = data["owner_action_flow"]
    autonomy_loop = flow["budgeted_autonomy_loop"]
    assert autonomy_loop["outcome"] == "blocked_with_retry_condition"
    assert autonomy_loop["hard_blockers"][0]["id"] == (
        "BUDGETED-AUTONOMY-PG-EXCHANGE-MISMATCH"
    )
    assert autonomy_loop["blocked_candidates"][0]["blockers"][0]["id"] == (
        "BUDGETED-AUTONOMY-PG-EXCHANGE-MISMATCH"
    )
    assert autonomy_loop["action_allowed"] is False
    assert autonomy_loop["backend_actionable"] is False
    assert autonomy_loop["frontend_action_enabled"] is False
    assert autonomy_loop["places_order"] is False
    assert data["action_state"]["enabled"] is False
    assert exchange.open_order_calls == [
        ("ETH/USDT:USDT", None),
        ("ETH/USDT:USDT", {"stop": True}),
    ]
    assert exchange.position_calls == ["ETH/USDT:USDT"]
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_owner_action_flow_marks_external_flat_hygiene_closed_reviewed(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(positions=[], normal_orders=[], stop_orders=[])
    tp = _FakeOrder("tp-eth", "TP1", "tp-exchange-eth", symbol="ETH/USDT:USDT")
    sl = _FakeOrder("sl-eth", "SL", "sl-exchange-eth", symbol="ETH/USDT:USDT")
    for order in (tp, sl):
        order.status = "CANCELED"
        order.exit_reason = "EXTERNAL_CLOSE_LOCAL_HYGIENE"
    eth_orders = [
        _FakeOrder(
            "entry-eth",
            "ENTRY",
            "entry-exchange-eth",
            parent_order_id=None,
            status="FILLED",
            symbol="ETH/USDT:USDT",
        ),
        tp,
        sl,
    ]
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        order_repo=_FakeOrderRepo(eth_orders),
        position_repo=_FakePositionRepo(),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "include_exchange": "true",
                "market_regime": "mean_reversion",
                "family": "Mean reversion",
                "strategy_family_id": "MR-001-live-readonly-v0",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "target_notional_usdt": "16.8",
                "current_price": "1680",
                "min_notional": "5",
                "min_qty": "0.001",
                "qty_step": "0.001",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    post_action = data["post_action_state"]
    assert post_action["exchange_state"]["status"] == "exchange_flat"
    ledger = post_action["review_ledger"]
    assert ledger["lifecycle_status"] == "closed_external_exchange_flat_unresolved"
    assert ledger["tp_sl_result"]["status"] == "external_flat_local_hygiene_terminalized"
    assert ledger["tp_sl_result"]["open_protection_order_count"] == 0
    assert ledger["exit"]["status"] == "external_exchange_flat_unresolved"
    assert ledger["review_decision"]["status"] == "revise"
    assert ledger["strategy_outcome"] == "revise_after_external_flat_reconciliation"
    autonomy_loop = data["owner_action_flow"]["budgeted_autonomy_loop"]
    assert autonomy_loop["outcome"] == "closed_reviewed"
    assert autonomy_loop["active_loop"] is False
    assert autonomy_loop["selected_candidate"] is None
    assert autonomy_loop["action_allowed"] is False
    assert autonomy_loop["places_order"] is False
    assert data["action_state"]["enabled"] is False
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_owner_action_flow_allows_mr_btc_owner_selection_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "market_regime": "mean_reversion",
                "family": "Mean reversion",
                "strategy_family_id": "MR-001-live-readonly-v0",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "quantity": "0.001",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    selected = data["selected_candidate"]
    assert selected["family"] == "Mean reversion"
    assert selected["scope_review"]["verdict"] == "matched"
    assert selected["generic_action_spec"]["symbol"] == "BTC/USDT:USDT"
    assert selected["generic_action_spec"]["recommended_quantity"] == "0.001"
    assert selected["generic_action_spec"]["recommended_max_notional"] == "20"
    flow = data["owner_action_flow"]
    assert flow["market_selection"]["range_candidate"]["carrier_id"] == (
        "MR-001-live-readonly-v0"
    )
    proposal = flow["selected_action_proposal"]
    assert proposal["symbol"] == "BTC/USDT:USDT"
    assert proposal["proposal_role"] == "range_candidate"
    assert proposal["owner_selected_scope"]["symbol"] == "BTC/USDT:USDT"
    assert proposal["backend_actionable"] is False
    assert proposal["frontend_action_enabled"] is False
    assert proposal["places_order"] is False
    assert data["action_state"]["enabled"] is False
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_owner_action_flow_blocks_mr_symbol_outside_carrier_bounds(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/owner-action-flow",
            params={
                "market_regime": "mean_reversion",
                "family": "Mean reversion",
                "strategy_family_id": "MR-001-live-readonly-v0",
                "carrier_id": "MR-001-live-readonly-v0",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "quantity": "0.1",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": "1",
                "protection_mode": "single_tp_plus_sl",
                "review_requirement": "post_action_review_required",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    selected_spec = data["selected_candidate"]["generic_action_spec"]
    assert selected_spec["symbol"] == "SOL/USDT:USDT"
    assert "owner_symbol_not_supported_by_carrier" in selected_spec["hard_blockers"]
    proposal = data["owner_action_flow"]["selected_action_proposal"]
    assert proposal["symbol"] == "SOL/USDT:USDT"
    assert "owner_symbol_not_supported_by_carrier" in proposal["hard_blockers"]
    assert proposal["frontend_action_enabled"] is False
    assert proposal["places_order"] is False
    assert data["action_state"]["enabled"] is False
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_action_entry_readiness_accepts_owner_market_input_without_actions(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    query = {
        "market_regime": "trend",
        "symbol_preference": "SOL/USDT:USDT",
        "side": "long",
        "risk_tier": "small",
        "note": "Owner sees a small trend continuation setup.",
        "family": "Trend",
        "strategy_family_id": "TF-001-live-readonly-v0",
        "carrier_id": "TF-001-live-readonly-v0",
        "symbol": "SOL/USDT:USDT",
        "quantity": "0.1",
        "max_notional": "20",
        "leverage": "1",
        "max_attempts": "1",
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
    }

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/action-entry-readiness", params=query)

    assert response.status_code == 200
    payload = response.json()
    market_input = payload["data"]["owner_market_input"]
    assert market_input["regime"] == "trend"
    assert market_input["mapped_family"] == "Trend"
    assert market_input["symbol_preference"] == "SOL/USDT:USDT"
    assert market_input["side"] == "long"
    assert market_input["risk_tier"] == "small"
    assert market_input["note"] == "Owner sees a small trend continuation setup."
    assert market_input["persisted"] is False

    selected = payload["data"]["selected_candidate"]
    assert selected["family"] == "Trend"
    assert selected["carrier_id"] == "TF-001-live-readonly-v0"
    assert selected["scope_review"]["verdict"] == "matched"
    assert selected["scope_review"]["mismatches"] == []
    action_state = payload["data"]["action_state"]
    assert action_state["enabled"] is False
    assert action_state["backend_actionable"] is False
    assert action_state["backend_actionable_only"] is False
    assert action_state["places_order"] is False
    assert payload["data"]["authorization_draft_path"]["creates_authorization"] is False
    assert payload["data"]["final_gate_result"]["frontend_action_enabled"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_budget_recommendation_degrades_without_account_facts(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/budget-recommendation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_model"] == "budget_recommendation"
    data = payload["data"]
    assert data["account_capacity"]["status"] == "degraded"
    assert data["account_capacity"]["account_equity"] is None
    assert data["budget_envelope"]["status"] == "degraded_missing_account_facts"
    assert [item["symbol"] for item in data["recommended_symbols"]] == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    assert data["owner_selection"]["status"] == "not_provided"
    assert "account_equity" in data["missing_facts"]
    assert "fresh_account_facts" in data["missing_facts"]
    blocker_ids = {item["id"] for item in data["blockers"]}
    assert "BUDGET-ACCOUNT-CAPACITY-ACCOUNT-FACTS" in blocker_ids
    assert "BUDGET-ACCOUNT-CAPACITY-FRESHNESS" in blocker_ids
    assert data["budgeted_autonomy_enabled"] is False
    assert data["grants_trading_permission"] is False
    assert data["may_execute_live"] is False
    assert data["frontend_action_enabled"] is False
    assert data["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.account_snapshot_calls == 0
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_budget_recommendation_uses_fresh_read_only_account_capacity(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway(positions=[], normal_orders=[], stop_orders=[])
    _patch_deps(
        monkeypatch,
        exchange=exchange,
        account_snapshot=_FakeAccountSnapshot(),
        order_repo=_FakeOrderRepo([]),
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/budget-recommendation",
            params={"include_exchange": "true", "risk_tier": "tiny"},
        )

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    capacity = data["account_capacity"]
    assert capacity["status"] == "available"
    assert capacity["account_equity"] == "1000"
    assert capacity["available_balance"] == "800"
    assert capacity["max_usable_notional"] == "150"
    envelope = data["budget_envelope"]
    assert envelope["status"] == "available"
    assert envelope["total_budget"] == "20"
    assert envelope["max_notional_per_action"] == "20"
    assert envelope["max_daily_loss"] == "1"
    assert envelope["max_active_positions"] == 1
    assert envelope["max_attempts"] == 1
    assert envelope["max_leverage"] == "1"
    assert envelope["allowed_symbols"] == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    assert envelope["allowed_sides"] == ["long"]
    assert envelope["not_authorization"] is True
    assert envelope["grants_trading_permission"] is False
    assert envelope["action_allowed"] is False
    examples = {item["proposal_kind"]: item for item in data["examples"]}
    assert set(examples) == {"trend_sol", "mean_reversion_eth", "volatility_proposal"}
    trend = examples["trend_sol"]["action_candidate_sizing"]
    assert trend["family"] == "Trend"
    assert trend["symbol"] == "SOL/USDT:USDT"
    assert trend["recommended_max_notional"] == "20"
    assert trend["owner_confirmation_required"] is True
    assert trend["action_allowed"] is False
    mr = examples["mean_reversion_eth"]["generic_action_spec_sizing"]
    assert mr["family"] == "Mean reversion"
    assert mr["symbol"] == "ETH/USDT:USDT"
    assert mr["max_notional"] == "20"
    assert mr["owner_confirmation_required"] is True
    assert mr["places_order"] is False
    assert data["owner_confirmation_requirement"]
    assert data["action_allowed"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert exchange.position_calls == [BNB]
    assert exchange.open_order_calls == [(BNB, None), (BNB, {"stop": True})]
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_strategy_family_admission_scoped_dry_run_examples_work_through_api(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        examples_response = client.get("/api/trading-console/strategy-family-admission-state")
        assert examples_response.status_code == 200
        examples = examples_response.json()["data"]["scoped_dry_run_examples"]
        assert len(examples) == 3

        for example in examples:
            response = client.get(
                "/api/trading-console/strategy-family-admission-state",
                params=example["owner_scope_query"],
            )
            assert response.status_code == 200
            payload = response.json()
            row = next(
                item for item in payload["data"]["families"] if item["family"] == example["family"]
            )
            eligibility = next(
                item
                for item in payload["data"]["live_action_eligibility_matrix"]
                if item["family"] == example["family"]
            )
            checks = {check["code"]: check for check in eligibility["checks"]}
            assert payload["data"]["scope_review"]["verdict"] == example["expected_scope_verdict"]
            assert payload["data"]["scope_review"]["matched_candidate"] is True
            assert row["scope_review"]["verdict"] == example["expected_scope_verdict"]
            assert row["budget_envelope_draft"]["status"] == "scope_complete_dry_run_only"
            assert row["authorization_draft_proposal"]["status"] == (
                example["expected_authorization_draft_status"]
            )
            assert row["protection_plan_draft"]["status"] == "scope_reviewed_draft_only"
            assert row["final_gate_dry_run"]["reason"] == example["expected_final_gate_reason"]
            assert row["action_api_compatibility"]["status"] == example["expected_action_api_status"]
            assert row["pre_execution_blocked_review"]["blocked_reason"] == (
                example["expected_final_gate_reason"]
            )
            assert eligibility["decision"] == example["expected_eligibility_decision"]
            assert checks["owner_scope_complete"]["status"] == "pass"
            assert checks["official_action_api_candidate_supported"]["status"] == (
                "pass" if example["family"] in {"Trend", "Mean reversion"} else "block"
            )
            assert checks["backend_final_gate_actionable"]["status"] == "block"
            assert row["backend_actionable"] is False
            assert row["frontend_action_enabled"] is False
            assert row["authorization_draft_proposal"]["not_authorization"] is True
            assert row["authorization_draft_proposal"]["not_execution_permission"] is True
            assert row["authorization_draft_proposal"]["not_order_permission"] is True
            assert row["budget_envelope_draft"]["action_allowed"] is False
            assert row["budget_envelope_draft"]["creates_authorization"] is False
            assert row["budget_envelope_draft"]["creates_execution_intent"] is False
            assert row["budget_envelope_draft"]["places_order"] is False
            assert row["budget_envelope_draft"]["mutates_pg"] is False
            assert row["action_candidate"]["action_allowed"] is False
            assert row["action_candidate"]["backend_actionable"] is False
            assert row["action_candidate"]["frontend_action_enabled"] is False
            assert row["action_candidate"]["creates_authorization"] is False
            assert row["action_candidate"]["creates_execution_intent"] is False
            assert row["action_candidate"]["places_order"] is False
            assert row["action_candidate"]["mutates_pg"] is False
            assert row["final_gate_dry_run"]["creates_execution_intent"] is False
            assert row["final_gate_dry_run"]["places_order"] is False
            blocker_codes = {item["code"] for item in payload["blockers"]}
            assert "production_scope_incomplete" not in blocker_codes
            if example["family"] in {"Trend", "Mean reversion"}:
                assert f"{row['blocker_record']['id']}-ACTION-API" not in blocker_codes
            else:
                assert f"{row['blocker_record']['id']}-ACTION-API" in blocker_codes
            capital_boundary = next(
                item
                for item in payload["data"]["production_capital_boundary_matrix"]
                if item["family"] == example["family"]
            )
            owner_scope = example["owner_scope_query"]
            assert capital_boundary["status"] == "scope_reviewed_dry_run_only"
            assert capital_boundary["scope_review_verdict"] == example["expected_scope_verdict"]
            assert capital_boundary["required_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
            assert capital_boundary["provided_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
            assert capital_boundary["missing_scope_fields"] == []
            assert capital_boundary["requested_symbol"] == owner_scope["symbol"]
            assert capital_boundary["requested_side"] == owner_scope["side"]
            assert capital_boundary["requested_quantity"] == owner_scope["quantity"]
            assert capital_boundary["requested_max_notional"] == owner_scope["max_notional"]
            assert capital_boundary["requested_leverage"] == owner_scope["leverage"]
            assert capital_boundary["requested_max_attempts"] == owner_scope["max_attempts"]
            assert capital_boundary["requested_protection_mode"] == owner_scope["protection_mode"]
            assert capital_boundary["requested_review_requirement"] == owner_scope[
                "review_requirement"
            ]
            assert capital_boundary["numbers_source"] == "owner_scope_only_no_fabrication"
            assert capital_boundary["scope_expansion_allowed"] is False
            assert capital_boundary["symbol_expansion_allowed"] is False
            assert capital_boundary["side_expansion_allowed"] is False
            assert capital_boundary["quantity_expansion_allowed"] is False
            assert capital_boundary["notional_expansion_allowed"] is False
            assert capital_boundary["leverage_expansion_allowed"] is False
            assert capital_boundary["max_attempts_expansion_allowed"] is False
            assert capital_boundary["action_allowed"] is False
            assert capital_boundary["creates_authorization"] is False
            assert capital_boundary["creates_execution_intent"] is False
            assert capital_boundary["starts_runtime"] is False
            assert capital_boundary["starts_strategy_execution"] is False
            assert capital_boundary["places_order"] is False
            assert capital_boundary["mutates_pg"] is False
            assert capital_boundary["exchange_write_action"] is False
            assert payload["no_action_guarantee"]["places_order"] is False
            assert payload["no_action_guarantee"]["mutates_pg"] is False
            assert payload["no_action_guarantee"]["starts_runtime"] is False

    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_strategy_family_admission_state_reviews_owner_scope_query_without_enabling_action(monkeypatch):
    _configure_auth(monkeypatch)
    exchange = _FakeExchangeGateway()
    _patch_deps(monkeypatch, exchange=exchange)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get(
            "/api/trading-console/strategy-family-admission-state",
            params={
                "family": "Trend",
                "strategy_family_id": "TF-001-live-readonly-v0",
                "carrier_id": "TF-001-live-readonly-v0",
                "symbol": "SOL/USDT:USDT",
                "side": "long",
                "quantity": "0.1",
                "max_notional": "20",
                "leverage": "1",
                "max_attempts": 1,
                "protection_mode": "mandatory_tp_sl",
                "review_requirement": "post_action_review_required_before_promotion",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["scope_review"]["verdict"] == "complete_dry_run_only"
    blocker_codes = {item["code"] for item in payload["blockers"]}
    assert "production_scope_incomplete" not in blocker_codes
    assert "BRC-PROD-ADMIT-20260604-TREND-001-ACTION-API" not in blocker_codes
    completion_by_family = {
        item["family"]: item for item in payload["data"]["family_completion_matrix"]
    }
    assert completion_by_family["Trend"]["completion_status"] == "actionable"
    assert "AuthorizationDraft" in completion_by_family["Trend"]["completed_stages"]
    assert completion_by_family["Trend"]["blocked_stage_statuses"]["BoundedLiveAuthorization"] == (
        "blocked_backend_final_gate"
    )
    assert "scope_review=complete_dry_run_only" in completion_by_family["Trend"]["evidence_refs"]
    eligibility_by_family = {
        item["family"]: item for item in payload["data"]["live_action_eligibility_matrix"]
    }
    trend_eligibility = eligibility_by_family["Trend"]
    trend_checks = {check["code"]: check for check in trend_eligibility["checks"]}
    assert trend_eligibility["eligibility"] == "not_eligible"
    assert trend_eligibility["decision"] == "scope_complete_but_backend_final_gate_blocked"
    assert trend_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_checks["official_action_api_candidate_supported"]["status"] == "pass"
    assert trend_checks["backend_final_gate_actionable"]["status"] == "block"
    risk_control_by_family = {
        item["family"]: item for item in payload["data"]["admission_risk_control_matrix"]
    }
    trend_risk_control = risk_control_by_family["Trend"]
    assert trend_risk_control["scope_review_verdict"] == "complete_dry_run_only"
    assert trend_risk_control["budget_envelope_status"] == "scope_complete_dry_run_only"
    assert trend_risk_control["authorization_draft_status"] == "scope_reviewed_dry_run_only"
    assert trend_risk_control["bounded_live_authorization_status"] == (
        "blocked_backend_final_gate"
    )
    assert trend_risk_control["action_api_status"] == (
        "supported_by_current_official_action_api_but_not_actionable"
    )
    assert trend_risk_control["final_gate_reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend_risk_control["protection_plan_status"] == "scope_reviewed_draft_only"
    assert trend_risk_control["review_contract_status"] == "draft_no_action_evidence"
    assert trend_risk_control["audit_chain_status"] == "gap_open_no_live_action_evidence"
    assert trend_risk_control["backend_actionable"] is False
    assert trend_risk_control["frontend_action_enabled"] is False
    assert trend_risk_control["action_allowed"] is False
    assert trend_risk_control["places_order"] is False
    capital_boundary_by_family = {
        item["family"]: item for item in payload["data"]["production_capital_boundary_matrix"]
    }
    trend_boundary = capital_boundary_by_family["Trend"]
    assert trend_boundary["status"] == "scope_reviewed_dry_run_only"
    assert trend_boundary["scope_review_verdict"] == "complete_dry_run_only"
    assert trend_boundary["required_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
    assert trend_boundary["provided_scope_fields"] == REQUIRED_OWNER_SCOPE_FIELDS
    assert trend_boundary["missing_scope_fields"] == []
    assert trend_boundary["requested_symbol"] == "SOL/USDT:USDT"
    assert trend_boundary["requested_side"] == "long"
    assert trend_boundary["requested_quantity"] == "0.1"
    assert trend_boundary["requested_max_notional"] == "20"
    assert trend_boundary["requested_leverage"] == "1"
    assert trend_boundary["requested_max_attempts"] == 1
    assert trend_boundary["requested_protection_mode"] == "mandatory_tp_sl"
    assert trend_boundary["requested_review_requirement"] == (
        "post_action_review_required_before_promotion"
    )
    assert trend_boundary["numbers_source"] == "owner_scope_only_no_fabrication"
    assert trend_boundary["scope_expansion_allowed"] is False
    assert trend_boundary["symbol_expansion_allowed"] is False
    assert trend_boundary["side_expansion_allowed"] is False
    assert trend_boundary["quantity_expansion_allowed"] is False
    assert trend_boundary["notional_expansion_allowed"] is False
    assert trend_boundary["leverage_expansion_allowed"] is False
    assert trend_boundary["max_attempts_expansion_allowed"] is False
    assert trend_boundary["action_allowed"] is False
    assert trend_boundary["creates_authorization"] is False
    assert trend_boundary["creates_execution_intent"] is False
    assert trend_boundary["starts_runtime"] is False
    assert trend_boundary["starts_strategy_execution"] is False
    assert trend_boundary["places_order"] is False
    assert trend_boundary["mutates_pg"] is False
    assert trend_boundary["exchange_write_action"] is False
    trend_chain = {
        item["stage"]: item
        for item in payload["data"]["full_chain_evidence_matrix"]
        if item["family"] == "Trend"
    }
    assert trend_chain["AuthorizationDraft"]["status"] == "scope_reviewed_dry_run_only"
    assert trend_chain["AuthorizationDraft"]["blocker_ids"] == []
    assert trend_chain["BoundedLiveAuthorization"]["status"] == "blocked_backend_final_gate"
    assert trend_chain["BoundedLiveAuthorization"]["blocker_ids"]
    assert trend_chain["ExecutionIntent"]["status"] == "not_created"
    assert trend_chain["ExecutionIntent"]["places_order"] is False
    assert trend_chain["Entry"]["status"] == "not_executed"
    assert trend_chain["Entry"]["places_order"] is False
    pra_by_family = {
        item["family"]: item for item in payload["data"]["protection_review_audit_matrix"]
    }
    trend_pra = pra_by_family["Trend"]
    assert trend_pra["protection_status"] == "scope_reviewed_draft_only"
    assert "complete_matched_owner_scope" not in trend_pra["missing_protection_fields"]
    assert "take_profit_price" in trend_pra["missing_protection_fields"]
    assert "stop_loss_price" in trend_pra["missing_protection_fields"]
    assert trend_pra["review_status"] == "draft_no_action_evidence"
    assert trend_pra["audit_status"] == "gap_open_no_live_action_evidence"
    assert trend_pra["action_allowed"] is False
    assert trend_pra["creates_order"] is False
    assert trend_pra["records_review"] is False
    assert trend_pra["places_order"] is False
    assert trend_pra["mutates_pg"] is False
    trend_retry_by_id = {
        item["blocker_id"]: item
        for item in payload["data"]["blocker_retry_matrix"]
        if item["family"] == "Trend"
    }
    assert "BRC-PROD-ADMIT-20260604-TREND-001-SCOPE" not in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-ACTION-API" not in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-FINAL-GATE" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-PROTECTION" in trend_retry_by_id
    assert "BRC-PROD-ADMIT-20260604-TREND-001-REVIEW" in trend_retry_by_id
    assert all(item["retry_ready"] is False for item in trend_retry_by_id.values())
    assert all(item["places_order"] is False for item in trend_retry_by_id.values())
    packet_by_family = {
        item["family"]: item for item in payload["data"]["owner_authorization_packet_matrix"]
    }
    trend_packet = packet_by_family["Trend"]
    assert trend_packet["status"] == "scope_reviewed_dry_run_only"
    assert trend_packet["owner_scope_verdict"] == "complete_dry_run_only"
    assert trend_packet["budget_envelope_status"] == "scope_complete_dry_run_only"
    assert trend_packet["authorization_draft_status"] == "scope_reviewed_dry_run_only"
    assert "strategy_family_version_id" not in trend_packet["unresolved_refs"]
    assert "playbook_id" not in trend_packet["unresolved_refs"]
    assert "evidence_packet_id" in trend_packet["unresolved_refs"]
    assert "admission_decision_id" in trend_packet["unresolved_refs"]
    assert trend_packet["not_authorization"] is True
    assert trend_packet["creates_authorization"] is False
    assert trend_packet["creates_execution_intent"] is False
    assert trend_packet["places_order"] is False
    handoff_by_family = {
        item["family"]: item for item in payload["data"]["owner_review_handoff_matrix"]
    }
    trend_handoff = handoff_by_family["Trend"]
    assert trend_handoff["status"] == "review_ready_dry_run_only"
    assert trend_handoff["owner_scope_verdict"] == "complete_dry_run_only"
    assert trend_handoff["budget_envelope_status"] == "scope_complete_dry_run_only"
    assert trend_handoff["authorization_draft_status"] == "scope_reviewed_dry_run_only"
    assert "strategy_family_version_id" not in trend_handoff["unresolved_refs"]
    assert "playbook_id" not in trend_handoff["unresolved_refs"]
    assert "evidence_packet_id" in trend_handoff["unresolved_refs"]
    assert "admission_decision_id" in trend_handoff["unresolved_refs"]
    assert "Owner risk acceptance is created through official API" in (
        trend_handoff["required_before_submit"]
    )
    assert trend_handoff["frontend_action_enabled"] is False
    assert trend_handoff["read_model_submits_authorization"] is False
    assert trend_handoff["creates_authorization"] is False
    assert trend_handoff["creates_execution_intent"] is False
    assert trend_handoff["places_order"] is False
    assert trend_handoff["mutates_pg"] is False
    trend_request_rows = {
        item["draft_name"]: item
        for item in payload["data"]["official_api_request_draft_matrix"]
        if item["family"] == "Trend"
    }
    assert len(trend_request_rows) == 5
    assert trend_request_rows["create_admission_request"]["owner_scope_verdict"] == (
        "complete_dry_run_only"
    )
    assert "strategy_family_version_id" not in trend_request_rows[
        "create_admission_request"
    ]["unresolved_refs"]
    assert "playbook_id" not in trend_request_rows[
        "create_admission_request"
    ]["unresolved_refs"]
    assert "evidence_packet_id" in trend_request_rows[
        "create_admission_request"
    ]["unresolved_refs"]
    assert trend_request_rows["create_admission_request"]["not_submitted"] is True
    assert trend_request_rows["create_admission_request"]["creates_authorization"] is False
    assert trend_request_rows["create_admission_request"]["creates_execution_intent"] is False
    assert trend_request_rows["create_admission_request"]["places_order"] is False
    assert trend_request_rows[
        "operation_preflight_create_gated_trial_from_admission"
    ]["starts_runtime"] is False
    final_gate_by_family = {
        item["family"]: item for item in payload["data"]["final_gate_readiness_matrix"]
    }
    trend_final_gate = final_gate_by_family["Trend"]
    final_gate_checks = {check["code"]: check for check in trend_final_gate["checks"]}
    assert trend_final_gate["status"] == "blocked"
    assert trend_final_gate["readiness_level"] == "scope_reviewed_backend_final_gate_blocked"
    assert trend_final_gate["final_gate_reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend_final_gate["owner_scope_verdict"] == "complete_dry_run_only"
    assert final_gate_checks["owner_scope_complete"]["status"] == "pass"
    assert final_gate_checks["official_action_api_candidate_supported"]["status"] == "pass"
    assert final_gate_checks["backend_final_gate_actionable"]["status"] == "block"
    assert "BoundedLiveAuthorization" in trend_final_gate["blocking_stages"]
    assert "ExecutionIntent" in trend_final_gate["blocking_stages"]
    assert trend_final_gate["backend_actionable"] is False
    assert trend_final_gate["frontend_action_enabled"] is False
    assert trend_final_gate["may_execute_live"] is False
    assert trend_final_gate["creates_authorization"] is False
    assert trend_final_gate["creates_execution_intent"] is False
    assert trend_final_gate["starts_runtime"] is False
    assert trend_final_gate["starts_strategy_execution"] is False
    assert trend_final_gate["places_order"] is False
    assert trend_final_gate["mutates_pg"] is False
    assert trend_final_gate["exchange_write_action"] is False
    decision_by_family = {
        item["family"]: item for item in payload["data"]["production_action_decision_matrix"]
    }
    trend_decision = decision_by_family["Trend"]
    assert trend_decision["decision"] == "do_not_execute"
    assert trend_decision["selection_status"] == "not_selected_for_live_action"
    assert trend_decision["reason"] == "backend_final_gate_not_actionable"
    assert trend_decision["owner_scope_verdict"] == "complete_dry_run_only"
    assert trend_decision["final_gate_reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert "final_gate_actionable_true" in trend_decision["missing_evidence"]
    assert "execution_intent" in trend_decision["missing_evidence"]
    assert trend_decision["live_action_taken"] is False
    assert trend_decision["backend_actionable"] is False
    assert trend_decision["frontend_action_enabled"] is False
    assert trend_decision["may_execute_live"] is False
    assert trend_decision["creates_authorization"] is False
    assert trend_decision["creates_execution_intent"] is False
    assert trend_decision["starts_runtime"] is False
    assert trend_decision["starts_strategy_execution"] is False
    assert trend_decision["places_order"] is False
    assert trend_decision["mutates_pg"] is False
    assert trend_decision["exchange_write_action"] is False
    acceptance_by_item = {
        item["item"]: item for item in payload["data"]["acceptance_evidence_matrix"]
    }
    assert acceptance_by_item["owner_risk_scope_review"]["status"] == "PASS_WITH_CONSTRAINT"
    assert "owner_review_handoff_matrix" in acceptance_by_item[
        "owner_risk_scope_review"
    ]["evidence_refs"]
    assert acceptance_by_item["official_action_api_candidate_support"]["status"] == "BLOCKED"
    assert acceptance_by_item["backend_final_gate_preflight"]["status"] == "BLOCKED"
    assert acceptance_by_item["live_action_execution"]["status"] == "BLOCKED"
    audit_by_requirement = {
        item["requirement_id"]: item
        for item in payload["data"]["objective_acceptance_audit_matrix"]
    }
    assert audit_by_requirement["production_capital_boundary"]["status"] == (
        "PASS_WITH_CONSTRAINT"
    )
    assert audit_by_requirement["live_action_decision"]["status"] == "BLOCKED"
    assert "scope_review.verdict=complete_dry_run_only" in audit_by_requirement[
        "production_capital_boundary"
    ]["evidence_refs"]
    assert "production_action_decision_matrix" in audit_by_requirement[
        "live_action_decision"
    ]["evidence_refs"]
    assert audit_by_requirement["live_action_decision"]["places_order"] is False
    assert audit_by_requirement["live_action_decision"]["mutates_pg"] is False
    bridge_statuses = {
        item["bridge_method"]: item for item in payload["data"]["bridge_artifact_statuses"]
    }
    assert bridge_statuses["BudgetEnvelopeDraft"]["row_statuses"]["Trend"] == (
        "scope_complete_dry_run_only"
    )
    assert bridge_statuses["FinalGateDryRun"]["row_statuses"]["Trend"] == "blocked"
    trend = next(item for item in payload["data"]["families"] if item["family"] == "Trend")
    assert trend["scope_review"]["verdict"] == "complete_dry_run_only"
    assert trend["budget_envelope_draft"]["status"] == "scope_complete_dry_run_only"
    assert trend["budget_envelope_draft"]["scope"]["symbol"] == "SOL/USDT:USDT"
    assert trend["budget_envelope_draft"]["provided_scope_fields"] == [
        "symbol",
        "side",
        "quantity",
        "max_notional",
        "leverage",
        "max_attempts",
        "protection_mode",
        "review_requirement",
    ]
    assert trend["budget_envelope_draft"]["missing_scope_fields"] == []
    assert trend["budget_envelope_draft"]["quantity"] == "0.1"
    assert trend["budget_envelope_draft"]["max_notional"] == "20"
    assert trend["budget_envelope_draft"]["leverage"] == "1"
    assert trend["budget_envelope_draft"]["max_attempts"] == 1
    assert trend["budget_envelope_draft"]["protection_mode"] == "mandatory_tp_sl"
    assert trend["budget_envelope_draft"]["review_requirement"] == (
        "post_action_review_required_before_promotion"
    )
    complete_budget_checks = {
        check["code"]: check for check in trend["budget_envelope_draft"]["validation_checks"]
    }
    assert complete_budget_checks["owner_scope_complete"]["status"] == "pass"
    assert complete_budget_checks["candidate_scope_matched"]["status"] == "pass"
    assert complete_budget_checks["numbers_source_owner_supplied"]["status"] == "pass"
    assert trend["budget_envelope_draft"]["action_allowed"] is False
    assert trend["budget_envelope_draft"]["places_order"] is False
    assert trend["authorization_draft_proposal"]["status"] == "scope_reviewed_dry_run_only"
    assert trend["authorization_draft_proposal"]["scope"]["symbol"] == "SOL/USDT:USDT"
    assert trend["authorization_draft_proposal"]["budget_envelope"]["quantity"] == "0.1"
    assert trend["authorization_draft_proposal"]["budget_envelope"]["action_allowed"] is False
    assert trend["protection_plan_draft"]["status"] == "scope_reviewed_draft_only"
    assert trend["protection_plan_draft"]["scope"]["symbol"] == "SOL/USDT:USDT"
    assert "complete_matched_owner_scope" not in trend["protection_plan_draft"]["missing_fields"]
    assert "take_profit_price" in trend["protection_plan_draft"]["missing_fields"]
    trend_protection_checks = {
        check["code"]: check for check in trend["protection_plan_draft"]["validation_checks"]
    }
    assert trend_protection_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_protection_checks["exchange_protection_orders_created"]["status"] == "not_created"
    assert trend["protection_plan_draft"]["places_order"] is False
    assert trend["authorization_draft_proposal"]["protection_plan"]["status"] == (
        "scope_reviewed_draft_only"
    )
    assert trend["authorization_draft_proposal"]["official_api_transition_plan"][
        "authorization_endpoint"
    ] == "deferred_until_backend_action_contract"
    assert trend["authorization_draft_proposal"]["not_authorization"] is True
    assert trend["final_gate_dry_run"]["reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    assert trend["pre_execution_blocked_review"]["blocked_reason"] == (
        "backend_final_gate_requires_authorization_and_live_preflight"
    )
    trend_pre_execution_checks = {
        check["code"]: check for check in trend["pre_execution_blocked_review"]["checks"]
    }
    assert trend_pre_execution_checks["owner_scope_complete"]["status"] == "pass"
    assert trend_pre_execution_checks["official_action_api_candidate_supported"]["status"] == "pass"
    assert trend["final_gate_dry_run"]["gates"][0] == {
        "code": "owner_scope_complete",
        "status": "pass",
    }
    assert trend["final_gate_dry_run"]["gates"][1] == {
        "code": "backend_final_gate_actionable",
        "status": "block",
    }
    assert trend["final_gate_dry_run"]["gates"][2] == {
        "code": "official_action_api_candidate_supported",
        "status": "pass",
    }
    assert trend["action_api_compatibility"]["compatible"] is True
    assert trend["action_candidate"]["candidate_carrier_id"] == "TF-001-live-readonly-v0"
    assert trend["action_candidate"]["action_allowed"] is False
    assert "complete_matched_owner_scope_required" not in trend["action_candidate"]["blockers"]
    assert "candidate_carrier_not_supported_by_owner_trial_flow" not in trend["action_candidate"]["blockers"]
    assert "backend_final_gate_actionable_true_required" in trend["action_candidate"]["blockers"]
    assert trend["admission_verdict"]["verdict"] == "blocked_backend_final_gate"
    assert trend["admission_verdict"]["may_execute_live"] is False
    assert "AuthorizationDraft" in trend["admission_verdict"]["completed_stages"]
    assert "BoundedLiveAuthorization" in trend["admission_verdict"]["blocked_stages"]
    trend_gate_blocker_ids = {record["id"] for record in trend["gate_blocker_records"]}
    assert f"{trend['blocker_record']['id']}-SCOPE" not in trend_gate_blocker_ids
    assert f"{trend['blocker_record']['id']}-ACTION-API" not in trend_gate_blocker_ids
    assert f"{trend['blocker_record']['id']}-FINAL-GATE" in trend_gate_blocker_ids
    admission_request_draft = next(
        draft for draft in trend["api_request_drafts"] if draft["name"] == "create_admission_request"
    )
    assert admission_request_draft["payload_template"]["trial_env"] == "live"
    assert admission_request_draft["payload_template"]["account_facts_snapshot_json"]["owner_scope"][
        "symbol"
    ] == "SOL/USDT:USDT"
    assert "evidence_packet_id" in admission_request_draft["unresolved_refs"]
    assert admission_request_draft["not_submitted"] is True
    assert trend["backend_actionable"] is False
    assert trend["frontend_action_enabled"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False
    assert exchange.open_order_calls == []
    assert exchange.position_calls == []
    assert exchange.place_calls == 0
    assert exchange.cancel_calls == 0


def test_authorization_state_degraded_path_keeps_future_action_slots(monkeypatch):
    _configure_auth(monkeypatch)
    _patch_deps(monkeypatch, exchange=_FakeExchangeGateway())
    from src.interfaces import api_trading_console as trading_console_module
    from src.interfaces.api import app

    monkeypatch.setattr(trading_console_module, "_owner_trial_flow_service", lambda: None)

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.get("/api/trading-console/authorization-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "unknown"
    assert payload["data"]["is_actionable"] is False
    assert payload["data"]["future_action_slots"] == {
        "void_authorization": "deferred_not_implemented",
        "cancel_authorization": "deferred_not_implemented",
    }
    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["mutates_pg"] is False


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
        "/api/trading-console/strategy-family-admission-state",
        "/api/trading-console/action-entry-readiness",
        "/api/trading-console/owner-action-flow",
        "/api/trading-console/budget-recommendation",
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
