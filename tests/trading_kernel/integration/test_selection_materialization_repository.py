from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditEvaluationRequest,
    CoordinateSelectionMaterializationRequest,
    MaterializationDisposition,
    complete_pending_authority_gap_audit,
    coordinate_selection_materialization_once,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAuditKind,
    AuthorityGapScope,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    MaterializationGeneration,
    MaterializationGenerationState,
    MaterializationTarget,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    build_pending_authority_gap_audit,
    complete_authority_gap_audit,
    selected_member_set_digest,
    selection_authority_allows_new_entry,
)
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_product_profiles,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    instruments,
    owner_authorizations,
    selection_authority_current,
    selection_authority_gap_audit_events,
    selection_authority_gap_audits_current,
    selection_session_authorities,
    sor_dynamic_selection_specs_v0,
    strategy_entry_controls_current,
    strategy_entry_vacuum_events,
    strategy_entry_vacuums_current,
    strategy_selection_control_current,
    strategy_trigger_suppressions,
    strategy_universe_current,
    strategy_universe_materialization_events,
    strategy_universe_materialization_generations,
    strategy_universe_materialization_targets,
    strategy_universe_members,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)

SESSION_START_MS = 1_704_067_200_000
SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
ALGORITHM_DIGEST = (
    "sha256:a2c0d5d809a54b90564086f4eab230726a16fdb5524a1ce8f29f48ad659cfb10"
)
LONG_UNIVERSE_ID = "universe:materialization:long:current"
SHORT_UNIVERSE_ID = "universe:materialization:short:current"
SELECTED_MEMBERS = tuple(sorted(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[:2]))


@pytest.mark.asyncio
async def test_repository_recovers_snapshot_and_advances_generation_to_desired(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)

    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        control = await repository.get_selection_control(
            "SOR-001",
            for_update=True,
        )
        disposition = await repository.get_snapshot_disposition(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            for_update=True,
        )

        assert control is not None
        assert control.selection_mode is SelectionMode.DYNAMIC_SELECTION
        assert control.pending_selection_mode is None
        assert disposition is not None
        assert disposition.selected_members == SELECTED_MEMBERS

        generation = MaterializationGeneration(
            materialization_generation_id="generation:materialization:test",
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            strategy_version_id="sgv:SOR-001:v4",
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            selection_snapshot_id=disposition.snapshot.selection_snapshot_id,
            rollback_baseline_id=None,
            session_start_ms=SESSION_START_MS,
            previous_long_universe_version_id=LONG_UNIVERSE_ID,
            previous_short_universe_version_id=SHORT_UNIVERSE_ID,
            desired_member_count=2,
            semantic_digest="sha256:" + "d" * 64,
            lifecycle_state=MaterializationGenerationState.PENDING,
            fallback_reason_code=None,
            projection_version=1,
            created_at_ms=SESSION_START_MS + 3_600_001,
            desired_at_ms=None,
        )
        member_digest = selected_member_set_digest(SELECTED_MEMBERS)
        targets = (
            MaterializationTarget(
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                position_side="long",
                expected_member_set_digest=member_digest,
                materialization_order=1,
            ),
            MaterializationTarget(
                event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                position_side="short",
                expected_member_set_digest=member_digest,
                materialization_order=2,
            ),
        )
        await repository.add_pending_materialization_generation(
            generation,
            targets=targets,
        )
        desired = await repository.mark_materialization_generation_desired(
            generation.materialization_generation_id,
            expected_projection_version=1,
            desired_at_ms=SESSION_START_MS + 3_600_002,
        )

    assert desired.lifecycle_state is MaterializationGenerationState.DESIRED
    assert desired.projection_version == 2
    async with head_template_engine.connect() as connection:
        target_rows = (
            await connection.execute(
                sa.select(strategy_universe_materialization_targets).order_by(
                    strategy_universe_materialization_targets.c.materialization_order
                )
            )
        ).mappings().all()
        events = (
            await connection.execute(
                sa.select(strategy_universe_materialization_events.c.event_type)
                .order_by(strategy_universe_materialization_events.c.event_sequence)
            )
        ).scalars().all()

    assert [row["position_side"] for row in target_rows] == ["long", "short"]
    assert events == ["PENDING", "DESIRED"]


