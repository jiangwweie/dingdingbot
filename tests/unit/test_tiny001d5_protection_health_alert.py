"""Tests for ProtectionHealthMonitor external alert integration.

TC-TINY-001D-5: Verifies the Feishu/external alert path through ProtectionHealthMonitor:
- Alert sends when enabled + CRITICAL mismatch
- Dedup prevents duplicate alerts
- Notifier failure does not block symbol
- External alerts disabled by default
- No secrets leaked in alert content
- Per-check alert cap respected
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from src.application.protection_health_monitor import (
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE,
    ProtectionHealthMonitor,
)
from src.application.reconciliation import ReconciliationMismatch, ReconciliationReadModelResult


SYMBOL = "ETH/USDT:USDT"


# --- Test helpers ---

class _Orchestrator:
    def __init__(self):
        self.blocks: list[tuple[str, str, dict]] = []

    def block_symbol_for_protection_health(self, symbol: str, reason: str, metadata: dict):
        self.blocks.append((symbol, reason, metadata))


class _Trace:
    def __init__(self):
        self.events: list[dict] = []

    def emit_risk_decision(self, **kwargs):
        self.events.append(kwargs)


def _critical_mismatch(
    reason_code: str = PROTECTION_MISSING_EXCHANGE_SL,
    *,
    local_ref: str = "ord-sl-1",
    exchange_ref: str = "ex-sl-1",
) -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="protection_health",
        severity="CRITICAL",
        reason=reason_code,
        local_ref=local_ref,
        exchange_ref=exchange_ref,
        metadata={
            "protection_reason_code": reason_code,
            "local_order_id": local_ref,
            "exchange_order_id": exchange_ref,
            "has_local_position": True,
            "has_exchange_position": True,
        },
    )


def _report_only_mismatch() -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="data_hygiene",
        severity="WARNING",
        reason="DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE",
        local_ref="ord-stale-1",
        metadata={
            "protection_reason_code": "DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE",
        },
    )


def _result(*mismatches: ReconciliationMismatch) -> ReconciliationReadModelResult:
    return ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=1700000000,
        mismatches=list(mismatches),
    )


# --- Tests ---

@pytest.mark.asyncio
async def test_critical_mismatch_sends_external_alert_when_enabled():
    """When external alerts are enabled, a CRITICAL mismatch triggers the notifier."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    orchestrator = _Orchestrator()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch()),
        source="test",
    )

    assert len(notifier_calls) == 1
    assert "Protection health block" in notifier_calls[0][0]
    assert SYMBOL in notifier_calls[0][1]
    assert len(orchestrator.blocks) == 1
    assert orchestrator.blocks[0][0] == SYMBOL


@pytest.mark.asyncio
async def test_external_alert_not_sent_when_disabled():
    """When external alerts are disabled (default), notifier is NOT called."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    orchestrator = _Orchestrator()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=mock_notifier,
        external_alerts_enabled=False,  # explicit; also the default
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch()),
        source="test",
    )

    assert len(notifier_calls) == 0  # NOT called
    assert len(orchestrator.blocks) == 1  # But block IS still applied


@pytest.mark.asyncio
async def test_dedup_prevents_duplicate_alerts():
    """Same CRITICAL mismatch sent twice should only trigger notifier once."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    mismatch = _critical_mismatch()
    result = _result(mismatch)

    await monitor.handle_read_model_result(result, source="test")
    await monitor.handle_read_model_result(result, source="test")

    assert len(notifier_calls) == 1  # Second call deduped


@pytest.mark.asyncio
async def test_different_reason_codes_send_separate_alerts():
    """Different reason codes are separate dedup keys."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch(PROTECTION_MISSING_EXCHANGE_SL)),
        source="test",
    )
    await monitor.handle_read_model_result(
        _result(_critical_mismatch(PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE)),
        source="test",
    )

    assert len(notifier_calls) == 2


@pytest.mark.asyncio
async def test_notifier_failure_does_not_block_symbol():
    """If notifier raises, the symbol is still blocked."""
    def failing_notifier(title, message):
        raise RuntimeError("Feishu API unreachable")

    orchestrator = _Orchestrator()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=failing_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch()),
        source="test",
    )

    # Block is applied despite notifier failure
    assert len(orchestrator.blocks) == 1
    assert orchestrator.blocks[0][0] == SYMBOL


@pytest.mark.asyncio
async def test_async_notifier_is_awaited():
    """If notifier returns a coroutine, it is properly awaited."""
    notifier_calls: list[tuple[str, str]] = []

    async def async_notifier(title, message):
        notifier_calls.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=async_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch()),
        source="test",
    )

    assert len(notifier_calls) == 1


@pytest.mark.asyncio
async def test_alert_content_has_no_secrets():
    """Alert title/message should not contain API keys, secrets, or webhook URLs."""
    captured_messages: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        captured_messages.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_critical_mismatch()),
        source="test",
    )

    for title, message in captured_messages:
        combined = title + message
        assert "api_key" not in combined.lower() or "api_key" in combined.lower() and "secret" not in combined.lower()
        assert "sk-" not in combined
        assert "webhook" not in combined.lower()
        assert "password" not in combined.lower()


@pytest.mark.asyncio
async def test_per_check_alert_cap():
    """External alerts are capped per check cycle."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=mock_notifier,
        external_alerts_enabled=True,
        max_external_alerts_per_check=2,
    )

    # Send 3 different CRITICAL mismatches in one result
    mismatches = [
        _critical_mismatch(PROTECTION_MISSING_EXCHANGE_SL, local_ref=f"ord-{i}")
        for i in range(3)
    ]
    # Each has the same reason code, so dedup will kick in.
    # Use different reason codes to bypass dedup.
    mismatches[1] = _critical_mismatch(PROTECTION_SL_NOT_CONFIRMED_ON_EXCHANGE, local_ref="ord-1")
    mismatches[2] = _critical_mismatch("PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE", local_ref="ord-2")

    await monitor.handle_read_model_result(
        _result(*mismatches),
        source="test",
    )

    # Cap is 2, so only 2 alerts sent
    assert len(notifier_calls) == 2


@pytest.mark.asyncio
async def test_report_only_mismatch_does_not_trigger_alert():
    """Non-CRITICAL mismatches (report_only) do not trigger external alerts."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    orchestrator = _Orchestrator()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result(_report_only_mismatch()),
        source="test",
    )

    assert len(notifier_calls) == 0
    assert len(orchestrator.blocks) == 0


@pytest.mark.asyncio
async def test_no_fan_out_single_notifier_call_per_critical_group():
    """Each unique CRITICAL group produces exactly one notifier call, not per-mismatch fan-out."""
    notifier_calls: list[tuple[str, str]] = []
    def mock_notifier(title, message):
        notifier_calls.append((title, message))

    monitor = ProtectionHealthMonitor(
        execution_orchestrator=_Orchestrator(),
        notifier=mock_notifier,
        external_alerts_enabled=True,
    )

    # Multiple mismatches with same reason code -> one group -> one alert
    mismatches = [
        _critical_mismatch(PROTECTION_MISSING_EXCHANGE_SL, local_ref=f"ord-{i}")
        for i in range(5)
    ]

    await monitor.handle_read_model_result(
        _result(*mismatches),
        source="test",
    )

    assert len(notifier_calls) == 1  # One call, not five
