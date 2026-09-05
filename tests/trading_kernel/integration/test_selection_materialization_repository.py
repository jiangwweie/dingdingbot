from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
    abandon_strategy_universe,
)
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationOperation,
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditDetectorDriftError,
    AuthorityGapAuditEvaluationRequest,
    AuthorityGapAuditSourceIntegrityError,
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
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    UniverseInstallStatus,
    install_strategy_universe,
)
from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    set_strategy_entry_state,
    stage_dynamic_selection_mode,
)
from src.trading_kernel.application.recover_expired_dynamic_activation import (
    ExpiredDynamicActivationRecoveryStatus,
    RecoverExpiredDynamicActivationRequest,
    recover_expired_dynamic_activation,
)
from src.trading_kernel.application.runtime import (
    RuntimeCompatibilityClassification,
    RuntimeReleaseCompatibilityFact,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.product import InstrumentProductProfile
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAuditKind,
    AuthorityGapScope,
    AuthorityGapScopeResult,
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    MaterializationGeneration,
    MaterializationGenerationClaimStatus,
    MaterializationGenerationState,
    MaterializationTarget,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    build_pending_authority_gap_audit,
    complete_authority_gap_audit,
    fail_authority_gap_audit,
    selected_member_set_digest,
    selection_authority_allows_new_entry,
)
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
    SelectionJobConflict,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_certification_current,
    instrument_product_profiles,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    instrument_selection_spec_events,
    instrument_selection_spec_members,
    instrument_selection_specs,
    instruments,
    owner_authorizations,
    runtime_release_compatibility_facts,
    runtime_scopes_current,
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
from src.trading_kernel.interfaces.readonly_api import (
    SelectionRuntimeReadonlyRequest,
    get_selection_runtime_view,
)
from tests.trading_kernel.integration.universe_activation_support import (
    make_warming_ready,
)
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
async def test_runtime_release_compatibility_fact_is_exactly_idempotent_and_immutable(
    head_template_engine,
) -> None:
    fact = RuntimeReleaseCompatibilityFact(
        release_compatibility_id="release-compatibility:" + "a" * 40 + ":" + "b" * 40,
        from_commit="a" * 40,
        to_commit="b" * 40,
        from_schema_revision="0005_tradfi_instrument_center",
        to_schema_revision=CURRENT_SCHEMA_REVISION,
        classification=RuntimeCompatibilityClassification.COMPATIBLE_RESTART,
        compatibility_basis_digest="sha256:" + "c" * 64,
        reason_codes=("PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",),
        certification_manifest_digest="sha256:" + "e" * 64,
        created_at_ms=SESSION_START_MS,
    )
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.add_runtime_release_compatibility_fact(fact)
        await repository.add_runtime_release_compatibility_fact(fact)
        assert (
            await repository.get_runtime_release_compatibility_fact(
                fact.release_compatibility_id
            )
            == fact
        )

    conflicting = fact.model_copy(
        update={"certification_manifest_digest": "sha256:" + "f" * 64}
    )
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        with pytest.raises(SelectionJobConflict, match="compatibility fact conflicts"):
            await repository.add_runtime_release_compatibility_fact(conflicting)

    async with head_template_engine.connect() as connection:
        assert int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    runtime_release_compatibility_facts
                )
            )
            or 0
        ) == 1


@pytest.mark.asyncio
async def test_selection_runtime_readonly_projects_one_exact_period_without_writes(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    snapshot_id = f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}"
    generation = MaterializationGeneration(
        materialization_generation_id="generation:readonly:test",
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=snapshot_id,
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
    vacuum = StrategyEntryVacuum(
        entry_vacuum_id="vacuum:SOR-001:1704067200000:readonly",
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        source_generation_id=generation.materialization_generation_id,
        state="DRAINING_ENTRY",
        fenced_at_ms=SESSION_START_MS + 3_600_010,
        drained_at_ms=None,
        resolved_at_ms=None,
        first_blocker="DESIRED_MEMBERS_CHANGED",
        projection_version=2,
    )
    pending_audit = build_pending_authority_gap_audit(
        authority_gap_audit_id=(
            f"gap-audit:{SELECTION_SPEC_ID}:{SESSION_START_MS}:"
            "ENTRY_VACUUM:ACTIVE_NEW"
        ),
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        proposed_authority_outcome=AuthorityOutcome.ACTIVE_NEW,
        unauthorized_from_close_time_ms=SESSION_START_MS + 4_500_000,
        detector_semantic_digest="sha256:" + "a" * 64,
        created_at_ms=SESSION_START_MS + 3_600_020,
        source_entry_vacuum_id=vacuum.entry_vacuum_id,
        source_generation_id=generation.materialization_generation_id,
    )
    audit = fail_authority_gap_audit(
        pending_audit,
        first_blocker="AUTHORITY_GAP_SOURCE_UNAVAILABLE",
    )
    authority = SelectionSessionAuthority(
        selection_authority_id=(
            f"selection-authority:{SELECTION_SPEC_ID}:{SESSION_START_MS}:1"
        ),
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 3_600_000,
        authority_sequence=1,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=snapshot_id,
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.NO_CHANGE,
        authorized_pair=UniverseAuthorityPair(
            long_universe_version_id=LONG_UNIVERSE_ID,
            short_universe_version_id=SHORT_UNIVERSE_ID,
        ),
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=(
                f"static-baseline:{LONG_UNIVERSE_ID}:{SHORT_UNIVERSE_ID}"
            ),
            authority_gap_audit_id=None,
        ),
        effective_from_ms=SESSION_START_MS + 3_600_001,
        first_eligible_close_time_ms=SESSION_START_MS + 4_500_000,
        expires_at_ms=SESSION_START_MS + 90_000_000,
        reason_code="FIRST_DYNAMIC_MEMBERS_UNCHANGED",
        created_at_ms=SESSION_START_MS + 3_600_001,
    )
    release_fact = RuntimeReleaseCompatibilityFact(
        release_compatibility_id="release-compatibility:" + "a" * 40 + ":" + "b" * 40,
        from_commit="a" * 40,
        to_commit="b" * 40,
        from_schema_revision="0005_tradfi_instrument_center",
        to_schema_revision=CURRENT_SCHEMA_REVISION,
        classification=RuntimeCompatibilityClassification.COMPATIBLE_RESTART,
        compatibility_basis_digest="sha256:" + "c" * 64,
        reason_codes=("PERSISTED_ACTIVE_UNIVERSE_CONTRACT_UNCHANGED",),
        certification_manifest_digest="sha256:" + "e" * 64,
        created_at_ms=SESSION_START_MS + 3_600_030,
    )
    member_digest = selected_member_set_digest(SELECTED_MEMBERS)
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await connection.execute(
            sa.insert(instrument_selection_jobs_current).values(
                selection_job_id=f"selection-job:{SELECTION_SPEC_ID}:{SESSION_START_MS}",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
                scheduled_at_ms=SESSION_START_MS + 3_600_000,
                feature_cutoff_at_ms=SESSION_START_MS + 3_600_000,
                state="SNAPSHOT_READY",
                selection_snapshot_id=snapshot_id,
                first_blocker=None,
                attempt_count=1,
                next_retry_at_ms=None,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=3,
                updated_at_ms=SESSION_START_MS + 3_600_001,
            )
        )
        await repository.add_pending_materialization_generation(
            generation,
            targets=(
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
            ),
        )
        await connection.execute(
            sa.insert(strategy_entry_vacuums_current).values(
                **vacuum.model_dump(mode="json")
            )
        )
        await repository.add_pending_authority_gap_audit(pending_audit)
        pending = await repository.get_authority_gap_audit(
            audit.authority_gap_audit_id
        )
        assert pending is not None
        await repository.fail_authority_gap_audit(
            audit,
            failed_at_ms=SESSION_START_MS + 3_600_025,
        )
        await repository.add_authority_and_set_current(
            authority,
            expected_current_version=None,
        )
        await repository.add_runtime_release_compatibility_fact(release_fact)

    tables = (
        instrument_selection_jobs_current,
        instrument_selection_snapshots,
        strategy_universe_materialization_generations,
        strategy_entry_vacuums_current,
        selection_authority_gap_audits_current,
        selection_session_authorities,
        runtime_release_compatibility_facts,
    )
    async with head_template_engine.connect() as connection:
        before_values: list[int] = []
        for table in tables:
            before_values.append(
                int(
                    await connection.scalar(
                        sa.select(sa.func.count()).select_from(table)
                    )
                    or 0
                )
            )
        before = tuple(before_values)

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        view = await get_selection_runtime_view(
            uow,
            SelectionRuntimeReadonlyRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
                release_compatibility_id=release_fact.release_compatibility_id,
            ),
        )

    assert view.selection_control is not None
    assert view.selection_job is not None
    assert view.selection_job.state == "SNAPSHOT_READY"
    assert view.snapshot_disposition is not None
    assert view.materialization_generation == generation
    assert view.entry_vacuums == (vacuum,)
    assert view.authority_gap_audits == (audit,)
    assert view.current_authority is not None
    assert view.current_authority.authority == authority
    assert view.first_eligible_close_time_ms == SESSION_START_MS + 4_500_000
    assert view.release_compatibility_fact == release_fact

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        empty_period = await get_selection_runtime_view(
            uow,
            SelectionRuntimeReadonlyRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS + 86_400_000,
            ),
        )
    assert empty_period.selection_control is not None
    assert empty_period.selection_job is None
    assert empty_period.snapshot_disposition is None
    assert empty_period.materialization_generation is None
    assert empty_period.entry_vacuums == ()
    assert empty_period.authority_gap_audits == ()
    assert empty_period.current_authority is None
    assert empty_period.first_eligible_close_time_ms is None

    async with head_template_engine.connect() as connection:
        after_values: list[int] = []
        for table in tables:
            after_values.append(
                int(
                    await connection.scalar(
                        sa.select(sa.func.count()).select_from(table)
                    )
                    or 0
                )
            )
        after = tuple(after_values)
    assert after == before


