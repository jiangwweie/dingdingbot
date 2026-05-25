from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.domain.models import SignalResult
from src.interfaces import api as api_module
from src.interfaces.api_console_runtime import router as runtime_router


ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"
PROFILE = "phase5e_btc_eth_testnet_runtime"


def _app():
    app = FastAPI()
    app.include_router(runtime_router)
    return app


def _patch_api_module(monkeypatch, **attrs):
    for name, value in attrs.items():
        monkeypatch.setattr(api_module, name, value)


def _config_provider(*, profile=PROFILE, symbols=(ETH, BTC), testnet=True):
    resolved = SimpleNamespace(
        profile_name=profile,
        environment=SimpleNamespace(exchange_testnet=testnet),
        market=SimpleNamespace(symbols=list(symbols)),
    )
    return SimpleNamespace(resolved_config=resolved)


def _intent(symbol=ETH):
    return ExecutionIntent(
        id=f"intent-{symbol.split('/')[0].lower()}",
        signal_id=f"sig-{symbol.split('/')[0].lower()}",
        signal=SignalResult(
            symbol=symbol,
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("100"),
            suggested_stop_loss=Decimal("99"),
            suggested_position_size=Decimal("0.001"),
            current_leverage=1,
            tags=[],
            risk_reward_info="phase5e-test",
            status="PENDING",
            strategy_name="phase5e_test",
        ),
        status=ExecutionIntentStatus.SUBMITTED,
    )


def _orchestrator():
    orch = MagicMock()
    orch.execute_signal = AsyncMock(side_effect=lambda signal, strategy: _intent(signal.symbol))
    orch.list_protection_health_blocks = MagicMock(return_value={})
    orch.is_symbol_blocked = MagicMock(return_value=False)
    close_order = Order(
        id="exit-phase5e",
        signal_id="sig-btc",
        exchange_order_id="ex-close",
        symbol=BTC,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.EXIT,
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0.001"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
        reduce_only=True,
        average_exec_price=Decimal("110000"),
    )
    orch.execute_controlled_close = AsyncMock(
        return_value={"close_order": close_order, "terminalized_protection_orders": []}
    )
    return orch


def _gateway(
    price=Decimal("2100"),
    min_notional=Decimal("20"),
    *,
    positions=None,
    normal_open_orders=None,
    conditional_open_orders=None,
):
    gw = MagicMock()
    gw.fetch_ticker_price = AsyncMock(return_value=price)
    gw.get_min_notional = MagicMock(return_value=min_notional)

    async def fetch_positions(symbol=None):
        return list((positions or {}).get(symbol, []))

    async def fetch_open_orders(symbol, params=None):
        if params and params.get("stop"):
            return list((conditional_open_orders or {}).get(symbol, []))
        return list((normal_open_orders or {}).get(symbol, []))

    gw.fetch_positions = AsyncMock(side_effect=fetch_positions)
    gw.fetch_open_orders = AsyncMock(side_effect=fetch_open_orders)
    return gw


def _guard(armed=True):
    svc = MagicMock()
    svc.is_armed = MagicMock(return_value=armed)
    return svc


def _gks(active=False):
    svc = MagicMock()
    svc.is_active = MagicMock(return_value=active)
    return svc


def _position(symbol=BTC, qty=Decimal("0.001")):
    return SimpleNamespace(
        id=f"pos-{symbol}",
        signal_id=f"sig-{symbol}",
        symbol=symbol,
        current_qty=qty,
    )


def _position_repo(active=None):
    repo = MagicMock()

    async def list_active(*, symbol=None, limit=10):
        positions = list(active or [])
        if symbol is not None:
            positions = [position for position in positions if position.symbol == symbol]
        return positions[:limit]

    repo.list_active = AsyncMock(side_effect=list_active)
    return repo


def _order_repo(open_orders=None):
    repo = MagicMock()

    async def get_open_orders(symbol=None):
        orders = list(open_orders or [])
        if symbol is not None:
            orders = [order for order in orders if order.symbol == symbol]
        return orders

    repo.get_open_orders = AsyncMock(side_effect=get_open_orders)
    return repo


@pytest.fixture(autouse=True)
def _reset_phase5e_guards(monkeypatch):
    import src.interfaces.api_console_runtime as mod

    mod._CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL.clear()
    mod._CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL.clear()
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    yield
    mod._CONTROLLED_ENTRY_EXECUTED_BY_SYMBOL.clear()
    mod._CONTROLLED_CLOSE_EXECUTED_BY_SYMBOL.clear()


def test_phase5e_eth_entry_uses_fixed_symbol_profile_and_caps(monkeypatch):
    orch = _orchestrator()
    gw = _gateway(price=Decimal("2100"), min_notional=Decimal("20"))
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _exchange_gateway=gw,
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/eth/execute-controlled-entry")

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == ETH
    assert body["profile"] == PROFILE
    assert Decimal(body["amount"]) == Decimal("0.01")
    signal_arg = orch.execute_signal.call_args[0][0]
    strategy_arg = orch.execute_signal.call_args[0][1]
    assert signal_arg.symbol == ETH
    assert signal_arg.suggested_position_size == Decimal("0.01")
    assert strategy_arg.name == f"phase5e_controlled_test_smoke/{PROFILE}/{ETH}"


def test_phase5e_btc_entry_enforces_max_notional_cap(monkeypatch):
    orch = _orchestrator()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(price=Decimal("140000"), min_notional=Decimal("100")),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/btc/execute-controlled-entry")

    assert resp.status_code == 409
    assert "above Phase 5E cap" in resp.json()["detail"]
    orch.execute_signal.assert_not_called()


