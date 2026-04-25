"""Unit tests for Console Runtime readmodels (v1 readonly API)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.application.readmodels.runtime_health import RuntimeHealthReadModel
from src.application.readmodels.runtime_overview import RuntimeOverviewReadModel
from src.application.readmodels.runtime_portfolio import RuntimePortfolioReadModel
from src.domain.models import PositionInfo


def _make_account_snapshot(
    total_balance: Decimal = Decimal("1000"),
    available_balance: Decimal = Decimal("800"),
    unrealized_pnl: Decimal = Decimal("50"),
    timestamp_ms: int | None = None,
    positions: list[PositionInfo] | None = None,
) -> MagicMock:
    snapshot = MagicMock()
    snapshot.total_balance = total_balance
    snapshot.available_balance = available_balance
    snapshot.unrealized_pnl = unrealized_pnl
    snapshot.timestamp = timestamp_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    snapshot.positions = positions or []
    return snapshot


def _make_runtime_config_provider() -> MagicMock:
    provider = MagicMock()
    resolved = MagicMock()
    resolved.profile_name = "sim1_eth_runtime"
    resolved.version = 1
    resolved.config_hash = "abc123"

    environment = MagicMock()
    environment.core_execution_intent_backend = "postgres"
    environment.core_order_backend = "sqlite"
    environment.core_position_backend = "sqlite"
    from pydantic import SecretStr

    environment.pg_database_url = SecretStr("postgresql://localhost/db")
    environment.feishu_webhook_url = SecretStr("https://example.com/webhook")
    resolved.environment = environment

    market = MagicMock()
    market.primary_symbol = "ETH/USDT:USDT"
    market.primary_timeframe = "15m"
    resolved.market = market

    risk = MagicMock()
    risk.max_total_exposure = Decimal("2.0")
    risk.daily_max_loss_percent = Decimal("0.02")
    resolved.risk = risk

    provider.resolved_config = resolved
    return provider


# ============================================================
# Runtime Overview Tests
# ============================================================


@pytest.mark.asyncio
async def test_overview_freshness_fresh():
    read_model = RuntimeOverviewReadModel()
    snapshot = _make_account_snapshot(timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000))
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=snapshot,
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    assert response.freshness_status == "Fresh"
    assert response.profile == "sim1_eth_runtime"
    assert response.symbol == "ETH/USDT:USDT"
    assert response.timeframe == "15m"
    assert response.backend_summary == "intent=postgres, order=sqlite, position=sqlite"


@pytest.mark.asyncio
async def test_overview_freshness_stale():
    read_model = RuntimeOverviewReadModel()
    stale_ts = int((datetime.now(timezone.utc).timestamp() - 120) * 1000)
    snapshot = _make_account_snapshot(timestamp_ms=stale_ts)
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=snapshot,
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    assert response.freshness_status == "Stale"
    assert response.exchange_health == "DEGRADED"


@pytest.mark.asyncio
async def test_overview_freshness_possibly_dead():
    read_model = RuntimeOverviewReadModel()
    dead_ts = int((datetime.now(timezone.utc).timestamp() - 400) * 1000)
    snapshot = _make_account_snapshot(timestamp_ms=dead_ts)
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=snapshot,
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    assert response.freshness_status == "Possibly Dead"
    assert response.exchange_health == "DOWN"


@pytest.mark.asyncio
async def test_overview_no_runtime_provider():
    read_model = RuntimeOverviewReadModel()
    snapshot = _make_account_snapshot()

    response = await read_model.build(
        runtime_config_provider=None,
        account_snapshot=snapshot,
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    assert response.profile == "unavailable"
    assert response.pg_health == "DOWN"
    assert response.webhook_health == "DOWN"


# ============================================================
# Runtime Portfolio Tests
# ============================================================


@pytest.mark.asyncio
async def test_portfolio_basic_calculation():
    read_model = RuntimePortfolioReadModel()
    position = PositionInfo(
        symbol="ETH/USDT:USDT",
        side="long",
        size=Decimal("0.5"),
        entry_price=Decimal("3000"),
        current_price=Decimal("3100"),
        unrealized_pnl=Decimal("50"),
        leverage=5,
    )
    snapshot = _make_account_snapshot(
        total_balance=Decimal("1000"),
        available_balance=Decimal("800"),
        unrealized_pnl=Decimal("50"),
        positions=[position],
    )
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        capital_protection=None,
        account_snapshot=snapshot,
    )

    assert response.total_equity == 1050.0  # 1000 + 50
    assert response.available_balance == 800.0
    assert response.unrealized_pnl == 50.0
    assert response.total_exposure == 1500.0  # 0.5 * 3000
    assert len(response.positions) == 1
    assert response.positions[0].symbol == "ETH/USDT:USDT"
    assert response.positions[0].direction == "LONG"
    assert abs(response.positions[0].pnl_percent - 3.33) < 0.01  # 50/1500 * 100


@pytest.mark.asyncio
async def test_portfolio_daily_loss_fallback():
    read_model = RuntimePortfolioReadModel()
    snapshot = _make_account_snapshot(total_balance=Decimal("1000"), unrealized_pnl=Decimal("0"))
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        capital_protection=None,
        account_snapshot=snapshot,
    )

    # daily_loss_limit should fallback to runtime risk config: 1000 * 0.02 = 20
    assert response.daily_loss_limit == 20.0
    assert response.daily_loss_used == 0.0


@pytest.mark.asyncio
async def test_portfolio_no_account_snapshot():
    read_model = RuntimePortfolioReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        capital_protection=None,
        account_snapshot=None,
    )

    assert response.total_equity == 0.0
    assert response.positions == []


# ============================================================
# Runtime Health Tests
# ============================================================


@pytest.mark.asyncio
async def test_health_breaker_recovery_separation():
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    orchestrator = MagicMock()
    orchestrator.list_circuit_breaker_symbols = MagicMock(return_value=["ETH/USDT:USDT"])

    recovery_repo = MagicMock()

    async def mock_list_active():
        return [{"id": "task1", "created_at": datetime.now(timezone.utc)}]

    recovery_repo.list_active = mock_list_active

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=orchestrator,
        execution_recovery_repo=recovery_repo,
        startup_reconciliation_summary={"pg_recovery_resolved_count": 5},
        account_snapshot=_make_account_snapshot(),
    )

    # Breaker summary should reflect circuit breakers
    assert response.breaker_summary.total_tripped == 1
    assert response.breaker_summary.active_breakers == ["ETH/USDT:USDT"]

    # Recovery summary should reflect recovery tasks
    assert response.recovery_summary.pending_tasks == 1
    assert response.recovery_summary.completed_tasks == 5


@pytest.mark.asyncio
async def test_health_startup_markers_permission_skipped():
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    exchange = MagicMock()
    exchange.get_permission_check_summary = MagicMock(return_value={"status": "skipped_testnet", "verified": False})

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=exchange,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=_make_account_snapshot(),
    )

    # permission_check should be PENDING (not verified, but not failed)
    assert response.startup_markers["permission_check"] == "PENDING"
    assert "withdraw permission check skipped on testnet" in response.recent_warnings


@pytest.mark.asyncio
async def test_health_exchange_stale():
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()
    stale_ts = int((datetime.now(timezone.utc).timestamp() - 400) * 1000)
    snapshot = _make_account_snapshot(timestamp_ms=stale_ts)

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=snapshot,
    )

    assert response.exchange_status == "DOWN"
    assert "exchange heartbeat stale" in response.recent_errors


# ============================================================
# Finding 1: Startup warmup exchange health tests
# ============================================================


@pytest.mark.asyncio
async def test_overview_startup_warmup_no_snapshot():
    """When account_snapshot is None (startup warmup), exchange should not be DOWN."""
    read_model = RuntimeOverviewReadModel()
    provider = _make_runtime_config_provider()

    # No snapshot yet, but exchange gateway exists
    exchange = MagicMock()
    exchange.get_permission_check_summary = MagicMock(return_value={"status": "passed", "verified": True})

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=None,
        exchange_gateway=exchange,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    # Should NOT be DOWN during startup warmup
    assert response.exchange_health != "DOWN"
    # Should be DEGRADED (conservative: warmup, not yet verified)
    assert response.exchange_health == "DEGRADED"
    # Freshness should be "Fresh" (pending first snapshot, not dead)
    assert response.freshness_status == "Fresh"


@pytest.mark.asyncio
async def test_overview_startup_warmup_permission_failed():
    """Startup warmup with permission check failed should be DOWN."""
    read_model = RuntimeOverviewReadModel()
    provider = _make_runtime_config_provider()

    exchange = MagicMock()
    exchange.get_permission_check_summary = MagicMock(return_value={"status": "failed", "verified": False})

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=None,
        exchange_gateway=exchange,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    # Permission failed should be DOWN even during warmup
    assert response.exchange_health == "DOWN"


@pytest.mark.asyncio
async def test_overview_and_health_consistency_startup_warmup():
    """Overview and health should have consistent semantics during startup warmup."""
    overview_model = RuntimeOverviewReadModel()
    health_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    exchange = MagicMock()
    exchange.get_permission_check_summary = MagicMock(return_value={"status": "passed", "verified": True})

    overview_response = await overview_model.build(
        runtime_config_provider=provider,
        account_snapshot=None,
        exchange_gateway=exchange,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    health_response = await health_model.build(
        runtime_config_provider=provider,
        exchange_gateway=exchange,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=None,
    )

    # Both should agree on exchange status during warmup
    assert overview_response.exchange_health == health_response.exchange_status
    assert overview_response.exchange_health == "DEGRADED"


# ============================================================
# Finding 2: PG and notification status conservative tests
# ============================================================


@pytest.mark.asyncio
async def test_health_pg_status_conservative_without_connectivity():
    """PG status should be DEGRADED when only config exists, not OK."""
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,  # No reconciliation signal
        account_snapshot=_make_account_snapshot(),
    )

    # Should NOT be OK when only config exists
    assert response.pg_status != "OK"
    # Should be DEGRADED (conservative: config exists, no connectivity verified)
    assert response.pg_status == "DEGRADED"
    assert "pg connectivity not verified" in response.recent_warnings


@pytest.mark.asyncio
async def test_health_pg_status_with_reconciliation_signal():
    """PG status should be DEGRADED (not OK) even with reconciliation signal."""
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary={"pg_recovery_resolved_count": 5},
        account_snapshot=_make_account_snapshot(),
    )

    # Even with reconciliation signal, should be DEGRADED (conservative)
    assert response.pg_status == "DEGRADED"


@pytest.mark.asyncio
async def test_health_notification_status_conservative():
    """Notification status should be DEGRADED when only config exists, not OK."""
    read_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=_make_account_snapshot(),
    )

    # Should NOT be OK when only config exists
    assert response.notification_status != "OK"
    # Should be DEGRADED (conservative: config exists, no delivery verified)
    assert response.notification_status == "DEGRADED"
    assert "notification delivery not verified" in response.recent_warnings


@pytest.mark.asyncio
async def test_health_pg_notification_down_when_no_provider():
    """PG and notification should be DOWN when provider is None."""
    read_model = RuntimeHealthReadModel()

    response = await read_model.build(
        runtime_config_provider=None,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=_make_account_snapshot(),
    )

    assert response.pg_status == "DOWN"
    assert response.notification_status == "DOWN"
    assert "pg config unavailable" in response.recent_warnings
    assert "notification config unavailable" in response.recent_warnings


# ============================================================
# Overview pg/webhook health semantic alignment tests
# ============================================================


@pytest.mark.asyncio
async def test_overview_pg_health_conservative_without_probe():
    """Overview pg_health should be DEGRADED when only config exists, not OK."""
    read_model = RuntimeOverviewReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=_make_account_snapshot(),
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    # Should NOT be OK when only config exists
    assert response.pg_health != "OK"
    # Should be DEGRADED (conservative: config exists, no connectivity verified)
    assert response.pg_health == "DEGRADED"


@pytest.mark.asyncio
async def test_overview_webhook_health_conservative_without_probe():
    """Overview webhook_health should be DEGRADED when only config exists, not OK."""
    read_model = RuntimeOverviewReadModel()
    provider = _make_runtime_config_provider()

    response = await read_model.build(
        runtime_config_provider=provider,
        account_snapshot=_make_account_snapshot(),
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    # Should NOT be OK when only config exists
    assert response.webhook_health != "OK"
    # Should be DEGRADED (conservative: config exists, no delivery verified)
    assert response.webhook_health == "DEGRADED"


@pytest.mark.asyncio
async def test_overview_pg_webhook_down_when_no_provider():
    """Overview pg_health and webhook_health should be DOWN when provider is None."""
    read_model = RuntimeOverviewReadModel()

    response = await read_model.build(
        runtime_config_provider=None,
        account_snapshot=_make_account_snapshot(),
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    assert response.pg_health == "DOWN"
    assert response.webhook_health == "DOWN"


@pytest.mark.asyncio
async def test_overview_and_health_pg_webhook_consistency():
    """Overview and health should have consistent PG/notification health semantics."""
    overview_model = RuntimeOverviewReadModel()
    health_model = RuntimeHealthReadModel()
    provider = _make_runtime_config_provider()

    overview_response = await overview_model.build(
        runtime_config_provider=provider,
        account_snapshot=_make_account_snapshot(),
        exchange_gateway=None,
        execution_orchestrator=None,
        startup_reconciliation_summary=None,
    )

    health_response = await health_model.build(
        runtime_config_provider=provider,
        exchange_gateway=None,
        execution_orchestrator=None,
        execution_recovery_repo=None,
        startup_reconciliation_summary=None,
        account_snapshot=_make_account_snapshot(),
    )

    # Both should agree on PG/notification status
    assert overview_response.pg_health == health_response.pg_status
    assert overview_response.webhook_health == health_response.notification_status
    # Both should be DEGRADED (conservative)
    assert overview_response.pg_health == "DEGRADED"
    assert overview_response.webhook_health == "DEGRADED"

# ============================================================
# Runtime Execution Intents Tests
# ============================================================

from src.application.readmodels.runtime_execution_intents import RuntimeExecutionIntentsReadModel

@pytest.mark.asyncio
async def test_execution_intents_domain_model_parsing():
    """Test execution intent parsing when it's a domain model with a signal object."""
    read_model = RuntimeExecutionIntentsReadModel()
    
    # Mock a domain intent model
    intent = MagicMock()
    intent.id = "intent-123"
    intent.status = "pending"
    
    signal_obj = MagicMock()
    signal_obj.symbol = "BTC/USDT:USDT"
    signal_obj.model_dump = MagicMock(return_value={"direction": "SHORT", "suggested_position_size": Decimal("0.5")})
    intent.signal = signal_obj
    
    repo = MagicMock()
    repo.list_unfinished = MagicMock(return_value=pytest.helpers.future([intent]) if hasattr(pytest, "helpers") else [intent])
    
    async def mock_list(): return [intent]
    repo.list_unfinished = mock_list
    
    response = await read_model.build(intent_repo=repo)
    
    assert len(response.intents) == 1
    assert response.intents[0].symbol == "BTC/USDT:USDT"
    assert response.intents[0].side == "SELL"
    assert response.intents[0].quantity == 0.5
