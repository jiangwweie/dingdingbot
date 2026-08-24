from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

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
from src.trading_kernel.domain.cross_margin_stress import AccountRiskSnapshot
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.selection_authority import (
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_models import instrument_selection_specs
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from tests.trading_kernel.support.signal_ingest import (
    seed_runtime_authority as _seed_runtime_authority,
)
from tests.trading_kernel.support.signal_ingest import (
    signal as _signal,
)


@pytest.mark.asyncio
async def test_claim_ticket_budget_domain_and_entry_command_commit_atomically(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    await _seed_selection_authority(issue_engine)
    signal = _signal(
        signal_event_id="signal-capacity-integration",
        selection_authority_id="authority:persistence:1",
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
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
                schema_revision=CURRENT_SCHEMA_REVISION,
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
        persisted_signal = await uow.signals.get(signal.signal_event_id)
        admission = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )

    assert claim is not None
    assert ticket == claim.to_ticket()
    assert ticket is not None
    assert ticket.take_profit_quantities == claim.take_profit_quantities
    assert sum(ticket.take_profit_quantities, Decimal(0)) < ticket.quantity
    assert reservation is not None
    assert reservation.reserved_notional == claim.notional
    assert reservation.reserved_risk == claim.risk_at_stop
    assert len(commands) == 1
    assert commands[0].kind is ExchangeCommandKind.ENTRY
    assert readiness is not None
    assert readiness.readiness_state == "processing"
    assert persisted_signal is not None
    assert admission is not None
    assert (
        persisted_signal.selection_authority_id
        == claim.selection_authority_id
        == admission.selection_authority_id
        == ticket.selection_authority_id
        == "authority:persistence:1"
    )


async def _seed_selection_authority(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(instrument_selection_specs).values(
                selection_spec_id="selection-spec:SOR-001:v0",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest="sha256:" + "f" * 64,
                status="active",
                installed_at_ms=1_000,
            )
        )
        await PostgresInstrumentSelectionRepository(
            connection
        ).add_authority_and_set_current(
            SelectionSessionAuthority(
                selection_authority_id="authority:persistence:1",
                selection_spec_id="selection-spec:SOR-001:v0",
                session_start_ms=1_704_067_200_000,
                decision_boundary_ms=1_704_070_800_000,
                authority_sequence=1,
                selection_mode=SelectionMode.DISABLED,
                selection_snapshot_id=None,
                continued_from_selection_authority_id=None,
                continuity_source_kind=ContinuitySourceKind.NONE,
                authority_gap_audit_id=None,
                materialization_generation_id=None,
                owner_control_version=1,
                authority_outcome=AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED,
                authorized_pair=None,
                grant_proof=None,
                effective_from_ms=1_704_070_800_000,
                first_eligible_close_time_ms=None,
                expires_at_ms=1_704_157_200_000,
                reason_code="PERSISTENCE_ONLY",
                created_at_ms=1_704_070_800_000,
            ),
            expected_current_version=None,
        )


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
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    stale_base = _admission_snapshot()
    stale = stale_base.model_copy(
        update={
            "account_risk_snapshot": (
                stale_base.account_risk_snapshot.model_copy(
                    update={"valid_until_ms": 1_004}
                )
            ),
            "valid_until_ms": 1_004,
        }
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=stale,
                claim_owner="entry-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
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
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            mark_price=Decimal(10000),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=1_003,
            valid_until_ms=1_100,
        ),
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=1_003,
        valid_until_ms=1_100,
    )