@pytest.mark.asyncio
async def test_repository_persists_valid_empty_intent_vacuum_without_authority(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000:valid-empty",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state="OPEN",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=1,
    )

    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.open_valid_empty_intent_vacuum(
            vacuum,
            selection_snapshot_id=(
                f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}"
            ),
        )
        persisted = await repository.get_current_entry_vacuum(
            strategy_group_id="SOR-001",
            selection_spec_id=SELECTION_SPEC_ID,
            for_update=True,
        )

    assert persisted == vacuum
    async with head_template_engine.connect() as connection:
        current_count = int(
            await connection.scalar(sa.select(sa.func.count()).select_from(
                strategy_entry_vacuums_current
            ))
            or 0
        )
        event = (
            await connection.execute(sa.select(strategy_entry_vacuum_events))
        ).mappings().one()
    assert current_count == 1
    assert event["event_type"] == "OPEN"
    assert event["payload"]["intended_authority_outcome"] == "VALID_EMPTY"


@pytest.mark.asyncio
async def test_valid_empty_finalizes_vacuum_authority_and_pending_mode_atomically(
    head_template_engine,
) -> None:
    await _seed_materialization_context(
        head_template_engine,
        selected_members=(),
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
    )
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000:valid-empty-final",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state="OPEN",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=1,
    )
    async with head_template_engine.begin() as connection:
        await PostgresInstrumentSelectionRepository(
            connection
        ).open_valid_empty_intent_vacuum(
            vacuum,
            selection_snapshot_id=(
                f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}"
            ),
        )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        started = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_020,
            ),
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        committed = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_030,
            ),
        )

    assert started.status is VacuumDrainStatus.DRAIN_STARTED
    assert committed.status is VacuumDrainStatus.VALID_EMPTY_COMMITTED
    async with head_template_engine.connect() as connection:
        vacuum_row = (
            await connection.execute(
                sa.select(strategy_entry_vacuums_current).where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id
                    == vacuum.entry_vacuum_id
                )
            )
        ).mappings().one()
        authority_row = (
            await connection.execute(
                sa.select(selection_session_authorities).where(
                    selection_session_authorities.c.selection_authority_id
                    == committed.selection_authority_id
                )
            )
        ).mappings().one()
        current_authority_id = await connection.scalar(
            sa.select(selection_authority_current.c.selection_authority_id).where(
                selection_authority_current.c.selection_spec_id == SELECTION_SPEC_ID
            )
        )
        control_row = (
            await connection.execute(
                sa.select(strategy_selection_control_current).where(
                    strategy_selection_control_current.c.strategy_group_id
                    == "SOR-001"
                )
            )
        ).mappings().one()
    assert vacuum_row["state"] == "VALID_EMPTY"
    assert vacuum_row["drained_at_ms"] == SESSION_START_MS + 3_600_030
    assert vacuum_row["resolved_at_ms"] == SESSION_START_MS + 3_600_030
    assert authority_row["authority_outcome"] == "VALID_EMPTY"
    assert current_authority_id == committed.selection_authority_id
    assert control_row["selection_mode"] == "dynamic_selection"
    assert control_row["pending_selection_mode"] is None


@pytest.mark.asyncio
async def test_valid_empty_rejects_generation_free_vacuum_with_wrong_intent(
    head_template_engine,
) -> None:
    await _seed_materialization_context(
        head_template_engine,
        selected_members=(),
    )
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000:wrong-intent",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state="DRAINING_ENTRY",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="OWNER_PAUSE",
        projection_version=2,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        result = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_020,
            ),
        )

    assert result.status is VacuumDrainStatus.BLOCKED
    assert result.reason_code == "VALID_EMPTY_VACUUM_INTENT_INVALID"
    async with head_template_engine.connect() as connection:
        persisted_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == vacuum.entry_vacuum_id
            )
        )
        authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(selection_session_authorities)
            )
            or 0
        )
    assert persisted_state == "DRAINING_ENTRY"
    assert authority_count == 0


@pytest.mark.asyncio
async def test_valid_empty_is_non_retroactive_for_protected_ticket(
    head_template_engine,
) -> None:
    ticket = registered_sor_long_ticket()
    await reach_position_protected(head_template_engine, ticket)
    await _seed_materialization_context(
        head_template_engine,
        selected_members=(),
        include_current_pair=False,
        seed_current_runtime=False,
    )
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000:protected-ticket",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state="DRAINING_ENTRY",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=2,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        before = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation_before = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        result = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_020,
            ),
        )
        after = await uow.aggregates.get(ticket.identity.ticket_id)
        reservation_after = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        domain_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key()
        )

    assert result.status is VacuumDrainStatus.VALID_EMPTY_COMMITTED
    assert before is not None and after is not None
    assert after.status == before.status
    assert after.position_qty == before.position_qty == ticket.quantity
    assert after.version == before.version
    assert reservation_after == reservation_before
    assert reservation_after is not None and reservation_after.status == "active"
    assert domain_active is True


