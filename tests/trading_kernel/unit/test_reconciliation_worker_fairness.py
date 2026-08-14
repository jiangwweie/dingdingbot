from __future__ import annotations

from decimal import Decimal

import pytest

import src.trading_kernel.interfaces.reconciliation_worker as worker_module
from src.trading_kernel.application.ports import (
    MonitorOwnerStatus,
    MonitorStateRecord,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketResult,
    ReconcileTicketStatus,
)
from src.trading_kernel.application.reconciliation_scheduler import (
    ReconciliationActionCandidate,
    ReconciliationActionKind,
)
from src.trading_kernel.application.runtime_facts import FeeDiscountCapabilityFacts
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
from tests.trading_kernel.integration.universe_certification_support import (
    NoInstrumentCertificationSource,
    NoTicketPositionSource,
    NoTicketVenueTruth,
)
from tests.trading_kernel.support.reducer_states import reconciliation_pending_aggregate as _reconciliation_pending_aggregate
from tests.trading_kernel.support.unknown_commands import cancel_command as _cancel_command


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

    async def claim_next_critical_reconciliation_work(self, *, now_ms):
        del now_ms
        if self.aggregate.status in {
            worker_module.AggregateStatus.POST_FILL_RISK_PENDING,
            *worker_module._POSITION_RECONCILIATION_STATUSES,
        }:
            return self.aggregate
        return None

    async def claim_next_routine_reconciliation_work(
        self, *, worker_id, now_ms, lease_until_ms
    ):
        del worker_id, now_ms, lease_until_ms
        return self.aggregate

    async def schedule_next_check(self, ticket_id, *, work_kind, due_at_ms):
        assert ticket_id == self.aggregate.identity.ticket_id
        assert work_kind == "reconciliation"
        self.scheduled_due_at_ms = due_at_ms


