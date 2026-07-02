from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.execution_orchestrator import (
    BRC_EXECUTION_PERMISSION_BLOCK_REASON,
    ExecutionOrchestrator,
)
from src.application.execution_permission import ExecutionPermission
from src.domain.execution_intent import ExecutionIntentStatus
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderStrategy, OrderType, SignalResult
from src.interfaces.api_brc_console import dev_testnet_router
from src.main import _signal_executor_for_brc_permission


class _CountingCapitalProtection:
    def __init__(self, *, allowed: bool = False):
        self.allowed = allowed
        self.calls = 0

    async def pre_order_check(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            allowed=self.allowed,
            reason=None if self.allowed else "CP_DENY",
            reason_message="allowed" if self.allowed else "CP_DENY",
        )


class _NoopLifecycle:
    def __init__(self):
        self.created = 0

    def set_entry_partially_filled_callback(self, _callback):
        return None

    def set_entry_filled_callback(self, _callback):
        return None

    def set_exit_progressed_callback(self, _callback):
        return None

    async def create_order(self, **_kwargs):
        self.created += 1
        return Order(
            id="local-entry",
            signal_id="sig-hardening",
            symbol="ETH/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            status=OrderStatus.CREATED,
            requested_qty=Decimal("0.1"),
            filled_qty=Decimal("0"),
            reduce_only=False,
        )


class _FakeGateway:
    pass


def _signal() -> SignalResult:
    return SignalResult(
        symbol="ETH/USDT:USDT",
        timeframe="4h",
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        suggested_stop_loss=Decimal("95"),
        suggested_position_size=Decimal("0.1"),
        current_leverage=1,
        risk_reward_info="test",
        strategy_name="test-strategy",
    )


def _strategy() -> OrderStrategy:
    return OrderStrategy(
        id="strategy-hardening",
        name="Hardening Strategy",
        tp_ratios=[Decimal("1")],
    )


def _orchestrator(permission: ExecutionPermission):
    cp = _CountingCapitalProtection(allowed=False)
    lifecycle = _NoopLifecycle()
    orchestrator = ExecutionOrchestrator(
        capital_protection=cp,
        order_lifecycle=lifecycle,
        gateway=_FakeGateway(),
        brc_execution_permission_max=permission,
    )
    return orchestrator, cp, lifecycle


@pytest.mark.parametrize(
    "permission",
    [
        ExecutionPermission.READ_ONLY,
        ExecutionPermission.SIGNAL_ONLY,
        ExecutionPermission.INTENT_RECORDING,
    ],
)
def test_main_signal_executor_is_none_below_order_allowed(permission):
    orchestrator = SimpleNamespace(execute_signal=object())

    assert _signal_executor_for_brc_permission(orchestrator, permission) is None


def test_main_signal_executor_stays_disabled_by_default_when_order_allowed():
    async def _execute_signal():
        return None

    orchestrator = SimpleNamespace(execute_signal=_execute_signal)

    assert _signal_executor_for_brc_permission(orchestrator, ExecutionPermission.ORDER_ALLOWED) is None


def test_main_signal_executor_requires_explicit_legacy_opt_in_when_order_allowed():
    async def _execute_signal():
        return None

    orchestrator = SimpleNamespace(execute_signal=_execute_signal)

    assert (
        _signal_executor_for_brc_permission(
            orchestrator,
            ExecutionPermission.ORDER_ALLOWED,
            allow_legacy_signal_execution=True,
        )
        is _execute_signal
    )


@pytest.mark.asyncio
async def test_execute_signal_blocks_before_order_path_when_permission_intent_recording():
    orchestrator, cp, lifecycle = _orchestrator(ExecutionPermission.INTENT_RECORDING)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == BRC_EXECUTION_PERMISSION_BLOCK_REASON
    assert "below order_allowed" in (intent.blocked_message or "")
    assert cp.calls == 0
    assert lifecycle.created == 0
    assert orchestrator._intents == {}


@pytest.mark.asyncio
async def test_execute_signal_order_allowed_preserves_existing_path():
    orchestrator, cp, lifecycle = _orchestrator(ExecutionPermission.ORDER_ALLOWED)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert cp.calls == 1
    assert lifecycle.created == 0
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CP_DENY"


def test_dev_testnet_router_has_no_generic_production_trading_or_transfer_endpoint():
    routes = [
        {
            "path": route.path,
            "methods": set(route.methods or []),
            "name": route.name,
        }
        for route in dev_testnet_router.routes
    ]
    paths = {route["path"] for route in routes}

    assert paths == {
        "/api/dev/testnet/brc/campaigns",
        "/api/dev/testnet/brc/switch-playbook",
        "/api/dev/testnet/brc/{symbol_key}/arm-attempt",
        "/api/dev/testnet/brc/{symbol_key}/execute-controlled-entry",
        "/api/dev/testnet/brc/{symbol_key}/execute-controlled-close",
        "/api/dev/testnet/brc/carriers",
        "/api/dev/testnet/brc/carriers/{carrier_id}/execute-controlled-entry",
        "/api/dev/testnet/brc/carriers/{carrier_id}/execute-controlled-close",
        "/api/dev/testnet/brc/mock-pnl",
        "/api/dev/testnet/brc/finalize",
    }
    assert all(
        route["methods"] == ({"GET"} if route["path"] == "/api/dev/testnet/brc/carriers" else {"POST"})
        for route in routes
    )
    assert not any(
        token in route["path"]
        for route in routes
        for token in ("withdraw", "transfer", "flatten", "cancel", "order")
    )
    controlled_paths = {
        "/api/dev/testnet/brc/{symbol_key}/execute-controlled-entry",
        "/api/dev/testnet/brc/{symbol_key}/execute-controlled-close",
        "/api/dev/testnet/brc/carriers/{carrier_id}/execute-controlled-entry",
        "/api/dev/testnet/brc/carriers/{carrier_id}/execute-controlled-close",
    }
    assert {route["path"] for route in routes if "execute-controlled" in route["path"]} == controlled_paths