@pytest.mark.asyncio
async def test_materialization_generation_lease_is_independent_and_recovers_after_expiry(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        disposition = await repository.get_snapshot_disposition(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
        )
        assert disposition is not None
        generation = MaterializationGeneration(
            materialization_generation_id="generation:lease:test",
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
        await repository.add_pending_materialization_generation(
            generation,
            targets=(
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
            ),
        )

    first_now = SESSION_START_MS + 3_600_010
    async with head_template_engine.begin() as connection:
        first = await PostgresInstrumentSelectionRepository(
            connection
        ).claim_materialization_generation(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="materializer:a",
            now_ms=first_now,
            lease_duration_ms=1_000,
        )
    assert first.status is MaterializationGenerationClaimStatus.CLAIMED
    assert first.lease_owner == "materializer:a"

    async with head_template_engine.begin() as connection:
        held = await PostgresInstrumentSelectionRepository(
            connection
        ).claim_materialization_generation(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="materializer:b",
            now_ms=first_now + 999,
            lease_duration_ms=1_000,
        )
    assert held.status is MaterializationGenerationClaimStatus.LEASE_HELD
    assert held.lease_owner == "materializer:a"

    async with head_template_engine.begin() as connection:
        recovered = await PostgresInstrumentSelectionRepository(
            connection
        ).claim_materialization_generation(
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            worker_id="materializer:b",
            now_ms=first_now + 1_000,
            lease_duration_ms=2_000,
        )
        await PostgresInstrumentSelectionRepository(
            connection
        ).release_materialization_generation_lease(
            materialization_generation_id=generation.materialization_generation_id,
            worker_id="materializer:b",
        )
    assert recovered.status is MaterializationGenerationClaimStatus.CLAIMED
    assert recovered.lease_owner == "materializer:b"

    async with head_template_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    strategy_universe_materialization_generations.c.lease_owner,
                    strategy_universe_materialization_generations.c.lease_expires_at_ms,
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation.materialization_generation_id
                )
            )
        ).one()
    assert row == (None, None)


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
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        readonly = await get_selection_runtime_view(
            uow,
            SelectionRuntimeReadonlyRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
            ),
        )
    assert readonly.entry_vacuums[0].state.value == "VALID_EMPTY"
    assert readonly.current_authority is not None
    assert readonly.current_authority.authority.authority_outcome.value == "VALID_EMPTY"
    assert readonly.first_eligible_close_time_ms is None


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
        # This is the real production-shaped Audit identity.  Concatenating it
        # with Event and Instrument identities exceeds the 160-character ID
        # column, so the suppression primary key must be a deterministic hash.
        authority_gap_audit_id=(
            "gap-audit:sor-dynamic-selection-v0:1788566400000:"
            "ENTRY_VACUUM:FALLBACK_PREVIOUS"
        ),
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
    assert len(str(suppressions[0]["trigger_suppression_id"])) <= 160
    assert str(suppressions[0]["trigger_suppression_id"]).startswith(
        "trigger-suppression:"
    )
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
    repeated = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert no_change.disposition is MaterializationDisposition.NO_CHANGE
    assert repeated.disposition is MaterializationDisposition.NO_CHANGE
    assert repeated.selection_authority_id == no_change.selection_authority_id
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
async def test_owner_pause_opens_durable_entry_vacuum_before_materialization(
    head_template_engine,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        paused = await set_strategy_entry_state(
            uow,
            strategy_group_id="SOR-001",
            target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(
                expected_version=1,
                reason="owner_pause_test",
                idempotency_key="owner-request:selection-pause:test",
                owner_identity="owner",
                now_ms=SESSION_START_MS + 3_600_000,
            ),
            authentication_strength="session",
        )
    assert paused.entry_state is StrategyEntryState.PAUSED

    result = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:paused"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_000),
    )

    assert result.disposition is MaterializationDisposition.OWNER_PAUSED
    async with head_template_engine.connect() as connection:
        vacuum = (
            await connection.execute(
                sa.select(
                    strategy_entry_vacuums_current.c.state,
                    strategy_entry_vacuums_current.c.first_blocker,
                    strategy_entry_vacuums_current.c.source_generation_id,
                ).where(
                    strategy_entry_vacuums_current.c.strategy_group_id == "SOR-001"
                )
            )
        ).one()
        generation_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    strategy_universe_materialization_generations
                )
            )
            or 0
        )
    assert vacuum == ("OPEN", "OWNER_PAUSED", None)
    assert generation_count == 0

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        started = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_010,
            ),
        )
    assert started.status is VacuumDrainStatus.DRAIN_STARTED

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        drained = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_020,
            ),
        )
    assert drained.status is VacuumDrainStatus.OWNER_PAUSED

    terminal = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:paused-terminal"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_030),
    )
    assert terminal.disposition is MaterializationDisposition.OWNER_PAUSED
    assert terminal.selection_authority_id is not None
    async with head_template_engine.connect() as connection:
        owner_pause_authority = (
            await connection.execute(
                sa.select(
                    selection_session_authorities.c.authority_outcome,
                    selection_session_authorities.c.materialization_generation_id,
                ).where(
                    selection_session_authorities.c.selection_authority_id
                    == terminal.selection_authority_id
                )
            )
        ).one()
    assert owner_pause_authority == ("OWNER_PAUSED_NOT_MATERIALIZED", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("generation_state", "coordinate_steps", "expected_vacuum_state"),
    (
        (MaterializationGenerationState.PENDING, 2, "OPEN"),
        (MaterializationGenerationState.DESIRED, 3, "OPEN"),
        (MaterializationGenerationState.DRAINING_ENTRY, 4, "DRAINING_ENTRY"),
    ),
)
async def test_owner_pause_abandons_every_pre_warming_generation_and_finishes_drain(
    head_template_engine,
    generation_state: MaterializationGenerationState,
    coordinate_steps: int,
    expected_vacuum_state: str,
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
    request = _materialization_request(f"materializer:pause:{generation_state.value}")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    generation_id = None
    for _ in range(coordinate_steps):
        result = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            request=request,
            clock_ms=clock,
        )
        generation_id = result.materialization_generation_id or generation_id
    assert generation_id is not None
    async with head_template_engine.connect() as connection:
        before_pause = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
    assert before_pause == generation_state.value

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await set_strategy_entry_state(
            uow,
            strategy_group_id="SOR-001",
            target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(
                expected_version=1,
                reason=f"owner_pause_{generation_state.value.lower()}",
                idempotency_key=(
                    f"owner-request:selection-pause:{generation_state.value.lower()}"
                ),
                owner_identity="owner",
                now_ms=SESSION_START_MS + 3_600_100,
            ),
            authentication_strength="session",
        )

    paused = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(SESSION_START_MS + 3_600_101),
    )

    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with head_template_engine.connect() as connection:
        generation_after_pause = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        vacuum_after_pause = (
            await connection.execute(
                sa.select(
                    strategy_entry_vacuums_current.c.state,
                    strategy_entry_vacuums_current.c.first_blocker,
                ).where(
                    strategy_entry_vacuums_current.c.strategy_group_id == "SOR-001"
                )
            )
        ).one()
        fallback_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(
                    selection_session_authorities.c.authority_outcome
                    == "FALLBACK_PREVIOUS"
                )
            )
            or 0
        )
    assert generation_after_pause == "ABANDONED"
    assert vacuum_after_pause == (expected_vacuum_state, "OWNER_PAUSED")
    assert fallback_count == 0

    if expected_vacuum_state == "OPEN":
        async with PostgresKernelUnitOfWork(head_template_engine) as uow:
            started = await drain_strategy_entry_vacuum_once(
                uow,
                DrainStrategyEntryVacuumRequest(
                    strategy_group_id="SOR-001",
                    selection_spec_id=SELECTION_SPEC_ID,
                    now_ms=SESSION_START_MS + 3_600_102,
                ),
            )
        assert started.status is VacuumDrainStatus.DRAIN_STARTED

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        drained = await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_103,
            ),
        )
    assert drained.status is VacuumDrainStatus.OWNER_PAUSED

    async with head_template_engine.connect() as connection:
        final_vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.strategy_group_id == "SOR-001"
            )
        )
    assert final_vacuum_state == "OWNER_PAUSED"


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
async def test_generation_owned_long_install_freezes_dynamic_source_and_generation(
    head_template_engine,
) -> None:
    generation_id, changed_members, installed = (
        await _prepare_generation_owned_long(head_template_engine)
    )
    install_request = UniverseInstallRequest(
        event_spec_id=SOR_LONG_EVENT_SPEC_ID,
        runtime_profile_id="tiny-live-v1",
        owner_policy_id="policy-main",
        exchange_instrument_ids=changed_members,
        source_kind="dynamic_selection",
        materialization_generation_id=generation_id,
        expected_member_set_digest=selected_member_set_digest(changed_members),
        installed_at_ms=SESSION_START_MS + 3_600_020,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        repeated = await install_strategy_universe(uow, install_request)

    assert installed.status is UniverseInstallStatus.INSTALLED
    assert installed.universe is not None
    assert repeated.status is UniverseInstallStatus.ALREADY_WARMING
    assert repeated.universe == installed.universe
    async with head_template_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    strategy_universe_versions.c.source_kind,
                    strategy_universe_versions.c.materialization_generation_id,
                    strategy_universe_versions.c.lifecycle_state,
                ).where(
                    strategy_universe_versions.c.universe_version_id
                    == installed.universe.universe_version_id
                )
            )
        ).one()
    assert row == (
        "dynamic_selection",
        generation_id,
        "warming",
    )


