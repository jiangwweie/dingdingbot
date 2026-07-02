"""Tests for TC-TINY-001D-1A: Controlled Synthetic Signal Injection Mechanism.

Verifies all 10 gate checks, once-per-session enforcement, trace emission,
and bound enforcement for the POST /api/runtime/test/smoke/execute-controlled-entry
endpoint.
"""
from __future__ import annotations

import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.decision_trace import TraceService
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, OrderStrategy, SignalResult
from src.interfaces import api as api_module
from src.interfaces.api_console_runtime import router as runtime_router


# ---- helpers ----

def _make_signal(**overrides) -> SignalResult:
    defaults = dict(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        direction=Direction.LONG,
        entry_price=Decimal("2100"),
        suggested_stop_loss=Decimal("2079"),
        suggested_position_size=Decimal("0.01"),
        current_leverage=1,
        tags=[],
        risk_reward_info="test",
        status="PENDING",
        strategy_name="controlled_test_smoke",
    )
    defaults.update(overrides)
    return SignalResult(**defaults)


def _make_intent(signal: SignalResult | None = None, status=ExecutionIntentStatus.SUBMITTED):
    return ExecutionIntent(
        id="intent_test001",
        signal_id="sig_test001",
        signal=signal or _make_signal(),
        status=status,
    )


def _make_config_provider(profile_name="sim1_eth_runtime", exchange_testnet=True):
    environment = SimpleNamespace(exchange_testnet=exchange_testnet)
    resolved = SimpleNamespace(
        profile_name=profile_name,
        environment=environment,
    )
    return SimpleNamespace(resolved_config=resolved)


def _make_orchestrator(
    intent: ExecutionIntent | None = None,
    protection_blocks: dict | None = None,
    circuit_breakers: set | None = None,
):
    orch = MagicMock()
    orch.execute_signal = AsyncMock(return_value=intent or _make_intent())
    orch.list_protection_health_blocks = MagicMock(return_value=protection_blocks or {})
    orch.is_symbol_blocked = MagicMock(
        side_effect=lambda sym: sym in (circuit_breakers or set())
    )
    return orch


def _make_gateway(price=Decimal("2100")):
    gw = MagicMock()
    gw.fetch_ticker_price = AsyncMock(return_value=price)
    return gw


def _make_guard(armed=True):
    svc = MagicMock()
    svc.is_armed = MagicMock(return_value=armed)
    return svc


def _make_gks(active=False):
    svc = MagicMock()
    svc.is_active = MagicMock(return_value=active)
    return svc


def _make_trace():
    return MagicMock(spec=TraceService)


def _build_app(**api_overrides):
    """Create isolated FastAPI app with mocked api module attributes."""
    app = FastAPI()
    app.include_router(runtime_router)
    return app


def _patch_api_module(monkeypatch, **attrs):
    """Set attributes on the api module for the test."""
    for name, value in attrs.items():
        monkeypatch.setattr(api_module, name, value)


# ---- Gate 1: RUNTIME_TEST_SIGNAL_INJECTION_ENABLED ----

