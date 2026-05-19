"""Tests for controlled entry once-per-session guard and multi-cycle reset behavior.

TC-TINY-001D-4: Verifies that the controlled entry endpoint enforces a strict
once-per-session guard, and that restarting the process (module re-import) resets it.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def _reset_guard():
    """Reset the module-level _CONTROLLED_ENTRY_EXECUTED flag before each test."""
    import src.interfaces.api_console_runtime as mod
    original = mod._CONTROLLED_ENTRY_EXECUTED
    mod._CONTROLLED_ENTRY_EXECUTED = False
    yield mod
    mod._CONTROLLED_ENTRY_EXECUTED = original


def _mock_request():
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "testclient"
    req.body = AsyncMock(return_value=b"")  # empty body passes _reject_controlled_entry_body
    return req


def _mock_api_module(*, testnet=True, profile_name="sim1_eth_runtime"):
    """Build a mock api module with _runtime_config_provider for Gate 3+4."""
    resolved = MagicMock()
    resolved.environment.exchange_testnet = testnet
    resolved.profile_name = profile_name

    provider = MagicMock()
    provider.resolved_config = resolved

    api_mod = MagicMock()
    api_mod._runtime_config_provider = provider
    return api_mod


@pytest.mark.asyncio
async def test_controlled_entry_rejected_when_already_executed(_reset_guard, monkeypatch):
    """Gate 6 (once-per-session) returns 409 when _CONTROLLED_ENTRY_EXECUTED is True."""
    mod = _reset_guard
    mod._CONTROLLED_ENTRY_EXECUTED = True
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")

    mock_api = _mock_api_module()
    with patch.object(mod, "_load_api_module", return_value=mock_api):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await mod.execute_controlled_entry(_mock_request())
        assert exc_info.value.status_code == 409
        assert "already executed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_controlled_entry_rejected_when_test_injection_disabled(_reset_guard, monkeypatch):
    """Gate 1 (env flag) returns 403 when RUNTIME_TEST_SIGNAL_INJECTION_ENABLED is off."""
    mod = _reset_guard
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await mod.execute_controlled_entry(_mock_request())
    assert exc_info.value.status_code == 403
    assert "disabled" in exc_info.value.detail


@pytest.mark.asyncio
async def test_controlled_entry_rejected_when_control_api_disabled(_reset_guard, monkeypatch):
    """Gate 2 (control API) returns 403 when RUNTIME_CONTROL_API_ENABLED is off."""
    mod = _reset_guard
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await mod.execute_controlled_entry(_mock_request())
    assert exc_info.value.status_code == 403
    assert "disabled" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_guard_resets_on_module_reimport():
    """Simulating a process restart: re-importing the module resets the guard."""
    import src.interfaces.api_console_runtime as mod

    mod._CONTROLLED_ENTRY_EXECUTED = True
    assert mod._CONTROLLED_ENTRY_EXECUTED is True

    importlib.reload(mod)
    assert mod._CONTROLLED_ENTRY_EXECUTED is False

    mod._CONTROLLED_ENTRY_EXECUTED = False


@pytest.mark.asyncio
async def test_guard_blocks_after_all_prior_gates_pass(_reset_guard, monkeypatch):
    """Gate 6 (session guard) returns 409 when all prior gates (1-5) pass."""
    mod = _reset_guard
    mod._CONTROLLED_ENTRY_EXECUTED = True
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")

    mock_api = _mock_api_module()
    with patch.object(mod, "_load_api_module", return_value=mock_api):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await mod.execute_controlled_entry(_mock_request())
        assert exc_info.value.status_code == 409
        assert "already executed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejected_when_not_testnet(_reset_guard, monkeypatch):
    """Gate 3 (testnet check) returns 403 when exchange_testnet is False."""
    mod = _reset_guard
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")

    mock_api = _mock_api_module(testnet=False)
    with patch.object(mod, "_load_api_module", return_value=mock_api):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await mod.execute_controlled_entry(_mock_request())
        assert exc_info.value.status_code == 403
        assert "EXCHANGE_TESTNET" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejected_when_wrong_profile(_reset_guard, monkeypatch):
    """Gate 4 (profile check) returns 403 when profile is not sim1_eth_runtime."""
    mod = _reset_guard
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "true")

    mock_api = _mock_api_module(profile_name="tiny_live_50u_eth")
    with patch.object(mod, "_load_api_module", return_value=mock_api):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await mod.execute_controlled_entry(_mock_request())
        assert exc_info.value.status_code == 403
        assert "sim1_eth_runtime" in exc_info.value.detail