@pytest.mark.asyncio
async def test_ready_dynamic_long_stages_without_signal_authority_and_releases_slot(
    head_template_engine,
) -> None:
    generation_id, _, installed = await _prepare_generation_owned_long(
        head_template_engine
    )
    assert installed.universe is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=installed.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        staged = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=installed.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_030,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )

    assert staged.status is UniverseActivationStatus.STAGED
    async with head_template_engine.connect() as connection:
        version_state = await connection.scalar(
            sa.select(strategy_universe_versions.c.lifecycle_state).where(
                strategy_universe_versions.c.universe_version_id
                == installed.universe.universe_version_id
            )
        )
        scopes = (
            await connection.execute(
                sa.select(
                    strategy_universe_versions.c.universe_version_id,
                    strategy_universe_versions.c.lifecycle_state,
                ).where(strategy_universe_versions.c.lifecycle_state == "warming")
            )
        ).all()
        runtime_scope_states = (
            await connection.execute(
                sa.text(
                    "SELECT lifecycle_state, observation_enabled, entry_enabled "
                    "FROM brc_runtime_scopes_current "
                    "WHERE universe_version_id = :universe_version_id"
                ),
                {"universe_version_id": installed.universe.universe_version_id},
            )
        ).all()
    assert version_state == "staged"
    assert scopes == []
    assert runtime_scope_states == [("staged", False, False)] * 2


@pytest.mark.asyncio
async def test_dynamic_pair_warms_serially_and_generation_stages_only_after_short(
    head_template_engine,
) -> None:
    generation_id, changed_members, long_install = (
        await _prepare_generation_owned_long(head_template_engine)
    )
    assert long_install.universe is not None
    short_request = UniverseInstallRequest(
        event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
        runtime_profile_id="tiny-live-v1",
        owner_policy_id="policy-main",
        exchange_instrument_ids=changed_members,
        source_kind="dynamic_selection",
        materialization_generation_id=generation_id,
        expected_member_set_digest=selected_member_set_digest(changed_members),
        installed_at_ms=SESSION_START_MS + 3_600_021,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        blocked_short = await install_strategy_universe(uow, short_request)
    assert (
        blocked_short.status
        is UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS
    )

    await make_warming_ready(
        head_template_engine,
        universe_version_id=long_install.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_022,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=long_install.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_030,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        short_install = await install_strategy_universe(uow, short_request)
    assert short_install.status is UniverseInstallStatus.INSTALLED
    assert short_install.universe is not None

    await make_warming_ready(
        head_template_engine,
        universe_version_id=short_install.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_031,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        short_stage = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=short_install.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_040,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )

    assert short_stage.status is UniverseActivationStatus.STAGED
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.materialization_generation_id
                    == generation_id
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
    assert generation_state == "STAGED"
    assert target_states == ("staged", "staged")


@pytest.mark.asyncio
async def test_formal_abandonment_accepts_staged_dynamic_target(
    head_template_engine,
) -> None:
    generation_id, _, long_install = await _prepare_generation_owned_long(
        head_template_engine
    )
    assert long_install.universe is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=long_install.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=long_install.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_030,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await abandon_strategy_universe(
            uow,
            AbandonStrategyUniverseRequest(
                universe_version_id=long_install.universe.universe_version_id,
                reason_code="dynamic_short_warming_failed",
                attempted_at_ms=SESSION_START_MS + 3_600_040,
            ),
        )

    async with head_template_engine.connect() as connection:
        version = (
            await connection.execute(
                sa.select(
                    strategy_universe_versions.c.lifecycle_state,
                    strategy_universe_versions.c.abandon_reason_code,
                ).where(
                    strategy_universe_versions.c.universe_version_id
                    == long_install.universe.universe_version_id
                )
            )
        ).one()
    assert version == ("abandoned", "dynamic_short_warming_failed")


@pytest.mark.asyncio
async def test_staged_pair_activation_atomically_switches_both_sides_and_authority(
    head_template_engine,
) -> None:
    generation_id, long_target_id, short_target_id = await _prepare_staged_pair(
        head_template_engine
    )
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:dynamic-pair:active-new",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        proposed_authority_outcome=AuthorityOutcome.ACTIVE_NEW,
        unauthorized_from_close_time_ms=SESSION_START_MS + 4_500_000,
        detector_semantic_digest="sha256:" + "4" * 64,
        created_at_ms=SESSION_START_MS + 4_500_001,
        source_entry_vacuum_id=(
            f"vacuum:SOR-001:{SESSION_START_MS}:generation"
        ),
        source_generation_id=generation_id,
    )
    selected_scopes = tuple(
        AuthorityGapScope(
            event_spec_id=event_spec_id,
            exchange_instrument_id=instrument_id,
        )
        for event_spec_id in (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
        for instrument_id in tuple(
            sorted(
                set(SELECTED_MEMBERS)
                | {
                    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0],
                    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[2],
                }
            )
        )
    )
    results = tuple(
        AuthorityGapScopeResult(
            scope=scope,
            session_reference=str(SESSION_START_MS),
            first_natural_trigger_at_ms=None,
        )
        for scope in selected_scopes
    )
    complete = complete_authority_gap_audit(
        audit,
        audited_through_close_time_ms=SESSION_START_MS + 4_500_000,
        scopes=selected_scopes,
        results=results,
    )
    async with head_template_engine.begin() as connection:
        repository = PostgresInstrumentSelectionRepository(connection)
        await repository.add_pending_authority_gap_audit(audit)
        await repository.complete_authority_gap_audit(
            complete,
            results=results,
            completed_at_ms=SESSION_START_MS + 4_500_001,
        )
        current_authority = await repository.get_current_authority_projection(
            SELECTION_SPEC_ID
        )
    assert current_authority is not None
    authority = SelectionSessionAuthority(
        selection_authority_id=(
            f"selection-authority:{SELECTION_SPEC_ID}:{SESSION_START_MS}:2"
        ),
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 3_600_000,
        authority_sequence=2,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=f"selection:{SELECTION_SPEC_ID}:{SESSION_START_MS}",
        continued_from_selection_authority_id=(
            current_authority.authority.selection_authority_id
        ),
        continuity_source_kind=ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
        authority_gap_audit_id=complete.authority_gap_audit_id,
        materialization_generation_id=generation_id,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.ACTIVE_NEW,
        authorized_pair=UniverseAuthorityPair(
            long_universe_version_id=long_target_id,
            short_universe_version_id=short_target_id,
        ),
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id=complete.authority_gap_audit_id,
        ),
        effective_from_ms=SESSION_START_MS + 4_500_001,
        first_eligible_close_time_ms=SESSION_START_MS + 5_400_000,
        expires_at_ms=SESSION_START_MS + 90_000_000,
        reason_code="DYNAMIC_PAIR_ACTIVATED",
        created_at_ms=SESSION_START_MS + 4_500_001,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        activated = await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=long_target_id,
                paired_universe_version_id=short_target_id,
                attempted_at_ms=SESSION_START_MS + 4_500_001,
                operation=UniverseActivationOperation.ACTIVATE_DYNAMIC_PAIR,
                materialization_generation_id=generation_id,
                selection_authority=authority,
            ),
        )

    assert activated.status is UniverseActivationStatus.ACTIVATED
    async with head_template_engine.connect() as connection:
        pointers = tuple(
            (
                await connection.execute(
                    sa.select(
                        strategy_universe_current.c.event_spec_id,
                        strategy_universe_current.c.universe_version_id,
                    )
                    .where(
                        strategy_universe_current.c.event_spec_id.in_(
                            (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                        )
                    )
                    .order_by(strategy_universe_current.c.event_spec_id)
                )
            ).all()
        )
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == generation_id
            )
        )
        authority_outcome = await connection.scalar(
            sa.select(selection_session_authorities.c.authority_outcome).where(
                selection_session_authorities.c.selection_authority_id
                == authority.selection_authority_id
            )
        )
    assert pointers == (
        (SOR_LONG_EVENT_SPEC_ID, long_target_id),
        (SOR_SHORT_EVENT_SPEC_ID, short_target_id),
    )
    assert generation_state == "ACTIVE"
    assert vacuum_state == "RESOLVED_ACTIVE"
    assert authority_outcome == "ACTIVE_NEW"