@pytest.mark.asyncio
async def test_repository_opens_new_vacuum_after_previous_operation_is_terminal(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    previous = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:previous:valid-empty",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS - 86_400_000,
        source_generation_id=None,
        state="VALID_EMPTY",
        fenced_at_ms=SESSION_START_MS - 82_800_000,
        drained_at_ms=SESSION_START_MS - 82_799_000,
        resolved_at_ms=SESSION_START_MS - 82_798_000,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=3,
    )
    current = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:current:valid-empty",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=None,
        state="OPEN",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="NO_SELECTION_READY_MEMBERS",
        projection_version=1,
    )

    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **previous.model_dump(mode="json")
            )
        )
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.open_valid_empty_intent_vacuum(
            current,
            selection_snapshot_id=f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}",
        )
        persisted = await repository.get_current_entry_vacuum(
            strategy_group_id="SOR-001",
            selection_spec_id=SELECTION_SPEC_ID,
            for_update=True,
        )

    assert persisted == current


@pytest.mark.asyncio
async def test_gap_audit_completion_persists_positive_and_checked_negative_proof(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:materialization:test",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
        proposed_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        unauthorized_from_close_time_ms=SESSION_START_MS + 4_500_000,
        detector_semantic_digest="sha256:" + "e" * 64,
        created_at_ms=SESSION_START_MS + 4_500_001,
    )
    scopes = (
        AuthorityGapScope(
            event_spec_id=SOR_LONG_EVENT_SPEC_ID,
            exchange_instrument_id=SELECTED_MEMBERS[0],
        ),
        AuthorityGapScope(
            event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
            exchange_instrument_id=SELECTED_MEMBERS[0],
        ),
    )
    results = (
        AuthorityGapScopeResult(
            scope=scopes[0],
            session_reference=str(SESSION_START_MS),
            first_natural_trigger_at_ms=SESSION_START_MS + 4_500_000,
        ),
        AuthorityGapScopeResult(
            scope=scopes[1],
            session_reference=str(SESSION_START_MS),
            first_natural_trigger_at_ms=None,
        ),
    )
    completed = complete_authority_gap_audit(
        audit,
        audited_through_close_time_ms=SESSION_START_MS + 4_500_000,
        scopes=scopes,
        results=results,
    )

    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.add_pending_authority_gap_audit(audit)
        await repository.complete_authority_gap_audit(
            completed,
            results=results,
            completed_at_ms=SESSION_START_MS + 4_500_001,
        )
        persisted = await repository.get_authority_gap_audit(
            audit.authority_gap_audit_id,
            for_update=True,
        )

    assert persisted == completed
    async with head_template_engine.connect() as connection:
        suppressions = (
            await connection.execute(sa.select(strategy_trigger_suppressions))
        ).mappings().all()
        events = (
            await connection.execute(
                sa.select(selection_authority_gap_audit_events.c.event_type).order_by(
                    selection_authority_gap_audit_events.c.event_sequence
                )
            )
        ).scalars().all()
    assert len(suppressions) == 1
    assert suppressions[0]["exchange_instrument_id"] == SELECTED_MEMBERS[0]
    assert events == ["STARTED", "TRIGGER_SUPPRESSED", "CHECKED_NEGATIVE", "COMPLETE"]


@pytest.mark.asyncio
async def test_coordinator_creates_continuity_then_no_change_from_durable_snapshot(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    clock = _Clock(SESSION_START_MS + 3_600_000)
    request = CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=SESSION_START_MS,
        worker_id="materializer:test",
    )

    continuity = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    no_change = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert no_change.disposition is MaterializationDisposition.NO_CHANGE
    async with head_template_engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text(
                    "SELECT authority_sequence, authority_outcome "
                    "FROM brc_selection_session_authorities "
                    "WHERE session_start_ms = :session_start_ms "
                    "ORDER BY authority_sequence"
                ),
                {"session_start_ms": SESSION_START_MS},
            )
        ).all()
    assert rows == [(1, "PRE_FENCE_CONTINUITY"), (2, "NO_CHANGE")]


