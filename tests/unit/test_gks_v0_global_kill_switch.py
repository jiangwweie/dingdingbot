from __future__ import annotations

import json
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.decision_trace import TraceService
from src.application.global_kill_switch import (
    GLOBAL_KILL_SWITCH_CONFLICTING_REASON,
    GLOBAL_KILL_SWITCH_CORRUPT_REASON,
    GLOBAL_KILL_SWITCH_MISSING_REASON,
    GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON,
    KILL_SWITCH_BLOCK_REASON,
    GlobalKillSwitchService,
)
from src.application.campaign_state_service import CampaignStateService
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.protection_health_monitor import PROTECTION_MISSING_EXCHANGE_SL
from src.application.startup_trading_guard import (
    STARTUP_TRADING_GUARD_BLOCK_REASON,
    StartupTradingGuardService,
)
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
from src.infrastructure.jsonl_trace_sink import JsonlTraceSink
from src.infrastructure.pg_models import PGGlobalKillSwitchStateORM
from src.infrastructure.repository_ports import CampaignStateSnapshot, GlobalKillSwitchStateSnapshot
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


class _CountingGks:
    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.checks = 0
        self.traces = 0

    def is_active(self) -> bool:
        self.checks += 1
        return self.active

    def emit_check_trace(self, **kwargs) -> None:
        self.traces += 1

    def get_state(self):
        return type(
            "GksState",
            (),
            {
                "reason": "test-gks",
                "source": "test",
                "updated_at_ms": 123,
            },
        )()


class _DenyAccountRisk:
    async def evaluate_new_entry(self, symbol: str):
        return type(
            "AccountRiskAssessment",
            (),
            {
                "allowed_new_entry": False,
                "reason": "LIQUIDATION_DISTANCE_CRITICAL",
                "reason_message": "too close",
                "state": type("State", (), {"value": "critical"})(),
                "metadata": {"symbol": symbol},
            },
        )()


class _CampaignGate:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed

    async def evaluate_new_entry(self, **kwargs):
        return type(
            "CampaignGateDecision",
            (),
            {
                "allowed_new_entry": self.allowed,
                "reason": "CAMPAIGN_STATE_NOT_ARMED",
                "reason_message": "not armed",
                "state": "observe",
            },
        )()


class _CampaignRepo:
    def __init__(self) -> None:
        self.snapshot: CampaignStateSnapshot | None = None

    async def initialize(self) -> None:
        return None

    async def get_state(self, scope_key: str):
        return self.snapshot if self.snapshot and self.snapshot.scope_key == scope_key else None

    async def set_state(
        self,
        *,
        scope_key: str,
        status: str,
        reason: str | None,
        updated_by: str,
        updated_at_ms: int,
        active_strategy_contract_id: str | None,
        active_session_id: str | None,
    ):
        self.snapshot = CampaignStateSnapshot(
            scope_key=scope_key,
            status=status,
            reason=reason,
            updated_by=updated_by,
            updated_at_ms=updated_at_ms,
            active_strategy_contract_id=active_strategy_contract_id,
            active_session_id=active_session_id,
            source="test",
        )
        return self.snapshot


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


class _CorruptGksRepository:
    async def initialize(self) -> None:
        return None

    async def get_state(self):
        return type(
            "CorruptSnapshot",
            (),
            {
                "active": "false",
                "reason": None,
                "updated_by": "owner",
                "updated_at_ms": 123,
                "source": "pg",
            },
        )()

    async def set_state(self, **kwargs):
        raise RuntimeError("pg write unavailable")


class _ConflictingGksRepository:
    async def initialize(self) -> None:
        return None

    async def get_state(self):
        return GlobalKillSwitchStateSnapshot(
            active=False,
            reason=GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON,
            updated_by="system",
            updated_at_ms=123,
            source="pg",
        )

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


async def _orchestrator_with_startup_guard(
    *,
    guard: StartupTradingGuardService,
    cp_allowed: bool = False,
):
    cp = _CountingCapitalProtection(allowed=cp_allowed)
    lifecycle = _NoopLifecycle()
    orchestrator = ExecutionOrchestrator(
        capital_protection=cp,
        order_lifecycle=lifecycle,
        gateway=_FakeGateway(),
        startup_trading_guard=guard,
    )
    return orchestrator, cp, lifecycle


async def _orchestrator_with_controls(
    *,
    gks,
    guard: StartupTradingGuardService | None = None,
    cp_allowed: bool = False,
):
    cp = _CountingCapitalProtection(allowed=cp_allowed)
    lifecycle = _NoopLifecycle()
    orchestrator = ExecutionOrchestrator(
        capital_protection=cp,
        order_lifecycle=lifecycle,
        gateway=_FakeGateway(),
        global_kill_switch=gks,
        startup_trading_guard=guard,
    )
    return orchestrator, cp, lifecycle


