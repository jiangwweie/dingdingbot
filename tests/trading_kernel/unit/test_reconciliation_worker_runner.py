from __future__ import annotations

import argparse

import pytest

import scripts.trading_kernel.run_reconciliation_worker_once as runner
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerResult,
    ReconciliationWorkerStatus,
)


@pytest.mark.asyncio
async def test_runner_always_delegates_durable_fee_due_decision_to_worker(
    monkeypatch,
) -> None:
    """Catches process-memory cadence suppressing a persisted monitor deadline."""

    class Adapter:
        async def lookup_command_truth(self, request):
            del request

        async def read_position_snapshot(self, request):
            del request

        async def read_account_risk_snapshot(self, request):
            del request

        async def read_instrument_rules(self, request):
            del request

        async def read_review_economics(self, request):
            del request

        async def read_fee_discount_capability(self, *, observed_at_ms):
            del observed_at_ms

        async def read_instrument_certification(self, request):
            del request

    class Engine:
        async def dispose(self):
            return None

    observed_sources: list[object | None] = []

    async def run_once(*args, fee_discount_capability_source=None, **kwargs):
        del args, kwargs
        observed_sources.append(fee_discount_capability_source)
        return ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.FEE_CAPABILITY_OBSERVED,
        )

    async def run_process(tick, **kwargs):
        del kwargs
        await tick()
        await tick()
        return 0

    monkeypatch.setattr(runner, "_load_factory", lambda spec: lambda: Adapter())
    monkeypatch.setattr(runner, "create_async_engine", lambda url: Engine())
    monkeypatch.setattr(runner, "run_reconciliation_worker_once", run_once)
    monkeypatch.setattr(runner, "run_worker_process", run_process)

    args = argparse.Namespace(
        database_url="postgresql+asyncpg://test",
        venue_factory="test:factory",
        worker_id="worker",
        runtime_commit="commit",
        schema_revision="schema",
        now_ms=600_000,
        timeout_seconds=1.0,
        unknown_visibility_grace_ms=30_000,
        review_economics_visibility_grace_ms=300_000,
        idle_poll_interval_ms=2_000,
        fee_capability_monitor_interval_ms=300_000,
        run_forever=False,
        poll_interval_ms=5_000,
        idle_log_interval_ms=300_000,
    )

    assert await runner._run(args) == 0
    assert observed_sources == [observed_sources[0], observed_sources[0]]
    assert observed_sources[0] is not None