@pytest.mark.asyncio
async def test_late_continuity_stages_and_completes_exact_gap_audit_before_grant(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    clock = _Clock(SESSION_START_MS + 4_500_000)
    request = CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=SESSION_START_MS,
        worker_id="materializer:late-test",
    )

    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert pending.authority_gap_audit_id is not None

    completed = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=clock,
    )

    assert completed.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    async with head_template_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.text(
                    "SELECT authority_outcome, authority_gap_audit_id, "
                    "grant_proof_kind, first_eligible_close_time_ms "
                    "FROM brc_selection_session_authorities "
                    "WHERE session_start_ms = :session_start_ms"
                ),
                {"session_start_ms": SESSION_START_MS},
            )
        ).one()
    assert row == (
        "PRE_FENCE_CONTINUITY",
        pending.authority_gap_audit_id,
        "AUDITED_AUTHORITY_GAP",
        SESSION_START_MS + 5_400_000,
    )


@pytest.mark.asyncio
async def test_owner_pause_creates_no_continuity_generation_or_vacuum(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                entry_state="paused",
                control_version=2,
                reason="owner_pause_test",
                updated_at_ms=SESSION_START_MS + 3_600_000,
            )
        )

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:paused"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_000),
    )

    assert result.disposition is MaterializationDisposition.OWNER_PAUSED
    async with head_template_engine.connect() as connection:
        counts = {
            table.name: int(
                await connection.scalar(sa.select(sa.func.count()).select_from(table))
                or 0
            )
            for table in (
                selection_session_authorities,
                strategy_universe_materialization_generations,
                strategy_entry_vacuums_current,
            )
        }
    assert counts == {
        "brc_selection_session_authorities": 1,
        "brc_strategy_universe_materialization_generations": 0,
        "brc_strategy_entry_vacuums_current": 0,
    }


@pytest.mark.asyncio
async def test_first_pending_dynamic_without_snapshot_keeps_static_without_predecessor(
    head_template_engine,
) -> None:
    await _seed_materialization_context(
        head_template_engine,
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
        include_snapshot=False,
    )

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:first-pending"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_000),
    )

    assert result.disposition is MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC
    async with head_template_engine.connect() as connection:
        authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(selection_session_authorities)
            )
            or 0
        )
    assert authority_count == 0


@pytest.mark.asyncio
async def test_changed_snapshot_advances_pending_then_desired_from_db_only(
    head_template_engine,
) -> None:
    changed_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[2],
            )
        )
    )
    await _seed_materialization_context(
        head_template_engine,
        selected_members=changed_members,
    )
    await _seed_previous_dynamic_authority(head_template_engine)
    request = _materialization_request("materializer:generation")
    clock = _Clock(SESSION_START_MS + 3_600_000)

    continuity = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    desired = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    fenced = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        drained = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_010,
            ),
        )

    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert pending.disposition is MaterializationDisposition.GENERATION_PENDING
    assert desired.disposition is MaterializationDisposition.GENERATION_DESIRED
    assert pending.materialization_generation_id == desired.materialization_generation_id
    assert fenced.disposition is MaterializationDisposition.WAITING_VACUUM
    assert fenced.entry_vacuum_id is not None
    assert drained.status is VacuumDrainStatus.ENTRY_DRAINED
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == desired.materialization_generation_id
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.entry_vacuum_id
                == fenced.entry_vacuum_id
            )
        )
    assert generation_state == "MATERIALIZING"
    assert vacuum_state == "RECONFIGURING"


@pytest.mark.asyncio
async def test_pending_generation_is_abandoned_when_frozen_previous_pair_drifts(
    head_template_engine,
) -> None:
    changed_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[2],
            )
        )
    )
    await _seed_materialization_context(
        head_template_engine,
        selected_members=changed_members,
    )
    await _seed_previous_dynamic_authority(head_template_engine)
    request = _materialization_request("materializer:abandon-drift")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert pending.materialization_generation_id is not None

    drifted_long_id = "universe:materialization:long:drifted"
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id=drifted_long_id,
                strategy_group_id="SOR-001",
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                universe_version=99,
                semantic_digest="sha256:" + "7" * 64,
                lifecycle_state="retired",
                source_kind="manual",
                materialization_generation_id=None,
                installed_at_ms=SESSION_START_MS - 10_000,
                activated_at_ms=SESSION_START_MS - 9_000,
                retired_at_ms=SESSION_START_MS - 8_000,
                abandoned_at_ms=None,
                abandon_reason_code=None,
            )
        )
        await connection.execute(
            sa.update(strategy_universe_materialization_generations)
            .where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == pending.materialization_generation_id
            )
            .values(previous_long_universe_version_id=drifted_long_id)
        )

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    retry = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "GENERATION_PREVIOUS_PAIR_DRIFT"
    assert retry.disposition is MaterializationDisposition.BLOCKED
    assert retry.reason_code == "GENERATION_ABANDONED"
    async with head_template_engine.connect() as connection:
        state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == pending.materialization_generation_id
            )
        )
    assert state == "ABANDONED"