@pytest.mark.parametrize(
    "failure_stage",
    (
        "retire_previous_scopes",
        "activate_target_scopes",
        "long_pointer",
        "short_pointer",
        "authority_insert",
        "authority_pointer",
        "generation_terminal",
        "vacuum_resolution",
    ),
)
@pytest.mark.asyncio
async def test_atomic_pair_activation_failure_rolls_back_all_visible_state(
    head_template_engine,
    failure_stage: str,
) -> None:
    generation_id, long_target_id, short_target_id = await _prepare_staged_pair(
        head_template_engine
    )
    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request(f"materializer:fault:{failure_stage}"),
        clock_ms=_Clock(SESSION_START_MS + 3_600_050),
    )
    assert audit_pending.authority_gap_audit_id is not None
    function_name = f"fail_ds06_{failure_stage}"
    trigger_name = f"trg_ds06_{failure_stage}"
    if failure_stage == "retire_previous_scopes":
        table_name = "brc_runtime_scopes_current"
        operation = "UPDATE"
        condition = (
            f"OLD.universe_version_id IN ('{LONG_UNIVERSE_ID}', "
            f"'{SHORT_UNIVERSE_ID}') AND NEW.lifecycle_state = 'retired'"
        )
    elif failure_stage == "activate_target_scopes":
        table_name = "brc_runtime_scopes_current"
        operation = "UPDATE"
        condition = (
            f"OLD.universe_version_id IN ('{long_target_id}', "
            f"'{short_target_id}') AND NEW.lifecycle_state = 'active'"
        )
    elif failure_stage in {"long_pointer", "short_pointer"}:
        table_name = "brc_strategy_universe_current"
        operation = "UPDATE"
        event_spec_id = (
            SOR_LONG_EVENT_SPEC_ID
            if failure_stage == "long_pointer"
            else SOR_SHORT_EVENT_SPEC_ID
        )
        condition = f"NEW.event_spec_id = '{event_spec_id}'"
    elif failure_stage == "authority_insert":
        table_name = "brc_selection_session_authorities"
        operation = "INSERT"
        condition = "NEW.authority_outcome = 'ACTIVE_NEW'"
    elif failure_stage == "authority_pointer":
        table_name = "brc_selection_authority_current"
        operation = "UPDATE"
        condition = f"NEW.selection_spec_id = '{SELECTION_SPEC_ID}'"
    elif failure_stage == "generation_terminal":
        table_name = "brc_strategy_universe_materialization_generations"
        operation = "UPDATE"
        condition = "NEW.lifecycle_state = 'ACTIVE'"
    else:
        table_name = "brc_strategy_entry_vacuums_current"
        operation = "UPDATE"
        condition = "NEW.state = 'RESOLVED_ACTIVE'"
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                f"""
                CREATE FUNCTION {function_name}()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF {condition} THEN
                        RAISE EXCEPTION 'ds06 injected {failure_stage} failure';
                    END IF;
                    RETURN NEW;
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE {operation} ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION {function_name}()
                """
            )
        )

    with pytest.raises(DBAPIError, match=f"ds06 injected {failure_stage} failure"):
        await complete_pending_authority_gap_audit(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            audit_source=_CheckedNegativeAuditSource(),
            authority_gap_audit_id=audit_pending.authority_gap_audit_id,
            clock_ms=_Clock(SESSION_START_MS + 4_500_000),
        )

    async with head_template_engine.connect() as connection:
        pointers = tuple(
            (
                await connection.execute(
                    sa.select(
                        strategy_universe_current.c.event_spec_id,
                        strategy_universe_current.c.universe_version_id,
                    )
                    .where(
                        strategy_universe_current.c.event_spec_id.in_(
                            (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                        )
                    )
                    .order_by(strategy_universe_current.c.event_spec_id)
                )
            ).all()
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (long_target_id, short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == generation_id
            )
        )
        audit_state = await connection.scalar(
            sa.select(selection_authority_gap_audits_current.c.state).where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == audit_pending.authority_gap_audit_id
            )
        )
        active_new_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(selection_session_authorities.c.authority_outcome == "ACTIVE_NEW")
        )
    assert pointers == (
        (SOR_LONG_EVENT_SPEC_ID, LONG_UNIVERSE_ID),
        (SOR_SHORT_EVENT_SPEC_ID, SHORT_UNIVERSE_ID),
    )
    assert target_states == ("staged", "staged")
    assert generation_state == "STAGED"
    assert vacuum_state == "RECONFIGURING"
    assert audit_state == "PENDING"
    assert active_new_count == 0


@pytest.mark.asyncio
async def test_coordinator_runs_serial_warming_audit_and_atomic_pair_activation(
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
    request = _materialization_request("materializer:serial-pair")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    for _ in range(4):
        await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            request=request,
            clock_ms=clock,
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_010,
            ),
        )

    long_wait = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert long_wait.disposition is MaterializationDisposition.LONG_WARMING
    async with head_template_engine.connect() as connection:
        long_target_id = await connection.scalar(
            sa.select(strategy_universe_versions.c.universe_version_id).where(
                strategy_universe_versions.c.materialization_generation_id
                == long_wait.materialization_generation_id,
                strategy_universe_versions.c.event_spec_id
                == SOR_LONG_EVENT_SPEC_ID,
            )
        )
    assert long_target_id is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=str(long_target_id),
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_005,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    short_wait = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert short_wait.disposition is MaterializationDisposition.SHORT_WARMING
    async with head_template_engine.connect() as connection:
        short_target_id = await connection.scalar(
            sa.select(strategy_universe_versions.c.universe_version_id).where(
                strategy_universe_versions.c.materialization_generation_id
                == short_wait.materialization_generation_id,
                strategy_universe_versions.c.event_spec_id
                == SOR_SHORT_EVENT_SPEC_ID,
            )
        )
    assert short_target_id is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=str(short_target_id),
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_006,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert audit_pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert audit_pending.authority_gap_audit_id is not None

    activated = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert activated.disposition is MaterializationDisposition.ACTIVE_NEW
    repeated = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(SESSION_START_MS + 4_500_010),
    )
    assert repeated.disposition is MaterializationDisposition.ACTIVE_NEW
    assert repeated.selection_authority_id == activated.selection_authority_id
    async with head_template_engine.connect() as connection:
        current_ids = tuple(
            await connection.scalars(
                sa.select(strategy_universe_current.c.universe_version_id)
                .where(
                    strategy_universe_current.c.event_spec_id.in_(
                        (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                    )
                )
                .order_by(strategy_universe_current.c.event_spec_id)
            )
        )
    assert current_ids == (str(long_target_id), str(short_target_id))


@pytest.mark.parametrize(
    ("selection_mode", "pending_selection_mode", "expected_authority_mode"),
    (
        ("dynamic_selection", None, "dynamic_selection"),
        ("static_baseline", "dynamic_selection", "static_baseline"),
    ),
)
@pytest.mark.asyncio
async def test_materialization_timeout_falls_back_to_exact_previous_pair(
    head_template_engine,
    selection_mode: str,
    pending_selection_mode: str | None,
    expected_authority_mode: str,
) -> None:
    generation_id, long_target_id, short_target_id = await _prepare_staged_pair(
        head_template_engine,
        selection_mode=selection_mode,
        pending_selection_mode=pending_selection_mode,
    )
    request = _materialization_request("materializer:timeout-fallback")
    timeout_clock = _Clock(SESSION_START_MS + 5_400_020)

    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=timeout_clock,
    )

    assert audit_pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert audit_pending.authority_gap_audit_id is not None
    assert audit_pending.reason_code is not None
    assert "ENTRY_VACUUM" in audit_pending.reason_code
    async with head_template_engine.connect() as connection:
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (long_target_id, short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
    assert target_states == ("abandoned", "abandoned")

    fallback = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_030),
    )
    repeated = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_040),
    )

    assert fallback.disposition is MaterializationDisposition.FALLBACK_PREVIOUS
    assert repeated.disposition is MaterializationDisposition.FALLBACK_PREVIOUS
    assert repeated.selection_authority_id == fallback.selection_authority_id
    coordinator_retry = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(SESSION_START_MS + 5_400_050),
    )
    assert (
        coordinator_retry.disposition
        is MaterializationDisposition.FALLBACK_PREVIOUS
    )
    assert coordinator_retry.selection_authority_id == fallback.selection_authority_id
    async with head_template_engine.connect() as connection:
        pointers = tuple(
            (
                await connection.execute(
                    sa.select(
                        strategy_universe_current.c.event_spec_id,
                        strategy_universe_current.c.universe_version_id,
                    )
                    .where(
                        strategy_universe_current.c.event_spec_id.in_(
                            (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                        )
                    )
                    .order_by(strategy_universe_current.c.event_spec_id)
                )
            ).all()
        )
        generation_row = (
            await connection.execute(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state,
                    strategy_universe_materialization_generations.c.fallback_reason_code,
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            )
        ).one()
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == generation_id
            )
        )
        authority_row = (
            await connection.execute(
                sa.select(
                    selection_session_authorities.c.authority_outcome,
                    selection_session_authorities.c.selection_mode,
                    selection_session_authorities.c.authorized_long_universe_version_id,
                    selection_session_authorities.c.authorized_short_universe_version_id,
                ).where(
                    selection_session_authorities.c.selection_authority_id
                    == fallback.selection_authority_id
                )
            )
        ).one()
        control_row = (
            await connection.execute(
                sa.select(strategy_selection_control_current).where(
                    strategy_selection_control_current.c.strategy_group_id
                    == "SOR-001"
                )
            )
        ).mappings().one()
    assert pointers == (
        (SOR_LONG_EVENT_SPEC_ID, LONG_UNIVERSE_ID),
        (SOR_SHORT_EVENT_SPEC_ID, SHORT_UNIVERSE_ID),
    )
    assert generation_row == ("FALLBACK_PREVIOUS", "materialization_timeout")
    assert vacuum_state == "RESOLVED_FALLBACK"
    assert authority_row == (
        "FALLBACK_PREVIOUS",
        expected_authority_mode,
        LONG_UNIVERSE_ID,
        SHORT_UNIVERSE_ID,
    )
    assert control_row["selection_mode"] == expected_authority_mode
    assert control_row["pending_selection_mode"] is None
    assert control_row["pending_effective_session_start_ms"] is None
    assert control_row["pending_authorization_id"] is None


@pytest.mark.asyncio
async def test_pre_first_close_fallback_audit_stays_pending_without_source_call(
    head_template_engine,
) -> None:
    generation_id, changed_members, installed = await _prepare_generation_owned_long(
        head_template_engine,
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
    )
    assert installed.universe is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=installed.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_certification_current)
            .where(
                instrument_certification_current.c.exchange_instrument_id
                == changed_members[0]
            )
            .values(
                status="owner_action_required",
                blocker_code="instrument_not_tradeable",
            )
        )

    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:pre-first-close"),
        clock_ms=_Clock(SESSION_START_MS + 3_780_000),
    )
    assert pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert generation_id is not None
    assert pending.authority_gap_audit_id is not None
    source = _UnexpectedAuditSource()

    still_pending = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=source,
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 3_780_010),
    )

    assert still_pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert still_pending.reason_code == "AUTHORITY_GAP_BEFORE_FIRST_ELIGIBLE_CLOSE"
    assert source.called is False
    async with head_template_engine.connect() as connection:
        audit_state = await connection.scalar(
            sa.select(selection_authority_gap_audits_current.c.state).where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == pending.authority_gap_audit_id
            )
        )
        authority_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(selection_session_authorities.c.session_start_ms == SESSION_START_MS)
        )
    assert audit_state == "PENDING"
    assert authority_count == 0


