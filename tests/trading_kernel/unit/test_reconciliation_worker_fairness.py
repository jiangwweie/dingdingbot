from __future__ import annotations

from decimal import Decimal

import pytest

import src.trading_kernel.interfaces.reconciliation_worker as worker_module
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketResult,
    ReconcileTicketStatus,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.venue_truth import (
    UnknownRecoveryDecision,
    UnknownRecoveryStatus,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.unit.test_reducer import (
    _reconciliation_pending_aggregate,
)
from tests.trading_kernel.unit.test_unknown_command_recovery import _cancel_command


class _CommandRepository:
    def __init__(self):
        self.command = _cancel_command()

    async def get_one_unknown(self):
        return self.command


class _AggregateRepository:
    def __init__(self):
        self.aggregate = _reconciliation_pending_aggregate()
        self.scheduled_due_at_ms: int | None = None

    async def get_next_for_statuses(self, statuses, **kwargs):
        del kwargs
        return self.aggregate if self.aggregate.status in statuses else None

    async def schedule_next_check(self, ticket_id, *, work_kind, due_at_ms):
        assert ticket_id == self.aggregate.identity.ticket_id
        assert work_kind == "reconciliation"
        self.scheduled_due_at_ms = due_at_ms


class _UnitOfWork:
    def __init__(self, state):
        self.exchange_commands = state.commands
        self.aggregates = state.aggregates

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback


class _State:
    def __init__(self):
        self.commands = _CommandRepository()
        self.aggregates = _AggregateRepository()

    def factory(self):
        return _UnitOfWork(self)


class _PositionSource:
    def __init__(self, aggregate):
        self.aggregate = aggregate
        self.requests = []

    async def read_position_snapshot(self, request):
        self.requests.append(request)
        return PositionSnapshot(
            netting_domain=self.aggregate.identity.netting_domain,
            quantity=Decimal("0"),
            average_entry_price=None,
            observed_at_ms=request.observed_at_ms,
        )


@pytest.mark.asyncio
async def test_pending_unknown_does_not_starve_position_reconciliation(
    monkeypatch,
) -> None:
    state = _State()
    position_source = _PositionSource(state.aggregates.aggregate)
    recovery_requests = []
    reconciliation_requests = []

    async def certified(*args, **kwargs):
        del args, kwargs
        return True

    async def pending_recovery(*args, **kwargs):
        del args
        recovery_requests.append(kwargs)
        return UnknownRecoveryDecision(
            status=UnknownRecoveryStatus.PENDING_VISIBILITY,
            observed_at_ms=5_000,
            reason="cancel_target_still_visible",
        )

    async def reconcile(*args, **kwargs):
        del args
        reconciliation_requests.append(kwargs)
        return ReconcileTicketResult(status=ReconcileTicketStatus.MATCHED)

    monkeypatch.setattr(worker_module, "_runtime_writer_is_certified", certified)
    monkeypatch.setattr(worker_module, "recover_unknown_command", pending_recovery)
    monkeypatch.setattr(worker_module, "reconcile_ticket", reconcile)

    result = await run_reconciliation_worker_once(
        state.factory,
        object(),
        position_source,
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            now_ms=5_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    assert result.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert len(recovery_requests) == 1
    assert len(position_source.requests) == 1
    assert len(reconciliation_requests) == 1
    assert state.aggregates.scheduled_due_at_ms == 7_000
