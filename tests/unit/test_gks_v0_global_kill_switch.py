from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.global_kill_switch import (
    KILL_SWITCH_BLOCK_REASON,
    GlobalKillSwitchService,
)
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.order_lifecycle_service import OrderLifecycleService
from src.domain.execution_intent import ExecutionIntentStatus
from src.domain.models import (
    Direction,
    Order,
    OrderRole,
    OrderStatus,
    OrderStrategy,
    OrderType,
    SignalResult,
)
from src.infrastructure.pg_global_kill_switch_repository import PgGlobalKillSwitchRepository
from src.infrastructure.pg_models import PGGlobalKillSwitchStateORM
from src.interfaces import api as api_module
from src.interfaces.api_console_runtime import router as runtime_router


class _CountingCapitalProtection:
    def __init__(self, *, allowed: bool = False, reason: str = "CP_DENY") -> None:
        self.allowed = allowed
        self.reason = reason
        self.calls = 0

    async def pre_order_check(self, **kwargs):
        self.calls += 1
        return type(
            "CheckResult",
            (),
            {
                "allowed": self.allowed,
                "reason": None if self.allowed else self.reason,
                "reason_message": "allowed" if self.allowed else self.reason,
            },
        )()


class _NoopLifecycle:
    def __init__(self) -> None:
        self.created = 0

    def set_entry_partially_filled_callback(self, callback) -> None:
        self.entry_partially_filled_callback = callback

    def set_entry_filled_callback(self, callback) -> None:
        self.entry_filled_callback = callback

    def set_exit_progressed_callback(self, callback) -> None:
        self.exit_progressed_callback = callback

    async def create_order(self, **kwargs) -> Order:
        self.created += 1
        return _order(
            order_id="local-entry",
            exchange_order_id=None,
            status=OrderStatus.CREATED,
        )


class _FakeGateway:
    async def place_order(self, **kwargs):
        return type(
            "PlacementResult",
            (),
            {
                "is_success": False,
                "error_code": "NOT_USED",
                "error_message": "not used by these tests",
                "status": OrderStatus.REJECTED,
                "exchange_order_id": None,
                "filled_qty": Decimal("0"),
                "average_exec_price": None,
            },
        )()


class _OrderRepository:
    def __init__(self, order: Order) -> None:
        self.order = order
        self.saved: list[Order] = []

    async def get_order_by_exchange_id(self, exchange_order_id: str):
        if self.order.exchange_order_id == exchange_order_id:
            return self.order.model_copy(deep=True)
        return None

    async def get_orders_by_signal(self, signal_id: str):
        return []

    async def save(self, order: Order) -> None:
        self.order = order.model_copy(deep=True)
        self.saved.append(order.model_copy(deep=True))


class _FailingGksRepository:
    async def initialize(self) -> None:
        return None

    async def get_state(self):
        return None

    async def set_state(self, **kwargs):
        raise RuntimeError("pg write unavailable")


class _ReadFailingGksRepository:
    """Repository where get_state() raises — simulates PG read failure at init."""

    async def initialize(self) -> None:
        return None

    async def get_state(self):
        raise RuntimeError("pg read unavailable")

    async def set_state(self, **kwargs):
        raise RuntimeError("pg write unavailable")

@pytest_asyncio.fixture()
async def gks_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGGlobalKillSwitchStateORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgGlobalKillSwitchRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


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
        id="strategy-test",
        name="Test Strategy",
        tp_ratios=[Decimal("1")],
    )