async def _orchestrator_with_runtime_gates(
    *,
    account_risk_service=None,
    campaign_state_service=None,
):
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")
    gks = _CountingGks(active=False)
    cp = _CountingCapitalProtection(allowed=False)
    lifecycle = _NoopLifecycle()
    orchestrator = ExecutionOrchestrator(
        capital_protection=cp,
        order_lifecycle=lifecycle,
        gateway=_FakeGateway(),
        global_kill_switch=gks,
        startup_trading_guard=guard,
        account_risk_service=account_risk_service,
        campaign_state_service=campaign_state_service,
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
async def test_gks_has_priority_over_circuit_breaker():
    orchestrator, cp, _lifecycle = await _orchestrator(gks_active=True)
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == KILL_SWITCH_BLOCK_REASON
    assert cp.calls == 0


@pytest.mark.asyncio
async def test_startup_guard_wins_when_all_gates_block():
    guard = StartupTradingGuardService()
    gks = _CountingGks(active=True)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == STARTUP_TRADING_GUARD_BLOCK_REASON
    assert gks.checks == 0
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_manual_arm_then_enters_gks_before_capital_protection():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")
    gks = _CountingGks(active=False)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert gks.checks == 1
    assert gks.traces == 1
    assert cp.calls == 1
    assert lifecycle.created == 0
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CP_DENY"


@pytest.mark.asyncio
async def test_gks_block_wins_before_circuit_breaker_and_capital_protection():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")
    gks = _CountingGks(active=True)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == KILL_SWITCH_BLOCK_REASON
    assert gks.checks == 1
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_after_startup_guard_and_gks_allow():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")
    gks = _CountingGks(active=False)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )
    orchestrator._circuit_breaker_symbols.add("ETH/USDT:USDT")

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CIRCUIT_BREAKER"
    assert gks.checks == 1
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_protection_health_block_preserves_reason_and_skips_capital_protection():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")
    gks = _CountingGks(active=False)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )
    orchestrator.block_symbol_for_protection_health(
        "ETH/USDT:USDT",
        PROTECTION_MISSING_EXCHANGE_SL,
        {"source": "startup"},
    )

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == PROTECTION_MISSING_EXCHANGE_SL
    assert gks.checks == 1
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_account_risk_gate_blocks_before_capital_protection():
    orchestrator, cp, lifecycle = await _orchestrator_with_runtime_gates(
        account_risk_service=_DenyAccountRisk(),
    )

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "ACCOUNT_RISK_NOT_HEALTHY"
    assert "LIQUIDATION_DISTANCE_CRITICAL" in intent.blocked_message
    assert cp.calls == 0
    assert lifecycle.created == 0


@pytest.mark.asyncio
async def test_campaign_state_gate_blocks_before_capital_protection():
    orchestrator, cp, lifecycle = await _orchestrator_with_runtime_gates(
        campaign_state_service=_CampaignGate(allowed=False),
    )

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CAMPAIGN_STATE_NOT_ARMED"
    assert cp.calls == 0
    assert lifecycle.created == 0


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
async def test_missing_gks_row_blocks_new_entries_fail_closed(gks_repo):
    service = GlobalKillSwitchService(repository=gks_repo)

    await service.initialize()

    state = service.get_state()
    assert state.active is True
    assert state.reason == GLOBAL_KILL_SWITCH_MISSING_REASON
    assert state.source == "missing_row_fail_closed"


@pytest.mark.asyncio
async def test_missing_gks_row_blocks_execute_signal_and_emits_trace(gks_repo, tmp_path):
    trace_path = tmp_path / "runtime" / "risk_decision.jsonl"
    trace_service = TraceService(sinks=[JsonlTraceSink(trace_path)])
    gks = GlobalKillSwitchService(repository=gks_repo, trace_service=trace_service)
    await gks.initialize()
    guard = StartupTradingGuardService(trace_service=trace_service)
    guard.manual_arm(updated_by="owner", reason="testnet smoke approved")
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        gks=gks,
        guard=guard,
    )

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == KILL_SWITCH_BLOCK_REASON
    assert cp.calls == 0
    assert lifecycle.created == 0
    payload = trace_path.read_text(encoding="utf-8")
    assert "risk.global_kill_switch_check" in payload
    assert GLOBAL_KILL_SWITCH_MISSING_REASON in payload
    assert KILL_SWITCH_BLOCK_REASON in payload


@pytest.mark.asyncio
async def test_activation_persistence_failure_logs_high_and_does_not_change_cache(caplog):
    service = GlobalKillSwitchService(repository=_FailingGksRepository())

    with pytest.raises(RuntimeError, match="pg write unavailable"):
        await service.set_state(active=True, reason="stop", updated_by="owner")

    state = service.get_state()
    assert state.active is False
    assert "[GKS-v0][HIGH]" in caplog.text


