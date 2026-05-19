from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from src.application.periodic_reconciliation import run_periodic_reconciliation


@dataclass
class _Mismatch:
    symbol: str
    mismatch_type: str
    severity: str
    reason: str
    metadata: dict = field(default_factory=dict)


@dataclass
class _Result:
    symbol: str
    checked_at: int
    mismatches: list[_Mismatch] = field(default_factory=list)


class _FakeReconciliationService:
    def __init__(
        self,
        shutdown_event: asyncio.Event,
        *,
        mismatches_by_symbol: dict[str, list[_Mismatch]] | None = None,
        failures: set[str] | None = None,
        stop_after_calls: int | None = None,
    ) -> None:
        self.shutdown_event = shutdown_event
        self.mismatches_by_symbol = mismatches_by_symbol or {}
        self.failures = failures or set()
        self.stop_after_calls = stop_after_calls
        self.calls: list[str] = []
        self.block_calls = 0
        self.recovery_calls = 0
        self.autofix_calls = 0

    async def build_read_model(self, symbol: str) -> _Result:
        self.calls.append(symbol)
        if symbol in self.failures:
            raise RuntimeError(f"{symbol} failed")
        if self.stop_after_calls is not None and len(self.calls) >= self.stop_after_calls:
            self.shutdown_event.set()
        return _Result(
            symbol=symbol,
            checked_at=123,
            mismatches=self.mismatches_by_symbol.get(symbol, []),
        )

    async def block_symbol(self, _symbol: str) -> None:
        self.block_calls += 1
        raise AssertionError("periodic reconciliation must not block symbols")

    async def create_recovery_task(self, _symbol: str) -> None:
        self.recovery_calls += 1
        raise AssertionError("periodic reconciliation must not create recovery tasks")

    async def auto_fix(self, _symbol: str) -> None:
        self.autofix_calls += 1
        raise AssertionError("periodic reconciliation must not auto-fix state")


class _SlowService:
    async def build_read_model(self, _symbol: str) -> _Result:
        await asyncio.sleep(60)
        return _Result(symbol=_symbol, checked_at=123)


class _FakeProtectionHealthMonitor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def handle_read_model_result(self, result: _Result, *, source: str) -> None:
        self.calls.append((result.symbol, source))


class _FakeExternalCloseMonitor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def handle_read_model_result(self, result: _Result, *, source: str) -> None:
        self.calls.append((result.symbol, source))


@pytest.mark.asyncio
async def test_loop_calls_build_read_model_after_startup_delay():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)

    task = asyncio.create_task(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0.05,
            interval_seconds=60,
        )
    )

    await asyncio.sleep(0.01)
    assert service.calls == []

    await asyncio.wait_for(task, timeout=1)
    assert service.calls == ["ETH/USDT:USDT"]


@pytest.mark.asyncio
async def test_loop_calls_each_symbol_once_per_cycle():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=2)

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT", "BTC/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert service.calls == ["ETH/USDT:USDT", "BTC/USDT:USDT"]


@pytest.mark.asyncio
async def test_loop_passes_read_model_to_protection_health_monitor():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)
    monitor = _FakeProtectionHealthMonitor()

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            protection_health_monitor=monitor,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert monitor.calls == [("ETH/USDT:USDT", "periodic")]


@pytest.mark.asyncio
async def test_loop_passes_read_model_to_external_close_monitor_before_protection_health():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)
    protection_monitor = _FakeProtectionHealthMonitor()
    external_monitor = _FakeExternalCloseMonitor()

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            protection_health_monitor=protection_monitor,
            external_close_monitor=external_monitor,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert external_monitor.calls == [("ETH/USDT:USDT", "periodic")]
    assert protection_monitor.calls == [("ETH/USDT:USDT", "periodic")]


@pytest.mark.asyncio
async def test_shutdown_event_before_startup_delay_exits_without_calling_service():
    shutdown_event = asyncio.Event()
    shutdown_event.set()
    service = _FakeReconciliationService(shutdown_event)

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=60,
            interval_seconds=60,
        ),
        timeout=0.2,
    )

    assert service.calls == []


@pytest.mark.asyncio
async def test_interval_wait_exits_quickly_when_shutdown_is_set():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=0.2,
    )

    assert service.calls == ["ETH/USDT:USDT"]


@pytest.mark.asyncio
async def test_single_symbol_failure_does_not_stop_later_symbols(caplog):
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(
        shutdown_event,
        failures={"ETH/USDT:USDT"},
        stop_after_calls=2,
    )
    caplog.set_level("ERROR")

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT", "BTC/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert service.calls == ["ETH/USDT:USDT", "BTC/USDT:USDT"]
    assert "Periodic reconciliation read model failed" in caplog.text


@pytest.mark.asyncio
async def test_mismatch_result_logs_warning(caplog):
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(
        shutdown_event,
        mismatches_by_symbol={
            "ETH/USDT:USDT": [
                _Mismatch(
                    symbol="ETH/USDT:USDT",
                    mismatch_type="missing_sl_protection",
                    severity="SEVERE",
                    reason="No SL protection.",
                )
            ]
        },
        stop_after_calls=1,
    )
    caplog.set_level("WARNING")

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert "Periodic reconciliation mismatches" in caplog.text
    assert "missing_sl_protection" in caplog.text


@pytest.mark.asyncio
async def test_consistent_result_does_not_log_warning(caplog):
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)
    caplog.set_level("INFO")

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert "Periodic reconciliation consistent" in caplog.text
    assert "Periodic reconciliation mismatches" not in caplog.text


@pytest.mark.asyncio
async def test_loop_does_not_call_block_recovery_or_autofix():
    shutdown_event = asyncio.Event()
    service = _FakeReconciliationService(shutdown_event, stop_after_calls=1)

    await asyncio.wait_for(
        run_periodic_reconciliation(
            service,
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        ),
        timeout=1,
    )

    assert service.block_calls == 0
    assert service.recovery_calls == 0
    assert service.autofix_calls == 0


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed():
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        run_periodic_reconciliation(
            _SlowService(),
            ["ETH/USDT:USDT"],
            shutdown_event,
            startup_delay_seconds=0,
            interval_seconds=60,
        )
    )

    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
