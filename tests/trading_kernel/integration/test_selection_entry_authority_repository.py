from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.instrument_selection import SOR_LONG_EVENT_SPEC_ID
from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
)
from src.trading_kernel.infrastructure.pg_models import (
    strategy_entry_vacuums_current,
    strategy_trigger_suppressions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.selection_authority import (
    FIRST_ELIGIBLE_CLOSE_MS,
    INTERVAL_MS,
    SELECTION_AUTHORITY_ID,
    SELECTION_SPEC_ID,
    SESSION_START_MS,
    install_dynamic_pre_fence_authority,
)
from tests.trading_kernel.support.signal_ingest import seed_runtime_authority

SELECTED_INSTRUMENT_ID = "binance-usdm:BTCUSDT:perpetual"
AUDIT_ID = "gap-audit:dynamic-test:1"
SUCCESSOR_AUTHORITY_ID = "authority:dynamic-test:2"


@pytest.mark.asyncio
async def test_signal_repository_reads_exact_bounded_authority_chain(
    head_template_engine,
) -> None:
    await _seed_authority_chain(head_template_engine)

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        chain = await uow.signals.get_selection_authority_chain(
            selection_spec_id=SELECTION_SPEC_ID,
            birth_selection_authority_id=SELECTION_AUTHORITY_ID,
            current_selection_authority_id=SUCCESSOR_AUTHORITY_ID,
            max_depth=8,
        )

    assert tuple(item.selection_authority_id for item in chain) == (
        SELECTION_AUTHORITY_ID,
        SUCCESSOR_AUTHORITY_ID,
    )


@pytest.mark.asyncio
async def test_signal_repository_detects_vacuum_or_control_interruption(
    head_template_engine,
) -> None:
    await _seed_authority_chain(head_template_engine)
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                entry_vacuum_id="vacuum:selection-entry-authority:test",
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
                source_generation_id=None,
                state="VALID_EMPTY",
                fenced_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 15,
                drained_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 16,
                resolved_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 17,
                first_blocker="test_interruption",
                projection_version=1,
            )
        )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        interrupted = await uow.signals.selection_authority_was_interrupted(
            strategy_group_id="SOR-001",
            selection_spec_id=SELECTION_SPEC_ID,
            owner_policy_id="policy-main",
            after_ms=FIRST_ELIGIBLE_CLOSE_MS - INTERVAL_MS,
            through_ms=FIRST_ELIGIBLE_CLOSE_MS + 20,
        )

    assert interrupted is True


@pytest.mark.asyncio
async def test_signal_repository_reads_exact_trigger_suppression(
    head_template_engine,
) -> None:
    await _seed_authority_chain(head_template_engine)
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_trigger_suppressions).values(
                trigger_suppression_id="trigger-suppression:selection-entry:test",
                authority_gap_audit_id=AUDIT_ID,
                entry_vacuum_id=None,
                materialization_generation_id=None,
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                exchange_instrument_id=SELECTED_INSTRUMENT_ID,
                session_reference=str(SESSION_START_MS),
                first_natural_trigger_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
                reason_code="TRIGGER_DURING_AUTHORITY_GAP",
                detector_semantic_digest="sha256:" + "4" * 64,
                created_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 1,
            )
        )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        exact = await uow.signals.is_strategy_trigger_suppressed(
            event_spec_id=SOR_LONG_EVENT_SPEC_ID,
            exchange_instrument_id=SELECTED_INSTRUMENT_ID,
            session_reference=str(SESSION_START_MS),
        )
        other_session = await uow.signals.is_strategy_trigger_suppressed(
            event_spec_id=SOR_LONG_EVENT_SPEC_ID,
            exchange_instrument_id=SELECTED_INSTRUMENT_ID,
            session_reference=str(SESSION_START_MS + 86_400_000),
        )

    assert exact is True
    assert other_session is False


@pytest.mark.asyncio
async def test_current_authority_for_update_serializes_ticket_birth_validation(
    head_template_engine,
) -> None:
    await _seed_authority_chain(head_template_engine)
    third = _continuity_successor(
        authority_id="authority:dynamic-test:3",
        sequence=3,
        predecessor_id=SUCCESSOR_AUTHORITY_ID,
        created_at_ms=FIRST_ELIGIBLE_CLOSE_MS - 1,
    )

    async with PostgresKernelUnitOfWork(head_template_engine) as locked_uow:
        locked = await locked_uow.instrument_selection.get_current_authority(
            SELECTION_SPEC_ID,
            for_update=True,
        )
        assert locked is not None
        assert locked.selection_authority_id == SUCCESSOR_AUTHORITY_ID
        advance = asyncio.create_task(
            _advance_current_authority(head_template_engine, third)
        )
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(advance), timeout=0.1)

    await asyncio.wait_for(advance, timeout=2)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        current = await uow.instrument_selection.get_current_authority(
            SELECTION_SPEC_ID
        )
    assert current is not None
    assert current.selection_authority_id == third.selection_authority_id


async def _seed_authority_chain(engine) -> None:
    await seed_runtime_authority(engine)
    birth = await install_dynamic_pre_fence_authority(engine)
    successor = _continuity_successor(
        authority_id=SUCCESSOR_AUTHORITY_ID,
        sequence=2,
        predecessor_id=birth.selection_authority_id,
        created_at_ms=FIRST_ELIGIBLE_CLOSE_MS - 1,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.instrument_selection.add_authority_and_set_current(
            successor,
            expected_current_version=1,
        )


def _continuity_successor(
    *,
    authority_id: str,
    sequence: int,
    predecessor_id: str,
    created_at_ms: int,
) -> SelectionSessionAuthority:
    return SelectionSessionAuthority(
        selection_authority_id=authority_id,
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 3_600_000,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=None,
        continued_from_selection_authority_id=predecessor_id,
        continuity_source_kind=ContinuitySourceKind.SELECTION_AUTHORITY,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        authorized_pair=(
            UniverseAuthorityPair(
                long_universe_version_id="universe:sor-long:4",
                short_universe_version_id="universe:sor-short:4",
            )
        ),
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=predecessor_id,
            authority_gap_audit_id=None,
        ),
        effective_from_ms=SESSION_START_MS + 3_600_000,
        first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=SESSION_START_MS + 90_000_000,
        reason_code="PRE_FENCE_CONTINUITY_REFRESH",
        created_at_ms=created_at_ms,
    )


async def _advance_current_authority(engine, authority) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.instrument_selection.add_authority_and_set_current(
            authority,
            expected_current_version=2,
        )
