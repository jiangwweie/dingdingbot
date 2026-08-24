from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
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
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    strategy_entry_controls_current,
    strategy_selection_control_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from tests.trading_kernel.support.dispatch_venues import CountingVenue, PreflightFacts
from tests.trading_kernel.support.selection_authority import (
    FIRST_ELIGIBLE_CLOSE_MS,
    SELECTION_AUTHORITY_ID,
    continuity_successor,
    install_dynamic_pre_fence_authority,
    move_seeded_runtime_to_dynamic_period,
)
from tests.trading_kernel.support.selection_vacuum import (
    open_strategy_entry_vacuum,
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
    authority = await install_dynamic_pre_fence_authority(issue_engine)
    await move_seeded_runtime_to_dynamic_period(issue_engine)
    signal = _signal(
        signal_event_id="signal-capacity-integration",
        occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
        selection_authority_id=authority.selection_authority_id,
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 2,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=FIRST_ELIGIBLE_CLOSE_MS + 3),
        )
    assert selected.status is SelectEntryCandidateStatus.SELECTED
    assert selected.candidate is not None
    assert selected.candidate.signal.signal_event_id == signal.signal_event_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=_admission_snapshot(
                    observed_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 3,
                ),
                claim_owner="entry-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 4,
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
        == SELECTION_AUTHORITY_ID
    )


@pytest.mark.asyncio
async def test_signal_ingest_accepts_uninterrupted_compatible_authority_successor(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    birth = await install_dynamic_pre_fence_authority(issue_engine)
    await move_seeded_runtime_to_dynamic_period(issue_engine)
    successor = continuity_successor(
        birth,
        authority_id="authority:dynamic-test:successor",
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await uow.instrument_selection.add_authority_and_set_current(
            successor,
            expected_current_version=1,
        )
    signal = _signal(
        signal_event_id="signal-compatible-selection-successor",
        occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
        selection_authority_id=birth.selection_authority_id,
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 2,
            ),
        )
        persisted = await uow.signals.get(signal.signal_event_id)

    assert result.status is IngestSignalStatus.CANDIDATE_READY
    assert persisted is not None
    assert persisted.selection_authority_id == birth.selection_authority_id


@pytest.mark.asyncio
async def test_signal_ingest_rejects_unknown_birth_authority_without_persistence(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    await install_dynamic_pre_fence_authority(issue_engine)
    await move_seeded_runtime_to_dynamic_period(issue_engine)
    signal = _signal(
        signal_event_id="signal-unknown-selection-birth",
        occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
        selection_authority_id="authority:unknown",
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 2,
            ),
        )
        persisted = await uow.signals.get(signal.signal_event_id)

    assert result.status is IngestSignalStatus.SELECTION_AUTHORITY_INVALID
    assert persisted is None


@pytest.mark.asyncio
async def test_selection_owner_pause_uses_scope_policy_blocker_not_lineage_error(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    authority = await install_dynamic_pre_fence_authority(issue_engine)
    await move_seeded_runtime_to_dynamic_period(issue_engine)
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                entry_state="paused",
                control_version=2,
                reason="test_selection_owner_pause",
                updated_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 1,
            )
        )
    signal = _signal(
        signal_event_id="signal-selection-owner-paused",
        occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
        selection_authority_id=authority.selection_authority_id,
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 2,
            ),
        )

    assert result.status is IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH


@pytest.mark.asyncio
async def test_open_selection_vacuum_rejects_admission_before_claim_or_ticket(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-vacuum-refused")
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
    vacuum = await open_strategy_entry_vacuum(
        issue_engine,
        strategy_group_id=signal.strategy_group_id,
        strategy_version_id=signal.strategy_version_id,
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=_admission_snapshot(),
                claim_owner="entry-worker-vacuum",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_004,
            ),
        )

    assert result.status is IssueTicketStatus.SELECTION_ENTRY_VACUUM
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        claim = await uow.capacity_claims.get_for_signal(signal.signal_event_id)
        admission = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        has_ticket = await uow.entry_admission.has_ticket_for_signal(
            signal.signal_event_id
        )
    assert claim is None
    assert has_ticket is False
    assert admission is not None
    assert admission.decision_status.value == "rejected"
    assert admission.first_blocker == "selection_entry_vacuum"
    assert admission.binding_constraint == vacuum.entry_vacuum_id
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "selection_entry_vacuum"


@pytest.mark.asyncio
async def test_dispatch_authority_drift_rejects_before_any_venue_mutation(
    issue_engine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    authority = await install_dynamic_pre_fence_authority(issue_engine)
    await move_seeded_runtime_to_dynamic_period(issue_engine)
    signal = _signal(
        signal_event_id="signal-selection-dispatch-drift",
        occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
        selection_authority_id=authority.selection_authority_id,
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 2,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        issued = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=_admission_snapshot(
                    observed_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 3,
                ),
                claim_owner="entry-worker-selection-drift",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=FIRST_ELIGIBLE_CLOSE_MS + 4,
            ),
        )
    assert issued.status is IssueTicketStatus.ISSUED
    assert issued.ticket_id is not None
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_selection_control_current)
            .where(
                strategy_selection_control_current.c.strategy_group_id == "SOR-001"
            )
            .values(
                selection_mode="disabled",
                control_version=2,
                updated_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 5,
            )
        )
    venue = CountingVenue()

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(issue_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher-selection-drift",
            ticket_id=issued.ticket_id,
            now_ms=FIRST_ELIGIBLE_CLOSE_MS + 6,
            lease_until_ms=FIRST_ELIGIBLE_CLOSE_MS + 5_006,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    assert result.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with issue_engine.connect() as connection:
        command = (
            await connection.execute(
                sa.select(exchange_commands).where(
                    exchange_commands.c.ticket_id == issued.ticket_id
                )
            )
        ).mappings().one()
    assert command["status"] == "rejected"
    assert command["result_payload"]["reason"] == (
        "dispatch_preflight:selection_authority_invalid"
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


def _admission_snapshot(*, observed_at_ms: int = 1_003) -> EntryAdmissionSnapshot:
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
            observed_at_ms=observed_at_ms,
            valid_until_ms=observed_at_ms + 100,
        ),
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=observed_at_ms,
        valid_until_ms=observed_at_ms + 100,
    )