def test_toggle_then_read_endpoint_returns_state(monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
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


def test_gks_mutation_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RUNTIME_CONTROL_API_ENABLED", raising=False)
    service = GlobalKillSwitchService()
    monkeypatch.setattr(api_module, "_global_kill_switch_service", service)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/runtime/control/global-kill-switch",
            json={"active": True, "reason": "manual stop", "updated_by": "owner"},
        )

    assert response.status_code == 403
    assert service.is_active() is False


def test_api_set_dependencies_receives_same_startup_guard_instance(monkeypatch):
    guard = StartupTradingGuardService()

    api_module.set_dependencies(startup_trading_guard_service=guard)

    assert api_module._startup_trading_guard_service is guard


def test_api_set_dependencies_receives_campaign_state_service(monkeypatch):
    service = CampaignStateService(repository=None)

    api_module.set_dependencies(campaign_state_service=service)

    assert api_module._campaign_state_service is service


def test_get_startup_guard_endpoint_returns_state(monkeypatch):
    monkeypatch.delenv("RUNTIME_CONTROL_API_ENABLED", raising=False)
    guard = StartupTradingGuardService()
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", guard)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.get("/api/runtime/control/startup-trading-guard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["armed"] is False
    assert payload["reason"] == STARTUP_TRADING_GUARD_BLOCK_REASON
    assert payload["source"] == "startup_default_block"


def test_startup_guard_arm_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RUNTIME_CONTROL_API_ENABLED", raising=False)
    guard = StartupTradingGuardService()
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", guard)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/runtime/control/startup-trading-guard/arm",
            json={"reason": "test", "updated_by": "owner"},
        )

    assert response.status_code == 403
    assert guard.is_armed() is False


@pytest.mark.asyncio
async def test_arm_endpoint_arms_same_instance_used_by_orchestrator(monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    guard = StartupTradingGuardService()
    gks = _CountingGks(active=False)
    orchestrator, cp, lifecycle = await _orchestrator_with_controls(
        guard=guard,
        gks=gks,
    )
    api_module.set_dependencies(startup_trading_guard_service=guard)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/runtime/control/startup-trading-guard/arm",
            json={"reason": "testnet smoke approved", "updated_by": "owner"},
        )

    assert response.status_code == 200
    assert response.json()["armed"] is True
    assert guard.is_armed() is True

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert gks.checks == 1
    assert cp.calls == 1
    assert lifecycle.created == 0
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CP_DENY"


def test_startup_guard_block_endpoint_resets_to_not_armed(monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="startup checked")
    monkeypatch.setattr(api_module, "_startup_trading_guard_service", guard)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/runtime/control/startup-trading-guard/block",
            json={"reason": "clean shutdown", "updated_by": "owner"},
        )

    assert response.status_code == 200
    assert response.json()["armed"] is False
    assert response.json()["reason"] == "clean shutdown"
    assert guard.is_armed() is False


@pytest.mark.asyncio
async def test_campaign_state_endpoint_updates_same_runtime_service(monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)
    await service.initialize()
    monkeypatch.setattr(api_module, "_campaign_state_service", service)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        arm_response = client.post(
            "/api/runtime/control/campaign-state",
            json={
                "status": "armed",
                "reason": "owner arm",
                "updated_by": "owner",
                "active_strategy_contract_id": "strategy-test",
            },
        )
        read_response = client.get("/api/runtime/control/campaign-state")

    assert arm_response.status_code == 200
    assert arm_response.json()["status"] == "armed"
    assert arm_response.json()["active_strategy_contract_id"] == "strategy-test"
    assert read_response.status_code == 200
    assert read_response.json()["status"] == "armed"


@pytest.mark.asyncio
async def test_campaign_state_endpoint_rejects_invalid_transition(monkeypatch):
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")
    repo = _CampaignRepo()
    service = CampaignStateService(repository=repo)
    await service.initialize()
    await service.set_state(status="hard_locked", reason="risk", updated_by="owner")
    monkeypatch.setattr(api_module, "_campaign_state_service", service)
    app = FastAPI()
    app.include_router(runtime_router)

    with TestClient(app) as client:
        response = client.post(
            "/api/runtime/control/campaign-state",
            json={"status": "armed", "reason": "bad", "updated_by": "owner"},
        )

    assert response.status_code == 409


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
    assert state.reason == GLOBAL_KILL_SWITCH_UNAVAILABLE_REASON
    assert service.is_active() is True
    assert "[GKS-v0][HIGH]" in caplog.text