@pytest.mark.asyncio
async def test_valid_empty_intent_vacuum_blocks_previous_current_authority(
    head_template_engine,
) -> None:
    await _seed_materialization_context(
        head_template_engine,
        selected_members=(),
    )
    await _seed_previous_dynamic_authority(head_template_engine)
    request = _materialization_request("materializer:valid-empty")
    clock = _Clock(SESSION_START_MS + 3_600_000)

    continuity = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    valid_empty_intent = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert valid_empty_intent.disposition is MaterializationDisposition.VALID_EMPTY_INTENT
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        current_authority = await repository.get_current_authority(SELECTION_SPEC_ID)
        vacuum = await repository.get_current_entry_vacuum(
            strategy_group_id="SOR-001",
            selection_spec_id=SELECTION_SPEC_ID,
            for_update=True,
        )
    assert current_authority is not None
    assert vacuum is not None
    assert current_authority.authority_outcome is AuthorityOutcome.PRE_FENCE_CONTINUITY
    assert not selection_authority_allows_new_entry(
        current_authority,
        now_ms=SESSION_START_MS + 4_500_001,
        observed_close_time_ms=SESSION_START_MS + 4_500_000,
        scoped_vacuum_open=vacuum.blocks_new_entry,
    )


@pytest.mark.asyncio
async def test_on_time_continuity_rejects_predecessor_pair_drift(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(
        head_template_engine,
        authorized_pair=UniverseAuthorityPair(
            long_universe_version_id=SHORT_UNIVERSE_ID,
            short_universe_version_id=LONG_UNIVERSE_ID,
        ),
    )

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:predecessor-drift"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_000),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "DYNAMIC_PREDECESSOR_AUTHORITY_DRIFT"


@pytest.mark.asyncio
async def test_existing_continuity_rejects_owner_control_version_drift(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    request = _materialization_request("materializer:owner-version-drift")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    continuity = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                control_version=2,
                reason="simulated_control_identity_drift",
                updated_at_ms=SESSION_START_MS + 3_600_010,
            )
        )

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "DYNAMIC_PREDECESSOR_AUTHORITY_DRIFT"


@pytest.mark.asyncio
async def test_expired_snapshot_is_not_materialized(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:expired-snapshot"),
        clock_ms=_Clock(SESSION_START_MS + 90_000_000),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "SELECTION_SNAPSHOT_EXPIRED"


@pytest.mark.asyncio
async def test_gap_audit_window_expiry_does_not_commit_proof_or_authority(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:expiry"),
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert pending.authority_gap_audit_id is not None

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_SequenceClock(
            SESSION_START_MS + 4_500_001,
            SESSION_START_MS + 5_400_000,
        ),
    )

    assert result.disposition is MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED
    async with head_template_engine.connect() as connection:
        audit_state = await connection.scalar(
            sa.select(selection_authority_gap_audits_current.c.state).where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == pending.authority_gap_audit_id
            )
        )
        current_session_authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(
                    selection_session_authorities.c.session_start_ms
                    == SESSION_START_MS
                )
            )
            or 0
        )
    assert audit_state == "PENDING"
    assert current_session_authority_count == 0

    retry_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:expiry-retry"),
        clock_ms=_Clock(SESSION_START_MS + 5_400_000),
    )
    assert retry_pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert retry_pending.authority_gap_audit_id == pending.authority_gap_audit_id

    completed = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_010),
    )
    assert completed.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY


@pytest.mark.asyncio
async def test_gap_audit_current_pair_projection_drift_fails_closed(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:drift"),
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert pending.authority_gap_audit_id is not None

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_PairProjectionDriftAuditSource(head_template_engine),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 4_500_010),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "AUTHORITY_GAP_AUDIT_RUNTIME_DRIFT"
    async with head_template_engine.connect() as connection:
        audit_state = await connection.scalar(
            sa.select(selection_authority_gap_audits_current.c.state).where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == pending.authority_gap_audit_id
            )
        )
    assert audit_state == "PENDING"


@pytest.mark.asyncio
async def test_gap_audit_missing_scope_result_is_persisted_failed_without_authority(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:missing-scope"),
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert pending.authority_gap_audit_id is not None

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_MissingScopeAuditSource(),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 4_500_010),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "AUTHORITY_GAP_AUDIT_INCOMPLETE"
    async with head_template_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    selection_authority_gap_audits_current.c.state,
                    selection_authority_gap_audits_current.c.first_blocker,
                ).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == pending.authority_gap_audit_id
                )
            )
        ).one()
        current_session_authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(
                    selection_session_authorities.c.session_start_ms
                    == SESSION_START_MS
                )
            )
            or 0
        )
    assert row == ("FAILED", "AUTHORITY_GAP_AUDIT_INCOMPLETE")
    assert current_session_authority_count == 0


