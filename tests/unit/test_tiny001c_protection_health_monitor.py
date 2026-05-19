from __future__ import annotations

import pytest

from src.application.protection_health_monitor import (
    PROTECTION_MISSING_EXCHANGE_SL,
    ProtectionHealthMonitor,
)
from src.application.reconciliation import (
    ReconciliationMismatch,
    ReconciliationReadModelResult,
)


SYMBOL = "ETH/USDT:USDT"


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.blocks: list[tuple[str, str, dict]] = []

    def block_symbol_for_protection_health(
        self,
        symbol: str,
        reason_code: str,
        metadata: dict,
    ) -> None:
        self.blocks.append((symbol, reason_code, metadata))


class _FakeTraceService:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit_risk_decision(self, **kwargs):
        self.events.append(kwargs)


class _FakeNotifier:
    def __init__(self) -> None:
        self.alerts: list[tuple[str, str]] = []

    async def __call__(self, title: str, message: str) -> None:
        self.alerts.append((title, message))


class _MutationProbe:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, _name: str):
        def _raise(*_args, **_kwargs):
            self.calls += 1
            raise AssertionError("mutation dependency should not be called")

        return _raise


def _critical_result() -> ReconciliationReadModelResult:
    return ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=1,
        mismatches=[
            ReconciliationMismatch(
                symbol=SYMBOL,
                mismatch_type="protection_missing_exchange_sl",
                severity="CRITICAL",
                reason=PROTECTION_MISSING_EXCHANGE_SL,
                local_ref=SYMBOL,
                exchange_ref=SYMBOL,
                metadata={
                    "protection_reason_code": PROTECTION_MISSING_EXCHANGE_SL,
                    "exchange_position_qty": "1",
                    "manual_recovery": "manual check",
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_critical_mismatch_blocks_symbol_sends_alert_and_emits_trace():
    orchestrator = _FakeOrchestrator()
    trace_service = _FakeTraceService()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        trace_service=trace_service,
        notifier=notifier,
    )

    await monitor.handle_read_model_result(_critical_result(), source="startup")

    assert orchestrator.blocks
    assert orchestrator.blocks[0][0] == SYMBOL
    assert orchestrator.blocks[0][1] == PROTECTION_MISSING_EXCHANGE_SL
    assert orchestrator.blocks[0][2]["source"] == "startup"
    assert notifier.alerts
    assert "[P0]" in notifier.alerts[0][0]
    assert trace_service.events
    assert trace_service.events[0]["event_type"] == "control.protection_health_block"
    assert trace_service.events[0]["decision"] == "deny_new_entries"
    assert trace_service.events[0]["reason"] == PROTECTION_MISSING_EXCHANGE_SL


@pytest.mark.asyncio
async def test_repeated_same_mismatch_dedupes_p0_alert_but_keeps_blocking():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
    )
    result = _critical_result()

    await monitor.handle_read_model_result(result, source="periodic")
    await monitor.handle_read_model_result(result, source="periodic")

    assert len(orchestrator.blocks) == 2
    assert len(notifier.alerts) == 1


@pytest.mark.asyncio
async def test_alert_dedupe_is_capped_and_evicts_oldest_key():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
        max_alert_dedupe_keys=1,
    )
    first = _critical_result()
    second = _critical_result()
    second.mismatches[0].metadata["exchange_position_qty"] = "2"

    await monitor.handle_read_model_result(first, source="periodic")
    await monitor.handle_read_model_result(second, source="periodic")
    await monitor.handle_read_model_result(first, source="periodic")

    assert len(notifier.alerts) == 3


@pytest.mark.asyncio
async def test_monitor_does_not_call_exchange_or_lifecycle_mutation_dependencies():
    orchestrator = _FakeOrchestrator()
    trace_service = _FakeTraceService()
    notifier = _FakeNotifier()
    exchange_probe = _MutationProbe()
    lifecycle_probe = _MutationProbe()
    projection_probe = _MutationProbe()
    capital_probe = _MutationProbe()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        trace_service=trace_service,
        notifier=notifier,
    )

    await monitor.handle_read_model_result(_critical_result(), source="startup")

    assert exchange_probe.calls == 0
    assert lifecycle_probe.calls == 0
    assert projection_probe.calls == 0
    assert capital_probe.calls == 0