@pytest.mark.asyncio
async def test_temporary_certification_outage_waits_and_resumes_materialization(
    head_template_engine,
) -> None:
    generation_id, changed_members, installed = await _prepare_generation_owned_long(
        head_template_engine,
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
    )
    assert installed.universe is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=installed.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_certification_current)
            .where(
                instrument_certification_current.c.exchange_instrument_id
                == changed_members[0]
            )
            .values(
                status="temporarily_unavailable",
                blocker_code="readonly_facts_unavailable",
            )
        )

    waiting = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:temporary-outage"),
        clock_ms=_Clock(SESSION_START_MS + 3_780_000),
    )

    assert waiting.disposition is MaterializationDisposition.LONG_WARMING
    assert waiting.reason_code == "CERTIFICATION_TEMPORARILY_UNAVAILABLE"
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        audit_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_authority_gap_audits_current)
            .where(
                selection_authority_gap_audits_current.c.source_generation_id
                == generation_id
            )
        )
    assert generation_state == "MATERIALIZING"
    assert audit_count == 0

    await make_warming_ready(
        head_template_engine,
        universe_version_id=installed.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_840_000,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    resumed = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:temporary-outage-recovered"),
        clock_ms=_Clock(SESSION_START_MS + 3_840_010),
    )

    assert resumed.disposition is MaterializationDisposition.SHORT_WARMING
    async with head_template_engine.connect() as connection:
        long_state = await connection.scalar(
            sa.select(strategy_universe_versions.c.lifecycle_state).where(
                strategy_universe_versions.c.universe_version_id
                == installed.universe.universe_version_id
            )
        )
    assert long_state == "staged"


@pytest.mark.asyncio
async def test_expired_gap_audit_window_never_calls_source_or_grants_authority(
    head_template_engine,
) -> None:
    _generation_id, changed_members, installed = await _prepare_generation_owned_long(
        head_template_engine,
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
    )
    assert installed.universe is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=installed.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 90_000_000,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_certification_current)
            .where(
                instrument_certification_current.c.exchange_instrument_id
                == changed_members[0]
            )
            .values(
                status="owner_action_required",
                blocker_code="instrument_not_tradeable",
            )
        )
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:expired-window"),
        clock_ms=_Clock(SESSION_START_MS + 3_780_000),
    )
    assert pending.authority_gap_audit_id is not None
    source = _UnexpectedAuditSource()

    expired = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=source,
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 96 * 900_000),
    )

    assert expired.disposition is MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED
    assert expired.reason_code == "AUTHORITY_GAP_SESSION_EXPIRED"
    assert source.called is False
    async with head_template_engine.connect() as connection:
        audit_state = await connection.scalar(
            sa.select(selection_authority_gap_audits_current.c.state).where(
                selection_authority_gap_audits_current.c.authority_gap_audit_id
                == pending.authority_gap_audit_id
            )
        )
        authority_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(selection_session_authorities.c.session_start_ms == SESSION_START_MS)
        )
    assert audit_state == "PENDING"
    assert authority_count == 0


@pytest.mark.asyncio
async def test_owner_paused_expired_first_activation_recovery_preserves_static_pair(
    head_template_engine,
) -> None:
    generation_id, _long_target_id, _short_target_id = await _prepare_staged_pair(
        head_template_engine,
        selection_mode="static_baseline",
        pending_selection_mode="dynamic_selection",
    )
    request = _materialization_request("materializer:expired-recovery")
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(SESSION_START_MS + 5_400_020),
    )
    assert pending.authority_gap_audit_id is not None
    failed = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_FailingAuditSource(
            AuthorityGapAuditSourceIntegrityError("expected_bars=4")
        ),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_030),
    )
    assert failed.disposition is MaterializationDisposition.BLOCKED
    assert failed.reason_code == "AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED"

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        paused = await set_strategy_entry_state(
            uow,
            strategy_group_id="SOR-001",
            target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(
                expected_version=1,
                reason="recover_expired_first_activation",
                idempotency_key="owner-request:expired-first-activation:pause",
                owner_identity="owner",
                now_ms=SESSION_START_MS + 5_400_040,
            ),
            authentication_strength="session",
        )
    assert paused.control_version == 2

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        generation = await uow.instrument_selection.get_materialization_generation(
            generation_id,
            for_update=True,
        )
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id="SOR-001",
            selection_spec_id=SELECTION_SPEC_ID,
            for_update=True,
        )
        assert generation is not None
        assert vacuum is not None
        await uow.instrument_selection.abandon_generation_for_owner_pause(
            generation=generation,
            vacuum=vacuum,
            paused_at_ms=SESSION_START_MS + 5_400_050,
        )

    async with head_template_engine.connect() as connection:
        before_ticket_count = int(
            await connection.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))
            or 0
        )
        before_command_count = int(
            await connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))
            or 0
        )
        generation_version_before_recovery = int(
            await connection.scalar(
                sa.select(
                    strategy_universe_materialization_generations.c.projection_version
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            )
            or 0
        )

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        recovered = await recover_expired_dynamic_activation(
            uow,
            RecoverExpiredDynamicActivationRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
                materialization_generation_id=generation_id,
                entry_vacuum_id="vacuum:SOR-001:1704067200000:generation",
                authority_gap_audit_id=pending.authority_gap_audit_id,
                expected_long_universe_version_id=LONG_UNIVERSE_ID,
                expected_short_universe_version_id=SHORT_UNIVERSE_ID,
                expected_selection_control_version=1,
                expected_owner_control_version=2,
                recovered_at_ms=SESSION_START_MS + 86_400_000,
            ),
        )

    assert recovered.status is ExpiredDynamicActivationRecoveryStatus.RECOVERED
    assert recovered.selection_control_version == 2
    async with head_template_engine.connect() as connection:
        control = (
            await connection.execute(
                sa.select(strategy_selection_control_current).where(
                    strategy_selection_control_current.c.strategy_group_id == "SOR-001"
                )
            )
        ).mappings().one()
        generation = (
            await connection.execute(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state,
                    strategy_universe_materialization_generations.c.fallback_reason_code,
                    strategy_universe_materialization_generations.c.projection_version,
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            )
        ).one()
        event_type = await connection.scalar(
            sa.select(strategy_universe_materialization_events.c.event_type)
            .where(
                strategy_universe_materialization_events.c.materialization_generation_id
                == generation_id
            )
            .order_by(
                strategy_universe_materialization_events.c.event_sequence.desc()
            )
            .limit(1)
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id == generation_id
            )
        )
        current_pair = tuple(
            await connection.scalars(
                sa.select(strategy_universe_current.c.universe_version_id)
                .where(
                    strategy_universe_current.c.event_spec_id.in_(
                        (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                    )
                )
                .order_by(strategy_universe_current.c.event_spec_id)
            )
        )
        authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(selection_session_authorities.c.session_start_ms == SESSION_START_MS)
            )
            or 0
        )
        after_ticket_count = int(
            await connection.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))
            or 0
        )
        after_command_count = int(
            await connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))
            or 0
        )
    assert control["selection_mode"] == "static_baseline"
    assert control["pending_selection_mode"] is None
    assert control["pending_effective_session_start_ms"] is None
    assert control["pending_authorization_id"] is None
    assert control["control_version"] == 2
    assert generation == (
        "ABANDONED",
        None,
        generation_version_before_recovery + 1,
    )
    assert event_type == "EXPIRED_ACTIVATION_RECOVERED"
    assert vacuum_state == "OWNER_PAUSED"
    assert current_pair == (LONG_UNIVERSE_ID, SHORT_UNIVERSE_ID)
    assert authority_count == 0
    assert after_ticket_count == before_ticket_count
    assert after_command_count == before_command_count

    resumed_at_ms = SESSION_START_MS + 86_400_000 + 4 * 3_600_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        resumed = await set_strategy_entry_state(
            uow,
            strategy_group_id="SOR-001",
            target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(
                expected_version=2,
                reason="retry_dynamic_after_recovery",
                idempotency_key="owner-request:expired-first-activation:resume",
                owner_identity="owner",
                now_ms=resumed_at_ms,
            ),
            authentication_strength="totp_step_up",
        )
    assert resumed.control_version == 3

    next_session_start_ms = SESSION_START_MS + 2 * 86_400_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        staged = await stage_dynamic_selection_mode(
            uow,
            strategy_group_id="SOR-001",
            effective_session_start_ms=next_session_start_ms,
            request=ControlMutationRequest(
                expected_version=2,
                reason="retry_dynamic_after_recovery",
                idempotency_key="owner-request:expired-first-activation:retry",
                owner_identity="owner",
                now_ms=resumed_at_ms,
            ),
            authentication_strength="totp_step_up",
        )
    assert staged.pending_effective_session_start_ms == next_session_start_ms
    next_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[1],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[3],
            )
        )
    )
    async with head_template_engine.begin() as connection:
        await _seed_snapshot(
            connection,
            session_start_ms=next_session_start_ms,
            selected_members=next_members,
        )

    superseded = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            session_start_ms=next_session_start_ms,
            worker_id="materializer:recovered-owner-pause-supersession",
        ),
        clock_ms=_Clock(next_session_start_ms + 3_600_000),
    )

    assert superseded.disposition is MaterializationDisposition.GENERATION_DESIRED
    assert superseded.materialization_generation_id == (
        f"generation:{SELECTION_SPEC_ID}:{next_session_start_ms}"
    )
    async with head_template_engine.connect() as connection:
        old_generation = (
            await connection.execute(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state,
                    strategy_universe_materialization_generations.c.projection_version,
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            )
        ).one()
        new_generation = (
            await connection.execute(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state,
                    strategy_universe_materialization_generations.c.session_start_ms,
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == superseded.materialization_generation_id
                )
            )
        ).one()
        retargeted_vacuum = (
            await connection.execute(
                sa.select(
                    strategy_entry_vacuums_current.c.state,
                    strategy_entry_vacuums_current.c.source_generation_id,
                    strategy_entry_vacuums_current.c.first_blocker,
                    strategy_entry_vacuums_current.c.fenced_at_ms,
                ).where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id
                    == "vacuum:SOR-001:1704067200000:generation"
                )
            )
        ).one()
        retroactive_authority_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(selection_session_authorities)
                .where(selection_session_authorities.c.session_start_ms == SESSION_START_MS)
            )
            or 0
        )
    assert old_generation[0] == "ABANDONED"
    assert old_generation[1] == generation_version_before_recovery + 2
    assert new_generation == ("MATERIALIZING", next_session_start_ms)
    assert retargeted_vacuum == (
        "RECONFIGURING",
        superseded.materialization_generation_id,
        "LATEST_VALID_SELECTION",
        next_session_start_ms + 3_600_001,
    )
    assert retroactive_authority_count == 0

    # The first retry owns the same newest Generation.  It must progress that
    # Generation into warming rather than trying to supersede it with an equal
    # Session/Snapshot pair, which violates the repository's strictly-newer
    # supersession invariant.
    warming = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            session_start_ms=next_session_start_ms,
            worker_id="materializer:recovered-owner-pause-retry",
        ),
        clock_ms=_Clock(next_session_start_ms + 3_600_010),
    )
    assert warming.disposition is MaterializationDisposition.LONG_WARMING
    assert warming.materialization_generation_id == superseded.materialization_generation_id


