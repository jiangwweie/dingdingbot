"""Tests for api._get_order_repo fallback assembly — runtime PG factory focus.

Verifies:
- _get_order_repo() fallback uses create_runtime_order_repository (not create_order_repository)
- DI-injected runtime repo is returned directly without factory call
"""

from unittest.mock import AsyncMock, MagicMock, patch

from src.interfaces import api


class TestGetOrderRepoRuntimePGFactory:
    """_get_order_repo fallback 走 create_runtime_order_repository() (runtime 主链 PG)。"""

    def setup_method(self):
        self._original_order_repo = api._order_repo
        self._original_exchange_gateway = api._exchange_gateway
        self._original_audit_logger = api._audit_logger

        api._order_repo = None
        api._exchange_gateway = None
        api._audit_logger = None

    def teardown_method(self):
        api._order_repo = self._original_order_repo
        api._exchange_gateway = self._original_exchange_gateway
        api._audit_logger = self._original_audit_logger

    def test_fallback_calls_create_runtime_order_repository(self):
        """_order_repo 为 None 时走 create_runtime_order_repository()，而非通用 create_order_repository。"""
        repo = MagicMock()

        with patch(
            "src.interfaces.api.create_runtime_order_repository",
            return_value=repo,
        ) as mock_runtime_create:
            resolved = api._get_order_repo()

        assert resolved is repo
        mock_runtime_create.assert_called_once_with()

    def test_runtime_factory_injects_exchange_gateway(self):
        """runtime factory 创建的 repo 注入 exchange_gateway。"""
        repo = MagicMock()
        repo.set_exchange_gateway = MagicMock()
        gateway = MagicMock()
        api._exchange_gateway = gateway

        with patch("src.interfaces.api.create_runtime_order_repository", return_value=repo):
            resolved = api._get_order_repo()

        repo.set_exchange_gateway.assert_called_once_with(gateway)

    def test_runtime_factory_injects_audit_logger(self):
        """runtime factory 创建的 repo 注入 audit_logger。"""
        repo = MagicMock()
        repo.set_audit_logger = MagicMock()
        audit_logger = MagicMock()
        api._audit_logger = audit_logger

        with patch("src.interfaces.api.create_runtime_order_repository", return_value=repo):
            resolved = api._get_order_repo()

        repo.set_audit_logger.assert_called_once_with(audit_logger)

    def test_returns_existing_runtime_repo_when_set(self):
        """_order_repo 已设置（由 main.py 注入的 runtime PG repo）时直接返回，不走 factory。"""
        existing_repo = MagicMock()
        api._order_repo = existing_repo

        with patch("src.interfaces.api.create_runtime_order_repository") as mock_create:
            resolved = api._get_order_repo()

        assert resolved is existing_repo
        mock_create.assert_not_called()

    def test_no_gateway_skips_injection(self):
        """_exchange_gateway 为 None 时跳过 gateway 注入。"""
        repo = MagicMock()
        repo.set_exchange_gateway = MagicMock()
        repo.set_audit_logger = MagicMock()
        api._exchange_gateway = None
        api._audit_logger = MagicMock()

        with patch("src.interfaces.api.create_runtime_order_repository", return_value=repo):
            resolved = api._get_order_repo()

        repo.set_exchange_gateway.assert_not_called()
        repo.set_audit_logger.assert_called()