class _UnitOfWork:
    def __init__(self, state):
        self.exchange_commands = state.commands
        self.aggregates = state.aggregates
        self.monitors = getattr(state, "monitors", None)
        self.strategy_universes = getattr(state, "strategy_universes", None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback


class _State:
    def __init__(self):
        self.commands = _CommandRepository()
        self.aggregates = _AggregateRepository()
        self.monitors = _MonitorRepository()

    def factory(self):
        return _UnitOfWork(self)


class _PositionSource:
    def __init__(self, aggregate):
        self.aggregate = aggregate
        self.requests: list[object] = []

    async def read_position_snapshot(self, request):
        self.requests.append(request)
        return PositionSnapshot(
            netting_domain=self.aggregate.identity.netting_domain,
            quantity=Decimal(0),
            average_entry_price=None,
            observed_at_ms=request.observed_at_ms,
        )


class _MonitorRepository:
    def __init__(self) -> None:
        self.states: list[object] = []
        self.current: MonitorStateRecord | None = None

    async def get(self, monitor_key):
        if self.current is not None and self.current.monitor_key == monitor_key:
            return self.current
        return None

    async def save_if_changed(self, state):
        self.states.append(state)
        self.current = state
        return state


class _FeeDiscountCapabilitySource:
    async def read_fee_discount_capability(self, *, observed_at_ms):
        return FeeDiscountCapabilityFacts(
            fee_burn_enabled=True,
            bnb_futures_wallet_balance=Decimal("0.02"),
            observed_at_ms=observed_at_ms,
            source="binance_usdm_readonly",
        )


@pytest.mark.asyncio
async def test_pending_unknown_is_the_only_network_work_in_a_cadence(
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
        NoTicketVenueTruth(),
        position_source,
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=5_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    assert result.status is ReconciliationWorkerStatus.UNKNOWN_RECOVERED
    assert len(recovery_requests) == 1
    assert position_source.requests == []
    assert reconciliation_requests == []
    assert state.aggregates.scheduled_due_at_ms is None


@pytest.mark.asyncio
async def test_bnb_capability_monitor_progresses_after_position_safety(
    monkeypatch,
) -> None:
    state = _State()
    state.commands.command = None

    async def certified(*args, **kwargs):
        del args, kwargs
        return True

    async def reconcile(*args, **kwargs):
        del args, kwargs
        return ReconcileTicketResult(status=ReconcileTicketStatus.MATCHED)

    monkeypatch.setattr(worker_module, "_runtime_writer_is_certified", certified)
    monkeypatch.setattr(worker_module, "reconcile_ticket", reconcile)

    result = await run_reconciliation_worker_once(
        state.factory,
        NoTicketVenueTruth(),
        _PositionSource(state.aggregates.aggregate),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=5_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
        fee_discount_capability_source=_FeeDiscountCapabilitySource(),
    )

    assert result.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert result.housekeeping_status is (
        ReconciliationWorkerStatus.FEE_CAPABILITY_OBSERVED
    )
    assert len(state.monitors.states) == 1


class _AgeAwareAggregateRepository:
    def __init__(self) -> None:
        position = _reconciliation_pending_aggregate()
        self.position = position.model_copy(
            update={"status": worker_module.AggregateStatus.POSITION_PROTECTED}
        )
        self.settlement = position.model_copy(
            update={"status": worker_module.AggregateStatus.SETTLEMENT_PENDING}
        )

    async def claim_next_critical_reconciliation_work(self, *, now_ms):
        del now_ms
        return self.position

    async def claim_next_routine_reconciliation_work(
        self, *, worker_id, now_ms, lease_until_ms
    ):
        del worker_id, now_ms, lease_until_ms
        return self.settlement

    async def get_next_for_statuses(self, statuses, **kwargs):
        del kwargs
        if self.position.status in statuses:
            return self.position
        if self.settlement.status in statuses:
            return self.settlement
        return None

    async def schedule_next_check(self, *args, **kwargs):
        assert args == (self.position.identity.ticket_id,)
        assert kwargs["work_kind"] == "reconciliation"


class _AgeAwareState:
    def __init__(self) -> None:
        self.aggregates = _AgeAwareAggregateRepository()
        self.commands = type("Commands", (), {"get_one_unknown": _no_unknown})()

    def factory(self):
        return _UnitOfWork(self)


async def _no_unknown(_self):
    return None


class _RoutineOnlyAggregateRepository:
    def __init__(self) -> None:
        self.aggregate = _reconciliation_pending_aggregate().model_copy(
            update={"status": worker_module.AggregateStatus.SETTLEMENT_PENDING}
        )
        self.routine_due_at_ms = 900_000

    async def claim_next_critical_reconciliation_work(self, *, now_ms):
        del now_ms

    async def claim_next_routine_reconciliation_work(
        self, *, worker_id, now_ms, lease_until_ms
    ):
        del worker_id, now_ms, lease_until_ms
        return self.aggregate

    async def peek_next_routine_reconciliation_action(self, *, now_ms):
        del now_ms
        return ReconciliationActionCandidate(
            kind=ReconciliationActionKind.SETTLEMENT,
            stable_identity=self.aggregate.identity.ticket_id,
            due_at_ms=self.routine_due_at_ms,
            max_wait_ms=60_000,
        )


class _RoutineOnlyState:
    def __init__(self) -> None:
        self.aggregates = _RoutineOnlyAggregateRepository()
        self.commands = type("Commands", (), {"get_one_unknown": _no_unknown})()
        self.monitors = _MonitorRepository()
        self.strategy_universes = None

    def factory(self):
        return _UnitOfWork(self)


@pytest.mark.asyncio
async def test_fee_monitor_preempts_later_closure_deadline(monkeypatch) -> None:
    """Catches the fixed routine-before-fee branch under continuous closure work."""

    state = _RoutineOnlyState()
    state.aggregates.routine_due_at_ms = 950_000
    state.monitors.current = MonitorStateRecord(
        monitor_key="account:binance-usdm:bnb-fee-capability",
        owner_status=MonitorOwnerStatus.RUNNING,
        summary="available",
        intervention="none",
        updated_at_ms=1,
    )

    async def certified(*args, **kwargs):
        del args, kwargs
        return True

    async def settle(*args, **kwargs):
        del args, kwargs
        return worker_module.ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.SETTLED,
            ticket_id="ticket:routine",
        )

    monkeypatch.setattr(worker_module, "_runtime_writer_is_certified", certified)
    monkeypatch.setattr(worker_module, "_run_reconciliation_worker_once_core", settle)

    result = await run_reconciliation_worker_once(
        state.factory,
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=1_000_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
        fee_discount_capability_source=_FeeDiscountCapabilitySource(),
    )

    assert result.status is ReconciliationWorkerStatus.FEE_CAPABILITY_OBSERVED


@pytest.mark.asyncio
async def test_due_certification_preempts_later_closure_deadline(monkeypatch) -> None:
    """Catches routine-first ordering before a due certification's deadline."""

    state = _RoutineOnlyState()
    state.aggregates.routine_due_at_ms = 950_000

    class CertificationRepository:
        async def peek_next_due_instrument_certification_action(self, *, now_ms):
            del now_ms
            return ReconciliationActionCandidate(
                kind=ReconciliationActionKind.CERTIFICATION,
                stable_identity="runtime:instrument:btc",
                due_at_ms=850_000,
                max_wait_ms=120_000,
            )

    state.strategy_universes = CertificationRepository()

    async def certify(*args, request, overdue_before_ms=None, **kwargs):
        del args, request, kwargs
        if overdue_before_ms is not None:
            return None
        return worker_module.ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        )

    async def settle(*args, **kwargs):
        del args, kwargs
        return worker_module.ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.SETTLED,
            ticket_id="ticket:routine",
        )

    monkeypatch.setattr(worker_module, "_certify_one_due_instrument", certify)
    monkeypatch.setattr(worker_module, "_run_reconciliation_worker_once_core", settle)

    result = await run_reconciliation_worker_once(
        state.factory,
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=1_000_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
        instrument_certification_source=NoInstrumentCertificationSource(),
    )

    assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED


