"""Tests for api_console_runtime._get_account_snapshot fallback logic.

Covers:
C. api_console_runtime.py
  1. _account_getter exists -> uses _account_getter()
  2. _account_getter empty -> falls back to _exchange_gateway.get_account_snapshot()
  3. gateway also unavailable -> returns None, no error
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.interfaces.api_console_runtime import _get_account_snapshot


def _make_snapshot():
    """Create a mock AccountSnapshot."""
    snap = MagicMock()
    snap.total_balance = Decimal("10000")
    snap.available_balance = Decimal("9000")
    snap.unrealized_pnl = Decimal("0")
    snap.timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    snap.positions = []
    return snap


class TestGetAccountSnapshot:
    """_get_account_snapshot fallback logic tests."""

    def test_account_getter_exists_and_returns_snapshot(self):
        """_account_getter exists -> uses it, ignores gateway."""
        api_module = MagicMock()
        snapshot = _make_snapshot()
        api_module._account_getter = lambda: snapshot
        api_module._exchange_gateway = MagicMock()

        result = _get_account_snapshot(api_module)

        assert result is snapshot
        # gateway.get_account_snapshot should NOT be called
        api_module._exchange_gateway.get_account_snapshot.assert_not_called()

    def test_account_getter_none_falls_back_to_gateway(self):
        """_account_getter is None -> falls back to gateway.get_account_snapshot()."""
        api_module = MagicMock()
        api_module._account_getter = None
        snapshot = _make_snapshot()
        gateway = MagicMock()
        gateway.get_account_snapshot = MagicMock(return_value=snapshot)
        api_module._exchange_gateway = gateway

        result = _get_account_snapshot(api_module)

        assert result is snapshot
        gateway.get_account_snapshot.assert_called_once()

    def test_account_getter_empty_string_falls_back_to_gateway(self):
        """_account_getter is falsy (empty string) -> falls back to gateway."""
        api_module = MagicMock()
        api_module._account_getter = ""
        snapshot = _make_snapshot()
        gateway = MagicMock()
        gateway.get_account_snapshot = MagicMock(return_value=snapshot)
        api_module._exchange_gateway = gateway

        result = _get_account_snapshot(api_module)

        assert result is snapshot
        gateway.get_account_snapshot.assert_called_once()

    def test_gateway_exception_returns_none(self):
        """gateway.get_account_snapshot() raises -> returns None, no error."""
        api_module = MagicMock()
        api_module._account_getter = None
        gateway = MagicMock()
        gateway.get_account_snapshot = MagicMock(side_effect=RuntimeError("connection lost"))
        api_module._exchange_gateway = gateway

        result = _get_account_snapshot(api_module)

        assert result is None

    def test_no_account_getter_no_gateway_returns_none(self):
        """Both _account_getter and _exchange_gateway unavailable -> returns None."""
        api_module = MagicMock()
        api_module._account_getter = None
        api_module._exchange_gateway = None

        result = _get_account_snapshot(api_module)

        assert result is None

    def test_gateway_without_get_account_snapshot_returns_none(self):
        """Gateway exists but lacks get_account_snapshot method -> returns None."""
        api_module = MagicMock()
        api_module._account_getter = None
        gateway = MagicMock(spec=[])  # empty spec = no methods
        api_module._exchange_gateway = gateway

        result = _get_account_snapshot(api_module)

        assert result is None