@pytest.mark.asyncio
async def test_long_staged_short_terminal_failure_abandons_pair_before_fallback(
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
    request = _materialization_request("materializer:short-terminal-failure")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    for _ in range(4):
        await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            request=request,
            clock_ms=clock,
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_010,
            ),
        )
    long_wait = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    assert long_wait.materialization_generation_id is not None
    async with head_template_engine.connect() as connection:
        long_target_id = await connection.scalar(
            sa.select(strategy_universe_versions.c.universe_version_id).where(
                strategy_universe_versions.c.materialization_generation_id
                == long_wait.materialization_generation_id,
                strategy_universe_versions.c.event_spec_id
                == SOR_LONG_EVENT_SPEC_ID,
            )
        )
    assert long_target_id is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=str(long_target_id),
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_005,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    short_wait = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )
    async with head_template_engine.connect() as connection:
        short_target_id = await connection.scalar(
            sa.select(strategy_universe_versions.c.universe_version_id).where(
                strategy_universe_versions.c.materialization_generation_id
                == short_wait.materialization_generation_id,
                strategy_universe_versions.c.event_spec_id
                == SOR_SHORT_EVENT_SPEC_ID,
            )
        )
    assert short_target_id is not None
    await make_warming_ready(
        head_template_engine,
        universe_version_id=str(short_target_id),
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_006,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_instrument_certification_current "
                "SET status = 'owner_action_required', "
                "blocker_code = 'instrument_not_tradeable' "
                "WHERE exchange_instrument_id = :instrument_id"
            ),
            {"instrument_id": changed_members[0]},
        )

    fallback_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=clock,
    )

    assert fallback_pending.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert fallback_pending.authority_gap_audit_id is not None
    async with head_template_engine.connect() as connection:
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (long_target_id, short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        pointers = tuple(
            await connection.scalars(
                sa.select(strategy_universe_current.c.universe_version_id)
                .where(
                    strategy_universe_current.c.event_spec_id.in_(
                        (SOR_LONG_EVENT_SPEC_ID, SOR_SHORT_EVENT_SPEC_ID)
                    )
                )
                .order_by(strategy_universe_current.c.event_spec_id)
            )
        )
    assert target_states == ("abandoned", "abandoned")
    assert pointers == (LONG_UNIVERSE_ID, SHORT_UNIVERSE_ID)


@pytest.mark.asyncio
async def test_owner_pause_during_fallback_audit_never_restores_entry_authority(
    head_template_engine,
) -> None:
    generation_id, _, _ = await _prepare_staged_pair(head_template_engine)
    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:paused-fallback"),
        clock_ms=_Clock(SESSION_START_MS + 5_400_020),
    )
    assert audit_pending.authority_gap_audit_id is not None
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                entry_state="paused",
                control_version=2,
                reason="owner_paused_during_fallback",
                updated_at_ms=SESSION_START_MS + 5_400_025,
            )
        )

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_030),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == "AUTHORITY_GAP_AUDIT_RUNTIME_DRIFT"
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == generation_id
            )
        )
        fallback_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(
                selection_session_authorities.c.authority_outcome
                == "FALLBACK_PREVIOUS"
            )
        )
    assert generation_state == "STAGED"
    assert vacuum_state == "RECONFIGURING"
    assert fallback_count == 0

    abandoned = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:paused-fallback-abandon"),
        clock_ms=_Clock(SESSION_START_MS + 5_400_040),
    )
    assert abandoned.disposition is MaterializationDisposition.OWNER_PAUSED
    async with head_template_engine.connect() as connection:
        audit_row = (
            await connection.execute(
                sa.select(
                    selection_authority_gap_audits_current.c.state,
                    selection_authority_gap_audits_current.c.first_blocker,
                ).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == audit_pending.authority_gap_audit_id
                )
            )
        ).one()
    assert audit_row == ("FAILED", "OWNER_PAUSED")


@pytest.mark.asyncio
async def test_owner_pause_abandons_staged_generation_and_keeps_vacuum_closed(
    head_template_engine,
) -> None:
    generation_id, long_target_id, short_target_id = await _prepare_staged_pair(
        head_template_engine
    )
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_entry_controls_current)
            .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
            .values(
                entry_state="paused",
                control_version=2,
                reason="owner_paused_materialization",
                updated_at_ms=SESSION_START_MS + 5_000_000,
            )
        )

    paused = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:owner-pause"),
        clock_ms=_Clock(SESSION_START_MS + 5_000_000),
    )

    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == generation_id
            )
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (long_target_id, short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == generation_id
            )
        )
        fallback_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(
                selection_session_authorities.c.authority_outcome
                == "FALLBACK_PREVIOUS"
            )
        )
    assert generation_state == "ABANDONED"
    assert target_states == ("abandoned", "abandoned")
    assert vacuum_state == "OWNER_PAUSED"
    assert fallback_count == 0


@pytest.mark.asyncio
async def test_newer_valid_snapshot_supersedes_unactivated_generation_without_fallback(
    head_template_engine,
) -> None:
    old_generation_id, old_long_target_id, old_short_target_id = (
        await _prepare_staged_pair(head_template_engine)
    )
    next_session_start_ms = SESSION_START_MS + 86_400_000
    next_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[1],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[3],
            )
        )
    )
    async with head_template_engine.begin() as connection:
        await _seed_snapshot(
            connection,
            session_start_ms=next_session_start_ms,
            selected_members=next_members,
        )

    superseded = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            session_start_ms=next_session_start_ms,
            worker_id="materializer:newest-valid-wins",
        ),
        clock_ms=_Clock(next_session_start_ms + 3_600_000),
    )

    assert superseded.disposition is MaterializationDisposition.GENERATION_DESIRED
    assert superseded.materialization_generation_id is not None
    assert superseded.materialization_generation_id != old_generation_id
    assert superseded.entry_vacuum_id is not None
    async with head_template_engine.connect() as connection:
        generation_rows = tuple(
            (
                await connection.execute(
                    sa.select(
                        strategy_universe_materialization_generations.c.materialization_generation_id,
                        strategy_universe_materialization_generations.c.lifecycle_state,
                    ).order_by(
                        strategy_universe_materialization_generations.c.session_start_ms
                    )
                )
            ).all()
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (old_long_target_id, old_short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        vacuum_row = (
            await connection.execute(
                sa.select(
                    strategy_entry_vacuums_current.c.state,
                    strategy_entry_vacuums_current.c.source_generation_id,
                    strategy_entry_vacuums_current.c.resolved_at_ms,
                ).where(
                    strategy_entry_vacuums_current.c.entry_vacuum_id
                    == superseded.entry_vacuum_id
                )
            )
        ).one()
        fallback_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(
                selection_session_authorities.c.authority_outcome
                == "FALLBACK_PREVIOUS"
            )
        )
    assert generation_rows == (
        (old_generation_id, "SUPERSEDED"),
        (superseded.materialization_generation_id, "MATERIALIZING"),
    )
    assert target_states == ("abandoned", "abandoned")
    assert vacuum_row == (
        "RECONFIGURING",
        superseded.materialization_generation_id,
        None,
    )
    assert fallback_count == 0


@pytest.mark.asyncio
async def test_newer_snapshot_supersession_fails_old_pending_gap_audit(
    head_template_engine,
) -> None:
    old_generation_id, _, _ = await _prepare_staged_pair(head_template_engine)
    old_audit = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:old-audit"),
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert old_audit.disposition is MaterializationDisposition.GAP_AUDIT_PENDING
    assert old_audit.authority_gap_audit_id is not None
    next_session_start_ms = SESSION_START_MS + 86_400_000
    next_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[1],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[3],
            )
        )
    )
    async with head_template_engine.begin() as connection:
        await _seed_snapshot(
            connection,
            session_start_ms=next_session_start_ms,
            selected_members=next_members,
        )

    superseded = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            session_start_ms=next_session_start_ms,
            worker_id="materializer:fail-old-audit",
        ),
        clock_ms=_Clock(next_session_start_ms + 3_600_000),
    )

    assert superseded.disposition is MaterializationDisposition.GENERATION_DESIRED
    async with head_template_engine.connect() as connection:
        audit_row = (
            await connection.execute(
                sa.select(
                    selection_authority_gap_audits_current.c.state,
                    selection_authority_gap_audits_current.c.first_blocker,
                ).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == old_audit.authority_gap_audit_id
                )
            )
        ).one()
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == old_generation_id
            )
        )
    assert audit_row == ("FAILED", "SUPERSEDED_BY_NEWER_SELECTION")
    assert generation_state == "SUPERSEDED"