@pytest.mark.asyncio
async def test_overdue_certification_preempts_continuous_routine_work_within_two_minutes(
    monkeypatch,
) -> None:
    """Virtual cadence catches the historical routine-reconciliation starvation bug."""

    state = _RoutineOnlyState()
    selected: list[tuple[int, int | None]] = []
    routine_calls: list[int] = []

    async def certify(*args, request, overdue_before_ms=None, **kwargs):
        del args, kwargs
        selected.append((request.now_ms, overdue_before_ms))
        if overdue_before_ms is not None and request.now_ms >= 125_000:
            return worker_module.ReconciliationWorkerResult(
                status=ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            )
        return None

    async def run_routine(*args, **kwargs):
        request = args[3]
        del kwargs
        routine_calls.append(request.now_ms)
        return worker_module.ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.SETTLED,
            ticket_id="ticket:routine",
        )

    monkeypatch.setattr(worker_module, "_certify_one_due_instrument", certify)
    monkeypatch.setattr(worker_module, "_run_reconciliation_worker_once_core", run_routine)
    source = NoInstrumentCertificationSource()
    for now_ms in range(5_000, 130_000, 5_000):
        result = await run_reconciliation_worker_once(
            state.factory,
            NoTicketVenueTruth(),
            NoTicketPositionSource(),
            ReconciliationWorkerRequest(
                worker_id="reconciliation-worker-test",
                runtime_commit="kernel-test-head",
                schema_revision="0002_sor_v3_strategy_group_capacity",
                now_ms=now_ms,
                timeout_seconds=1,
                unknown_visibility_grace_ms=30_000,
                idle_poll_interval_ms=2_000,
            ),
            instrument_certification_source=source,
        )
        if result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED:
            break

    assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert result.exchange_instrument_id == "binance-usdm:BTCUSDT:perpetual"
    assert selected[-1] == (125_000, 5_000)
    assert routine_calls == list(range(5_000, 125_000, 5_000))


class _PositionSafetySource:
    async def read_position_snapshot(self, request):
        return PositionSnapshot(
            netting_domain=request.netting_domain,
            quantity=Decimal(0),
            average_entry_price=None,
            observed_at_ms=request.observed_at_ms,
        )


@pytest.mark.asyncio
async def test_worker_progresses_position_safety_before_routine_closure(
    monkeypatch,
) -> None:
    state = _AgeAwareState()
    settled = []

    async def certified(*args, **kwargs):
        del args, kwargs
        return True

    async def settle(_uow, request):
        settled.append(request.ticket_id)

    async def reconcile(*args, **kwargs):
        del args, kwargs
        return ReconcileTicketResult(status=ReconcileTicketStatus.MATCHED)

    monkeypatch.setattr(worker_module, "_runtime_writer_is_certified", certified)
    monkeypatch.setattr(worker_module, "settle_ticket", settle)
    monkeypatch.setattr(worker_module, "reconcile_ticket", reconcile)

    result = await run_reconciliation_worker_once(
        state.factory,
        NoTicketVenueTruth(),
        _PositionSafetySource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=31_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
    )

    assert result.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert result.housekeeping_status is ReconciliationWorkerStatus.SETTLED
    assert settled == [state.aggregates.settlement.identity.ticket_id]


@pytest.mark.asyncio
async def test_overdue_certification_progresses_during_continuous_position_safety(
    monkeypatch,
) -> None:
    """Catches active-position safety permanently excluding housekeeping."""

    state = _AgeAwareState()
    certification_calls: list[tuple[int, int | None]] = []

    async def certified(*args, **kwargs):
        del args, kwargs
        return True

    async def reconcile(*args, **kwargs):
        del args, kwargs
        return ReconcileTicketResult(status=ReconcileTicketStatus.MATCHED)

    async def certify(*args, request, overdue_before_ms=None, **kwargs):
        del args, kwargs
        certification_calls.append((request.now_ms, overdue_before_ms))
        return worker_module.ReconciliationWorkerResult(
            status=ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        )

    monkeypatch.setattr(worker_module, "_runtime_writer_is_certified", certified)
    monkeypatch.setattr(worker_module, "reconcile_ticket", reconcile)
    monkeypatch.setattr(worker_module, "_certify_one_due_instrument", certify)

    result = await run_reconciliation_worker_once(
        state.factory,
        NoTicketVenueTruth(),
        _PositionSafetySource(),
        ReconciliationWorkerRequest(
            worker_id="reconciliation-worker-test",
            runtime_commit="kernel-test-head",
            schema_revision="0002_sor_v3_strategy_group_capacity",
            now_ms=125_000,
            timeout_seconds=1,
            unknown_visibility_grace_ms=30_000,
            idle_poll_interval_ms=2_000,
        ),
        instrument_certification_source=NoInstrumentCertificationSource(),
    )

    assert result.status is ReconciliationWorkerStatus.POSITION_RECONCILED
    assert result.housekeeping_status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert result.housekeeping_exchange_instrument_id == (
        "binance-usdm:BTCUSDT:perpetual"
    )
    assert certification_calls == [(125_000, 5_000)]
