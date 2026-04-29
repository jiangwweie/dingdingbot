"""
Tests for API lifespan execution runtime assembly.

Coverage:
1. validate_pg_core_configuration() raises ValueError when postgres backend
   is selected but PG_DATABASE_URL is missing
2. lifespan startup assembles standalone runtime in standalone uvicorn mode
3. lifespan shutdown resets standalone-created globals to None
4. Repeated startup can re-assemble after shutdown (no stale state)

These tests use mocks to avoid real database/exchange connections.
"""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager


class TestValidatePgCoreConfiguration:
    """Tests for validate_pg_core_configuration() in database.py."""

    def test_sqlite_backend_no_error_without_pg_url(self, monkeypatch):
        """SQLite backend should not require PG_DATABASE_URL."""
        # Clear PG_DATABASE_URL
        monkeypatch.delenv("PG_DATABASE_URL", raising=False)
        monkeypatch.setenv("CORE_ORDER_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_EXECUTION_INTENT_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_POSITION_BACKEND", "sqlite")

        # Re-import to pick up new env vars
        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        # Should not raise
        from src.infrastructure.database import validate_pg_core_configuration
        validate_pg_core_configuration()  # No exception

    def test_postgres_backend_raises_without_pg_url(self, monkeypatch):
        """Postgres backend requires PG_DATABASE_URL."""
        monkeypatch.delenv("PG_DATABASE_URL", raising=False)
        monkeypatch.setenv("CORE_ORDER_BACKEND", "postgres")
        monkeypatch.setenv("CORE_EXECUTION_INTENT_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_POSITION_BACKEND", "sqlite")

        # Re-import to pick up new env vars
        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        from src.infrastructure.database import validate_pg_core_configuration
        with pytest.raises(ValueError, match="PG_DATABASE_URL 未配置"):
            validate_pg_core_configuration()

    def test_postgres_backend_raises_with_non_pg_url(self, monkeypatch):
        """Postgres backend requires PostgreSQL DSN (not sqlite/mysql)."""
        monkeypatch.setenv("PG_DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("CORE_ORDER_BACKEND", "postgres")
        monkeypatch.setenv("CORE_EXECUTION_INTENT_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_POSITION_BACKEND", "sqlite")

        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        from src.infrastructure.database import validate_pg_core_configuration
        with pytest.raises(ValueError, match="必须是 PostgreSQL DSN"):
            validate_pg_core_configuration()

    def test_invalid_backend_value_raises(self, monkeypatch):
        """Invalid backend value (not sqlite/postgres) raises error."""
        monkeypatch.delenv("PG_DATABASE_URL", raising=False)
        monkeypatch.setenv("CORE_ORDER_BACKEND", "mysql")  # Invalid
        monkeypatch.setenv("CORE_EXECUTION_INTENT_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_POSITION_BACKEND", "sqlite")

        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        from src.infrastructure.database import validate_pg_core_configuration
        with pytest.raises(ValueError, match="核心后端配置非法"):
            validate_pg_core_configuration()

    def test_mixed_backends_with_postgres_requires_pg_url(self, monkeypatch):
        """If any backend is postgres, PG_DATABASE_URL is required."""
        monkeypatch.delenv("PG_DATABASE_URL", raising=False)
        monkeypatch.setenv("CORE_ORDER_BACKEND", "sqlite")
        monkeypatch.setenv("CORE_EXECUTION_INTENT_BACKEND", "postgres")  # This one
        monkeypatch.setenv("CORE_POSITION_BACKEND", "sqlite")

        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        from src.infrastructure.database import validate_pg_core_configuration
        with pytest.raises(ValueError, match="PG_DATABASE_URL 未配置"):
            validate_pg_core_configuration()


class TestLifespanStandaloneRuntime:
    """Tests for lifespan() standalone runtime assembly and cleanup."""

    @pytest.fixture(autouse=True)
    def reset_api_globals(self):
        """Reset api.py global variables before and after each test."""
        # Import api module to access globals
        from src.interfaces import api

        # Store original values
        original_values = {
            '_exchange_gateway': api._exchange_gateway,
            '_capital_protection': api._capital_protection,
            '_account_service': api._account_service,
            '_execution_orchestrator': api._execution_orchestrator,
            '_repository': api._repository,
            '_config_entry_repo': api._config_entry_repo,
            '_order_repo': api._order_repo,
            '_execution_intent_repo': api._execution_intent_repo,
            '_audit_logger': api._audit_logger,
            '_order_lifecycle_service': api._order_lifecycle_service,
            '_config_manager': api._config_manager,
        }

        # Reset to None before test
        api._exchange_gateway = None
        api._capital_protection = None
        api._account_service = None
        api._execution_orchestrator = None
        api._repository = None
        api._config_entry_repo = None
        api._order_repo = None
        api._execution_intent_repo = None
        api._audit_logger = None
        api._order_lifecycle_service = None
        api._config_manager = None

        # Also reset api_config_globals
        from src.interfaces import api_config_globals
        api_config_globals._config_manager = None

        yield

        # Restore original values after test
        for name, value in original_values.items():
            setattr(api, name, value)

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock ConfigManager with minimal required interface."""
        mock_cm = MagicMock()
        mock_cm.get_user_config = AsyncMock()
        mock_cm.close = AsyncMock()

        # Mock user config with exchange settings
        user_config = MagicMock()
        user_config.exchange = MagicMock()
        user_config.exchange.name = "binance"
        user_config.exchange.api_key = "test_key"
        user_config.exchange.api_secret = "test_secret"
        user_config.exchange.testnet = True
        user_config.notification = MagicMock()
        user_config.notification.channels = []

        mock_cm.get_user_config.return_value = user_config
        mock_cm.build_capital_protection_config = MagicMock(return_value=MagicMock())

        return mock_cm

    @pytest.mark.asyncio
    async def test_lifespan_assembles_standalone_runtime(
        self, mock_config_manager, monkeypatch
    ):
        """In standalone uvicorn mode, lifespan() should assemble execution runtime."""
        from src.interfaces import api
        from src.interfaces import api_config_globals

        # Set config_manager so lifespan can use it
        api_config_globals._config_manager = mock_config_manager

        # Mock all external dependencies
        mock_gateway = AsyncMock()
        mock_gateway.initialize = AsyncMock()
        mock_gateway.close = AsyncMock()
        mock_gateway.set_global_order_callback = MagicMock()

        mock_account_service = MagicMock()
        mock_capital_protection = MagicMock()
        mock_orchestrator = MagicMock()

        mock_intent_repo = AsyncMock()
        mock_intent_repo.close = AsyncMock()

        mock_signal_repo = AsyncMock()
        mock_signal_repo.initialize = AsyncMock()
        mock_signal_repo.close = AsyncMock()

        mock_config_entry_repo = AsyncMock()
        mock_config_entry_repo.initialize = AsyncMock()
        mock_config_entry_repo.close = AsyncMock()

        mock_audit_logger = AsyncMock()
        mock_audit_logger.stop = AsyncMock()

        mock_lifecycle_service = AsyncMock()
        mock_lifecycle_service.stop = AsyncMock()

        mock_order_repo = AsyncMock()
        mock_order_repo.initialize = AsyncMock()
        mock_order_repo.close = AsyncMock()
        mock_order_repo.set_exchange_gateway = MagicMock()
        mock_order_repo.set_audit_logger = MagicMock()

        mock_position_repo = AsyncMock()
        mock_position_repo.initialize = AsyncMock()
        mock_position_repo.close = AsyncMock()

        with patch("src.infrastructure.exchange_gateway.ExchangeGateway", return_value=mock_gateway), \
             patch("src.application.account_service.BinanceAccountService", return_value=mock_account_service), \
             patch("src.application.capital_protection.CapitalProtectionManager", return_value=mock_capital_protection), \
             patch("src.application.execution_orchestrator.ExecutionOrchestrator", return_value=mock_orchestrator), \
             patch("src.infrastructure.notifier.get_notification_service") as mock_notifier_svc, \
             patch("src.interfaces.api.validate_pg_core_configuration", return_value=None), \
             patch("src.interfaces.api.create_runtime_signal_repository", return_value=mock_signal_repo), \
             patch("src.infrastructure.config_entry_repository.ConfigEntryRepository", return_value=mock_config_entry_repo), \
             patch("src.interfaces.api.create_runtime_order_repository", return_value=mock_order_repo), \
             patch("src.interfaces.api.create_execution_intent_repository", return_value=mock_intent_repo), \
             patch("src.interfaces.api.create_runtime_position_repository", return_value=mock_position_repo), \
             patch("src.application.order_audit_logger.OrderAuditLogger", return_value=mock_audit_logger), \
             patch("src.infrastructure.order_audit_repository.OrderAuditLogRepository") as mock_audit_repo_cls, \
             patch("src.application.order_lifecycle_service.OrderLifecycleService", return_value=mock_lifecycle_service):

            mock_notifier_svc.return_value = MagicMock()
            mock_notifier_svc.return_value.setup_channels = MagicMock()
            mock_audit_repo_cls.return_value.initialize = AsyncMock()

            # Create a FastAPI app with the lifespan
            from fastapi import FastAPI
            app = FastAPI(lifespan=api.lifespan)

            # Simulate startup/shutdown cycle
            async with api.lifespan(app):
                # Verify standalone runtime was assembled
                assert api._exchange_gateway is mock_gateway
                assert api._capital_protection is mock_capital_protection
                assert api._account_service is mock_account_service
                assert api._execution_orchestrator is mock_orchestrator

                # Verify gateway was initialized
                mock_gateway.initialize.assert_called_once()

            # After context exit (shutdown), globals should be reset
            assert api._exchange_gateway is None
            assert api._capital_protection is None
            assert api._account_service is None
            assert api._execution_orchestrator is None

            # Verify gateway was closed
            mock_gateway.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_resets_globals(self, mock_config_manager):
        """After shutdown, standalone-created globals should be None."""
        from src.interfaces import api
        from src.interfaces import api_config_globals

        api_config_globals._config_manager = mock_config_manager

        mock_gateway = AsyncMock()
        mock_gateway.initialize = AsyncMock()
        mock_gateway.close = AsyncMock()
        mock_gateway.set_global_order_callback = MagicMock()

        mock_signal_repo = AsyncMock()
        mock_signal_repo.initialize = AsyncMock()
        mock_signal_repo.close = AsyncMock()

        mock_config_entry_repo = AsyncMock()
        mock_config_entry_repo.initialize = AsyncMock()
        mock_config_entry_repo.close = AsyncMock()

        mock_intent_repo = AsyncMock()
        mock_intent_repo.close = AsyncMock()

        mock_audit_logger = AsyncMock()
        mock_audit_logger.stop = AsyncMock()

        mock_lifecycle_service = AsyncMock()
        mock_lifecycle_service.stop = AsyncMock()

        mock_order_repo = AsyncMock()
        mock_order_repo.initialize = AsyncMock()
        mock_order_repo.close = AsyncMock()
        mock_order_repo.set_exchange_gateway = MagicMock()
        mock_order_repo.set_audit_logger = MagicMock()

        mock_position_repo = AsyncMock()
        mock_position_repo.initialize = AsyncMock()
        mock_position_repo.close = AsyncMock()

        with patch("src.infrastructure.exchange_gateway.ExchangeGateway", return_value=mock_gateway), \
             patch("src.application.account_service.BinanceAccountService"), \
             patch("src.application.capital_protection.CapitalProtectionManager"), \
             patch("src.application.execution_orchestrator.ExecutionOrchestrator"), \
             patch("src.infrastructure.notifier.get_notification_service") as mock_notifier_svc, \
             patch("src.interfaces.api.validate_pg_core_configuration", return_value=None), \
             patch("src.interfaces.api.create_runtime_signal_repository", return_value=mock_signal_repo), \
             patch("src.infrastructure.config_entry_repository.ConfigEntryRepository", return_value=mock_config_entry_repo), \
             patch("src.interfaces.api.create_runtime_order_repository", return_value=mock_order_repo), \
             patch("src.interfaces.api.create_execution_intent_repository", return_value=mock_intent_repo), \
             patch("src.interfaces.api.create_runtime_position_repository", return_value=mock_position_repo), \
             patch("src.application.order_audit_logger.OrderAuditLogger", return_value=mock_audit_logger), \
             patch("src.infrastructure.order_audit_repository.OrderAuditLogRepository") as mock_audit_repo_cls, \
             patch("src.application.order_lifecycle_service.OrderLifecycleService", return_value=mock_lifecycle_service):

            mock_notifier_svc.return_value = MagicMock()
            mock_notifier_svc.return_value.setup_channels = MagicMock()
            mock_audit_repo_cls.return_value.initialize = AsyncMock()

            from fastapi import FastAPI
            app = FastAPI()

            async with api.lifespan(app):
                pass  # Just trigger startup/shutdown

            # All standalone globals should be None after shutdown
            assert api._exchange_gateway is None, "_exchange_gateway should be None after shutdown"
            assert api._capital_protection is None, "_capital_protection should be None after shutdown"
            assert api._account_service is None, "_account_service should be None after shutdown"
            assert api._execution_orchestrator is None, "_execution_orchestrator should be None after shutdown"

    @pytest.mark.asyncio
    async def test_repeated_startup_reassembles_fresh_runtime(self, mock_config_manager):
        """After shutdown, a second startup should create fresh runtime (no stale state)."""
        from src.interfaces import api
        from src.interfaces import api_config_globals

        api_config_globals._config_manager = mock_config_manager

        # First gateway instance
        mock_gateway_1 = AsyncMock()
        mock_gateway_1.initialize = AsyncMock()
        mock_gateway_1.close = AsyncMock()
        mock_gateway_1.set_global_order_callback = MagicMock()

        # Second gateway instance (for second startup)
        mock_gateway_2 = AsyncMock()
        mock_gateway_2.initialize = AsyncMock()
        mock_gateway_2.close = AsyncMock()
        mock_gateway_2.set_global_order_callback = MagicMock()

        mock_signal_repo = AsyncMock()
        mock_signal_repo.initialize = AsyncMock()
        mock_signal_repo.close = AsyncMock()

        mock_config_entry_repo = AsyncMock()
        mock_config_entry_repo.initialize = AsyncMock()
        mock_config_entry_repo.close = AsyncMock()

        mock_intent_repo = AsyncMock()
        mock_intent_repo.close = AsyncMock()

        mock_audit_logger = AsyncMock()
        mock_audit_logger.stop = AsyncMock()

        mock_lifecycle_service = AsyncMock()
        mock_lifecycle_service.stop = AsyncMock()

        mock_order_repo = AsyncMock()
        mock_order_repo.initialize = AsyncMock()
        mock_order_repo.close = AsyncMock()
        mock_order_repo.set_exchange_gateway = MagicMock()
        mock_order_repo.set_audit_logger = MagicMock()

        mock_position_repo = AsyncMock()
        mock_position_repo.initialize = AsyncMock()
        mock_position_repo.close = AsyncMock()

        gateway_factory = MagicMock(side_effect=[mock_gateway_1, mock_gateway_2])

        with patch("src.infrastructure.exchange_gateway.ExchangeGateway", gateway_factory), \
             patch("src.application.account_service.BinanceAccountService"), \
             patch("src.application.capital_protection.CapitalProtectionManager"), \
             patch("src.application.execution_orchestrator.ExecutionOrchestrator"), \
             patch("src.infrastructure.notifier.get_notification_service") as mock_notifier_svc, \
             patch("src.interfaces.api.validate_pg_core_configuration", return_value=None), \
             patch("src.interfaces.api.create_runtime_signal_repository", return_value=mock_signal_repo), \
             patch("src.infrastructure.config_entry_repository.ConfigEntryRepository", return_value=mock_config_entry_repo), \
             patch("src.interfaces.api.create_runtime_order_repository", return_value=mock_order_repo), \
             patch("src.interfaces.api.create_execution_intent_repository", return_value=mock_intent_repo), \
             patch("src.interfaces.api.create_runtime_position_repository", return_value=mock_position_repo), \
             patch("src.application.order_audit_logger.OrderAuditLogger", return_value=mock_audit_logger), \
             patch("src.infrastructure.order_audit_repository.OrderAuditLogRepository") as mock_audit_repo_cls, \
             patch("src.application.order_lifecycle_service.OrderLifecycleService", return_value=mock_lifecycle_service):

            mock_notifier_svc.return_value = MagicMock()
            mock_notifier_svc.return_value.setup_channels = MagicMock()
            mock_audit_repo_cls.return_value.initialize = AsyncMock()

            from fastapi import FastAPI
            app = FastAPI()

            # First startup/shutdown cycle
            async with api.lifespan(app):
                assert api._exchange_gateway is mock_gateway_1

            # After first shutdown
            assert api._exchange_gateway is None
            mock_gateway_1.close.assert_called_once()

            # Second startup/shutdown cycle
            async with api.lifespan(app):
                assert api._exchange_gateway is mock_gateway_2, "Second startup should create fresh gateway"

            # After second shutdown
            assert api._exchange_gateway is None
            mock_gateway_2.close.assert_called_once()

            # Verify both gateways were created (not reused)
            assert gateway_factory.call_count == 2

    @pytest.mark.asyncio
    async def test_lifespan_does_not_create_gateway_if_already_injected(self, mock_config_manager):
        """If _exchange_gateway is already set (main.py embedded mode), lifespan should not create a new one."""
        from src.interfaces import api
        from src.interfaces import api_config_globals

        api_config_globals._config_manager = mock_config_manager

        # Simulate main.py embedded mode: gateway already injected
        pre_injected_gateway = MagicMock()
        api._exchange_gateway = pre_injected_gateway

        mock_signal_repo = AsyncMock()
        mock_signal_repo.initialize = AsyncMock()
        mock_signal_repo.close = AsyncMock()

        mock_config_entry_repo = AsyncMock()
        mock_config_entry_repo.initialize = AsyncMock()
        mock_config_entry_repo.close = AsyncMock()

        mock_intent_repo = AsyncMock()
        mock_intent_repo.close = AsyncMock()

        mock_audit_logger = AsyncMock()
        mock_audit_logger.stop = AsyncMock()

        mock_lifecycle_service = AsyncMock()
        mock_lifecycle_service.stop = AsyncMock()

        mock_order_repo = AsyncMock()
        mock_order_repo.initialize = AsyncMock()
        mock_order_repo.close = AsyncMock()
        mock_order_repo.set_exchange_gateway = MagicMock()
        mock_order_repo.set_audit_logger = MagicMock()

        mock_position_repo = AsyncMock()
        mock_position_repo.initialize = AsyncMock()
        mock_position_repo.close = AsyncMock()

        with patch("src.interfaces.api.validate_pg_core_configuration", return_value=None), \
             patch("src.interfaces.api.create_runtime_signal_repository", return_value=mock_signal_repo), \
             patch("src.infrastructure.config_entry_repository.ConfigEntryRepository", return_value=mock_config_entry_repo), \
             patch("src.interfaces.api.create_runtime_order_repository", return_value=mock_order_repo), \
             patch("src.interfaces.api.create_execution_intent_repository", return_value=mock_intent_repo), \
             patch("src.interfaces.api.create_runtime_position_repository", return_value=mock_position_repo), \
             patch("src.application.order_audit_logger.OrderAuditLogger", return_value=mock_audit_logger), \
             patch("src.infrastructure.order_audit_repository.OrderAuditLogRepository") as mock_audit_repo_cls, \
             patch("src.application.order_lifecycle_service.OrderLifecycleService", return_value=mock_lifecycle_service):

            mock_audit_repo_cls.return_value.initialize = AsyncMock()

            from fastapi import FastAPI
            app = FastAPI()

            async with api.lifespan(app):
                # Gateway should remain the pre-injected one
                assert api._exchange_gateway is pre_injected_gateway

            # After shutdown, pre-injected gateway should NOT be closed
            # (because _standalone_gateway_created is False)
            assert api._exchange_gateway is pre_injected_gateway, \
                "Pre-injected gateway should not be reset by standalone shutdown"

    @pytest.mark.asyncio
    async def test_lifespan_raises_fatal_startup_error_on_pg_config_error(self, monkeypatch):
        """If validate_pg_core_configuration raises ValueError, lifespan should raise FatalStartupError."""
        from src.interfaces import api

        # Force postgres backend without PG_DATABASE_URL
        monkeypatch.delenv("PG_DATABASE_URL", raising=False)
        monkeypatch.setenv("CORE_ORDER_BACKEND", "postgres")

        # Reload database module to pick up env vars
        import importlib
        import src.infrastructure.database as db_module
        importlib.reload(db_module)

        from fastapi import FastAPI
        app = FastAPI()

        from src.domain.exceptions import FatalStartupError
        with pytest.raises(FatalStartupError, match="F-003"):
            async with api.lifespan(app):
                pass