def test_phase5e_entry_skips_btc_when_min_notional_exceeds_cap(monkeypatch):
    orch = _orchestrator()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(price=Decimal("110000"), min_notional=Decimal("251")),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/btc/execute-controlled-entry")

    assert resp.status_code == 409
    assert "min_notional exceeds symbol cap" in resp.json()["detail"]
    orch.execute_signal.assert_not_called()


def test_phase5e_entry_requires_exact_btc_eth_market_scope(monkeypatch):
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(symbols=(ETH,)),
        _execution_orchestrator=_orchestrator(),
        _exchange_gateway=_gateway(),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/eth/execute-controlled-entry")

    assert resp.status_code == 403
    assert "market symbols exactly" in resp.json()["detail"]


def test_phase5e_feasibility_endpoint_reports_btc_ok_after_owner_cap_increase(monkeypatch):
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _exchange_gateway=_gateway(price=Decimal("77550.6"), min_notional=Decimal("100")),
    )

    with TestClient(_app()) as client:
        resp = client.get("/api/runtime/test/phase5e/btc/feasibility")

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == BTC
    assert body["feasible"] is True
    assert body["reason"] == "OK"
    assert Decimal(body["amount"]) == Decimal("0.002")
    assert Decimal(body["notional"]) == Decimal("155.1012")
    assert Decimal(body["min_notional"]) == Decimal("100")
    assert Decimal(body["max_notional"]) == Decimal("250")
    assert Decimal(body["next_viable_amount"]) == Decimal("0.002")
    assert Decimal(body["next_viable_notional"]) == Decimal("155.1012")
    assert body["cap_shortfall"] is None


def test_phase5e_feasibility_endpoint_reports_eth_ok(monkeypatch):
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _exchange_gateway=_gateway(price=Decimal("2100"), min_notional=Decimal("20")),
    )

    with TestClient(_app()) as client:
        resp = client.get("/api/runtime/test/phase5e/eth/feasibility")

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == ETH
    assert body["feasible"] is True
    assert body["reason"] == "OK"


def test_phase5e_entry_blocks_when_any_position_is_already_active(monkeypatch):
    orch = _orchestrator()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[_position(BTC)]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/eth/execute-controlled-entry")

    assert resp.status_code == 409
    assert "at most one sequential active symbol" in resp.json()["detail"]
    orch.execute_signal.assert_not_called()


def test_phase5e_entry_once_guard_is_symbol_scoped(monkeypatch):
    orch = _orchestrator()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _exchange_gateway=_gateway(price=Decimal("2100"), min_notional=Decimal("20")),
        _startup_trading_guard_service=_guard(),
        _global_kill_switch_service=_gks(),
        _position_repo=_position_repo(active=[]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        first = client.post("/api/runtime/test/phase5e/eth/execute-controlled-entry")
        second = client.post("/api/runtime/test/phase5e/eth/execute-controlled-entry")

    assert first.status_code == 200
    assert second.status_code == 409
    assert orch.execute_signal.await_count == 1


def test_phase5e_btc_close_uses_fixed_symbol_and_amount(monkeypatch):
    orch = _orchestrator()
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _execution_orchestrator=orch,
        _position_repo=_position_repo(active=[_position(BTC, Decimal("0.002"))]),
        _trace_service=None,
    )

    with TestClient(_app()) as client:
        resp = client.post("/api/runtime/test/phase5e/btc/execute-controlled-close")

    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == BTC
    assert body["profile"] == PROFILE
    assert Decimal(body["amount"]) == Decimal("0.002")
    orch.execute_controlled_close.assert_awaited_once()
    assert orch.execute_controlled_close.call_args.kwargs["max_amount"] == Decimal("0.002")


def test_phase5e_inventory_reports_all_flat_for_exchange_and_pg(monkeypatch):
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _exchange_gateway=_gateway(),
        _position_repo=_position_repo(active=[]),
        _order_repo=_order_repo(open_orders=[]),
    )

    with TestClient(_app()) as client:
        resp = client.get("/api/runtime/test/phase5e/inventory")

    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"] == PROFILE
    assert body["testnet"] is True
    assert body["all_flat"] is True
    assert {item["symbol"] for item in body["symbols"]} == {ETH, BTC}
    assert all(item["flat"] is True for item in body["symbols"])


def test_phase5e_inventory_reports_nonflat_counts(monkeypatch):
    local_order = Order(
        id="ord-local-btc",
        signal_id="sig-btc",
        exchange_order_id="ex-local-btc",
        symbol=BTC,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        requested_qty=Decimal("0.001"),
        filled_qty=Decimal("0"),
        status=OrderStatus.OPEN,
        created_at=1,
        updated_at=1,
        reduce_only=True,
    )
    _patch_api_module(
        monkeypatch,
        _runtime_config_provider=_config_provider(),
        _exchange_gateway=_gateway(
            positions={BTC: [SimpleNamespace(symbol=BTC, size=Decimal("0.002"))]},
            normal_open_orders={BTC: [{"id": "normal-1"}]},
            conditional_open_orders={BTC: [{"id": "stop-1"}]},
        ),
        _position_repo=_position_repo(active=[_position(BTC, Decimal("0.002"))]),
        _order_repo=_order_repo(open_orders=[local_order]),
    )

    with TestClient(_app()) as client:
        resp = client.get("/api/runtime/test/phase5e/inventory")

    assert resp.status_code == 200
    body = resp.json()
    assert body["all_flat"] is False
    btc = next(item for item in body["symbols"] if item["symbol"] == BTC)
    assert btc == {
        "symbol": BTC,
        "exchange_position_count": 1,
        "exchange_normal_open_order_count": 1,
        "exchange_conditional_open_order_count": 1,
        "local_active_position_count": 1,
        "local_open_order_count": 1,
        "flat": False,
    }