@pytest.mark.parametrize(
    ("selection_mode", "pending_selection_mode"),
    (
        ("dynamic_selection", None),
        ("static_baseline", "dynamic_selection"),
    ),
)
@pytest.mark.asyncio
async def test_newer_valid_empty_supersedes_generation_and_resolves_existing_vacuum(
    head_template_engine,
    selection_mode: str,
    pending_selection_mode: str | None,
) -> None:
    old_generation_id, old_long_target_id, old_short_target_id = (
        await _prepare_staged_pair(
            head_template_engine,
            selection_mode=selection_mode,
            pending_selection_mode=pending_selection_mode,
        )
    )
    next_session_start_ms = SESSION_START_MS + 86_400_000
    async with head_template_engine.begin() as connection:
        await _seed_snapshot(
            connection,
            session_start_ms=next_session_start_ms,
            selected_members=(),
        )
    request = CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=next_session_start_ms,
        worker_id="materializer:newest-valid-empty",
    )

    resolved = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(next_session_start_ms + 3_600_000),
    )
    repeated = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(next_session_start_ms + 3_600_010),
    )

    assert resolved.disposition is MaterializationDisposition.VALID_EMPTY
    assert repeated.disposition is MaterializationDisposition.VALID_EMPTY
    assert repeated.selection_authority_id == resolved.selection_authority_id
    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == old_generation_id
            )
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (old_long_target_id, old_short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        vacuum_rows = tuple(
            (
                await connection.execute(
                    sa.select(
                        strategy_entry_vacuums_current.c.entry_vacuum_id,
                        strategy_entry_vacuums_current.c.state,
                        strategy_entry_vacuums_current.c.source_generation_id,
                        strategy_entry_vacuums_current.c.resolved_at_ms,
                    )
                )
            ).all()
        )
        authority_row = (
            await connection.execute(
                sa.select(
                    selection_session_authorities.c.authority_outcome,
                    selection_session_authorities.c.selection_mode,
                    selection_session_authorities.c.selection_snapshot_id,
                    selection_session_authorities.c.materialization_generation_id,
                ).where(
                    selection_session_authorities.c.selection_authority_id
                    == resolved.selection_authority_id
                )
            )
        ).one()
        control_row = (
            await connection.execute(
                sa.select(strategy_selection_control_current).where(
                    strategy_selection_control_current.c.strategy_group_id
                    == "SOR-001"
                )
            )
        ).mappings().one()
        fallback_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(
                selection_session_authorities.c.authority_outcome
                == "FALLBACK_PREVIOUS"
            )
        )
    assert generation_state == "SUPERSEDED"
    assert target_states == ("abandoned", "abandoned")
    assert len(vacuum_rows) == 1
    assert vacuum_rows[0][1:3] == ("VALID_EMPTY", None)
    assert vacuum_rows[0][3] is not None
    assert authority_row == (
        "VALID_EMPTY",
        "dynamic_selection",
        f"selection:{SELECTION_SPEC_ID}:{next_session_start_ms}",
        None,
    )
    assert control_row["selection_mode"] == "dynamic_selection"
    assert control_row["pending_selection_mode"] is None
    assert fallback_count == 0