@pytest.mark.asyncio
async def test_gap_audit_detector_identity_drift_is_persisted_failed(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:detector-drift:test",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
        proposed_authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        unauthorized_from_close_time_ms=SESSION_START_MS + 4_500_000,
        detector_semantic_digest="sha256:" + "0" * 64,
        created_at_ms=SESSION_START_MS + 4_500_001,
    )
    async with head_template_engine.begin() as connection:
        await PostgresInstrumentSelectionRepository(
            connection
        ).add_pending_authority_gap_audit(audit)

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 4_500_010),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "AUTHORITY_GAP_DETECTOR_IDENTITY_DRIFT"
    async with head_template_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    selection_authority_gap_audits_current.c.state,
                    selection_authority_gap_audits_current.c.first_blocker,
                ).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == audit.authority_gap_audit_id
                )
            )
        ).one()
    assert row == ("FAILED", "AUTHORITY_GAP_DETECTOR_IDENTITY_DRIFT")


async def _seed_materialization_context(
    engine,
    *,
    selected_members: tuple[str, ...] = SELECTED_MEMBERS,
    selection_mode: str = "dynamic_selection",
    pending_selection_mode: str | None = None,
    include_snapshot: bool = True,
    include_current_pair: bool = True,
    seed_current_runtime: bool = True,
) -> None:
    if seed_current_runtime:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="selection-materialization-test",
                    runtime_commit="selection-materialization-test",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=SESSION_START_MS,
                ),
            )
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(instruments).on_conflict_do_nothing(),
            [
                {
                    "exchange_instrument_id": instrument_id,
                    "venue_id": "binance-usdm",
                    "asset_class": "crypto",
                    "venue_symbol": instrument_id.split(":")[1],
                    "contract_kind": "perpetual",
                    "status": "pending_certification",
                }
                for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ],
        )
        await connection.execute(
            pg_insert(instrument_product_profiles).on_conflict_do_nothing(),
            [
                {
                    "exchange_instrument_id": instrument_id,
                    "product_family": "crypto_perpetual",
                    "asset_class": "crypto",
                    "contract_type": "PERPETUAL",
                    "underlying_type": "CRYPTO",
                    "margin_asset": "USDT",
                    "entry_session_policy": "continuous",
                    "status": "candidate",
                    "max_entry_spread_bps": None,
                    "max_mark_index_deviation_bps": None,
                    "semantic_digest": "sha256:" + "9" * 64,
                    "updated_at_ms": SESSION_START_MS,
                }
                for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ],
        )
        await connection.execute(
            sa.insert(instrument_selection_specs).values(
                selection_spec_id=SELECTION_SPEC_ID,
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest=ALGORITHM_DIGEST,
                status="active",
                installed_at_ms=SESSION_START_MS,
            )
        )
        await connection.execute(
            sa.insert(sor_dynamic_selection_specs_v0).values(
                selection_spec_id=SELECTION_SPEC_ID,
                decision_offset_utc_seconds=3600,
                feature_cutoff_offset_utc_seconds=3600,
                eligibility_not_before_offset_utc_seconds=4500,
                valid_until_next_decision_offset_seconds=86400,
                candidate_count=24,
                selected_count_max=7,
                near_count_max=7,
                activity_floor_quote_usdt=Decimal(20_000_000),
                materialization_timeout_seconds=1800,
            )
        )
        await connection.execute(
            sa.insert(instrument_selection_spec_events),
            [
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "event_spec_id": SOR_LONG_EVENT_SPEC_ID,
                    "position_side": "long",
                },
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "event_spec_id": SOR_SHORT_EVENT_SPEC_ID,
                    "position_side": "short",
                },
            ],
        )
        await connection.execute(
            sa.insert(instrument_selection_spec_members),
            [
                {
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "exchange_instrument_id": instrument_id,
                }
                for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            ],
        )
        if include_current_pair:
            await _seed_current_universe_pair(connection)
        if pending_selection_mode is not None:
            await connection.execute(
                sa.insert(owner_authorizations).values(
                    authorization_id="owner-authorization:selection-mode:test",
                    purpose="universe_configure",
                    owner_identity="test-owner",
                    authentication_strength="session",
                    request_digest="sha256:" + "8" * 64,
                    target_scope={"strategy_group_id": "SOR-001"},
                    idempotency_key="owner-request:selection-mode:test",
                    authorized_at_ms=SESSION_START_MS,
                )
            )
        await connection.execute(
            sa.insert(strategy_selection_control_current).values(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                selection_mode=selection_mode,
                pending_selection_mode=pending_selection_mode,
                pending_effective_session_start_ms=(
                    SESSION_START_MS if pending_selection_mode is not None else None
                ),
                pending_authorization_id=(
                    "owner-authorization:selection-mode:test"
                    if pending_selection_mode is not None
                    else None
                ),
                control_version=1,
                rollback_baseline_id=None,
                updated_at_ms=SESSION_START_MS,
            )
        )
        await connection.execute(
            pg_insert(strategy_entry_controls_current)
            .values(
                strategy_group_id="SOR-001",
                entry_state="enabled",
                control_version=1,
                last_event_id="strategy-control-event:selection-materialization:test",
                reason="selection_materialization_test_enabled",
                updated_at_ms=SESSION_START_MS,
            )
            .on_conflict_do_nothing(
                index_elements=[strategy_entry_controls_current.c.strategy_group_id]
            )
        )
        if include_snapshot:
            await _seed_snapshot(connection, selected_members=selected_members)