def _order(
    *,
    order_id: str = "local-entry",
    exchange_order_id: str | None = "ex-1",
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    return Order(
        id=order_id,
        signal_id="sig-gks",
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        status=status,
        requested_qty=Decimal("0.1"),
        filled_qty=Decimal("0"),
        average_exec_price=None,
        reduce_only=False,
        exchange_order_id=exchange_order_id,
        created_at=1,
        updated_at=1,
    )


async def _orchestrator(*, gks_active: bool, cp_allowed: bool = False):
    gks = GlobalKillSwitchService()
    await gks.set_state(active=gks_active, reason="test", updated_by="test")
    cp = _CountingCapitalProtection(allowed=cp_allowed)
    lifecycle = _NoopLifecycle()
    orchestrator = ExecutionOrchestrator(
        capital_protection=cp,
        order_lifecycle=lifecycle,
        gateway=_FakeGateway(),
        global_kill_switch=gks,
    )
    return orchestrator, cp, lifecycle


@pytest.mark.asyncio
async def test_gks_active_blocks_new_entries():
    orchestrator, cp, lifecycle = await _orchestrator(gks_active=True)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == KILL_SWITCH_BLOCK_REASON
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_gks_inactive_reaches_capital_protection():
    orchestrator, cp, lifecycle = await _orchestrator(gks_active=False)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert cp.calls == 1
    assert lifecycle.created == 0
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CP_DENY"


@pytest.mark.asyncio
async def test_circuit_breaker_has_priority_over_gks():
    orchestrator, cp, _lifecycle = await _orchestrator(gks_active=True)
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CIRCUIT_BREAKER"
    assert cp.calls == 0


@pytest.mark.asyncio
async def test_gks_has_priority_over_capital_protection():
    orchestrator, cp, _lifecycle = await _orchestrator(gks_active=True)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == KILL_SWITCH_BLOCK_REASON
    assert cp.calls == 0


@pytest.mark.asyncio
async def test_startup_restores_persisted_on_state(gks_repo):
    await gks_repo.set_state(
        active=True,
        reason="owner stop",
        updated_by="owner",
        updated_at_ms=123,
    )
    service = GlobalKillSwitchService(repository=gks_repo)

    await service.initialize()

    state = service.get_state()
    assert state.active is True
    assert state.reason == "owner stop"
    assert state.updated_by == "owner"
    assert state.updated_at_ms == 123
    assert state.source == "pg"


@pytest.mark.asyncio
async def test_activation_persistence_failure_logs_high_and_does_not_change_cache(caplog):
    service = GlobalKillSwitchService(repository=_FailingGksRepository())

    with pytest.raises(RuntimeError, match="pg write unavailable"):
        await service.set_state(active=True, reason="stop", updated_by="owner")

    state = service.get_state()
    assert state.active is False
    assert "[GKS-v0][HIGH]" in caplog.text


def test_toggle_then_read_endpoint_returns_state(monkeypatch):
    service = GlobalKillSwitchService()
    monkeypatch.setattr(api_module, "_global_kill_switch_service", service)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        post_response = client.post(
            "/api/runtime/control/global-kill-switch",
            json={"active": True, "reason": "manual stop", "updated_by": "owner"},
        )
        assert post_response.status_code == 200
        assert post_response.json()["active"] is True
        assert post_response.json()["live_ready"] is False

        get_response = client.get("/api/runtime/control/global-kill-switch")
        assert get_response.status_code == 200
        payload = get_response.json()
        assert payload["active"] is True
        assert payload["reason"] == "manual stop"
        assert "not a public internet control plane" in payload["access_boundary"]


@pytest.mark.asyncio
async def test_gks_does_not_affect_existing_order_update_path():
    gks = GlobalKillSwitchService()
    await gks.set_state(active=True, reason="stop entries", updated_by="owner")
    local_order = _order(status=OrderStatus.OPEN)
    repository = _OrderRepository(local_order)
    lifecycle = OrderLifecycleService(repository=repository)

    exchange_update = _order(
        order_id="exchange-event",
        exchange_order_id="ex-1",
        status=OrderStatus.FILLED,
    )
    exchange_update.filled_qty = Decimal("0.1")
    exchange_update.average_exec_price = Decimal("101")

    updated = await lifecycle.update_order_from_exchange(exchange_update)

    assert gks.is_active() is True
    assert updated.status == OrderStatus.FILLED
    assert repository.saved[-1].status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_read_failure_on_init_activates_fail_closed(caplog):
    """If PG get_state() raises during initialize(), GKS must fail closed (active=True)."""
    service = GlobalKillSwitchService(repository=_ReadFailingGksRepository())

    await service.initialize()

    state = service.get_state()
    assert state.active is True
    assert state.source == "read_failure_fail_closed"
    assert state.reason == "GKS_STATE_UNAVAILABLE"
    assert service.is_active() is True
    assert "[GKS-v0][HIGH]" in caplog.text
