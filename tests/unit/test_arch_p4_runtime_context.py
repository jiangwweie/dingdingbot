from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.runtime_context import RuntimeContext
from src.application.startup_trading_guard import StartupTradingGuardService
from src.interfaces.api_console_runtime import router as runtime_router


def test_runtime_context_supports_legacy_api_attribute_names():
    gateway = object()
    signal_repo = object()
    context = RuntimeContext(exchange_gateway=gateway, signal_repository=signal_repo)

    assert context.exchange_gateway is gateway
    assert context._exchange_gateway is gateway
    assert context._signal_repo is signal_repo
    assert context._repository is signal_repo
    assert context._account_getter() is None


@pytest.mark.asyncio
async def test_runtime_context_start_and_shutdown_marks_owner_and_blocks_guard():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="startup checked")
    event = SimpleNamespace(is_set=False)
    event.set = lambda: setattr(event, "is_set", True)
    context = RuntimeContext(
        shutdown_event=event,
        startup_trading_guard_service=guard,
    )

    await context.start()
    await context.shutdown("unit_shutdown")

    state = guard.get_state()
    assert context.started is False
    assert context.shutdown_source == "unit_shutdown"
    assert event.is_set is True
    assert state.armed is False
    assert state.reason == "RUNTIME_SHUTDOWN_RESET"


def test_bind_runtime_context_sets_app_state_and_api_compat_globals():
    import src.interfaces.api as api_module

    target_app = FastAPI()
    gateway = SimpleNamespace(get_account_snapshot=lambda: {"ok": True})
    guard = StartupTradingGuardService()
    context = RuntimeContext(
        exchange_gateway=gateway,
        startup_trading_guard_service=guard,
    )

    try:
        api_module.bind_runtime_context(context, target_app)

        assert api_module.get_runtime_context() is context
        assert target_app.state.runtime is context
        assert api_module._exchange_gateway is gateway
        assert api_module._startup_trading_guard_service is guard
    finally:
        api_module.clear_runtime_context(target_app)


def test_clear_runtime_context_clears_api_compat_globals():
    import src.interfaces.api as api_module

    target_app = FastAPI()
    gateway = SimpleNamespace(get_account_snapshot=lambda: {"ok": True})
    guard = StartupTradingGuardService()
    orchestrator = object()
    context = RuntimeContext(
        exchange_gateway=gateway,
        startup_trading_guard_service=guard,
        execution_orchestrator=orchestrator,
    )

    api_module.bind_runtime_context(context, target_app)
    api_module.clear_runtime_context(target_app)

    assert api_module.get_runtime_context() is None
    assert target_app.state.runtime is None
    assert api_module._exchange_gateway is None
    assert api_module._startup_trading_guard_service is None
    assert api_module._execution_orchestrator is None


def test_console_runtime_reads_services_from_bound_runtime_context():
    import src.interfaces.api as api_module

    guard = StartupTradingGuardService()
    context = RuntimeContext(startup_trading_guard_service=guard)
    app = FastAPI()
    app.include_router(runtime_router)

    try:
        api_module.bind_runtime_context(context, app)
        with TestClient(app) as client:
            response = client.get("/api/runtime/control/startup-trading-guard")

        assert response.status_code == 200
        assert response.json()["armed"] is False
    finally:
        api_module.clear_runtime_context(app)


def test_console_runtime_reads_signal_repo_from_bound_runtime_context():
    import src.interfaces.api as api_module

    class FakeSignalRepo:
        async def get_signals(self, symbol=None, limit=100):
            return {
                "total": 1,
                "data": [
                    {
                        "id": "sig-1",
                        "symbol": "ETH/USDT:USDT",
                        "timeframe": "1h",
                        "direction": "LONG",
                        "strategy_name": "arch-test",
                        "score": 1,
                        "created_at": 1,
                        "status": "PENDING",
                    }
                ],
            }

    context = RuntimeContext(signal_repository=FakeSignalRepo())
    app = FastAPI()
    app.include_router(runtime_router)

    try:
        api_module.bind_runtime_context(context, app)
        with TestClient(app) as client:
            response = client.get("/api/runtime/signals")

        assert response.status_code == 200
        assert response.json()["signals"][0]["signal_id"] == "sig-1"
    finally:
        api_module.clear_runtime_context(app)
