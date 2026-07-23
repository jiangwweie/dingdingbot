from __future__ import annotations

from decimal import Decimal

import pytest

from tests.trading_kernel.integration import test_signal_to_ticket as signal_fixture
from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
)
from src.trading_kernel.application.issue_ready_signal import (
    IssueReadySignalRequest,
    issue_ready_signal,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionInstrumentFacts,
    EntryAdmissionSnapshot,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _seed_runtime_authority,
    _signal,
)


issue_engine = signal_fixture.signal_engine


@pytest.mark.asyncio
async def test_claim_ticket_budget_domain_and_entry_command_commit_atomically(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-capacity-integration")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_003),
        )
    assert selected.status is SelectEntryCandidateStatus.SELECTED
    assert selected.candidate is not None
    assert selected.candidate.signal.signal_event_id == signal.signal_event_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=_admission_snapshot(),
                claim_owner="entry-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_004,
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert result.ticket_id is not None
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        claim = await uow.capacity_claims.get_for_ticket(result.ticket_id)
        ticket = await uow.tickets.get(result.ticket_id)
        reservation = await uow.budgets.get_for_ticket(result.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(result.ticket_id)
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)

    assert claim is not None
    assert ticket == claim.to_ticket()
    assert ticket is not None
    assert ticket.take_profit_quantities == claim.take_profit_quantities
    assert sum(ticket.take_profit_quantities, Decimal("0")) < ticket.quantity
    assert reservation is not None
    assert reservation.reserved_notional == claim.notional
    assert reservation.reserved_risk == claim.risk_at_stop
    assert len(commands) == 1
    assert commands[0].kind is ExchangeCommandKind.ENTRY
    assert readiness is not None
    assert readiness.readiness_state == "processing"


@pytest.mark.asyncio
async def test_capacity_refusal_persists_no_partial_issuance(issue_engine) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-capacity-refused")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )

    stale = _admission_snapshot().model_copy(
        update={"valid_until_ms": 1_004}
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=stale,
                claim_owner="entry-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_004,
            ),
        )

    assert result.status is IssueTicketStatus.SIGNAL_INVALID_OR_STALE
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.capacity_claims.get_for_signal(signal.signal_event_id) is None
        assert not await uow.entry_admission.has_ticket_for_signal(
            signal.signal_event_id
        )


def _admission_snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        venue_id="binance-usdm",
        account_id="subaccount-main",
        position_mode="independent_sides",
        margin_mode="cross",
        total_wallet_balance=Decimal("1000"),
        total_margin_balance=Decimal("1000"),
        total_initial_margin=Decimal("0"),
        total_maintenance_margin=Decimal("0"),
        available_margin=Decimal("1000"),
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal("10000"),
        instrument_facts=(
            AdmissionInstrumentFacts(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                mark_price=Decimal("10000"),
                configured_leverage=10,
            ),
        ),
        positions=(),
        open_orders=(),
        observed_at_ms=1_003,
        valid_until_ms=1_100,
    )