@pytest.mark.asyncio
async def test_newer_valid_empty_commit_failure_rolls_back_entire_supersession(
    head_template_engine,
) -> None:
    old_generation_id, old_long_target_id, old_short_target_id = (
        await _prepare_staged_pair(head_template_engine)
    )
    next_session_start_ms = SESSION_START_MS + 86_400_000
    async with head_template_engine.begin() as connection:
        await _seed_snapshot(
            connection,
            session_start_ms=next_session_start_ms,
            selected_members=(),
        )
        await connection.execute(
            sa.text(
                """
                CREATE FUNCTION fail_ds06_valid_empty_authority()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.authority_outcome = 'VALID_EMPTY' THEN
                        RAISE EXCEPTION 'ds06 injected valid empty failure';
                    END IF;
                    RETURN NEW;
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                """
                CREATE TRIGGER trg_ds06_valid_empty_authority
                BEFORE INSERT ON brc_selection_session_authorities
                FOR EACH ROW EXECUTE FUNCTION fail_ds06_valid_empty_authority()
                """
            )
        )
    request = CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=next_session_start_ms,
        worker_id="materializer:valid-empty-fault",
    )

    with pytest.raises(DBAPIError, match="ds06 injected valid empty failure"):
        await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            request=request,
            clock_ms=_Clock(next_session_start_ms + 3_600_000),
        )

    async with head_template_engine.connect() as connection:
        generation_state = await connection.scalar(
            sa.select(
                strategy_universe_materialization_generations.c.lifecycle_state
            ).where(
                strategy_universe_materialization_generations.c.materialization_generation_id
                == old_generation_id
            )
        )
        target_states = tuple(
            await connection.scalars(
                sa.select(strategy_universe_versions.c.lifecycle_state)
                .where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (old_long_target_id, old_short_target_id)
                    )
                )
                .order_by(strategy_universe_versions.c.event_spec_id)
            )
        )
        vacuum_state = await connection.scalar(
            sa.select(strategy_entry_vacuums_current.c.state).where(
                strategy_entry_vacuums_current.c.source_generation_id
                == old_generation_id
            )
        )
        valid_empty_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(selection_session_authorities)
            .where(
                selection_session_authorities.c.authority_outcome
                == "VALID_EMPTY"
            )
        )
    assert generation_state == "STAGED"
    assert target_states == ("staged", "staged")
    assert vacuum_state == "RECONFIGURING"
    assert valid_empty_count == 0

    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "DROP TRIGGER trg_ds06_valid_empty_authority "
                "ON brc_selection_session_authorities"
            )
        )
        await connection.execute(
            sa.text("DROP FUNCTION fail_ds06_valid_empty_authority()")
        )
    retried = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=request,
        clock_ms=_Clock(next_session_start_ms + 3_600_010),
    )
    assert retried.disposition is MaterializationDisposition.VALID_EMPTY


@pytest.mark.asyncio
async def test_fallback_commit_failure_rolls_back_and_retry_is_idempotent(
    head_template_engine,
) -> None:
    generation_id, _, _ = await _prepare_staged_pair(head_template_engine)
    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:fallback-crash"),
        clock_ms=_Clock(SESSION_START_MS + 5_400_020),
    )
    assert audit_pending.authority_gap_audit_id is not None
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                CREATE FUNCTION fail_ds06_fallback_commit()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.authority_outcome = 'FALLBACK_PREVIOUS' THEN
                        RAISE EXCEPTION 'ds06 injected fallback commit failure';
                    END IF;
                    RETURN NEW;
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                """
                CREATE TRIGGER trg_ds06_fallback_commit
                BEFORE INSERT ON brc_selection_session_authorities
                FOR EACH ROW EXECUTE FUNCTION fail_ds06_fallback_commit()
                """
            )
        )

    with pytest.raises(DBAPIError, match="ds06 injected fallback commit failure"):
        await complete_pending_authority_gap_audit(
            uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
            audit_source=_CheckedNegativeAuditSource(),
            authority_gap_audit_id=audit_pending.authority_gap_audit_id,
            clock_ms=_Clock(SESSION_START_MS + 5_400_030),
        )
    async with head_template_engine.connect() as connection:
        before_retry = (
            await connection.scalar(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            ),
            await connection.scalar(
                sa.select(strategy_entry_vacuums_current.c.state).where(
                    strategy_entry_vacuums_current.c.source_generation_id
                    == generation_id
                )
            ),
            await connection.scalar(
                sa.select(selection_authority_gap_audits_current.c.state).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == audit_pending.authority_gap_audit_id
                )
            ),
        )
    assert before_retry == ("STAGED", "RECONFIGURING", "PENDING")
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "DROP TRIGGER trg_ds06_fallback_commit "
                "ON brc_selection_session_authorities"
            )
        )
        await connection.execute(sa.text("DROP FUNCTION fail_ds06_fallback_commit()"))

    committed = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_040),
    )
    repeated = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 5_400_050),
    )
    assert committed.disposition is MaterializationDisposition.FALLBACK_PREVIOUS
    assert repeated.selection_authority_id == committed.selection_authority_id


@pytest.mark.asyncio
async def test_fallback_transaction_crossing_first_close_rolls_back_grant(
    head_template_engine,
) -> None:
    generation_id, _, _ = await _prepare_staged_pair(head_template_engine)
    audit_pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:fallback-close-cross"),
        clock_ms=_Clock(SESSION_START_MS + 5_400_020),
    )
    assert audit_pending.authority_gap_audit_id is not None

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_CheckedNegativeAuditSource(),
        authority_gap_audit_id=audit_pending.authority_gap_audit_id,
        clock_ms=_SequenceClock(
            SESSION_START_MS + 5_400_030,
            SESSION_START_MS + 6_299_999,
            SESSION_START_MS + 6_300_000,
        ),
    )

    assert result.disposition is MaterializationDisposition.GAP_AUDIT_WINDOW_EXPIRED
    async with head_template_engine.connect() as connection:
        state = (
            await connection.scalar(
                sa.select(
                    strategy_universe_materialization_generations.c.lifecycle_state
                ).where(
                    strategy_universe_materialization_generations.c.materialization_generation_id
                    == generation_id
                )
            ),
            await connection.scalar(
                sa.select(strategy_entry_vacuums_current.c.state).where(
                    strategy_entry_vacuums_current.c.source_generation_id
                    == generation_id
                )
            ),
            await connection.scalar(
                sa.select(selection_authority_gap_audits_current.c.state).where(
                    selection_authority_gap_audits_current.c.authority_gap_audit_id
                    == audit_pending.authority_gap_audit_id
                )
            ),
        )
    assert state == ("STAGED", "RECONFIGURING", "PENDING")


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "expected_blocker"),
    (
        (
            AuthorityGapAuditSourceIntegrityError(
                "Authority Gap Audit source path is not canonical"
            ),
            "AUTHORITY_GAP_SOURCE_INTEGRITY_FAILED",
        ),
        (
            AuthorityGapAuditDetectorDriftError(
                "Authority Gap Audit detector rejected canonical input"
            ),
            "AUTHORITY_GAP_DETECTOR_DRIFT",
        ),
        (RuntimeError("temporary source failure"), "AUTHORITY_GAP_SOURCE_UNAVAILABLE"),
    ),
)
async def test_gap_audit_source_failure_is_durable_and_never_checked_negative(
    head_template_engine,
    source: Exception,
    expected_blocker: str,
) -> None:
    await _seed_materialization_context(head_template_engine)
    await _seed_previous_dynamic_authority(head_template_engine)
    pending = await coordinate_selection_materialization_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        request=_materialization_request("materializer:source-failure"),
        clock_ms=_Clock(SESSION_START_MS + 4_500_000),
    )
    assert pending.authority_gap_audit_id is not None

    result = await complete_pending_authority_gap_audit(
        uow_factory=lambda: PostgresKernelUnitOfWork(head_template_engine),
        audit_source=_FailingAuditSource(source),
        authority_gap_audit_id=pending.authority_gap_audit_id,
        clock_ms=_Clock(SESSION_START_MS + 4_500_010),
    )

    assert result.disposition is MaterializationDisposition.BLOCKED
    assert result.reason_code == expected_blocker
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
        event_types = tuple(
            await connection.scalars(
                sa.select(selection_authority_gap_audit_events.c.event_type)
                .where(
                    selection_authority_gap_audit_events.c.authority_gap_audit_id
                    == pending.authority_gap_audit_id
                )
                .order_by(selection_authority_gap_audit_events.c.event_sequence)
            )
        )
        authority_count = int(
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
    assert row == ("FAILED", expected_blocker)
    assert event_types == ("STARTED", "FAILED")
    assert authority_count == 0


async def _prepare_generation_owned_long(
    engine,
    *,
    selection_mode: str = "dynamic_selection",
    pending_selection_mode: str | None = None,
):
    changed_members = tuple(
        sorted(
            (
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[0],
                CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS[2],
            )
        )
    )
    await _seed_materialization_context(
        engine,
        selected_members=changed_members,
        selection_mode=selection_mode,
        pending_selection_mode=pending_selection_mode,
    )
    if selection_mode == "dynamic_selection":
        await _seed_previous_dynamic_authority(engine)
    request = _materialization_request("materializer:generation-owned-install")
    clock = _Clock(SESSION_START_MS + 3_600_000)
    generation_id = None
    for _ in range(4):
        result = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            request=request,
            clock_ms=clock,
        )
        generation_id = result.materialization_generation_id or generation_id
    async with PostgresKernelUnitOfWork(engine) as uow:
        await drain_strategy_entry_vacuum_once(
            uow,
            DrainStrategyEntryVacuumRequest(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                now_ms=SESSION_START_MS + 3_600_010,
            ),
        )
    assert generation_id is not None
    async with PostgresKernelUnitOfWork(engine) as uow:
        installed = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=SOR_LONG_EVENT_SPEC_ID,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_ids=changed_members,
                source_kind="dynamic_selection",
                materialization_generation_id=generation_id,
                expected_member_set_digest=selected_member_set_digest(
                    changed_members
                ),
                installed_at_ms=SESSION_START_MS + 3_600_020,
            ),
        )
    return generation_id, changed_members, installed


async def _prepare_staged_pair(
    engine,
    *,
    selection_mode: str = "dynamic_selection",
    pending_selection_mode: str | None = None,
):
    generation_id, changed_members, long_install = (
        await _prepare_generation_owned_long(
            engine,
            selection_mode=selection_mode,
            pending_selection_mode=pending_selection_mode,
        )
    )
    assert long_install.universe is not None
    await make_warming_ready(
        engine,
        universe_version_id=long_install.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_021,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=long_install.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_030,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )
        short_install = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_ids=changed_members,
                source_kind="dynamic_selection",
                materialization_generation_id=generation_id,
                expected_member_set_digest=selected_member_set_digest(
                    changed_members
                ),
                installed_at_ms=SESSION_START_MS + 3_600_031,
            ),
        )
    assert short_install.universe is not None
    await make_warming_ready(
        engine,
        universe_version_id=short_install.universe.universe_version_id,
        warm_closed_bar_time_ms=SESSION_START_MS + 3_600_032,
        valid_until_ms=SESSION_START_MS + 7_200_000,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await advance_strategy_universe(
            uow,
            UniverseActivationRequest(
                universe_version_id=short_install.universe.universe_version_id,
                attempted_at_ms=SESSION_START_MS + 3_600_040,
                operation=UniverseActivationOperation.STAGE_DYNAMIC,
                materialization_generation_id=generation_id,
            ),
        )
    return (
        generation_id,
        long_install.universe.universe_version_id,
        short_install.universe.universe_version_id,
    )


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
        product_profiles = tuple(
            InstrumentProductProfile(
                exchange_instrument_id=instrument_id,
                product_family="crypto_perpetual",
                asset_class="crypto",
                contract_type="PERPETUAL",
                underlying_type="CRYPTO",
                margin_asset="USDT",
                entry_session_policy="continuous",
                status="candidate",
            )
            for instrument_id in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS
        )
        await connection.execute(
            pg_insert(instrument_product_profiles).on_conflict_do_nothing(),
            [
                {
                    **profile.model_dump(mode="python"),
                    "semantic_digest": profile.semantic_digest,
                    "updated_at_ms": SESSION_START_MS,
                }
                for profile in product_profiles
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
    await connection.execute(
        sa.insert(runtime_scopes_current),
        [
            {
                "runtime_scope_id": (
                    f"scope:materialization:{position_side}:{instrument_id}"
                ),
                "strategy_group_id": "SOR-001",
                "strategy_version_id": "sgv:SOR-001:v4",
                "event_spec_id": event_spec_id,
                "runtime_profile_id": "tiny-live-v1",
                "owner_policy_id": "policy-main",
                "exchange_instrument_id": instrument_id,
                "position_side": position_side,
                "universe_version_id": universe_id,
                "universe_semantic_digest": digest,
                "lifecycle_state": "active",
                "observation_enabled": True,
                "entry_enabled": True,
                "scope_version": 1,
                "warm_closed_bar_time_ms": SESSION_START_MS,
                "warm_completed_at_ms": SESSION_START_MS,
                "warm_readiness_digest": "sha256:" + "a" * 64,
                "warm_valid_until_ms": SESSION_START_MS + 90_000_000,
                "next_observation_due_at_ms": SESSION_START_MS + 900_000,
                "lease_expires_at_ms": None,
                "lease_owner": None,
                "observation_generation": 1,
                "updated_at_ms": SESSION_START_MS,
            }
            for universe_id, event_spec_id, position_side in (
                (LONG_UNIVERSE_ID, SOR_LONG_EVENT_SPEC_ID, "long"),
                (SHORT_UNIVERSE_ID, SOR_SHORT_EVENT_SPEC_ID, "short"),
            )
            for instrument_id in SELECTED_MEMBERS
        ],
    )


async def _seed_snapshot(
    connection,
    *,
    session_start_ms: int = SESSION_START_MS,
    selected_members: tuple[str, ...] = SELECTED_MEMBERS,
) -> None:
    snapshot_id = f"selection:{SELECTION_SPEC_ID}:{session_start_ms}"
    ranks = {instrument_id: index + 1 for index, instrument_id in enumerate(selected_members)}
    await connection.execute(
        sa.insert(instrument_selection_snapshots).values(
            selection_snapshot_id=snapshot_id,
            selection_spec_id=SELECTION_SPEC_ID,
            strategy_group_id="SOR-001",
            strategy_version_id="sgv:SOR-001:v4",
            session_start_ms=session_start_ms,
            decision_at_ms=session_start_ms + 3_600_000,
            feature_cutoff_at_ms=session_start_ms + 3_600_000,
            eligibility_not_before_ms=session_start_ms + 4_500_000,
            expires_at_ms=session_start_ms + 90_000_000,
            candidate_count=24,
            ready_count=len(selected_members),
            selected_count=len(selected_members),
            source_observed_at_ms=session_start_ms + 3_600_000,
            source_semantic_digest="sha256:" + "1" * 64,
            selection_semantic_digest="sha256:" + "2" * 64,
            created_at_ms=session_start_ms + 3_600_000,
        )
    )
    await connection.execute(
        sa.insert(instrument_selection_member_decisions),
        [
            {
                "selection_snapshot_id": snapshot_id,
                "member_decision_id": f"member:{session_start_ms}:{index}",
                "selection_spec_id": SELECTION_SPEC_ID,
                "session_start_ms": session_start_ms,
                "feature_cutoff_at_ms": session_start_ms + 3_600_000,
                "input_window_start_ms": session_start_ms - 82_800_000,
                "input_window_end_ms": session_start_ms + 3_600_000,
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


class _FailingAuditSource:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        del request
        raise self._error


class _UnexpectedAuditSource:
    def __init__(self) -> None:
        self.called = False

    async def evaluate_authority_gap(
        self,
        request: AuthorityGapAuditEvaluationRequest,
    ) -> tuple[AuthorityGapScopeResult, ...]:
        del request
        self.called = True
        raise AssertionError("Gap Audit source must not run outside its Session window")


def _materialization_request(worker_id: str) -> CoordinateSelectionMaterializationRequest:
    return CoordinateSelectionMaterializationRequest(
        selection_spec_id=SELECTION_SPEC_ID,
        strategy_group_id="SOR-001",
        session_start_ms=SESSION_START_MS,
        worker_id=worker_id,
    )
