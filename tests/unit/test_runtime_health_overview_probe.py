"""Tests for runtime health / overview PG probe semantics.

Covers:
A. RuntimeHealthReadModel
  1. probe success -> pg_status = OK
  2. probe failure -> pg_status = DOWN
  3. execution_recovery_repo with list_blocking() preferred
  4. fallback to list_active() when no list_blocking()

B. RuntimeOverviewReadModel
  1. Pg*Repository + probe success -> pg_health = OK
  2. probe failure -> pg_health = DOWN
  3. backend_summary uses actual repo class name
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.readmodels.runtime_health import RuntimeHealthReadModel
from src.application.readmodels.runtime_overview import RuntimeOverviewReadModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    order_backend="sqlite",
    position_backend="sqlite",
    intent_backend="postgres",
):
    provider = MagicMock()
    resolved = MagicMock()
    resolved.profile_name = "test_profile"
    resolved.version = 1
    resolved.config_hash = "hash123"

    environment = MagicMock()
    environment.core_order_backend = order_backend
    environment.core_position_backend = position_backend
    environment.core_execution_intent_backend = intent_backend
    resolved.environment = environment

    market = MagicMock()
    market.primary_symbol = "BTC/USDT:USDT"
    market.primary_timeframe = "15m"
    resolved.market = market

    provider.resolved_config = resolved
    return provider


def _make_account_snapshot():
    snapshot = MagicMock()
    snapshot.total_balance = 1000
    snapshot.available_balance = 800
    snapshot.unrealized_pnl = 50
    snapshot.timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    return snapshot


# ---------------------------------------------------------------------------
# A. RuntimeHealthReadModel
# ---------------------------------------------------------------------------


class TestRuntimeHealthPGProbe:
    """PG connectivity probe semantics for RuntimeHealthReadModel."""

    @pytest.mark.asyncio
    async def test_probe_success_pg_status_ok(self):
        """When probe succeeds, pg_status should be OK."""
        model = RuntimeHealthReadModel()
        provider = _make_provider()
        repo = MagicMock()
        repo._session_maker = MagicMock()
        repo.list_blocking = AsyncMock(return_value=[])

        with patch(
            "src.application.readmodels.runtime_health.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=True,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                exchange_gateway=None,
                execution_orchestrator=None,
                execution_recovery_repo=repo,
                startup_reconciliation_summary=None,
                account_snapshot=_make_account_snapshot(),
            )

        assert response.pg_status == "OK"

    @pytest.mark.asyncio
    async def test_probe_failure_pg_status_down(self):
        """When probe fails, pg_status should be DOWN."""
        model = RuntimeHealthReadModel()
        provider = _make_provider()
        repo = MagicMock()
        repo._session_maker = MagicMock()
        repo.list_blocking = AsyncMock(return_value=[])

        with patch(
            "src.application.readmodels.runtime_health.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=False,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                exchange_gateway=None,
                execution_orchestrator=None,
                execution_recovery_repo=repo,
                startup_reconciliation_summary=None,
                account_snapshot=_make_account_snapshot(),
            )

        assert response.pg_status == "DOWN"
        assert "pg connectivity unavailable" in response.recent_warnings

    @pytest.mark.asyncio
    async def test_recovery_repo_list_blocking_preferred(self):
        """list_blocking() is preferred over list_active()."""
        model = RuntimeHealthReadModel()
        provider = _make_provider()
        repo = MagicMock()
        repo._session_maker = MagicMock()
        repo.list_blocking = AsyncMock(return_value=[
            {"id": "t1", "created_at": datetime.now(timezone.utc)},
        ])
        repo.list_active = AsyncMock(return_value=[])

        with patch(
            "src.application.readmodels.runtime_health.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=True,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                exchange_gateway=None,
                execution_orchestrator=None,
                execution_recovery_repo=repo,
                startup_reconciliation_summary=None,
                account_snapshot=_make_account_snapshot(),
            )

        repo.list_blocking.assert_called_once()
        repo.list_active.assert_not_called()
        assert response.recovery_summary.pending_tasks == 1

    @pytest.mark.asyncio
    async def test_fallback_list_active_when_no_list_blocking(self):
        """Falls back to list_active() when list_blocking() is absent."""
        model = RuntimeHealthReadModel()
        provider = _make_provider()
        repo = MagicMock()
        repo._session_maker = MagicMock()
        del repo.list_blocking
        repo.list_active = AsyncMock(return_value=[
            {"id": "t1", "created_at": datetime.now(timezone.utc)},
        ])

        with patch(
            "src.application.readmodels.runtime_health.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=True,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                exchange_gateway=None,
                execution_orchestrator=None,
                execution_recovery_repo=repo,
                startup_reconciliation_summary=None,
                account_snapshot=_make_account_snapshot(),
            )

        repo.list_active.assert_called_once()
        assert response.recovery_summary.pending_tasks == 1


# ---------------------------------------------------------------------------
# B. RuntimeOverviewReadModel
# ---------------------------------------------------------------------------


class TestRuntimeOverviewPGProbe:
    """PG connectivity probe semantics for RuntimeOverviewReadModel."""

    @pytest.mark.asyncio
    async def test_pg_repo_probe_success_pg_health_ok(self):
        """Pg*Repository + probe success -> pg_health = OK."""
        model = RuntimeOverviewReadModel()
        provider = _make_provider()

        pg_repo = MagicMock()
        pg_repo.__class__.__name__ = "PgOrderRepository"
        pg_repo._session_maker = MagicMock()

        with patch(
            "src.application.readmodels.runtime_overview.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=True,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                account_snapshot=_make_account_snapshot(),
                exchange_gateway=None,
                execution_orchestrator=None,
                startup_reconciliation_summary=None,
                order_repo=pg_repo,
            )

        assert response.pg_health == "OK"

    @pytest.mark.asyncio
    async def test_probe_failure_pg_health_down(self):
        """Probe failure -> pg_health = DOWN."""
        model = RuntimeOverviewReadModel()
        provider = _make_provider()

        pg_repo = MagicMock()
        pg_repo.__class__.__name__ = "PgOrderRepository"
        pg_repo._session_maker = MagicMock()

        with patch(
            "src.application.readmodels.runtime_overview.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=False,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                account_snapshot=_make_account_snapshot(),
                exchange_gateway=None,
                execution_orchestrator=None,
                startup_reconciliation_summary=None,
                order_repo=pg_repo,
            )

        assert response.pg_health == "DOWN"

    @pytest.mark.asyncio
    async def test_backend_summary_uses_actual_repo_class_name(self):
        """backend_summary reflects actual repo class, not env config."""
        model = RuntimeOverviewReadModel()
        provider = _make_provider(order_backend="sqlite", position_backend="sqlite")

        pg_order_repo = MagicMock()
        pg_order_repo.__class__.__name__ = "PgOrderRepository"
        pg_order_repo._session_maker = MagicMock()

        with patch(
            "src.application.readmodels.runtime_overview.probe_pg_connectivity",
            new_callable=AsyncMock, return_value=True,
        ):
            response = await model.build(
                runtime_config_provider=provider,
                account_snapshot=_make_account_snapshot(),
                exchange_gateway=None,
                execution_orchestrator=None,
                startup_reconciliation_summary=None,
                order_repo=pg_order_repo,
            )

        assert "order=postgres" in response.backend_summary