@pytest.mark.asyncio
async def test_corrupt_gks_state_activates_fail_closed(caplog):
    service = GlobalKillSwitchService(repository=_CorruptGksRepository())

    await service.initialize()

    state = service.get_state()
    assert state.active is True
    assert state.reason == GLOBAL_KILL_SWITCH_CORRUPT_REASON
    assert state.source == "invalid_state_fail_closed"
    assert service.is_active() is True
    assert "[GKS-v0][HIGH]" in caplog.text


@pytest.mark.asyncio
async def test_conflicting_gks_state_activates_fail_closed(caplog):
    service = GlobalKillSwitchService(repository=_ConflictingGksRepository())

    await service.initialize()

    state = service.get_state()
    assert state.active is True
    assert state.reason == GLOBAL_KILL_SWITCH_CONFLICTING_REASON
    assert state.source == "invalid_state_fail_closed"
    assert service.is_active() is True
    assert "[GKS-v0][HIGH]" in caplog.text


@pytest.mark.asyncio
async def test_startup_guard_blocks_until_manual_arm_and_emits_trace(tmp_path):
    trace_path = tmp_path / "runtime" / "risk_decision.jsonl"
    guard = StartupTradingGuardService(
        trace_service=TraceService(sinks=[JsonlTraceSink(trace_path)])
    )
    orchestrator, cp, lifecycle = await _orchestrator_with_startup_guard(guard=guard)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == STARTUP_TRADING_GUARD_BLOCK_REASON
    assert cp.calls == 0
    assert lifecycle.created == 0
    payload = trace_path.read_text(encoding="utf-8")
    assert "risk.startup_trading_guard_check" in payload
    assert STARTUP_TRADING_GUARD_BLOCK_REASON in payload


def test_new_startup_guard_instance_after_restart_defaults_blocked():
    guard = StartupTradingGuardService()
    guard.manual_arm(updated_by="owner", reason="test")

    restarted_guard = StartupTradingGuardService()

    assert guard.is_armed() is True
    assert restarted_guard.is_armed() is False
    assert restarted_guard.get_state().reason == STARTUP_TRADING_GUARD_BLOCK_REASON


@pytest.mark.asyncio
async def test_manual_arm_allows_signal_to_reach_capital_protection(tmp_path):
    trace_path = tmp_path / "runtime" / "risk_decision.jsonl"
    guard = StartupTradingGuardService(
        trace_service=TraceService(sinks=[JsonlTraceSink(trace_path)])
    )
    guard.manual_arm(updated_by="owner", reason="testnet smoke approved")
    orchestrator, cp, lifecycle = await _orchestrator_with_startup_guard(guard=guard)

    intent = await orchestrator.execute_signal(_signal(), _strategy())

    assert cp.calls == 1
    assert lifecycle.created == 0
    assert intent.status == ExecutionIntentStatus.BLOCKED
    assert intent.blocked_reason == "CP_DENY"
    payload = trace_path.read_text(encoding="utf-8")
    assert "risk.startup_trading_guard_check" in payload
    assert '"decision": "allow"' in payload


def test_manual_arm_emits_control_trace_without_secrets(tmp_path):
    trace_path = tmp_path / "runtime" / "risk_decision.jsonl"
    guard = StartupTradingGuardService(
        trace_service=TraceService(sinks=[JsonlTraceSink(trace_path)]),
        config_hash="cfg-safe",
    )

    guard.manual_arm(updated_by="owner", reason="testnet smoke approved")

    payload = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["event_type"] == "control.startup_trading_guard_arm"
    assert payload["lifecycle_id"] == "control:startup_trading_guard"
    assert payload["config_hash"] == "cfg-safe"
    assert payload["metadata"]["previous_state"]["armed"] is False
    assert payload["metadata"]["new_state"]["armed"] is True
    assert payload["metadata"]["source"] == "manual_arm"
    serialized = json.dumps(payload)
    assert "api_key" not in serialized
    assert "secret" not in serialized.lower()


@pytest.mark.asyncio
async def test_startup_guard_does_not_affect_existing_exit_order_lifecycle():
    guard = StartupTradingGuardService()
    local_order = _order(status=OrderStatus.OPEN)
    local_order.order_role = OrderRole.SL
    repository = _OrderRepository(local_order)
    lifecycle = OrderLifecycleService(repository=repository)

    exchange_update = _order(
        order_id="exchange-event",
        exchange_order_id="ex-1",
        status=OrderStatus.FILLED,
    )
    exchange_update.order_role = OrderRole.SL
    exchange_update.filled_qty = Decimal("0.1")
    exchange_update.average_exec_price = Decimal("101")

    updated = await lifecycle.update_order_from_exchange(exchange_update)

    assert guard.is_armed() is False
    assert updated.status == OrderStatus.FILLED
    assert repository.saved[-1].status == OrderStatus.FILLED