class TestGate1InjectionEnabled:
    def test_returns_403_when_disabled(self, monkeypatch):
        monkeypatch.delenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", raising=False)
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 403
        assert "injection disabled" in resp.json()["detail"]

    def test_returns_403_when_empty(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 403


# ---- Gate 2: RUNTIME_CONTROL_API_ENABLED ----

class TestGate2ControlApiEnabled:
    def test_returns_403_when_control_disabled(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.delenv("RUNTIME_CONTROL_API_ENABLED", raising=False)
        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 403
        assert "control API disabled" in resp.json()["detail"]


# ---- Gate 3: EXCHANGE_TESTNET ----

class TestGate3ExchangeTestnet:
    def test_returns_403_when_testnet_false(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider(exchange_testnet=False)
        _patch_api_module(monkeypatch, _runtime_config_provider=config_provider)
        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 403
        assert "EXCHANGE_TESTNET=true" in resp.json()["detail"]


# ---- Gate 4: Profile ----

class TestGate4Profile:
    def test_returns_403_when_wrong_profile(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider(profile_name="wrong_profile")
        _patch_api_module(monkeypatch, _runtime_config_provider=config_provider)
        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 403
        assert "sim1_eth_runtime" in resp.json()["detail"]


# ---- Gate 5: Parameter bounds (server-side enforced) ----

class TestGate5ParameterBounds:
    def test_endpoint_accepts_no_body(self, monkeypatch):
        """Verify endpoint works with no request body (all params server-derived)."""
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway()
        guard = _make_guard(armed=True)
        gks = _make_gks(active=False)
        trace = _make_trace()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=guard,
            _global_kill_switch_service=gks,
            _trace_service=trace,
        )
        # Reset module-level guard
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 200

    def test_request_body_attempting_override_is_rejected(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post(
                "/api/runtime/test/smoke/execute-controlled-entry",
                json={
                    "symbol": "BTC/USDT:USDT",
                    "direction": "SHORT",
                    "amount": "1",
                    "entry_price": "1",
                    "stop_loss": "0.5",
                },
            )

        assert resp.status_code == 400
        assert "Request body is not accepted" in resp.json()["detail"]
        orch.execute_signal.assert_not_called()


# ---- Gate 6: Once-per-session ----

class TestGate6OncePerSession:
    def test_returns_409_on_repeated_call(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway()
        guard = _make_guard(armed=True)
        gks = _make_gks(active=False)
        trace = _make_trace()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=guard,
            _global_kill_switch_service=gks,
            _trace_service=trace,
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp1 = client.post("/api/runtime/test/smoke/execute-controlled-entry")
            assert resp1.status_code == 200

            resp2 = client.post("/api/runtime/test/smoke/execute-controlled-entry")
            assert resp2.status_code == 409
            assert "already executed" in resp2.json()["detail"]

    def test_once_per_session_locks_after_blocked_execution_attempt(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        blocked_intent = _make_intent(status=ExecutionIntentStatus.BLOCKED)
        blocked_intent.blocked_reason = "CAPITAL_PROTECTION_DENY"
        orch = _make_orchestrator(intent=blocked_intent)
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=_make_config_provider(),
            _execution_orchestrator=orch,
            _exchange_gateway=_make_gateway(),
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp1 = client.post("/api/runtime/test/smoke/execute-controlled-entry")
            resp2 = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp1.status_code == 200
        assert resp1.json()["status"] == "blocked"
        assert resp1.json()["attempt_locked"] is True
        assert resp2.status_code == 409
        assert orch.execute_signal.call_count == 1


# ---- Gate 7a: Startup guard not armed ----

class TestGate7aStartupGuard:
    def test_returns_409_when_guard_not_armed(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        guard = _make_guard(armed=False)
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=guard,
            _global_kill_switch_service=_make_gks(active=False),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 409
        assert "startup guard not armed" in resp.json()["detail"]

    def test_returns_409_when_guard_service_missing(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=None,
            _global_kill_switch_service=_make_gks(active=False),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 409
        assert "startup guard not armed" in resp.json()["detail"]


# ---- Gate 7b: GKS active ----

class TestGate7bGKS:
    def test_returns_409_when_gks_active(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=True),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 409
        assert "kill switch active" in resp.json()["detail"]

    def test_returns_503_when_gks_service_missing(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        orch = _make_orchestrator()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=_make_config_provider(),
            _execution_orchestrator=orch,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=None,
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp.status_code == 503
        assert "GKS_SERVICE_UNAVAILABLE" in resp.json()["detail"]
        orch.execute_signal.assert_not_called()


# ---- Gate 7c: Protection-health block ----

class TestGate7cProtectionHealth:
    def test_returns_409_when_protection_health_blocks_symbol(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator(
            protection_blocks={"ETH/USDT:USDT": {"reason_code": "PROTECTION_MISSING_EXCHANGE_SL"}},
        )
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 409
        assert "protection-health block" in resp.json()["detail"]


# ---- Gate 7d: Circuit breaker ----

class TestGate7dCircuitBreaker:
    def test_returns_409_when_circuit_breaker_active(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator(circuit_breakers={"ETH/USDT:USDT"})
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 409
        assert "circuit breaker" in resp.json()["detail"]


# ---- Valid call: calls orchestrator exactly once ----

class TestValidCall:
    def test_valid_call_calls_execute_signal_once(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway(price=Decimal("2124.50"))
        trace = _make_trace()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=trace,
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 200
        assert orch.execute_signal.call_count == 1
        assert resp.json()["attempt_locked"] is True

    def test_valid_call_returns_intent_fields(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway(price=Decimal("2124.50"))
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        body = resp.json()
        assert body["intent_id"] == "intent_test001"
        assert body["signal_id"] == "sig_test001"
        assert body["testnet"] is True
        assert body["profile"] == "sim1_eth_runtime"
        assert Decimal(body["amount"]) == Decimal("0.01")
        assert Decimal(body["entry_price"]) == Decimal("2124.50")
        assert Decimal(body["notional"]) == Decimal("21.2450")
        assert Decimal(body["min_notional"]) == Decimal("20")

    def test_valid_call_passes_correct_signal_to_orchestrator(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway(price=Decimal("2100"))
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            client.post("/api/runtime/test/smoke/execute-controlled-entry")

        call_args = orch.execute_signal.call_args
        signal_arg = call_args[0][0]
        strategy_arg = call_args[0][1]
        assert signal_arg.symbol == "ETH/USDT:USDT"
        assert signal_arg.direction == Direction.LONG
        assert signal_arg.suggested_position_size == Decimal("0.01")
        assert signal_arg.suggested_position_size <= Decimal("0.01")
        assert signal_arg.strategy_name == "controlled_test_smoke"
        assert strategy_arg.name == "controlled_test_smoke/sim1_eth_runtime"
        assert strategy_arg.tp_targets == [Decimal("1.0"), Decimal("3.5")]
        assert strategy_arg.initial_stop_loss_rr == Decimal("-1.0")

    def test_notional_below_min_notional_blocks_before_execute_signal(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        orch = _make_orchestrator()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=_make_config_provider(),
            _execution_orchestrator=orch,
            _exchange_gateway=_make_gateway(price=Decimal("1000")),
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp.status_code == 409
        assert "below min_notional" in resp.json()["detail"]
        orch.execute_signal.assert_not_called()

    def test_endpoint_uses_execute_signal_and_does_not_call_order_mutations(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        orch = _make_orchestrator()
        order_lifecycle = MagicMock()
        order_lifecycle.create_order = MagicMock()
        gateway = _make_gateway(price=Decimal("2100"))
        gateway.create_order = AsyncMock()
        gateway.cancel_order = AsyncMock()
        gateway.edit_order = AsyncMock()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=_make_config_provider(),
            _execution_orchestrator=orch,
            _exchange_gateway=gateway,
            _order_lifecycle_service=order_lifecycle,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp.status_code == 200
        orch.execute_signal.assert_awaited_once()
        order_lifecycle.create_order.assert_not_called()
        gateway.create_order.assert_not_called()
        gateway.cancel_order.assert_not_called()
        gateway.edit_order.assert_not_called()


# ---- Trace emission ----

class TestTraceEmission:
    def test_trace_emitted_on_success(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator()
        gw = _make_gateway(price=Decimal("2100"))
        trace = _make_trace()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=trace,
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert trace.emit_risk_decision.call_count == 1
        call_kwargs = trace.emit_risk_decision.call_args[1]
        assert call_kwargs["event_type"] == "control.test_signal_injection"
        assert call_kwargs["decision"] == "executed"
        assert call_kwargs["reason"] == "controlled_test_signal_injection"
        meta = call_kwargs["metadata"]
        assert meta["symbol"] == "ETH/USDT:USDT"
        assert meta["direction"] == "LONG"
        assert meta["testnet"] is True
        assert meta["source"] == "runtime_test_endpoint"
        assert meta["profile"] == "sim1_eth_runtime"
        assert meta["attempt_locked"] is True
        assert "entry_price" in meta
        assert "stop_loss" in meta

    def test_trace_failure_does_not_fail_endpoint_after_execute_signal(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        orch = _make_orchestrator()
        trace = _make_trace()
        trace.emit_risk_decision.side_effect = RuntimeError("trace sink down")
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=_make_config_provider(),
            _execution_orchestrator=orch,
            _exchange_gateway=_make_gateway(),
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=trace,
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp.status_code == 200
        orch.execute_signal.assert_awaited_once()
        trace.emit_risk_decision.assert_called_once()

    def test_set_dependencies_trace_service_is_used_by_endpoint(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        orch = _make_orchestrator()
        trace = _make_trace()
        api_module.set_dependencies(
            repository=None,
            exchange_gateway=_make_gateway(),
            runtime_config_provider=_make_config_provider(),
            order_lifecycle_service=None,
            global_kill_switch_service=_make_gks(active=False),
            startup_trading_guard_service=_make_guard(armed=True),
            trace_service=trace,
        )
        monkeypatch.setattr(api_module, "_execution_orchestrator", orch)
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")

        assert resp.status_code == 200
        trace.emit_risk_decision.assert_called_once()


# ---- Protection-health empty not blocked ----

class TestProtectionHealthEmpty:
    def test_empty_protection_blocks_passes(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator(protection_blocks={})
        gw = _make_gateway()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 200


# ---- Circuit breaker for different symbol not blocked ----

class TestCircuitBreakerDifferentSymbol:
    def test_circuit_breaker_for_other_symbol_does_not_block(self, monkeypatch):
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        config_provider = _make_config_provider()
        orch = _make_orchestrator(circuit_breakers={"BTC/USDT:USDT"})
        gw = _make_gateway()
        _patch_api_module(
            monkeypatch,
            _runtime_config_provider=config_provider,
            _execution_orchestrator=orch,
            _exchange_gateway=gw,
            _startup_trading_guard_service=_make_guard(armed=True),
            _global_kill_switch_service=_make_gks(active=False),
            _trace_service=_make_trace(),
        )
        import src.interfaces.api_console_runtime as crt
        crt._CONTROLLED_ENTRY_EXECUTED = False

        app = _build_app()
        with TestClient(app) as client:
            resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
        assert resp.status_code == 200


# ---- No live key / no live profile path ----

class TestNoLivePath:
    def test_endpoint_requires_sim1_profile(self, monkeypatch):
        """The endpoint rejects any profile other than sim1_eth_runtime."""
        monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
        monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
        for profile in ["live_eth_runtime", "paper_eth_runtime", "testnet_main"]:
            config_provider = _make_config_provider(profile_name=profile)
            _patch_api_module(monkeypatch, _runtime_config_provider=config_provider)
            import src.interfaces.api_console_runtime as crt
            crt._CONTROLLED_ENTRY_EXECUTED = False

            app = _build_app()
            with TestClient(app) as client:
                resp = client.post("/api/runtime/test/smoke/execute-controlled-entry")
            assert resp.status_code == 403, f"Profile {profile} should be rejected"