async def _seed_current_universe_pair(connection) -> None:
    digest = "sha256:" + "f" * 64
    await connection.execute(
        sa.insert(strategy_universe_versions),
        [
            {
                "universe_version_id": LONG_UNIVERSE_ID,
                "strategy_group_id": "SOR-001",
                "event_spec_id": SOR_LONG_EVENT_SPEC_ID,
                "universe_version": 1,
                "semantic_digest": digest,
                "lifecycle_state": "active",
                "source_kind": "manual",
                "materialization_generation_id": None,
                "installed_at_ms": SESSION_START_MS,
                "activated_at_ms": SESSION_START_MS + 1,
                "retired_at_ms": None,
                "abandoned_at_ms": None,
                "abandon_reason_code": None,
            },
            {
                "universe_version_id": SHORT_UNIVERSE_ID,
                "strategy_group_id": "SOR-001",
                "event_spec_id": SOR_SHORT_EVENT_SPEC_ID,
                "universe_version": 1,
                "semantic_digest": digest,
                "lifecycle_state": "active",
                "source_kind": "manual",
                "materialization_generation_id": None,
                "installed_at_ms": SESSION_START_MS,
                "activated_at_ms": SESSION_START_MS + 1,
                "retired_at_ms": None,
                "abandoned_at_ms": None,
                "abandon_reason_code": None,
            },
        ],
    )
    await connection.execute(
        sa.insert(strategy_universe_members),
        [
            {
                "universe_version_id": universe_id,
                "exchange_instrument_id": instrument_id,
            }
            for universe_id in (LONG_UNIVERSE_ID, SHORT_UNIVERSE_ID)
            for instrument_id in SELECTED_MEMBERS
        ],
    )
    await connection.execute(
        sa.insert(strategy_universe_current),
        [
            {
                "event_spec_id": SOR_LONG_EVENT_SPEC_ID,
                "universe_version_id": LONG_UNIVERSE_ID,
                "semantic_digest": digest,
                "lifecycle_state": "active",
                "activation_generation": 1,
                "activated_at_ms": SESSION_START_MS + 1,
            },
            {
                "event_spec_id": SOR_SHORT_EVENT_SPEC_ID,
                "universe_version_id": SHORT_UNIVERSE_ID,
                "semantic_digest": digest,
                "lifecycle_state": "active",
                "activation_generation": 1,
                "activated_at_ms": SESSION_START_MS + 1,
            },
        ],
    )


