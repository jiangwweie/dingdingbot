from __future__ import annotations

import pytest

from src.application.protection_health_monitor import (
    PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
    PROTECTION_MISSING_EXCHANGE_SL,
    PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.alerts: list[tuple[str, str]] = []

    async def __call__(self, title: str, message: str) -> None:
        if self.fail:
            raise RuntimeError("feishu unavailable")
        self.alerts.append((title, message))


class _MutationProbe:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, _name: str):
        def _raise(*_args, **_kwargs):
            self.calls += 1
            raise AssertionError("mutation dependency should not be called")

        return _raise


def _critical_missing_sl(local_order_id: str = "local-sl") -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="protection_local_sl_missing_on_exchange",
        severity="CRITICAL",
        reason=PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
        local_ref=local_order_id,
        exchange_ref=None,
        metadata={
            "protection_reason_code": PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE,
            "local_order_id": local_order_id,
            "has_local_position": True,
            "has_exchange_position": False,
            "manual_recovery": "manual check",
        },
    )


def _critical_position_missing_sl() -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="protection_missing_exchange_sl",
        severity="CRITICAL",
        reason=PROTECTION_MISSING_EXCHANGE_SL,
        local_ref=SYMBOL,
        exchange_ref=SYMBOL,
        metadata={
            "protection_reason_code": PROTECTION_MISSING_EXCHANGE_SL,
            "exchange_position_qty": "1",
            "has_local_position": True,
            "has_exchange_position": True,
            "manual_recovery": "manual check",
        },
    )


def _critical_orphan_reduce_only() -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="protection_orphan_reduce_only_order",
        severity="CRITICAL",
        reason=PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
        exchange_ref="ex-orphan",
        metadata={
            "protection_reason_code": PROTECTION_ORPHAN_REDUCE_ONLY_ORDER,
            "exchange_order_id": "ex-orphan",
            "reduce_only": True,
            "has_local_position": False,
            "has_exchange_position": False,
            "manual_recovery": "manual check",
        },
    )


def _data_hygiene_missing_sl(local_order_id: str) -> ReconciliationMismatch:
    return ReconciliationMismatch(
        symbol=SYMBOL,
        mismatch_type="protection_local_sl_missing_on_exchange",
        severity="HIGH",
        reason=PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE,
        local_ref=local_order_id,
        exchange_ref=None,
        metadata={
            "protection_reason_code": PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE,
            "local_order_id": local_order_id,
            "has_local_position": False,
            "has_exchange_position": False,
            "manual_recovery": "manual data hygiene",
        },
    )


def _result(mismatches: list[ReconciliationMismatch]) -> ReconciliationReadModelResult:
    return ReconciliationReadModelResult(
        symbol=SYMBOL,
        checked_at=1,
        mismatches=mismatches,
    )


@pytest.mark.asyncio
async def test_critical_mismatch_blocks_symbol_sends_summary_alert_and_emits_trace():
    orchestrator = _FakeOrchestrator()
    trace_service = _FakeTraceService()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        trace_service=trace_service,
        notifier=notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result([_critical_position_missing_sl()]),
        source="startup",
    )

    assert orchestrator.blocks
    assert orchestrator.blocks[0][0] == SYMBOL
    assert orchestrator.blocks[0][1] == PROTECTION_MISSING_EXCHANGE_SL
    assert orchestrator.blocks[0][2]["action"] == "block_new_entries"
    assert notifier.alerts
    assert "[P0]" in notifier.alerts[0][0]
    assert trace_service.events
    assert trace_service.events[0]["event_type"] == "control.protection_health_block"
    assert trace_service.events[0]["decision"] == "deny_new_entries"
    assert trace_service.events[0]["reason"] == PROTECTION_MISSING_EXCHANGE_SL


@pytest.mark.asyncio
async def test_many_local_sl_missing_without_position_is_data_hygiene_summary_only():
    orchestrator = _FakeOrchestrator()
    trace_service = _FakeTraceService()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        trace_service=trace_service,
        notifier=notifier,
        external_alerts_enabled=True,
    )
    mismatches = [_data_hygiene_missing_sl(f"local-sl-{idx}") for idx in range(1852)]

    await monitor.handle_read_model_result(_result(mismatches), source="startup")

    assert orchestrator.blocks == []
    assert notifier.alerts == []
    assert len(trace_service.events) == 1
    event = trace_service.events[0]
    assert event["event_type"] == "risk.protection_health_check"
    assert event["decision"] == "report_only"
    assert event["reason"] == PROTECTION_DATA_HYGIENE_LOCAL_SL_MISSING_ON_EXCHANGE
    assert event["metadata"]["count"] == 1852
    assert len(event["metadata"]["sample_local_order_ids"]) == 10


@pytest.mark.asyncio
async def test_multiple_local_order_ids_same_reason_emit_one_summary_alert():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
        external_alerts_enabled=True,
    )
    mismatches = [_critical_missing_sl(f"local-sl-{idx}") for idx in range(20)]

    await monitor.handle_read_model_result(_result(mismatches), source="startup")

    assert len(orchestrator.blocks) == 1
    assert orchestrator.blocks[0][2]["count"] == 20
    assert len(orchestrator.blocks[0][2]["sample_local_order_ids"]) == 10
    assert len(notifier.alerts) == 1


@pytest.mark.asyncio
async def test_external_alerts_disabled_skips_notifier_but_keeps_block_and_trace():
    orchestrator = _FakeOrchestrator()
    trace_service = _FakeTraceService()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        trace_service=trace_service,
        notifier=notifier,
    )

    await monitor.handle_read_model_result(
        _result([_critical_position_missing_sl()]),
        source="startup",
    )

    assert len(orchestrator.blocks) == 1
    assert len(trace_service.events) == 1
    assert notifier.alerts == []


@pytest.mark.asyncio
async def test_external_alerts_enabled_respects_per_check_cap():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
        external_alerts_enabled=True,
        max_external_alerts_per_check=1,
    )

    await monitor.handle_read_model_result(
        _result([_critical_position_missing_sl(), _critical_orphan_reduce_only()]),
        source="startup",
    )

    assert len(orchestrator.blocks) == 2
    assert len(notifier.alerts) == 1


@pytest.mark.asyncio
async def test_notifier_failure_does_not_prevent_block():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier(fail=True)
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result([_critical_position_missing_sl()]),
        source="startup",
    )

    assert len(orchestrator.blocks) == 1


@pytest.mark.asyncio
async def test_periodic_repeated_same_mismatch_dedupes_external_alert():
    orchestrator = _FakeOrchestrator()
    notifier = _FakeNotifier()
    monitor = ProtectionHealthMonitor(
        execution_orchestrator=orchestrator,
        notifier=notifier,
        external_alerts_enabled=True,
    )
    result = _result([_critical_position_missing_sl()])

    await monitor.handle_read_model_result(result, source="periodic")
    await monitor.handle_read_model_result(result, source="periodic")

    assert len(orchestrator.blocks) == 2
    assert len(notifier.alerts) == 1


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
        external_alerts_enabled=True,
    )

    await monitor.handle_read_model_result(
        _result([_critical_position_missing_sl()]),
        source="startup",
    )

    assert exchange_probe.calls == 0
    assert lifecycle_probe.calls == 0
    assert projection_probe.calls == 0
    assert capital_probe.calls == 0