async def _seed_snapshot(
    connection,
    *,
    selected_members: tuple[str, ...] = SELECTED_MEMBERS,
) -> None:
    snapshot_id = f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}"
    ranks = {instrument_id: index + 1 for index, instrument_id in enumerate(selected_members)}
    await connection.execute(
        sa.insert(instrument_selection_snapshots).values(
            selection_snapshot_id=snapshot_id,
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            strategy_version_id="sgv:SOR-001:v4",
            session_start_ms=SESSION_START_MS,
            decision_at_ms=SESSION_START_MS + 3_600_000,
            feature_cutoff_at_ms=SESSION_START_MS + 3_600_000,
            eligibility_not_before_ms=SESSION_START_MS + 4_500_000,
            expires_at_ms=SESSION_START_MS + 90_000_000,
            candidate_count=24,
            ready_count=len(selected_members),
            selected_count=len(selected_members),
            source_observed_at_ms=SESSION_START_MS + 3_600_000,
            source_semantic_digest="sha256:" + "1" * 64,
            selection_semantic_digest="sha256:" + "2" * 64,
            created_at_ms=SESSION_START_MS + 3_600_000,
        )
    )
    await connection.execute(
        sa.insert(instrument_selection_member_decisions),
        [
            {
                "selection_snapshot_id": snapshot_id,
                "member_decision_id": f"member:{index}",
                "selection_spec_id": SELECTION_SPEC_ID,
                "session_start_ms": SESSION_START_MS,
                "feature_cutoff_at_ms": SESSION_START_MS + 3_600_000,
                "input_window_start_ms": SESSION_START_MS - 82_800_000,
                "input_window_end_ms": SESSION_START_MS + 3_600_000,
                "exchange_instrument_id": instrument_id,
                "input_window_digest": "sha256:" + "3" * 64,
                "source_status": "READY",
                "or_high": Decimal(101),
                "or_low": Decimal(99),
                "or_width": Decimal(2),
                "pre_or_atr14": Decimal(1),
                "pre_or_width_atr14": Decimal(index + 1),
                "trailing_24h_quote_volume": Decimal(30000000),
                "or_geometry_valid": True,
                "atr_valid": True,
                "activity_valid": instrument_id in ranks,
                "selection_ready": instrument_id in ranks,
                "primary_reason": None if instrument_id in ranks else "LOW_ACTIVITY",
                "secondary_reasons": [],
                "stable_rank": ranks.get(instrument_id),
                "member_state": (
                    "SELECTED" if instrument_id in ranks else "INELIGIBLE"
                ),
                "selected": instrument_id in ranks,
                "member_semantic_digest": "sha256:" + f"{index:064x}",
            }
            for index, instrument_id in enumerate(
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
            )
        ],
    )


async def _seed_previous_dynamic_authority(
    engine,
    *,
    authorized_pair: UniverseAuthorityPair | None = None,
) -> None:
    previous_session_start_ms = SESSION_START_MS - 86_400_000
    authority = SelectionSessionAuthority(
        selection_authority_id="selection-authority:previous:no-change",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=previous_session_start_ms,
        decision_boundary_ms=previous_session_start_ms + 3_600_000,
        authority_sequence=1,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}",
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.NO_CHANGE,
        authorized_pair=(
            authorized_pair
            or UniverseAuthorityPair(
                long_universe_version_id=LONG_UNIVERSE_ID,
                short_universe_version_id=SHORT_UNIVERSE_ID,
            )
        ),
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id="static-baseline:test",
            authority_gap_audit_id=None,
        ),
        effective_from_ms=previous_session_start_ms + 3_600_000,
        first_eligible_close_time_ms=previous_session_start_ms + 4_500_000,
        expires_at_ms=SESSION_START_MS + 3_600_000,
        reason_code="PREVIOUS_DYNAMIC_NO_CHANGE",
        created_at_ms=previous_session_start_ms + 3_600_001,
    )
    async with engine.begin() as connection:
        await PostgresInstrumentSelectionRepository(
            connection
        ).add_authority_and_set_current(authority, expected_current_version=None)
class _Clock:
    def __init__(self, now_ms: int) -> None:
        self._now_ms = now_ms

    def __call__(self) -> int:
        self._now_ms += 1
        return self._now_ms


class _SequenceClock:
    def __init__(self, *values: int) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


class _CheckedNegativeAuditSource:
    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        return tuple(
            AuthorityGapScopeResult(
                scope=scope,
                session_reference=str(request.audit.session_start_ms),
                first_natural_trigger_at_ms=None,
            )
            for scope in request.scopes
        )


class _PairProjectionDriftAuditSource(_CheckedNegativeAuditSource):
    def __init__(self, engine) -> None:
        self._engine = engine

    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        async with self._engine.begin() as connection:
            await connection.execute(
                sa.update(strategy_universe_current)
                .where(strategy_universe_current.c.event_spec_id == SOR_LONG_EVENT_SPEC_ID)
                .values(activation_generation=2)
            )
        return await super().evaluate_authority_gap(request)


class _MissingScopeAuditSource(_CheckedNegativeAuditSource):
    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        results = await super().evaluate_authority_gap(request)
        return results[:-1]


def _materialization_request(worker_id: str) -> CoordinateSelectionMaterializationRequest:
    return CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=SESSION_START_MS,
        worker_id=worker_id,
    )
