from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

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
    CoordinateGenericGenerationRequest,
    CoordinateGenericPeriodRequest,
    CoordinateGenericSnapshotRequest,
    MaterializationDisposition,
    coordinate_selection_materialization_once,
    prepare_generic_current_close_proof,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
)
from src.trading_kernel.application.ingest_signal import (
    resolve_selection_entry_authority,
    resolve_selection_observation_authority,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    OwnerControlBlocked,
    OwnerControlConflict,
    stage_generic_dynamic_selection_mode,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    ComparativeProjectionAuthorityChanged,
    build_comparative_projection_failure,
    build_comparative_universe_projection,
)
from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    build_dynamic_membership_freshness,
    build_generic_selection_period,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import (
    LockedObservationCursor,
    advance_comparison_bound_exposure_episode,
    advance_exposure_episode,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
    GenericStaticMaterializationGeneration,
    MaterializationEventBaseline,
)
from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
    compute_generic_selection,
)
from src.trading_kernel.domain.generic_selection_jobs import GenericSelectionJobClaim
from src.trading_kernel.domain.generic_selection_spec import (
    SpecNumericInstallationEvidence,
)
from src.trading_kernel.domain.instrument_selection import (
    SelectionAttemptOutcome,
    SelectionJobFailure,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    GenericRecoveryAuthority,
    GenericSelectionAuthority,
    selected_member_set_digest,
)
from src.trading_kernel.domain.strategy_entry_vacuum import (
    StrategyEntryVacuum,
    StrategyEntryVacuumState,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
    SelectionJobConflict,
    generic_authority_from_storage,
    generic_authority_storage_values,
    generic_recovery_authority_storage_values,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    materialization_generation_event_baselines,
    selection_authority_event_bindings,
    selection_session_authorities,
    strategy_selection_control_current,
    strategy_universe_materialization_generations,
    strategy_universe_materialization_targets,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_universe_repository import (
    PostgresStrategyUniverseRepository,
    UniverseInstallConflict,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.integration.universe_activation_support import (
    make_warming_ready,
)
from tests.trading_kernel.support.generic_selection import (
    CUTOFF,
    HOUR,
    inputs,
    qualify_window,
    shift_window,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    brf2_short_snapshot,
    cpm_flat_snapshot,
    cpm_long_snapshot,
    mi_flat_snapshot,
    mi_long_snapshot,
    mpg_flat_snapshot,
    mpg_long_snapshot,
)


@pytest_asyncio.fixture
async def database(head_template_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(
            account_id="generic-snapshot", runtime_commit="a" * 40,
            schema_revision=CURRENT_SCHEMA_REVISION, seeded_at_ms=CUTOFF - HOUR,
        ))
        for group in ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"):
            spec = inputs(group).spec
            await uow.instrument_selection.install_generic_spec(spec, installed_at_ms=CUTOFF-HOUR, certification=SpecNumericInstallationEvidence(
                selection_spec_id=spec.selection_spec_id, algorithm_semantic_digest=spec.algorithm_semantic_digest,
                checked_cutoffs=463 if spec.cadence_hours == 4 else 1852, mismatch_count=0, source_archive_count=96,
                reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb", common_numeric_authority="PASS", sor_golden="PASS", spec_cert="PASS",
            ))
    yield head_template_engine


async def _install_static_selection_source(database: AsyncEngine, group: str):
    spec = inputs(group).spec
    members = spec.candidate_ids[:1]
    async with PostgresKernelUnitOfWork(database) as uow:
        installed = await install_strategy_universe(uow,UniverseInstallRequest(
            event_spec_id=spec.event_spec_id,runtime_profile_id="tiny-live-v1",
            owner_policy_id="policy-main",exchange_instrument_ids=members,
            installed_at_ms=CUTOFF-1,
        ))
    assert installed.universe is not None
    uid = installed.universe.universe_version_id
    comparison_id = None
    async with database.begin() as conn:
        await conn.execute(sa.text(
            "UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:at "
            "WHERE universe_version_id=:uid"
        ),{"uid":uid,"at":CUTOFF-1})
        await conn.execute(sa.text(
            "UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,"
            "observation_enabled=true,warm_closed_bar_time_ms=:closed,warm_completed_at_ms=:at,"
            "warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"
        ),{"uid":uid,"closed":CUTOFF-HOUR,"at":CUTOFF-1,
            "digest":"sha256:"+"1"*64,"valid":CUTOFF+2*HOUR})
        await conn.execute(sa.text(
            "INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:at)"
        ),{"event":spec.event_spec_id,"uid":uid,
            "digest":installed.universe.semantic_digest,"at":CUTOFF-1})
        if group in {"MPG-001","MI-001"}:
            digest = canonical_digest({"exchange_instrument_ids":members})
            comparison_id = "comparison:"+digest[7:]
            await conn.execute(sa.text(
                "INSERT INTO brc_comparison_universe_definitions VALUES(:id,:digest,1)"
            ),{"id":comparison_id,"digest":digest})
            await conn.execute(sa.text(
                "INSERT INTO brc_comparison_universe_members VALUES(:id,:member)"
            ),{"id":comparison_id,"member":members[0]})
            await conn.execute(sa.text(
                "INSERT INTO brc_comparison_binding_current VALUES(:event,:id,0,:uid)"
            ),{"event":spec.event_spec_id,"id":comparison_id,"uid":uid})
    return uid,comparison_id


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
async def test_first_generic_owner_request_freezes_actual_static_rollback_source(
    database: AsyncEngine, group: str,
) -> None:
    uid,comparison_id = await _install_static_selection_source(database,group)
    request = ControlMutationRequest(expected_version=1,reason="capture_static_source",
        idempotency_key=f"owner:baseline:{group}",owner_identity="owner",now_ms=CUTOFF-1)
    async with PostgresKernelUnitOfWork(database) as uow:
        staged = await stage_generic_dynamic_selection_mode(
            uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=request,authentication_strength="totp_step_up",
        )
    assert staged.rollback_baseline_id is not None
    async with database.connect() as conn:
        baseline = (await conn.execute(sa.text(
            "SELECT * FROM brc_strategy_selection_rollback_baselines WHERE rollback_baseline_id=:id"
        ),{"id":staged.rollback_baseline_id})).mappings().one()
        events = (await conn.execute(sa.text(
            "SELECT * FROM brc_selection_rollback_baseline_events WHERE rollback_baseline_id=:id"
        ),{"id":staged.rollback_baseline_id})).mappings().all()
        assert baseline["strategy_group_id"] == group
        assert baseline["strategy_version_id"] == inputs(group).spec.strategy_version_id
        assert len(events) == 1
        assert events[0]["universe_version_id"] == uid
        assert events[0]["comparison_universe_id"] == comparison_id
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_members "
            "WHERE universe_version_id=:uid"),{"uid":uid}) == 1
    async with PostgresKernelUnitOfWork(database) as uow:
        repeated = await stage_generic_dynamic_selection_mode(
            uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=request,authentication_strength="totp_step_up",
        )
    assert repeated == staged
    with pytest.raises(sa.exc.DBAPIError,match="rollback baseline pointer is immutable"):
        async with database.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE brc_strategy_selection_control_current SET rollback_baseline_id=NULL "
                "WHERE strategy_group_id=:group"
            ),{"group":group})
    other_group = "CPM-RO-001" if group != "CPM-RO-001" else "BRF2-001"
    with pytest.raises(sa.exc.DBAPIError,match="rollback baseline parent mismatch"):
        async with database.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE brc_strategy_selection_control_current SET rollback_baseline_id=:id "
                "WHERE strategy_group_id=:group"
            ),{"id":staged.rollback_baseline_id,"group":other_group})
    with pytest.raises(sa.exc.DBAPIError,match="immutable"):
        async with database.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE brc_selection_rollback_baseline_events SET comparison_universe_id=NULL "
                "WHERE rollback_baseline_id=:id"
            ),{"id":staged.rollback_baseline_id})
    async with database.connect() as conn:
        await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        frozen = await PostgresInstrumentSelectionRepository(conn).get_generic_static_rollback_baseline(
            staged.rollback_baseline_id)
        assert frozen.source_event.universe_version_id == uid
        assert frozen.source_event.comparison_universe_id == comparison_id


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["missing_universe","missing_comparison","commit_fault"])
async def test_generic_owner_baseline_failure_commits_no_authorization_or_pending_mode(
    database: AsyncEngine, defect: str,
) -> None:
    group = "MPG-001"
    if defect != "missing_universe":
        await _install_static_selection_source(database,group)
    if defect == "missing_comparison":
        async with database.begin() as conn:
            await conn.execute(sa.text("DELETE FROM brc_comparison_binding_current WHERE event_spec_id=:event"),
                {"event":inputs(group).spec.event_spec_id})
    request = ControlMutationRequest(expected_version=1,reason="baseline_refusal",
        idempotency_key=f"owner:baseline:{defect}",owner_identity="owner",now_ms=CUTOFF-1)
    if defect == "commit_fault":
        with pytest.raises(OwnerControlConflict,match="version_conflict"):
            async with PostgresKernelUnitOfWork(database) as uow:
                with patch.object(uow.instrument_selection,"stage_pending_generic_selection_mode",
                    new=AsyncMock(return_value=None)):
                    await stage_generic_dynamic_selection_mode(uow,strategy_group_id=group,
                        effective_period_anchor_ms=CUTOFF,request=request,
                        authentication_strength="totp_step_up")
    else:
        with pytest.raises(OwnerControlBlocked,match="static_baseline_source_invalid"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await stage_generic_dynamic_selection_mode(uow,strategy_group_id=group,
                    effective_period_anchor_ms=CUTOFF,request=request,
                    authentication_strength="totp_step_up")
    async with database.connect() as conn:
        for table in ("brc_strategy_selection_rollback_baselines",
            "brc_selection_rollback_baseline_events",
            "brc_instrument_selection_jobs_current","brc_strategy_universe_materialization_generations"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0,table
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_owner_authorizations WHERE idempotency_key=:key"
        ),{"key":request.idempotency_key}) == 0
        control = (await conn.execute(sa.text("SELECT * FROM brc_strategy_selection_control_current "
            "WHERE strategy_group_id=:group"),{"group":group})).mappings().one()
        assert control["selection_mode"] == "static_baseline"
        assert control["pending_selection_mode"] is None
        assert control["rollback_baseline_id"] is None and control["control_version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
async def test_direct_sql_cannot_forge_static_rollback_baseline_digest(
    database: AsyncEngine, group: str,
) -> None:
    uid,comparison_id = await _install_static_selection_source(database,group)
    spec = inputs(group).spec
    bid = "rollback-baseline:"+"b"*64
    with pytest.raises(sa.exc.DBAPIError,match="Static baseline semantic identity mismatch"):
        async with database.begin() as conn:
            await conn.execute(sa.text(
                "INSERT INTO brc_strategy_selection_rollback_baselines "
                "(rollback_baseline_id,strategy_group_id,strategy_version_id,semantic_digest,captured_at_ms) "
                "VALUES(:id,:group,:version,:digest,:at)"
            ),{"id":bid,"group":group,"version":spec.strategy_version_id,
                "digest":"sha256:"+"b"*64,"at":CUTOFF-1})
            await conn.execute(sa.text(
                "INSERT INTO brc_selection_rollback_baseline_events "
                "(rollback_baseline_id,event_spec_id,position_side,universe_version_id,comparison_universe_id) "
                "VALUES(:id,:event,:side,:uid,:comparison)"
            ),{"id":bid,"event":spec.event_spec_id,"side":spec.position_side,
                "uid":uid,"comparison":comparison_id})
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_rollback_baseline_events")) == 0


@pytest.mark.asyncio
async def test_concurrent_first_owner_requests_commit_one_static_capture(database: AsyncEngine) -> None:
    group = "MPG-001"
    await _install_static_selection_source(database,group)

    async def stage(key: str):
        async with PostgresKernelUnitOfWork(database) as uow:
            return await stage_generic_dynamic_selection_mode(
                uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
                request=ControlMutationRequest(expected_version=1,reason="concurrent_capture",
                    idempotency_key=key,owner_identity="owner",now_ms=CUTOFF-1),
                authentication_strength="totp_step_up",
            )
    results = await asyncio.gather(stage("baseline:concurrent:a"),
        stage("baseline:concurrent:b"),return_exceptions=True)
    assert sum(not isinstance(result,BaseException) for result in results) == 1
    assert sum(isinstance(result,OwnerControlConflict) for result in results) == 1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_rollback_baseline_events")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_owner_authorizations "
            "WHERE idempotency_key LIKE 'baseline:concurrent:%'")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_jobs_current")) == 0


@pytest.mark.asyncio
async def test_static_baseline_fact_cannot_commit_outside_owner_activation_transaction(
    database: AsyncEngine,
) -> None:
    group = "MPG-001"
    await _install_static_selection_source(database,group)
    with pytest.raises(sa.exc.DBAPIError,match="requires atomic Owner capture"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.capture_generic_static_rollback_baseline(
                selection_spec_id=inputs(group).spec.selection_spec_id,
                captured_at_ms=CUTOFF-1,
            )
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_rollback_baseline_events")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("pending", [False,True])
async def test_recovery_checkpoint_is_durable_and_blocks_reuse_of_consumed_close(database: AsyncEngine, group: str, pending: bool) -> None:
    from src.trading_kernel.domain.authority_recovery_rebase import (
        advance_authority_recovery_rebase,
        begin_authority_recovery_rebase,
    )
    source = inputs(group)
    spec = source.spec
    member = compute_generic_selection(source).selected_members[0]
    source = source.model_copy(update={"member_windows":tuple(qualify_window(w,w.exchange_instrument_id==member) for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    assert snapshot.selected_members == (member,)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=source.decision_at_ms,source_observed_at_ms=source.source_observed_at_ms)
    key = build_episode_domain_key(event_spec_id=spec.event_spec_id,exchange_instrument_id=member,position_side=spec.position_side)
    recovery = advance_authority_recovery_rebase(current=None,episode_domain_key=key,recovery_id="recovery:test",recovery_revision=1,
        effective_from_ms=CUTOFF+1,first_eligible_close_time_ms=CUTOFF+HOUR,
        observed_close_time_ms=CUTOFF+HOUR,detector_status=DetectorStatus.TRIGGERED).checkpoint
    if pending:
        recovery = begin_authority_recovery_rebase(current=None,episode_domain_key=key,recovery_id="recovery:test",recovery_revision=1,
            effective_from_ms=CUTOFF+1,first_eligible_close_time_ms=CUTOFF+HOUR,latest_consumed_close_time_ms=None)
    async with database.begin() as conn:
        # Storage-only prerequisite. No Recovery Authority or trading grant is
        # fabricated; the dormant checkpoint must already fence cursor reuse.
        await conn.execute(sa.text("INSERT INTO brc_exposure_episode_current (episode_domain_key,event_spec_id,exchange_instrument_id,position_side,episode_policy,state,last_observed_at_ms,projection_version,authority_recovery_id,authority_recovery_revision,authority_recovery_effective_from_ms,authority_recovery_first_eligible_close_time_ms,authority_recovery_last_observed_at_ms,authority_recovery_last_detector_status,authority_recovery_checkpoint_version) VALUES (:key,:event,:member,:side,'rising_edge','authority_rebase_required',:observed,1,:rid,1,:effective,:first,:observed,:status,1)"),
            {"key":key,"event":spec.event_spec_id,"member":member,"side":spec.position_side,"first":CUTOFF+HOUR,"rid":recovery.recovery_id,"effective":CUTOFF+1,
             "observed":None if pending else CUTOFF+HOUR,"status":None if pending else "triggered"})
    await database.dispose()
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.signals.get_authority_recovery_checkpoint(key) == recovery
        state = await uow.signals.lock_exposure_episode(key)
        assert state is not None and state.state == "authority_rebase_required" and state.exposure_episode_id is None
        with pytest.raises(ValueError,match="rebase"):
            advance_exposure_episode(contract=strategy_contract_for(spec.event_spec_id),current=state,
                detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=CUTOFF+2*HOUR,
                observed_at_ms=CUTOFF+2*HOUR,exchange_instrument_id=member)
        if pending:
            coverage = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,exchange_instrument_ids=(member,),closed_at_ms=CUTOFF+HOUR)
            assert coverage[0].episode_version == 1 and coverage[0].authority_recovery_checkpoint_version == 1
            assert coverage[0].last_observed_at_ms is None
            assert state.last_observed_at_ms is None
    if pending:
        with pytest.raises(sa.exc.DBAPIError):
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_exposure_episode_current SET state='armed' WHERE episode_domain_key=:key"),{"key":key})
        return
    async with PostgresKernelUnitOfWork(database) as uow:
        with pytest.raises(RuntimeError,match="already consumed"):
            await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,exchange_instrument_ids=(member,),closed_at_ms=CUTOFF+HOUR)
        coverage = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,exchange_instrument_ids=(member,),closed_at_ms=CUTOFF+2*HOUR)
        assert coverage[0].authority_recovery_checkpoint_version == 1
        assert coverage[0].last_observed_at_ms == CUTOFF+HOUR
        recovery_coverage = await uow.signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,
            exchange_instrument_ids=(member,),selection_mode="dynamic_selection",evaluated_at_ms=CUTOFF+HOUR+1)
        assert recovery_coverage == coverage
        with pytest.raises(RuntimeError,match="future"):
            await uow.signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,
                exchange_instrument_ids=(member,),selection_mode="dynamic_selection",evaluated_at_ms=CUTOFF+HOUR-1)
        with pytest.raises(ValueError):
            await uow.signals.lock_recovery_close_coverage(event_spec_id=spec.event_spec_id,
                exchange_instrument_ids=(member,member),selection_mode="dynamic_selection",evaluated_at_ms=CUTOFF+HOUR+1)
    for update in ("authority_recovery_revision=0", "authority_recovery_first_eligible_close_time_ms=authority_recovery_effective_from_ms",
                   "authority_recovery_last_detector_status='invalid'", "authority_recovery_checkpoint_version=NULL",
                   "authority_recovery_armed_at_ms=authority_recovery_last_observed_at_ms"):
        with pytest.raises(sa.exc.DBAPIError):
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_exposure_episode_current SET "+update+" WHERE episode_domain_key=:key"),{"key":key})
    async with database.begin() as conn:
        # Recovery may advance while preserving an older canonical Episode.
        await conn.execute(sa.text("UPDATE brc_exposure_episode_current SET state='armed',last_observed_at_ms=:old WHERE episode_domain_key=:key"),{"old":CUTOFF,"key":key})
    async with PostgresKernelUnitOfWork(database) as uow:
        with pytest.raises(RuntimeError,match="already consumed"):
            await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,exchange_instrument_ids=(member,),closed_at_ms=CUTOFF+HOUR)
    proof = CurrentFinalCloseGrantProof(selection_snapshot_id=snapshot.selection_snapshot_id,selection_committed_at_ms=snapshot.committed_at_ms,
        source_snapshot_cutoff_at_ms=CUTOFF,period=build_generic_selection_period(feature_cutoff_at_ms=CUTOFF,cadence_hours=spec.cadence_hours),
        current_final_close_time_ms=CUTOFF+HOUR,authority_granted_at_ms=CUTOFF+HOUR+8000,
        observation_cursors=(LockedObservationCursor(episode_domain_key=key,exchange_instrument_id=member,episode_version=1,
            comparison_checkpoint_version=0,last_observed_at_ms=CUTOFF),))
    async with database.begin() as conn:
        query = sa.text("SELECT brc_generic_close_proof_matches(:sid,CAST(:proof AS jsonb),:at)")
        params = {"sid":snapshot.selection_snapshot_id,"proof":proof.model_dump_json(),"at":proof.authority_granted_at_ms}
        assert await conn.scalar(query,params) is False
        checkpoint = await conn.begin_nested()
        await conn.execute(sa.text("UPDATE brc_exposure_episode_current SET authority_recovery_id=NULL,authority_recovery_revision=NULL,authority_recovery_effective_from_ms=NULL,authority_recovery_first_eligible_close_time_ms=NULL,authority_recovery_armed_at_ms=NULL,authority_recovery_last_observed_at_ms=NULL,authority_recovery_last_detector_status=NULL,authority_recovery_checkpoint_version=NULL WHERE episode_domain_key=:key"),{"key":key})
        assert await conn.scalar(query,params) is True
        await checkpoint.rollback()
        assert await conn.scalar(query,params) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("group,normal_parent", [
    (group, mode) for group in ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001") for mode in (False, True, "commit")
] + [("CPM-RO-001", "first"), ("BRF2-001", "first")])
async def test_prepare_generic_proof_uses_database_clock_and_complete_locked_coverage(database: AsyncEngine, group: str, normal_parent: bool | str) -> None:
    commit_parent = normal_parent in ("commit", "first")
    source = inputs(group)
    async with PostgresKernelUnitOfWork(database) as uow:
        now = await uow.instrument_selection.read_authority_clock_ms()
    cadence = source.spec.cadence_hours*HOUR
    cutoff = (now-HOUR)//cadence*cadence
    delta = cutoff-source.feature_cutoff_at_ms
    source = source.model_copy(update={"feature_cutoff_at_ms":cutoff,"decision_at_ms":source.decision_at_ms+delta,
        "source_observed_at_ms":source.source_observed_at_ms+delta,"committed_at_ms":source.committed_at_ms+delta,
        "member_windows":tuple(shift_window(w,delta) for w in source.member_windows)})
    if normal_parent:
        chosen = compute_generic_selection(source).selected_members[0]
        source = source.model_copy(update={"member_windows":tuple(qualify_window(w,w.exchange_instrument_id==chosen) for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=source.decision_at_ms,source_observed_at_ms=source.source_observed_at_ms)
        if normal_parent:
            installed = await install_strategy_universe(uow,UniverseInstallRequest(event_spec_id=source.spec.event_spec_id,
                runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",exchange_instrument_ids=snapshot.selected_members,installed_at_ms=cutoff))
            assert installed.universe is not None
    if normal_parent:
        async with database.begin() as conn:
            uid = installed.universe.universe_version_id
            await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:now WHERE universe_version_id=:uid"),{"uid":uid,"now":cutoff})
            await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,warm_closed_bar_time_ms=:now,warm_completed_at_ms=:now,warm_readiness_digest=:digest,warm_valid_until_ms=:expiry WHERE universe_version_id=:uid"),{"uid":uid,"now":cutoff,"digest":installed.universe.semantic_digest,"expiry":snapshot.expires_at_ms})
            await conn.execute(sa.text("INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:now)"),{"event":source.spec.event_spec_id,"uid":uid,"digest":installed.universe.semantic_digest,"now":cutoff})
    with pytest.raises(ValueError,match="latest-close"):
        async with PostgresKernelUnitOfWork(database) as uow:
            start = now//HOUR*HOUR+8_000
            with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(side_effect=[start,start//HOUR*HOUR+HOUR+1])):
                await prepare_generic_current_close_proof(uow,selection_snapshot_id=snapshot.selection_snapshot_id)
    async with PostgresKernelUnitOfWork(database) as uow:
        proof = await prepare_generic_current_close_proof(uow,selection_snapshot_id=snapshot.selection_snapshot_id)
        assert proof.authority_granted_at_ms >= now
        assert proof.current_final_close_time_ms == proof.authority_granted_at_ms//HOUR*HOUR
        assert tuple(c.exchange_instrument_id for c in proof.observation_cursors) == snapshot.selected_members
        freshness = build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,
            source_member_set_digest=snapshot.member_set_digest,period=proof.period)
        if normal_parent:
            cid = "comparison:"+canonical_digest({"exchange_instrument_ids":source.spec.candidate_ids})[7:] if group in {"MPG-001","MI-001"} else None
            authority = GenericSelectionAuthority(selection_authority_id="authority:normal:"+group,
                selection_spec_id=source.spec.selection_spec_id,strategy_group_id=group,selection_epoch_id=snapshot.selection_epoch_id,
                selection_snapshot_id=snapshot.selection_snapshot_id,authority_sequence=1,owner_control_version=1,selection_control_version=1,
                period=proof.period,authority_outcome="NO_CHANGE",event_binding=AuthorityEventBinding(event_spec_id=source.spec.event_spec_id,
                    position_side=source.spec.position_side,grant_state="ACTIVE",universe_version_id=installed.universe.universe_version_id,member_set_digest=snapshot.member_set_digest),
                current_close_proof=proof,membership_freshness=freshness,comparison_universe_id=cid,
                comparison_transition_revision=1 if cid else None,effective_from_ms=proof.authority_granted_at_ms,created_at_ms=proof.authority_granted_at_ms)
            # Storage contract only; no current pointer or trading activation.
            async with database.begin() as conn:
                if cid:
                    await conn.execute(sa.text("INSERT INTO brc_comparison_binding_current VALUES(:event,:cid,1,NULL)"),{"event":source.spec.event_spec_id,"cid":cid})
                for changes in ({"current_close_proof":{}}, {"membership_freshness":{}},
                                {"first_eligible_close_time_ms":proof.current_final_close_time_ms-HOUR},
                                {"grant_proof_kind":"AUDITED_AUTHORITY_GAP"}):
                    with pytest.raises(sa.exc.DBAPIError):
                        async with conn.begin_nested():
                            await conn.execute(sa.insert(selection_session_authorities).values(**{
                                **generic_authority_storage_values(authority),**changes}))
                with pytest.raises(sa.exc.DBAPIError,match="recovery proof differs"):
                    async with conn.begin_nested():
                        await conn.execute(sa.insert(selection_session_authorities).values(**{
                            **generic_authority_storage_values(authority),"recovery_grant_proof":{}}))
                with pytest.raises(sa.exc.DBAPIError,match="Generic NO_CHANGE requires exact current active membership"):
                    async with conn.begin_nested():
                        await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
                        await conn.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,
                            **authority.event_binding.model_dump(mode="json")))
                        await conn.execute(sa.text("DELETE FROM brc_strategy_universe_current WHERE event_spec_id=:event"),{"event":source.spec.event_spec_id})
                        await conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                if not commit_parent:
                    await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
                    await conn.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,
                        **authority.event_binding.model_dump(mode="json")))
            if commit_parent:
                await enable_epoch(database,group,pending=normal_parent=="first",pending_anchor_ms=cutoff)
                authority = authority.model_copy(update={"selection_control_version":2+int(normal_parent=="first"),
                    "activation_authorization_id":"owner:first:"+group if normal_parent=="first" else None})
                async with database.begin() as conn:
                    await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true WHERE owner_policy_id='policy-main'"))
                await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=proof.current_final_close_time_ms,
                    valid_until_ms=proof.current_final_close_time_ms+HOUR)
                if cid:
                    template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
                    delta = proof.current_final_close_time_ms-template.trigger_candle_close_time_ms
                    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
                    cache = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=uid,
                        strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=proof.current_final_close_time_ms,
                        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids))
                    await uow.strategy_universes.save_comparative_projection(cache.model_copy(update={"comparison_transition_revision":1}))
                with pytest.raises(SelectionJobConflict,match="current version"):
                    await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=99)
                with pytest.raises(SelectionJobConflict,match="Owner control"):
                    await uow.instrument_selection.commit_generic_no_change(authority.model_copy(update={"owner_control_version":99}),expected_current_version=None)
                # Test-only savepoint makes the final-clock rollback observable
                # without releasing the outer proof's per-Episode locks.
                assert uow._connection is not None
                pending_control = await uow.instrument_selection.get_selection_control(group)
                if normal_parent == "first":
                    with pytest.raises(SelectionJobConflict,match="Selection control"):
                        await uow.instrument_selection.commit_generic_no_change(authority.model_copy(update={"activation_authorization_id":None}),expected_current_version=None)
                    with pytest.raises(sa.exc.DBAPIError,match="atomic authorized mode transition"):
                        async with uow._connection.begin_nested():
                            with patch.object(uow.instrument_selection,"activate_pending_selection_mode",new=AsyncMock(return_value=pending_control)):
                                await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=None)
                                await uow._connection.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                with pytest.raises(ValueError,match="boundary"):
                    async with uow._connection.begin_nested():
                        with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(side_effect=[
                            proof.authority_granted_at_ms,proof.period.period_expires_at_ms])):
                            await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=None)
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
                assert await uow.instrument_selection.get_selection_control(group) == pending_control
                assert await uow._connection.scalar(sa.select(sa.func.count()).select_from(selection_session_authorities)) == 0
                @asynccontextmanager
                async def borrowed_transaction():
                    # Share the real transaction already holding coverage locks.
                    yield uow
                coordinator_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="no-change")
                coordinated = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,
                    request=coordinator_request,clock_ms=lambda:proof.authority_granted_at_ms)
                assert coordinated.disposition == MaterializationDisposition.NO_CHANGE
                current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
                assert current is not None
                authority = current.authority
                control = await uow.instrument_selection.get_selection_control(group)
                assert control is not None and control.selection_mode.value == "dynamic_selection"
                assert control.control_version == 2 + int(normal_parent=="first")
                assert authority.selection_control_version == control.control_version
                assert authority.activation_authorization_id == ("owner:first:"+group if normal_parent=="first" else None)
                if normal_parent == "first":
                    with pytest.raises(sa.exc.DBAPIError,match="atomic authorized mode transition"):
                        async with uow._connection.begin_nested():
                            await uow._connection.execute(sa.text("DELETE FROM brc_selection_authority_current WHERE selection_spec_id=:spec"),{"spec":source.spec.selection_spec_id})
                            await uow._connection.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                repeated = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,
                    request=coordinator_request,clock_ms=lambda:proof.authority_granted_at_ms+1)
                assert repeated.selection_authority_id == coordinated.selection_authority_id
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=authority.expires_at_ms)):
                    stale_retry = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,
                        request=coordinator_request,clock_ms=lambda:proof.authority_granted_at_ms+2)
                assert stale_retry.disposition == MaterializationDisposition.BLOCKED
                assert stale_retry.reason_code == "GENERIC_NO_CHANGE_AUTHORITY_STALE"
                await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=None)
                # Assert inside this transaction; it still owns the coverage locks.
                current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
                assert current is not None and current.authority == authority and current.projection_version == 1
                scope_id = await uow._connection.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid"),{"uid":uid})
                scope = await uow.signals.get_runtime_scope(scope_id)
                assert scope is not None
                allowed = await resolve_selection_entry_authority(uow,runtime_scope=scope,
                    birth_selection_authority_id=None,observed_close_time_ms=proof.current_final_close_time_ms,
                    now_ms=await uow.instrument_selection.read_authority_clock_ms(),allow_current_as_birth=True,lock_current=True)
                assert allowed.allowed and allowed.selection_authority_id == authority.selection_authority_id
                assert await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
                assert await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
            async with database.connect() as conn:
                if not commit_parent:
                    row = (await conn.execute(sa.select(selection_session_authorities))).mappings().one()
                    bindings = tuple((await conn.execute(sa.select(selection_authority_event_bindings))).mappings())
                    assert generic_authority_from_storage(dict(row),spec=source.spec,event_bindings=tuple(dict(b) for b in bindings)) == authority
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_authority_current")) == 0
            if cid and not commit_parent:
                async with PostgresKernelUnitOfWork(database) as read_uow:
                    comparison_source = await read_uow.strategy_universes.get_comparative_source(
                        event_spec_id=source.spec.event_spec_id,universe_version_id=uid)
                    assert comparison_source.exchange_instrument_ids == source.spec.candidate_ids
                    assert comparison_source.comparison_transition_revision == 1
                with pytest.raises(ComparativeProjectionAuthorityChanged,match="current Universe"):
                    async with database.begin() as conn:
                        await conn.execute(sa.text("DELETE FROM brc_strategy_universe_current WHERE event_spec_id=:event"),{"event":source.spec.event_spec_id})
                        await PostgresStrategyUniverseRepository(conn).get_comparative_source(
                            event_spec_id=source.spec.event_spec_id,universe_version_id=uid)
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT brc_generic_freshness_matches(:sid,CAST(:fresh AS jsonb))"),
                {"sid":snapshot.selection_snapshot_id,"fresh":freshness.model_dump_json()}) is True
            for changes in ({"membership_valid_until_ms":freshness.membership_valid_until_ms+HOUR},
                            {"source_member_set_digest":"sha256:"+"0"*64}, {"state":"GRACE","consecutive_missed_periods":1}):
                assert await conn.scalar(sa.text("SELECT brc_generic_freshness_matches(:sid,CAST(:fresh AS jsonb))"),
                    {"sid":snapshot.selection_snapshot_id,"fresh":json.dumps({**freshness.model_dump(mode="json"),**changes})}) is False
            assert await conn.scalar(sa.text("SELECT brc_generic_close_proof_matches(:sid,CAST(:proof AS jsonb),:at)"),
                {"sid":snapshot.selection_snapshot_id,"proof":proof.model_dump_json(),"at":proof.authority_granted_at_ms}) is True
            payload = proof.model_dump(mode="json")
            for changes in ({"observation_cursors":[]}, {"selection_committed_at_ms":proof.selection_committed_at_ms+1},
                            {"current_final_close_time_ms":proof.current_final_close_time_ms-HOUR},
                            {"observation_cursors":[{**payload["observation_cursors"][0],"episode_version":99},*payload["observation_cursors"][1:]]},
                            {"observation_cursors":[{**payload["observation_cursors"][0],"authority_recovery_checkpoint_version":99},*payload["observation_cursors"][1:]]},
                            {"unexpected_field":True}):
                assert await conn.scalar(sa.text("SELECT brc_generic_close_proof_matches(:sid,CAST(:proof AS jsonb),:at)"),
                    {"sid":snapshot.selection_snapshot_id,"proof":json.dumps({**payload,**changes}),"at":proof.authority_granted_at_ms}) is False
        state = advance_exposure_episode(contract=strategy_contract_for(source.spec.event_spec_id),current=None,
            detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,observed_at_ms=proof.current_final_close_time_ms,
            exchange_instrument_id=snapshot.selected_members[0]).current
        await uow.signals.save_exposure_episode(state,expected_version=0)
    if commit_parent:
        await database.dispose()
        async with PostgresKernelUnitOfWork(database) as restored:
            persisted = await restored.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            control = await restored.instrument_selection.get_selection_control(group)
            assert persisted is not None and persisted.authority == authority
            assert control is not None and control.selection_mode.value == "dynamic_selection"
            assert control.control_version == authority.selection_control_version
            assert control.pending_selection_mode is None and control.pending_authorization_id is None
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_generations")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current")) == 0
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT brc_generic_close_proof_matches(:sid,CAST(:proof AS jsonb),:at)"),
            {"sid":snapshot.selection_snapshot_id,"proof":proof.model_dump_json(),"at":proof.authority_granted_at_ms}) is False
    with pytest.raises(SelectionJobConflict,match="PostgreSQL facts"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.require_generic_close_proof(proof)
    with pytest.raises(RuntimeError,match="already consumed"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await prepare_generic_current_close_proof(uow,selection_snapshot_id=snapshot.selection_snapshot_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_grant_coverage_rejects_consumed_episode_close(database: AsyncEngine, group: str) -> None:
    spec = inputs(group).spec
    contract = strategy_contract_for(spec.event_spec_id)
    members = spec.candidate_ids[:2]
    close = CUTOFF+HOUR
    async with PostgresKernelUnitOfWork(database) as uow:
        coverage = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
            exchange_instrument_ids=members,closed_at_ms=close)
        assert len(coverage) == 2 and all(c.episode_version == 0 and c.last_observed_at_ms is None for c in coverage)
        if group == "CPM-RO-001":
            with pytest.raises(sa.exc.DBAPIError,match="lock timeout"):
                async with database.connect() as conn:
                    await conn.execute(sa.text("SET LOCAL lock_timeout='100ms'"))
                    from src.trading_kernel.infrastructure.pg_signal_repository import (
                        PostgresSignalRepository,
                    )
                    await PostgresSignalRepository(conn).lock_exposure_episode(coverage[0].episode_domain_key)
        state = advance_exposure_episode(contract=contract,current=None,detector_status=DetectorStatus.NOT_TRIGGERED,
            occurred_at_ms=None,observed_at_ms=close,exchange_instrument_id=members[1]).current
        await uow.signals.save_exposure_episode(state,expected_version=0)
    with pytest.raises(RuntimeError,match="already consumed"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
                exchange_instrument_ids=members,closed_at_ms=close)
    async with PostgresKernelUnitOfWork(database) as uow:
        later = await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
            exchange_instrument_ids=members,closed_at_ms=close+HOUR)
        assert later[1].episode_version == 1 and later[1].last_observed_at_ms == close
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_owner_static_rollback_stages_exact_frozen_source_without_activation(
    database: AsyncEngine, group: str,
) -> None:
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )

    source, _, _, active_uid = await _exercise_generic_generation(database, group, False,
        durable=True, first_activation=True, natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert control is not None and control.rollback_baseline_id is not None
        assert authority is not None
        baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(control.rollback_baseline_id)
    at = authority.authority.created_at_ms+1
    anchor = (at//(source.spec.cadence_hours*HOUR)+1)*source.spec.cadence_hours*HOUR
    request = ControlMutationRequest(expected_version=control.control_version,reason="owner_static_rollback",
        idempotency_key=f"owner:static:rollback:{group}",owner_identity="owner",now_ms=at)
    for defect in ("version","epoch","baseline","period","step_up","time"):
        with pytest.raises((OwnerControlBlocked,OwnerControlConflict)):
            async with PostgresKernelUnitOfWork(database) as uow:
                await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                    rollback_baseline_id="rollback-baseline:wrong" if defect=="baseline" else baseline.rollback_baseline_id,
                    selection_epoch_id="epoch:wrong" if defect=="epoch" else control.selection_epoch_id,
                    effective_period_anchor_ms=anchor+HOUR if defect=="period" else anchor,
                    request=request.model_copy(update={"expected_version":control.control_version+1 if defect=="version"
                        else control.control_version,"idempotency_key":request.idempotency_key+":"+defect,
                        "now_ms":control.updated_at_ms-1 if defect=="time" else at}),
                    authentication_strength="password" if defect=="step_up" else "totp_step_up")
    @asynccontextmanager
    async def interrupted_static_schedule():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected static authorization rollback")
    with pytest.raises(RuntimeError,match="static authorization rollback"):
        async with interrupted_static_schedule() as uow:
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                effective_period_anchor_ms=anchor,request=request,authentication_strength="totp_step_up")
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_selection_control(group) == control
        assert await uow.owner_controls.get_authorization_by_idempotency_key(request.idempotency_key) is None
    async with database.connect() as conn:
        counts_before = tuple([await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in (
            "brc_strategy_universe_materialization_generations","brc_strategy_entry_vacuums_current",
            "brc_selection_session_authorities","brc_strategy_universe_versions","brc_exchange_commands")])
    async with PostgresKernelUnitOfWork(database) as uow:
        scheduled = await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,request=request,authentication_strength="totp_step_up")
    assert scheduled.selection_mode.value == "dynamic_selection"
    assert scheduled.pending_selection_mode.value == "static_baseline"
    assert scheduled.pending_effective_period_anchor_ms == anchor
    assert scheduled.selection_epoch_id == control.selection_epoch_id
    assert scheduled.rollback_baseline_id == baseline.rollback_baseline_id
    # Scheduling carries an immutable Owner proof but leaves the effective
    # Dynamic authority version unchanged until the runtime transition is due.
    assert scheduled.control_version == control.control_version
    async with PostgresKernelUnitOfWork(database) as uow:
        authorization = await uow.owner_controls.get_authorization_by_idempotency_key(request.idempotency_key)
        assert authorization is not None and authorization.purpose == "selection_mode_change"
        assert authorization.authentication_strength == "totp_step_up"
        assert authorization.target_scope == {"strategy_group_id":group,
            "selection_spec_id":source.spec.selection_spec_id,"target_selection_mode":"static_baseline",
            "rollback_baseline_id":baseline.rollback_baseline_id,"selection_epoch_id":control.selection_epoch_id,
            "effective_period_anchor_ms":anchor}
        assert await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,request=request,authentication_strength="totp_step_up") == scheduled
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        active = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        assert active is not None and active.universe_version_id == active_uid
        assert uow._connection is not None
        scope_id = await uow._connection.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":active_uid})
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        permission = await resolve_selection_observation_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=authority.authority.current_close_proof.current_final_close_time_ms,
            now_ms=at,allow_current_as_birth=True,lock_current=True)
        assert permission.allowed, permission
        # Pending Static cutoff cannot create a new Dynamic Selection Job.
        denied = await uow.instrument_selection.claim_generic_selection_job(selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=control.selection_epoch_id,feature_cutoff_at_ms=anchor,
            worker_id="dynamic-after-static-cutoff",now_ms=anchor+1,lease_duration_ms=1000)
        assert denied is None
    async with database.connect() as conn:
        counts_after = tuple([await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) for table in (
            "brc_strategy_universe_materialization_generations","brc_strategy_entry_vacuums_current",
            "brc_selection_session_authorities","brc_strategy_universe_versions","brc_exchange_commands")])
        assert counts_after == counts_before
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),
            {"uid":baseline.source_event.universe_version_id}) == "retired"
    with pytest.raises(sa.exc.DBAPIError, match="pending Static Owner proof"):
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_strategy_selection_control_current SET pending_authorization_id=:id "
                "WHERE strategy_group_id=:group"),{"id":authority.authority.activation_authorization_id,"group":group})
    with pytest.raises(sa.exc.DBAPIError, match="pending Static Owner proof"):
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_strategy_selection_control_current SET pending_effective_period_anchor_ms=:anchor "
                "WHERE strategy_group_id=:group"),{"anchor":anchor+source.spec.cadence_hours*HOUR,"group":group})
    # An immutable offline Snapshot is not trading authority. Attack the low-level
    # handoff with such a fact at the scheduled Static cutoff.
    shifted = source
    async with PostgresKernelUnitOfWork(database) as uow:
        parent = await uow.instrument_selection.get_generic_snapshot(authority.authority.selection_snapshot_id)
    while shifted.feature_cutoff_at_ms<anchor:
        shifted = next_input(shifted).model_copy(update={"predecessor_snapshot":parent})
        if shifted.feature_cutoff_at_ms==anchor:
            shifted = shifted.model_copy(update={"member_windows":tuple(qualify_window(window,False)
                for window in shifted.member_windows)})
        parent = compute_generic_selection(shifted)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(parent,
                decision_at_ms=shifted.decision_at_ms,source_observed_at_ms=shifted.source_observed_at_ms)
    due_at = parent.effective_from_ms+1
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due_at)):
        refused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericSnapshotRequest(selection_snapshot_id=parent.selection_snapshot_id,
                worker_id="dynamic-fact-at-static-period"),clock_ms=lambda:due_at)
    assert refused.reason_code == "GENERIC_STATIC_ROLLBACK_PENDING", refused
    forbidden_authority = GenericSelectionAuthority(selection_authority_id=f"authority:forbidden-static-period:{group}",
        selection_spec_id=source.spec.selection_spec_id,strategy_group_id=group,selection_epoch_id=control.selection_epoch_id,
        selection_snapshot_id=parent.selection_snapshot_id,authority_sequence=1,
        owner_control_version=authority.authority.owner_control_version,selection_control_version=control.control_version,
        period=build_generic_selection_period(feature_cutoff_at_ms=anchor,cadence_hours=source.spec.cadence_hours),
        current_close_proof=None,membership_freshness=None,
        authority_outcome="VALID_EMPTY",event_binding=AuthorityEventBinding.empty(event_spec_id=source.spec.event_spec_id,
            position_side=source.spec.position_side),effective_from_ms=due_at,created_at_ms=due_at)
    with pytest.raises(sa.exc.DBAPIError,match="Dynamic Authority crosses pending Static period"):
        async with database.begin() as conn:
            await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(forbidden_authority)))
            await conn.execute(sa.insert(selection_authority_event_bindings).values(
                selection_authority_id=forbidden_authority.selection_authority_id,
                **forbidden_authority.event_binding.model_dump(mode="json")))


@pytest.mark.asyncio
@pytest.mark.parametrize("same_request", [False, True])
async def test_concurrent_static_requests_preserve_one_pending_owner_intent(database: AsyncEngine, same_request: bool) -> None:
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )
    source, _, _, _ = await _exercise_generic_generation(database,"CPM-RO-001",False,
        durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert control is not None and authority is not None
    at = authority.authority.created_at_ms+1
    cadence = source.spec.cadence_hours*HOUR
    anchor = (at//cadence+1)*cadence
    async def schedule(key):
        try:
            async with PostgresKernelUnitOfWork(database) as uow:
                return await stage_generic_static_selection_mode(uow,strategy_group_id=source.spec.strategy_group_id,
                    rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                    effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
                    request=ControlMutationRequest(expected_version=control.control_version,
                        reason="concurrent_static_request",idempotency_key=key,owner_identity="owner",now_ms=at))
        except OwnerControlBlocked as exc:
            return str(exc)
    results = await asyncio.gather(schedule("owner:static:concurrent:1"),
        schedule("owner:static:concurrent:1" if same_request else "owner:static:concurrent:2"))
    if same_request:
        assert results[0] == results[1]
    else:
        assert sum(isinstance(result,str) for result in results) == 1
        assert "selection_mode_transition_already_pending" in results
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_owner_authorizations "
            "WHERE target_scope->>'target_selection_mode'='static_baseline'")) == 1
    async with PostgresKernelUnitOfWork(database) as uow:
        stored = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
        assert stored is not None and stored.control_version == control.control_version
        assert stored.pending_selection_mode.value == "static_baseline"
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
async def test_future_static_schedule_preserves_prior_period_continuity(database: AsyncEngine, group: str) -> None:
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )
    source, _, _, uid = await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert control is not None and current is not None and control.rollback_baseline_id is not None
        at = current.authority.created_at_ms+1
        pending_cutoff = (at//HOUR+1)*HOUR
        await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=pending_cutoff,authentication_strength="totp_step_up",
            request=ControlMutationRequest(expected_version=control.control_version,
                reason="future_static_schedule",idempotency_key=f"owner:future:static:{group}",owner_identity="owner",now_ms=at))
    cutoff = source.feature_cutoff_at_ms+HOUR
    close = cutoff+HOUR
    assert cutoff<pending_cutoff
    await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
    template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
    delta = close-template.trigger_candle_close_time_ms
    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
    projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
        universe_version_id=uid,strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,
        closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles)
            for member in source.spec.candidate_ids)).model_copy(update={
                "comparison_transition_revision":current.authority.comparison_transition_revision})
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.strategy_universes.save_comparative_projection(projection)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+1)):
        result = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                period_anchor_ms=cutoff,worker_id="before-static-boundary"),clock_ms=lambda:close+1)
    assert result.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, result
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=pending_cutoff+HOUR+1)):
        refused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                period_anchor_ms=pending_cutoff,worker_id="at-static-boundary"),clock_ms=lambda:pending_cutoff+HOUR+1)
    assert refused.disposition is MaterializationDisposition.BLOCKED
    async with PostgresKernelUnitOfWork(database) as uow:
        scheduled = await uow.instrument_selection.get_selection_control(group)
        assert scheduled is not None and scheduled.pending_selection_mode.value == "static_baseline"
        assert scheduled.control_version == control.control_version


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("failure_case", [None,"timeout","owner_action","pause","pause_staged"])
async def test_due_static_owner_intent_creates_exact_generation_not_selection_snapshot(
    database: AsyncEngine, group: str, failure_case: str | None,
) -> None:
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )
    source, _, _, uid = await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert control is not None and authority is not None
        baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(control.rollback_baseline_id)
        at = authority.authority.created_at_ms+1
        cadence = source.spec.cadence_hours*HOUR
        anchor = (at//cadence+1)*cadence
        scheduled = await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
            request=ControlMutationRequest(expected_version=control.control_version,
                reason="materialize_static_baseline",idempotency_key=f"owner:static:materialize:{group}",owner_identity="owner",now_ms=at))
    request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="static-materializer")
    early = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
        request=request,clock_ms=lambda:anchor+HOUR-1)
    assert early.disposition is MaterializationDisposition.NOT_DUE
    due = anchor+HOUR+1
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)), patch.object(
        GenericStaticMaterializationGeneration,"semantic_digest",new_callable=PropertyMock,
        return_value="sha256:"+"d"*64), pytest.raises(sa.exc.DBAPIError,match="Static Generation source digest mismatch"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_static_materialization_generation(
            GenericStaticMaterializationGeneration.id_for_authorization(scheduled.pending_authorization_id)) is None
    @asynccontextmanager
    async def interrupted_static_generation():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected static Generation rollback")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)), pytest.raises(
        RuntimeError,match="static Generation rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_static_generation,request=request,clock_ms=lambda:due)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)):
        created = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due)
    assert created.disposition is MaterializationDisposition.GENERATION_PENDING, created
    assert created.selection_snapshot_id is None
    async with database.connect() as conn:
        generation = (await conn.execute(sa.text("SELECT * FROM brc_strategy_universe_materialization_generations "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id})).mappings().one()
        events = (await conn.execute(sa.text("SELECT * FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid ORDER BY event_sequence"),{"gid":created.materialization_generation_id})).mappings().all()
        old = (await conn.execute(sa.text("SELECT * FROM brc_materialization_generation_event_baselines "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id})).mappings().one()
        target = (await conn.execute(sa.text("SELECT * FROM brc_strategy_universe_materialization_targets "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id})).mappings().one()
        assert generation["selection_mode"] == "static_baseline" and generation["selection_snapshot_id"] is None
        assert generation["rollback_baseline_id"] == baseline.rollback_baseline_id
        assert generation["selection_epoch_id"] == control.selection_epoch_id
        assert generation["period_anchor_ms"] is None
        assert generation["desired_member_count"] == 1
        assert old["universe_version_id"] == uid
        assert target["expected_member_set_digest"] == baseline.source_event.member_set_digest
        assert len(events) == 1 and events[0]["payload"]["authorization_id"] == scheduled.pending_authorization_id
        assert events[0]["payload"]["effective_period_anchor_ms"] == anchor
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current "
            "WHERE state IN ('OPEN','DRAINING_ENTRY','RECONFIGURING')")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_selection_control(group) == scheduled
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
        loaded = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        assert loaded is not None and loaded.authorization_id == scheduled.pending_authorization_id
        assert loaded.semantic_digest == generation["semantic_digest"]
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)):
        async with PostgresKernelUnitOfWork(database) as uow:
            held_lease = await uow.instrument_selection.claim_generic_static_materialization_generation(
                created.materialization_generation_id,worker_id="static-held-lease",now_ms=due,lease_duration_ms=1000)
    assert held_lease is not None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+1)):
        held_tick = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+1)
    assert held_tick.disposition is MaterializationDisposition.GENERATION_LEASE_HELD
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+1)), pytest.raises(
        SelectionJobConflict,match="lease/version"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.mark_generic_static_materialization_generation_desired(
                created.materialization_generation_id,worker_id="static-held-lease",lease_epoch=held_lease.lease_epoch+1,
                expected_projection_version=held_lease.projection_version,desired_at_ms=due+1)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert not await uow.instrument_selection.release_generic_materialization_generation_lease(created.materialization_generation_id,
            worker_id="static-held-lease",lease_epoch=held_lease.lease_epoch+1)
        assert await uow.instrument_selection.release_generic_materialization_generation_lease(created.materialization_generation_id,
            worker_id="static-held-lease",lease_epoch=held_lease.lease_epoch)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+1)):
        repeated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+1)
    assert repeated.materialization_generation_id == created.materialization_generation_id
    assert repeated.disposition is MaterializationDisposition.GENERATION_DESIRED, repeated
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id}) == 2
    with pytest.raises(sa.exc.DBAPIError,match="source identity is immutable"):
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_strategy_universe_materialization_generations SET semantic_digest=:digest "
                "WHERE materialization_generation_id=:gid"),{"digest":"sha256:"+"e"*64,"gid":created.materialization_generation_id})
    # Rebuild the whole transaction through the real application, then omit its
    # immutable source event. Without the DB guard this previously committed.
    with pytest.raises(sa.exc.DBAPIError,match="Static Generation Owner source"):
        async with database.begin() as conn:
            broken_id = "generation:"+"f"*64
            await conn.execute(sa.insert(strategy_universe_materialization_generations).values(
                **{**dict(generation),"materialization_generation_id":broken_id,"lifecycle_state":"ABANDONED","terminal_at_ms":due}))
            await conn.execute(sa.insert(materialization_generation_event_baselines).values(
                **{**dict(old),"materialization_generation_id":broken_id}))
            await conn.execute(sa.insert(strategy_universe_materialization_targets).values(
                **{**dict(target),"materialization_generation_id":broken_id}))
    @asynccontextmanager
    async def interrupted_static_fence():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected static fence rollback")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+2)), pytest.raises(
        RuntimeError,match="static fence rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_static_fence,request=request,clock_ms=lambda:due+2)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,
            selection_spec_id=source.spec.selection_spec_id) is None
        preserved = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        assert preserved is not None and preserved.lifecycle_state.value == "DESIRED" and preserved.lease_owner is None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+2)):
        fenced = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+2)
    assert fenced.disposition is MaterializationDisposition.WAITING_VACUUM, fenced
    async with PostgresKernelUnitOfWork(database) as uow:
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,
            selection_spec_id=source.spec.selection_spec_id)
        draining = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        assert vacuum is not None and vacuum.state.value == "DRAINING_ENTRY"
        assert vacuum.period_anchor_ms == anchor and vacuum.source_generation_id == created.materialization_generation_id
        assert draining is not None and draining.lifecycle_state.value == "DRAINING_ENTRY"
        assert draining.fenced_at_ms == vacuum.fenced_at_ms == due+2
        assert draining.lease_owner is None
        assert await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id) == ()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+3)):
        drained = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+3)
    assert drained.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, drained
    async with PostgresKernelUnitOfWork(database) as uow:
        prepared = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,
            selection_spec_id=source.spec.selection_spec_id)
        assert prepared is not None and prepared.lifecycle_state.value == "MATERIALIZING"
        assert vacuum is not None and vacuum.state.value == "RECONFIGURING"
        assert vacuum.drained_at_ms == due+3 and vacuum.fenced_at_ms == due+2
        assert prepared.lease_owner is None
        assert await uow.instrument_selection.get_selection_control(group) == scheduled
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
        assert await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id) == ()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+4)):
        warming = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+4)
    assert warming.disposition is MaterializationDisposition.TARGET_WARMING, warming
    async with PostgresKernelUnitOfWork(database) as uow:
        targets = await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)
        assert len(targets) == 1 and targets[0].lifecycle_state.value == "warming"
        target_uid = targets[0].universe_version_id
        assert target_uid not in {uid,baseline.source_event.universe_version_id}
        static_target_members = await uow.strategy_universes.get_members(target_uid)
        assert static_target_members == await uow.strategy_universes.get_members(baseline.source_event.universe_version_id)
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        assert await uow.instrument_selection.get_selection_control(group) == scheduled
    async def pause_static_target(paused_at):
        from src.trading_kernel.application.owner_control import (
            set_strategy_entry_state,
        )
        from src.trading_kernel.domain.owner_control import StrategyEntryState
        async with PostgresKernelUnitOfWork(database) as uow:
            original_generation = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
            original_targets = await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)
            owner = await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_static_warming_target",
                    idempotency_key=f"pause-static-target:{group}",owner_identity="owner",now_ms=paused_at-1),authentication_strength="totp_step_up")
        @asynccontextmanager
        async def interrupted_static_pause():
            async with PostgresKernelUnitOfWork(database) as uow:
                yield uow
                raise RuntimeError("injected static pause commit failure")
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at)), pytest.raises(RuntimeError,match="static pause commit"):
            await coordinate_selection_materialization_once(uow_factory=interrupted_static_pause,request=request,clock_ms=lambda:paused_at)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)==original_generation
            assert await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)==original_targets
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at)), patch(
            "src.trading_kernel.application.coordinate_selection_materialization._abandon_generation_targets",
            new=AsyncMock(return_value=None)), pytest.raises(SelectionJobConflict,match="abandoned targets"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:paused_at)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at)):
            paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:paused_at)
        assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
        async with PostgresKernelUnitOfWork(database) as uow:
            abandoned = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
            paused_targets = await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)
            paused_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
            assert abandoned.lifecycle_state.value=="ABANDONED" and abandoned.terminal_at_ms==paused_at
            assert abandoned.lease_owner is None and abandoned.lease_expires_at_ms is None
            assert paused_targets[0].lifecycle_state.value=="abandoned"
            assert paused_vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
            assert paused_vacuum.fenced_at_ms==vacuum.fenced_at_ms and paused_vacuum.drained_at_ms==vacuum.drained_at_ms
            assert await uow.instrument_selection.get_selection_control(group)==scheduled
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==authority
            assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==uid
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at+1)):
            repeated_pause = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:paused_at+1)
        assert repeated_pause.disposition is MaterializationDisposition.OWNER_PAUSED
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)==abandoned
            paused_owner = await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=paused_owner.control_version,reason="resume_does_not_revive_static_target",
                    idempotency_key=f"resume-static-target:{group}",owner_identity="owner",now_ms=paused_at+2),authentication_strength="totp_step_up")
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at+3)):
            old_callback = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:paused_at+3)
        assert old_callback.disposition is MaterializationDisposition.BLOCKED
        assert old_callback.reason_code=="GENERIC_STATIC_RECOVERY_REQUIRED"
        await _assert_terminal_static_owner_reauthorization(database,group=group,at_ms=paused_at+4)
    if failure_case == "pause":
        await pause_static_target(due+6)
        return
    if failure_case in {"timeout","owner_action"}:
        failed_at = due+2+source.spec.materialization_timeout_ms if failure_case=="timeout" else due+5
        if failure_case=="owner_action":
            await make_warming_ready(database,universe_version_id=target_uid,
                warm_closed_bar_time_ms=anchor+HOUR,valid_until_ms=due+HOUR)
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='owner_action_required',"
                    "blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN "
                    "(SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":target_uid})
        expected_reason = "MATERIALIZATION_TIMEOUT" if failure_case=="timeout" else "CERTIFICATION_OWNER_ACTION_REQUIRED"
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)):
            async with PostgresKernelUnitOfWork(database) as uow:
                failure_lease = await uow.instrument_selection.claim_generic_static_materialization_generation(
                    created.materialization_generation_id,worker_id="static-failure-probe",now_ms=failed_at,lease_duration_ms=30000)
        assert failure_lease is not None
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)), pytest.raises(
            SelectionJobConflict,match="lease/state"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.fail_generic_static_materialization_generation(created.materialization_generation_id,
                    worker_id="static-failure-probe",lease_epoch=failure_lease.lease_epoch+1,
                    expected_projection_version=failure_lease.projection_version,reason_code=expected_reason)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.release_generic_materialization_generation_lease(created.materialization_generation_id,
                worker_id="static-failure-probe",lease_epoch=failure_lease.lease_epoch)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)), patch.object(
            PostgresStrategyUniverseRepository,"abandon",new=AsyncMock(return_value=None)), pytest.raises(
                sa.exc.DBAPIError,match="Static failure requires abandoned targets"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda:failed_at)
        async with PostgresKernelUnitOfWork(database) as uow:
            before_failure = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
            assert before_failure is not None and before_failure.lifecycle_state.value == "MATERIALIZING"
            assert before_failure.lease_owner is None
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)):
            failed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda:failed_at)
        assert failed.disposition is MaterializationDisposition.BLOCKED and failed.reason_code == expected_reason, failed
        async with PostgresKernelUnitOfWork(database) as uow:
            failed_generation = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
            failed_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
            failed_targets = await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)
            assert failed_generation is not None and failed_generation.lifecycle_state.value == "FAILED_CLOSED"
            assert failed_generation.terminal_at_ms == failed_at and failed_generation.lease_owner is None
            assert failed_vacuum is not None and failed_vacuum.state.value == "RECONFIGURING"
            assert failed_vacuum.first_blocker == expected_reason and failed_vacuum.resolved_at_ms is None
            assert failed_vacuum.fenced_at_ms == due+2 and failed_vacuum.drained_at_ms == due+3
            assert len(failed_targets)==1 and failed_targets[0].lifecycle_state.value == "abandoned"
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
            assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
            assert await uow.instrument_selection.get_selection_control(group) == scheduled
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at+1)):
            repeated_failure = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda:failed_at+1)
        assert repeated_failure.reason_code == expected_reason
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events "
                "WHERE materialization_generation_id=:gid AND event_type='FAILED_CLOSED'"),{"gid":created.materialization_generation_id}) == 1
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_versions WHERE lifecycle_state='warming'")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        await _assert_terminal_static_owner_reauthorization(database,group=group,at_ms=failed_at+2,
            fail_retries=1 if failure_case=="timeout" else 0)
        return
    await make_warming_ready(database,universe_version_id=target_uid,warm_closed_bar_time_ms=anchor+HOUR,
        valid_until_ms=due+HOUR)
    @asynccontextmanager
    async def interrupted_static_stage():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected static staging rollback")
    if group in {"MPG-001","MI-001"}:
        template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        shift = anchor+HOUR-template.trigger_candle_close_time_ms
        static_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift})
            for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=target_uid,strategy_group_id=group,
            exchange_instrument_ids=static_target_members,closed_bar_time_ms=anchor+HOUR,
            lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=static_candles)
                for member in static_target_members))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='temporarily_unavailable',"
            "blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN "
            "(SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":target_uid})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+5)):
        retry = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+5)
    assert retry.disposition is MaterializationDisposition.TARGET_WARMING
    assert retry.reason_code == "CERTIFICATION_TEMPORARILY_UNAVAILABLE"
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='eligible',blocker_code=NULL "
            "WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members "
            "WHERE universe_version_id=:uid)"),{"uid":target_uid})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+5)), pytest.raises(
        RuntimeError,match="static staging rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_static_stage,request=request,clock_ms=lambda:due+5)
    async with PostgresKernelUnitOfWork(database) as uow:
        after_failure = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        assert after_failure is not None and after_failure.lifecycle_state.value == "MATERIALIZING"
        assert after_failure.fenced_at_ms == due+2 and after_failure.lease_owner is None
        assert (await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id))[0].lifecycle_state.value == "warming"
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+5)):
        staged = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+5)
    assert staged.disposition is MaterializationDisposition.GENERATION_STAGED, staged
    if failure_case == "pause_staged":
        await pause_static_target(due+7)
        return
    async with PostgresKernelUnitOfWork(database) as uow:
        finalized_staging = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        staged_target = await uow.strategy_universes.get_generation_universe_targets(created.materialization_generation_id)
        assert finalized_staging is not None and finalized_staging.lifecycle_state.value == "STAGED"
        assert finalized_staging.lease_owner is None
        assert len(staged_target) == 1 and staged_target[0].lifecycle_state.value == "staged"
        assert finalized_staging.fenced_at_ms == due+2
        assert await uow.instrument_selection.get_selection_control(group) == scheduled
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)):
        async with PostgresKernelUnitOfWork(database) as uow:
            claim = await uow.instrument_selection.claim_generic_static_materialization_generation(created.materialization_generation_id,
                worker_id="static-proof-preparer",now_ms=due+6,lease_duration_ms=30000)
            assert claim is not None
            with pytest.raises(SelectionJobConflict,match="staged lease"):
                await uow.instrument_selection.prepare_generic_static_activation_proof(created.materialization_generation_id,
                    worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch+1)
            proof = await uow.instrument_selection.prepare_generic_static_activation_proof(created.materialization_generation_id,
                worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            assert proof.materialization_generation_id == created.materialization_generation_id
            assert proof.authorization_id == scheduled.pending_authorization_id
            assert proof.source_selection_authority_id == authority.authority.selection_authority_id
            assert proof.target_event.universe_version_id == target_uid
            assert proof.target_event.member_set_digest == baseline.source_event.member_set_digest
            assert proof.previous_event.universe_version_id == uid
            assert proof.result_selection_control_version == scheduled.control_version+1
            checked = await uow.instrument_selection.require_generic_static_activation_proof(proof,
                worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            assert checked == due+6
            wrong_proof = proof.model_copy(update={"source_selection_authority_id":"authority:forged-static-source"})
            with pytest.raises(SelectionJobConflict,match="proof changed"):
                await uow.instrument_selection.require_generic_static_activation_proof(wrong_proof,
                    worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            if group in {"MPG-001","MI-001"}:
                assert proof.transition_rule == "RECOVERY_TRANSITION"
                assert proof.recovery_reason == "AUTHORITY_GAP"
                assert proof.first_eligible_close_time_ms > proof.prepared_at_ms
                assert proof.comparison_universe_id == baseline.source_event.comparison_universe_id
                assert proof.comparison_transition_revision == authority.authority.comparison_transition_revision+1
            else:
                assert proof.transition_rule == "NORMAL_TRANSITION"
                assert proof.first_eligible_close_time_ms == anchor+HOUR
            from src.trading_kernel.infrastructure.pg_signal_repository import (
                PostgresSignalRepository,
            )
            assert uow._connection is not None
            signal_repo = PostgresSignalRepository(uow._connection)
            assert await signal_repo.selection_authority_was_interrupted(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id,owner_policy_id="policy-main",
                after_ms=authority.authority.created_at_ms,through_ms=due+6)
            assert not await signal_repo.selection_authority_was_interrupted(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id,owner_policy_id="policy-main",
                after_ms=authority.authority.created_at_ms,through_ms=due+6,excluded_entry_vacuum_id=proof.entry_vacuum_id)
            assert await signal_repo.selection_authority_was_interrupted(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id,owner_policy_id="policy-main",
                after_ms=authority.authority.created_at_ms,through_ms=due+6,excluded_entry_vacuum_id="vacuum:wrong")
            assert await uow.instrument_selection.get_selection_control(group) == scheduled
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
            assert uow._connection is not None
            policy_probe = await uow._connection.begin_nested()
            await uow._connection.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=false "
                "WHERE owner_policy_id='policy-main'"))
            with pytest.raises(SelectionJobConflict,match="Policy blocks Entry"):
                await uow.instrument_selection.prepare_generic_static_activation_proof(created.materialization_generation_id,
                    worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            await policy_probe.rollback()
            from src.trading_kernel.domain.exposure_episode import (
                advance_exposure_episode,
            )
            cursor_probe = await uow._connection.begin_nested()
            member_cursor = proof.observation_cursors[0]
            old_episode = await uow.signals.lock_exposure_episode(member_cursor.episode_domain_key)
            observed_close = proof.prepared_at_ms//HOUR*HOUR
            consumption = advance_exposure_episode(contract=strategy_contract_for(source.spec.event_spec_id),
                current=old_episode,detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,
                observed_at_ms=observed_close,exchange_instrument_id=member_cursor.exchange_instrument_id)
            await uow.signals.save_exposure_episode(consumption.current,
                expected_version=0 if old_episode is None else old_episode.projection_version)
            if proof.transition_rule=="NORMAL_TRANSITION":
                with pytest.raises(ValueError,match="consumed"):
                    await uow.instrument_selection.prepare_generic_static_activation_proof(created.materialization_generation_id,
                        worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            else:
                future_proof = await uow.instrument_selection.prepare_generic_static_activation_proof(created.materialization_generation_id,
                    worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
                assert future_proof.first_eligible_close_time_ms>observed_close
            await cursor_probe.rollback()
            assert await uow.instrument_selection.release_generic_materialization_generation_lease(created.materialization_generation_id,
                worker_id="static-proof-preparer",lease_epoch=claim.lease_epoch)
            finalized_staging = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
    @asynccontextmanager
    async def interrupted_static_activation():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            inside = await uow.instrument_selection.get_selection_control(group)
            assert inside is not None and inside.selection_mode.value == "static_baseline"
            raise RuntimeError("injected Static activation commit rollback")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)), pytest.raises(
        RuntimeError,match="Static activation commit rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_static_activation,request=request,clock_ms=lambda:due+6)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_selection_control(group) == scheduled
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
        restored_staging = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        assert restored_staging is not None and restored_staging.lifecycle_state.value == "STAGED" and restored_staging.lease_owner is None
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
    for clock_failure in ("hour_boundary","lease_expiry","materialization_deadline","clock_backwards"):
        reached_post_switch_clock = []
        async def interrupted_commit_clock(repository, *, failure=clock_failure, reached=reached_post_switch_clock):
            inside = await repository.get_selection_control(group)
            if inside is not None and inside.selection_mode.value=="static_baseline":
                reached.append(inside.control_version)
                if failure=="hour_boundary":
                    return (due//HOUR+1)*HOUR
                if failure=="lease_expiry":
                    return due+6+30000
                if failure=="materialization_deadline":
                    return due+2+source.spec.materialization_timeout_ms
                return due+5
            return due+6
        expected_code = "STATIC_ACTIVATION_COMMIT_DEADLINE_EXPIRED" if clock_failure in {
            "lease_expiry","materialization_deadline","hour_boundary"} else "STATIC_ACTIVATION_COMMIT_CROSSED_CLOSE"
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=interrupted_commit_clock), pytest.raises(
            UniverseInstallConflict,match=expected_code):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due+6)
        assert reached_post_switch_clock == [scheduled.control_version+1]
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_selection_control(group) == scheduled
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == authority
            preserved_generation = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
            assert preserved_generation is not None and preserved_generation.lifecycle_state.value=="STAGED"
            assert preserved_generation.lease_owner is None
            assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == uid
            preserved_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id)
            assert preserved_vacuum is not None and preserved_vacuum.state.value=="RECONFIGURING"
            assert preserved_vacuum.fenced_at_ms==due+2 and preserved_vacuum.drained_at_ms==due+3
            for cursor in proof.observation_cursors:
                restored_checkpoint = await uow.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
                assert restored_checkpoint is None or restored_checkpoint.recovery_id!=proof.recovery_id
    actual_execute = sa.ext.asyncio.AsyncConnection.execute
    async def omit_static_cursor_payload(connection, statement, *args, **kwargs):
        if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_universe_materialization_events" and getattr(statement,"is_insert",False):
            params = statement.compile().params
            if params.get("event_type")=="ACTIVE" and "static_activation_proof" in params.get("payload",{}):
                original_payload = params["payload"]
                statement = statement.values(payload={**original_payload,"static_activation_proof":{
                    **original_payload["static_activation_proof"],"observation_cursors":[]}})
        return await actual_execute(connection,statement,*args,**kwargs)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)), patch.object(
        sa.ext.asyncio.AsyncConnection,"execute",new=omit_static_cursor_payload), pytest.raises(
            sa.exc.DBAPIError,match="complete cursor coverage"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due+6)
    if group not in {"MPG-001","MI-001"}:
        actual_cursor_prepare = PostgresInstrumentSelectionRepository.prepare_generic_static_activation_proof
        async def forge_consumed_cursor(repository, gid, *, worker_id, lease_epoch):
            authentic = await actual_cursor_prepare(repository,gid,worker_id=worker_id,lease_epoch=lease_epoch)
            cursor = authentic.observation_cursors[0]
            changed_cursor = cursor.model_copy(update={"episode_version":cursor.episode_version+10,
                "last_observed_at_ms":authentic.first_eligible_close_time_ms-HOUR})
            return type(authentic).model_validate({**authentic.model_dump(),
                "observation_cursors":(changed_cursor,*authentic.observation_cursors[1:])})
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)), patch.object(
            PostgresInstrumentSelectionRepository,"prepare_generic_static_activation_proof",new=forge_consumed_cursor), patch.object(
            PostgresInstrumentSelectionRepository,"require_generic_static_activation_proof",new=AsyncMock(return_value=due+6)), pytest.raises(
                sa.exc.DBAPIError,match="Static NORMAL cursor evidence changed"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due+6)
    if group in {"MPG-001","MI-001"}:
        actual_prepare = PostgresInstrumentSelectionRepository.prepare_generic_static_activation_proof
        async def forge_normal_proof(repository, gid, *, worker_id, lease_epoch):
            authentic = await actual_prepare(repository,gid,worker_id=worker_id,lease_epoch=lease_epoch)
            assert authentic.transition_rule=="RECOVERY_TRANSITION"
            return type(authentic).model_validate({**authentic.model_dump(),"transition_rule":"NORMAL_TRANSITION",
                "recovery_reason":None,"first_eligible_close_time_ms":authentic.prepared_at_ms//HOUR*HOUR})
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)), patch.object(
            PostgresInstrumentSelectionRepository,"prepare_generic_static_activation_proof",new=forge_normal_proof), patch.object(
            PostgresInstrumentSelectionRepository,"require_generic_static_activation_proof",new=AsyncMock(return_value=due+6)), pytest.raises(
                sa.exc.DBAPIError,match="Static NORMAL cannot cross authority gap"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due+6)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)), patch.object(
            PostgresInstrumentSelectionRepository,"initialize_generic_static_recovery_checkpoints",new=AsyncMock(return_value=None)), pytest.raises(
                sa.exc.DBAPIError,match="complete recovery rebase"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due+6)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+6)):
        activated_static = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+6)
    assert activated_static.disposition is MaterializationDisposition.ACTIVE_NEW, activated_static
    async with PostgresKernelUnitOfWork(database) as uow:
        active_static_generation = await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id)
        static_control = await uow.instrument_selection.get_selection_control(group)
        active_static = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        assert active_static_generation is not None and active_static_generation.lifecycle_state.value == "ACTIVE"
        assert active_static_generation.lease_owner is None
        assert active_static is not None and active_static.universe_version_id == target_uid
        assert static_control is not None and static_control.selection_mode.value == "static_baseline"
        assert static_control.selection_epoch_id is None and static_control.pending_authorization_id is None
        assert static_control.control_version == scheduled.control_version+1
        committed_proof = await uow.instrument_selection.get_generic_static_activation_proof(created.materialization_generation_id)
        assert committed_proof is not None
        # Static authority is the existing Control/current-Universe contract,
        # with the transition proof retained in its immutable ACTIVE event.
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
        if group in {"MPG-001","MI-001"}:
            binding = await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id)
            assert binding is not None and binding.source_static_universe_version_id == target_uid
            assert binding.comparison_universe_id == baseline.source_event.comparison_universe_id
            assert binding.comparison_transition_revision == authority.authority.comparison_transition_revision+1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid}) == "retired"
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":baseline.source_event.universe_version_id}) == "retired"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    async with database.connect() as conn:
        static_scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":target_uid})
        committed_event_count = await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+7)):
        repeated_active = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:due+7)
    assert repeated_active.disposition is MaterializationDisposition.ACTIVE_NEW
    assert repeated_active.materialization_generation_id == created.materialization_generation_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid"),{"gid":created.materialization_generation_id}) == committed_event_count
    async with PostgresKernelUnitOfWork(database) as uow:
        static_scope = await uow.signals.get_runtime_scope(static_scope_id)
        assert static_scope is not None
        initial_permission = await resolve_selection_entry_authority(uow,runtime_scope=static_scope,
            birth_selection_authority_id=None,observed_close_time_ms=anchor+HOUR,now_ms=due+6,
            allow_current_as_birth=True,lock_current=True)
        assert initial_permission.allowed is (group not in {"MPG-001","MI-001"})
    if group in {"MPG-001","MI-001"}:
        class StaticObservationMarket:
            def __init__(self, template, close):
                self.template = template
                self.shift = close-template.trigger_candle_close_time_ms
            async def fetch_closed_candles(self, query):
                candles = self.template.candles_1h if query.timeframe=="1h" else self.template.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.shift,"close_time_ms":c.close_time_ms+self.shift})
                    for c in candles)
        outcomes = []
        for step,template in enumerate((mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot(),
            mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot(),
            mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot())):
            close = committed_proof.first_eligible_close_time_ms+step*HOUR
            attempted = close+8000
            await make_warming_ready(database,universe_version_id=target_uid,warm_closed_bar_time_ms=close,
                valid_until_ms=attempted+60000)
            shift = close-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift})
                for c in template.candles_1h)
            projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
                universe_version_id=target_uid,strategy_group_id=group,exchange_instrument_ids=static_target_members,
                closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in static_target_members)
            ).model_copy(update={"comparison_transition_revision":committed_proof.comparison_transition_revision})
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(projection)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=attempted)):
                observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),StaticObservationMarket(template,close),
                    ObservationRequest(runtime_scope_id=static_scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                        trigger_candle_close_time_ms=close,attempted_at_ms=attempted))
            outcomes.append(observed)
        assert outcomes[0].status is ObservationStatus.NO_SIGNAL and outcomes[0].detector_reason=="RECOVERY_REBASE_REQUIRED", outcomes
        assert outcomes[1].status is ObservationStatus.NO_SIGNAL, outcomes
        assert outcomes[2].status is ObservationStatus.SIGNAL_CREATED, outcomes
    restage_at = committed_proof.first_eligible_close_time_ms+3*HOUR
    dynamic_anchor = (restage_at//(source.spec.cadence_hours*HOUR)+1)*source.spec.cadence_hours*HOUR
    async with PostgresKernelUnitOfWork(database) as uow:
        again_dynamic = await stage_generic_dynamic_selection_mode(uow,strategy_group_id=group,
            effective_period_anchor_ms=dynamic_anchor,authentication_strength="totp_step_up",
            request=ControlMutationRequest(expected_version=static_control.control_version,reason="dynamic_after_static_rollback",
                idempotency_key=f"owner:dynamic:second:{group}",owner_identity="owner",now_ms=restage_at))
        assert again_dynamic.selection_epoch_id != control.selection_epoch_id
        assert again_dynamic.rollback_baseline_id == baseline.rollback_baseline_id
        assert again_dynamic.selection_mode.value == "static_baseline"
        permission_before_fence = await resolve_selection_observation_authority(uow,runtime_scope=static_scope,
            birth_selection_authority_id=None,observed_close_time_ms=restage_at,now_ms=restage_at+1,
            allow_current_as_birth=True,lock_current=True)
        assert permission_before_fence.allowed, permission_before_fence
        assert await uow.instrument_selection.get_generic_static_rollback_baseline(baseline.rollback_baseline_id) == baseline
    if group in {"MPG-001","MI-001"}:
        pending_close = restage_at
        attempted = pending_close+8000
        template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        await make_warming_ready(database,universe_version_id=target_uid,warm_closed_bar_time_ms=pending_close,valid_until_ms=attempted+60000)
        shifted_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+pending_close-template.trigger_candle_close_time_ms,
            "close_time_ms":c.close_time_ms+pending_close-template.trigger_candle_close_time_ms}) for c in template.candles_1h)
        pending_projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=target_uid,strategy_group_id=group,exchange_instrument_ids=static_target_members,
            closed_bar_time_ms=pending_close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=shifted_candles) for member in static_target_members)
        ).model_copy(update={"comparison_transition_revision":committed_proof.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(pending_projection)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=attempted)):
            pending_observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),StaticObservationMarket(template,pending_close),
                ObservationRequest(runtime_scope_id=static_scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                    trigger_candle_close_time_ms=pending_close,attempted_at_ms=attempted))
        assert pending_observed.status is ObservationStatus.NO_SIGNAL, pending_observed
    new_input = inputs(group).model_copy(update={"selection_epoch_id":again_dynamic.selection_epoch_id})
    while new_input.feature_cutoff_at_ms<dynamic_anchor:
        new_input = next_input(new_input)
    new_input = new_input.model_copy(update={"predecessor_snapshot":None})
    class NewEpochMarket:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for w in new_input.member_windows)
        async def fetch_generic_selection_klines(self, query):
            return next(w.candles for w in new_input.member_windows if w.exchange_instrument_id==query.exchange_instrument_id)
    selector_tick = dynamic_anchor
    def new_epoch_clock():
        nonlocal selector_tick
        selector_tick += 1
        return selector_tick
    selected_again = await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=NewEpochMarket(),
        request=RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=again_dynamic.selection_epoch_id,period_anchor_ms=dynamic_anchor,worker_id="new-epoch-runner"),
        clock_ms=new_epoch_clock)
    assert selected_again.outcome=="SNAPSHOT_READY", selected_again
    async with PostgresKernelUnitOfWork(database) as uow:
        new_snapshot = await uow.instrument_selection.get_generic_snapshot(selected_again.selection_snapshot_id)
        assert new_snapshot.selection_epoch_id==again_dynamic.selection_epoch_id
        assert new_snapshot.predecessor_snapshot_id is None
        assert new_snapshot.selection_snapshot_id != authority.authority.selection_snapshot_id
        assert await uow.instrument_selection.claim_generic_selection_job(selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=control.selection_epoch_id,feature_cutoff_at_ms=dynamic_anchor,worker_id="stale-epoch-runner",
            now_ms=dynamic_anchor+100,lease_duration_ms=1000) is None
    second_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=new_snapshot.selection_snapshot_id,worker_id="second-dynamic-coordinator")
    second_start = new_snapshot.effective_from_ms+1
    second_active = None
    for offset in range(12):
        second_at = second_start+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=second_at)):
            progressed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=second_request,clock_ms=lambda second_at=second_at:second_at)
        if progressed.materialization_generation_id is not None:
            async with PostgresKernelUnitOfWork(database) as uow:
                second_targets = await uow.strategy_universes.get_generation_universe_targets(progressed.materialization_generation_id)
            if second_targets and second_targets[0].lifecycle_state.value=="warming":
                await make_warming_ready(database,universe_version_id=second_targets[0].universe_version_id,
                    warm_closed_bar_time_ms=new_snapshot.effective_from_ms,valid_until_ms=second_at+HOUR)
                if group in {"MPG-001","MI-001"}:
                    template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                    shift = new_snapshot.effective_from_ms-template.trigger_candle_close_time_ms
                    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
                    projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
                        universe_version_id=second_targets[0].universe_version_id,strategy_group_id=group,
                        exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=new_snapshot.effective_from_ms,
                        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in source.spec.candidate_ids))
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.strategy_universes.save_comparative_projection(projection)
        if progressed.disposition is MaterializationDisposition.ACTIVE_NEW:
            second_active = progressed
            break
    assert second_active is not None, progressed
    async with PostgresKernelUnitOfWork(database) as uow:
        rotated_control = await uow.instrument_selection.get_selection_control(group)
        rotated_authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert rotated_control is not None and rotated_control.selection_mode.value=="dynamic_selection"
        assert rotated_control.selection_epoch_id==again_dynamic.selection_epoch_id
        assert rotated_control.control_version==again_dynamic.control_version+1
        assert rotated_control.rollback_baseline_id==baseline.rollback_baseline_id
        assert rotated_authority is not None and rotated_authority.authority.selection_epoch_id==again_dynamic.selection_epoch_id
        rotated_uid = rotated_authority.authority.event_binding.universe_version_id
        assert rotated_uid not in {uid,target_uid,baseline.source_event.universe_version_id}
        if group in {"MPG-001","MI-001"}:
            rotated_comparison = await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id)
            assert rotated_comparison is not None and rotated_comparison.source_static_universe_version_id is None
            assert rotated_comparison.exchange_instrument_ids==source.spec.candidate_ids
            assert rotated_comparison.comparison_transition_revision==committed_proof.comparison_transition_revision+1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":target_uid}) == "retired"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines WHERE strategy_group_id=:group"),{"group":group}) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    from src.trading_kernel.application.owner_control import set_strategy_entry_state
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    pause_base_at = second_at
    if group in {"CPM-RO-001","BRF2-001"}:
        pause_base_at = await _issue_second_dynamic_noncomparative_trade(database,group=group)
    else:
        pause_base_at = await _issue_second_dynamic_comparative_trade(database,group=group)
        async with PostgresKernelUnitOfWork(database) as uow:
            rotated_authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    async with PostgresKernelUnitOfWork(database) as uow:
        before_pause = await uow.owner_controls.get_strategy_control(group)
        assert before_pause is not None
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=before_pause.control_version,
                reason="pause_static_materialization",idempotency_key=f"owner:pause:static:{group}",
                owner_identity="owner",now_ms=pause_base_at+1),authentication_strength="totp_step_up")
    pause_at = pause_base_at+2
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=pause_at)):
        paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:pause_at)
    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with PostgresKernelUnitOfWork(database) as uow:
        assert (await uow.owner_controls.get_strategy_control(group)).entry_state is StrategyEntryState.PAUSED
        assert await uow.instrument_selection.get_generic_static_materialization_generation(created.materialization_generation_id) == active_static_generation
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == rotated_authority
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id == rotated_uid


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("first_activation", [False, True])
async def test_generic_empty_snapshot_coordinator_commits_negative_authority(database: AsyncEngine, group: str, first_activation: bool) -> None:
    source = inputs(group)
    source = source.model_copy(update={"member_windows":tuple(qualify_window(w,False) for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=source.decision_at_ms,source_observed_at_ms=source.source_observed_at_ms)
        installed = await install_strategy_universe(uow,UniverseInstallRequest(event_spec_id=source.spec.event_spec_id,
            runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",exchange_instrument_ids=source.spec.candidate_ids[:1],
            installed_at_ms=CUTOFF-1))
    assert installed.universe is not None
    uid = installed.universe.universe_version_id
    # Existing active Static scope is a migration/runtime prerequisite, not a
    # claim that the new Selector activated it.
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:now WHERE universe_version_id=:uid"),{"uid":uid,"now":CUTOFF})
        await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,warm_closed_bar_time_ms=:now,warm_completed_at_ms=:now,warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"),
            {"uid":uid,"now":CUTOFF,"valid":snapshot.expires_at_ms,"digest":installed.universe.semantic_digest})
        await conn.execute(sa.text("INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:now)"),
            {"event":source.spec.event_spec_id,"uid":uid,"digest":installed.universe.semantic_digest,"now":CUTOFF})
    await enable_epoch(database,group,pending=first_activation)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="empty-coordinator")
    results = []
    for tick in range(4):
        if tick == 1:
            async with PostgresKernelUnitOfWork(database) as uow:
                with patch.object(uow.instrument_selection,"get_snapshot_disposition",new=AsyncMock(side_effect=AssertionError("Generic drain must not read SOR Snapshot"))):
                    drained = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
                        strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,now_ms=snapshot.effective_from_ms+2))
                assert drained.status == VacuumDrainStatus.ENTRY_DRAINED
                assert await uow.instrument_selection.get_current_generic_authority(snapshot.selection_spec_id) is None
        if first_activation and tick == 1:
            async with PostgresKernelUnitOfWork(database) as uow:
                pending = await uow.instrument_selection.get_selection_control(group)
            with pytest.raises(sa.exc.DBAPIError,match="atomic authorized mode transition"), patch.object(
                PostgresInstrumentSelectionRepository,"activate_pending_selection_mode",new=AsyncMock(return_value=pending)):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                    request=request,clock_ms=lambda:snapshot.effective_from_ms+2)

            @asynccontextmanager
            async def fail_empty_commit():
                async with PostgresKernelUnitOfWork(database) as uow:
                    yield uow
                    control = await uow.instrument_selection.get_selection_control(group)
                    assert control is not None and control.selection_mode.value == "dynamic_selection"
                    raise RuntimeError("empty commit interrupted")

            with pytest.raises(RuntimeError,match="empty commit interrupted"):
                await coordinate_selection_materialization_once(uow_factory=fail_empty_commit,
                    request=request,clock_ms=lambda:snapshot.effective_from_ms+2)
            await database.dispose()
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.get_selection_control(group) == pending
                assert await uow.instrument_selection.get_current_generic_authority(snapshot.selection_spec_id) is None
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=snapshot.selection_spec_id)
                assert vacuum is not None and vacuum.state.value == "DRAINING_ENTRY"
        results.append(await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda tick=tick:snapshot.effective_from_ms+tick+1))
    assert results[-1].disposition == MaterializationDisposition.VALID_EMPTY
    assert results[-1].selection_authority_id == results[-2].selection_authority_id
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid"),{"uid":uid})
    class NoMarket:
        async def fetch_closed_candles(self, request):
            raise AssertionError("VALID_EMPTY must reject before market reads")
    observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),NoMarket(),
        ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=snapshot.effective_from_ms,attempted_at_ms=snapshot.effective_from_ms+10))
    assert observed.status == ObservationStatus.INVALID
    assert observed.detector_reason == "selection_owner_or_policy_blocked"
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true WHERE owner_policy_id='policy-main'"))
    observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),NoMarket(),
        ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=snapshot.effective_from_ms,attempted_at_ms=snapshot.effective_from_ms+11))
    assert observed.status == ObservationStatus.INVALID
    assert observed.detector_reason == "selection_valid_empty"
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        rejected = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=snapshot.effective_from_ms,
            now_ms=snapshot.effective_from_ms+12,allow_current_as_birth=False,lock_current=True)
        assert not rejected.allowed and rejected.reason_code == "selection_valid_empty"
        expired = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=snapshot.expires_at_ms,
            now_ms=snapshot.expires_at_ms,allow_current_as_birth=False,lock_current=True)
        assert not expired.allowed and expired.reason_code == "selection_authority_missing_or_expired"
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(snapshot.selection_spec_id)
        assert current is not None and current.authority.blocks_new_entry
        assert current.projection_version == 1
        control = await uow.instrument_selection.get_selection_control(group)
        assert control is not None and control.selection_mode.value == "dynamic_selection"
        assert control.control_version == 2 + int(first_activation)
        assert control.pending_authorization_id is None and control.pending_selection_mode is None
        assert current.authority.selection_control_version == control.control_version
        assert current.authority.activation_authorization_id == ("owner:first:"+group if first_activation else None)
    async with database.connect() as conn:
        for table in ("brc_strategy_universe_materialization_generations","brc_trade_tickets","brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
        assert await conn.scalar(sa.text("SELECT state FROM brc_strategy_entry_vacuums_current")) == "VALID_EMPTY"


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_empty_authority_persists_without_positive_grant(database: AsyncEngine, group: str) -> None:
    source = inputs(group)
    source = source.model_copy(update={"member_windows":tuple(qualify_window(w,False) for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    assert not snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=source.decision_at_ms,source_observed_at_ms=source.source_observed_at_ms)
    authority = GenericSelectionAuthority(selection_authority_id="authority:empty:"+group,
        selection_spec_id=source.spec.selection_spec_id,strategy_group_id=group,selection_epoch_id=snapshot.selection_epoch_id,
        selection_snapshot_id=snapshot.selection_snapshot_id,authority_sequence=1,owner_control_version=1,selection_control_version=2,
        period=build_generic_selection_period(feature_cutoff_at_ms=CUTOFF,cadence_hours=source.spec.cadence_hours),
        authority_outcome="VALID_EMPTY",event_binding=AuthorityEventBinding.empty(event_spec_id=source.spec.event_spec_id,position_side=source.spec.position_side),
        current_close_proof=None,membership_freshness=None,effective_from_ms=snapshot.effective_from_ms+1,created_at_ms=snapshot.effective_from_ms+1)
    for changes, reason in (({"current_close_proof":{}},"Generic VALID_EMPTY"),
                            ({"expires_at_ms":authority.expires_at_ms+HOUR},"Generic Authority period"),
                            ({"authority_outcome":"NO_CHANGE"},"Generic normal Authority proof"),
                            ({"selection_epoch_id":"wrong-epoch"},"Generic VALID_EMPTY")):
        with pytest.raises(sa.exc.DBAPIError,match=reason):
            async with database.begin() as conn:
                await conn.execute(sa.insert(selection_session_authorities).values(**{**generic_authority_storage_values(authority),**changes}))
    nonempty_source = next_input(inputs(group)).model_copy(update={"predecessor_snapshot":snapshot})
    nonempty = compute_generic_selection(nonempty_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(nonempty,decision_at_ms=nonempty_source.decision_at_ms,source_observed_at_ms=nonempty_source.source_observed_at_ms)
    with pytest.raises(sa.exc.DBAPIError,match="Generic VALID_EMPTY"):
        async with database.begin() as conn:
            await conn.execute(sa.insert(selection_session_authorities).values(**{
                **generic_authority_storage_values(authority),"selection_snapshot_id":nonempty.selection_snapshot_id,
                "period_anchor_ms":nonempty.feature_cutoff_at_ms,"decision_boundary_ms":nonempty.effective_from_ms,
                "expires_at_ms":nonempty.expires_at_ms,"effective_from_ms":nonempty.effective_from_ms+1,
                "created_at_ms":nonempty.effective_from_ms+1}))
    await enable_epoch(database,group)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
    vacuum = StrategyEntryVacuum(entry_vacuum_id="vacuum:empty:"+group,strategy_group_id=group,
        selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=CUTOFF,source_generation_id=None,
        state="OPEN",fenced_at_ms=snapshot.effective_from_ms,drained_at_ms=None,resolved_at_ms=None,
        first_blocker="NO_SELECTION_READY_MEMBERS",projection_version=1)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.open_valid_empty_intent_vacuum(vacuum,selection_snapshot_id=snapshot.selection_snapshot_id)
        vacuum = await uow.instrument_selection.mark_entry_vacuum_draining(vacuum,started_at_ms=snapshot.effective_from_ms)
    with pytest.raises(SelectionJobConflict,match="current version"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum.entry_vacuum_id,
                expected_vacuum_version=vacuum.projection_version,expected_current_version=99)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id=:group"),{"group":group})
    with pytest.raises(SelectionJobConflict,match="Owner control"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum.entry_vacuum_id,
                expected_vacuum_version=vacuum.projection_version,expected_current_version=None)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='enabled' WHERE strategy_group_id=:group"),{"group":group})
        await conn.execute(sa.text("CREATE FUNCTION reject_empty_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected empty current failure'; END; $$"))
        await conn.execute(sa.text("CREATE TRIGGER reject_empty_test BEFORE INSERT ON brc_selection_authority_current FOR EACH ROW EXECUTE FUNCTION reject_empty_test()"))
    with pytest.raises(sa.exc.DBAPIError,match="injected empty current failure"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum.entry_vacuum_id,
                expected_vacuum_version=vacuum.projection_version,expected_current_version=None)
    async with database.begin() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 0
        assert await conn.scalar(sa.text("SELECT state FROM brc_strategy_entry_vacuums_current")) == "DRAINING_ENTRY"
        await conn.execute(sa.text("DROP TRIGGER reject_empty_test ON brc_selection_authority_current"))
        await conn.execute(sa.text("DROP FUNCTION reject_empty_test()"))
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum.entry_vacuum_id,
            expected_vacuum_version=vacuum.projection_version,expected_current_version=None)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.commit_generic_valid_empty(authority,entry_vacuum_id=vacuum.entry_vacuum_id,
            expected_vacuum_version=vacuum.projection_version,expected_current_version=None)
    async with database.connect() as conn:
        row = (await conn.execute(sa.select(selection_session_authorities))).mappings().one()
        bindings = tuple((await conn.execute(sa.select(selection_authority_event_bindings))).mappings())
        assert generic_authority_from_storage(row,spec=source.spec,event_bindings=bindings) == authority
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_authority_current")) == 1
        assert await conn.scalar(sa.text("SELECT state FROM brc_strategy_entry_vacuums_current")) == "VALID_EMPTY"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    with pytest.raises(sa.exc.DBAPIError,match="exact homogeneous Spec Event binding shape"):
        async with database.begin() as conn:
            await conn.execute(sa.insert(selection_authority_event_bindings).values(
                selection_authority_id=authority.selection_authority_id,
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",position_side="long",
                grant_state="EMPTY",universe_version_id=None,
                member_set_digest=authority.event_binding.member_set_digest))
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_authority_event_bindings "
            "WHERE selection_authority_id=:id"),{"id":authority.selection_authority_id}) == 1
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id,for_update=True)
        assert current is not None and current.authority == authority and current.projection_version == 1
    async with database.connect() as conn:
        await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        readonly = await PostgresInstrumentSelectionRepository(conn).get_current_generic_authority(source.spec.selection_spec_id)
        assert readonly == current


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_vacuum_roundtrips_hourly_period(database: AsyncEngine, group: str) -> None:
    spec = inputs(group).spec
    vacuum = StrategyEntryVacuum(entry_vacuum_id="vacuum:"+group, strategy_group_id=group,
        selection_spec_id=spec.selection_spec_id, period_anchor_ms=CUTOFF,
        source_generation_id=None,state="OPEN",fenced_at_ms=CUTOFF+HOUR+1,
        drained_at_ms=None,resolved_at_ms=None,first_blocker="OWNER_PAUSED",projection_version=1)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.open_owner_paused_entry_vacuum(vacuum)
    async with PostgresKernelUnitOfWork(database) as uow:
        loaded = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=spec.selection_spec_id)
        assert loaded is not None and loaded.period_anchor_ms == CUTOFF
        assert loaded.blocks_new_entry and not loaded.blocks_existing_ticket_lifecycle


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
@pytest.mark.parametrize("initial", [None, DetectorStatus.NOT_TRIGGERED, DetectorStatus.TRIGGERED])
async def test_comparison_checkpoint_persists_without_fabricating_episode(
    database: AsyncEngine, group: str, initial: DetectorStatus | None,
) -> None:
    spec = inputs(group).spec
    contract = strategy_contract_for(spec.event_spec_id)
    member = spec.candidate_ids[0]
    digest = canonical_digest({"exchange_instrument_ids": spec.candidate_ids})
    key = build_episode_domain_key(event_spec_id=spec.event_spec_id,
        exchange_instrument_id=member, position_side=spec.position_side)
    async with database.begin() as conn:
        await conn.execute(sa.text("INSERT INTO brc_comparison_binding_current VALUES(:event,:cid,1,NULL)"),
            {"event": spec.event_spec_id, "cid": "comparison:"+digest[7:]})
    if initial is not None:
        old = advance_exposure_episode(contract=contract, current=None, detector_status=initial,
            occurred_at_ms=500 if initial is DetectorStatus.TRIGGERED else None,
            observed_at_ms=500, exchange_instrument_id=member)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.signals.save_exposure_episode(old.current, expected_version=0)
    last_episode_id = None
    for revision in (1, 2):
        if revision == 2:
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_comparison_binding_current SET comparison_transition_revision=2 WHERE event_spec_id=:event"), {"event":spec.event_spec_id})
        for step, status in enumerate((DetectorStatus.TRIGGERED, DetectorStatus.NOT_TRIGGERED, DetectorStatus.TRIGGERED)):
            close = ((revision-1)*3 + step+1)*HOUR
            async with PostgresKernelUnitOfWork(database) as uow:
                current = await uow.signals.lock_exposure_episode(key)
                checkpoint = await uow.signals.get_comparison_episode_checkpoint(key)
                transition = advance_comparison_bound_exposure_episode(
                    contract=contract, current_episode=current, current_checkpoint=checkpoint,
                    detector_status=status, occurred_at_ms=close if status is DetectorStatus.TRIGGERED else None,
                    observed_at_ms=close, exchange_instrument_id=member,
                    comparison_binding_digest=digest, comparison_transition_revision=revision)
                if revision == 2 and step == 0:
                    stale_transition = transition
                    stale_episode_version = current.projection_version
                    stale_checkpoint_version = checkpoint.projection_version
                await uow.signals.save_comparison_episode_transition(
                    transition, event_spec_id=spec.event_spec_id, exchange_instrument_id=member,
                    position_side=spec.position_side,
                    expected_episode_version=0 if current is None else current.projection_version,
                    expected_checkpoint_version=0 if checkpoint is None else checkpoint.projection_version)
            # A new transaction stands in for restarting the Observation process.
            async with PostgresKernelUnitOfWork(database) as uow:
                recovered = await uow.signals.get_comparison_episode_checkpoint(key)
                assert recovered == transition.checkpoint
                persisted = await uow.signals.lock_exposure_episode(key)
            assert persisted is not None
            if step == 0:
                assert not transition.signal_eligible
                with pytest.raises(RuntimeError,match="already consumed"):
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.signals.lock_generic_close_coverage(event_spec_id=spec.event_spec_id,
                            exchange_instrument_ids=(member,),closed_at_ms=close)
                assert persisted.exposure_episode_id == (None if current is None else current.exposure_episode_id)
                if current is None:
                    assert persisted.state == "comparison_rebase_required"
            elif step == 1:
                assert persisted.state == "armed" and persisted.exposure_episode_id is None
            else:
                assert transition.signal_eligible and persisted.exposure_episode_id is not None
                assert persisted.exposure_episode_id != last_episode_id
                last_episode_id = persisted.exposure_episode_id
    with pytest.raises(RuntimeError, match="version changed"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.signals.save_comparison_episode_transition(stale_transition,
                event_spec_id=spec.event_spec_id, exchange_instrument_id=member, position_side=spec.position_side,
                expected_episode_version=stale_episode_version, expected_checkpoint_version=stale_checkpoint_version)
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current")) == 1
        for table in ("brc_signal_events", "brc_trade_tickets", "brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_snapshot_exact_roundtrip_and_idempotent_handoff(database: AsyncEngine, group: str) -> None:
    source = inputs(group)
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    async with PostgresKernelUnitOfWork(database) as uow:
        loaded = await uow.instrument_selection.get_generic_snapshot(snapshot.selection_snapshot_id)
        assert loaded == snapshot
        assert loaded.semantic_digest == snapshot.semantic_digest
        await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    static = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="static-handoff"),
        clock_ms=lambda:snapshot.effective_from_ms+1)
    assert static.disposition == MaterializationDisposition.STATIC_BASELINE
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_member_decisions")) == 24
        for table in ("brc_strategy_universe_materialization_generations", "brc_selection_session_authorities", "brc_trade_tickets", "brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0


def next_input(source: GenericSelectionInput) -> GenericSelectionInput:
    step = source.spec.cadence_hours * HOUR
    return source.model_copy(update={
        "feature_cutoff_at_ms": source.feature_cutoff_at_ms + step,
        "decision_at_ms": source.decision_at_ms + step,
        "source_observed_at_ms": source.source_observed_at_ms + step,
        "committed_at_ms": source.committed_at_ms + step,
        "member_windows": tuple(shift_window(member, step) for member in source.member_windows),
        "predecessor_snapshot": compute_generic_selection(source),
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["none", "missing", "wrong_digest", "wrong_epoch", "stale", "forged_retained"])
async def test_snapshot_predecessor_is_exact_latest_desired_not_active_universe(database: AsyncEngine, defect: str) -> None:
    first_source = inputs("MPG-001")
    second_source = next_input(first_source)
    first = compute_generic_selection(first_source)
    second = compute_generic_selection(second_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(first, decision_at_ms=first_source.decision_at_ms, source_observed_at_ms=first_source.source_observed_at_ms)
    if defect == "none":
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(second, decision_at_ms=second_source.decision_at_ms, source_observed_at_ms=second_source.source_observed_at_ms)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_snapshot(second.selection_snapshot_id) == second
        return
    payload = second.model_dump(mode="python")
    if defect == "missing":
        payload["predecessor_snapshot_id"] = "selection:missing"
    elif defect == "wrong_digest":
        payload["predecessor_member_digest"] = "sha256:" + "f" * 64
    elif defect == "wrong_epoch":
        from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
        payload["selection_epoch_id"] = "epoch:2"
        payload["selection_snapshot_id"] = "selection:" + canonical_digest({"spec": second.selection_spec_id, "epoch": "epoch:2", "cutoff": second.feature_cutoff_at_ms})[7:]
    elif defect == "stale":
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(second, decision_at_ms=second_source.decision_at_ms, source_observed_at_ms=second_source.source_observed_at_ms)
        second_source = next_input(second_source)
        payload = compute_generic_selection(second_source).model_dump(mode="python")
        payload["predecessor_snapshot_id"] = first.selection_snapshot_id
        payload["predecessor_member_digest"] = first.member_set_digest
    else:
        payload["members"][0]["retained"] = False
    forged = type(second).model_validate(payload)
    with pytest.raises(SelectionJobConflict, match="predecessor|retention"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(forged, decision_at_ms=second_source.decision_at_ms, source_observed_at_ms=second_source.source_observed_at_ms)


@pytest.mark.asyncio
async def test_conflicting_same_period_writers_commit_exactly_one_snapshot(database: AsyncEngine) -> None:
    source = inputs("CPM-RO-001")
    other = source.model_copy(update={"member_windows": tuple(qualify_window(m, False) for m in source.member_windows)})

    async def persist(candidate: GenericSelectionInput) -> str:
        try:
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.save_generic_snapshot(compute_generic_selection(candidate), decision_at_ms=candidate.decision_at_ms, source_observed_at_ms=candidate.source_observed_at_ms)
            return "committed"
        except SelectionJobConflict:
            return "conflict"

    assert sorted(await asyncio.gather(persist(source), persist(other))) == ["committed", "conflict"]
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 1
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_member_decisions)) == 24


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["wrong_epoch", "wrong_digest", "rank", "count", "window", "family", "retained", "late_source"])
async def test_direct_sql_cannot_bypass_snapshot_family_and_lineage_constraints(database: AsyncEngine, defect: str) -> None:
    source = inputs("MPG-001")
    first = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(first, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    async with database.connect() as conn:
        parent = dict((await conn.execute(sa.select(instrument_selection_snapshots))).mappings().one())
        members = [dict(row) for row in (await conn.execute(sa.select(instrument_selection_member_decisions))).mappings()]
    parent.update(selection_snapshot_id="selection:sql-child", predecessor_snapshot_id=first.selection_snapshot_id, predecessor_member_digest=first.member_set_digest)
    for key in ("period_anchor_ms", "decision_at_ms", "feature_cutoff_at_ms", "eligibility_not_before_ms", "expires_at_ms", "source_observed_at_ms", "created_at_ms"):
        parent[key] += HOUR
    for member in members:
        member.update(selection_snapshot_id=parent["selection_snapshot_id"], member_decision_id=member["member_decision_id"] + ":next", retained=member["selected"])
        for key in ("period_anchor_ms", "feature_cutoff_at_ms", "input_window_start_ms", "input_window_end_ms"):
            member[key] += HOUR
    if defect == "wrong_epoch": parent["selection_epoch_id"] = "epoch:2"
    elif defect == "wrong_digest": parent["predecessor_member_digest"] = "sha256:" + "f" * 64
    elif defect == "rank": members[0]["stable_rank"] = members[1]["stable_rank"]
    elif defect == "count": parent["selected_count"] -= 1
    elif defect == "window": members[0]["input_window_start_ms"] -= HOUR
    elif defect == "family": members[0]["selection_family"] = "sor_dynamic_v0"
    elif defect == "retained":
        next(m for m in members if m["selected"])["retained"] = False
    else: parent["source_observed_at_ms"] = parent["created_at_ms"] + 1
    with pytest.raises(sa.exc.DBAPIError):
        async with database.begin() as conn:
            await conn.execute(sa.insert(instrument_selection_snapshots).values(**parent))
            await conn.execute(sa.insert(instrument_selection_member_decisions), members)
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 1


@pytest.mark.asyncio
async def test_generic_snapshot_empty_preserves_qualification_without_backfill(database: AsyncEngine) -> None:
    source = inputs("CPM-RO-001")
    source = source.model_copy(update={"member_windows": tuple(
        qualify_window(member, index >= 16) for index, member in enumerate(source.member_windows)
    )})
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    async with PostgresKernelUnitOfWork(database) as uow:
        loaded = await uow.instrument_selection.get_generic_snapshot(snapshot.selection_snapshot_id)
        assert loaded.selected_members == ()
        assert loaded.ready_count == 8
        assert loaded == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("feature", ["-0", "1E+5", "1.1234567890123456789012345678901234567"])
async def test_pg_decimal_representation_does_not_change_semantic_identity(database: AsyncEngine, feature: str) -> None:
    source = inputs("CPM-RO-001")
    snapshot = compute_generic_selection(source)
    snapshot = type(snapshot).model_validate(snapshot.model_copy(update={"members": tuple(
        member.model_copy(update={"feature_value": Decimal(feature)}) for member in snapshot.members
    )}).model_dump(mode="python"))
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    async with PostgresKernelUnitOfWork(database) as uow:
        loaded = await uow.instrument_selection.get_generic_snapshot(snapshot.selection_snapshot_id)
        assert loaded == snapshot
        assert loaded.semantic_digest == snapshot.semantic_digest


async def enable_epoch(database: AsyncEngine, group: str, epoch: str = "epoch:1", *, pending=False, pending_anchor_ms=CUTOFF) -> None:
    # Isolated repository prerequisite, not an Owner API/activation acceptance.
    async with database.begin() as conn:
        row = (await conn.execute(sa.select(strategy_selection_control_current).where(
            strategy_selection_control_current.c.strategy_group_id == group,
        ))).mappings().one()
        if row["selection_mode"] == "dynamic_selection":
            raise AssertionError("Epoch rotation fixtures must use formal Owner Static/Dynamic transitions")
        auth_id = "owner:first:"+group if epoch == "epoch:1" else f"owner:first:{group}:{epoch}"
        await conn.execute(sa.text("INSERT INTO brc_owner_authorizations VALUES (:id,'selection_mode_change','test-owner','totp_step_up',:digest,CAST(:scope AS jsonb),:id,:at)"),
            {"id":auth_id,"digest":"sha256:"+"8"*64,"at":pending_anchor_ms-1,
             "scope":json.dumps({"strategy_group_id":group,"selection_spec_id":inputs(group).spec.selection_spec_id,
                 "target_selection_mode":"dynamic_selection","effective_period_anchor_ms":pending_anchor_ms,
                 "selection_epoch_id":epoch})})
        await conn.execute(sa.update(strategy_selection_control_current).where(
            strategy_selection_control_current.c.strategy_group_id == group,
        ).values(selection_mode="static_baseline",pending_selection_mode="dynamic_selection",
            pending_effective_period_anchor_ms=pending_anchor_ms,pending_authorization_id=auth_id,
            selection_epoch_id=epoch,control_version=int(row["control_version"])+int(pending)))
        if not pending:
            await conn.execute(sa.update(strategy_selection_control_current).where(
                strategy_selection_control_current.c.strategy_group_id == group,
            ).values(selection_mode="dynamic_selection",pending_selection_mode=None,
                pending_effective_period_anchor_ms=None,pending_authorization_id=None,
                control_version=int(row["control_version"])+1))


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
@pytest.mark.parametrize("installed", [True,False])
async def test_generic_runner_short_circuits_static_or_uninstalled_without_artifacts(
    head_template_engine: AsyncEngine, group: str, installed: bool,
) -> None:
    database = head_template_engine
    source = inputs(group)
    async with PostgresKernelUnitOfWork(database) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id="selector-short-circuit",
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=CUTOFF-HOUR))
        if installed:
            await uow.instrument_selection.install_generic_spec(source.spec,installed_at_ms=CUTOFF-HOUR,
                certification=SpecNumericInstallationEvidence(selection_spec_id=source.spec.selection_spec_id,
                    algorithm_semantic_digest=source.spec.algorithm_semantic_digest,
                    checked_cutoffs=463 if source.spec.cadence_hours==4 else 1852,mismatch_count=0,source_archive_count=96,
                    reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",common_numeric_authority="PASS",sor_golden="PASS",spec_cert="PASS"))
    class NetworkForbidden:
        def __getattr__(self,name):
            raise AssertionError(f"Static/uninstalled Selector requested market I/O: {name}")
    result = await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
        market_source=NetworkForbidden(),request=RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id="epoch:inactive",period_anchor_ms=CUTOFF,worker_id="inactive-selector"),clock_ms=lambda:CUTOFF+1)
    assert result.outcome==("NOT_DUE" if installed else "NOT_INSTALLED"),result
    async with database.connect() as conn:
        for table in ("brc_instrument_selection_jobs_current","brc_instrument_selection_attempts",
            "brc_instrument_selection_snapshots","brc_instrument_selection_member_decisions",
            "brc_strategy_universe_materialization_generations","brc_strategy_entry_vacuums_current",
            "brc_trade_tickets","brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}"))==0


@pytest.mark.asyncio
async def test_static_generic_selection_claim_short_circuits_without_job(database: AsyncEngine) -> None:
    source = inputs("MPG-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF, worker_id="selection:test", now_ms=CUTOFF + 1, lease_duration_ms=1000,
        ) is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_jobs_current)) == 0


@pytest.mark.asyncio
async def test_generic_static_control_cannot_jump_directly_to_dynamic(database: AsyncEngine) -> None:
    with pytest.raises(sa.exc.DBAPIError, match="Generic activation requires pending Owner epoch"):
        async with database.begin() as conn:
            await conn.execute(sa.text("""
                UPDATE brc_strategy_selection_control_current
                SET selection_mode='dynamic_selection',selection_epoch_id='epoch:rogue',
                    control_version=control_version+1
                WHERE strategy_group_id='MPG-001'
            """))
    async with database.connect() as conn:
        row = (await conn.execute(sa.text(
            "SELECT selection_mode,selection_epoch_id,pending_selection_mode "
            "FROM brc_strategy_selection_control_current WHERE strategy_group_id='MPG-001'"
        ))).mappings().one()
        assert row["selection_mode"] == "static_baseline"
        assert row["selection_epoch_id"] is None
        assert row["pending_selection_mode"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_first_activation_stages_exact_owner_epoch_without_runtime_work(
    database: AsyncEngine, group: str,
) -> None:
    source = inputs(group)
    await _install_static_selection_source(database,group)
    request = ControlMutationRequest(
        expected_version=1,reason="first_generic_shadow_live",
        idempotency_key=f"owner:generic:first:{group}",owner_identity="owner",
        now_ms=CUTOFF-1,
    )
    with pytest.raises(OwnerControlBlocked, match="step_up"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await stage_generic_dynamic_selection_mode(
                uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
                request=request,authentication_strength="session",
            )
    with pytest.raises(OwnerControlBlocked, match="next"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await stage_generic_dynamic_selection_mode(
                uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF+HOUR,
                request=request,authentication_strength="totp_step_up",
            )
    async with PostgresKernelUnitOfWork(database) as uow:
        staged = await stage_generic_dynamic_selection_mode(
            uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=request,authentication_strength="totp_step_up",
        )
    assert staged.selection_mode.value == "static_baseline"
    assert staged.pending_selection_mode.value == "dynamic_selection"
    assert staged.pending_effective_period_anchor_ms == CUTOFF
    assert staged.selection_epoch_id is not None
    async with PostgresKernelUnitOfWork(database) as uow:
        authorization = await uow.owner_controls.get_authorization_by_idempotency_key(
            request.idempotency_key
        )
        assert authorization is not None
        assert authorization.purpose == "selection_mode_change"
        assert authorization.authentication_strength == "totp_step_up"
        assert staged.selection_epoch_id == authorization.target_scope["selection_epoch_id"]
        assert authorization.target_scope == {
            "strategy_group_id":group,
            "selection_spec_id":source.spec.selection_spec_id,
            "target_selection_mode":"dynamic_selection",
            "effective_period_anchor_ms":CUTOFF,
            "selection_epoch_id":staged.selection_epoch_id,
        }
        repeated = await stage_generic_dynamic_selection_mode(
            uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=request,authentication_strength="totp_step_up",
        )
        assert repeated == staged
    with pytest.raises(OwnerControlConflict, match="idempotency"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await stage_generic_dynamic_selection_mode(
                uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
                request=request.model_copy(update={"reason":"different_reason"}),
                authentication_strength="totp_step_up",
            )
    with pytest.raises(sa.exc.DBAPIError, match="Generic pending Owner epoch"):
        async with database.begin() as conn:
            await conn.execute(sa.text("""
                UPDATE brc_strategy_selection_control_current
                SET selection_epoch_id='epoch:forged'
                WHERE strategy_group_id=:group
            """), {"group":group})
    async with database.connect() as conn:
        for table in ("brc_instrument_selection_jobs_current", "brc_instrument_selection_snapshots",
                      "brc_strategy_universe_materialization_generations",
                      "brc_strategy_entry_vacuums_current", "brc_selection_session_authorities",
                      "brc_trade_tickets", "brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=staged.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:owner-authorized",
            now_ms=CUTOFF+1,
            lease_duration_ms=1000,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    assert claim.selection_epoch_id == staged.selection_epoch_id
    assert claim.predecessor_snapshot_id is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_jobs_current")) == 1
        for table in ("brc_instrument_selection_snapshots", "brc_strategy_universe_materialization_generations",
                      "brc_selection_session_authorities", "brc_trade_tickets", "brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    # A later successful materialization clears pending fields. Replaying the
    # same Owner idempotency key must still resolve to this exact epoch.
    async with database.begin() as conn:
        await conn.execute(sa.text("""
            UPDATE brc_strategy_selection_control_current
            SET selection_mode='dynamic_selection',pending_selection_mode=NULL,
                pending_effective_period_anchor_ms=NULL,pending_authorization_id=NULL,
                control_version=control_version+1
            WHERE strategy_group_id=:group
        """), {"group":group})
    async with PostgresKernelUnitOfWork(database) as uow:
        activated_replay = await stage_generic_dynamic_selection_mode(
            uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=request,authentication_strength="totp_step_up",
        )
    assert activated_replay.selection_mode.value == "dynamic_selection"
    assert activated_replay.selection_epoch_id == staged.selection_epoch_id


@pytest.mark.asyncio
async def test_installed_fixed24_comparison_does_not_activate_it(database: AsyncEngine) -> None:
    source = inputs("MPG-001")
    digest = canonical_digest({"exchange_instrument_ids":source.spec.candidate_ids})
    comparison_id = "comparison:"+digest[7:]
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_comparison_universe_members WHERE comparison_universe_id=:id"), {"id":comparison_id}) == 24
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_comparison_binding_current")) == 0
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id) is None
    async with database.begin() as conn:
        # Activation is a separate future full-chain contract, not performed by Spec installation.
        await conn.execute(sa.text("INSERT INTO brc_comparison_binding_current VALUES(:event,:id,1,NULL)"),
            {"event":source.spec.event_spec_id,"id":comparison_id})
    async with PostgresKernelUnitOfWork(database) as uow:
        binding = await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id)
        assert binding.exchange_instrument_ids == source.spec.candidate_ids
        assert binding.comparison_transition_revision == 1
    shrunk = source.spec.candidate_ids[:-1]
    shrunk_digest = canonical_digest({"exchange_instrument_ids":shrunk})
    shrunk_id = "comparison:"+shrunk_digest[7:]
    async with database.begin() as conn:
        await conn.execute(sa.text("INSERT INTO brc_comparison_universe_definitions VALUES(:id,:digest,23)"), {"id":shrunk_id,"digest":shrunk_digest})
        await conn.execute(sa.text("INSERT INTO brc_comparison_universe_members VALUES(:id,:member)"), [{"id":shrunk_id,"member":member} for member in shrunk])
        await conn.execute(sa.text("UPDATE brc_comparison_binding_current SET comparison_universe_id=:id,comparison_transition_revision=2 WHERE event_spec_id=:event"),
            {"id":shrunk_id,"event":source.spec.event_spec_id})
    async with PostgresKernelUnitOfWork(database) as uow:
        with pytest.raises(ValueError, match="exact Candidate24"):
            await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id)


@pytest.mark.asyncio
async def test_generic_job_commits_attempt_snapshot_and_epoch_atomically(database: AsyncEngine) -> None:
    source = inputs("MPG-001")
    await enable_epoch(database, "MPG-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF, worker_id="selection:test", now_ms=CUTOFF + 1, lease_duration_ms=1000,
        )
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.complete_generic_selection_snapshot(
            claim=claim, snapshot=snapshot, source_observed_at_ms=source.source_observed_at_ms,
            completed_at_ms=source.committed_at_ms,
        )
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF, worker_id="selection:replay", now_ms=CUTOFF + 30, lease_duration_ms=1000,
        ) == snapshot
    async with database.connect() as conn:
        job = (await conn.execute(sa.select(instrument_selection_jobs_current))).mappings().one()
        attempt = (await conn.execute(sa.select(instrument_selection_attempts))).mappings().one()
        assert job["state"] == "SNAPSHOT_READY"
        assert job["selection_snapshot_id"] == snapshot.selection_snapshot_id
        assert job["selection_epoch_id"] == attempt["selection_epoch_id"] == "epoch:1"
        assert attempt["outcome"] == "SNAPSHOT_READY"
        assert attempt["source_digest"] == snapshot.source_semantic_digest


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["claim_epoch_mismatch", "control_changed", "lease_expired", "lease_reclaimed", "predecessor_changed"])
async def test_generic_completion_revalidates_claim_control_epoch_and_predecessor(database: AsyncEngine, defect: str) -> None:
    source = inputs("MPG-001")
    await enable_epoch(database, "MPG-001")
    # Claim a later period with no predecessor; a late older result may commit while market I/O runs.
    if defect == "predecessor_changed":
        source = next_input(source).model_copy(update={"predecessor_snapshot": None})
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=source.feature_cutoff_at_ms, worker_id="selection:old", now_ms=source.feature_cutoff_at_ms + 1, lease_duration_ms=1000,
        )
    if defect == "claim_epoch_mismatch":
        claim = claim.model_copy(update={"selection_epoch_id":"epoch:wrong"})
    elif defect == "control_changed":
        async with database.begin() as conn:
            await conn.execute(sa.update(strategy_selection_control_current).where(
                strategy_selection_control_current.c.strategy_group_id == "MPG-001",
            ).values(control_version=3))
    elif defect == "lease_reclaimed":
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.claim_generic_selection_job(
                selection_spec_id=source.spec.selection_spec_id, selection_epoch_id=source.selection_epoch_id,
                feature_cutoff_at_ms=source.feature_cutoff_at_ms, worker_id="selection:new", now_ms=source.feature_cutoff_at_ms + 1001, lease_duration_ms=1000,
            )
    elif defect == "predecessor_changed":
        earlier_source = inputs("MPG-001")
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(compute_generic_selection(earlier_source), decision_at_ms=earlier_source.decision_at_ms, source_observed_at_ms=earlier_source.source_observed_at_ms)
    completed_at = source.feature_cutoff_at_ms + (1001 if defect == "lease_expired" else 20)
    source = source.model_copy(update={"committed_at_ms": completed_at})
    with pytest.raises(ValueError if defect=="claim_epoch_mismatch" else SelectionJobConflict):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.complete_generic_selection_snapshot(
                claim=claim, snapshot=compute_generic_selection(source), source_observed_at_ms=source.source_observed_at_ms,
                completed_at_ms=completed_at,
            )
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0


@pytest.mark.asyncio
async def test_generic_failed_source_is_not_empty_and_does_not_advance_desired(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF, worker_id="source:failed", now_ms=CUTOFF + 1, lease_duration_ms=1000,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim, outcome=SelectionAttemptOutcome.SOURCE_FAILED, reason_code="SOURCE_INCOMPLETE",
            source_member_count=23, source_digest=None, completed_at_ms=CUTOFF + 20,
        )
    async with PostgresKernelUnitOfWork(database) as uow:
        replay = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF, worker_id="source:replay", now_ms=CUTOFF + 30, lease_duration_ms=1000,
        )
        assert isinstance(replay, SelectionJobFailure)
        assert replay.outcome == "SOURCE_FAILED"
        later = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF + HOUR, worker_id="source:next", now_ms=CUTOFF + HOUR + 1, lease_duration_ms=1000,
        )
        assert isinstance(later, GenericSelectionJobClaim)
        assert later.predecessor_snapshot_id is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 0
        attempts = (await conn.execute(sa.select(instrument_selection_attempts))).mappings().all()
        assert len(attempts) == 1 and attempts[0]["outcome"] == "SOURCE_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["qualification", "one_member", "rate_limited"])
async def test_generic_temporary_source_timeout_retries_without_shrinking_candidate24(
    database: AsyncEngine, failure_kind: str,
) -> None:
    source = inputs("MI-001")
    await enable_epoch(database,"MI-001")
    calls = 0
    from src.trading_kernel.domain.generic_selection_jobs import (
        GenericSelectionSourceTemporarilyUnavailable,
    )

    class FlakyMarket:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            nonlocal calls
            calls += 1
            assert event_spec_id == source.spec.event_spec_id and len(product_profiles) == 24
            if calls == 1 and failure_kind == "qualification":
                raise TimeoutError("bounded public source timeout")
            if calls == 1 and failure_kind == "rate_limited":
                raise GenericSelectionSourceTemporarilyUnavailable(
                    "public_market_rate_limited",retry_after_ms=45_000)
            return tuple(member.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for member in source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            if (calls == 1 and failure_kind == "one_member"
                and request.exchange_instrument_id == source.spec.candidate_ids[0]):
                raise TimeoutError("one Candidate read timed out")
            return next(member.candles for member in source.member_windows
                if member.exchange_instrument_id == request.exchange_instrument_id)

    now = CUTOFF

    def clock():
        nonlocal now
        now += 1
        return now

    request = RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
        selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF,
        worker_id="generic:timeout-retry",lease_duration_ms=60_000)
    market = FlakyMarket()
    first = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert first.outcome == "SOURCE_FAILED" and calls == 1
    async with PostgresKernelUnitOfWork(database) as uow:
        job = await uow.instrument_selection.get_selection_job(selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF)
        assert job is not None and job.next_retry_at_ms is not None
        assert job.next_retry_at_ms>=job.updated_at_ms+(45_000 if failure_kind=="rate_limited" else 30_000)
        assert job.lease_owner is None and job.attempt_count == 1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT source_member_count FROM brc_instrument_selection_attempts"
        )) == (23 if failure_kind == "one_member" else 0)
    now = job.next_retry_at_ms-2
    waiting = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert waiting.outcome == "SOURCE_FAILED" and calls == 1
    now = job.next_retry_at_ms-1
    retried = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert retried.outcome == "SNAPSHOT_READY" and calls == 2
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_attempts")) == 2
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_member_decisions")) == 24
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots")) == 1


@pytest.mark.asyncio
async def test_generic_temporary_source_retry_budget_ends_after_three_attempts(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database,"MI-001")
    calls = 0

    class UnavailableMarket:
        async def fetch_generic_selection_qualifications(self, **kwargs):
            nonlocal calls
            calls += 1
            raise TimeoutError("bounded public source timeout")

    now = CUTOFF

    def clock():
        nonlocal now
        now += 1
        return now

    request = RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
        selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF,
        worker_id="generic:timeout-budget",lease_duration_ms=60_000)
    market = UnavailableMarket()
    for attempt in range(1,4):
        failed = await run_instrument_selection_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
            request=request,clock_ms=clock)
        assert failed.outcome == "SOURCE_FAILED"
        async with PostgresKernelUnitOfWork(database) as uow:
            job = await uow.instrument_selection.get_selection_job(
                selection_spec_id=source.spec.selection_spec_id,
                selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF)
            assert job is not None and job.attempt_count == attempt
            assert (job.next_retry_at_ms is None) == (attempt == 3)
        if job.next_retry_at_ms is not None:
            now = job.next_retry_at_ms-1
    again = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert again.outcome == "SOURCE_FAILED" and calls == 3
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_attempts")) == 3
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots")) == 0


@pytest.mark.asyncio
async def test_generic_source_retry_is_not_extended_past_period_expiry(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database,"MI-001")
    expiry = build_generic_selection_period(feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours).period_expires_at_ms
    calls = 0

    class TimedOutMarket:
        async def fetch_generic_selection_qualifications(self, **kwargs):
            nonlocal calls
            calls += 1
            raise TimeoutError("market temporarily unavailable")

    tick = expiry-30_000

    def clock():
        nonlocal tick
        tick += 1
        return tick

    request = RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
        selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF,
        worker_id="generic:near-expiry",lease_duration_ms=60_000)
    failed = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=TimedOutMarket(),
        request=request,clock_ms=clock)
    assert failed.outcome == "SOURCE_FAILED" and calls == 1
    async with PostgresKernelUnitOfWork(database) as uow:
        job = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF)
        assert job is not None and job.next_retry_at_ms is None
    tick = expiry
    expired = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=TimedOutMarket(),
        request=request,clock_ms=clock)
    assert expired.outcome == "EXPIRED" and calls == 1


@pytest.mark.asyncio
async def test_generic_source_integrity_gap_never_enters_retry(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database,"MI-001")
    calls = 0

    class MissingMarket:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            nonlocal calls
            calls += 1
            return tuple(member.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for member in source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            candles = next(member.candles for member in source.member_windows
                if member.exchange_instrument_id == request.exchange_instrument_id)
            return candles[:-1] if request.exchange_instrument_id == source.spec.candidate_ids[0] else candles

    now = CUTOFF

    def clock():
        nonlocal now
        now += 1
        return now

    request = RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
        selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF,
        worker_id="generic:integrity-fail",lease_duration_ms=60_000)
    market = MissingMarket()
    failed = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert failed.outcome == "SOURCE_FAILED"
    async with PostgresKernelUnitOfWork(database) as uow:
        job = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,period_anchor_ms=CUTOFF)
        assert job is not None and job.next_retry_at_ms is None
        assert job.attempt_count == 1 and job.first_blocker is not None
    now += 31_000
    repeated = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=market,
        request=request,clock_ms=clock)
    assert repeated.outcome == "SOURCE_FAILED" and calls == 1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots")) == 0


@pytest.mark.asyncio
async def test_unauthorized_epoch_cannot_reuse_job_or_snapshot_hysteresis(database: AsyncEngine) -> None:
    source = inputs("MPG-001")
    await enable_epoch(database, "MPG-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        original = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF, worker_id="epoch:old", now_ms=CUTOFF + 1, lease_duration_ms=1000,
        )
    # An unauthorized epoch cannot read/reuse another epoch's existing Job.
    # Positive Owner epoch rotation is covered by the full Static/Dynamic chain.
    async with PostgresKernelUnitOfWork(database) as uow:
        fresh = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:2",
            feature_cutoff_at_ms=CUTOFF, worker_id="epoch:new", now_ms=CUTOFF + 2, lease_duration_ms=1000,
        )
        assert isinstance(original, GenericSelectionJobClaim) and fresh is None
        assert await uow.instrument_selection.get_selection_job(selection_spec_id=source.spec.selection_spec_id, period_anchor_ms=CUTOFF, selection_epoch_id="epoch:2") is None
        prior = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            period_anchor_ms=CUTOFF,
            selection_epoch_id="epoch:1",
        )
        assert prior is not None and prior.state == "CLAIMED" and prior.lease_owner=="epoch:old"
    first = compute_generic_selection(source)
    next_epoch = compute_generic_selection(source.model_copy(update={"selection_epoch_id":"epoch:2","predecessor_snapshot":None}))
    assert next_epoch.selection_snapshot_id!=first.selection_snapshot_id
    assert next_epoch.predecessor_snapshot_id is None
    assert all(not member.retained for member in next_epoch.members)
    with pytest.raises(ValueError,match="epoch"):
        compute_generic_selection(next_input(source).model_copy(update={"selection_epoch_id":"epoch:2","predecessor_snapshot":first}))


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_snapshot_commit_response_loss_retries_without_second_market_read(
    database: AsyncEngine, group: str,
) -> None:
    source = inputs(group)
    await enable_epoch(database,group)
    active_transactions = 0
    allowed_selection_methods = frozenset({"get_generic_spec","claim_generic_selection_job","get_selection_job",
        "get_generic_snapshot","get_selection_product_profiles","complete_generic_selection_snapshot","complete_selection_failure"})
    class SelectionOnlyRepository:
        def __init__(self,repository):
            self.repository = repository

        def __getattr__(self,name):
            assert name in allowed_selection_methods, f"Selection Runner read runtime authority: {name}"
            return getattr(self.repository,name)
    class TradingReadsForbidden:
        def __getattr__(self,name):
            raise AssertionError(f"Selection Runner read Trading Plane: {name}")
    @asynccontextmanager
    async def selection_uow():
        nonlocal active_transactions
        active_transactions += 1
        try:
            async with PostgresKernelUnitOfWork(database) as uow:
                uow.instrument_selection = SelectionOnlyRepository(uow.instrument_selection)
                uow.strategy_universes = TradingReadsForbidden()
                uow.tickets = TradingReadsForbidden()
                uow.capacity_claims = TradingReadsForbidden()
                uow.exchange_commands = TradingReadsForbidden()
                yield uow
        finally:
            active_transactions -= 1
    class CompleteMarket:
        def __init__(self):
            self.qualifications = 0
            self.klines = 0

        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            assert active_transactions==0
            self.qualifications += 1
            assert event_spec_id == source.spec.event_spec_id and len(product_profiles) == 24
            return tuple(window.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for window in source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            assert active_transactions==0
            self.klines += 1
            return next(window.candles for window in source.member_windows
                if window.exchange_instrument_id==request.exchange_instrument_id)
    market = CompleteMarket()
    request = RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
        selection_epoch_id=source.selection_epoch_id,period_anchor_ms=source.feature_cutoff_at_ms,
        worker_id=f"lost-response:{group}")
    tick = source.feature_cutoff_at_ms
    def clock():
        nonlocal tick
        tick += 1
        return tick
    injected = False
    @asynccontextmanager
    async def lost_commit_response():
        nonlocal injected
        async with selection_uow() as uow:
            yield uow
        if not injected:
            async with database.connect() as conn:
                ready = await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_jobs_current "
                    "WHERE selection_spec_id=:spec AND state='SNAPSHOT_READY'"),
                    {"spec":source.spec.selection_spec_id})
            if ready:
                injected = True
                raise RuntimeError("selection commit acknowledgement lost")
    with pytest.raises(RuntimeError,match="acknowledgement lost"):
        await run_instrument_selection_once(uow_factory=lost_commit_response,
            market_source=market,request=request,clock_ms=clock)
    assert injected and market.qualifications == 1 and market.klines == 24
    retry = await run_instrument_selection_once(
        uow_factory=selection_uow,market_source=market,
        request=request,clock_ms=clock)
    assert retry.outcome == "ALREADY_READY"
    assert market.qualifications == 1 and market.klines == 24
    assert active_transactions==0
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_attempts "
            "WHERE selection_spec_id=:spec"),{"spec":source.spec.selection_spec_id}) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots "
            "WHERE selection_spec_id=:spec"),{"spec":source.spec.selection_spec_id}) == 1
        for table in ("brc_strategy_universe_materialization_generations",
            "brc_strategy_entry_vacuums_current","brc_trade_tickets","brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0


@pytest.mark.asyncio
async def test_generic_claim_rejects_live_lease_then_reclaims_without_stale_completion(database: AsyncEngine) -> None:
    source = inputs("BRF2-001")
    await enable_epoch(database, "BRF2-001")
    arguments = {"selection_spec_id": source.spec.selection_spec_id, "selection_epoch_id": "epoch:1",
        "feature_cutoff_at_ms": CUTOFF, "lease_duration_ms": 1000}
    async with PostgresKernelUnitOfWork(database) as uow:
        original = await uow.instrument_selection.claim_generic_selection_job(**arguments, worker_id="claim:old", now_ms=CUTOFF + 1)
    assert isinstance(original, GenericSelectionJobClaim)
    with pytest.raises(SelectionJobConflict, match="live lease"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.claim_generic_selection_job(**arguments, worker_id="claim:early", now_ms=CUTOFF + 20)
    async with PostgresKernelUnitOfWork(database) as uow:
        fresh = await uow.instrument_selection.claim_generic_selection_job(**arguments, worker_id="claim:new", now_ms=CUTOFF + 1001)
    assert isinstance(fresh, GenericSelectionJobClaim)
    assert fresh.attempt_number == 2 and fresh.projection_version == original.projection_version + 1
    source = source.model_copy(update={"source_observed_at_ms": CUTOFF + 1010, "committed_at_ms": CUTOFF + 1020})
    snapshot = compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.complete_generic_selection_snapshot(claim=fresh, snapshot=snapshot,
            source_observed_at_ms=source.source_observed_at_ms, completed_at_ms=source.committed_at_ms)
    async with database.connect() as conn:
        attempt = (await conn.execute(sa.select(instrument_selection_attempts))).mappings().one()
        assert attempt["attempt_number"] == 2 and attempt["worker_id"] == "claim:new"


@pytest.mark.asyncio
async def test_generic_claimed_job_expires_durably_without_stale_completion(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    expiry = build_generic_selection_period(
        feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours,
    ).period_expires_at_ms
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:expired",
            now_ms=CUTOFF + 1,
            lease_duration_ms=expiry - CUTOFF + 1,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:later",
            now_ms=expiry,
            lease_duration_ms=1000,
        ) is None
    async with database.connect() as conn:
        row = (await conn.execute(sa.select(instrument_selection_jobs_current))).mappings().one()
        assert row["state"] == "EXPIRED"
        assert row["first_blocker"] == "SELECTION_PERIOD_EXPIRED"
        assert row["lease_owner"] is None and row["lease_expires_at_ms"] is None
        assert row["projection_version"] == claim.projection_version + 1
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0
    async with PostgresKernelUnitOfWork(database) as uow:
        typed = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
        )
        assert typed is not None and typed.state == "EXPIRED"
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:repeat-expired",
            now_ms=expiry + 1,
            lease_duration_ms=1000,
        ) is None
    async with database.connect() as conn:
        repeated = (await conn.execute(sa.select(instrument_selection_jobs_current))).mappings().one()
        assert repeated["state"] == "EXPIRED"
        assert repeated["projection_version"] == row["projection_version"]
    with pytest.raises(SelectionJobConflict):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.complete_generic_selection_snapshot(
                claim=claim,
                snapshot=compute_generic_selection(source),
                source_observed_at_ms=source.source_observed_at_ms,
                completed_at_ms=expiry,
            )


@pytest.mark.asyncio
async def test_generic_source_failure_cannot_commit_after_period_expiry(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    expiry = build_generic_selection_period(
        feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours,
    ).period_expires_at_ms
    async with PostgresKernelUnitOfWork(database) as uow:
        claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:late-source",
            now_ms=CUTOFF + 1,
            lease_duration_ms=expiry - CUTOFF + 1000,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    with pytest.raises(SelectionJobConflict, match="period expired"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.complete_selection_failure(
                claim=claim,
                outcome=SelectionAttemptOutcome.SOURCE_FAILED,
                reason_code="SOURCE_INCOMPLETE",
                source_member_count=23,
                source_digest=None,
                completed_at_ms=expiry,
            )
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0


@pytest.mark.asyncio
async def test_expired_generic_period_records_terminal_job_without_source_attempt(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    expiry = build_generic_selection_period(
        feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours,
    ).period_expires_at_ms
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:too-late",
            now_ms=expiry,
            lease_duration_ms=1000,
        ) is None
    async with database.connect() as conn:
        row = (await conn.execute(sa.select(instrument_selection_jobs_current))).mappings().one()
        assert row["state"] == "EXPIRED"
        assert row["first_blocker"] == "SELECTION_PERIOD_EXPIRED"
        assert row["attempt_count"] == 0
        assert row["lease_owner"] is None
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0


@pytest.mark.asyncio
async def test_newer_due_generic_job_supersedes_live_older_claim(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        old_claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:old-period",
            now_ms=CUTOFF + 1,
            lease_duration_ms=2 * HOUR,
        )
    assert isinstance(old_claim, GenericSelectionJobClaim)
    newer_cutoff = CUTOFF + HOUR
    from src.trading_kernel.domain.generic_selection_jobs import selection_job_identity

    with pytest.raises(sa.exc.DBAPIError, match="one_actionable_epoch"):
        async with database.begin() as conn:
            await conn.execute(sa.text("""
                INSERT INTO brc_instrument_selection_jobs_current
                (selection_job_id,selection_spec_id,selection_epoch_id,
                 selection_control_version,period_anchor_ms,scheduled_at_ms,
                 feature_cutoff_at_ms,state,attempt_count,projection_version,updated_at_ms)
                VALUES(:job,:spec,:epoch,2,:cutoff,:cutoff,:cutoff,'DUE',0,1,:cutoff)
            """), {"job":selection_job_identity(source.spec.selection_spec_id,newer_cutoff,source.selection_epoch_id),
                    "spec":source.spec.selection_spec_id,"epoch":source.selection_epoch_id,"cutoff":newer_cutoff})
    async with PostgresKernelUnitOfWork(database) as uow:
        new_claim = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=newer_cutoff,
            worker_id="selection:new-period",
            now_ms=newer_cutoff + 1,
            lease_duration_ms=1000,
        )
    assert isinstance(new_claim, GenericSelectionJobClaim)
    async with database.connect() as conn:
        rows = (await conn.execute(sa.select(instrument_selection_jobs_current)
            .order_by(instrument_selection_jobs_current.c.period_anchor_ms))).mappings().all()
        assert len(rows) == 2
        assert rows[0]["state"] == "SUPERSEDED"
        assert rows[0]["first_blocker"] == "SUPERSEDED_BY_NEWER_DUE_PERIOD"
        assert rows[0]["lease_owner"] is None
        assert rows[0]["projection_version"] == old_claim.projection_version + 1
        assert rows[1]["state"] == "CLAIMED"
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0
    async with PostgresKernelUnitOfWork(database) as uow:
        typed = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
        )
        assert typed is not None and typed.state == "SUPERSEDED"
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:stale-retry",
            now_ms=newer_cutoff + 2,
            lease_duration_ms=1000,
        ) is None
    with pytest.raises(SelectionJobConflict):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.complete_generic_selection_snapshot(
                claim=old_claim,
                snapshot=compute_generic_selection(source),
                source_observed_at_ms=source.source_observed_at_ms,
                completed_at_ms=newer_cutoff + 2,
            )


@pytest.mark.asyncio
async def test_older_due_generic_period_cannot_reclaim_after_newer_due(database: AsyncEngine) -> None:
    source = inputs("CPM-RO-001")
    await enable_epoch(database, "CPM-RO-001")
    newer_cutoff = CUTOFF + 4 * HOUR
    async with PostgresKernelUnitOfWork(database) as uow:
        newer = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=newer_cutoff,
            worker_id="selection:newer-first",
            now_ms=newer_cutoff + 1,
            lease_duration_ms=1000,
        )
    assert isinstance(newer, GenericSelectionJobClaim)
    async with PostgresKernelUnitOfWork(database) as uow:
        older = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            feature_cutoff_at_ms=CUTOFF,
            worker_id="selection:old-late",
            now_ms=newer_cutoff + 2,
            lease_duration_ms=1000,
        )
        terminal = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
        )
    assert older is None
    assert terminal is not None and terminal.state == "SUPERSEDED"
    assert terminal.attempt_count == 0 and terminal.lease_owner is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0


@pytest.mark.asyncio
async def test_control_cannot_point_at_another_strategys_selection_spec(database: AsyncEngine) -> None:
    with pytest.raises(sa.exc.DBAPIError, match="Control.*Spec"):
        async with database.begin() as conn:
            await conn.execute(sa.update(strategy_selection_control_current).where(
                strategy_selection_control_current.c.strategy_group_id == "MI-001",
            ).values(selection_spec_id=inputs("MPG-001").spec.selection_spec_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("group,comparison_only", [("CPM-RO-001",False), ("MPG-001",False), ("MI-001",False), ("BRF2-001",False), ("MPG-001",True), ("MI-001",True)])
async def test_generic_generation_schema_uses_one_exact_previous_event_without_fake_pair(database: AsyncEngine, group: str, comparison_only: bool) -> None:
    await _exercise_generic_generation(database, group, comparison_only)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("first_activation", [False, True])
async def test_generic_activation_commits_and_restarts_through_real_uow(database: AsyncEngine, group: str, first_activation: bool) -> None:
    await _exercise_generic_generation(database, group, False, durable=True, first_activation=first_activation)


@pytest.mark.asyncio
@pytest.mark.parametrize("group,cancel_before_fill", [
    ("CPM-RO-001",False),("MPG-001",False),("MI-001",False),("BRF2-001",False),
    ("CPM-RO-001",True),("BRF2-001",True),
    ("CPM-RO-001","latest_nonempty"),("BRF2-001","latest_nonempty"),
    ("CPM-RO-001","latest_nonempty_unknown"),("BRF2-001","latest_nonempty_unknown"),
    ("CPM-RO-001","latest_nonempty_partial"),("BRF2-001","latest_nonempty_partial"),
    *((group,"latest_nonempty_pause"+suffix) for group in ("CPM-RO-001","BRF2-001") for suffix in ("","_unknown","_partial","_false","_string","_recover","_unknown_recover","_partial_recover","_early_resume","_early_resume_unknown","_early_resume_partial","_early_resume_recover","_early_resume_unknown_recover","_early_resume_partial_recover")),
    *((group,"entry_fault:"+fault) for group in ("CPM-RO-001","BRF2-001")
        for fault in ("before_issue","between_claim_ticket","before_dispatch","stale_before_dispatch","stale_before_claim","pending_static_between_claim_ticket","static_after_protection","static_timeout_after_protection","static_close_boundary_after_protection")),
    *((group,"entry_fault:prepared_pause:"+fault) for group in ("CPM-RO-001","BRF2-001") for fault in ("empty","nonempty","early_empty","early_nonempty")),
    *((group,"entry_fault:static_new_entry:"+fault) for group in ("CPM-RO-001","BRF2-001")
        for fault in ("before_issue","between_claim_ticket","before_dispatch","stale_before_dispatch")),
])
async def test_owner_staged_runner_materializes_without_fixture_snapshot(
    database: AsyncEngine, group: str, cancel_before_fill: bool | str,
) -> None:
    await _exercise_generic_generation(database, group, False,
        durable=True, first_activation=True, natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        selection_control = await uow.instrument_selection.get_selection_control(group)
        assert selection_control is not None and selection_control.rollback_baseline_id is not None
        frozen_baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(
            selection_control.rollback_baseline_id)
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions "
            "WHERE universe_version_id=:uid"),{"uid":frozen_baseline.source_event.universe_version_id}) == "retired"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines "
            "WHERE strategy_group_id=:group"),{"group":group}) == 1
    if group not in {"CPM-RO-001", "BRF2-001"}:
        return
    source = inputs(group)
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert current is not None and current.authority.authority_outcome == "ACTIVE_NEW"
        close = current.authority.current_close_proof.current_final_close_time_ms
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text(
            "SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"
        ), {"uid":current.authority.event_binding.universe_version_id})
    template = cpm_long_snapshot() if group == "CPM-RO-001" else brf2_short_snapshot()
    delta = close-template.trigger_candle_close_time_ms

    class SignalMarket:
        async def fetch_closed_candles(self, request):
            candles = template.candles_1h if request.timeframe == "1h" else template.candles_4h
            return tuple(c.model_copy(update={
                "open_time_ms":c.open_time_ms+delta,
                "close_time_ms":c.close_time_ms+delta,
            }) for c in candles)

    observed = await observe_strategy_scope(
        lambda:PostgresKernelUnitOfWork(database),SignalMarket(),
        ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,
            schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=close,
            attempted_at_ms=close+30_005),
    )
    async with database.connect() as conn:
        blocker = await conn.scalar(sa.text(
            "SELECT first_blocker FROM brc_readiness_current WHERE runtime_scope_id=:scope"
        ), {"scope":scope_id})
        member = await conn.scalar(sa.text(
            "SELECT exchange_instrument_id FROM brc_runtime_scopes_current WHERE runtime_scope_id=:scope"
        ), {"scope":scope_id})
        instrument_status = await conn.scalar(sa.text(
            "SELECT status FROM brc_instruments WHERE exchange_instrument_id=:member"
        ), {"member":member})
    assert observed.status == ObservationStatus.SIGNAL_CREATED, (observed,blocker,member,instrument_status)
    if isinstance(cancel_before_fill,str) and cancel_before_fill.startswith("entry_fault:"):
        await _issue_and_dispatch_hourly_natural_entry(database,group=group,signal_event_id=observed.signal_event_id,
            selection_authority_id=current.authority.selection_authority_id,member=member,
            universe_version_id=current.authority.event_binding.universe_version_id,closed_at_ms=close,
            now_ms=close+30006,fault_stage=cancel_before_fill.split(":",1)[1])
        return
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
    from src.trading_kernel.application.issue_ready_signal import (
        IssueReadySignalRequest,
        issue_ready_signal,
    )
    from src.trading_kernel.domain.cross_margin_stress import (
        AccountRiskSnapshot,
        MaintenanceMarginBracket,
    )
    from src.trading_kernel.domain.entry_admission_snapshot import (
        EntryAdmissionSnapshot,
    )

    issued_at = close+30_006
    await make_warming_ready(database,
        universe_version_id=current.authority.event_binding.universe_version_id,
        warm_closed_bar_time_ms=close,valid_until_ms=issued_at+60_000)
    risk = AccountRiskSnapshot.create(
        venue_id="binance-usdm",account_id="generic-snapshot",
        account_risk_mode="standard_usdm_single_asset",settlement_asset="USDT",
        position_mode="independent_sides",margin_mode="cross",
        exchange_instrument_id=member,mark_price=Decimal(105),configured_leverage=5,
        total_wallet_balance=Decimal(1000),total_margin_balance=Decimal(1000),
        total_initial_margin=Decimal(0),total_maintenance_margin=Decimal(0),
        available_margin=Decimal(1000),account_positions=(),
        observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
    admission = EntryAdmissionSnapshot(account_risk_snapshot=risk,
        best_bid_price=Decimal("104.99"),best_ask_price=Decimal(105),open_orders=(),
        observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
    brackets = (MaintenanceMarginBracket(bracket_id=f"natural-{group}:1",notional_floor=Decimal(0),
        notional_cap=Decimal(20_000),maintenance_margin_rate=Decimal("0.005"),
        maintenance_amount=Decimal(0)),)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.signals.upsert_instrument_rules(venue_id="binance-usdm",exchange_instrument_id=member,
            quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),exchange_max_leverage=5,
            maintenance_margin_brackets=brackets,maintenance_margin_brackets_digest=canonical_digest(brackets),
            notional_coefficient=Decimal(1),notional_coefficient_certified=True,
            observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
        issued = await issue_ready_signal(uow,IssueReadySignalRequest(
            signal_event_id=observed.signal_event_id,admission_snapshot=admission,
            claim_owner=f"natural-{group}-entry",runtime_commit="a"*40,
            schema_revision=CURRENT_SCHEMA_REVISION,now_ms=issued_at))
    assert issued.status.value == "issued", issued
    async with PostgresKernelUnitOfWork(database) as uow:
        ticket = await uow.tickets.get(issued.ticket_id)
        claim = await uow.capacity_claims.get_for_signal(observed.signal_event_id)
        decision = await uow.admission_decisions.get_for_signal(observed.signal_event_id)
        assert ticket is not None and claim is not None and decision is not None
        assert ticket.selection_authority_id == current.authority.selection_authority_id
        assert claim.selection_authority_id == ticket.selection_authority_id
        assert decision.selection_authority_id == ticket.selection_authority_id
        source_snapshot = await uow.instrument_selection.get_generic_snapshot(
            current.authority.selection_snapshot_id)
        chosen = next(row for row in source_snapshot.members
            if row.exchange_instrument_id == member)
        assert chosen.selected and chosen.qualified and chosen.stable_rank > 0
        assert chosen.input_window_digest.startswith("sha256:")
        assert chosen.qualification_semantic_digest.startswith("sha256:")
        assert ticket.exit_binding_id is not None
        assert ticket.exit_binding_semantic_hash is not None
        assert ticket.exit_binding_authority_version is not None
        assert ticket.initial_stop_price > 0
    async with database.connect() as conn:
        frozen_path = (await conn.execute(sa.text("SELECT a.selection_spec_id,a.selection_epoch_id,"
            "a.selection_snapshot_id,s.occurred_at_ms,s.fact_digest,t.fact_digest AS ticket_fact_digest "
            "FROM brc_trade_tickets t "
            "JOIN brc_selection_session_authorities a ON a.selection_authority_id=t.selection_authority_id "
            "JOIN brc_signal_events s ON s.signal_event_id=t.signal_event_id "
            "WHERE t.ticket_id=:ticket"),{"ticket":issued.ticket_id})).mappings().one()
        assert frozen_path["selection_spec_id"] == source_snapshot.selection_spec_id
        assert frozen_path["selection_epoch_id"] == source_snapshot.selection_epoch_id
        assert frozen_path["selection_snapshot_id"] == source_snapshot.selection_snapshot_id
        assert frozen_path["occurred_at_ms"] == close
        assert frozen_path["fact_digest"] == frozen_path["ticket_fact_digest"]
        commands = (await conn.execute(sa.text(
            "SELECT command_kind,status FROM brc_exchange_commands WHERE ticket_id=:ticket"
        ), {"ticket":issued.ticket_id})).mappings().all()
        assert len(commands) == 1 and commands[0]["command_kind"] == "entry"
        assert commands[0]["status"] == "prepared"
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
    from src.trading_kernel.domain.commands import (
        ExchangeCommandResult,
        ExchangeCommandStatus,
    )

    class NaturalEntryFacts:
        async def read_entry_admission_snapshot(self, request):
            fresh_risk = AccountRiskSnapshot.create(**{
                **risk.model_dump(exclude={"snapshot_digest"}),
                "observed_at_ms":request.observed_at_ms,
                "valid_until_ms":request.observed_at_ms+request.valid_for_ms,
            })
            return admission.model_copy(update={
                "account_risk_snapshot":fresh_risk,
                "observed_at_ms":request.observed_at_ms,
                "valid_until_ms":request.observed_at_ms+request.valid_for_ms,
            })

        async def read_instrument_rules(self, request):
            return InstrumentRulesFacts(exchange_instrument_id=request.exchange_instrument_id,
                quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),exchange_max_leverage=5,
                maintenance_margin_brackets=brackets,
                maintenance_margin_brackets_digest=canonical_digest(brackets),
                notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms+request.valid_for_ms)

    class RecordingVenue:
        def __init__(self):
            self.calls = []
            self.now_ms = issued_at+5

        async def execute(self, request):
            async with PostgresKernelUnitOfWork(database) as durable_uow:
                durable = await durable_uow.exchange_commands.get(request.command_id)
                assert durable.status is ExchangeCommandStatus.CLAIMED
            self.calls.append(request)
            return ExchangeCommandResult(status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self.now_ms+1,
                exchange_order_id=f"natural-{request.kind.value}-{len(self.calls)}")

    async with database.begin() as conn:
        await conn.execute(sa.text(
            "UPDATE brc_runtime_capabilities_current SET enabled=true "
            "WHERE capability_key='exchange_commands'"
        ))
    venue = RecordingVenue()
    dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
        DispatchCommandRequest(worker_id=f"natural-{group}-dispatch",ticket_id=issued.ticket_id,
            now_ms=issued_at+5,lease_until_ms=issued_at+30_000,timeout_seconds=1,
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=60_000),entry_facts_source=NaturalEntryFacts())
    assert dispatched.status.value == "accepted", dispatched
    assert len(venue.calls) == 1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT status FROM brc_exchange_commands WHERE ticket_id=:ticket AND command_kind='entry'"
        ), {"ticket":issued.ticket_id}) == "accepted"
    if cancel_before_fill:
        await _assert_natural_sent_entry_drained_by_selection(database,
            group=group,current=current,issued=issued,ticket=ticket,venue=venue,
            initial_source=source,entry_dispatched_at_ms=issued_at+5,
            supersede_with_nonempty=isinstance(cancel_before_fill,str) and cancel_before_fill.startswith("latest_nonempty"),
            unknown_cancel=isinstance(cancel_before_fill,str) and "_unknown" in cancel_before_fill,
            partial_fill=isinstance(cancel_before_fill,str) and "_partial" in cancel_before_fill,
            pause_owner=isinstance(cancel_before_fill,str) and "_pause" in cancel_before_fill,
            corrupt_pause_completion=cancel_before_fill.rsplit("_",1)[-1] if isinstance(cancel_before_fill,str) and cancel_before_fill.endswith(("_false","_string")) else None,
            paused_nonempty_recovery=isinstance(cancel_before_fill,str) and cancel_before_fill.endswith("_recover"),
            early_resume=isinstance(cancel_before_fill,str) and "_early_resume" in cancel_before_fill)
        return
    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.application.reconcile_ticket import (
        ReconcileTicketRequest,
        reconcile_ticket,
    )
    from src.trading_kernel.application.settle_ticket import (
        RecordTradeReviewRequest,
        SettleTicketRequest,
        record_trade_review,
        settle_ticket,
    )
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.events import PostFillStressAssessed
    from src.trading_kernel.domain.position import PositionSnapshot
    from src.trading_kernel.domain.reducer import reduce_event
    from tests.trading_kernel.support.capacity_claims import make_stress_evidence

    async with PostgresKernelUnitOfWork(database) as uow:
        filled = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=ticket.quantity,average_entry_price=ticket.entry_reference_price,
                venue_reported_liquidation_price=Decimal(0),open_orders=(),
                observed_at_ms=issued_at+100)))
    assert filled.status.value == "entry_fill_recorded"

    async def dispatch_safety(step):
        async with PostgresKernelUnitOfWork(database) as uow:
            pending = await uow.aggregates.get(issued.ticket_id)
            if pending is not None and pending.status is AggregateStatus.POST_FILL_RISK_PENDING:
                event = PostFillStressAssessed(
                    event_id=f"event:{issued.ticket_id}:{pending.last_event_sequence+1}",
                    ticket_id=issued.ticket_id,sequence=pending.last_event_sequence+1,
                    occurred_at_ms=issued_at+step-1,status="passed",
                    evidence=make_stress_evidence(pending.ticket),
                    owner_policy_id=pending.ticket.owner_policy_id,
                    owner_policy_version=pending.ticket.owner_policy_version,
                    filled_qty=pending.position_qty,average_fill_price=pending.average_fill_price,
                    initial_stop_price=pending.ticket.initial_stop_price,
                    initial_stop_exchange_order_id=pending.initial_stop_exchange_order_id)
                await uow.commit_reduction(event=event,reduction=reduce_event(pending,event),
                    expected_version=pending.version)
        venue.now_ms = issued_at+step
        result = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
            DispatchCommandRequest(worker_id=f"natural-{group}-lifecycle",ticket_id=issued.ticket_id,
                now_ms=venue.now_ms,lease_until_ms=venue.now_ms+30_000,timeout_seconds=1))
        assert result.status.value == "accepted", result

    await dispatch_safety(200)
    await dispatch_safety(300)
    async with PostgresKernelUnitOfWork(database) as uow:
        protected = await uow.aggregates.get(issued.ticket_id)
    assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
    assert protected.initial_stop_exchange_order_id is not None
    assert protected.tp1_exchange_order_id is not None
    async with PostgresKernelUnitOfWork(database) as uow:
        first_snapshot = await uow.instrument_selection.get_generic_snapshot(
            current.authority.selection_snapshot_id)
    first_input = inputs(group).model_copy(update={
        "selection_epoch_id":current.authority.selection_epoch_id})
    empty_input = next_input(first_input).model_copy(update={
        "predecessor_snapshot":first_snapshot})
    empty_input = empty_input.model_copy(update={"member_windows":tuple(
        qualify_window(window,False) for window in empty_input.member_windows)})
    empty_snapshot = compute_generic_selection(empty_input)
    assert not empty_snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(empty_snapshot,
            decision_at_ms=empty_input.decision_at_ms,
            source_observed_at_ms=empty_input.source_observed_at_ms)
    empty_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty_snapshot.selection_snapshot_id,
        worker_id=f"natural-{group}-valid-empty")
    empty_at = empty_snapshot.effective_from_ms+1
    empty_result = None
    for offset in range(5):
        tick = empty_at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            outcome = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=empty_request,clock_ms=lambda tick=tick:tick)
        if outcome.disposition is MaterializationDisposition.VALID_EMPTY:
            empty_result = outcome
            break
    assert empty_result is not None
    async with PostgresKernelUnitOfWork(database) as uow:
        empty_authority = await uow.instrument_selection.get_current_generic_authority(
            current.authority.selection_spec_id)
        still_protected = await uow.aggregates.get(issued.ticket_id)
        frozen_before_exit = await uow.tickets.get(issued.ticket_id)
        old_scope = await uow.signals.get_runtime_scope(scope_id)
        assert old_scope is not None
        new_entry = await resolve_selection_entry_authority(uow,runtime_scope=old_scope,
            birth_selection_authority_id=current.authority.selection_authority_id,
            observed_close_time_ms=empty_snapshot.effective_from_ms,
            now_ms=empty_at+5,allow_current_as_birth=False,lock_current=True)
    assert empty_authority is not None and empty_authority.authority.authority_outcome == "VALID_EMPTY"
    assert still_protected is not None and still_protected.status is AggregateStatus.POSITION_PROTECTED
    assert frozen_before_exit is not None and frozen_before_exit.selection_authority_id == current.authority.selection_authority_id
    assert frozen_before_exit.initial_stop_price == ticket.initial_stop_price
    assert not new_entry.allowed and new_entry.reason_code == "selection_valid_empty"
    exit_offset = empty_at-issued_at+400
    async with PostgresKernelUnitOfWork(database) as uow:
        runner = await maintain_ticket_lifecycle(uow,LifecycleMaintenanceRequest(
            ticket_id=issued.ticket_id,
            facts=TicketLifecycleFacts(position_quantity=ticket.quantity-ticket.take_profit_quantities[0],
                tp1_filled_quantity=ticket.take_profit_quantities[0],
                tp1_average_fill_price=ticket.take_profit_prices[0],
                allocated_entry_fee_quote=Decimal("0.01"),exit_taker_fee_rate=Decimal("0.001"),
                price_tick=Decimal("0.01"),market_facts=None,observed_at_ms=issued_at+exit_offset),
            now_ms=issued_at+exit_offset))
    assert runner.status.value == "break_even_requested"
    await dispatch_safety(exit_offset+100)
    await dispatch_safety(exit_offset+200)
    async with PostgresKernelUnitOfWork(database) as uow:
        external_flat = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=Decimal(0),average_entry_price=None,open_orders=(),
                observed_at_ms=issued_at+exit_offset+300)))
    assert external_flat.status.value == "external_flat_incident"
    await dispatch_safety(exit_offset+400)
    async with PostgresKernelUnitOfWork(database) as uow:
        matched = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=Decimal(0),average_entry_price=None,open_orders=(),
                observed_at_ms=issued_at+exit_offset+500)))
        settled = await settle_ticket(uow,SettleTicketRequest(
            ticket_id=issued.ticket_id,settled_at_ms=issued_at+exit_offset+600))
        reviewed = await record_trade_review(uow,RecordTradeReviewRequest(
            ticket_id=issued.ticket_id,review_id=f"review:natural-{group}",
            outcome="closed",metrics={"realized_pnl":"1.25"},
            decision_impact={"strategy_action":"keep"},recorded_at_ms=issued_at+exit_offset+700))
        terminal = await uow.aggregates.get(issued.ticket_id)
        frozen_ticket = await uow.tickets.get(issued.ticket_id)
        reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(issued.ticket_id)
        active_domain = await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
        commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
    assert matched.status.value == "matched"
    assert settled.status.value == "budget_settled" and reviewed.status.value == "review_recorded"
    assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
    assert frozen_ticket is not None and frozen_ticket.selection_authority_id == current.authority.selection_authority_id
    assert reservation is not None and reservation.status == "released"
    assert incident is None and not active_domain
    assert len(commands) == len(venue.calls)
    async with database.connect() as conn:
        lineage = set((await conn.execute(sa.text("SELECT event_type FROM brc_trade_events "
            "WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})).scalars())
        assert {"EntryFilled","TakeProfitFilled","ProtectionReplacementConfirmed",
            "BudgetSettled","ReviewRecorded"} <= lineage
        final_pointer = await conn.scalar(sa.text("SELECT review_id FROM brc_trade_aggregates "
            "WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})
        frozen_binding = (await conn.execute(sa.text("SELECT exit_binding_id,exit_binding_semantic_hash "
            "FROM brc_trade_tickets WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})).one()
    assert final_pointer == f"review:natural-{group}"
    assert frozen_binding == (ticket.exit_binding_id,ticket.exit_binding_semantic_hash)


async def _assert_natural_sent_entry_drained_by_selection(
    database, *, group, current, issued, ticket, venue, initial_source,
    entry_dispatched_at_ms,
    supersede_with_nonempty: bool = False,
    unknown_cancel: bool = False,
    partial_fill: bool = False,
    pause_owner: bool = False,
    corrupt_pause_completion: str | None = None,
    paused_nonempty_recovery: bool = False,
    early_resume: bool = False,
) -> None:
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.commands import ExchangeCommandKind
    from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot

    async with PostgresKernelUnitOfWork(database) as uow:
        parent = await uow.instrument_selection.get_generic_snapshot(
            current.authority.selection_snapshot_id)
    empty_source = next_input(initial_source.model_copy(update={
        "selection_epoch_id":parent.selection_epoch_id})).model_copy(update={
            "predecessor_snapshot":parent})
    replacement_member=empty_source.spec.candidate_ids[int(parent.selected_members==(empty_source.spec.candidate_ids[0],))]
    empty_source = empty_source.model_copy(update={"member_windows":tuple(
        qualify_window(window.model_copy(update={"candles":empty_source.member_windows[0].candles}),supersede_with_nonempty and window.exchange_instrument_id==replacement_member)
        for window in empty_source.member_windows)})
    class EmptyMarket:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            assert event_spec_id==empty_source.spec.event_spec_id and len(product_profiles)==24
            return tuple(window.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for window in empty_source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            return next(window.candles for window in empty_source.member_windows
                if window.exchange_instrument_id==request.exchange_instrument_id)
    tick = empty_source.feature_cutoff_at_ms
    def selection_clock():
        nonlocal tick
        tick += 1
        return tick
    selected = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=EmptyMarket(),
        request=RunInstrumentSelectionRequest(selection_spec_id=empty_source.spec.selection_spec_id,
            selection_epoch_id=empty_source.selection_epoch_id,
            period_anchor_ms=empty_source.feature_cutoff_at_ms,
            worker_id=f"natural-{group}-cancel-selector"),clock_ms=selection_clock)
    assert selected.outcome == "SNAPSHOT_READY", selected
    async with PostgresKernelUnitOfWork(database) as uow:
        empty = await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
    assert bool(empty.selected_members) == supersede_with_nonempty
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,
        worker_id=f"natural-{group}-cancel-materializer")
    now = empty.effective_from_ms+1
    for offset in range(4):
        at = now+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda at=at:at)
        if step.reason_code == "VACUUM_POSITION_FACTS_REQUIRED":
            break
    async with PostgresKernelUnitOfWork(database) as uow:
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
        aggregate = await uow.aggregates.get(issued.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
    assert vacuum is not None and vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY
    assert aggregate is not None and aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert len(commands)==1 and commands[0].kind is ExchangeCommandKind.ENTRY
    assert aggregate.entry_exchange_order_id is not None
    original_vacuum = vacuum
    if supersede_with_nonempty:
        # The exact original ENTRY is still open when a third-period Desired arrives.
        # Reuse Runner/source acquisition; do not mutate the old Vacuum pointer.
        empty_source = next_input(empty_source).model_copy(update={"predecessor_snapshot": empty})
        if pause_owner and not paused_nonempty_recovery:
            empty_source=empty_source.model_copy(update={"member_windows":tuple(qualify_window(window,False) for window in empty_source.member_windows)})
        tick = empty_source.feature_cutoff_at_ms
        selected = await run_instrument_selection_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=EmptyMarket(),
            request=RunInstrumentSelectionRequest(selection_spec_id=empty_source.spec.selection_spec_id,
                selection_epoch_id=empty_source.selection_epoch_id,
                period_anchor_ms=empty_source.feature_cutoff_at_ms,
                worker_id=f"natural-{group}-latest-nonempty-selector"),clock_ms=selection_clock)
        assert selected.outcome == "SNAPSHOT_READY", selected
        async with PostgresKernelUnitOfWork(database) as uow:
            empty = await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
        assert bool(empty.selected_members)==(not pause_owner or paused_nonempty_recovery)
        request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,
            worker_id=f"natural-{group}-latest-nonempty-materializer")
        now = empty.effective_from_ms+1
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now)):
            waiting = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now)
        assert waiting.disposition is MaterializationDisposition.WAITING_VACUUM, waiting
        async with PostgresKernelUnitOfWork(database) as uow:
            still_draining = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
            assert still_draining == original_vacuum
            assert await uow.instrument_selection.get_generic_materialization_generation(
                GenericMaterializationGeneration.id_for_snapshot(empty.selection_snapshot_id)) is None
            assert await uow.strategy_universes.get_generation_universe_targets(original_vacuum.source_generation_id) == ()
    if pause_owner:
        from src.trading_kernel.application.owner_control import (
            set_strategy_entry_state,
        )
        from src.trading_kernel.domain.owner_control import StrategyEntryState
        async with PostgresKernelUnitOfWork(database) as uow:
            owner=await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_real_entry_drain",
                    idempotency_key=f"pause-real-drain:{group}:{unknown_cancel}:{partial_fill}",owner_identity="owner",now_ms=now+4),authentication_strength="totp_step_up")
        paused_request=CoordinateGenericGenerationRequest(materialization_generation_id=original_vacuum.source_generation_id,worker_id="paused-real-entry-drain")
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now+4)):
            paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=paused_request,clock_ms=lambda:now+4)
        assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
        async with PostgresKernelUnitOfWork(database) as uow:
            abandoned=await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)
            owner_vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
            assert abandoned.lifecycle_state.value=="ABANDONED" and owner_vacuum.state is StrategyEntryVacuumState.DRAINING_ENTRY
            assert owner_vacuum.fenced_at_ms==original_vacuum.fenced_at_ms and owner_vacuum.drained_at_ms is None
        original_vacuum=owner_vacuum
        if early_resume:
            async with PostgresKernelUnitOfWork(database) as uow:
                owner=await uow.owner_controls.get_strategy_control(group)
                await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                    request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_before_actual_entry_drain",
                        idempotency_key=f"early-resume:{group}:{unknown_cancel}:{partial_fill}:{paused_nonempty_recovery}",owner_identity="owner",now_ms=now+5),authentication_strength="totp_step_up")
    open_order = VenueOrderSnapshot(exchange_order_id=aggregate.entry_exchange_order_id,
        venue_client_order_id=commands[0].venue_client_order_id,
        position_side=ticket.identity.netting_domain.position_side,reduce_only=False,
        order_namespace="regular")
    partial_qty = ticket.quantity//Decimal("0.002")*Decimal("0.001") if partial_fill else Decimal(0)
    assert not partial_fill or Decimal(0)<partial_qty<ticket.quantity
    opened = PositionSnapshot(netting_domain=ticket.identity.netting_domain,
        quantity=partial_qty,average_entry_price=ticket.entry_reference_price if partial_fill else None,open_orders=(open_order,),
        observed_at_ms=now+5)
    async with PostgresKernelUnitOfWork(database) as uow:
        cancel = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
            strategy_group_id=group,selection_spec_id=empty.selection_spec_id,
            now_ms=now+5,ticket_id=issued.ticket_id,position_snapshot=opened))
        after_request = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
    assert cancel.status is VacuumDrainStatus.CANCEL_REQUESTED, cancel
    assert [command.kind for command in after_request] == [
        ExchangeCommandKind.ENTRY,ExchangeCommandKind.CANCEL_ORDER]
    assert after_request[-1].status.value == "prepared"
    if supersede_with_nonempty:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now+5)):
            waiting_cancel = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now+5)
        assert waiting_cancel.disposition is (MaterializationDisposition.OWNER_PAUSED if pause_owner and not early_resume else MaterializationDisposition.WAITING_VACUUM), waiting_cancel
        if not pause_owner or early_resume:
            assert waiting_cancel.reason_code == "VACUUM_CANCEL_NOT_DISPATCHED"
    venue.now_ms = now+6
    dispatch_request = DispatchCommandRequest(worker_id=f"natural-{group}-cancel-dispatch",
        ticket_id=issued.ticket_id,now_ms=now+6,lease_until_ms=now+30_000,timeout_seconds=1)
    if unknown_cancel:
        from src.trading_kernel.application.recover_unknown_command import (
            RecoverUnknownCommandRequest,
            recover_unknown_command,
        )
        from src.trading_kernel.domain.commands import (
            ExchangeCommandResult,
            ExchangeCommandStatus,
        )
        from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot

        async def unknown_execution(command_request):
            async with PostgresKernelUnitOfWork(database) as uow:
                durable = await uow.exchange_commands.get(command_request.command_id)
            assert durable is not None and durable.status is ExchangeCommandStatus.CLAIMED
            assert command_request.kind is ExchangeCommandKind.CANCEL_ORDER
            venue.calls.append(command_request)
            return ExchangeCommandResult(status=ExchangeCommandStatus.OUTCOME_UNKNOWN,
                observed_at_ms=now+6,reason="recording_cancel_response_lost")

        with patch.object(venue,"execute",new=unknown_execution):
            dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,dispatch_request)
        assert dispatched.status.value == "outcome_unknown", dispatched
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now+7)):
            blocked = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now+7)
        assert blocked.disposition is (MaterializationDisposition.OWNER_PAUSED if pause_owner and not early_resume else MaterializationDisposition.WAITING_VACUUM), blocked
        if not pause_owner or early_resume:
            assert blocked.reason_code == "VACUUM_DRAIN_UNKNOWN_OUTCOME"
        async with PostgresKernelUnitOfWork(database) as uow:
            held = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
            assert held == original_vacuum
            assert await uow.strategy_universes.get_generation_universe_targets(original_vacuum.source_generation_id) == ()
            assert await uow.instrument_selection.get_generic_materialization_generation(
                GenericMaterializationGeneration.id_for_snapshot(empty.selection_snapshot_id)) is None
            held_commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
        no_resend = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
            dispatch_request.model_copy(update={"now_ms":now+7}))
        assert no_resend.status.value == "no_command", no_resend
        assert len(venue.calls) == 2
        unknown_command = held_commands[-1]

        class CancelTruth:
            async def lookup_command_truth(self, truth_request):
                assert truth_request.command_id == unknown_command.command_id
                assert truth_request.kind is ExchangeCommandKind.CANCEL_ORDER
                assert truth_request.payload.exchange_order_id == aggregate.entry_exchange_order_id
                assert truth_request.exchange_instrument_id == ticket.identity.netting_domain.exchange_instrument_id
                assert truth_request.position_side == ticket.identity.netting_domain.position_side
                assert truth_request.account_id == ticket.identity.netting_domain.account_id
                return VenueTruthSnapshot(lookup_status="absent",position_quantity=Decimal(0),
                    matching_fill_quantity=Decimal(0),regular_open_client_order_ids=(),
                    conditional_open_client_order_ids=(),observed_at_ms=now+7)

        recovered = await recover_unknown_command(lambda:PostgresKernelUnitOfWork(database),CancelTruth(),
            RecoverUnknownCommandRequest(command_id=unknown_command.command_id,now_ms=now+7,
                visibility_deadline_ms=now+6,timeout_seconds=1))
        assert recovered.status.value == "reconciled_absent", recovered
    else:
        dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,dispatch_request)
        assert dispatched.status.value == "accepted", dispatched
    flat = PositionSnapshot(netting_domain=ticket.identity.netting_domain,
        quantity=partial_qty,average_entry_price=ticket.entry_reference_price if partial_fill else None,
        open_orders=(),observed_at_ms=now+7)
    async with PostgresKernelUnitOfWork(database) as uow:
        absence = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
            strategy_group_id=group,selection_spec_id=empty.selection_spec_id,
            now_ms=now+7,ticket_id=issued.ticket_id,position_snapshot=flat))
    assert absence.status is VacuumDrainStatus.ORDER_ABSENCE_RECORDED, absence
    async with PostgresKernelUnitOfWork(database) as uow:
        closed = await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(
            strategy_group_id=group,selection_spec_id=empty.selection_spec_id,now_ms=now+8,
            ticket_id=issued.ticket_id,position_snapshot=flat.model_copy(update={"observed_at_ms":now+8})))
        reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
        still_active = await uow.entry_admission.has_active_ticket_in_domain(
            ticket.identity.netting_domain.key())
    if partial_fill:
        assert closed.status is VacuumDrainStatus.PARTIAL_RETAINED_PROTECTION_REQUESTED, closed
        assert reservation is not None and reservation.status == "active" and still_active
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now+9)):
            waiting_protection = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now+9)
        assert waiting_protection.disposition is (MaterializationDisposition.OWNER_PAUSED if pause_owner and not early_resume else MaterializationDisposition.WAITING_VACUUM), waiting_protection
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.strategy_universes.get_generation_universe_targets(original_vacuum.source_generation_id) == ()
            assert await uow.instrument_selection.get_generic_materialization_generation(
                GenericMaterializationGeneration.id_for_snapshot(empty.selection_snapshot_id)) is None
        venue.now_ms = now+10
        stop = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
            dispatch_request.model_copy(update={"now_ms":now+10}))
        assert stop.status.value == "accepted", stop
        async with PostgresKernelUnitOfWork(database) as uow:
            protected = await uow.aggregates.get(issued.ticket_id)
            assert protected is not None and protected.position_qty == partial_qty
            assert protected.initial_stop_exchange_order_id is not None
            assert protected.status is AggregateStatus.POST_FILL_RISK_PENDING
            assert await uow.instrument_selection.entry_vacuum_has_drain_blockers(strategy_group_id=group)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now+11)):
            waiting_stress = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now+11)
        assert waiting_stress.disposition is (MaterializationDisposition.OWNER_PAUSED if pause_owner and not early_resume else MaterializationDisposition.WAITING_VACUUM), waiting_stress
        from src.trading_kernel.domain.cross_margin_stress import (
            evaluate_cross_margin_stress,
        )
        from src.trading_kernel.domain.events import PostFillStressAssessed
        from src.trading_kernel.domain.reducer import reduce_event
        from tests.trading_kernel.support.capacity_claims import make_stress_evidence

        # Recorded local risk fixture evaluates the actual partial quantity.
        # It is evidence input only; never rewrite the immutable Ticket.
        async with PostgresKernelUnitOfWork(database) as uow:
            pending = await uow.aggregates.get(issued.ticket_id)
            assert pending is not None
            base_stress = make_stress_evidence(pending.ticket)
            actual_stress = evaluate_cross_margin_stress(base_stress.request.model_copy(update={
                "projected_instrument_positions":tuple(position.model_copy(update={"quantity":partial_qty})
                    for position in base_stress.request.projected_instrument_positions)}))
            stress = PostFillStressAssessed(
                event_id=f"event:{issued.ticket_id}:{pending.last_event_sequence+1}",
                ticket_id=issued.ticket_id,sequence=pending.last_event_sequence+1,
                occurred_at_ms=now+12,status="passed",
                evidence=actual_stress,
                owner_policy_id=pending.ticket.owner_policy_id,
                owner_policy_version=pending.ticket.owner_policy_version,
                filled_qty=pending.position_qty,average_fill_price=pending.average_fill_price,
                initial_stop_price=pending.ticket.initial_stop_price,
                initial_stop_exchange_order_id=pending.initial_stop_exchange_order_id)
            await uow.commit_reduction(event=stress,reduction=reduce_event(pending,stress),expected_version=pending.version)
            assert not await uow.instrument_selection.entry_vacuum_has_drain_blockers(strategy_group_id=group)
    else:
        assert closed.status is VacuumDrainStatus.ZERO_FILL_CLOSED, closed
        assert reservation is not None and reservation.status == "released" and not still_active
    resume_offset = 13 if partial_fill else 9
    if pause_owner:
        actual_execute=sa.ext.asyncio.AsyncConnection.execute
        if early_resume:
            async def corrupt_early_resume_record(connection,statement,*args,**kwargs):
                if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
                    params=statement.compile().params
                    if params.get("event_type")=="OWNER_PAUSED" and params.get("payload",{}).get("resumed_before_drain"):
                        statement=statement.values(payload={**params["payload"],"owner_resume_authorization_id":"authorization:forged"})
                return await actual_execute(connection,statement,*args,**kwargs)
            checked_at=now+resume_offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=checked_at)), patch.object(
                sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_early_resume_record), pytest.raises(sa.exc.DBAPIError,match="Early Resume drain completion requires exact"):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=paused_request,clock_ms=lambda:checked_at)
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=empty.selection_spec_id)==original_vacuum
                assert await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)==abandoned
                assert await uow.instrument_selection.get_current_generic_authority(empty.selection_spec_id)==current
        async def corrupt_pause_drain_completion(connection,statement,*args,**kwargs):
            if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
                params=statement.compile().params
                if params.get("event_type")=="OWNER_PAUSED" and params.get("payload",{}).get("entry_drain_complete"):
                    statement=statement.values(payload={"entry_drain_complete":"true" if corrupt_pause_completion=="string" else False})
            return await actual_execute(connection,statement,*args,**kwargs)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now+resume_offset)):
            if corrupt_pause_completion:
                with patch.object(sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_pause_drain_completion):
                    paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=paused_request,clock_ms=lambda:now+resume_offset)
            else:
                paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=paused_request,clock_ms=lambda:now+resume_offset)
        assert paused.disposition in ({MaterializationDisposition.OWNER_PAUSED,MaterializationDisposition.WAITING_VACUUM} if early_resume else {MaterializationDisposition.OWNER_PAUSED})
        async with PostgresKernelUnitOfWork(database) as uow:
            drained=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
            assert drained.state is StrategyEntryVacuumState.OWNER_PAUSED and drained.drained_at_ms==now+resume_offset
            assert await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)==abandoned
            owner=await uow.owner_controls.get_strategy_control(group)
            if not early_resume:
                await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                    request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_after_exact_entry_drain",
                        idempotency_key=f"resume-real-drain:{group}:{unknown_cancel}:{partial_fill}",owner_identity="owner",now_ms=now+resume_offset+1),authentication_strength="totp_step_up")
        resume_offset+=2
        supersede_with_nonempty=paused_nonempty_recovery
        if corrupt_pause_completion:
            checked_at=now+resume_offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=checked_at)), pytest.raises(
                SelectionJobConflict,match="Owner Pause completion proof missing"):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:checked_at)
            with pytest.raises(sa.exc.DBAPIError,match="Owner Pause EMPTY requires exact"):
                async with database.begin() as conn:
                    await conn.execute(sa.text("INSERT INTO brc_strategy_entry_vacuum_events "
                        "(entry_vacuum_event_id,entry_vacuum_id,event_sequence,event_type,payload,occurred_at_ms) "
                        "VALUES (:event,:id,:version,'VALID_EMPTY_INTENT',CAST(:payload AS jsonb),:at)"),
                        {"event":f"vacuum-event:{drained.entry_vacuum_id}:{drained.projection_version+1}","id":drained.entry_vacuum_id,
                            "version":drained.projection_version+1,"at":checked_at,"payload":json.dumps({"selection_snapshot_id":empty.selection_snapshot_id,
                                "intended_authority_outcome":"VALID_EMPTY","supersedes_owner_pause":True})})
                    await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='DRAINING_ENTRY',source_generation_id=NULL,"
                        "period_anchor_ms=:period,first_blocker='NO_SELECTION_READY_MEMBERS',projection_version=projection_version+1 WHERE entry_vacuum_id=:id"),
                        {"period":empty.feature_cutoff_at_ms,"id":drained.entry_vacuum_id})
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=empty.selection_spec_id)==drained
                assert await uow.instrument_selection.get_current_generic_authority(empty.selection_spec_id)==current
                assert await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)==abandoned
            return
    for offset in range(resume_offset,resume_offset+3):
        at = now+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            negative = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,
                clock_ms=lambda at=at:at)
        if negative.disposition in {MaterializationDisposition.VALID_EMPTY,MaterializationDisposition.GENERATION_MATERIALIZING}:
            break
    assert negative.disposition is (MaterializationDisposition.GENERATION_MATERIALIZING
        if supersede_with_nonempty else MaterializationDisposition.VALID_EMPTY), negative
    async with PostgresKernelUnitOfWork(database) as uow:
        terminal = await uow.aggregates.get(issued.ticket_id)
        frozen = await uow.tickets.get(issued.ticket_id)
        final_commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
        authority = await uow.instrument_selection.get_current_generic_authority(empty.selection_spec_id)
    assert terminal is not None
    if partial_fill:
        assert terminal.position_qty == partial_qty and terminal.initial_stop_exchange_order_id is not None
        assert terminal.entry_materialization_kind == "VACUUM_PARTIAL_RETAINED"
        assert terminal.ticket.model_dump(exclude={"status"}) == ticket.model_dump(exclude={"status"})
    else:
        assert terminal.status is AggregateStatus.ENTRY_RECONCILED_ABSENT
    assert frozen is not None and frozen.selection_authority_id == current.authority.selection_authority_id
    assert authority is not None
    if supersede_with_nonempty:
        assert authority == current
        async with PostgresKernelUnitOfWork(database) as uow:
            inherited = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=empty.selection_spec_id)
            superseded = await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)
        assert inherited is not None and inherited.entry_vacuum_id == original_vacuum.entry_vacuum_id
        assert inherited.fenced_at_ms == original_vacuum.fenced_at_ms and inherited.drained_at_ms is not None
        assert superseded is not None and superseded.lifecycle_state.value == ("ABANDONED" if pause_owner else "SUPERSEDED")
        if pause_owner:
            assert superseded==abandoned
        if paused_nonempty_recovery:
            for offset in (resume_offset+3,resume_offset+4,resume_offset+5):
                recovery_at=now+offset
                async with PostgresKernelUnitOfWork(database) as uow:
                    targets=await uow.strategy_universes.get_generation_universe_targets(negative.materialization_generation_id)
                if targets:
                    await make_warming_ready(database,universe_version_id=targets[0].universe_version_id,
                        warm_closed_bar_time_ms=recovery_at//HOUR*HOUR,valid_until_ms=recovery_at+HOUR)
                    if group in {"MPG-001","MI-001"}:
                        template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                        shift=recovery_at//HOUR*HOUR-template.trigger_candle_close_time_ms
                        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
                        projection=build_comparative_universe_projection(event_spec_id=empty_source.spec.event_spec_id,universe_version_id=targets[0].universe_version_id,
                            strategy_group_id=group,exchange_instrument_ids=empty_source.spec.candidate_ids,closed_bar_time_ms=recovery_at//HOUR*HOUR,
                            lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in empty_source.spec.candidate_ids))
                        async with PostgresKernelUnitOfWork(database) as uow:
                            await uow.strategy_universes.save_comparative_projection(projection)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=recovery_at)):
                    recovered=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda recovery_at=recovery_at:recovery_at)
            assert recovered.disposition is MaterializationDisposition.ACTIVE_NEW,recovered
            async with PostgresKernelUnitOfWork(database) as uow:
                active=await uow.instrument_selection.get_current_generic_authority(empty.selection_spec_id)
                assert isinstance(active.authority,GenericRecoveryAuthority)
                assert active.authority.recovery_proof.recovery_close_plan.reason=="AUTHORITY_GAP"
                assert active.authority.first_eligible_close_time_ms>recovery_at
                assert active.authority.recovery_proof.episode_rebase_required
                assert await uow.instrument_selection.get_generic_materialization_generation(original_vacuum.source_generation_id)==abandoned
                assert (await uow.strategy_universes.get_current(empty_source.spec.event_spec_id)).universe_version_id!=current.authority.event_binding.universe_version_id
    else:
        assert authority.authority.authority_outcome == "VALID_EMPTY"
    if partial_fill:
        assert sum(command.kind is ExchangeCommandKind.ENTRY for command in final_commands) == 1
        assert sum(command.kind is ExchangeCommandKind.CANCEL_ORDER for command in final_commands) == 1
        assert sum(command.kind is ExchangeCommandKind.INITIAL_STOP for command in final_commands) == 1
        assert len(venue.calls)==3
    else:
        assert [command.kind for command in final_commands] == [ExchangeCommandKind.ENTRY,ExchangeCommandKind.CANCEL_ORDER]
        assert len(venue.calls)==2
    assert entry_dispatched_at_ms<vacuum.fenced_at_ms
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_runtime_incidents WHERE status='open'")) == 0
    if partial_fill:
        from src.trading_kernel.application.maintain_ticket_lifecycle import (
            LifecycleMaintenanceRequest,
            TicketLifecycleFacts,
            maintain_ticket_lifecycle,
        )
        from src.trading_kernel.application.reconcile_ticket import (
            ReconcileTicketRequest,
            reconcile_ticket,
        )
        from src.trading_kernel.application.settle_ticket import (
            RecordTradeReviewRequest,
            SettleTicketRequest,
            record_trade_review,
            settle_ticket,
        )

        async def safety_dispatch(offset):
            venue.now_ms = now+offset
            result = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                dispatch_request.model_copy(update={"now_ms":now+offset}))
            assert result.status.value == "accepted", result

        await safety_dispatch(20)
        async with PostgresKernelUnitOfWork(database) as uow:
            protected = await uow.aggregates.get(issued.ticket_id)
            assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
            assert protected.tp1_target_qty is not None and Decimal(0)<protected.tp1_target_qty<partial_qty
            runner = await maintain_ticket_lifecycle(uow,LifecycleMaintenanceRequest(ticket_id=issued.ticket_id,
                facts=TicketLifecycleFacts(position_quantity=partial_qty-protected.tp1_target_qty,
                    tp1_filled_quantity=protected.tp1_target_qty,tp1_average_fill_price=ticket.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal("0.01"),exit_taker_fee_rate=Decimal("0.001"),
                    price_tick=Decimal("0.01"),market_facts=None,observed_at_ms=now+21),now_ms=now+21))
        assert runner.status.value == "break_even_requested", runner
        await safety_dispatch(22)
        await safety_dispatch(23)
        truly_flat = flat.model_copy(update={"quantity":Decimal(0),"average_entry_price":None,
            "observed_at_ms":now+24})
        async with PostgresKernelUnitOfWork(database) as uow:
            external_flat = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,snapshot=truly_flat))
        assert external_flat.status.value == "external_flat_incident", external_flat
        await safety_dispatch(25)
        async with PostgresKernelUnitOfWork(database) as uow:
            matched = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
                snapshot=truly_flat.model_copy(update={"observed_at_ms":now+26})))
            settled = await settle_ticket(uow,SettleTicketRequest(ticket_id=issued.ticket_id,settled_at_ms=now+27))
            reviewed = await record_trade_review(uow,RecordTradeReviewRequest(ticket_id=issued.ticket_id,
                review_id=f"review:selection-partial-{group}",outcome="closed",metrics={"realized_pnl":"1.25"},
                decision_impact={"strategy_action":"keep"},recorded_at_ms=now+28))
            terminal = await uow.aggregates.get(issued.ticket_id)
            reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
            assert await uow.incidents.get_open_for_ticket(issued.ticket_id) is None
            assert not await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
            final_commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
        assert matched.status.value == "matched" and settled.status.value == "budget_settled"
        assert reviewed.status.value == "review_recorded"
        assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
        assert terminal.ticket.selection_authority_id == current.authority.selection_authority_id
        assert reservation is not None and reservation.status == "released"
        assert sum(command.kind is ExchangeCommandKind.ENTRY for command in final_commands) == 1


@pytest.mark.asyncio
async def test_generic_continuity_precedes_selection_result_and_has_one_miss_budget(database: AsyncEngine) -> None:
    first_source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,"CPM-RO-001",False,durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        initial = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
    assert initial is not None
    period_anchor = first_source.feature_cutoff_at_ms+first_source.spec.cadence_hours*HOUR
    boundary = period_anchor+HOUR
    at = boundary+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=boundary,valid_until_ms=at+HOUR)
    request = CoordinateGenericPeriodRequest(strategy_group_id="CPM-RO-001",
        selection_spec_id=first_source.spec.selection_spec_id,period_anchor_ms=period_anchor,
        worker_id="continuity-before-selector")
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' "
            "WHERE strategy_group_id='CPM-RO-001'"))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        paused = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at)
    assert paused.disposition is MaterializationDisposition.BLOCKED
    assert paused.reason_code=="GENERIC_CONTINUITY_OWNER_OR_MODE_BLOCKED"
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='enabled' "
            "WHERE strategy_group_id='CPM-RO-001'"))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        granted = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at)
    assert granted.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, granted
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        active = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id="CPM-RO-001",selection_spec_id=first_source.spec.selection_spec_id)
    assert current is not None and current.authority.authority_outcome=="PRE_FENCE_CONTINUITY"
    assert current.authority.event_binding.universe_version_id==uid
    assert current.authority.continuity_source_authority_id==initial.authority.selection_authority_id
    assert current.authority.membership_freshness.source_snapshot_id==first_snapshot.selection_snapshot_id
    assert current.authority.membership_freshness.state.value=="GRACE"
    assert current.authority.membership_freshness.membership_valid_until_ms==initial.authority.membership_freshness.membership_valid_until_ms
    assert active is not None and active.universe_version_id==uid
    assert vacuum is None
    source_proof = current.authority.current_close_proof
    forged = current.authority.model_copy(update={
        "selection_authority_id":"authority:forged-continuity",
        "continuity_source_authority_id":"authority:forged-source",
        "current_close_proof":source_proof.model_copy(update={
            "source_selection_authority_id":"authority:forged-source"})})
    with pytest.raises(sa.exc.DBAPIError,match="Generic continuity proof differs"):
        async with database.begin() as conn:
            await conn.execute(sa.insert(selection_session_authorities).values(
                **generic_authority_storage_values(forged)))
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_observation_authority,
    )
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        observation = await resolve_selection_observation_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=boundary,
            now_ms=at,allow_current_as_birth=True,lock_current=True)
    assert observation.allowed, observation
    assert observation.selection_authority_id==current.authority.selection_authority_id
    template = cpm_long_snapshot()
    shift = boundary-template.trigger_candle_close_time_ms
    class ContinuityMarket:
        async def fetch_closed_candles(self, request):
            candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                "close_time_ms":c.close_time_ms+shift}) for c in candles)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=boundary+2)):
        produced = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),ContinuityMarket(),
            ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=boundary,
                attempted_at_ms=boundary+2))
    assert produced.status is ObservationStatus.SIGNAL_CREATED, produced
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        entry = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=current.authority.selection_authority_id,
            observed_close_time_ms=boundary,now_ms=boundary+3,
            allow_current_as_birth=False,lock_current=True)
    assert entry.allowed, entry
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at+3)):
        repeated = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at+3)
    assert repeated.selection_authority_id==granted.selection_authority_id
    second_anchor = period_anchor+first_source.spec.cadence_hours*HOUR
    second_boundary = second_anchor+HOUR
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=second_boundary+1)):
        stale = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request.model_copy(update={"period_anchor_ms":second_anchor}),
            clock_ms=lambda:second_boundary+1)
    assert stale.disposition is MaterializationDisposition.BLOCKED
    assert stale.reason_code == "GENERIC_CONTINUITY_MEMBERSHIP_STALE"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_jobs_current"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_generations"))==1


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","BRF2-001","MPG-001","MI-001"])
@pytest.mark.parametrize("activation_commits_first", [False,True])
@pytest.mark.parametrize("detector_triggers", [False,True])
async def test_generic_replacement_revalidates_inflight_old_observation_before_any_fact_or_cursor(
    database: AsyncEngine, group: str, activation_commits_first: bool, detector_triggers: bool,
) -> None:
    source,first,_,old_uid=await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    shifted=next_input(source)
    chosen=first.selected_members[0]
    next_source=shifted.model_copy(update={"predecessor_snapshot":first,"member_windows":tuple(
        qualify_window(window.model_copy(update={"candles":shifted.member_windows[0].candles}),window.exchange_instrument_id==chosen)
        for window in shifted.member_windows)})
    snapshot=compute_generic_selection(next_source)
    assert snapshot.selected_members!=first.selected_members
    close=snapshot.effective_from_ms
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=next_source.decision_at_ms,source_observed_at_ms=next_source.source_observed_at_ms)
    await make_warming_ready(database,universe_version_id=old_uid,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
    async with database.connect() as conn:
        scope_id=await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND exchange_instrument_id=:member"),
            {"uid":old_uid,"member":chosen})
    template={"CPM-RO-001":cpm_long_snapshot,"BRF2-001":brf2_short_snapshot,"MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot}[group]()
    if not detector_triggers:
        template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot() if group=="MI-001" else cpm_flat_snapshot()
    delta=close-template.trigger_candle_close_time_ms
    candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
    async def comparison(uid):
        if group in {"MPG-001","MI-001"}:
            flat=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
            flat_delta=close-flat.trigger_candle_close_time_ms
            flat_candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+flat_delta,"close_time_ms":c.close_time_ms+flat_delta}) for c in flat.candles_1h)
            projection=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=uid,strategy_group_id=group,
                exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,
                freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles if m==chosen else flat_candles) for m in source.spec.candidate_ids))
            async with PostgresKernelUnitOfWork(database) as uow:
                binding=await uow.instrument_selection.get_comparison_universe_binding(source.spec.event_spec_id)
                await uow.strategy_universes.save_comparative_projection(projection.model_copy(update={"comparison_transition_revision":binding.comparison_transition_revision if uid==old_uid else 0}))
    await comparison(old_uid)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+1)):
        continuity=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                period_anchor_ms=snapshot.feature_cutoff_at_ms,worker_id="inflight-continuity"),clock_ms=lambda:close+1)
    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY,continuity
    network_started=asyncio.Event()
    release_market=asyncio.Event()
    reads=0
    @asynccontextmanager
    async def delayed_observation_uow():
        nonlocal reads
        reads+=1
        initial_read=reads==1
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
        if initial_read:
            # The read transaction has committed; activation must never wait
            # on a market-I/O transaction, including MI's cached-only path.
            network_started.set()
            await asyncio.wait_for(release_market.wait(),timeout=30)
    class Market:
        async def fetch_closed_candles(self,request):
            network_started.set()
            await asyncio.wait_for(release_market.wait(),timeout=30)
            path=template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in path)
    key=build_episode_domain_key(event_spec_id=source.spec.event_spec_id,exchange_instrument_id=chosen,position_side=source.spec.position_side)
    async with PostgresKernelUnitOfWork(database) as uow:
        before=await uow.signals.lock_exposure_episode(key)
    async with database.connect() as conn:
        before_facts=(await conn.execute(sa.text("SELECT * FROM brc_facts_current WHERE runtime_scope_id=:id ORDER BY fact_definition_id"),{"id":scope_id})).mappings().all()
    observation=None
    if not activation_commits_first:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+2)):
            observation=asyncio.create_task(observe_strategy_scope(delayed_observation_uow,Market(),ObservationRequest(
                runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=close,attempted_at_ms=close+2)))
            await asyncio.wait_for(network_started.wait(),timeout=10)
    request=CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="inflight-replacement")
    try:
        for offset in range(3,11):
            tick=close+offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
                step=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda tick=tick:tick)
            if step.disposition is MaterializationDisposition.TARGET_WARMING:
                break
        assert step.disposition is MaterializationDisposition.TARGET_WARMING,step
        async with PostgresKernelUnitOfWork(database) as uow:
            target=(await uow.strategy_universes.get_generation_universe_targets(step.materialization_generation_id))[0]
        await make_warming_ready(database,universe_version_id=target.universe_version_id,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
        await comparison(target.universe_version_id)
        for offset in (11,12):
            tick=close+offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
                if activation_commits_first and offset==12:
                    written=asyncio.Event()
                    release_activation=asyncio.Event()
                    waiter_started=asyncio.Event()
                    pids={}
                    @asynccontextmanager
                    async def activation_uow(pids=pids,written=written,release_activation=release_activation):
                        async with PostgresKernelUnitOfWork(database) as uow:
                            yield uow
                            state=await uow._connection.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:id"),{"id":target.universe_version_id})
                            if state=="active":
                                pids["first"]=await uow._connection.scalar(sa.text("SELECT pg_backend_pid()"))
                                written.set()
                                await asyncio.wait_for(release_activation.wait(),timeout=15)
                    @asynccontextmanager
                    async def waiting_observation_uow(pids=pids,waiter_started=waiter_started):
                        async with PostgresKernelUnitOfWork(database) as uow:
                            pids["waiter"]=await uow._connection.scalar(sa.text("SELECT pg_backend_pid()"))
                            waiter_started.set()
                            yield uow
                    activation=asyncio.create_task(coordinate_selection_materialization_once(uow_factory=activation_uow,request=request,clock_ms=lambda tick=tick:tick))
                    done,_=await asyncio.wait({activation,asyncio.create_task(written.wait())},timeout=10,return_when=asyncio.FIRST_COMPLETED)
                    if activation in done:
                        await activation
                        raise AssertionError("activation returned before its commit barrier")
                    assert written.is_set()
                    observation=asyncio.create_task(observe_strategy_scope(waiting_observation_uow,Market(),ObservationRequest(
                        runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=close,attempted_at_ms=close+13)))
                    try:
                        await asyncio.wait_for(waiter_started.wait(),timeout=10)
                        deadline=asyncio.get_running_loop().time()+3
                        while True:
                            async with database.connect() as conn:
                                blockers=await conn.scalar(sa.text("SELECT pg_blocking_pids(:pid)"),{"pid":pids["waiter"]})
                            if pids["first"] in blockers:
                                break
                            assert asyncio.get_running_loop().time()<deadline,(pids,blockers)
                            await asyncio.sleep(0.01)
                    finally:
                        release_activation.set()
                    step=await asyncio.wait_for(activation,timeout=10)
                else:
                    step=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda tick=tick:tick)
        assert step.disposition is MaterializationDisposition.ACTIVE_NEW,step
    finally:
        release_market.set()
        if observation is not None and not observation.done() and ("step" not in locals() or step.disposition is not MaterializationDisposition.ACTIVE_NEW):
            observation.cancel()
            await asyncio.gather(observation,return_exceptions=True)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+13)):
        assert observation is not None
        observed=await asyncio.wait_for(observation,timeout=10)
    assert observed.status is ObservationStatus.INVALID,observed
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.signals.lock_exposure_episode(key)==before
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==target.universe_version_id
        current=await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert isinstance(current.authority,GenericSelectionAuthority)
        assert current.authority.first_eligible_close_time_ms==close
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==0
        assert (await conn.execute(sa.text("SELECT * FROM brc_facts_current WHERE runtime_scope_id=:id ORDER BY fact_definition_id"),{"id":scope_id})).mappings().all()==before_facts
        new_scope=await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND exchange_instrument_id=:member"),
            {"uid":target.universe_version_id,"member":chosen})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+14)):
        fresh=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),Market(),ObservationRequest(
            runtime_scope_id=new_scope,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=close,attempted_at_ms=close+14))
    if not detector_triggers:
        assert fresh.status is ObservationStatus.NO_SIGNAL,fresh
    elif group in {"MPG-001","MI-001"}:
        assert fresh.status is ObservationStatus.NO_SIGNAL and fresh.detector_reason=="COMPARISON_REBASE_REQUIRED",fresh
    else:
        assert fresh.status is ObservationStatus.SIGNAL_CREATED,fresh
        async with PostgresKernelUnitOfWork(database) as uow:
            signal=await uow.signals.get(fresh.signal_event_id)
            assert signal.selection_authority_id==step.selection_authority_id and signal.universe_version_id==target.universe_version_id


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","BRF2-001","MPG-001","MI-001"])
@pytest.mark.parametrize("consume_first", [True,False])
async def test_generic_same_close_observation_and_no_change_grant_serialize(
    database: AsyncEngine, group: str, consume_first: bool,
) -> None:
    comparative = group in {"MPG-001","MI-001"}
    source,first,_,uid = await _exercise_generic_generation(database,group,comparative,
        durable=True,first_activation=True,natural_selection=True)
    successor_source = next_input(source)
    successor = compute_generic_selection(successor_source)
    assert successor.selected_members==first.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(successor,
            decision_at_ms=successor_source.decision_at_ms,source_observed_at_ms=successor_source.source_observed_at_ms)
    close = successor.effective_from_ms
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
    if comparative:
        async with PostgresKernelUnitOfWork(database) as uow:
            initial = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        initial_close = first.effective_from_ms
        flat = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        initial_delta = initial_close-flat.trigger_candle_close_time_ms
        flat_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+initial_delta,
            "close_time_ms":c.close_time_ms+initial_delta}) for c in flat.candles_1h)
        initial_projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=uid,strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,
            closed_bar_time_ms=initial_close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=flat_candles) for member in source.spec.candidate_ids)).model_copy(update={
                "comparison_transition_revision":initial.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(initial_projection)
        class FlatMarket:
            async def fetch_closed_candles(self,request):
                candles = flat.candles_1h if request.timeframe=="1h" else flat.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+initial_delta,
                    "close_time_ms":c.close_time_ms+initial_delta}) for c in candles)
        armed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),FlatMarket(),ObservationRequest(
            runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=initial_close,attempted_at_ms=initial.authority.created_at_ms+1))
        assert armed.status is ObservationStatus.NO_SIGNAL, armed
        template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        delta = close-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=uid,strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,
            closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in source.spec.candidate_ids)).model_copy(update={
                "comparison_transition_revision":initial.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
    await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+1)):
        continued = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                period_anchor_ms=successor.feature_cutoff_at_ms,worker_id="concurrent-continuity"),clock_ms=lambda:close+1)
    assert continued.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
    template = {"CPM-RO-001":cpm_long_snapshot,"BRF2-001":brf2_short_snapshot,
        "MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot}[group]()
    delta = close-template.trigger_candle_close_time_ms
    class Market:
        async def fetch_closed_candles(self,request):
            candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)
    first_written = asyncio.Event()
    release_first = asyncio.Event()
    waiter_started = asyncio.Event()
    pids = {}
    @asynccontextmanager
    async def observation_uow():
        async with PostgresKernelUnitOfWork(database) as uow:
            assert uow._connection is not None
            pid = await uow._connection.scalar(sa.text("SELECT pg_backend_pid()"))
            if not consume_first:
                pids["waiter"] = pid
                waiter_started.set()
            yield uow
            if consume_first and await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==1:
                pids["first"] = pid
                first_written.set()
                await asyncio.wait_for(release_first.wait(),timeout=10)
    @asynccontextmanager
    async def grant_uow():
        async with PostgresKernelUnitOfWork(database) as uow:
            assert uow._connection is not None
            pid = await uow._connection.scalar(sa.text("SELECT pg_backend_pid()"))
            if consume_first:
                pids["waiter"] = pid
                waiter_started.set()
            yield uow
            if not consume_first:
                pids["first"] = pid
                first_written.set()
                await asyncio.wait_for(release_first.wait(),timeout=10)
    async def observe():
        return await observe_strategy_scope(observation_uow,Market(),ObservationRequest(runtime_scope_id=scope_id,
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=close,attempted_at_ms=close+5))
    async def grant():
        return await coordinate_selection_materialization_once(uow_factory=grant_uow,
            request=CoordinateGenericSnapshotRequest(selection_snapshot_id=successor.selection_snapshot_id,worker_id="concurrent-no-change"),
            clock_ms=lambda:close+4)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+4)):
        first_task = asyncio.create_task(observe() if consume_first else grant())
        await asyncio.wait_for(first_written.wait(),timeout=10)
        second_task = asyncio.create_task(grant() if consume_first else observe())
        try:
            await asyncio.wait_for(waiter_started.wait(),timeout=10)
            deadline = asyncio.get_running_loop().time()+3
            while True:
                async with database.connect() as conn:
                    blockers = await conn.scalar(sa.text("SELECT pg_blocking_pids(:pid)"),{"pid":pids["waiter"]})
                if pids["first"] in blockers:
                    break
                assert asyncio.get_running_loop().time()<deadline, (pids,blockers)
                await asyncio.sleep(0.01)
        finally:
            release_first.set()
        results = await asyncio.wait_for(asyncio.gather(first_task,second_task,return_exceptions=True),timeout=10)
    observed,granted = results if consume_first else results[::-1]
    assert observed.status is ObservationStatus.SIGNAL_CREATED, observed
    if consume_first:
        assert isinstance(granted,RuntimeError) and str(granted)=="Generic grant close was already consumed", granted
    else:
        assert granted.disposition is MaterializationDisposition.NO_CHANGE, granted
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        signal = await uow.signals.get(observed.signal_event_id)
    assert current.authority.selection_authority_id==(continued.selection_authority_id if consume_first else granted.selection_authority_id)
    assert signal.selection_authority_id==current.authority.selection_authority_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities "
            "WHERE selection_snapshot_id=:snapshot AND authority_outcome='NO_CHANGE'"),
            {"snapshot":successor.selection_snapshot_id})==int(not consume_first)
    repeated = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),Market(),
        ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=close,attempted_at_ms=close+6))
    assert repeated.signal_event_id in {None,observed.signal_event_id}
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==1


@pytest.mark.asyncio
async def test_generic_continuity_is_replaced_by_same_period_no_change(database: AsyncEngine) -> None:
    first_source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,"CPM-RO-001",False,durable=True,first_activation=True,natural_selection=True)
    next_source = next_input(first_source)
    next_snapshot = compute_generic_selection(next_source)
    assert next_snapshot.selected_members == first_snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(next_snapshot,
            decision_at_ms=next_source.decision_at_ms,source_observed_at_ms=next_source.source_observed_at_ms)
    at = next_snapshot.effective_from_ms+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=next_snapshot.effective_from_ms,valid_until_ms=at+HOUR)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        continuity = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id="CPM-RO-001",
                selection_spec_id=first_source.spec.selection_spec_id,
                period_anchor_ms=next_snapshot.feature_cutoff_at_ms,worker_id="period-continuity"),
            clock_ms=lambda:at)
    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at+1)):
        no_change = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericSnapshotRequest(selection_snapshot_id=next_snapshot.selection_snapshot_id,
                worker_id="replace-continuity"),clock_ms=lambda:at+1)
    assert no_change.disposition is MaterializationDisposition.NO_CHANGE, no_change
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id="CPM-RO-001",selection_spec_id=first_source.spec.selection_spec_id)
    assert current is not None and current.authority.authority_outcome=="NO_CHANGE"
    assert current.authority.selection_snapshot_id==next_snapshot.selection_snapshot_id
    assert current.authority.membership_freshness.state.value=="ACTIVE"
    assert vacuum is None


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","BRF2-001","MPG-001","MI-001"])
@pytest.mark.parametrize("fault_stage", [None,"switch_before_claim","switch_between_claim_ticket","switch_before_dispatch","switch_during_dispatch_facts",
    "activated_before_claim","activated_between_claim_ticket","activated_before_dispatch"])
async def test_generic_new_desired_fences_pre_fence_continuity_before_warming(
    database: AsyncEngine, group: str, fault_stage: str | None,
) -> None:
    first_source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    next_source = next_input(first_source)
    next_source = next_source.model_copy(update={
        "predecessor_snapshot":first_snapshot,
        "member_windows":tuple(qualify_window(window.model_copy(update={"candles":next_source.member_windows[0].candles}),window.exchange_instrument_id==next_source.spec.candidate_ids[0])
            for window in next_source.member_windows)})
    class NextSelectionMarket:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            assert event_spec_id==first_source.spec.event_spec_id and len(product_profiles)==24
            return tuple(window.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for window in next_source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            return next(window.candles for window in next_source.member_windows
                if window.exchange_instrument_id==request.exchange_instrument_id)
    selection_tick = next_source.feature_cutoff_at_ms
    def next_selection_clock():
        nonlocal selection_tick
        selection_tick += 1
        return selection_tick
    selected = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=NextSelectionMarket(),
        request=RunInstrumentSelectionRequest(selection_spec_id=next_source.spec.selection_spec_id,
            selection_epoch_id=first_snapshot.selection_epoch_id,
            period_anchor_ms=next_source.feature_cutoff_at_ms,worker_id="next-desired-selector"),
        clock_ms=next_selection_clock)
    assert selected.outcome=="SNAPSHOT_READY", selected
    async with PostgresKernelUnitOfWork(database) as uow:
        next_snapshot = await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
    assert next_snapshot.selected_members and next_snapshot.selected_members!=first_snapshot.selected_members
    e = next_snapshot.effective_from_ms
    member=next(m for m in first_snapshot.selected_members if m!=next_source.spec.candidate_ids[0])
    async def comparative_cache(universe_id,at,*,flat=False):
        if group not in {"MPG-001","MI-001"}:
            return
        template=(mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()) if flat else (
            mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot())
        delta=at-template.trigger_candle_close_time_ms
        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        quiet=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        quiet_delta=at-quiet.trigger_candle_close_time_ms
        quiet_candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+quiet_delta,"close_time_ms":c.close_time_ms+quiet_delta}) for c in quiet.candles_1h)
        projection=build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,universe_version_id=universe_id,strategy_group_id=group,
            exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=at,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles if flat or m==member else quiet_candles) for m in first_source.spec.candidate_ids))
        async with PostgresKernelUnitOfWork(database) as uow:
            binding=await uow.instrument_selection.get_comparison_universe_binding(first_source.spec.event_spec_id)
            await uow.strategy_universes.save_comparative_projection(projection.model_copy(update={"comparison_transition_revision":binding.comparison_transition_revision if universe_id==uid else 0}))
    if group in {"MPG-001","MI-001"}:
        async with database.connect() as conn:
            old_scope=await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND exchange_instrument_id=:member"),{"uid":uid,"member":member})
        await comparative_cache(uid,first_snapshot.effective_from_ms,flat=True)
        quiet=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        delta=first_snapshot.effective_from_ms-quiet.trigger_candle_close_time_ms
        class FlatMarket:
            async def fetch_closed_candles(self,request):
                path=quiet.candles_1h if request.timeframe=="1h" else quiet.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in path)
        async with PostgresKernelUnitOfWork(database) as uow:
            initial=await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=initial.authority.created_at_ms+1)):
            arm=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),FlatMarket(),ObservationRequest(
                runtime_scope_id=old_scope,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=first_snapshot.effective_from_ms,attempted_at_ms=initial.authority.created_at_ms+1))
        assert arm.status is ObservationStatus.NO_SIGNAL,arm
        await comparative_cache(uid,e)
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=e,valid_until_ms=e+HOUR)
    period_request = CoordinateGenericPeriodRequest(strategy_group_id=group,
        selection_spec_id=first_source.spec.selection_spec_id,
        period_anchor_ms=next_snapshot.feature_cutoff_at_ms,worker_id="before-new-desired")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=e+1)):
        continued = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=period_request,clock_ms=lambda:e+1)
    assert continued.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    snapshot_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=next_snapshot.selection_snapshot_id,
        worker_id="fence-continuity")
    if fault_stage is not None:
        async with database.connect() as conn:
            row = (await conn.execute(sa.text("SELECT runtime_scope_id,exchange_instrument_id "
                "FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND exchange_instrument_id=:member "
                "ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid,"member":member})).one()
        template = {"CPM-RO-001":cpm_long_snapshot,"BRF2-001":brf2_short_snapshot,"MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot}[group]()
        delta = e-template.trigger_candle_close_time_ms
        class NaturalMarket:
            async def fetch_closed_candles(self, request):
                candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,
                    "close_time_ms":c.close_time_ms+delta}) for c in candles)
        observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),NaturalMarket(),
            ObservationRequest(runtime_scope_id=row.runtime_scope_id,runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=e,attempted_at_ms=e+2))
        assert observed.status is ObservationStatus.SIGNAL_CREATED, observed

        async def commit_switch_fence():
            activating=fault_stage.startswith("activated_")
            for offset in range(4,24 if activating else 8):
                at = e+offset
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
                    step = await coordinate_selection_materialization_once(
                        uow_factory=lambda:PostgresKernelUnitOfWork(database),request=snapshot_request,
                        clock_ms=lambda at=at:at)
                if activating and step.disposition is MaterializationDisposition.TARGET_WARMING:
                    async with PostgresKernelUnitOfWork(database) as uow:
                        target=(await uow.strategy_universes.get_generation_universe_targets(step.materialization_generation_id))[0]
                    await make_warming_ready(database,universe_version_id=target.universe_version_id,warm_closed_bar_time_ms=e,valid_until_ms=e+HOUR)
                    await comparative_cache(target.universe_version_id,e,flat=True)
                if step.disposition is (MaterializationDisposition.ACTIVE_NEW if activating else MaterializationDisposition.WAITING_VACUUM):
                    break
            assert step.disposition is (MaterializationDisposition.ACTIVE_NEW if activating else MaterializationDisposition.WAITING_VACUUM), step
            async with PostgresKernelUnitOfWork(database) as uow:
                active = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
            if activating:
                assert active.universe_version_id!=uid and vacuum is None
                async with PostgresKernelUnitOfWork(database) as uow:
                    signal=await uow.signals.get(observed.signal_event_id)
                    current=await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
                assert signal.selection_authority_id==continued.selection_authority_id
                assert current.authority.selection_authority_id==step.selection_authority_id
                assert signal.expires_at_ms>e+30 and current.authority.expires_at_ms>e+30
                assert signal.universe_version_id==uid and current.authority.event_binding.universe_version_id==active.universe_version_id
                return
            assert active.universe_version_id==uid
            assert vacuum is not None and vacuum.blocks_new_entry
            assert vacuum.source_generation_id is not None
            async with PostgresKernelUnitOfWork(database) as uow:
                signal = await uow.signals.get(observed.signal_event_id)
                current = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
            assert signal.expires_at_ms>e+8
            assert current.authority.expires_at_ms>e+8
            assert current.authority.selection_authority_id==continued.selection_authority_id

        await _issue_and_dispatch_hourly_natural_entry(database,group=group,
            signal_event_id=observed.signal_event_id,selection_authority_id=continued.selection_authority_id,
            member=row.exchange_instrument_id,universe_version_id=uid,closed_at_ms=e,now_ms=e+3,
            fault_stage=fault_stage,authority_transition=commit_switch_fence)
        return
    steps = []
    for offset in range(2,6):
        at = e+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=snapshot_request,
                clock_ms=lambda at=at:at)
        steps.append(step)
        if step.disposition is MaterializationDisposition.WAITING_VACUUM:
            break
    assert steps[-1].disposition is MaterializationDisposition.WAITING_VACUUM, steps
    async with PostgresKernelUnitOfWork(database) as uow:
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
        current = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        active = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
    assert vacuum is not None and vacuum.blocks_new_entry
    assert current is not None and current.authority.selection_authority_id==continued.selection_authority_id
    assert active is not None and active.universe_version_id==uid
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        fenced = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=continued.selection_authority_id,
            observed_close_time_ms=e,now_ms=e+6,allow_current_as_birth=False,lock_current=True)
    assert not fenced.allowed and fenced.reason_code=="selection_entry_vacuum_open"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_versions "
            "WHERE lifecycle_state IN ('warming','staged')"))==0


@pytest.mark.asyncio
async def test_generic_continuity_refuses_an_already_consumed_close(database: AsyncEngine) -> None:
    source,_,_,uid = await _exercise_generic_generation(
        database,"CPM-RO-001",False,durable=True,first_activation=True,natural_selection=True)
    anchor = source.feature_cutoff_at_ms+source.spec.cadence_hours*HOUR
    close = anchor+HOUR
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
    member = source.spec.candidate_ids[0]
    transition = advance_exposure_episode(contract=strategy_contract_for(source.spec.event_spec_id),
        current=None,detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,
        observed_at_ms=close,exchange_instrument_id=member)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.signals.save_exposure_episode(transition.current,expected_version=0)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=close+1)):
        refused = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id="CPM-RO-001",
                selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
                worker_id="consumed-close-continuity"),clock_ms=lambda:close+1)
    assert refused.disposition is MaterializationDisposition.BLOCKED
    assert refused.reason_code=="GENERIC_CONTINUITY_CLOSE_NOT_PROVEN"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities"))==1


@pytest.mark.asyncio
@pytest.mark.parametrize("group,template_factory", [
    ("CPM-RO-001", cpm_long_snapshot),
    ("BRF2-001", brf2_short_snapshot),
])
async def test_generic_late_continuity_needs_gap_recovery_not_current_close(
    database: AsyncEngine, group: str, template_factory,
) -> None:
    source,_,_,uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    anchor = source.feature_cutoff_at_ms+source.spec.cadence_hours*HOUR
    late_close = anchor+2*HOUR
    at = late_close+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=late_close,valid_until_ms=at+HOUR)
    request = CoordinateGenericPeriodRequest(strategy_group_id=group,
        selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
        worker_id="late-continuity")
    outcomes = []
    for offset in range(4):
        now = at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now)):
            late = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda now=now:now)
        outcomes.append(late)
        if late.reason_code == "GENERIC_GAP_RECOVERY_PENDING":
            break
    assert outcomes[-1].disposition is MaterializationDisposition.WAITING_VACUUM, outcomes
    assert outcomes[-1].reason_code == "GENERIC_GAP_RECOVERY_PENDING"
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
    assert current is not None and current.authority.period.feature_cutoff_at_ms < anchor
    assert vacuum is not None and vacuum.state is StrategyEntryVacuumState.RECOVERY_PENDING
    assert vacuum.fenced_at_ms == at and vacuum.drained_at_ms is not None
    assert vacuum.blocks_new_entry
    async with database.connect() as conn:
        gap_open = await conn.scalar(sa.text("SELECT payload FROM brc_strategy_entry_vacuum_events "
            "WHERE entry_vacuum_id=:id AND event_type='OPEN'"),{"id":vacuum.entry_vacuum_id})
    assert gap_open["missed_close_time_ms"] == [anchor+HOUR,late_close]
    assert gap_open["missed_close_count"] == 2
    assert gap_open["missed_close_reason"] == "AUTHORITY_GAP"
    async with database.connect() as conn:
        forged_ledger = {**gap_open,"missed_close_count":1}
        assert await conn.scalar(sa.text("SELECT brc_generic_gap_open_ledger_matches("
            ":id,CAST(:payload AS jsonb),:at)"),
            {"id":vacuum.entry_vacuum_id,"payload":json.dumps(forged_ledger),"at":at}) is False
        assert await conn.scalar(sa.text("SELECT brc_generic_gap_open_ledger_matches("
            ":id,CAST(:payload AS jsonb),:at)"),
            {"id":vacuum.entry_vacuum_id,"payload":json.dumps(gap_open),"at":at}) is True
    with pytest.raises(sa.exc.DBAPIError):
        async with database.begin() as conn:
            await conn.execute(sa.text("INSERT INTO brc_strategy_entry_vacuum_events "
                "(entry_vacuum_event_id,entry_vacuum_id,event_sequence,event_type,payload,occurred_at_ms) "
                "VALUES (:eid,:id,99,'OPEN',CAST(:payload AS jsonb),:at)"),
                {"eid":"vacuum-event:forged-gap-ledger","id":vacuum.entry_vacuum_id,
                    "payload":json.dumps(forged_ledger),"at":at})
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        fenced = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=current.authority.selection_authority_id,
            observed_close_time_ms=late_close,now_ms=at+4,
            allow_current_as_birth=False,lock_current=True)
    assert not fenced.allowed and fenced.reason_code == "selection_entry_vacuum_open"
    async with database.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError):
            await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current "
                "SET state='RESOLVED_ACTIVE',resolved_at_ms=:at WHERE entry_vacuum_id=:id"),
                {"id":vacuum.entry_vacuum_id,"at":at+3})
        await conn.rollback()
        with pytest.raises(sa.exc.DBAPIError):
            await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current "
                "SET first_blocker='OTHER',state='RESOLVED_ACTIVE',resolved_at_ms=:at "
                "WHERE entry_vacuum_id=:id"),
                {"id":vacuum.entry_vacuum_id,"at":at+3})
        await conn.rollback()
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current "
            "WHERE state='RECOVERY_PENDING'"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==0
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at+5)):
        async with PostgresKernelUnitOfWork(database) as uow:
            proposal = await uow.instrument_selection.prepare_generic_gap_continuity_proof(
                strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                period_anchor_ms=anchor)
        assert proposal.authority_outcome == "PRE_FENCE_CONTINUITY"
        assert proposal.materialization_generation_id is None
        assert proposal.source_entry_vacuum_id == vacuum.entry_vacuum_id
        assert proposal.source_selection_authority_id == current.authority.selection_authority_id
        assert proposal.first_eligible_close_time_ms == late_close+HOUR
        async with database.connect() as conn:
            assert await conn.scalar(sa.text(
                "SELECT brc_generic_gap_continuity_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
                {"proof":proposal.model_dump_json(),"checked_at":proposal.committed_at_ms}) is True
            forged = proposal.model_copy(update={"owner_control_version":proposal.owner_control_version+1})
            assert await conn.scalar(sa.text(
                "SELECT brc_generic_gap_continuity_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
                {"proof":forged.model_dump_json(),"checked_at":proposal.committed_at_ms}) is False
        forged_authority = GenericRecoveryAuthority.build(proof=forged,authority_sequence=1)
        with pytest.raises(sa.exc.DBAPIError):
            async with database.begin() as conn:
                await conn.execute(sa.insert(selection_session_authorities).values(
                    **generic_recovery_authority_storage_values(forged_authority)))
        valid_authority = GenericRecoveryAuthority.build(proof=proposal,authority_sequence=1)
        with pytest.raises(sa.exc.DBAPIError):
            async with database.begin() as conn:
                await conn.execute(sa.insert(selection_session_authorities).values(
                    **generic_recovery_authority_storage_values(valid_authority)))
        async with PostgresKernelUnitOfWork(database) as uow:
            assert uow._connection is not None
            pause_probe = await uow._connection.begin_nested()
            await uow._connection.execute(sa.text("UPDATE brc_strategy_entry_controls_current "
                "SET entry_state='paused' WHERE strategy_group_id=:group"),{"group":group})
            with pytest.raises(SelectionJobConflict,match="Owner/Control"):
                await uow.instrument_selection.prepare_generic_gap_continuity_proof(
                    strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                    period_anchor_ms=anchor)
            await pause_probe.rollback()
            cursor_probe = await uow._connection.begin_nested()
            cursor = proposal.observation_cursors[0]
            changed_episode = advance_exposure_episode(
                contract=strategy_contract_for(source.spec.event_spec_id),current=None,
                detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,
                observed_at_ms=late_close,exchange_instrument_id=cursor.exchange_instrument_id)
            await uow.signals.save_exposure_episode(changed_episode.current,expected_version=0)
            with pytest.raises(SelectionJobConflict,match="proof changed"):
                await uow.instrument_selection.require_generic_gap_continuity_proof(proposal)
            await cursor_probe.rollback()
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict,match="proof changed"):
                await uow.instrument_selection.require_generic_gap_continuity_proof(forged)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=proposal.first_eligible_close_time_ms)):
            async with PostgresKernelUnitOfWork(database) as uow:
                with pytest.raises(ValueError,match="boundary"):
                    await uow.instrument_selection.require_generic_gap_continuity_proof(proposal)
        with patch.object(PostgresInstrumentSelectionRepository,
            "initialize_generic_recovery_checkpoints",new=AsyncMock(side_effect=RuntimeError("injected rebase failure"))), pytest.raises(
                RuntimeError,match="injected rebase failure"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.commit_generic_gap_continuity(proposal)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert (await uow.instrument_selection.get_current_generic_authority(
                source.spec.selection_spec_id)).authority.selection_authority_id == current.authority.selection_authority_id
            still_open = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
            assert still_open is not None and still_open.state is StrategyEntryVacuumState.RECOVERY_PENDING
            assert await uow.signals.get_authority_recovery_checkpoint(
                proposal.observation_cursors[0].episode_domain_key) is None
        restored = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:at+5)
    assert restored.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    async with PostgresKernelUnitOfWork(database) as uow:
        recovery = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) is None
    assert recovery is not None and recovery.authority.authority_outcome == "PRE_FENCE_CONTINUITY"
    assert recovery.authority.first_eligible_close_time_ms == late_close+HOUR
    assert recovery.authority.event_binding == current.authority.event_binding
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        rejected = await resolve_selection_observation_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=late_close,
            now_ms=at+6,allow_current_as_birth=True,lock_current=True)
    assert not rejected.allowed
    future_close = recovery.authority.first_eligible_close_time_ms
    template = template_factory()
    shift = future_close-template.trigger_candle_close_time_ms
    class GapRecoveryMarket:
        async def fetch_closed_candles(self, request):
            candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                "close_time_ms":c.close_time_ms+shift}) for c in candles)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=future_close+1)):
        suppressed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
            GapRecoveryMarket(),ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=future_close,
                attempted_at_ms=future_close+1))
    assert suppressed.status is ObservationStatus.NO_SIGNAL, suppressed
    assert suppressed.detector_reason == "RECOVERY_REBASE_REQUIRED", suppressed
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at+6)):
        duplicate = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:at+6)
    assert duplicate.selection_authority_id == recovery.authority.selection_authority_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 2
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current "
            "WHERE state='RESOLVED_CONTINUITY'")) == 1
        expected_members = await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_strategy_universe_members WHERE universe_version_id=:uid"),
            {"uid":uid})
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current "
            "WHERE authority_recovery_id IS NOT NULL")) == expected_members
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=late_close+HOUR)):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict,match="Vacuum"):
                await uow.instrument_selection.prepare_generic_gap_continuity_proof(
                    strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
                    period_anchor_ms=anchor)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
async def test_hourly_valid_empty_after_expired_authority_records_gap_before_empty(
    database: AsyncEngine, group: str,
) -> None:
    source,first_snapshot,_,old_uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    next_input_source = next_input(next_input(source)).model_copy(update={
        "predecessor_snapshot":first_snapshot})
    next_input_source = next_input_source.model_copy(update={"member_windows":tuple(
        qualify_window(window,False) for window in next_input_source.member_windows)})
    empty = compute_generic_selection(next_input_source)
    assert not empty.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(empty,
            decision_at_ms=next_input_source.decision_at_ms,
            source_observed_at_ms=next_input_source.source_observed_at_ms)
        previous = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert previous is not None
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,
        worker_id="hourly-gap-empty")
    now = empty.effective_from_ms+1
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now)):
        first = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now)
    assert first.disposition is MaterializationDisposition.WAITING_VACUUM, first
    async with PostgresKernelUnitOfWork(database) as uow:
        gap = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        still_previous = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert gap is not None and gap.first_blocker == "AUTHORITY_GAP"
    assert still_previous is not None and still_previous.authority.selection_authority_id == previous.authority.selection_authority_id
    async with database.connect() as conn:
        opened = await conn.scalar(sa.text("SELECT payload FROM brc_strategy_entry_vacuum_events "
            "WHERE entry_vacuum_id=:id AND event_type='OPEN'"),{"id":gap.entry_vacuum_id})
    assert opened["missed_close_time_ms"] == [previous.authority.expires_at_ms]
    terminal = None
    for offset in range(1,5):
        tick = now+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            result = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,
                clock_ms=lambda tick=tick:tick)
        if result.disposition is MaterializationDisposition.VALID_EMPTY:
            terminal = result
            break
    assert terminal is not None
    async with PostgresKernelUnitOfWork(database) as uow:
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        active = await uow.strategy_universes.get_current(source.spec.event_spec_id)
    assert authority is not None and authority.authority.authority_outcome == "VALID_EMPTY"
    assert active is not None and active.universe_version_id == old_uid
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
@pytest.mark.parametrize("skipped_periods", [1,3])
@pytest.mark.parametrize("same_members", [False,True])
async def test_hourly_new_selection_after_unobserved_expired_period_is_recovery_not_normal(
    database: AsyncEngine, group: str, skipped_periods: int, same_members: bool,
) -> None:
    source,first_snapshot,_,old_uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        old_authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert old_authority is not None
    newer_input = source
    for _ in range(skipped_periods+1):
        newer_input = next_input(newer_input)
    newer_input = newer_input.model_copy(update={"predecessor_snapshot":first_snapshot})
    assert len(first_snapshot.selected_members) > 1
    outsider = next(member for member in source.spec.candidate_ids
        if member not in first_snapshot.selected_members)
    retained = first_snapshot.selected_members[0]
    retained_candles = next(window.candles for window in newer_input.member_windows
        if window.exchange_instrument_id==retained)
    newer_input = newer_input.model_copy(update={"member_windows":tuple(
        qualify_window(window,window.exchange_instrument_id in first_snapshot.selected_members)
        if same_members else qualify_window(window.model_copy(update={"candles":retained_candles})
            if window.exchange_instrument_id==outsider else window,
            window.exchange_instrument_id in {retained,outsider})
        for window in newer_input.member_windows)})
    newer = compute_generic_selection(newer_input)
    assert newer.selected_members
    assert (newer.selected_members == first_snapshot.selected_members) == same_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(newer,
            decision_at_ms=newer_input.decision_at_ms,
            source_observed_at_ms=newer_input.source_observed_at_ms)
    now = newer.effective_from_ms+1
    await make_warming_ready(database,universe_version_id=old_uid,
        warm_closed_bar_time_ms=now//HOUR*HOUR,valid_until_ms=now+HOUR)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=newer.selection_snapshot_id,
        worker_id="hourly-unobserved-gap")
    steps = []
    for offset in range(5):
        tick = now+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda tick=tick:tick)
        steps.append(step)
        if step.entry_vacuum_id is not None:
            break
    assert steps[-1].entry_vacuum_id is not None, steps
    async with PostgresKernelUnitOfWork(database) as uow:
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        still_old = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert vacuum is not None and vacuum.first_blocker == "AUTHORITY_GAP"
    assert still_old is not None and still_old.authority.selection_authority_id == old_authority.authority.selection_authority_id
    async with database.connect() as conn:
        opened = await conn.scalar(sa.text("SELECT payload FROM brc_strategy_entry_vacuum_events "
            "WHERE entry_vacuum_id=:id AND event_type='OPEN'"),{"id":vacuum.entry_vacuum_id})
    assert opened["source_selection_authority_id"] == old_authority.authority.selection_authority_id
    assert opened["missed_close_time_ms"] == [old_authority.authority.expires_at_ms]
    assert opened["missed_close_reason"] == "AUTHORITY_GAP"
    assert opened["uncovered_close_count"] == skipped_periods+1
    assert opened["uncovered_last_close_time_ms"] == now//HOUR*HOUR
    async with database.connect() as conn:
        check_ledger = sa.text("SELECT brc_generic_gap_open_ledger_matches("
            ":id,CAST(:payload AS jsonb),:at)")
        assert await conn.scalar(check_ledger,{"id":vacuum.entry_vacuum_id,
            "payload":json.dumps(opened),"at":vacuum.fenced_at_ms}) is True
        forged_ledger = {**opened,"uncovered_close_count":skipped_periods}
        assert await conn.scalar(check_ledger,{"id":vacuum.entry_vacuum_id,
            "payload":json.dumps(forged_ledger),"at":vacuum.fenced_at_ms}) is False
    handed_off = None
    for offset in range(5,11):
        tick = now+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda tick=tick:tick)
        if step.disposition is MaterializationDisposition.GENERATION_MATERIALIZING:
            handed_off = step
            break
    assert handed_off is not None
    assert handed_off.entry_vacuum_id == vacuum.entry_vacuum_id
    async with PostgresKernelUnitOfWork(database) as uow:
        inherited = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        generation = await uow.instrument_selection.get_generic_materialization_generation(
            handed_off.materialization_generation_id)
    assert inherited is not None and inherited.fenced_at_ms == vacuum.fenced_at_ms
    assert inherited.drained_at_ms is not None and inherited.source_generation_id == generation.materialization_generation_id
    assert generation.fenced_at_ms > vacuum.fenced_at_ms
    generation_request = CoordinateGenericGenerationRequest(
        materialization_generation_id=generation.materialization_generation_id,
        worker_id="hourly-unobserved-gap")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+11)):
        installing = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+11)
    assert installing.disposition is MaterializationDisposition.TARGET_WARMING, installing
    async with PostgresKernelUnitOfWork(database) as uow:
        targets = await uow.strategy_universes.get_generation_universe_targets(generation.materialization_generation_id)
    assert len(targets) == 1
    target_uid = targets[0].universe_version_id
    await make_warming_ready(database,universe_version_id=target_uid,
        warm_closed_bar_time_ms=now//HOUR*HOUR,valid_until_ms=now+HOUR)
    template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
    delta = now//HOUR*HOUR-template.trigger_candle_close_time_ms
    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,
        "close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
    projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
        universe_version_id=target_uid,strategy_group_id=group,
        exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=now//HOUR*HOUR,
        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,
            candles_1h=candles) for member in source.spec.candidate_ids))
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.strategy_universes.save_comparative_projection(projection)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+12)):
        staged = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+12)
    assert staged.disposition is MaterializationDisposition.GENERATION_STAGED, staged
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+13)):
        async with PostgresKernelUnitOfWork(database) as uow:
            proof = await uow.instrument_selection.prepare_generic_recovered_activation_proof(
                generation.materialization_generation_id)
    assert proof.authority_outcome == "ACTIVE_NEW"
    assert proof.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert proof.first_eligible_close_time_ms == newer.expires_at_ms
    async with database.connect() as conn:
        proof_check = sa.text("SELECT brc_generic_recovered_activation_proof_matches("
            "CAST(:proof AS jsonb),:checked_at)")
        assert await conn.scalar(proof_check,{"proof":proof.model_dump_json(),
            "checked_at":proof.committed_at_ms}) is True
        wrong_source = proof.model_copy(update={"source_selection_authority_id":"authority:forged"})
        assert await conn.scalar(proof_check,{"proof":wrong_source.model_dump_json(),
            "checked_at":proof.committed_at_ms}) is False
        assert await conn.scalar(proof_check,{"proof":proof.model_dump_json(),
            "checked_at":proof.first_eligible_close_time_ms}) is False
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+14)):
        activated = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+14)
    assert activated.disposition is MaterializationDisposition.ACTIVE_NEW, activated
    async with PostgresKernelUnitOfWork(database) as uow:
        recovered = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        active = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        unresolved = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
    assert recovered is not None and recovered.authority.authority_outcome == "ACTIVE_NEW"
    assert recovered.authority.recovery_proof.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert recovered.authority.first_eligible_close_time_ms == newer.expires_at_ms
    assert active is not None and active.universe_version_id == target_uid
    assert unresolved is None
    added_members = sorted(set(newer.selected_members)-set(first_snapshot.selected_members))
    assert same_members or added_members, (first_snapshot.selected_members,newer.selected_members)
    focus_member = newer.selected_members[0] if same_members else added_members[0]
    if not same_members:
        assert focus_member not in first_snapshot.selected_members
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+15)):
        repeated = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+15)
    assert repeated.selection_authority_id == recovered.authority.selection_authority_id
    first_close = recovered.authority.first_eligible_close_time_ms
    await make_warming_ready(database,universe_version_id=target_uid,
        warm_closed_bar_time_ms=first_close,valid_until_ms=first_close+HOUR)
    shift = first_close-template.trigger_candle_close_time_ms
    next_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
        "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
    flat = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
    flat_shift = first_close-flat.trigger_candle_close_time_ms
    flat_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+flat_shift,
        "close_time_ms":c.close_time_ms+flat_shift}) for c in flat.candles_1h)
    next_projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
        universe_version_id=target_uid,strategy_group_id=group,
        exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=first_close,
        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,
            candles_1h=next_candles if member==focus_member else flat_candles)
            for member in source.spec.candidate_ids)).model_copy(update={
                "comparison_transition_revision":recovered.authority.comparison_transition_revision})
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.strategy_universes.save_comparative_projection(next_projection)
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid AND exchange_instrument_id=:member LIMIT 1"),
            {"uid":target_uid,"member":focus_member})
    class HourlyRecoveryMarket:
        async def fetch_closed_candles(self, request):
            candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                "close_time_ms":c.close_time_ms+shift}) for c in candles)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=first_close+1)):
        first_observation = await observe_strategy_scope(
            lambda:PostgresKernelUnitOfWork(database),HourlyRecoveryMarket(),
            ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=first_close,
                attempted_at_ms=first_close+1))
    assert first_observation.status is ObservationStatus.NO_SIGNAL, first_observation
    assert first_observation.detector_reason == "RECOVERY_REBASE_REQUIRED"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
        checkpoint = (await conn.execute(sa.text("SELECT authority_recovery_id,"
            "authority_recovery_armed_at_ms,comparison_transition_revision,"
            "comparison_armed_at_ms FROM brc_exposure_episode_current "
            "WHERE event_spec_id=:event AND exchange_instrument_id=:member"),
            {"event":source.spec.event_spec_id,"member":focus_member})).one()
    assert checkpoint[0] == recovered.authority.recovery_proof.recovery_close_plan.recovery_id
    assert checkpoint[1] is None
    if not same_members:
        assert focus_member == outsider
        assert checkpoint[3] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("group,owner_pause,corrupt_completion", [(g,False,None) for g in ("CPM-RO-001","BRF2-001")]+
    [(g,True,c) for g in ("CPM-RO-001","BRF2-001","MPG-001","MI-001") for c in (None,"false","string")])
@pytest.mark.parametrize("same_members", [False,True])
async def test_new_nonempty_snapshot_takes_over_generation_free_gap_without_normal_grant(
    database: AsyncEngine, group: str, same_members: bool,owner_pause: bool,corrupt_completion: str | None,
) -> None:
    source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    anchor = source.feature_cutoff_at_ms+source.spec.cadence_hours*HOUR
    late_close = anchor+(HOUR if owner_pause else 2*HOUR)
    at = late_close+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=late_close,valid_until_ms=at+4*HOUR)
    period_request = CoordinateGenericPeriodRequest(strategy_group_id=group,
        selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
        worker_id="gap-before-nonempty")
    if owner_pause:
        from src.trading_kernel.application.owner_control import (
            set_strategy_entry_state,
        )
        from src.trading_kernel.domain.owner_control import StrategyEntryState
        async with PostgresKernelUnitOfWork(database) as uow:
            previous=await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            owner=await uow.owner_controls.get_strategy_control(group)
            pause_at=previous.authority.created_at_ms+1000
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="generation_free_nonempty_recovery",
                    idempotency_key=f"pause-free:{group}:{same_members}:{corrupt_completion}",owner_identity="owner",now_ms=pause_at),authentication_strength="totp_step_up")
        actual_execute=sa.ext.asyncio.AsyncConnection.execute
        async def corrupt_completion_event(connection,statement,*args,**kwargs):
            if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
                params=statement.compile().params
                if params.get("event_type")=="OWNER_PAUSED" and params.get("payload",{}).get("entry_drain_complete"):
                    statement=statement.values(payload={"entry_drain_complete":"true" if corrupt_completion=="string" else False})
            return await actual_execute(connection,statement,*args,**kwargs)
        for drain_at in (pause_at+1,pause_at+2):
            async with PostgresKernelUnitOfWork(database) as uow:
                if corrupt_completion:
                    with patch.object(sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_completion_event):
                        await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,now_ms=drain_at))
                else:
                    await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,now_ms=drain_at))
        async with PostgresKernelUnitOfWork(database) as uow:
            owner=await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_generation_free_nonempty",
                    idempotency_key=f"resume-free:{group}:{same_members}:{corrupt_completion}",owner_identity="owner",now_ms=pause_at+3),authentication_strength="totp_step_up")
    for offset in range(0 if owner_pause else 4):
        now = at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now)):
            result = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=period_request,clock_ms=lambda now=now:now)
        if result.reason_code == "GENERIC_GAP_RECOVERY_PENDING":
            break
    async with PostgresKernelUnitOfWork(database) as uow:
        gap = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        previous = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert gap is not None and gap.state is (StrategyEntryVacuumState.OWNER_PAUSED if owner_pause else StrategyEntryVacuumState.RECOVERY_PENDING)
    assert previous is not None
    successor = next_input(source).model_copy(update={"predecessor_snapshot":first_snapshot})
    removed = first_snapshot.selected_members[0]
    successor = successor.model_copy(update={"member_windows":tuple(
        qualify_window(w,w.exchange_instrument_id in first_snapshot.selected_members)
        if same_members else (qualify_window(w,False) if w.exchange_instrument_id==removed else w)
        for w in successor.member_windows)})
    snapshot = compute_generic_selection(successor)
    assert snapshot.selected_members
    assert (snapshot.selected_members == first_snapshot.selected_members) == same_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,
            decision_at_ms=successor.decision_at_ms,
            source_observed_at_ms=successor.source_observed_at_ms)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,
        worker_id="new-desired-after-gap")
    now = at+5
    if corrupt_completion:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)), pytest.raises(SelectionJobConflict,match="Pause"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now)
        actual_scalar=sa.ext.asyncio.AsyncConnection.scalar
        async def bypass_python_resume(connection,statement,*args,**kwargs):
            if "brc_generic_vacuum_owner_resume_matches" in str(statement):
                return True
            return await actual_scalar(connection,statement,*args,**kwargs)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)), patch.object(
            sa.ext.asyncio.AsyncConnection,"scalar",new=bypass_python_resume), pytest.raises(sa.exc.DBAPIError,match="Owner Pause generation-free handoff"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==gap
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==previous
            assert await uow.instrument_selection.get_generic_materialization_generation(GenericMaterializationGeneration.id_for_snapshot(snapshot.selection_snapshot_id)) is None
        return
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now)):
        result = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:now)
    assert result.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, result
    async with PostgresKernelUnitOfWork(database) as uow:
        inherited = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        generation = await uow.instrument_selection.get_generic_materialization_generation(
            result.materialization_generation_id)
    assert inherited is not None and inherited.entry_vacuum_id == gap.entry_vacuum_id
    assert inherited.fenced_at_ms == gap.fenced_at_ms and inherited.drained_at_ms == gap.drained_at_ms
    assert inherited.source_generation_id == generation.materialization_generation_id
    assert inherited.state is StrategyEntryVacuumState.RECONFIGURING
    assert generation.fenced_at_ms == now
    assert current is not None and current.authority.selection_authority_id == previous.authority.selection_authority_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
    generation_request = CoordinateGenericGenerationRequest(
        materialization_generation_id=generation.materialization_generation_id,
        worker_id="new-desired-after-gap")
    staged = None
    for offset in range(1,7):
        tick = now+offset
        await make_warming_ready(database,universe_version_id=uid,
            warm_closed_bar_time_ms=late_close,valid_until_ms=tick+HOUR)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=generation_request,clock_ms=lambda tick=tick:tick)
        async with PostgresKernelUnitOfWork(database) as uow:
            targets = await uow.strategy_universes.get_generation_universe_targets(
                generation.materialization_generation_id)
        if targets:
            await make_warming_ready(database,universe_version_id=targets[0].universe_version_id,
                warm_closed_bar_time_ms=late_close,valid_until_ms=tick+HOUR)
            if group in {"MPG-001","MI-001"}:
                template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                shift=late_close-template.trigger_candle_close_time_ms
                candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
                projection=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=targets[0].universe_version_id,
                    strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=late_close,lookback_bars=8 if group=="MPG-001" else 12,
                    freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids))
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.strategy_universes.save_comparative_projection(projection)
        if step.disposition is MaterializationDisposition.GENERATION_STAGED:
            staged = step
            break
    assert staged is not None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+8)):
        async with PostgresKernelUnitOfWork(database) as uow:
            proposal = await uow.instrument_selection.prepare_generic_recovered_activation_proof(
                generation.materialization_generation_id)
    assert proposal.authority_outcome == "ACTIVE_NEW"
    assert proposal.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert proposal.first_eligible_close_time_ms > proposal.committed_at_ms
    assert proposal.source_entry_vacuum_id == gap.entry_vacuum_id
    with pytest.raises(sa.exc.DBAPIError):
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current "
                "SET state='RESOLVED_ACTIVE',resolved_at_ms=:at "
                "WHERE entry_vacuum_id=:id"),
                {"at":now+8,"id":gap.entry_vacuum_id})
    async with database.connect() as conn:
        assert await conn.scalar(sa.text(
            "SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof":proposal.model_dump_json(),"checked_at":proposal.committed_at_ms}) is True
        wrong_source = proposal.model_copy(update={"source_selection_authority_id":"authority:wrong"})
        assert await conn.scalar(sa.text(
            "SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof":wrong_source.model_dump_json(),"checked_at":proposal.committed_at_ms}) is False
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+8)):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict,match="proof changed"):
                await uow.instrument_selection.require_generic_recovered_activation_proof(wrong_source)
            assert uow._connection is not None
            owner_probe = await uow._connection.begin_nested()
            await uow._connection.execute(sa.text("UPDATE brc_strategy_entry_controls_current "
                "SET entry_state='paused' WHERE strategy_group_id=:group"),{"group":group})
            with pytest.raises(SelectionJobConflict,match="Owner or Control"):
                await uow.instrument_selection.prepare_generic_recovered_activation_proof(
                    generation.materialization_generation_id)
            await owner_probe.rollback()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=proposal.first_eligible_close_time_ms)):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(ValueError,match="boundary"):
                await uow.instrument_selection.require_generic_recovered_activation_proof(proposal)
    @asynccontextmanager
    async def interrupted_gap_activation():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            inside = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            assert inside is not None and inside.authority.authority_outcome == "ACTIVE_NEW"
            raise RuntimeError("injected gap target activation interruption")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+8)), pytest.raises(RuntimeError,
            match="injected gap target activation interruption"):
        await coordinate_selection_materialization_once(
            uow_factory=interrupted_gap_activation,
            request=generation_request,clock_ms=lambda:now+8)
    async with PostgresKernelUnitOfWork(database) as uow:
        still_previous = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        still_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        still_target = await uow.strategy_universes.get_generation_universe_targets(
            generation.materialization_generation_id)
    assert still_previous is not None and still_previous.authority.selection_authority_id == previous.authority.selection_authority_id
    assert still_vacuum is not None and still_vacuum.state is StrategyEntryVacuumState.RECONFIGURING
    assert len(still_target) == 1 and still_target[0].lifecycle_state.value == "staged"
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+8)):
        activated = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+8)
    assert activated.disposition is MaterializationDisposition.ACTIVE_NEW, activated
    async with PostgresKernelUnitOfWork(database) as uow:
        live = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        switched = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        unresolved = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
    assert live is not None and live.authority.selection_authority_id == activated.selection_authority_id
    assert live.authority.recovery_proof.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert live.authority.first_eligible_close_time_ms > live.authority.created_at_ms
    assert switched is not None and switched.universe_version_id != uid
    assert unresolved is None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now+9)):
        duplicate = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=generation_request,clock_ms=lambda:now+9)
    assert duplicate.selection_authority_id == live.authority.selection_authority_id
    async with database.connect() as conn:
        target_scope = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),
            {"uid":switched.universe_version_id})
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current "
            "WHERE authority_recovery_id=:rid"),
            {"rid":live.authority.recovery_proof.recovery_close_plan.recovery_id}) == len(snapshot.selected_members)
    first_future = live.authority.first_eligible_close_time_ms
    await make_warming_ready(database,universe_version_id=switched.universe_version_id,
        warm_closed_bar_time_ms=first_future,valid_until_ms=first_future+HOUR)
    template = {"CPM-RO-001":cpm_long_snapshot,"BRF2-001":brf2_short_snapshot,"MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot}[group]()
    delta = first_future-template.trigger_candle_close_time_ms
    if group in {"MPG-001","MI-001"}:
        async with database.connect() as conn:
            focus=await conn.scalar(sa.text("SELECT exchange_instrument_id FROM brc_runtime_scopes_current WHERE runtime_scope_id=:id"),{"id":target_scope})
        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        flat=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        flat_delta=first_future-flat.trigger_candle_close_time_ms
        flat_candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+flat_delta,"close_time_ms":c.close_time_ms+flat_delta}) for c in flat.candles_1h)
        projection=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=switched.universe_version_id,
            strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=first_future,lookback_bars=8 if group=="MPG-001" else 12,
            freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles if m==focus else flat_candles) for m in source.spec.candidate_ids))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection.model_copy(update={"comparison_transition_revision":live.authority.comparison_transition_revision}))
    class RecoveredGapMarket:
        async def fetch_closed_candles(self, request):
            candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,
                "close_time_ms":c.close_time_ms+delta}) for c in candles)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=first_future+1)):
        observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
            RecoveredGapMarket(),ObservationRequest(runtime_scope_id=target_scope,runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=first_future,
                attempted_at_ms=first_future+1))
    assert observed.status is ObservationStatus.NO_SIGNAL, observed
    assert observed.detector_reason == "RECOVERY_REBASE_REQUIRED", observed
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "BRF2-001"])
async def test_generic_new_empty_snapshot_supersedes_drained_gap_without_previous_fallback(
    database: AsyncEngine, group: str,
) -> None:
    source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    anchor = source.feature_cutoff_at_ms+source.spec.cadence_hours*HOUR
    late_close = anchor+2*HOUR
    at = late_close+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=late_close,valid_until_ms=anchor+3*source.spec.cadence_hours*HOUR)
    period_request = CoordinateGenericPeriodRequest(strategy_group_id=source.spec.strategy_group_id,
        selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
        worker_id="gap-before-empty")
    gap_outcomes = []
    for offset in range(4):
        now = at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now)):
            gap_outcomes.append(await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=period_request,clock_ms=lambda now=now:now))
        if gap_outcomes[-1].reason_code == "GENERIC_GAP_RECOVERY_PENDING":
            break
    async with PostgresKernelUnitOfWork(database) as uow:
        gap = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id)
        original = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert gap is not None and gap.state is StrategyEntryVacuumState.RECOVERY_PENDING, gap_outcomes
    assert original is not None
    successor = next_input(source)
    while successor.feature_cutoff_at_ms <= gap.period_anchor_ms:
        successor = next_input(successor)
    successor = successor.model_copy(update={"predecessor_snapshot":first_snapshot,"member_windows":tuple(
        qualify_window(w,False) for w in successor.member_windows)})
    empty = compute_generic_selection(successor)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(empty,
            decision_at_ms=successor.decision_at_ms,source_observed_at_ms=successor.source_observed_at_ms)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,
        worker_id="empty-after-gap")
    now = empty.effective_from_ms+1
    async with database.connect() as conn:
        with pytest.raises(sa.exc.DBAPIError):
            await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current "
                "SET state='DRAINING_ENTRY',first_blocker='NO_SELECTION_READY_MEMBERS',"
                "period_anchor_ms=:anchor,projection_version=projection_version+1 "
                "WHERE entry_vacuum_id=:id"),
                {"anchor":empty.feature_cutoff_at_ms,"id":gap.entry_vacuum_id})
        await conn.rollback()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now)):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict,match="Owner or Control"):
                await uow.instrument_selection.retarget_generic_empty_vacuum(
                    gap,selection_snapshot_id=empty.selection_snapshot_id,
                    expected_owner_version=original.authority.owner_control_version+1,
                    expected_control_version=original.authority.selection_control_version)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current "
            "SET entry_state='paused' WHERE strategy_group_id=:group"),
            {"group":source.spec.strategy_group_id})
    paused = await coordinate_selection_materialization_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now)
    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current "
            "SET entry_state='enabled' WHERE strategy_group_id=:group"),
            {"group":source.spec.strategy_group_id})
    @asynccontextmanager
    async def interrupted_empty_handoff():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            committed_in_transaction = await uow.instrument_selection.get_current_generic_authority(
                source.spec.selection_spec_id)
            assert committed_in_transaction is not None
            assert committed_in_transaction.authority.authority_outcome == "VALID_EMPTY"
            raise RuntimeError("injected empty handoff interruption")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now)), pytest.raises(RuntimeError,match="injected empty handoff interruption"):
        await coordinate_selection_materialization_once(
            uow_factory=interrupted_empty_handoff,request=request,clock_ms=lambda:now)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=source.spec.strategy_group_id,
            selection_spec_id=source.spec.selection_spec_id) == gap
        assert (await uow.instrument_selection.get_current_generic_authority(
            source.spec.selection_spec_id)).authority.selection_authority_id == original.authority.selection_authority_id
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=now)):
        async with PostgresKernelUnitOfWork(database) as uow:
            handoff = await uow.instrument_selection.retarget_generic_empty_vacuum(
                gap,selection_snapshot_id=empty.selection_snapshot_id,
                expected_owner_version=original.authority.owner_control_version,
                expected_control_version=original.authority.selection_control_version)
    assert handoff.state is StrategyEntryVacuumState.DRAINING_ENTRY
    assert handoff.fenced_at_ms == gap.fenced_at_ms
    assert handoff.drained_at_ms == gap.drained_at_ms
    for target in ("RESOLVED_ACTIVE", "VALID_EMPTY"):
        with pytest.raises(sa.exc.DBAPIError):
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current "
                    "SET state=:target,resolved_at_ms=:at WHERE entry_vacuum_id=:id"),
                    {"target":target,"at":now+1,"id":gap.entry_vacuum_id})
    results = []
    for offset in range(3):
        now = empty.effective_from_ms+offset+1
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=now)):
            result = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda now=now:now)
        results.append(result)
        if result.disposition is MaterializationDisposition.VALID_EMPTY:
            break
    assert results[-1].disposition is MaterializationDisposition.VALID_EMPTY, results
    async with PostgresKernelUnitOfWork(database) as uow:
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        unresolved = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id)
        current_universe = await uow.strategy_universes.get_current(source.spec.event_spec_id)
    assert authority is not None and authority.authority.authority_outcome == "VALID_EMPTY"
    assert authority.authority.selection_authority_id != original.authority.selection_authority_id
    assert unresolved is None
    assert current_universe is not None and current_universe.universe_version_id == uid
    repeated = await coordinate_selection_materialization_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,
        clock_ms=lambda:empty.effective_from_ms+10)
    assert repeated.disposition is MaterializationDisposition.VALID_EMPTY
    assert repeated.selection_authority_id == authority.authority.selection_authority_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current "
            "WHERE entry_vacuum_id=:id AND state='VALID_EMPTY'"),{"id":gap.entry_vacuum_id}) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 2
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities "
            "WHERE authority_outcome='FALLBACK_PREVIOUS'")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0


@pytest.mark.asyncio
async def test_generic_source_failure_cannot_revoke_pre_fence_continuity(database: AsyncEngine) -> None:
    first_source,first_snapshot,_,uid = await _exercise_generic_generation(
        database,"CPM-RO-001",False,durable=True,first_activation=True,natural_selection=True)
    source = next_input(first_source)
    anchor = source.feature_cutoff_at_ms
    class BrokenSource:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            return tuple(member.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for member in source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            bars = next(member.candles for member in source.member_windows
                if member.exchange_instrument_id==request.exchange_instrument_id)
            return bars[:-1] if request.exchange_instrument_id==source.spec.candidate_ids[0] else bars
    failed = await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
        market_source=BrokenSource(),request=RunInstrumentSelectionRequest(
            selection_spec_id=source.spec.selection_spec_id,selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=anchor,worker_id="source-failure-before-continuity"),
        clock_ms=lambda:anchor+1)
    assert failed.outcome=="SOURCE_FAILED"
    boundary = anchor+HOUR
    at = boundary+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=boundary,valid_until_ms=at+HOUR)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        continued = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id="CPM-RO-001",
                selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
                worker_id="source-failed-continuity"),clock_ms=lambda:at)
    assert continued.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id="CPM-RO-001",selection_spec_id=source.spec.selection_spec_id)
    assert current is not None and current.authority.membership_freshness.source_snapshot_id==first_snapshot.selection_snapshot_id
    assert vacuum is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_generations"))==1


@pytest.mark.asyncio
@pytest.mark.parametrize("group",("MPG-001","MI-001","BRF2-001"))
async def test_generic_continuity_preserves_event_side_and_comparison(database: AsyncEngine,group: str) -> None:
    source,snapshot,_,uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    async with PostgresKernelUnitOfWork(database) as uow:
        original = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert original is not None
    anchor = source.feature_cutoff_at_ms+source.spec.cadence_hours*HOUR
    boundary = anchor+HOUR
    at = boundary+1
    await make_warming_ready(database,universe_version_id=uid,
        warm_closed_bar_time_ms=boundary,valid_until_ms=at+HOUR)
    if group in {"MPG-001","MI-001"}:
        template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        shift = boundary-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
            "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=uid,strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,
            closed_bar_time_ms=boundary,lookback_bars=8 if group=="MPG-001" else 12,
            freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(
                exchange_instrument_id=member,candles_1h=candles) for member in source.spec.candidate_ids))
        projection = projection.model_copy(update={
            "comparison_transition_revision":original.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        result = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id,period_anchor_ms=anchor,
                worker_id="multi-strategy-continuity"),clock_ms=lambda:at)
    assert result.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, result
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert current is not None
    assert current.authority.event_binding==original.authority.event_binding
    assert current.authority.comparison_universe_id==original.authority.comparison_universe_id
    assert current.authority.comparison_transition_revision==original.authority.comparison_transition_revision
    assert current.authority.membership_freshness.source_snapshot_id==snapshot.selection_snapshot_id


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
@pytest.mark.parametrize("stage", ["PENDING","DESIRED"])
@pytest.mark.parametrize("static_source", [False,True])
async def test_owner_pause_abandons_unfenced_generic_generation(database: AsyncEngine,group: str,stage: str,static_source: bool) -> None:
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    from src.trading_kernel.application.owner_control import (
        set_strategy_entry_state,
        stage_generic_static_selection_mode,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    source,first,_,uid = await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    shifted = next_input(source)
    next_source = shifted.model_copy(update={"predecessor_snapshot":first,"member_windows":tuple(
        qualify_window(window.model_copy(update={"candles":shifted.member_windows[0].candles}),
            window.exchange_instrument_id==source.spec.candidate_ids[0]) for window in shifted.member_windows)})
    snapshot = compute_generic_selection(next_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        if not static_source:
            await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=next_source.decision_at_ms,source_observed_at_ms=next_source.source_observed_at_ms)
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="pause-unfenced")
    at = snapshot.effective_from_ms+1
    if static_source:
        async with PostgresKernelUnitOfWork(database) as uow:
            control = await uow.instrument_selection.get_selection_control(group)
            schedule_at = authority.authority.created_at_ms+1
            cadence = source.spec.cadence_hours*HOUR
            anchor = (schedule_at//cadence+1)*cadence
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,rollback_baseline_id=control.rollback_baseline_id,
                selection_epoch_id=control.selection_epoch_id,effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
                request=ControlMutationRequest(expected_version=control.control_version,reason="pause_unfenced_static_intent",
                    idempotency_key=f"unfenced-static:{group}:{stage}",owner_identity="owner",now_ms=schedule_at))
        request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="pause-unfenced-static")
        at = anchor+HOUR+1
    for offset in range(2 if stage=="DESIRED" else 1):
        tick = at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            result = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda tick=tick:tick)
    async with PostgresKernelUnitOfWork(database) as uow:
        before = await (uow.instrument_selection.get_generic_static_materialization_generation(result.materialization_generation_id)
            if static_source else uow.instrument_selection.get_generic_materialization_generation(result.materialization_generation_id))
        assert before.lifecycle_state.value==stage
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) is None
        owner = await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_before_materialization_fence",
                idempotency_key=f"pause-unfenced:{group}:{stage}",owner_identity="owner",now_ms=tick+1),authentication_strength="totp_step_up")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+2)):
        paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:tick+2)
    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with PostgresKernelUnitOfWork(database) as uow:
        abandoned = await (uow.instrument_selection.get_generic_static_materialization_generation(before.materialization_generation_id)
            if static_source else uow.instrument_selection.get_generic_materialization_generation(before.materialization_generation_id))
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        assert abandoned.lifecycle_state.value=="ABANDONED" and abandoned.terminal_at_ms==tick+2
        assert abandoned.semantic_digest==before.semantic_digest and abandoned.fenced_at_ms is None
        assert abandoned.lease_owner is None and abandoned.lease_expires_at_ms is None
        assert vacuum is not None and vacuum.first_blocker=="OWNER_PAUSED" and vacuum.blocks_new_entry
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==uid
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==authority
        assert await uow.strategy_universes.get_generation_universe_targets(before.materialization_generation_id)==()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+3)):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:tick+3)
    async with PostgresKernelUnitOfWork(database) as uow:
        drained = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        assert drained.entry_vacuum_id==vacuum.entry_vacuum_id and drained.fenced_at_ms==vacuum.fenced_at_ms
        assert drained.state is StrategyEntryVacuumState.OWNER_PAUSED and drained.resolved_at_ms is None
        assert await (uow.instrument_selection.get_generic_static_materialization_generation(before.materialization_generation_id)
            if static_source else uow.instrument_selection.get_generic_materialization_generation(before.materialization_generation_id))==abandoned
    if not static_source:
        async with PostgresKernelUnitOfWork(database) as uow:
            owner = await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="latest_empty_after_unfenced_pause",
                    idempotency_key=f"resume-empty:{group}:{stage}",owner_identity="owner",now_ms=tick+4),authentication_strength="totp_step_up")
        empty_source = next_input(next_source).model_copy(update={"predecessor_snapshot":snapshot})
        empty_source = empty_source.model_copy(update={"member_windows":tuple(qualify_window(window,False) for window in empty_source.member_windows)})
        empty = compute_generic_selection(empty_source)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(empty,decision_at_ms=empty_source.decision_at_ms,source_observed_at_ms=empty_source.source_observed_at_ms)
        empty_at = empty.effective_from_ms+1
        empty_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,worker_id="latest-empty-after-pause")
        actual_execute = sa.ext.asyncio.AsyncConnection.execute
        async def corrupt_empty_intent(connection,statement,*args,**kwargs):
            if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
                params = statement.compile().params
                if params.get("event_type")=="VALID_EMPTY_INTENT" and params.get("payload",{}).get("supersedes_owner_pause"):
                    statement = statement.values(payload={**params["payload"],"supersedes_owner_pause":False})
            return await actual_execute(connection,statement,*args,**kwargs)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)), patch.object(
            sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_empty_intent), pytest.raises(sa.exc.DBAPIError,match="Owner Pause EMPTY requires exact"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:empty_at)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==drained
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==authority
        async def omit_negative_authority(repository,negative,*,entry_vacuum_id,**kwargs):
            await repository._connection.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='VALID_EMPTY',resolved_at_ms=:at,"
                "projection_version=projection_version+1 WHERE entry_vacuum_id=:id"),{"at":negative.created_at_ms,"id":entry_vacuum_id})
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)), patch.object(
            PostgresInstrumentSelectionRepository,"commit_generic_valid_empty",new=omit_negative_authority), pytest.raises(
                sa.exc.DBAPIError,match="VALID_EMPTY requires atomic negative Authority"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:empty_at)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)):
            for _ in range(4):
                outcome = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:empty_at)
                if outcome.disposition is MaterializationDisposition.VALID_EMPTY:
                    break
        assert outcome.disposition is MaterializationDisposition.VALID_EMPTY,outcome
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_materialization_generation(before.materialization_generation_id)==abandoned
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) is None
            current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            assert current.authority.authority_outcome=="VALID_EMPTY" and current.authority.blocks_new_entry
            assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==uid
        async with database.connect() as conn:
            retained = (await conn.execute(sa.text("SELECT state,fenced_at_ms,drained_at_ms FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=:id"),{"id":drained.entry_vacuum_id})).one()
            assert retained==("VALID_EMPTY",drained.fenced_at_ms,drained.drained_at_ms)
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
@pytest.mark.parametrize("static_source,corrupt_completion", [(False,False),(True,False),(True,True),(True,"string_true"),(False,"early_resume"),(True,"early_resume"),(False,"deferred_cleanup"),(True,"deferred_cleanup")])
async def test_owner_pause_during_generic_entry_drain_preserves_fence_and_finishes_drain(
    database: AsyncEngine, group: str,static_source: bool,corrupt_completion: bool | str,
) -> None:
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    from src.trading_kernel.application.owner_control import (
        set_strategy_entry_state,
        stage_generic_static_selection_mode,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    deferred_cleanup=corrupt_completion=="deferred_cleanup"
    early_resume=corrupt_completion in {"early_resume","deferred_cleanup"}
    if early_resume:
        corrupt_completion=False
    source,first,_,uid = await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    shifted = next_input(source)
    successor_source = shifted.model_copy(update={"predecessor_snapshot":first,"member_windows":tuple(
        qualify_window(window.model_copy(update={"candles":shifted.member_windows[0].candles}),
            window.exchange_instrument_id==source.spec.candidate_ids[0]) for window in shifted.member_windows)})
    successor = compute_generic_selection(successor_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        if not static_source:
            await uow.instrument_selection.save_generic_snapshot(successor,decision_at_ms=successor_source.decision_at_ms,
                source_observed_at_ms=successor_source.source_observed_at_ms)
        original = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=successor.selection_snapshot_id,worker_id="draining-pause")
    start = successor.effective_from_ms+1
    if static_source:
        async with PostgresKernelUnitOfWork(database) as uow:
            control = await uow.instrument_selection.get_selection_control(group)
            at = original.authority.created_at_ms+1
            cadence = source.spec.cadence_hours*HOUR
            anchor = (at//cadence+1)*cadence
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,rollback_baseline_id=control.rollback_baseline_id,
                selection_epoch_id=control.selection_epoch_id,effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
                request=ControlMutationRequest(expected_version=control.control_version,reason="pause_static_entry_drain",
                    idempotency_key=f"static-drain-pause:{group}",owner_identity="owner",now_ms=at))
        request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="static-draining-pause")
        start = anchor+HOUR+1
    for offset in range(4):
        at = start+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
            result = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda at=at:at)
        if result.disposition is MaterializationDisposition.WAITING_VACUUM:
            break
    assert result.disposition is MaterializationDisposition.WAITING_VACUUM
    async with PostgresKernelUnitOfWork(database) as uow:
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        owner = await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_existing_entry_drain",
                idempotency_key=f"pause-drain:{group}",owner_identity="owner",now_ms=at+1),authentication_strength="totp_step_up")
    if deferred_cleanup:
        async with PostgresKernelUnitOfWork(database) as uow:
            owner=await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_before_cleanup",
                    idempotency_key=f"deferred-resume:{group}:{static_source}",owner_identity="owner",now_ms=at+2),authentication_strength="totp_step_up")
        at+=1
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+2)):
        @asynccontextmanager
        async def interrupted_pause():
            async with PostgresKernelUnitOfWork(database) as uow:
                yield uow
                raise RuntimeError("injected drain-pause commit failure")
        with pytest.raises(RuntimeError,match="drain-pause commit"):
            await coordinate_selection_materialization_once(uow_factory=interrupted_pause,request=request,clock_ms=lambda:at+2)
        async with PostgresKernelUnitOfWork(database) as uow:
            unchanged = await (uow.instrument_selection.get_generic_static_materialization_generation(result.materialization_generation_id)
                if static_source else uow.instrument_selection.get_generic_materialization_generation(result.materialization_generation_id))
            assert unchanged.lifecycle_state.value=="DRAINING_ENTRY"
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==vacuum
        paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at+2)
    assert paused.disposition is (MaterializationDisposition.WAITING_VACUUM if deferred_cleanup else MaterializationDisposition.OWNER_PAUSED)
    async with PostgresKernelUnitOfWork(database) as uow:
        abandoned = await (uow.instrument_selection.get_generic_static_materialization_generation(result.materialization_generation_id)
            if static_source else uow.instrument_selection.get_generic_materialization_generation(result.materialization_generation_id))
        assert abandoned.lifecycle_state.value=="ABANDONED"
        assert abandoned.lease_owner is None and abandoned.terminal_at_ms==at+2
        marked = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        assert marked.state is StrategyEntryVacuumState.DRAINING_ENTRY and marked.first_blocker=="OWNER_PAUSED"
    if early_resume and not deferred_cleanup:
        async with PostgresKernelUnitOfWork(database) as uow:
            owner=await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="early_resume_static_or_dynamic_drain",
                    idempotency_key=f"early-resume-drain:{group}:{static_source}",owner_identity="owner",now_ms=at+3),authentication_strength="totp_step_up")
        at+=1
    actual_execute = sa.ext.asyncio.AsyncConnection.execute
    async def corrupt_pause_completion(connection,statement,*args,**kwargs):
        if corrupt_completion and getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
            params = statement.compile().params
            if params.get("event_type")=="OWNER_PAUSED" and params.get("payload",{}).get("entry_drain_complete"):
                statement = statement.values(payload={"entry_drain_complete":"true" if corrupt_completion=="string_true" else False})
        return await actual_execute(connection,statement,*args,**kwargs)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+3)), patch.object(
        sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_pause_completion):
        drained = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at+3)
    assert drained.disposition is (MaterializationDisposition.WAITING_VACUUM if early_resume else MaterializationDisposition.OWNER_PAUSED),drained
    async with PostgresKernelUnitOfWork(database) as uow:
        finished = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        assert finished.state is StrategyEntryVacuumState.OWNER_PAUSED
        assert finished.entry_vacuum_id==vacuum.entry_vacuum_id and finished.fenced_at_ms==vacuum.fenced_at_ms
        assert finished.drained_at_ms==at+3 and finished.resolved_at_ms is None
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==original
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==uid
        assert await uow.strategy_universes.get_generation_universe_targets(abandoned.materialization_generation_id)==()
    if static_source:
        async with PostgresKernelUnitOfWork(database) as uow:
            paused_owner = await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=paused_owner.control_version,reason="retry_static_after_paused_drain",
                    idempotency_key=f"resume-static-drain:{group}",owner_identity="owner",now_ms=at+4),authentication_strength="totp_step_up")
        if corrupt_completion:
            async with PostgresKernelUnitOfWork(database) as uow:
                control = await uow.instrument_selection.get_selection_control(group)
                cadence = source.spec.cadence_hours*HOUR
                next_anchor = ((at+5)//cadence+1)*cadence
                scheduled = await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                    rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                    effective_period_anchor_ms=next_anchor,authentication_strength="totp_step_up",
                    request=ControlMutationRequest(expected_version=control.control_version,reason="corrupted_completion_must_not_grant",
                        idempotency_key=f"retry-corrupt-drain:{group}",owner_identity="owner",now_ms=at+5))
            due = next_anchor+HOUR+1
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)), pytest.raises(
                sa.exc.DBAPIError,match="Static retry requires exact original Vacuum handoff"):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:due)
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.get_generic_static_materialization_generation(
                    GenericStaticMaterializationGeneration.id_for_authorization(scheduled.pending_authorization_id)) is None
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==finished
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==original
            return
        await _assert_terminal_static_owner_reauthorization(database,group=group,at_ms=at+5)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
@pytest.mark.parametrize("old_stage", ["DESIRED","DRAINING_ENTRY","warming","staged"])
@pytest.mark.parametrize("retry_dynamic", [False,True,"unchanged","empty"])
async def test_first_dynamic_pause_restores_static_through_transition_scoped_recovery(database: AsyncEngine,group: str,old_stage: str,retry_dynamic: bool | str) -> None:
    from src.trading_kernel.application.owner_control import (
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    source=inputs(group)
    static_uid,comparison_id=await _install_static_selection_source(database,group)
    async with PostgresKernelUnitOfWork(database) as uow:
        owner_selection=await stage_generic_dynamic_selection_mode(uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
            request=ControlMutationRequest(expected_version=1,reason="first_dynamic_pause_recovery",
                idempotency_key=f"first-pause:{group}:{old_stage}",owner_identity="owner",now_ms=CUTOFF-1),authentication_strength="totp_step_up")
    source=source.model_copy(update={"selection_epoch_id":owner_selection.selection_epoch_id})
    snapshot=compute_generic_selection(source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot,decision_at_ms=source.decision_at_ms,source_observed_at_ms=source.source_observed_at_ms)
    request=CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="first-pause-materializer")
    start=snapshot.effective_from_ms+1
    for offset in range(12):
        at=start+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
            step=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda at=at:at)
        if step.materialization_generation_id:
            async with PostgresKernelUnitOfWork(database) as uow:
                generation=await uow.instrument_selection.get_generic_materialization_generation(step.materialization_generation_id)
                targets=await uow.strategy_universes.get_generation_universe_targets(step.materialization_generation_id)
            if generation.lifecycle_state.value==old_stage or (targets and targets[0].lifecycle_state.value==old_stage):
                break
            if targets and old_stage=="staged":
                await make_warming_ready(database,universe_version_id=targets[0].universe_version_id,warm_closed_bar_time_ms=at//HOUR*HOUR,valid_until_ms=at+HOUR)
                if group in {"MPG-001","MI-001"}:
                    template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                    delta=at//HOUR*HOUR-template.trigger_candle_close_time_ms
                    candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
                    cache=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=targets[0].universe_version_id,
                        strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=at//HOUR*HOUR,
                        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids))
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.strategy_universes.save_comparative_projection(cache)
    assert generation.lifecycle_state.value==old_stage or (targets and targets[0].lifecycle_state.value==old_stage)
    gid=generation.materialization_generation_id
    async with PostgresKernelUnitOfWork(database) as uow:
        owner=await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_first_attempt",
                idempotency_key=f"first-pause-control:{group}:{old_stage}",owner_identity="owner",now_ms=at+1),authentication_strength="totp_step_up")
    old_request=CoordinateGenericGenerationRequest(materialization_generation_id=gid,worker_id="first-pause-cleanup")
    for tick in (at+2,at+3):
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=old_request,clock_ms=lambda tick=tick:tick)
        assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with PostgresKernelUnitOfWork(database) as uow:
        abandoned=await uow.instrument_selection.get_generic_materialization_generation(gid)
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        assert abandoned.lifecycle_state.value=="ABANDONED"
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
        owner=await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_first_attempt_static",
                idempotency_key=f"first-resume-control:{group}:{old_stage}",owner_identity="owner",now_ms=at+4),authentication_strength="totp_step_up")
    await make_warming_ready(database,universe_version_id=static_uid,warm_closed_bar_time_ms=at//HOUR*HOUR,valid_until_ms=at+HOUR)
    if group in {"MPG-001","MI-001"}:
        template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        delta=at//HOUR*HOUR-template.trigger_candle_close_time_ms
        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        cache=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=static_uid,strategy_group_id=group,
            exchange_instrument_ids=source.spec.candidate_ids[:1],closed_bar_time_ms=at//HOUR*HOUR,lookback_bars=8 if group=="MPG-001" else 12,
            freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids[:1]))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(cache)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true"))
    @asynccontextmanager
    async def interrupted_first_restore():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("first paused recovery commit interruption")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+5)), pytest.raises(RuntimeError,match="first paused recovery commit"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_first_restore,request=old_request,clock_ms=lambda:at+5)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==vacuum
        assert (await uow.instrument_selection.get_selection_control(group)).pending_authorization_id==owner_selection.pending_authorization_id
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+5)):
        async with PostgresKernelUnitOfWork(database) as uow:
            proposal=await uow.instrument_selection.prepare_generic_recovery_grant_proof(gid)
    async with database.connect() as conn:
        check=sa.text("SELECT brc_generic_static_recovery_proof_matches(CAST(:proof AS jsonb),:at)")
        assert await conn.scalar(check,{"proof":proposal.model_dump_json(),"at":at+5}) is True
        forged=proposal.model_copy(update={"failed_activation_authorization_id":"authorization:forged"})
        assert await conn.scalar(check,{"proof":forged.model_dump_json(),"at":at+5}) is False
    async def omit_atomic_static_control(repository,proof):
        proof=forged
        await repository._connection.execute(sa.insert(selection_session_authorities).values(
            **generic_recovery_authority_storage_values(GenericRecoveryAuthority.build(proof=proof,authority_sequence=1))))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+5)), patch.object(
        PostgresInstrumentSelectionRepository,"commit_generic_recovery",new=omit_atomic_static_control), pytest.raises(sa.exc.DBAPIError):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=old_request,clock_ms=lambda:at+5)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+5)):
        recovered=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=old_request,clock_ms=lambda:at+5)
    assert recovered.disposition is MaterializationDisposition.FALLBACK_PREVIOUS,recovered
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at+6)):
        retried=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=old_request,clock_ms=lambda:at+6)
    assert retried.selection_authority_id==recovered.selection_authority_id
    async with PostgresKernelUnitOfWork(database) as uow:
        current=await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        control=await uow.instrument_selection.get_selection_control(group)
        assert control.selection_mode.value=="static_baseline" and control.pending_authorization_id is None and control.selection_epoch_id is None
        assert isinstance(current.authority,GenericRecoveryAuthority) and current.authority.selection_mode=="static_baseline"
        assert current.authority.first_eligible_close_time_ms>current.authority.created_at_ms
        assert current.authority.recovery_proof.recovery_close_plan.reason=="AUTHORITY_GAP"
        assert current.authority.event_binding.universe_version_id==static_uid and current.authority.comparison_universe_id==comparison_id
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) is None
    async with database.connect() as conn:
        assert (await conn.execute(sa.text("SELECT fenced_at_ms,drained_at_ms FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=:id"),{"id":vacuum.entry_vacuum_id})).one()==(vacuum.fenced_at_ms,vacuum.drained_at_ms)
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities WHERE selection_mode='dynamic_selection'"))==0
        scope_id=await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":static_uid})
    first_close=current.authority.first_eligible_close_time_ms
    await make_warming_ready(database,universe_version_id=static_uid,warm_closed_bar_time_ms=first_close,valid_until_ms=first_close+HOUR)
    template={"CPM-RO-001":cpm_long_snapshot,"BRF2-001":brf2_short_snapshot,"MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot}[group]()
    if retry_dynamic:
        template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot() if group=="MI-001" else cpm_flat_snapshot()
    delta=first_close-template.trigger_candle_close_time_ms
    class StaticRecoveryMarket:
        async def fetch_closed_candles(self,request):
            path=template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in path)
    if group in {"MPG-001","MI-001"}:
        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        cache=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=static_uid,strategy_group_id=group,
            exchange_instrument_ids=source.spec.candidate_ids[:1],closed_bar_time_ms=first_close,lookback_bars=8 if group=="MPG-001" else 12,
            freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids[:1]))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(cache)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+1)):
        suppressed=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),StaticRecoveryMarket(),ObservationRequest(
            runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=first_close,attempted_at_ms=first_close+1))
    assert suppressed.status is ObservationStatus.NO_SIGNAL,suppressed
    if not retry_dynamic:
        assert suppressed.detector_reason=="RECOVERY_REBASE_REQUIRED",suppressed
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==0
    if retry_dynamic:
        async with PostgresKernelUnitOfWork(database) as uow:
            control=await uow.instrument_selection.get_selection_control(group)
            baseline_id=control.rollback_baseline_id
            cadence=source.spec.cadence_hours*HOUR
            retry_at=first_close+2
            anchor=(retry_at//cadence+1)*cadence
            next_control=await stage_generic_dynamic_selection_mode(uow,strategy_group_id=group,effective_period_anchor_ms=anchor,
                request=ControlMutationRequest(expected_version=control.control_version,reason="fresh_dynamic_after_first_pause_static_recovery",
                    idempotency_key=f"fresh-first-pause:{group}:{old_stage}",owner_identity="owner",now_ms=retry_at),authentication_strength="totp_step_up")
        assert next_control.selection_epoch_id!=source.selection_epoch_id and next_control.rollback_baseline_id==baseline_id
        before_activation_close=first_close+HOUR
        await make_warming_ready(database,universe_version_id=static_uid,warm_closed_bar_time_ms=before_activation_close,valid_until_ms=before_activation_close+HOUR)
        if group in {"MPG-001","MI-001"}:
            shift=before_activation_close-first_close
            cache=build_comparative_universe_projection(
                event_spec_id=source.spec.event_spec_id,universe_version_id=static_uid,strategy_group_id=group,exchange_instrument_ids=source.spec.candidate_ids[:1],
                closed_bar_time_ms=before_activation_close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta+shift,"close_time_ms":c.close_time_ms+delta+shift}) for c in template.candles_1h)) for m in source.spec.candidate_ids[:1]))
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(cache)
        class ContinuedStaticMarket:
            async def fetch_closed_candles(self,request):
                path=template.candles_1h if request.timeframe=="1h" else template.candles_4h
                shift=before_activation_close-template.trigger_candle_close_time_ms
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift}) for c in path)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=before_activation_close+1)):
            continued_static=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),ContinuedStaticMarket(),ObservationRequest(
                runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=before_activation_close,attempted_at_ms=before_activation_close+1))
        assert continued_static.status is ObservationStatus.NO_SIGNAL,continued_static
        fresh_source=inputs(group).model_copy(update={"selection_epoch_id":next_control.selection_epoch_id})
        while fresh_source.feature_cutoff_at_ms<anchor:
            fresh_source=next_input(fresh_source)
        if retry_dynamic=="unchanged":
            fresh_source=fresh_source.model_copy(update={"member_windows":tuple(
                qualify_window(w.model_copy(update={"candles":fresh_source.member_windows[0].candles}),w.exchange_instrument_id==source.spec.candidate_ids[0]) for w in fresh_source.member_windows)})
        if retry_dynamic=="empty":
            fresh_source=fresh_source.model_copy(update={"member_windows":tuple(qualify_window(w,False) for w in fresh_source.member_windows)})
        class FreshSelectionMarket:
            async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
                return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for w in fresh_source.member_windows)
            async def fetch_generic_selection_klines(self,request):
                return next(w.candles for w in fresh_source.member_windows if w.exchange_instrument_id==request.exchange_instrument_id)
        tick=anchor
        def selection_clock():
            nonlocal tick
            tick+=1
            return tick
        selected=await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=FreshSelectionMarket(),
            request=RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,selection_epoch_id=next_control.selection_epoch_id,
                period_anchor_ms=anchor,worker_id="fresh-first-pause-selector"),clock_ms=selection_clock)
        assert selected.outcome=="SNAPSHOT_READY",selected
        async with PostgresKernelUnitOfWork(database) as uow:
            fresh=await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
        assert fresh.predecessor_snapshot_id is None and len(fresh.members)==24 and fresh.selection_epoch_id==next_control.selection_epoch_id
        fresh_request=CoordinateGenericSnapshotRequest(selection_snapshot_id=fresh.selection_snapshot_id,worker_id="fresh-first-pause-activation")
        await make_warming_ready(database,universe_version_id=static_uid,warm_closed_bar_time_ms=fresh.effective_from_ms,valid_until_ms=fresh.effective_from_ms+HOUR)
        if retry_dynamic=="unchanged" and group in {"CPM-RO-001","BRF2-001"}:
            @asynccontextmanager
            async def corrupted_unarmed_retry():
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow._connection.execute(sa.text("UPDATE brc_exposure_episode_current SET authority_recovery_armed_at_ms=NULL,authority_recovery_last_observed_at_ms=NULL,authority_recovery_last_detector_status=NULL WHERE event_spec_id=:event"),
                        {"event":source.spec.event_spec_id})
                    yield uow
            checked_at=fresh.effective_from_ms+1
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=checked_at)), patch.object(
                PostgresInstrumentSelectionRepository,"generic_recovery_transition_blocker",new=AsyncMock(return_value=None)), pytest.raises(
                    sa.exc.DBAPIError,match="Generic recovery rebase pending"):
                await coordinate_selection_materialization_once(uow_factory=corrupted_unarmed_retry,request=fresh_request,clock_ms=lambda:checked_at)
            async with PostgresKernelUnitOfWork(database) as uow:
                assert (await uow.instrument_selection.get_selection_control(group)).pending_authorization_id==next_control.pending_authorization_id
                assert (await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)).authority==current.authority
        for offset in range(1,15):
            activation_at=fresh.effective_from_ms+offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=activation_at)):
                activation=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=fresh_request,clock_ms=lambda activation_at=activation_at:activation_at)
            if activation.disposition in {MaterializationDisposition.ACTIVE_NEW,MaterializationDisposition.NO_CHANGE,MaterializationDisposition.VALID_EMPTY}:
                break
            if activation.materialization_generation_id:
                async with PostgresKernelUnitOfWork(database) as uow:
                    fresh_targets=await uow.strategy_universes.get_generation_universe_targets(activation.materialization_generation_id)
                if fresh_targets:
                    uid=fresh_targets[0].universe_version_id
                    await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=fresh.effective_from_ms,valid_until_ms=activation_at+HOUR)
                    if group in {"MPG-001","MI-001"}:
                        flat=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                        delta=fresh.effective_from_ms-flat.trigger_candle_close_time_ms
                        candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in flat.candles_1h)
                        cache=build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=uid,strategy_group_id=group,
                            exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=fresh.effective_from_ms,lookback_bars=8 if group=="MPG-001" else 12,
                            freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids))
                        async with PostgresKernelUnitOfWork(database) as uow:
                            await uow.strategy_universes.save_comparative_projection(cache)
        assert activation.disposition is (MaterializationDisposition.VALID_EMPTY if retry_dynamic=="empty" else
            MaterializationDisposition.NO_CHANGE if retry_dynamic=="unchanged" and group in {"CPM-RO-001","BRF2-001"} else MaterializationDisposition.ACTIVE_NEW),activation
        async with PostgresKernelUnitOfWork(database) as uow:
            active=await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            actual_control=await uow.instrument_selection.get_selection_control(group)
            assert actual_control.selection_mode.value=="dynamic_selection" and actual_control.selection_epoch_id==next_control.selection_epoch_id
            assert active.authority.selection_epoch_id==next_control.selection_epoch_id
            assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert active.authority.activation_authorization_id==next_control.pending_authorization_id
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_rollback_baselines WHERE strategy_group_id=:group"),{"group":group})==1
        if retry_dynamic=="empty":
            assert active.authority.blocks_new_entry and active.authority.event_binding.universe_version_id is None
            async with PostgresKernelUnitOfWork(database) as uow:
                assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==static_uid
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==0
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0
            return
        if group in {"CPM-RO-001","BRF2-001"}:
            await _issue_second_dynamic_noncomparative_trade(database,group=group)
        else:
            await _issue_second_dynamic_comparative_trade(database,group=group,selection_input=fresh_source)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==1
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands WHERE command_kind='entry'"))==1
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_aggregates WHERE status='terminal'"))==1


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001","MPG-001","MI-001","BRF2-001"])
@pytest.mark.parametrize("target_stage", ["warming","staged"])
async def test_owner_pause_abandons_generic_unactivated_targets(
    database: AsyncEngine, group: str, target_stage: str,
) -> None:
    from src.trading_kernel.application.owner_control import set_strategy_entry_state
    from src.trading_kernel.domain.owner_control import StrategyEntryState

    source, first, _, active_uid = await _exercise_generic_generation(
        database,group,False,durable=True,first_activation=True,natural_selection=True)
    shifted = next_input(source)
    second_source = shifted.model_copy(update={"predecessor_snapshot":first,
        "member_windows":tuple(qualify_window(window.model_copy(update={"candles":shifted.member_windows[0].candles}),
            window.exchange_instrument_id==source.spec.candidate_ids[0]) for window in shifted.member_windows)})
    second = compute_generic_selection(second_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(second,
            decision_at_ms=second_source.decision_at_ms,source_observed_at_ms=second_source.source_observed_at_ms)
        original = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=second.selection_snapshot_id,worker_id="pause-target-materializer")
    at = second.effective_from_ms
    for offset in range(1,12):
        tick = at+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            step = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda tick=tick:tick)
        if step.materialization_generation_id is None:
            continue
        async with PostgresKernelUnitOfWork(database) as uow:
            targets = await uow.strategy_universes.get_generation_universe_targets(step.materialization_generation_id)
        if not targets:
            continue
        target = targets[0]
        if target.lifecycle_state.value==target_stage:
            break
        await make_warming_ready(database,universe_version_id=target.universe_version_id,
            warm_closed_bar_time_ms=second.effective_from_ms,valid_until_ms=at+HOUR)
        if group in {"MPG-001","MI-001"}:
            template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
            delta = at-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
            projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
                universe_version_id=target.universe_version_id,strategy_group_id=group,
                exchange_instrument_ids=source.spec.candidate_ids,closed_bar_time_ms=at,
                lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in source.spec.candidate_ids))
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(projection)
    assert target.lifecycle_state.value==target_stage, step
    gid = step.materialization_generation_id
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
        async with PostgresKernelUnitOfWork(database) as uow:
            held = await uow.instrument_selection.claim_generic_materialization_generation(gid,
                worker_id="prepause-outstanding-callback",now_ms=tick,lease_duration_ms=30000)
            assert held.generation is not None and held.generation.lease_owner=="prepause-outstanding-callback"
            generation = await uow.instrument_selection.get_generic_materialization_generation(gid)
            current_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
            with pytest.raises(SelectionJobConflict,match="current Owner Pause"):
                await uow.instrument_selection.abandon_generation_for_owner_pause(
                    generation=generation,vacuum=current_vacuum,paused_at_ms=tick)
    async with PostgresKernelUnitOfWork(database) as uow:
        before = await uow.instrument_selection.get_generic_materialization_generation(gid)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
        owner = await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="abandon_unactivated_target",
                idempotency_key=f"pause-target:{group}:{target_stage}",owner_identity="owner",now_ms=tick+1),authentication_strength="totp_step_up")
    @asynccontextmanager
    async def interrupted_pause_cleanup():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected pause cleanup commit failure")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+2)), pytest.raises(RuntimeError,match="pause cleanup commit"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_pause_cleanup,request=request,clock_ms=lambda:tick+2)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==before
        assert (await uow.strategy_universes.get_generation_universe_targets(gid))[0].lifecycle_state.value==target_stage
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==vacuum
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+2)), patch(
        "src.trading_kernel.application.coordinate_selection_materialization._abandon_generation_targets",
        new=AsyncMock(return_value=None)), pytest.raises(SelectionJobConflict,match="abandoned targets"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:tick+2)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+2)):
        paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=request,clock_ms=lambda:tick+2)
    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    async with PostgresKernelUnitOfWork(database) as uow:
        abandoned = await uow.instrument_selection.get_generic_materialization_generation(gid)
        targets = await uow.strategy_universes.get_generation_universe_targets(gid)
        retained = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        current = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        paused_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
    assert targets[0].lifecycle_state.value=="abandoned"
    assert abandoned.lifecycle_state.value=="ABANDONED" and abandoned.terminal_at_ms==tick+2
    assert abandoned.lease_owner is None and abandoned.lease_expires_at_ms is None
    assert abandoned.semantic_digest==before.semantic_digest
    assert retained==original and current.universe_version_id==active_uid
    assert paused_vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
    assert paused_vacuum.fenced_at_ms==vacuum.fenced_at_ms and paused_vacuum.drained_at_ms==vacuum.drained_at_ms
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+3)):
        repeated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:tick+3)
    assert repeated.disposition is MaterializationDisposition.OWNER_PAUSED
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert not await uow.instrument_selection.release_generic_materialization_generation_lease(
            gid,worker_id="prepause-outstanding-callback",lease_epoch=held.generation.lease_epoch)
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_versions WHERE lifecycle_state IN ('warming','staged')"))==0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0
    async with PostgresKernelUnitOfWork(database) as uow:
        paused_owner = await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=paused_owner.control_version,reason="resume_does_not_revive_abandoned_target",
                idempotency_key=f"resume-target:{group}:{target_stage}",owner_identity="owner",now_ms=tick+4),authentication_strength="totp_step_up")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick+5)):
        old_callback = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:tick+5)
    assert old_callback.disposition is MaterializationDisposition.BLOCKED
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert (await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)).blocks_new_entry
    empty_source=next_input(second_source).model_copy(update={"predecessor_snapshot":second})
    empty_source=empty_source.model_copy(update={"member_windows":tuple(qualify_window(window,False) for window in empty_source.member_windows)})
    empty=compute_generic_selection(empty_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(empty,decision_at_ms=empty_source.decision_at_ms,source_observed_at_ms=empty_source.source_observed_at_ms)
    empty_at=empty.effective_from_ms+1
    empty_request=CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,worker_id="empty-after-paused-target")
    actual_execute=sa.ext.asyncio.AsyncConnection.execute
    async def corrupt_paused_handoff(connection,statement,*args,**kwargs):
        if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
            params=statement.compile().params
            if params.get("event_type")=="VALID_EMPTY_INTENT" and params.get("payload",{}).get("supersedes_owner_pause"):
                statement=statement.values(payload={**params["payload"],"supersedes_owner_pause":False})
        return await actual_execute(connection,statement,*args,**kwargs)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)), patch.object(
        sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_paused_handoff), pytest.raises(sa.exc.DBAPIError,match="Owner Pause EMPTY requires exact"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:empty_at)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==paused_vacuum
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==original
    async def omit_paused_negative_authority(repository,negative,*,entry_vacuum_id,**kwargs):
        await repository._connection.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='VALID_EMPTY',resolved_at_ms=:at,"
            "projection_version=projection_version+1 WHERE entry_vacuum_id=:id"),{"at":negative.created_at_ms,"id":entry_vacuum_id})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)), patch.object(
        PostgresInstrumentSelectionRepository,"commit_generic_valid_empty",new=omit_paused_negative_authority), pytest.raises(
            sa.exc.DBAPIError,match="VALID_EMPTY requires atomic negative Authority"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:empty_at)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==paused_vacuum
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at)):
        outcome=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=empty_request,clock_ms=lambda:empty_at)
    assert outcome.disposition is MaterializationDisposition.VALID_EMPTY,outcome
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=empty_at+1)):
        retried=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=empty_request,clock_ms=lambda:empty_at+1)
    assert retried.disposition is MaterializationDisposition.VALID_EMPTY
    assert retried.selection_authority_id==outcome.selection_authority_id
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(gid)==abandoned
        assert (await uow.strategy_universes.get_generation_universe_targets(gid))[0].lifecycle_state.value=="abandoned"
        assert (await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)).authority.authority_outcome=="VALID_EMPTY"
        assert (await uow.strategy_universes.get_current(source.spec.event_spec_id)).universe_version_id==active_uid
    async with database.connect() as conn:
        fact=(await conn.execute(sa.text("SELECT state,fenced_at_ms,drained_at_ms FROM brc_strategy_entry_vacuums_current WHERE entry_vacuum_id=:id"),{"id":vacuum.entry_vacuum_id})).one()
        assert fact==("VALID_EMPTY",vacuum.fenced_at_ms,vacuum.drained_at_ms)


@pytest.mark.asyncio
@pytest.mark.parametrize("latest_outcome", ["NO_CHANGE", "VALID_EMPTY"])
async def test_new_no_change_snapshot_supersedes_unfenced_desired_after_continuity(
    database: AsyncEngine, latest_outcome: str,
) -> None:
    group = "CPM-RO-001"
    source, first, _, uid = await _exercise_generic_generation(
        database, group, False, durable=True, first_activation=True, natural_selection=True)
    shifted = next_input(source)
    second_source = shifted.model_copy(update={
        "predecessor_snapshot": first,
        "member_windows": tuple(qualify_window(
            window.model_copy(update={"candles": shifted.member_windows[0].candles}),
            window.exchange_instrument_id == source.spec.candidate_ids[0])
            for window in shifted.member_windows),
    })
    second = compute_generic_selection(second_source)
    at = second.effective_from_ms+1
    await make_warming_ready(database, universe_version_id=uid,
        warm_closed_bar_time_ms=second.effective_from_ms, valid_until_ms=at+HOUR)
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        continuity = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database),
            request=CoordinateGenericPeriodRequest(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id, period_anchor_ms=second.feature_cutoff_at_ms,
                worker_id="continuity-before-unfenced-desired"), clock_ms=lambda: at)
    assert continuity.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, continuity
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(second,
            decision_at_ms=second_source.decision_at_ms, source_observed_at_ms=second_source.source_observed_at_ms)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=second.selection_snapshot_id,
        worker_id="unfenced-desired")
    for tick in (at+1, at+2):
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            old = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request, clock_ms=lambda tick=tick: tick)
    assert old.disposition is MaterializationDisposition.GENERATION_DESIRED, old
    third_source = next_input(next_input(source)).model_copy(update={"predecessor_snapshot": second})
    if latest_outcome == "VALID_EMPTY":
        third_source = third_source.model_copy(update={"member_windows": tuple(
            qualify_window(window, False) for window in third_source.member_windows)})
    third = compute_generic_selection(third_source)
    assert third.selected_members == (first.selected_members if latest_outcome == "NO_CHANGE" else ())
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(third,
            decision_at_ms=third_source.decision_at_ms, source_observed_at_ms=third_source.source_observed_at_ms)
    at = third.effective_from_ms+1
    await make_warming_ready(database, universe_version_id=uid,
        warm_closed_bar_time_ms=third.effective_from_ms, valid_until_ms=at+HOUR)
    async def apply_latest_outcome():
        for _ in range(4):
            result = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database),
                request=CoordinateGenericSnapshotRequest(selection_snapshot_id=third.selection_snapshot_id,
                    worker_id="latest-no-change-or-empty"), clock_ms=lambda: at)
            if result.disposition in {MaterializationDisposition.NO_CHANGE, MaterializationDisposition.VALID_EMPTY}:
                return result
        raise AssertionError(result)

    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)), patch.object(
            PostgresInstrumentSelectionRepository, "_supersede_unfenced_generic_predecessors",
            new=AsyncMock(return_value=None)), pytest.raises(sa.exc.DBAPIError, match="unfinished Generation"):
        await apply_latest_outcome()
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        unchanged = await apply_latest_outcome()
    assert unchanged.disposition.value == latest_outcome, unchanged
    async with PostgresKernelUnitOfWork(database) as uow:
        superseded = await uow.instrument_selection.get_generic_materialization_generation(old.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
    assert superseded is not None and superseded.lifecycle_state.value == "SUPERSEDED"
    assert vacuum is None
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at+1)):
        stale = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request, clock_ms=lambda: at+1)
    assert stale.disposition is MaterializationDisposition.BLOCKED


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("old_stage", ["DESIRED", "DRAINING_ENTRY"])
async def test_latest_nonempty_snapshot_takes_over_early_generation_after_drain(
    database: AsyncEngine, group: str, old_stage: str,
) -> None:
    source, first_snapshot, _, active_uid = await _exercise_generic_generation(
        database, group, False, durable=True, first_activation=True, natural_selection=True)
    shifted = next_input(source)
    second_source = shifted.model_copy(update={
        "predecessor_snapshot": first_snapshot,
        "member_windows": tuple(qualify_window(
            window.model_copy(update={"candles": shifted.member_windows[0].candles}),
            window.exchange_instrument_id == source.spec.candidate_ids[0])
            for window in shifted.member_windows),
    })
    second = compute_generic_selection(second_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(second,
            decision_at_ms=second_source.decision_at_ms,
            source_observed_at_ms=second_source.source_observed_at_ms)
        original_authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=second.selection_snapshot_id,
        worker_id="early-generation-owner")
    stop = MaterializationDisposition.GENERATION_DESIRED if old_stage == "DESIRED" else MaterializationDisposition.WAITING_VACUUM
    for offset in range(4):
        tick = second.effective_from_ms+1+offset
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request,
                clock_ms=lambda tick=tick: tick)
        if step.disposition is stop:
            break
    assert step.disposition is stop, step
    old_id = step.materialization_generation_id
    async with PostgresKernelUnitOfWork(database) as uow:
        old = await uow.instrument_selection.get_generic_materialization_generation(old_id)
        original_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
    assert old is not None and old.lifecycle_state.value == old_stage
    assert (original_vacuum is None) == (old_stage == "DESIRED")
    newest_source = next_input(second_source)
    newest = compute_generic_selection(newest_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(newest,
            decision_at_ms=newest_source.decision_at_ms,
            source_observed_at_ms=newest_source.source_observed_at_ms)
    newest_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=newest.selection_snapshot_id,
        worker_id="newest-early-target-owner")
    at = newest.effective_from_ms+1
    @asynccontextmanager
    async def paused_early_handoff():
        async with PostgresKernelUnitOfWork(database) as uow:
            assert uow._connection is not None
            pause_probe = await uow._connection.begin_nested()
            await uow._connection.execute(sa.text("UPDATE brc_strategy_entry_controls_current "
                "SET entry_state='paused' WHERE strategy_group_id=:group"), {"group": group})
            yield uow
            await pause_probe.rollback()
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        paused = await coordinate_selection_materialization_once(uow_factory=paused_early_handoff,
            request=newest_request, clock_ms=lambda: at)
    assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
    # Rollback of the entire handoff must retain both unfenced and fenced sources.
    @asynccontextmanager
    async def interrupted_early_handoff():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected early handoff rollback")

    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)), pytest.raises(RuntimeError, match="early handoff rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_early_handoff,
            request=newest_request, clock_ms=lambda: at)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(old_id) == old
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id) == original_vacuum
    steps = []
    for offset in range(6):
        tick = newest.effective_from_ms+1+offset
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=tick)):
            takeover = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request,
                clock_ms=lambda tick=tick: tick)
        steps.append(takeover)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) == original_authority
            active = await uow.strategy_universes.get_current(source.spec.event_spec_id)
            assert active is not None and active.universe_version_id == active_uid
            assert await uow.strategy_universes.get_generation_universe_targets(old_id) == ()
        if takeover.disposition is MaterializationDisposition.GENERATION_MATERIALIZING:
            break
    assert takeover.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, steps
    async with PostgresKernelUnitOfWork(database) as uow:
        superseded = await uow.instrument_selection.get_generic_materialization_generation(old_id)
        replacement = await uow.instrument_selection.get_generic_materialization_generation(takeover.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
    assert superseded is not None and superseded.lifecycle_state.value == "SUPERSEDED"
    assert replacement is not None and replacement.previous_events == old.previous_events
    assert vacuum is not None and vacuum.drained_at_ms is not None
    assert vacuum.source_generation_id == replacement.materialization_generation_id
    if original_vacuum is not None:
        assert vacuum.entry_vacuum_id == original_vacuum.entry_vacuum_id
        assert vacuum.fenced_at_ms == original_vacuum.fenced_at_ms
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=tick+1)):
        stale = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request, clock_ms=lambda: tick+1)
    assert stale.disposition is MaterializationDisposition.BLOCKED
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("restore_current_members", [False, True])
@pytest.mark.parametrize("staged_old_target,pause_before_takeover,corrupt_completion", [(False,False,None),(True,False,None),(False,True,None),(True,True,None),
    ("draining",True,None),("draining",True,"false"),("draining",True,"string"),
    ("deferred_warming",True,None),("deferred_staged",True,None),("deferred_draining",True,None)])
async def test_latest_nonempty_snapshot_supersedes_unfinished_warming_target(
    database: AsyncEngine, group: str, restore_current_members: bool, staged_old_target: bool | str, pause_before_takeover: bool,corrupt_completion: str | None,
) -> None:
    deferred_cleanup=isinstance(staged_old_target,str) and staged_old_target.startswith("deferred_")
    if deferred_cleanup:
        staged_old_target={"deferred_warming":False,"deferred_staged":True,"deferred_draining":"draining"}[staged_old_target]
    source, first_snapshot, _, active_uid = await _exercise_generic_generation(
        database, group, False, durable=True, first_activation=True, natural_selection=True)
    shifted = next_input(source)
    second_source = shifted.model_copy(update={
        "predecessor_snapshot": first_snapshot,
        "member_windows": tuple(qualify_window(
            window.model_copy(update={"candles": shifted.member_windows[0].candles}),
            window.exchange_instrument_id == source.spec.candidate_ids[0])
            for window in shifted.member_windows),
    })
    second = compute_generic_selection(second_source)
    assert second.selected_members != first_snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(second,
            decision_at_ms=second_source.decision_at_ms,
            source_observed_at_ms=second_source.source_observed_at_ms)
        original_authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=second.selection_snapshot_id,
        worker_id="unfinished-target-owner")
    for offset in range(8):
        at = second.effective_from_ms + 1 + offset
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request,
                clock_ms=lambda at=at: at)
        if step.disposition is (MaterializationDisposition.WAITING_VACUUM if staged_old_target=="draining" else MaterializationDisposition.TARGET_WARMING):
            break
    assert step.disposition is (MaterializationDisposition.WAITING_VACUUM if staged_old_target=="draining" else MaterializationDisposition.TARGET_WARMING), step
    old_id = step.materialization_generation_id
    async with PostgresKernelUnitOfWork(database) as uow:
        old = await uow.instrument_selection.get_generic_materialization_generation(old_id)
        old_targets = await uow.strategy_universes.get_generation_universe_targets(old_id)
        original_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
    assert old is not None and old.lifecycle_state.value == ("DRAINING_ENTRY" if staged_old_target=="draining" else "MATERIALIZING")
    assert (old_targets==()) if staged_old_target=="draining" else (len(old_targets) == 1 and old_targets[0].lifecycle_state.value == "warming")
    assert original_vacuum is not None

    async def ready_target(uid: str, at: int) -> None:
        await make_warming_ready(database, universe_version_id=uid,
            warm_closed_bar_time_ms=at//HOUR*HOUR, valid_until_ms=at+HOUR)
        if group in {"MPG-001", "MI-001"}:
            template = mpg_long_snapshot() if group == "MPG-001" else mi_long_snapshot()
            delta = at//HOUR*HOUR-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms": c.open_time_ms+delta,
                "close_time_ms": c.close_time_ms+delta}) for c in template.candles_1h)
            projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
                universe_version_id=uid, strategy_group_id=group,
                exchange_instrument_ids=source.spec.candidate_ids, closed_bar_time_ms=at//HOUR*HOUR,
                lookback_bars=8 if group == "MPG-001" else 12, freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,
                    candles_1h=candles) for member in source.spec.candidate_ids))
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(projection)

    if staged_old_target is True:
        stage_at = second.effective_from_ms+20
        await ready_target(old_targets[0].universe_version_id, stage_at)
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=stage_at)):
            staged = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request,
                clock_ms=lambda: stage_at)
        assert staged.disposition is MaterializationDisposition.GENERATION_STAGED, staged
    if pause_before_takeover:
        from src.trading_kernel.application.owner_control import (
            set_strategy_entry_state,
        )
        from src.trading_kernel.domain.owner_control import StrategyEntryState
        for offset,state in ((21,StrategyEntryState.PAUSED),(25,StrategyEntryState.ENABLED)):
            async with PostgresKernelUnitOfWork(database) as uow:
                owner=await uow.owner_controls.get_strategy_control(group)
                await set_strategy_entry_state(uow,strategy_group_id=group,target_state=state,
                    request=ControlMutationRequest(expected_version=owner.control_version,reason="paused_nonempty_takeover",
                        idempotency_key=f"paused-nonempty:{group}:{restore_current_members}:{staged_old_target}:{offset}",
                        owner_identity="owner",now_ms=second.effective_from_ms+offset),authentication_strength="totp_step_up")
            if state is StrategyEntryState.PAUSED and not deferred_cleanup:
                paused_at=second.effective_from_ms+22
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at)):
                    paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda paused_at=paused_at:paused_at)
                assert paused.disposition is MaterializationDisposition.OWNER_PAUSED
                if staged_old_target=="draining":
                    actual_execute=sa.ext.asyncio.AsyncConnection.execute
                    async def corrupt_completion_event(connection,statement,*args,actual_execute=actual_execute,**kwargs):
                        if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
                            params=statement.compile().params
                            if params.get("event_type")=="OWNER_PAUSED" and params.get("payload",{}).get("entry_drain_complete"):
                                statement=statement.values(payload={"entry_drain_complete":"true" if corrupt_completion=="string" else False})
                        return await actual_execute(connection,statement,*args,**kwargs)
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=paused_at+1)):
                        if corrupt_completion:
                            with patch.object(sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_completion_event):
                                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda paused_at=paused_at:paused_at+1)
                        else:
                            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda paused_at=paused_at:paused_at+1)
                async with PostgresKernelUnitOfWork(database) as uow:
                    old=await uow.instrument_selection.get_generic_materialization_generation(old_id)
                    original_vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
                assert old.lifecycle_state.value=="ABANDONED" and original_vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
        if deferred_cleanup:
            async with PostgresKernelUnitOfWork(database) as uow:
                before_cleanup=await uow.instrument_selection.get_generic_materialization_generation(old_id)
                before_targets=await uow.strategy_universes.get_generation_universe_targets(old_id)
            actual_execute=sa.ext.asyncio.AsyncConnection.execute
            async def corrupt_deferred_cleanup(connection,statement,*args,**kwargs):
                if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_universe_materialization_events" and getattr(statement,"is_insert",False):
                    params=statement.compile().params
                    if params.get("event_type")=="ABANDONED" and params.get("payload",{}).get("cleanup_deferred"):
                        statement=statement.values(payload={**params["payload"],"owner_pause_authorization_id":"authorization:forged"})
                return await actual_execute(connection,statement,*args,**kwargs)
            cleanup_at=second.effective_from_ms+26
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=cleanup_at)), patch.object(
                sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_deferred_cleanup), pytest.raises(sa.exc.DBAPIError,match="Deferred cleanup requires exact"):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:cleanup_at)
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.get_generic_materialization_generation(old_id)==before_cleanup
                assert await uow.strategy_universes.get_generation_universe_targets(old_id)==before_targets
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==original_authority
            for cleanup_at in ((second.effective_from_ms+26,second.effective_from_ms+27) if staged_old_target=="draining" else (second.effective_from_ms+26,)):
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=cleanup_at)):
                    cleanup=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda cleanup_at=cleanup_at:cleanup_at)
                assert cleanup.disposition is MaterializationDisposition.WAITING_VACUUM,cleanup
            async with PostgresKernelUnitOfWork(database) as uow:
                old=await uow.instrument_selection.get_generic_materialization_generation(old_id)
                original_vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)
            assert old.lifecycle_state.value=="ABANDONED" and original_vacuum.state is StrategyEntryVacuumState.OWNER_PAUSED
    newest_source = next_input(source if restore_current_members else second_source)
    if restore_current_members:
        # Restore the first selection's geometry at the third period, not a SQL member edit.
        newest_source = next_input(newest_source).model_copy(update={"predecessor_snapshot": second})
    newest = compute_generic_selection(newest_source)
    assert newest.selected_members
    if restore_current_members:
        assert newest.selected_members == first_snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(newest,
            decision_at_ms=newest_source.decision_at_ms,
            source_observed_at_ms=newest_source.source_observed_at_ms)
    at = newest.effective_from_ms + 1
    newest_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=newest.selection_snapshot_id,
        worker_id="latest-target-owner")
    if corrupt_completion:
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
                {"vid":original_vacuum.entry_vacuum_id,"source":original_authority.authority.selection_authority_id,"at":at}) is False
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)), pytest.raises(
            SelectionJobConflict,match="Owner resume provenance missing"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=newest_request,clock_ms=lambda:at)
        actual_scalar=sa.ext.asyncio.AsyncConnection.scalar
        async def bypass_python_proof(connection,statement,*args,**kwargs):
            if "brc_generic_vacuum_owner_resume_matches" in str(statement):
                return True
            return await actual_scalar(connection,statement,*args,**kwargs)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)), patch.object(
            sa.ext.asyncio.AsyncConnection,"scalar",new=bypass_python_proof), pytest.raises(sa.exc.DBAPIError,match="Owner Pause nonempty handoff requires exact"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=newest_request,clock_ms=lambda:at)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id)==original_vacuum
            assert await uow.instrument_selection.get_generic_materialization_generation(old_id)==old
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)==original_authority
            assert await uow.instrument_selection.get_generic_materialization_generation(GenericMaterializationGeneration.id_for_snapshot(newest.selection_snapshot_id)) is None
        return

    @asynccontextmanager
    async def interrupted_takeover():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected supersession rollback")

    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)), pytest.raises(RuntimeError, match="supersession rollback"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_takeover,
            request=newest_request, clock_ms=lambda: at)
    if pause_before_takeover:
        actual_execute=sa.ext.asyncio.AsyncConnection.execute
        async def corrupt_paused_nonempty_handoff(connection,statement,*args,**kwargs):
            if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_universe_materialization_events" and getattr(statement,"is_insert",False):
                params=statement.compile().params
                if params.get("event_type")=="MATERIALIZING" and params.get("payload",{}).get("supersedes_generation_id")==old_id:
                    statement=statement.values(payload={**params["payload"],"supersedes_generation_id":"generation:forged"})
            return await actual_execute(connection,statement,*args,**kwargs)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)), patch.object(
            sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_paused_nonempty_handoff), pytest.raises(
                sa.exc.DBAPIError,match="Owner Pause nonempty handoff requires exact"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=newest_request,clock_ms=lambda:at)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id) == original_vacuum
        assert await uow.instrument_selection.get_generic_materialization_generation(
            GenericMaterializationGeneration.id_for_snapshot(newest.selection_snapshot_id)) is None
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at)):
        takeover = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request,
            clock_ms=lambda: at)
    assert takeover.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, takeover
    async with PostgresKernelUnitOfWork(database) as uow:
        retired = await uow.instrument_selection.get_generic_materialization_generation(old_id)
        targets = await uow.strategy_universes.get_generation_universe_targets(old_id)
        replacement = await uow.instrument_selection.get_generic_materialization_generation(takeover.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        active = await uow.strategy_universes.get_current(source.spec.event_spec_id)
    assert retired is not None and retired.lifecycle_state.value == ("ABANDONED" if pause_before_takeover else "SUPERSEDED")
    if pause_before_takeover:
        assert retired==old
    assert all(target.lifecycle_state.value == "abandoned" for target in targets)
    assert replacement is not None and replacement.selection_snapshot_id == newest.selection_snapshot_id
    assert replacement.previous_events == old.previous_events
    assert vacuum is not None and vacuum.entry_vacuum_id == original_vacuum.entry_vacuum_id
    assert vacuum.fenced_at_ms == original_vacuum.fenced_at_ms
    assert vacuum.drained_at_ms == original_vacuum.drained_at_ms
    assert vacuum.source_generation_id == replacement.materialization_generation_id
    assert authority == original_authority
    assert active is not None and active.universe_version_id == active_uid
    assert retired.lease_owner is None and retired.lease_expires_at_ms is None
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at+1)):
        stale = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=request, clock_ms=lambda: at+1)
        warming = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request, clock_ms=lambda: at+1)
    assert stale.disposition is MaterializationDisposition.BLOCKED
    assert warming.disposition is MaterializationDisposition.TARGET_WARMING, warming
    if restore_current_members:
        # Repeated retargets retain the original fence, not the last Generation's fence.
        chained_source = next_input(newest_source)
        chained = compute_generic_selection(chained_source)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(chained,
                decision_at_ms=chained_source.decision_at_ms,
                source_observed_at_ms=chained_source.source_observed_at_ms)
        prior_replacement = replacement
        previous_request = newest_request
        newest_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=chained.selection_snapshot_id,
            worker_id="chained-latest-target-owner")
        at = chained.effective_from_ms+1
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            chained_takeover = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request, clock_ms=lambda: at)
        assert chained_takeover.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, chained_takeover
        async with PostgresKernelUnitOfWork(database) as uow:
            replacement = await uow.instrument_selection.get_generic_materialization_generation(chained_takeover.materialization_generation_id)
            superseded = await uow.instrument_selection.get_generic_materialization_generation(prior_replacement.materialization_generation_id)
            vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group, selection_spec_id=source.spec.selection_spec_id)
        assert replacement is not None and replacement.selection_snapshot_id == chained.selection_snapshot_id
        assert superseded is not None and superseded.lifecycle_state.value == "SUPERSEDED"
        assert vacuum is not None and vacuum.fenced_at_ms == original_vacuum.fenced_at_ms
        assert vacuum.drained_at_ms == original_vacuum.drained_at_ms
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
            new=AsyncMock(return_value=at+1)):
            stale = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=previous_request, clock_ms=lambda: at+1)
            warming = await coordinate_selection_materialization_once(
                uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request, clock_ms=lambda: at+1)
        assert stale.disposition is MaterializationDisposition.BLOCKED
        assert warming.disposition is MaterializationDisposition.TARGET_WARMING, warming
    async with PostgresKernelUnitOfWork(database) as uow:
        replacement_targets = await uow.strategy_universes.get_generation_universe_targets(replacement.materialization_generation_id)
    assert len(replacement_targets) == 1
    await ready_target(replacement_targets[0].universe_version_id, at+2)
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at+2)):
        staged = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request, clock_ms=lambda: at+2)
    assert staged.disposition is MaterializationDisposition.GENERATION_STAGED, staged
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at+3)):
        async with PostgresKernelUnitOfWork(database) as uow:
            proof = await uow.instrument_selection.prepare_generic_recovered_activation_proof(replacement.materialization_generation_id)
    assert proof.recovery_close_plan.reason == "AUTHORITY_GAP"
    assert proof.first_eligible_close_time_ms > proof.committed_at_ms
    assert proof.episode_rebase_required is True
    async with database.connect() as conn:
        if pause_before_takeover:
            params={"vid":original_vacuum.entry_vacuum_id,"source":original_authority.authority.selection_authority_id,"at":proof.committed_at_ms}
            assert await conn.scalar(sa.text("SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),params) is True
            assert await conn.scalar(sa.text("SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
                {**params,"at":second.effective_from_ms+22}) is False
            assert await conn.scalar(sa.text("SELECT brc_generic_vacuum_owner_resume_matches(:vid,:source,:at)"),
                {**params,"source":"authority:forged"}) is False
            wrong_owner=proof.model_copy(update={"owner_control_version":original_authority.authority.owner_control_version})
            assert await conn.scalar(sa.text("SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
                {"proof":wrong_owner.model_dump_json(),"checked_at":proof.committed_at_ms}) is False
        assert await conn.scalar(sa.text(
            "SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof": proof.model_dump_json(), "checked_at": proof.committed_at_ms}) is True
        wrong_source = proof.model_copy(update={"source_selection_authority_id": "authority:forged"})
        assert await conn.scalar(sa.text(
            "SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)"),
            {"proof": wrong_source.model_dump_json(), "checked_at": proof.committed_at_ms}) is False
        assert await conn.scalar(sa.text(
            "SELECT count(*) FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid AND event_type='FAILED_CLOSED'"), {"gid": old_id}) == 0
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms",
        new=AsyncMock(return_value=at+3)):
        activated = await coordinate_selection_materialization_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(database), request=newest_request, clock_ms=lambda: at+3)
    assert activated.disposition is MaterializationDisposition.ACTIVE_NEW, activated
    async with PostgresKernelUnitOfWork(database) as uow:
        recovered = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
    assert recovered is not None and isinstance(recovered.authority, GenericRecoveryAuthority)
    assert recovered.authority.first_eligible_close_time_ms > at+3


@pytest.mark.asyncio
@pytest.mark.parametrize(("group","resolution"),(
    ("CPM-RO-001","fallback"),("MPG-001","activate"),("MPG-001","activate_refusal"),("MPG-001","empty"),
    ("MI-001","activate"),("MI-001","activate_refusal"),("MI-001","empty"),("BRF2-001","fallback"),
    ("MPG-001","activate_change_guard"),("MI-001","activate_change_guard"),
    ("MPG-001","activate_change_after_arm"),("MI-001","activate_change_after_arm"),
    ("CPM-RO-001","fallback_armed_static"),("BRF2-001","fallback_armed_static"),
    ("CPM-RO-001","fallback_continued_static"),("BRF2-001","fallback_continued_static")))
async def test_failed_second_dynamic_generation_respects_previous_freshness(
    database: AsyncEngine,group: str,resolution: str,
) -> None:
    first_result = await _exercise_generic_generation(database,group,False,
        durable=True,first_activation=True,natural_selection=True)
    first_source,first_snapshot,_,previous_uid = first_result
    async with PostgresKernelUnitOfWork(database) as uow:
        previous_authority = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        assert previous_authority is not None
        control = await uow.instrument_selection.get_selection_control(group)
        assert control is not None and control.selection_mode.value == "dynamic_selection"
    shifted_source = next_input(first_source)
    successor_source = shifted_source.model_copy(update={
        "predecessor_snapshot":first_snapshot,
        "member_windows":tuple(qualify_window(
            window.model_copy(update={"candles":shifted_source.member_windows[0].candles}),
            window.exchange_instrument_id==first_source.spec.candidate_ids[0])
            for window in shifted_source.member_windows),
    })
    successor = compute_generic_selection(successor_source)
    assert successor.selected_members != first_snapshot.selected_members
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(successor,
            decision_at_ms=successor_source.decision_at_ms,
            source_observed_at_ms=successor_source.source_observed_at_ms)
    start = successor.effective_from_ms+1
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=successor.selection_snapshot_id,
        worker_id="dynamic-second-failure")
    steps = []
    for offset in range(6):
        at = start+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=at)):
            step = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda at=at:at)
        steps.append(step)
        if step.disposition is MaterializationDisposition.GENERATION_MATERIALIZING:
            break
    assert steps[-1].disposition is MaterializationDisposition.GENERATION_MATERIALIZING, steps
    generation_id = steps[-1].materialization_generation_id
    async with PostgresKernelUnitOfWork(database) as uow:
        materializing = await uow.instrument_selection.get_generic_materialization_generation(generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
    assert materializing is not None and materializing.fenced_at_ms is not None
    assert vacuum is not None and vacuum.state.value == "RECONFIGURING"
    fail_at = materializing.fenced_at_ms+first_source.spec.materialization_timeout_ms
    generation_request = CoordinateGenericGenerationRequest(
        materialization_generation_id=generation_id,worker_id="dynamic-failure-coordinator")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=fail_at)):
        failed = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=generation_request,
            clock_ms=lambda:fail_at)
    assert failed.reason_code == "MATERIALIZATION_TIMEOUT", failed
    async with database.connect() as conn:
        failure_payload = await conn.scalar(sa.text(
            "SELECT payload FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid AND event_type='FAILED_CLOSED'"),
            {"gid":generation_id})
    assert failure_payload is not None
    assert failure_payload["no_eligible_close_before_expiry"] == (group in {"MPG-001","MI-001"})
    assert failure_payload["next_future_close_time_ms"] == (fail_at//HOUR+1)*HOUR
    await make_warming_ready(database,universe_version_id=previous_uid,
        warm_closed_bar_time_ms=fail_at//HOUR*HOUR,
        valid_until_ms=fail_at+HOUR)
    if group in {"MPG-001","MI-001"}:
        template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        closed = fail_at//HOUR*HOUR
        delta = closed-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta})
            for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,
            universe_version_id=previous_uid,strategy_group_id=group,
            exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=closed,
            lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles)
                for member in first_source.spec.candidate_ids)).model_copy(update={
                    "comparison_transition_revision":previous_authority.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=fail_at+1)):
        async with PostgresKernelUnitOfWork(database) as uow:
            if group in {"MPG-001","MI-001"}:
                with pytest.raises(SelectionJobConflict,match="Dynamic recovery source membership stale"):
                    await uow.instrument_selection.prepare_generic_recovery_grant_proof(generation_id)
            else:
                proposal = await uow.instrument_selection.prepare_generic_recovery_grant_proof(generation_id)
    if group in {"MPG-001","MI-001"}:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=fail_at+1)):
            refused = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=generation_request,
                clock_ms=lambda:fail_at+1)
        assert refused.disposition is MaterializationDisposition.BLOCKED
        async with PostgresKernelUnitOfWork(database) as uow:
            still_previous = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
            still_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
        assert still_previous is not None
        assert still_previous.authority.selection_authority_id == previous_authority.authority.selection_authority_id
        assert still_vacuum is not None and still_vacuum.state.value == "RECONFIGURING"
        next_source = next_input(successor_source)
        next_snapshot = compute_generic_selection(next_source)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(next_snapshot,
                decision_at_ms=next_source.decision_at_ms,
                source_observed_at_ms=next_source.source_observed_at_ms)
        next_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=next_snapshot.selection_snapshot_id,
            worker_id="new-period-after-failure")
        next_at = next_snapshot.effective_from_ms+1
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=next_at)):
            handoff = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                clock_ms=lambda:next_at)
        assert handoff.disposition is MaterializationDisposition.GENERATION_MATERIALIZING, handoff
        assert handoff.materialization_generation_id != generation_id
        async with PostgresKernelUnitOfWork(database) as uow:
            old_generation = await uow.instrument_selection.get_generic_materialization_generation(generation_id)
            new_generation = await uow.instrument_selection.get_generic_materialization_generation(handoff.materialization_generation_id)
            resumed_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
            still_previous = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        assert old_generation is not None and old_generation.lifecycle_state.value == "FAILED_CLOSED"
        assert new_generation is not None and new_generation.lifecycle_state.value == "MATERIALIZING"
        assert new_generation.fenced_at_ms == next_at
        assert resumed_vacuum is not None and resumed_vacuum.entry_vacuum_id == vacuum.entry_vacuum_id
        assert resumed_vacuum.source_generation_id == handoff.materialization_generation_id
        assert resumed_vacuum.fenced_at_ms == vacuum.fenced_at_ms
        assert resumed_vacuum.drained_at_ms == vacuum.drained_at_ms
        assert still_previous is not None
        assert still_previous.authority.selection_authority_id == previous_authority.authority.selection_authority_id
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=next_at+1)):
            stale_callback = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=generation_request,
                clock_ms=lambda:next_at+1)
            progressed = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                clock_ms=lambda:next_at+1)
        assert stale_callback.disposition is MaterializationDisposition.BLOCKED
        assert progressed.disposition is MaterializationDisposition.TARGET_WARMING
        async with PostgresKernelUnitOfWork(database) as uow:
            not_failed = await uow.instrument_selection.get_generic_materialization_generation(handoff.materialization_generation_id)
        assert not_failed is not None and not_failed.lifecycle_state.value == "MATERIALIZING"
        async with PostgresKernelUnitOfWork(database) as uow:
            targets = await uow.strategy_universes.get_generation_universe_targets(handoff.materialization_generation_id)
        assert len(targets) == 1 and targets[0].lifecycle_state.value == "warming"
        target_uid = targets[0].universe_version_id
        await make_warming_ready(database,universe_version_id=target_uid,
            warm_closed_bar_time_ms=next_at//HOUR*HOUR,valid_until_ms=next_at+HOUR)
        template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        delta = next_at//HOUR*HOUR-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta})
            for c in template.candles_1h)
        target_projection = build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,
            universe_version_id=target_uid,strategy_group_id=group,
            exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=next_at//HOUR*HOUR,
            lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles)
                for member in first_source.spec.candidate_ids))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(target_projection)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=next_at+2)):
            staged = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                clock_ms=lambda:next_at+2)
        assert staged.disposition is MaterializationDisposition.GENERATION_STAGED
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=next_at+3)):
            async with PostgresKernelUnitOfWork(database) as uow:
                recovery_proof = await uow.instrument_selection.prepare_generic_recovered_activation_proof(
                    handoff.materialization_generation_id)
        assert recovery_proof.authority_outcome == "ACTIVE_NEW"
        assert recovery_proof.target_snapshot_id == next_snapshot.selection_snapshot_id
        assert recovery_proof.source_selection_authority_id == previous_authority.authority.selection_authority_id
        assert recovery_proof.event_binding.universe_version_id == target_uid
        assert recovery_proof.recovery_close_plan.period.scheduled_effective_at_ms == (
            next_snapshot.effective_from_ms+HOUR)
        assert recovery_proof.first_eligible_close_time_ms > recovery_proof.committed_at_ms
        assert recovery_proof.membership_freshness is not None
        assert recovery_proof.membership_freshness.membership_valid_until_ms == (
            next_snapshot.effective_from_ms+2*HOUR)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=next_at+3)):
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.instrument_selection.require_generic_recovered_activation_proof(recovery_proof) == next_at+3
                with pytest.raises(SelectionJobConflict,match="proof changed"):
                    await uow.instrument_selection.require_generic_recovered_activation_proof(
                        recovery_proof.model_copy(update={"source_selection_authority_id":"authority:forged"}))
        from src.trading_kernel.domain.selection_authority import (
            GenericRecoveryAuthority,
        )
        from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
            generic_recovery_authority_storage_values,
        )
        proposed_new_authority = GenericRecoveryAuthority.build(proof=recovery_proof,authority_sequence=1)
        async with database.connect() as conn:
            proof_check = sa.text("SELECT brc_generic_recovered_activation_proof_matches(CAST(:proof AS jsonb),:checked_at)")
            assert await conn.scalar(proof_check,{"proof":recovery_proof.model_dump_json(),"checked_at":next_at+3}) is True
            assert await conn.scalar(proof_check,{"proof":recovery_proof.model_dump_json(),
                "checked_at":recovery_proof.first_eligible_close_time_ms}) is False
            for changes in ({"source_selection_authority_id":"authority:forged"},
                {"target_snapshot_id":"selection:forged"},{"owner_control_version":999},
                {"observation_cursors":()}):
                forged = recovery_proof.model_copy(update=changes)
                assert await conn.scalar(proof_check,{"proof":forged.model_dump_json(),"checked_at":next_at+3}) is False
        with pytest.raises(sa.exc.DBAPIError,match="requires exact homogeneous Spec Event binding shape|Recovered activation requires atomic"):
            async with database.begin() as conn:
                await conn.execute(sa.insert(selection_session_authorities).values(
                    **generic_recovery_authority_storage_values(proposed_new_authority)))
        async with database.connect() as conn:
            before = await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities"))
            await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' "
                "WHERE strategy_group_id=:group"),{"group":group})
            assert await conn.scalar(proof_check,{"proof":recovery_proof.model_dump_json(),"checked_at":next_at+3}) is False
            with (patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=next_at+3)),pytest.raises(SelectionJobConflict)):
                await PostgresInstrumentSelectionRepository(conn).prepare_generic_recovered_activation_proof(
                    handoff.materialization_generation_id)
            await conn.rollback()
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == before
        async with PostgresKernelUnitOfWork(database) as uow:
            still_previous = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        assert still_previous is not None
        assert still_previous.authority.selection_authority_id == previous_authority.authority.selection_authority_id
        if resolution in {"activate","activate_refusal","activate_change_guard","activate_change_after_arm"}:
            if resolution in {"activate","activate_refusal"}:
                @asynccontextmanager
                async def interrupted_recovered_activation():
                    async with PostgresKernelUnitOfWork(database) as interrupted_uow:
                        yield interrupted_uow
                        inside = await interrupted_uow.instrument_selection.get_current_generic_authority(
                            first_source.spec.selection_spec_id)
                        assert inside is not None and inside.authority.authority_outcome=="ACTIVE_NEW"
                        raise RuntimeError("recovered activation interrupted before commit")
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                    new=AsyncMock(return_value=next_at+4)),pytest.raises(RuntimeError,
                        match="recovered activation interrupted before commit"):
                    await coordinate_selection_materialization_once(
                        uow_factory=interrupted_recovered_activation,
                        request=CoordinateGenericGenerationRequest(
                            materialization_generation_id=handoff.materialization_generation_id,
                            worker_id="recover-interrupted"),clock_ms=lambda:next_at+4)
                async with PostgresKernelUnitOfWork(database) as uow:
                    prior_after_fault = await uow.instrument_selection.get_current_generic_authority(
                        first_source.spec.selection_spec_id)
                    target_after_fault = await uow.strategy_universes.get_generation_universe_targets(
                        handoff.materialization_generation_id)
                    vacuum_after_fault = await uow.instrument_selection.get_current_entry_vacuum(
                        strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
                assert prior_after_fault is not None
                assert prior_after_fault.authority.selection_authority_id==previous_authority.authority.selection_authority_id
                assert len(target_after_fault)==1 and target_after_fault[0].lifecycle_state.value=="staged"
                assert vacuum_after_fault is not None and vacuum_after_fault.state.value=="RECONFIGURING"
                async with database.connect() as conn:
                    assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current "
                        "WHERE authority_recovery_id=:id"),{
                            "id":recovery_proof.recovery_close_plan.recovery_id})==0
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=next_at+4)):
                activated = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                    clock_ms=lambda:next_at+4)
            assert activated.disposition is MaterializationDisposition.ACTIVE_NEW, activated
            async with PostgresKernelUnitOfWork(database) as uow:
                current_recovery = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
                current_universe = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
                resolved_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
            assert current_recovery is not None and current_recovery.authority.authority_outcome == "ACTIVE_NEW"
            assert current_recovery.authority.selection_authority_id == activated.selection_authority_id
            assert current_recovery.authority.recovery_proof == recovery_proof.model_copy(update={
                "committed_at_ms":next_at+4,
                "recovery_close_plan":recovery_proof.recovery_close_plan.model_copy(update={"evaluated_at_ms":next_at+4})})
            assert current_recovery.authority.first_eligible_close_time_ms > next_at+4
            assert current_universe is not None and current_universe.universe_version_id == target_uid
            assert resolved_vacuum is None
            async with database.connect() as conn:
                checkpoint_count = await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current "
                    "WHERE authority_recovery_id=:id"),{"id":current_recovery.authority.recovery_proof.recovery_close_plan.recovery_id})
            assert checkpoint_count == len(next_snapshot.selected_members)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=next_at+5)):
                repeated_activation = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                    clock_ms=lambda:next_at+5)
            assert repeated_activation.disposition is MaterializationDisposition.ACTIVE_NEW
            assert repeated_activation.selection_authority_id == activated.selection_authority_id
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities "
                    "WHERE materialization_generation_id=:gid"),{"gid":handoff.materialization_generation_id}) == 1
                active_scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
                    "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":target_uid})
            first_close = current_recovery.authority.first_eligible_close_time_ms
            await make_warming_ready(database,universe_version_id=target_uid,
                warm_closed_bar_time_ms=first_close,valid_until_ms=first_close+HOUR)
            template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
            shift = first_close-template.trigger_candle_close_time_ms
            class RecoveredTargetMarket:
                async def fetch_closed_candles(self, request):
                    candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                    return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                        "close_time_ms":c.close_time_ms+shift}) for c in candles)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=first_close+1)):
                first_observation = await observe_strategy_scope(
                    lambda:PostgresKernelUnitOfWork(database),RecoveredTargetMarket(),
                    ObservationRequest(runtime_scope_id=active_scope_id,runtime_commit="a"*40,
                        schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=first_close,
                        attempted_at_ms=first_close+1))
            assert first_observation.status is ObservationStatus.NO_SIGNAL
            assert first_observation.detector_reason == "RECOVERY_REBASE_REQUIRED"
            async with PostgresKernelUnitOfWork(database) as uow:
                checkpoint = await uow.signals.get_authority_recovery_checkpoint(
                    current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key)
            assert checkpoint is not None and checkpoint.armed_at_close_time_ms is None
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
            intermediate_source = next_input(next_source).model_copy(update={
                "predecessor_snapshot":next_snapshot})
            intermediate_snapshot = compute_generic_selection(intermediate_source)
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.save_generic_snapshot(intermediate_snapshot,
                    decision_at_ms=intermediate_source.decision_at_ms,
                    source_observed_at_ms=intermediate_source.source_observed_at_ms)
            following_source = next_input(intermediate_source).model_copy(update={
                "predecessor_snapshot":intermediate_snapshot})
            assert following_source.feature_cutoff_at_ms == first_close
            following_source = following_source.model_copy(update={
                "member_windows":tuple(qualify_window(
                    window.model_copy(update={"candles":following_source.member_windows[0].candles}),
                    window.exchange_instrument_id in next_snapshot.selected_members)
                    for window in following_source.member_windows)})
            following_snapshot = compute_generic_selection(following_source)
            assert following_snapshot.selected_members == next_snapshot.selected_members
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.save_generic_snapshot(following_snapshot,
                    decision_at_ms=following_source.decision_at_ms,
                    source_observed_at_ms=following_source.source_observed_at_ms)
            following_at = following_snapshot.effective_from_ms+1
            await make_warming_ready(database,universe_version_id=target_uid,
                warm_closed_bar_time_ms=following_at//HOUR*HOUR,valid_until_ms=following_at+HOUR)
            template = (mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()) if (
                resolution=="activate_change_after_arm") else (mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot())
            shift = following_at//HOUR*HOUR-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
            comparison_projection = build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,
                universe_version_id=target_uid,strategy_group_id=group,
                exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=following_at//HOUR*HOUR,
                lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles)
                    for member in first_source.spec.candidate_ids)).model_copy(update={
                        "comparison_transition_revision":current_recovery.authority.comparison_transition_revision})
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(comparison_projection)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=following_at)):
                continuation = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),
                    request=CoordinateGenericSnapshotRequest(selection_snapshot_id=following_snapshot.selection_snapshot_id,
                        worker_id="post-recovery-no-change"),clock_ms=lambda:following_at)
            assert continuation.disposition is MaterializationDisposition.NO_CHANGE, continuation
            async with PostgresKernelUnitOfWork(database) as uow:
                successor = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
                still_pending = await uow.signals.get_authority_recovery_checkpoint(
                    current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key)
            assert successor is not None
            assert successor.authority.selection_authority_id == continuation.selection_authority_id
            assert successor.authority.continued_from_recovery_authority_id == current_recovery.authority.selection_authority_id
            assert still_pending is not None and still_pending.armed_at_close_time_ms is None
            if resolution in {"activate_change_guard","activate_change_after_arm"}:
                if resolution=="activate_change_after_arm":
                    class ArmingMarket:
                        async def fetch_closed_candles(self, request):
                            path = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                                "close_time_ms":c.close_time_ms+shift}) for c in path)
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=following_at+1)):
                        arming = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),ArmingMarket(),
                            ObservationRequest(runtime_scope_id=active_scope_id,runtime_commit="a"*40,
                                schema_revision=CURRENT_SCHEMA_REVISION,
                                trigger_candle_close_time_ms=following_at//HOUR*HOUR,
                                attempted_at_ms=following_at+1))
                    assert arming.status is ObservationStatus.NO_SIGNAL
                    async with PostgresKernelUnitOfWork(database) as uow:
                        checkpoint = await uow.signals.get_authority_recovery_checkpoint(
                            current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key)
                    assert checkpoint is not None and checkpoint.state=="ARMED"
                changed_source = next_input(following_source).model_copy(update={
                    "predecessor_snapshot":following_snapshot})
                retained = set(next_snapshot.selected_members)
                extra = next(member for member in first_source.spec.candidate_ids if member not in retained)
                changed_source = changed_source.model_copy(update={
                    "member_windows":tuple(qualify_window(
                        window.model_copy(update={"candles":changed_source.member_windows[0].candles}),
                        window.exchange_instrument_id in retained or window.exchange_instrument_id==extra)
                        for window in changed_source.member_windows)})
                changed_snapshot = compute_generic_selection(changed_source)
                assert set(next_snapshot.selected_members).issubset(changed_snapshot.selected_members)
                assert changed_snapshot.selected_members!=next_snapshot.selected_members
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.instrument_selection.save_generic_snapshot(changed_snapshot,
                        decision_at_ms=changed_source.decision_at_ms,
                        source_observed_at_ms=changed_source.source_observed_at_ms)
                changed_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=changed_snapshot.selection_snapshot_id,
                    worker_id="recovery-membership-change")
                changed_at = changed_snapshot.effective_from_ms+1
                handoff_steps = []
                for offset in range(6):
                    at = changed_at+offset
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=at)):
                        stage = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=changed_request,
                            clock_ms=lambda at=at:at)
                    handoff_steps.append(stage)
                    if stage.disposition is MaterializationDisposition.GENERATION_MATERIALIZING:
                        break
                assert handoff_steps[-1].disposition is MaterializationDisposition.GENERATION_MATERIALIZING, handoff_steps
                generation_id = handoff_steps[-1].materialization_generation_id
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                    new=AsyncMock(return_value=changed_at+6)):
                    warming = await coordinate_selection_materialization_once(
                        uow_factory=lambda:PostgresKernelUnitOfWork(database),
                        request=CoordinateGenericGenerationRequest(materialization_generation_id=generation_id,
                            worker_id="recovery-membership-change"),clock_ms=lambda:changed_at+6)
                assert warming.disposition is MaterializationDisposition.TARGET_WARMING
                async with PostgresKernelUnitOfWork(database) as uow:
                    targets = await uow.strategy_universes.get_generation_universe_targets(generation_id)
                assert len(targets)==1
                next_uid = targets[0].universe_version_id
                await make_warming_ready(database,universe_version_id=next_uid,
                    warm_closed_bar_time_ms=changed_at//HOUR*HOUR,valid_until_ms=changed_at+HOUR)
                template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
                shift = changed_at//HOUR*HOUR-template.trigger_candle_close_time_ms
                path = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                    "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
                next_comparison = build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,
                    universe_version_id=next_uid,strategy_group_id=group,
                    exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=changed_at//HOUR*HOUR,
                    lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                    member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=path)
                        for member in first_source.spec.candidate_ids))
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.strategy_universes.save_comparative_projection(next_comparison)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                    new=AsyncMock(return_value=changed_at+7)):
                    staged_change = await coordinate_selection_materialization_once(
                        uow_factory=lambda:PostgresKernelUnitOfWork(database),request=changed_request,
                        clock_ms=lambda:changed_at+7)
                    refused_change = await coordinate_selection_materialization_once(
                        uow_factory=lambda:PostgresKernelUnitOfWork(database),request=changed_request,
                        clock_ms=lambda:changed_at+7)
                assert staged_change.disposition is MaterializationDisposition.GENERATION_STAGED
                if resolution=="activate_change_guard":
                    assert refused_change.disposition is MaterializationDisposition.BLOCKED
                    assert refused_change.reason_code == "GENERIC_RECOVERY_REBASE_PENDING"
                    async with PostgresKernelUnitOfWork(database) as uow:
                        pending_generation = await uow.instrument_selection.get_generic_materialization_generation(generation_id)
                    assert pending_generation is not None and pending_generation.fenced_at_ms is not None
                    timed_out_at = pending_generation.fenced_at_ms+first_source.spec.materialization_timeout_ms
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=timed_out_at)):
                        timed_out = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=changed_request,
                            clock_ms=lambda:timed_out_at)
                    assert timed_out.reason_code == "MATERIALIZATION_TIMEOUT"
                    replacement_source = next_input(changed_source).model_copy(update={
                        "predecessor_snapshot":changed_snapshot})
                    replacement_snapshot = compute_generic_selection(replacement_source)
                    assert replacement_snapshot.selected_members == changed_snapshot.selected_members
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.instrument_selection.save_generic_snapshot(replacement_snapshot,
                            decision_at_ms=replacement_source.decision_at_ms,
                            source_observed_at_ms=replacement_source.source_observed_at_ms)
                    replacement_request = CoordinateGenericSnapshotRequest(
                        selection_snapshot_id=replacement_snapshot.selection_snapshot_id,
                        worker_id="recover-changed-membership")
                    replacement_at = replacement_snapshot.effective_from_ms+1
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=replacement_at)):
                        retargeted = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=replacement_request,
                            clock_ms=lambda:replacement_at)
                    assert retargeted.disposition is MaterializationDisposition.GENERATION_MATERIALIZING
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=replacement_at+1)):
                        new_warming = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=replacement_request,
                            clock_ms=lambda:replacement_at+1)
                    assert new_warming.disposition is MaterializationDisposition.TARGET_WARMING
                    async with PostgresKernelUnitOfWork(database) as uow:
                        replacement_targets = await uow.strategy_universes.get_generation_universe_targets(
                            retargeted.materialization_generation_id)
                    assert len(replacement_targets)==1
                    replacement_uid = replacement_targets[0].universe_version_id
                    await make_warming_ready(database,universe_version_id=replacement_uid,
                        warm_closed_bar_time_ms=replacement_at//HOUR*HOUR,
                        valid_until_ms=replacement_at+HOUR)
                    template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
                    shift = replacement_at//HOUR*HOUR-template.trigger_candle_close_time_ms
                    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                        "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
                    replacement_projection = build_comparative_universe_projection(
                        event_spec_id=first_source.spec.event_spec_id,universe_version_id=replacement_uid,
                        strategy_group_id=group,exchange_instrument_ids=first_source.spec.candidate_ids,
                        closed_bar_time_ms=replacement_at//HOUR*HOUR,
                        lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles)
                            for member in first_source.spec.candidate_ids))
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.strategy_universes.save_comparative_projection(replacement_projection)
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                        new=AsyncMock(return_value=replacement_at+2)):
                        replacement_staged = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=replacement_request,
                            clock_ms=lambda:replacement_at+2)
                        replacement_active = await coordinate_selection_materialization_once(
                            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=replacement_request,
                            clock_ms=lambda:replacement_at+2)
                    assert replacement_staged.disposition is MaterializationDisposition.GENERATION_STAGED
                    assert replacement_active.disposition is MaterializationDisposition.ACTIVE_NEW, replacement_active
                    async with PostgresKernelUnitOfWork(database) as uow:
                        recovered_current = await uow.instrument_selection.get_current_generic_authority(
                            first_source.spec.selection_spec_id)
                        recovered_universe = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
                    assert recovered_current is not None and recovered_current.authority.authority_outcome=="ACTIVE_NEW"
                    assert recovered_current.authority.recovery_proof.first_eligible_close_time_ms>replacement_at+2
                    assert recovered_universe is not None and recovered_universe.universe_version_id==replacement_uid
                else:
                    assert refused_change.disposition is MaterializationDisposition.ACTIVE_NEW, refused_change
                return
            forged_successor = successor.authority.model_copy(update={
                "selection_authority_id":"authority:forged-successor",
                "authority_sequence":successor.authority.authority_sequence+1})
            async with database.connect() as conn:
                await conn.execute(sa.text("UPDATE brc_exposure_episode_current "
                    "SET authority_recovery_revision=authority_recovery_revision+1 "
                    "WHERE episode_domain_key=:key"),
                    {"key":current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key})
                with pytest.raises(sa.exc.DBAPIError,match="successor checkpoint changed"):
                    async with conn.begin_nested():
                        await conn.execute(sa.insert(selection_session_authorities).values(
                            **generic_authority_storage_values(forged_successor)))
                await conn.rollback()
            async with PostgresKernelUnitOfWork(database) as gate_uow:
                active_scope = await gate_uow.signals.get_runtime_scope(active_scope_id)
                assert active_scope is not None and gate_uow._connection is not None
                checkpoint_fault = await gate_uow._connection.begin_nested()
                await gate_uow._connection.execute(sa.text(
                    "UPDATE brc_exposure_episode_current SET authority_recovery_revision=authority_recovery_revision+1 "
                    "WHERE episode_domain_key=:key"),
                    {"key":current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key})
                drift = await resolve_selection_entry_authority(gate_uow,runtime_scope=active_scope,
                    birth_selection_authority_id=successor.authority.selection_authority_id,
                    observed_close_time_ms=following_at//HOUR*HOUR,now_ms=following_at+1,
                    allow_current_as_birth=False,lock_current=True)
                assert not drift.allowed and drift.reason_code == "RECOVERY_REBASE_AUTHORITY_CHANGED"
                await checkpoint_fault.rollback()
                unarmed = await resolve_selection_entry_authority(gate_uow,runtime_scope=active_scope,
                    birth_selection_authority_id=successor.authority.selection_authority_id,
                    observed_close_time_ms=following_at//HOUR*HOUR,now_ms=following_at+1,
                    allow_current_as_birth=False,lock_current=True)
                assert not unarmed.allowed and unarmed.reason_code == "RECOVERY_REBASE_REQUIRED"
            class ContinuedRecoveryMarket:
                async def fetch_closed_candles(self, request):
                    path = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                    return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                        "close_time_ms":c.close_time_ms+shift}) for c in path)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=following_at+1)):
                second_trigger = await observe_strategy_scope(
                    lambda:PostgresKernelUnitOfWork(database),ContinuedRecoveryMarket(),
                    ObservationRequest(runtime_scope_id=active_scope_id,runtime_commit="a"*40,
                        schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=following_at//HOUR*HOUR,
                        attempted_at_ms=following_at+1))
            assert second_trigger.status is ObservationStatus.NO_SIGNAL
            assert second_trigger.detector_reason == "RECOVERY_REBASE_REQUIRED"
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
            period_source = following_source
            period_snapshot = following_snapshot
            for expected, market_template in (
                (ObservationStatus.NO_SIGNAL,mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()),
                (ObservationStatus.SIGNAL_CREATED,mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()),
            ):
                candidate_source = next_input(period_source).model_copy(update={
                    "predecessor_snapshot":period_snapshot})
                candidate_source = candidate_source.model_copy(update={
                    "member_windows":tuple(qualify_window(
                        window.model_copy(update={"candles":candidate_source.member_windows[0].candles}),
                        window.exchange_instrument_id in next_snapshot.selected_members)
                        for window in candidate_source.member_windows)})
                candidate_snapshot = compute_generic_selection(candidate_source)
                assert candidate_snapshot.selected_members == next_snapshot.selected_members
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.instrument_selection.save_generic_snapshot(candidate_snapshot,
                        decision_at_ms=candidate_source.decision_at_ms,
                        source_observed_at_ms=candidate_source.source_observed_at_ms)
                close = candidate_snapshot.effective_from_ms
                await make_warming_ready(database,universe_version_id=target_uid,
                    warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
                market_shift = close-market_template.trigger_candle_close_time_ms
                market_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+market_shift,
                    "close_time_ms":c.close_time_ms+market_shift}) for c in market_template.candles_1h)
                projection = build_comparative_universe_projection(event_spec_id=first_source.spec.event_spec_id,
                    universe_version_id=target_uid,strategy_group_id=group,
                    exchange_instrument_ids=first_source.spec.candidate_ids,closed_bar_time_ms=close,
                    lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                    member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=market_candles)
                        for member in first_source.spec.candidate_ids)).model_copy(update={
                            "comparison_transition_revision":current_recovery.authority.comparison_transition_revision})
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.strategy_universes.save_comparative_projection(projection)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                    new=AsyncMock(return_value=close+1)):
                    renewed = await coordinate_selection_materialization_once(
                        uow_factory=lambda:PostgresKernelUnitOfWork(database),
                        request=CoordinateGenericSnapshotRequest(selection_snapshot_id=candidate_snapshot.selection_snapshot_id,
                            worker_id="recovery-successor-period"),clock_ms=lambda close=close:close+1)
                assert renewed.disposition is MaterializationDisposition.NO_CHANGE
                class ContinuedMarket:
                    def __init__(self, template, shift):
                        self.template = template
                        self.shift = shift

                    async def fetch_closed_candles(self, request):
                        path = self.template.candles_1h if request.timeframe=="1h" else self.template.candles_4h
                        return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.shift,
                            "close_time_ms":c.close_time_ms+self.shift}) for c in path)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                    new=AsyncMock(return_value=close+2)):
                    result = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
                        ContinuedMarket(market_template,market_shift),
                        ObservationRequest(runtime_scope_id=active_scope_id,runtime_commit="a"*40,
                            schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=close,
                            attempted_at_ms=close+2))
                assert result.status is expected, result
                period_source,period_snapshot = candidate_source,candidate_snapshot
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 1
            from src.trading_kernel.application.issue_ready_signal import (
                IssueReadySignalRequest,
                issue_ready_signal,
            )
            from src.trading_kernel.domain.cross_margin_stress import (
                AccountRiskSnapshot,
                MaintenanceMarginBracket,
            )
            from src.trading_kernel.domain.entry_admission_snapshot import (
                EntryAdmissionSnapshot,
            )
            assert result.signal_event_id is not None
            issued_at = close+3
            admission = EntryAdmissionSnapshot(account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id="binance-usdm",account_id="generic-snapshot",account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",position_mode="independent_sides",margin_mode="cross",
                exchange_instrument_id=active_scope.exchange_instrument_id,mark_price=Decimal(105),configured_leverage=5,
                total_wallet_balance=Decimal(1000),total_margin_balance=Decimal(1000),total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),available_margin=Decimal(1000),account_positions=(),
                observed_at_ms=issued_at,valid_until_ms=issued_at+60_000),
                best_bid_price=Decimal("104.99"),best_ask_price=Decimal(105),open_orders=(),
                observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
            brackets = (MaintenanceMarginBracket(bracket_id="recovery-successor:1",
                notional_floor=Decimal(0),notional_cap=Decimal(20_000),
                maintenance_margin_rate=Decimal("0.005"),maintenance_amount=Decimal(0)),)
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.signals.upsert_instrument_rules(venue_id="binance-usdm",
                    exchange_instrument_id=active_scope.exchange_instrument_id,
                    quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
                    min_notional=Decimal(5),exchange_max_leverage=5,maintenance_margin_brackets=brackets,
                    maintenance_margin_brackets_digest=canonical_digest(brackets),
                    notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                    observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
                issue_request = IssueReadySignalRequest(signal_event_id=result.signal_event_id,
                    admission_snapshot=admission,claim_owner="recovery-successor-entry",
                    runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,now_ms=issued_at)
                assert uow._connection is not None
                checkpoint_fault = await uow._connection.begin_nested()
                await uow._connection.execute(sa.text("UPDATE brc_exposure_episode_current "
                    "SET authority_recovery_revision=authority_recovery_revision+1 "
                    "WHERE episode_domain_key=:key"),
                    {"key":current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key})
                rejected = await issue_ready_signal(uow,issue_request)
                assert rejected.status.value == "selection_authority_invalid"
                assert await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
                assert await uow._connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
                await checkpoint_fault.rollback()
                issued = await issue_ready_signal(uow,issue_request)
            assert issued.status.value == "issued", issued
            async with PostgresKernelUnitOfWork(database) as uow:
                ticket = await uow.tickets.get(issued.ticket_id)
                claim = await uow.capacity_claims.get_for_signal(result.signal_event_id)
            assert ticket is not None and claim is not None
            assert ticket.selection_authority_id == renewed.selection_authority_id
            assert claim.selection_authority_id == ticket.selection_authority_id
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands "
                    "WHERE ticket_id=:ticket AND command_kind='entry'"),{"ticket":issued.ticket_id}) == 1
            from src.trading_kernel.application.dispatch_exchange_command import (
                DispatchCommandRequest,
                dispatch_one_command,
            )
            from src.trading_kernel.application.runtime_facts import (
                InstrumentRulesFacts,
            )
            from src.trading_kernel.domain.commands import (
                ExchangeCommandResult,
                ExchangeCommandStatus,
            )
            class SuccessorEntryFacts:
                async def read_entry_admission_snapshot(self, request):
                    fresh_risk = AccountRiskSnapshot.create(**{
                        **admission.account_risk_snapshot.model_dump(exclude={"snapshot_digest"}),
                        "observed_at_ms":request.observed_at_ms,
                        "valid_until_ms":request.observed_at_ms+request.valid_for_ms})
                    return admission.model_copy(update={"account_risk_snapshot":fresh_risk,
                        "observed_at_ms":request.observed_at_ms,
                        "valid_until_ms":request.observed_at_ms+request.valid_for_ms})

                async def read_instrument_rules(self, request):
                    return InstrumentRulesFacts(exchange_instrument_id=request.exchange_instrument_id,
                        quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
                        min_notional=Decimal(5),exchange_max_leverage=5,maintenance_margin_brackets=brackets,
                        maintenance_margin_brackets_digest=canonical_digest(brackets),
                        notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                        observed_at_ms=request.observed_at_ms,
                        valid_until_ms=request.observed_at_ms+request.valid_for_ms)
            class SuccessorVenue:
                def __init__(self):
                    self.calls = []
                    self.now_ms = issued_at+5

                async def execute(self, request):
                    async with PostgresKernelUnitOfWork(database) as durable_uow:
                        durable = await durable_uow.exchange_commands.get(request.command_id)
                        assert durable.status is ExchangeCommandStatus.CLAIMED
                    self.calls.append(request)
                    return ExchangeCommandResult(status=ExchangeCommandStatus.ACCEPTED,
                        observed_at_ms=self.now_ms+1,exchange_order_id=f"successor-{len(self.calls)}")
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_runtime_capabilities_current SET enabled=true "
                    "WHERE capability_key='exchange_commands'"))
            venue = SuccessorVenue()
            dispatch_request = DispatchCommandRequest(worker_id="recovery-successor-dispatch",
                ticket_id=issued.ticket_id,now_ms=issued_at+5,lease_until_ms=issued_at+30_000,
                timeout_seconds=1,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                admission_snapshot_validity_ms=60_000)
            if resolution == "activate_refusal":
                async with database.begin() as conn:
                    await conn.execute(sa.text("UPDATE brc_exposure_episode_current "
                        "SET authority_recovery_revision=authority_recovery_revision+1 "
                        "WHERE episode_domain_key=:key"),
                        {"key":current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key})
            dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                dispatch_request,entry_facts_source=SuccessorEntryFacts())
            if resolution == "activate_refusal":
                assert dispatched.status.value == "superseded", dispatched
                assert venue.calls == []
                async with database.connect() as conn:
                    assert await conn.scalar(sa.text("SELECT status FROM brc_exchange_commands "
                        "WHERE ticket_id=:ticket AND command_kind='entry'"),{"ticket":issued.ticket_id}) == "rejected"
                return
            assert dispatched.status.value == "accepted", dispatched
            assert len(venue.calls) == 1
            repeated_dispatch = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                dispatch_request.model_copy(update={"now_ms":issued_at+7}),entry_facts_source=SuccessorEntryFacts())
            assert repeated_dispatch.status.value == "no_command"
            assert len(venue.calls) == 1
            next_anchor = period_snapshot.feature_cutoff_at_ms+first_source.spec.cadence_hours*HOUR
            continuity_close = next_anchor+HOUR
            await make_warming_ready(database,universe_version_id=target_uid,
                warm_closed_bar_time_ms=continuity_close,valid_until_ms=continuity_close+HOUR)
            template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
            shift = continuity_close-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                "close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
            async with PostgresKernelUnitOfWork(database) as uow:
                before_continuity = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
            assert before_continuity is not None
            compare_at_boundary = build_comparative_universe_projection(
                event_spec_id=first_source.spec.event_spec_id,universe_version_id=target_uid,
                strategy_group_id=group,exchange_instrument_ids=first_source.spec.candidate_ids,
                closed_bar_time_ms=continuity_close,lookback_bars=8 if group=="MPG-001" else 12,
                freshness_window_ms=HOUR,member_windows=tuple(ComparativeMemberWindow(
                    exchange_instrument_id=member,candles_1h=candles) for member in first_source.spec.candidate_ids))
            compare_at_boundary = compare_at_boundary.model_copy(update={
                "comparison_transition_revision":before_continuity.authority.comparison_transition_revision})
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(compare_at_boundary)
            at = continuity_close+1
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=at)):
                carried = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),
                    request=CoordinateGenericPeriodRequest(strategy_group_id=group,
                        selection_spec_id=first_source.spec.selection_spec_id,period_anchor_ms=next_anchor,
                        worker_id="recovery-origin-continuity"),clock_ms=lambda:at)
            assert carried.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, carried
            async with PostgresKernelUnitOfWork(database) as uow:
                continuation = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
                scope = await uow.signals.get_runtime_scope(active_scope_id)
                frozen_ticket = await uow.tickets.get(issued.ticket_id)
            assert continuation is not None and scope is not None and frozen_ticket is not None
            assert continuation.authority.current_close_proof.origin_recovery_authority_id==current_recovery.authority.selection_authority_id
            assert continuation.authority.membership_freshness.source_snapshot_id==period_snapshot.selection_snapshot_id
            assert continuation.authority.membership_freshness.state.value=="GRACE"
            assert frozen_ticket.selection_authority_id==renewed.selection_authority_id
            async with PostgresKernelUnitOfWork(database) as uow:
                observation_permission = await resolve_selection_observation_authority(uow,runtime_scope=scope,
                    birth_selection_authority_id=None,observed_close_time_ms=continuity_close,
                    now_ms=at,allow_current_as_birth=True,lock_current=True)
            assert observation_permission.allowed
            assert observation_permission.reason_code=="generic_recovery_observation"
            class RecoveryOriginMarket:
                async def fetch_closed_candles(self, request):
                    path = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                    return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,
                        "close_time_ms":c.close_time_ms+shift}) for c in path)
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=at+2)):
                preserved = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),RecoveryOriginMarket(),
                    ObservationRequest(runtime_scope_id=active_scope_id,runtime_commit="a"*40,
                        schema_revision=CURRENT_SCHEMA_REVISION,trigger_candle_close_time_ms=continuity_close,
                        attempted_at_ms=at+2))
            assert preserved.status is ObservationStatus.NO_SIGNAL, preserved
            async with PostgresKernelUnitOfWork(database) as uow:
                checkpoint = await uow.signals.get_authority_recovery_checkpoint(
                    current_recovery.authority.recovery_proof.observation_cursors[0].episode_domain_key)
            assert checkpoint is not None and checkpoint.recovery_id==current_recovery.authority.recovery_proof.recovery_close_plan.recovery_id
            from src.trading_kernel.application.maintain_ticket_lifecycle import (
                LifecycleMaintenanceRequest,
                TicketLifecycleFacts,
                maintain_ticket_lifecycle,
            )
            from src.trading_kernel.application.reconcile_ticket import (
                ReconcileTicketRequest,
                reconcile_ticket,
            )
            from src.trading_kernel.application.settle_ticket import (
                RecordTradeReviewRequest,
                SettleTicketRequest,
                record_trade_review,
                settle_ticket,
            )
            from src.trading_kernel.domain.aggregate import AggregateStatus
            from src.trading_kernel.domain.events import PostFillStressAssessed
            from src.trading_kernel.domain.position import PositionSnapshot
            from src.trading_kernel.domain.reducer import reduce_event
            from tests.trading_kernel.support.capacity_claims import (
                make_stress_evidence,
            )
            lifecycle_at = continuity_close+100
            async with PostgresKernelUnitOfWork(database) as uow:
                filled = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
                    snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                        quantity=ticket.quantity,average_entry_price=ticket.entry_reference_price,
                        venue_reported_liquidation_price=Decimal(0),open_orders=(),
                        observed_at_ms=lifecycle_at)))
            assert filled.status.value=="entry_fill_recorded"
            async def dispatch_safety(offset):
                now = lifecycle_at+offset
                async with PostgresKernelUnitOfWork(database) as uow:
                    aggregate = await uow.aggregates.get(issued.ticket_id)
                    if aggregate is not None and aggregate.status is AggregateStatus.POST_FILL_RISK_PENDING:
                        stress = PostFillStressAssessed(event_id=f"event:{issued.ticket_id}:{aggregate.last_event_sequence+1}",
                            ticket_id=issued.ticket_id,sequence=aggregate.last_event_sequence+1,
                            occurred_at_ms=now-1,status="passed",evidence=make_stress_evidence(aggregate.ticket),
                            owner_policy_id=aggregate.ticket.owner_policy_id,
                            owner_policy_version=aggregate.ticket.owner_policy_version,
                            filled_qty=aggregate.position_qty,average_fill_price=aggregate.average_fill_price,
                            initial_stop_price=aggregate.ticket.initial_stop_price,
                            initial_stop_exchange_order_id=aggregate.initial_stop_exchange_order_id)
                        await uow.commit_reduction(event=stress,reduction=reduce_event(aggregate,stress),
                            expected_version=aggregate.version)
                venue.now_ms = now
                dispatched_safety = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                    DispatchCommandRequest(worker_id="successor-lifecycle",ticket_id=issued.ticket_id,
                        now_ms=now,lease_until_ms=now+30_000,timeout_seconds=1))
                assert dispatched_safety.status.value=="accepted", dispatched_safety
            await dispatch_safety(100)
            await dispatch_safety(200)
            async with PostgresKernelUnitOfWork(database) as uow:
                protected = await uow.aggregates.get(issued.ticket_id)
            assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
            async with PostgresKernelUnitOfWork(database) as uow:
                runner = await maintain_ticket_lifecycle(uow,LifecycleMaintenanceRequest(
                    ticket_id=issued.ticket_id,
                    facts=TicketLifecycleFacts(position_quantity=ticket.quantity-ticket.take_profit_quantities[0],
                        tp1_filled_quantity=ticket.take_profit_quantities[0],
                        tp1_average_fill_price=ticket.take_profit_prices[0],
                        allocated_entry_fee_quote=Decimal("0.01"),exit_taker_fee_rate=Decimal("0.001"),
                        price_tick=Decimal("0.01"),market_facts=None,observed_at_ms=lifecycle_at+300),
                    now_ms=lifecycle_at+300))
            assert runner.status.value=="break_even_requested"
            await dispatch_safety(400)
            await dispatch_safety(500)
            async with PostgresKernelUnitOfWork(database) as uow:
                external_flat = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
                    snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                        quantity=Decimal(0),average_entry_price=None,open_orders=(),
                        observed_at_ms=lifecycle_at+600)))
            assert external_flat.status.value=="external_flat_incident"
            await dispatch_safety(700)
            async with PostgresKernelUnitOfWork(database) as uow:
                matched = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
                    snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                        quantity=Decimal(0),average_entry_price=None,open_orders=(),
                        observed_at_ms=lifecycle_at+800)))
                settled = await settle_ticket(uow,SettleTicketRequest(ticket_id=issued.ticket_id,
                    settled_at_ms=lifecycle_at+900))
                reviewed = await record_trade_review(uow,RecordTradeReviewRequest(
                    ticket_id=issued.ticket_id,review_id=f"review:recovery-successor-{group}",
                    outcome="closed",metrics={"realized_pnl":"1.25"},
                    decision_impact={"strategy_action":"keep"},recorded_at_ms=lifecycle_at+1000))
                terminal = await uow.aggregates.get(issued.ticket_id)
                frozen_ticket = await uow.tickets.get(issued.ticket_id)
                reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
                incident = await uow.incidents.get_open_for_ticket(issued.ticket_id)
                active_domain = await uow.entry_admission.has_active_ticket_in_domain(
                    ticket.identity.netting_domain.key())
                commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
            assert matched.status.value=="matched"
            assert settled.status.value=="budget_settled"
            assert reviewed.status.value=="review_recorded"
            assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
            assert frozen_ticket is not None and frozen_ticket.selection_authority_id==renewed.selection_authority_id
            assert reservation is not None and reservation.status=="released"
            assert incident is None and not active_domain
            assert len(commands)==len(venue.calls)
            return
        second_failure_at = next_at+first_source.spec.materialization_timeout_ms
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
            new=AsyncMock(return_value=second_failure_at)):
            failed_again = await coordinate_selection_materialization_once(
                uow_factory=lambda:PostgresKernelUnitOfWork(database),request=next_request,
                clock_ms=lambda:second_failure_at)
        assert failed_again.reason_code == "MATERIALIZATION_TIMEOUT"
        empty_input = next_input(next_source)
        empty_input = empty_input.model_copy(update={
            "predecessor_snapshot":next_snapshot,
            "member_windows":tuple(qualify_window(window,False) for window in empty_input.member_windows),
        })
        empty_snapshot = compute_generic_selection(empty_input)
        assert not empty_snapshot.selected_members
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(empty_snapshot,
                decision_at_ms=empty_input.decision_at_ms,
                source_observed_at_ms=empty_input.source_observed_at_ms)
        empty_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty_snapshot.selection_snapshot_id,
            worker_id="valid-empty-after-failed-retarget")
        empty_at = empty_snapshot.effective_from_ms+1
        outcomes = []
        for offset in range(3):
            at = empty_at+offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=at)):
                outcome = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,
                    clock_ms=lambda at=at:at)
            outcomes.append(outcome)
            if outcome.disposition is MaterializationDisposition.VALID_EMPTY:
                break
        assert outcomes[-1].disposition is MaterializationDisposition.VALID_EMPTY, outcomes
        async with PostgresKernelUnitOfWork(database) as uow:
            empty_authority = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
            no_open_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
        assert empty_authority is not None and empty_authority.authority.blocks_new_entry
        assert no_open_vacuum is None
        return
    assert proposal.selection_mode == "dynamic_selection"
    assert proposal.source_selection_authority_id == previous_authority.authority.selection_authority_id
    assert proposal.membership_freshness is not None
    assert proposal.membership_freshness.source_snapshot_id == first_snapshot.selection_snapshot_id
    assert proposal.membership_freshness.state.value == "GRACE"
    assert proposal.membership_freshness.membership_valid_until_ms == (
        previous_authority.authority.membership_freshness.membership_valid_until_ms)
    for statement,parameters in (
        (("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' "
            "WHERE strategy_group_id=:group_id"),{"group_id":group}),
        (("UPDATE brc_strategy_entry_vacuums_current SET state='DRAINING_ENTRY',drained_at_ms=NULL "
            "WHERE entry_vacuum_id=:vacuum_id"),{"vacuum_id":vacuum.entry_vacuum_id}),
    ):
        async with database.connect() as conn:
            await conn.execute(sa.text(statement),parameters)
            with (patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=fail_at+1)),pytest.raises(SelectionJobConflict)):
                await PostgresInstrumentSelectionRepository(conn).prepare_generic_recovery_grant_proof(generation_id)
            await conn.rollback()
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=fail_at+1)):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict,match="Generic recovery proof changed"):
                await uow.instrument_selection.require_generic_recovery_grant_proof(
                    proposal.model_copy(update={"source_selection_authority_id":"authority:wrong-source"}))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=fail_at+1)):
        recovered = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=generation_request,
            clock_ms=lambda:fail_at+1)
    assert recovered.disposition is MaterializationDisposition.FALLBACK_PREVIOUS, recovered
    async with PostgresKernelUnitOfWork(database) as uow:
        active = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        current_universe = await uow.strategy_universes.get_current(first_source.spec.event_spec_id)
        refreshed_control = await uow.instrument_selection.get_selection_control(group)
        open_vacuum = await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=first_source.spec.selection_spec_id)
    assert active is not None and active.authority.authority_outcome == "FALLBACK_PREVIOUS"
    assert active.authority.event_binding.universe_version_id == previous_uid
    assert active.authority.recovery_proof.source_selection_authority_id == previous_authority.authority.selection_authority_id
    assert active.authority.recovery_proof.membership_freshness.source_snapshot_id == first_snapshot.selection_snapshot_id
    assert current_universe is not None and current_universe.universe_version_id == previous_uid
    assert refreshed_control is not None and refreshed_control.selection_mode.value == "dynamic_selection"
    assert open_vacuum is None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=fail_at+1)):
        repeated = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),request=generation_request,
            clock_ms=lambda:fail_at+1)
    assert repeated.disposition is MaterializationDisposition.FALLBACK_PREVIOUS
    assert repeated.selection_authority_id == active.authority.selection_authority_id
    async with database.connect() as conn:
        checkpoint_count = await conn.scalar(sa.text("SELECT count(*) FROM brc_exposure_episode_current "
            "WHERE authority_recovery_id=:id AND authority_recovery_first_eligible_close_time_ms=:first"),
            {"id":active.authority.recovery_proof.recovery_close_plan.recovery_id,
             "first":active.authority.first_eligible_close_time_ms})
    assert checkpoint_count == len(proposal.observation_cursors)
    static_request_at = fail_at+2
    if resolution=="fallback_continued_static":
        fresh_source = next_input(next_input(first_source)).model_copy(update={"predecessor_snapshot":successor})
        fresh = compute_generic_selection(fresh_source)
        assert fresh.selected_members==first_snapshot.selected_members
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(fresh,
                decision_at_ms=fresh_source.decision_at_ms,source_observed_at_ms=fresh_source.source_observed_at_ms)
        renew_at = fresh.effective_from_ms+1
        await make_warming_ready(database,universe_version_id=previous_uid,
            warm_closed_bar_time_ms=fresh.effective_from_ms,valid_until_ms=renew_at+HOUR)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=renew_at)):
            renewed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=CoordinateGenericSnapshotRequest(selection_snapshot_id=fresh.selection_snapshot_id,worker_id="unarmed-origin-no-change"),clock_ms=lambda:renew_at)
        assert renewed.disposition is MaterializationDisposition.NO_CHANGE, renewed
        async with PostgresKernelUnitOfWork(database) as uow:
            continued = await uow.instrument_selection.get_current_generic_authority(first_source.spec.selection_spec_id)
        assert continued.authority.continued_from_recovery_authority_id==active.authority.selection_authority_id
        static_request_at = renew_at+1
    await _assert_static_normal_cannot_skip_unarmed_recovery(database,group=group,at_ms=static_request_at,
        arm_before_switch=resolution=="fallback_armed_static")


async def _assert_static_normal_cannot_skip_unarmed_recovery(database, *, group, at_ms,arm_before_switch=False):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )
    if arm_before_switch:
        async with PostgresKernelUnitOfWork(database) as uow:
            recovery = await uow.instrument_selection.get_current_generic_authority(inputs(group).spec.selection_spec_id)
            baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(
                (await uow.instrument_selection.get_selection_control(group)).rollback_baseline_id)
            member = (await uow.strategy_universes.get_members(baseline.source_event.universe_version_id))[0]
            assert uow._connection is not None
            scope_id = await uow._connection.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
                "WHERE universe_version_id=:uid AND exchange_instrument_id=:member"),
                {"uid":recovery.authority.event_binding.universe_version_id,"member":member})
        close = recovery.authority.first_eligible_close_time_ms
        await make_warming_ready(database,universe_version_id=recovery.authority.event_binding.universe_version_id,
            warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
        template = cpm_flat_snapshot()
        delta = close-template.trigger_candle_close_time_ms
        class ArmingMarket:
            async def fetch_closed_candles(self,request):
                candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+1)):
            armed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),ArmingMarket(),ObservationRequest(
                runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=close,attempted_at_ms=close+1))
        assert armed.status is ObservationStatus.NO_SIGNAL, armed
        at_ms = close+2
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        previous = await uow.instrument_selection.get_current_generic_authority(control.selection_spec_id)
        assert isinstance(previous.authority,GenericRecoveryAuthority) or previous.authority.continued_from_recovery_authority_id is not None
        spec = await uow.instrument_selection.get_generic_spec(control.selection_spec_id)
        baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(control.rollback_baseline_id)
        anchor = (at_ms//(spec.cadence_hours*HOUR)+1)*spec.cadence_hours*HOUR
        await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
            request=ControlMutationRequest(expected_version=control.control_version,reason="preserve_unarmed_recovery_on_static_switch",
                idempotency_key=f"static:unarmed:{group}",owner_identity="owner",now_ms=at_ms))
    due = anchor+HOUR+1
    assert previous.authority.expires_at_ms==anchor+HOUR
    request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="static-from-unarmed-recovery")
    for offset in range(8):
        tick = due+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            result = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda tick=tick:tick)
        if result.disposition is MaterializationDisposition.GENERATION_STAGED:
            break
        if result.materialization_generation_id is not None:
            async with PostgresKernelUnitOfWork(database) as uow:
                targets = await uow.strategy_universes.get_generation_universe_targets(result.materialization_generation_id)
            if targets:
                await make_warming_ready(database,universe_version_id=targets[0].universe_version_id,
                    warm_closed_bar_time_ms=anchor+HOUR,valid_until_ms=due+HOUR)
    assert result.disposition is MaterializationDisposition.GENERATION_STAGED, result
    gid = result.materialization_generation_id
    at = tick+1
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
        async with PostgresKernelUnitOfWork(database) as uow:
            generation = await uow.instrument_selection.claim_generic_static_materialization_generation(gid,
                worker_id=request.worker_id,now_ms=at,lease_duration_ms=30000)
            proof = await uow.instrument_selection.prepare_generic_static_activation_proof(gid,
                worker_id=request.worker_id,lease_epoch=generation.lease_epoch)
            assert proof.transition_rule==("NORMAL_TRANSITION" if arm_before_switch else "RECOVERY_TRANSITION")
            assert proof.recovery_reason==(None if arm_before_switch else "RECOVERY_PROVENANCE")
            assert await uow.instrument_selection.release_generic_materialization_generation_lease(gid,
                worker_id=request.worker_id,lease_epoch=generation.lease_epoch)
    forged = type(proof).model_validate({**proof.model_dump(),"transition_rule":"NORMAL_TRANSITION",
        "recovery_reason":None,"first_eligible_close_time_ms":at//HOUR*HOUR})
    if not arm_before_switch:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)), patch.object(
            PostgresInstrumentSelectionRepository,"prepare_generic_static_activation_proof",new=AsyncMock(return_value=forged)), patch.object(
            PostgresInstrumentSelectionRepository,"require_generic_static_activation_proof",new=AsyncMock(return_value=at)), pytest.raises(
                sa.exc.DBAPIError,match="Static NORMAL cannot skip recovery provenance"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_generic_authority(control.selection_spec_id)==previous
        assert (await uow.instrument_selection.get_generic_static_materialization_generation(gid)).lifecycle_state.value=="STAGED"
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
        activated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at)
    assert activated.disposition is MaterializationDisposition.ACTIVE_NEW


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
@pytest.mark.parametrize("fault_stage", [None, "comparison_switch_before_claim", "before_issue", "between_claim_ticket", "before_dispatch", "valid_empty_after_protection", "stale_before_claim", "pending_static_between_claim_ticket", "static_after_protection", "static_timeout_after_protection", "static_normal_after_protection", "static_close_boundary_after_protection",
    *(f"static_slow_normal_after_protection:{delay}" for delay in (8000,30000,120000)),
    *("static_new_entry:"+fault for fault in ("before_issue","between_claim_ticket","before_dispatch","stale_before_dispatch")),
    *("real_pause_drain:"+fault for fault in ("sent","unknown","partial","false","string","sent_recover","unknown_recover","partial_recover",
        "sent_early_resume","unknown_early_resume","partial_early_resume","sent_early_resume_recover","unknown_early_resume_recover","partial_early_resume_recover")),
    *("prepared_pause:"+fault for fault in ("empty","nonempty","early_empty","early_nonempty"))])
async def test_hourly_natural_selection_no_change_successor_is_eligible(
    database: AsyncEngine, group: str, fault_stage: str | None,
) -> None:
    await _exercise_generic_generation(database,group,True,
        durable=True,first_activation=True,natural_selection=True)
    spec = inputs(group).spec
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        assert current is not None and current.authority.authority_outcome == "ACTIVE_NEW"
        first = await uow.instrument_selection.get_generic_snapshot(current.authority.selection_snapshot_id)
    assert first.selected_members == (spec.candidate_ids[0],)
    current_uid = current.authority.event_binding.universe_version_id
    async with database.connect() as conn:
        scope_id = await conn.scalar(sa.text(
            "SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid AND exchange_instrument_id=:member"
        ), {"uid":current_uid,"member":first.selected_members[0]})
    first_close = current.authority.current_close_proof.current_final_close_time_ms

    class HourlyObservationMarket:
        def __init__(self, template, closed_at_ms):
            self.template = template
            self.shift_ms = closed_at_ms-template.trigger_candle_close_time_ms

        async def fetch_closed_candles(self, request):
            candles = self.template.candles_1h if request.timeframe=="1h" else self.template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.shift_ms,
                "close_time_ms":c.close_time_ms+self.shift_ms}) for c in candles)[-request.limit:]

    long_template = mpg_long_snapshot() if group == "MPG-001" else mi_long_snapshot()
    first_observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
        HourlyObservationMarket(long_template,first_close),ObservationRequest(
            runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=first_close,attempted_at_ms=first_close+30_005))
    assert first_observed.status is ObservationStatus.NO_SIGNAL, first_observed
    assert first_observed.detector_reason == "COMPARISON_REBASE_REQUIRED", first_observed
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
    source = inputs(group).model_copy(update={"selection_epoch_id":first.selection_epoch_id})
    source = source.model_copy(update={"member_windows":tuple(
        qualify_window(member.model_copy(update={"candles":source.member_windows[0].candles}),
            member.exchange_instrument_id==spec.candidate_ids[0])
        for member in source.member_windows)})
    successor_source = next_input(source).model_copy(update={"predecessor_snapshot":first})

    class HourlyMarket:
        def __init__(self, source_input):
            self.source_input = source_input

        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            assert event_spec_id == spec.event_spec_id and len(product_profiles) == 24
            return tuple(member.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                for member in self.source_input.member_windows)

        async def fetch_generic_selection_klines(self, request):
            return next(member.candles for member in self.source_input.member_windows
                if member.exchange_instrument_id == request.exchange_instrument_id)

    tick = successor_source.feature_cutoff_at_ms

    def clock():
        nonlocal tick
        tick += 1
        return tick

    selected = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=HourlyMarket(successor_source),
        request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=first.selection_epoch_id,
            period_anchor_ms=successor_source.feature_cutoff_at_ms,
            worker_id=f"hourly-successor:{group}"),clock_ms=clock)
    assert selected.outcome == "SNAPSHOT_READY", selected
    async with PostgresKernelUnitOfWork(database) as uow:
        successor = await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
    assert successor.selected_members == first.selected_members
    grant_at = successor.effective_from_ms+8_000
    await make_warming_ready(database,universe_version_id=current_uid,
        warm_closed_bar_time_ms=successor.effective_from_ms,valid_until_ms=grant_at+60_000)
    template = mpg_flat_snapshot() if group == "MPG-001" else mi_flat_snapshot()
    delta = successor.effective_from_ms-template.trigger_candle_close_time_ms
    candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,
        "close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
    cache = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,
        universe_version_id=current_uid,strategy_group_id=group,
        exchange_instrument_ids=spec.candidate_ids,
        closed_bar_time_ms=successor.effective_from_ms,
        lookback_bars=8 if group=="MPG-001" else 12,
        freshness_window_ms=HOUR,
        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,
            candles_1h=candles) for member in spec.candidate_ids))
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.strategy_universes.save_comparative_projection(
            cache.model_copy(update={"comparison_transition_revision":1}))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=grant_at)):
        granted = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericSnapshotRequest(selection_snapshot_id=successor.selection_snapshot_id,
                worker_id=f"hourly-no-change:{group}"),clock_ms=lambda:grant_at)
    assert granted.disposition is MaterializationDisposition.NO_CHANGE, granted
    async with PostgresKernelUnitOfWork(database) as uow:
        next_current = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        assert next_current is not None
        assert next_current.authority.selection_snapshot_id == successor.selection_snapshot_id
        assert next_current.authority.event_binding.universe_version_id == current_uid
        assert next_current.authority.comparison_transition_revision == 1
    flat_template = mpg_flat_snapshot() if group == "MPG-001" else mi_flat_snapshot()
    second_observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
        HourlyObservationMarket(flat_template,successor.effective_from_ms),ObservationRequest(
            runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=successor.effective_from_ms,
            attempted_at_ms=grant_at+1))
    assert second_observed.status is ObservationStatus.NO_SIGNAL, second_observed
    assert second_observed.detector_reason != "COMPARISON_REBASE_REQUIRED", second_observed
    async with database.connect() as conn:
        checkpoint = (await conn.execute(sa.text(
            "SELECT comparison_armed_at_ms,comparison_transition_revision,comparison_last_detector_status,comparison_last_observed_at_ms "
            "FROM brc_exposure_episode_current WHERE event_spec_id=:event AND exchange_instrument_id=:member"
        ), {"event":spec.event_spec_id,"member":first.selected_members[0]})).mappings().one()
        assert checkpoint["comparison_armed_at_ms"] == successor.effective_from_ms, checkpoint
        assert checkpoint["comparison_transition_revision"] == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
    third_source = next_input(successor_source).model_copy(update={
        "predecessor_snapshot":successor,
    })
    third_tick = third_source.feature_cutoff_at_ms

    def third_clock():
        nonlocal third_tick
        third_tick += 1
        return third_tick

    third_run = await run_instrument_selection_once(
        uow_factory=lambda:PostgresKernelUnitOfWork(database),
        market_source=HourlyMarket(third_source),
        request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=first.selection_epoch_id,
            period_anchor_ms=third_source.feature_cutoff_at_ms,
            worker_id=f"hourly-third:{group}"),clock_ms=third_clock)
    assert third_run.outcome == "SNAPSHOT_READY", third_run
    async with PostgresKernelUnitOfWork(database) as uow:
        third = await uow.instrument_selection.get_generic_snapshot(third_run.selection_snapshot_id)
    assert third.selected_members == first.selected_members
    third_grant_at = third.effective_from_ms+8_000
    await make_warming_ready(database,universe_version_id=current_uid,
        warm_closed_bar_time_ms=third.effective_from_ms,valid_until_ms=third_grant_at+60_000)
    third_delta = third.effective_from_ms-long_template.trigger_candle_close_time_ms
    third_candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+third_delta,
        "close_time_ms":c.close_time_ms+third_delta}) for c in long_template.candles_1h)
    third_cache = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,
        universe_version_id=current_uid,strategy_group_id=group,
        exchange_instrument_ids=spec.candidate_ids,
        closed_bar_time_ms=third.effective_from_ms,
        lookback_bars=8 if group=="MPG-001" else 12,
        freshness_window_ms=HOUR,
        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,
            candles_1h=third_candles) for member in spec.candidate_ids))
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.strategy_universes.save_comparative_projection(
            third_cache.model_copy(update={"comparison_transition_revision":1}))
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
        new=AsyncMock(return_value=third_grant_at)):
        third_grant = await coordinate_selection_materialization_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),
            request=CoordinateGenericSnapshotRequest(selection_snapshot_id=third.selection_snapshot_id,
                worker_id=f"hourly-third-grant:{group}"),clock_ms=lambda:third_grant_at)
    assert third_grant.disposition is MaterializationDisposition.NO_CHANGE, third_grant
    third_observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),
        HourlyObservationMarket(long_template,third.effective_from_ms),ObservationRequest(
            runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            trigger_candle_close_time_ms=third.effective_from_ms,
            attempted_at_ms=third_grant_at+1))
    assert third_observed.status == ObservationStatus.SIGNAL_CREATED, third_observed
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 1
    await _issue_and_dispatch_hourly_natural_entry(database,group=group,
        signal_event_id=third_observed.signal_event_id,
        selection_authority_id=third_grant.selection_authority_id,
        member=first.selected_members[0],universe_version_id=current_uid,
        closed_at_ms=third.effective_from_ms,now_ms=third_grant_at+2,
        fault_stage=fault_stage)


async def _assert_terminal_static_owner_reauthorization(database, *, group, at_ms, fail_retries=0):
    from src.trading_kernel.application.owner_control import (
        set_strategy_entry_state,
        stage_generic_static_selection_mode,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        old = await uow.instrument_selection.get_generic_static_materialization_generation(
            GenericStaticMaterializationGeneration.id_for_authorization(control.pending_authorization_id))
        authority = await uow.instrument_selection.get_current_generic_authority(control.selection_spec_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=control.selection_spec_id)
    assert old.lifecycle_state.value in {"FAILED_CLOSED","ABANDONED"}
    cadence = inputs(group).spec.cadence_hours*HOUR
    anchor = (at_ms//cadence+1)*cadence
    request = ControlMutationRequest(expected_version=control.control_version,
        reason="retry_terminal_static_intent",idempotency_key=f"retry-static:{group}:{old.authorization_id}",
        owner_identity="owner",now_ms=at_ms)
    for defect in ("version","epoch","baseline","period","step_up","time"):
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises((OwnerControlBlocked,OwnerControlConflict)):
                await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                    rollback_baseline_id="rollback-baseline:wrong" if defect=="baseline" else control.rollback_baseline_id,
                    selection_epoch_id="epoch:wrong" if defect=="epoch" else control.selection_epoch_id,
                    effective_period_anchor_ms=anchor+HOUR if defect=="period" else anchor,
                    request=request.model_copy(update={"expected_version":control.control_version+1 if defect=="version" else control.control_version,
                        "idempotency_key":request.idempotency_key+":"+defect,"now_ms":old.terminal_at_ms-1 if defect=="time" else at_ms}),
                    authentication_strength="password" if defect=="step_up" else "totp_step_up")
    async with PostgresKernelUnitOfWork(database) as uow:
        savepoint = await uow._connection.begin_nested()
        owner = await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="reauthorization_must_not_clear_pause",
                idempotency_key=request.idempotency_key+":pause-probe",owner_identity="owner",now_ms=at_ms),authentication_strength="totp_step_up")
        with pytest.raises(OwnerControlBlocked,match="reauthorization_source_invalid"):
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                effective_period_anchor_ms=anchor,request=request.model_copy(update={"idempotency_key":request.idempotency_key+":paused"}),
                authentication_strength="totp_step_up")
        await savepoint.rollback()
    @asynccontextmanager
    async def interrupted_authorization():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected Static reauthorization rollback")
    with pytest.raises(RuntimeError,match="reauthorization rollback"):
        async with interrupted_authorization() as uow:
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                effective_period_anchor_ms=anchor,request=request,authentication_strength="totp_step_up")
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_selection_control(group)==control
        assert await uow.owner_controls.get_authorization_by_idempotency_key(request.idempotency_key) is None
    async def authorize(retry_request):
        try:
            async with PostgresKernelUnitOfWork(database) as uow:
                return await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                    rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                    effective_period_anchor_ms=anchor,request=retry_request,authentication_strength="totp_step_up")
        except OwnerControlBlocked as exc:
            return exc
    results = await asyncio.wait_for(asyncio.gather(authorize(request),authorize(request.model_copy(update={
        "idempotency_key":request.idempotency_key+":concurrent"}))),timeout=10)
    winners = [result for result in results if not isinstance(result,OwnerControlBlocked)]
    assert len(winners)==1 and sum(isinstance(result,OwnerControlBlocked) for result in results)==1
    new = winners[0]
    winning_request = request if results[0] is new else request.model_copy(update={"idempotency_key":request.idempotency_key+":concurrent"})
    assert new.pending_authorization_id!=control.pending_authorization_id
    assert new.pending_effective_period_anchor_ms==anchor and new.control_version==control.control_version
    assert new.selection_mode.value=="dynamic_selection" and new.selection_epoch_id==control.selection_epoch_id
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,request=winning_request,authentication_strength="totp_step_up")==new
        assert await uow.instrument_selection.get_generic_static_materialization_generation(old.materialization_generation_id)==old
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=control.selection_spec_id)==vacuum
        assert await uow.instrument_selection.get_current_generic_authority(control.selection_spec_id)==authority
        losing_key = request.idempotency_key+":concurrent" if winning_request.idempotency_key==request.idempotency_key else request.idempotency_key
        assert await uow.owner_controls.get_authorization_by_idempotency_key(losing_key) is None
    async with database.connect() as conn:
        events = (await conn.execute(sa.text("SELECT payload FROM brc_strategy_universe_materialization_events "
            "WHERE materialization_generation_id=:gid AND event_type='OWNER_REAUTHORIZED'"),{"gid":old.materialization_generation_id})).scalars().all()
    assert events==[{"authorization_id":new.pending_authorization_id,
        "effective_period_anchor_ms":anchor,"entry_vacuum_id":vacuum.entry_vacuum_id}]
    async with PostgresKernelUnitOfWork(database) as uow:
        with pytest.raises(OwnerControlBlocked,match="already_pending"):
            await stage_generic_static_selection_mode(uow,strategy_group_id=group,
                rollback_baseline_id=control.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
                effective_period_anchor_ms=anchor,request=request.model_copy(update={"idempotency_key":request.idempotency_key+":duplicate"}),
                authentication_strength="totp_step_up")
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    due = anchor+HOUR+1
    @asynccontextmanager
    async def interrupted_retry_handoff():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            raise RuntimeError("injected retry handoff commit failure")
    retry_request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="static-retry-materializer")
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)), pytest.raises(RuntimeError,match="retry handoff commit"):
        await coordinate_selection_materialization_once(uow_factory=interrupted_retry_handoff,request=retry_request,clock_ms=lambda:due)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=control.selection_spec_id)==vacuum
        assert await uow.instrument_selection.get_generic_static_materialization_generation(
            GenericStaticMaterializationGeneration.id_for_authorization(new.pending_authorization_id)) is None
    actual_execute = sa.ext.asyncio.AsyncConnection.execute
    async def corrupt_handoff_payload(connection,statement,*args,**kwargs):
        if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_entry_vacuum_events" and getattr(statement,"is_insert",False):
            params = statement.compile().params
            if params.get("event_type")=="SUPERSEDED" and params.get("payload",{}).get("recovery_origin")=="STATIC_RETRY":
                statement = statement.values(payload={**params["payload"],"previous_generation_id":"generation:wrong"})
        return await actual_execute(connection,statement,*args,**kwargs)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)), patch.object(
        sa.ext.asyncio.AsyncConnection,"execute",new=corrupt_handoff_payload), pytest.raises(sa.exc.DBAPIError,match="Static retry requires exact"):
        await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda:due)
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due)):
        retargeted = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda:due)
    async with PostgresKernelUnitOfWork(database) as uow:
        replacement = await uow.instrument_selection.get_generic_static_materialization_generation(retargeted.materialization_generation_id)
        retained_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=control.selection_spec_id)
        assert await uow.instrument_selection.get_generic_static_materialization_generation(old.materialization_generation_id)==old
        assert await uow.instrument_selection.get_current_generic_authority(control.selection_spec_id)==authority
    assert replacement.lifecycle_state.value=="MATERIALIZING"
    assert replacement.materialization_generation_id!=old.materialization_generation_id and replacement.fenced_at_ms==due
    assert replacement.previous_events==old.previous_events
    assert retained_vacuum.entry_vacuum_id==vacuum.entry_vacuum_id
    assert retained_vacuum.fenced_at_ms==vacuum.fenced_at_ms and retained_vacuum.drained_at_ms==vacuum.drained_at_ms
    assert retained_vacuum.source_generation_id==replacement.materialization_generation_id
    assert retained_vacuum.state is StrategyEntryVacuumState.RECONFIGURING and retained_vacuum.blocks_new_entry
    if fail_retries:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=due+1)):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda:due+1)
        failed_at = due+inputs(group).spec.materialization_timeout_ms
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)):
            failed_again = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda:failed_at)
        assert failed_again.reason_code=="MATERIALIZATION_TIMEOUT"
        async with PostgresKernelUnitOfWork(database) as uow:
            failed_replacement = await uow.instrument_selection.get_generic_static_materialization_generation(replacement.materialization_generation_id)
        assert failed_replacement.lifecycle_state.value=="FAILED_CLOSED"
        await _assert_terminal_static_owner_reauthorization(database,group=group,at_ms=failed_at+1,fail_retries=fail_retries-1)
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.instrument_selection.get_generic_static_materialization_generation(old.materialization_generation_id)==old
            assert await uow.instrument_selection.get_generic_static_materialization_generation(replacement.materialization_generation_id)==failed_replacement
            with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at+HOUR)), pytest.raises(SelectionJobConflict,match="Owner or Control"):
                await uow.instrument_selection.claim_generic_static_materialization_generation(replacement.materialization_generation_id,
                    worker_id="old-retry-callback",now_ms=failed_at+HOUR,lease_duration_ms=30000)
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT brc_static_retry_handoff_matches_v1(:gid)"),{"gid":replacement.materialization_generation_id})
            assert await conn.scalar(sa.text("SELECT brc_static_retry_successor_matches_v1(:gid,:vid)"),
                {"gid":old.materialization_generation_id,"vid":vacuum.entry_vacuum_id})
            assert not await conn.scalar(sa.text("SELECT brc_static_retry_successor_matches_v1(:gid,:vid)"),
                {"gid":old.materialization_generation_id,"vid":"vacuum:wrong-scope"})
        # Force independent deferred validation of historical terminal facts.
        # A no-op update must not invalidate them when Current has advanced.
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_strategy_universe_materialization_generations "
                "SET projection_version=projection_version WHERE materialization_generation_id IN (:root,:retry)"),
                {"root":old.materialization_generation_id,"retry":replacement.materialization_generation_id})
        return
    # A new Owner intent does not cure permanent certification failure.
    # Supply renewed eligible certification facts before testing recovery.
    async with PostgresKernelUnitOfWork(database) as uow:
        retry_baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(old.rollback_baseline_id)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='eligible',blocker_code=NULL,"
            "observed_at_ms=:at,valid_until_ms=:valid,next_check_at_ms=:valid WHERE exchange_instrument_id IN "
            "(SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),
            {"at":anchor+HOUR,"valid":due+HOUR,"uid":retry_baseline.source_event.universe_version_id})
    async def omit_retry_budget_payload(connection,statement,*args,**kwargs):
        if getattr(getattr(statement,"table",None),"name",None)=="brc_strategy_universe_materialization_events" and getattr(statement,"is_insert",False):
            params = statement.compile().params
            if params.get("event_type")=="ACTIVE" and "static_activation_proof" in params.get("payload",{}):
                original_payload = params["payload"]
                forged = dict(original_payload["static_activation_proof"])
                forged.pop("materialization_started_at_ms")
                statement = statement.values(payload={**original_payload,"static_activation_proof":forged})
        return await actual_execute(connection,statement,*args,**kwargs)
    target = None
    for offset in range(2,10):
        tick = due+offset
        async with PostgresKernelUnitOfWork(database) as uow:
            pending = await uow.instrument_selection.get_generic_static_materialization_generation(replacement.materialization_generation_id)
        if pending.lifecycle_state.value=="STAGED":
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)), patch.object(
                sa.ext.asyncio.AsyncConnection,"execute",new=omit_retry_budget_payload), pytest.raises(sa.exc.DBAPIError,match="Static activation requires atomic"):
                await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda tick=tick:tick)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            progressed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=retry_request,clock_ms=lambda tick=tick:tick)
        if progressed.disposition is MaterializationDisposition.ACTIVE_NEW:
            break
        async with PostgresKernelUnitOfWork(database) as uow:
            targets = await uow.strategy_universes.get_generation_universe_targets(replacement.materialization_generation_id)
        if targets:
            target = targets[0]
            await make_warming_ready(database,universe_version_id=target.universe_version_id,warm_closed_bar_time_ms=anchor+HOUR,valid_until_ms=due+HOUR)
            if group in {"MPG-001","MI-001"}:
                async with PostgresKernelUnitOfWork(database) as uow:
                    members = await uow.strategy_universes.get_members(target.universe_version_id)
                template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                delta = anchor+HOUR-template.trigger_candle_close_time_ms
                candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
                projection = build_comparative_universe_projection(event_spec_id=inputs(group).spec.event_spec_id,
                    universe_version_id=target.universe_version_id,strategy_group_id=group,exchange_instrument_ids=members,
                    closed_bar_time_ms=anchor+HOUR,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                    member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in members))
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.strategy_universes.save_comparative_projection(projection)
    assert progressed.disposition is MaterializationDisposition.ACTIVE_NEW, progressed
    async with PostgresKernelUnitOfWork(database) as uow:
        proof = await uow.instrument_selection.get_generic_static_activation_proof(replacement.materialization_generation_id)
        activated = await uow.instrument_selection.get_selection_control(group)
        closed_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=control.selection_spec_id)
        assert await uow.instrument_selection.get_generic_static_materialization_generation(old.materialization_generation_id)==old
    assert proof.transition_rule=="RECOVERY_TRANSITION" and proof.episode_rebase_required
    assert proof.first_eligible_close_time_ms==(proof.prepared_at_ms//HOUR+1)*HOUR
    assert proof.materialization_started_at_ms==due and proof.fenced_at_ms==vacuum.fenced_at_ms
    assert target.universe_version_id!=old.previous_events[0].universe_version_id
    assert activated.selection_mode.value=="static_baseline" and activated.pending_selection_mode is None
    assert closed_vacuum is None
    async with PostgresKernelUnitOfWork(database) as uow:
        for cursor in proof.observation_cursors:
            checkpoint = await uow.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
            assert checkpoint is not None and checkpoint.recovery_id==proof.recovery_id
            assert checkpoint.first_eligible_close_time_ms==proof.first_eligible_close_time_ms
            assert checkpoint.armed_at_close_time_ms is None
        assert uow._connection is not None
        scope_id = await uow._connection.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
            "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":target.universe_version_id})
        scope = await uow.signals.get_runtime_scope(scope_id)
        past = await resolve_selection_entry_authority(uow,runtime_scope=scope,birth_selection_authority_id=None,
            observed_close_time_ms=proof.first_eligible_close_time_ms-HOUR,now_ms=proof.prepared_at_ms+1,
            allow_current_as_birth=True,lock_current=True)
    assert not past.allowed


async def _assert_natural_prepared_entry_owner_pause(database,*,group,ticket,issued,now_ms,empty,early_resume):
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.application.owner_control import (
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    spec=inputs(group).spec
    async with PostgresKernelUnitOfWork(database) as uow:
        original=await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        before_commands=await uow.exchange_commands.list_for_ticket(issued.ticket_id)
        assert len(before_commands)==1 and before_commands[0].status.value=="prepared" and before_commands[0].generation==1
        owner=await uow.owner_controls.get_strategy_control(group)
        await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=owner.control_version,reason="pause_prepared_natural_entry",
                idempotency_key=f"prepared-pause:{group}:{empty}:{early_resume}",owner_identity="owner",now_ms=now_ms+1),authentication_strength="totp_step_up")
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=spec.selection_spec_id)
    async def resume(at):
        async with PostgresKernelUnitOfWork(database) as uow:
            owner=await uow.owner_controls.get_strategy_control(group)
            await set_strategy_entry_state(uow,strategy_group_id=group,target_state=StrategyEntryState.ENABLED,
                request=ControlMutationRequest(expected_version=owner.control_version,reason="resume_prepared_natural_entry",
                    idempotency_key=f"prepared-resume:{group}:{empty}:{early_resume}",owner_identity="owner",now_ms=at),authentication_strength="totp_step_up")
    if early_resume:
        await resume(now_ms+2)
    outcomes=[]
    for offset in (3,4,5):
        if offset==4:
            with pytest.raises(RuntimeError,match="prepared pause drain rollback"):
                async with PostgresKernelUnitOfWork(database) as uow:
                    result=await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=group,selection_spec_id=spec.selection_spec_id,now_ms=now_ms+offset))
                    assert result.status is VacuumDrainStatus.PREPARED_ENTRY_SUPERSEDED,result
                    raise RuntimeError("prepared pause drain rollback")
            async with PostgresKernelUnitOfWork(database) as uow:
                assert (await uow.aggregates.get(issued.ticket_id)).status.value=="entry_pending"
                assert (await uow.budgets.get_for_ticket(issued.ticket_id)).status=="active"
                assert await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
                assert (await uow.exchange_commands.list_for_ticket(issued.ticket_id))[0].status.value=="prepared"
        async with PostgresKernelUnitOfWork(database) as uow:
            step=await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=group,selection_spec_id=spec.selection_spec_id,now_ms=now_ms+offset))
        outcomes.append(step.status)
    assert outcomes==[VacuumDrainStatus.DRAIN_STARTED,VacuumDrainStatus.PREPARED_ENTRY_SUPERSEDED,VacuumDrainStatus.OWNER_PAUSED],outcomes
    async with PostgresKernelUnitOfWork(database) as uow:
        drained=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=spec.selection_spec_id)
        assert drained.entry_vacuum_id==vacuum.entry_vacuum_id and drained.fenced_at_ms==vacuum.fenced_at_ms
        assert drained.state is StrategyEntryVacuumState.OWNER_PAUSED and drained.drained_at_ms==now_ms+5
        assert await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)==original
        retained=await uow.tickets.get(issued.ticket_id)
        aggregate=await uow.aggregates.get(issued.ticket_id)
        commands=await uow.exchange_commands.list_for_ticket(issued.ticket_id)
        reservation=await uow.budgets.get_for_ticket(issued.ticket_id)
        assert retained.model_dump(exclude={"status"})==ticket.model_dump(exclude={"status"})
        assert aggregate.status.value=="entry_rejected" and aggregate.position_qty==0
        assert reservation.status=="released" and not await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
        assert len(commands)==1 and commands[0].status.value=="superseded"
    if not early_resume:
        await resume(now_ms+6)
    class NoVenue:
        async def execute(self,request):
            raise AssertionError("prepared paused ENTRY must never reach venue")
    refused=await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),NoVenue(),DispatchCommandRequest(worker_id="prepared-after-pause",
        ticket_id=issued.ticket_id,now_ms=now_ms+7,lease_until_ms=now_ms+30000,timeout_seconds=1))
    assert refused.status.value=="no_command",refused
    source=inputs(group).model_copy(update={"selection_epoch_id":original.authority.selection_epoch_id})
    async with PostgresKernelUnitOfWork(database) as uow:
        parent=await uow.instrument_selection.get_generic_snapshot(original.authority.selection_snapshot_id)
    while source.feature_cutoff_at_ms<parent.feature_cutoff_at_ms:
        source=next_input(source)
    source=next_input(source).model_copy(update={"predecessor_snapshot":parent})
    member=spec.candidate_ids[int(parent.selected_members==(spec.candidate_ids[0],))]
    source=source.model_copy(update={"member_windows":tuple(qualify_window(w.model_copy(update={"candles":source.member_windows[0].candles}),not empty and w.exchange_instrument_id==member) for w in source.member_windows)})
    class SelectionMarket:
        async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for w in source.member_windows)
        async def fetch_generic_selection_klines(self,request):
            return next(w.candles for w in source.member_windows if w.exchange_instrument_id==request.exchange_instrument_id)
    tick=source.feature_cutoff_at_ms
    def clock():
        nonlocal tick
        tick+=1
        return tick
    selected=await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=SelectionMarket(),
        request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,selection_epoch_id=source.selection_epoch_id,period_anchor_ms=source.feature_cutoff_at_ms,worker_id="prepared-latest-selector"),clock_ms=clock)
    assert selected.outcome=="SNAPSHOT_READY",selected
    async with PostgresKernelUnitOfWork(database) as uow:
        snapshot=await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
    assert bool(snapshot.selected_members)==(not empty)
    request=CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="prepared-latest-owner")
    for offset in range(1,8):
        at=snapshot.effective_from_ms+offset
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
            outcome=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda at=at:at)
        if outcome.disposition in {MaterializationDisposition.VALID_EMPTY,MaterializationDisposition.ACTIVE_NEW}:
            break
        if outcome.materialization_generation_id:
            async with PostgresKernelUnitOfWork(database) as uow:
                targets=await uow.strategy_universes.get_generation_universe_targets(outcome.materialization_generation_id)
            if targets:
                await make_warming_ready(database,universe_version_id=targets[0].universe_version_id,warm_closed_bar_time_ms=snapshot.effective_from_ms,valid_until_ms=at+HOUR)
                if group in {"MPG-001","MI-001"}:
                    flat=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                    delta=snapshot.effective_from_ms-flat.trigger_candle_close_time_ms
                    candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in flat.candles_1h)
                    projection=build_comparative_universe_projection(event_spec_id=spec.event_spec_id,universe_version_id=targets[0].universe_version_id,strategy_group_id=group,
                        exchange_instrument_ids=spec.candidate_ids,closed_bar_time_ms=snapshot.effective_from_ms,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                        member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in spec.candidate_ids))
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.strategy_universes.save_comparative_projection(projection)
    assert outcome.disposition is (MaterializationDisposition.VALID_EMPTY if empty else MaterializationDisposition.ACTIVE_NEW),outcome
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_runtime_incidents WHERE status='open'"))==0


async def _issue_and_dispatch_hourly_natural_entry(database, *, group, signal_event_id,
    selection_authority_id, member, universe_version_id, closed_at_ms, now_ms,
    fault_stage: str | None, authority_transition=None):
    prepared_pause_fault=None
    if fault_stage is not None and fault_stage.startswith("prepared_pause:"):
        prepared_pause_fault=fault_stage.split(":",1)[1]
        fault_stage=None
    real_pause_fault=None
    if fault_stage is not None and fault_stage.startswith("real_pause_drain:"):
        real_pause_fault=fault_stage.split(":",1)[1]
        fault_stage=None
    static_entry_fault = None
    if fault_stage is not None and fault_stage.startswith("static_new_entry:"):
        static_entry_fault = fault_stage.split(":",1)[1]
        fault_stage = "static_after_protection"
    from src.trading_kernel.application.dispatch_exchange_command import (
        DispatchCommandRequest,
        dispatch_one_command,
    )
    from src.trading_kernel.application.issue_ready_signal import (
        IssueReadySignalRequest,
        issue_ready_signal,
    )
    from src.trading_kernel.application.owner_control import set_strategy_entry_state
    from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
    from src.trading_kernel.domain.commands import (
        ExchangeCommandResult,
        ExchangeCommandStatus,
    )
    from src.trading_kernel.domain.cross_margin_stress import (
        AccountRiskSnapshot,
        MaintenanceMarginBracket,
    )
    from src.trading_kernel.domain.entry_admission_snapshot import (
        EntryAdmissionSnapshot,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState

    async def owner_pause(at_ms):
        async with PostgresKernelUnitOfWork(database) as uow:
            control = await uow.owner_controls.get_strategy_control(group)
            assert control is not None
            await set_strategy_entry_state(uow,strategy_group_id=group,
                target_state=StrategyEntryState.PAUSED,
                request=ControlMutationRequest(expected_version=control.control_version,
                    reason="hourly_entry_fault_test",idempotency_key=f"pause:{group}:{fault_stage}",
                    owner_identity="owner",now_ms=at_ms),
                authentication_strength="totp_step_up")

    async def assert_no_ticket_for_signal():
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets WHERE signal_event_id=:signal"),{"signal":signal_event_id})==0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands c JOIN brc_trade_tickets t USING(ticket_id) WHERE t.signal_event_id=:signal"),{"signal":signal_event_id})==0

    await make_warming_ready(database,universe_version_id=universe_version_id,
        warm_closed_bar_time_ms=closed_at_ms,valid_until_ms=now_ms+60_000)
    risk = AccountRiskSnapshot.create(venue_id="binance-usdm",account_id="generic-snapshot",
        account_risk_mode="standard_usdm_single_asset",settlement_asset="USDT",
        position_mode="independent_sides",margin_mode="cross",exchange_instrument_id=member,
        mark_price=Decimal(105),configured_leverage=5,total_wallet_balance=Decimal(1000),
        total_margin_balance=Decimal(1000),total_initial_margin=Decimal(0),
        total_maintenance_margin=Decimal(0),available_margin=Decimal(1000),
        account_positions=(),observed_at_ms=now_ms,valid_until_ms=now_ms+60_000)
    admission = EntryAdmissionSnapshot(account_risk_snapshot=risk,
        best_bid_price=Decimal("104.99"),best_ask_price=Decimal(105),open_orders=(),
        observed_at_ms=now_ms,valid_until_ms=now_ms+60_000)
    brackets = (MaintenanceMarginBracket(bracket_id=f"hourly-{group}:1",notional_floor=Decimal(0),
        notional_cap=Decimal(20_000),maintenance_margin_rate=Decimal("0.005"),
        maintenance_amount=Decimal(0)),)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.signals.upsert_instrument_rules(venue_id="binance-usdm",exchange_instrument_id=member,
            quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),exchange_max_leverage=5,
            maintenance_margin_brackets=brackets,maintenance_margin_brackets_digest=canonical_digest(brackets),
            notional_coefficient=Decimal(1),notional_coefficient_certified=True,
            observed_at_ms=now_ms,valid_until_ms=now_ms+60_000)
    if fault_stage in {"switch_before_claim","activated_before_claim"}:
        await authority_transition()
        async with PostgresKernelUnitOfWork(database) as uow:
            refused = await issue_ready_signal(uow,IssueReadySignalRequest(
                signal_event_id=signal_event_id,admission_snapshot=admission,
                claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms+(30 if fault_stage=="activated_before_claim" else 5)))
        if fault_stage=="activated_before_claim":
            assert refused.status.value=="scope_or_policy_mismatch",refused
            await assert_no_ticket_for_signal()
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.capacity_claims.get_for_signal(signal_event_id) is None
            return
        assert refused.status.value=="selection_entry_vacuum", refused
        async with PostgresKernelUnitOfWork(database) as uow:
            decision = await uow.admission_decisions.get_for_signal(signal_event_id)
            vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                strategy_group_id=group,selection_spec_id=inputs(group).spec.selection_spec_id)
        assert decision.first_blocker=="selection_entry_vacuum"
        assert decision.binding_constraint==vacuum.entry_vacuum_id
        assert decision.selection_authority_id==selection_authority_id
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands"))==0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_capacity_claims"))==0
        return
    if fault_stage == "stale_before_claim":
        stale_risk = AccountRiskSnapshot.create(**{
            **risk.model_dump(exclude={"snapshot_digest"}),
            "observed_at_ms":now_ms-60_000,"valid_until_ms":now_ms-1})
        stale_admission = admission.model_copy(update={
            "account_risk_snapshot":stale_risk,
            "observed_at_ms":now_ms-60_000,"valid_until_ms":now_ms-1})
        async with PostgresKernelUnitOfWork(database) as uow:
            refused = await issue_ready_signal(uow,IssueReadySignalRequest(
                signal_event_id=signal_event_id,admission_snapshot=stale_admission,
                claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms))
        assert refused.status.value == "signal_invalid_or_stale", refused
        async with PostgresKernelUnitOfWork(database) as uow:
            decision = await uow.admission_decisions.get_for_signal(signal_event_id)
            assert decision is not None
            assert decision.decision_status.value == "rejected"
            assert decision.selection_authority_id == selection_authority_id
            assert decision.entry_admission_snapshot_digest == stale_admission.digest()
            assert decision.capacity_claim_id is None and decision.ticket_id is None
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_capacity_claims")) == 0
        return
    if fault_stage == "comparison_switch_before_claim":
        async with database.begin() as conn:
            await conn.execute(sa.text("""
                UPDATE brc_comparison_binding_current
                SET comparison_transition_revision=comparison_transition_revision+1
                WHERE event_spec_id=:event
            """), {"event":inputs(group).spec.event_spec_id})
        async with PostgresKernelUnitOfWork(database) as uow:
            refused = await issue_ready_signal(uow,IssueReadySignalRequest(
                signal_event_id=signal_event_id,admission_snapshot=admission,
                claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms))
        assert refused.status.value == "selection_authority_invalid", refused
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        return
    if fault_stage == "before_issue":
        await owner_pause(now_ms+1)
        refused_admission = admission.model_copy(update={
            "account_risk_snapshot":AccountRiskSnapshot.create(**{
                **risk.model_dump(exclude={"snapshot_digest"}),
                "observed_at_ms":now_ms+2,"valid_until_ms":now_ms+60_002}),
            "observed_at_ms":now_ms+2,"valid_until_ms":now_ms+60_002})
        async with PostgresKernelUnitOfWork(database) as uow:
            refused = await issue_ready_signal(uow,IssueReadySignalRequest(
                signal_event_id=signal_event_id,admission_snapshot=refused_admission,
                claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms+2))
        assert refused.status.value == "scope_or_policy_mismatch", refused
        await assert_no_ticket_for_signal()
        return
    delayed_static = fault_stage is not None and fault_stage.startswith("static_slow_normal_after_protection:")
    assert delayed_static or fault_stage in {None,"between_claim_ticket","before_dispatch","stale_before_dispatch","valid_empty_after_protection","pending_static_between_claim_ticket","switch_between_claim_ticket","switch_before_dispatch","switch_during_dispatch_facts","static_after_protection","static_timeout_after_protection","static_normal_after_protection","static_close_boundary_after_protection","activated_between_claim_ticket","activated_before_dispatch"}
    if fault_stage in {"between_claim_ticket","switch_between_claim_ticket","activated_between_claim_ticket"}:
        from src.trading_kernel.application.issue_ticket import (
            issue_ticket as actual_issue_ticket,
        )

        async def pause_after_claim(uow, issue_request):
            assert issue_request.capacity_claim.selection_authority_id == selection_authority_id
            if fault_stage=="activated_between_claim_ticket":
                assert issue_request.capacity_claim.expires_at_ms>now_ms+30
            if fault_stage in {"switch_between_claim_ticket","activated_between_claim_ticket"}:
                await authority_transition()
                issue_request = issue_request.model_copy(update={"now_ms":now_ms+(30 if fault_stage=="activated_between_claim_ticket" else 5)})
            else:
                await owner_pause(now_ms+1)
            return await actual_issue_ticket(uow,issue_request)

        with patch("src.trading_kernel.application.issue_ready_signal.issue_ticket",
            new=pause_after_claim):
            async with PostgresKernelUnitOfWork(database) as uow:
                refused = await issue_ready_signal(uow,IssueReadySignalRequest(
                    signal_event_id=signal_event_id,admission_snapshot=admission,
                    claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                    schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms))
        assert refused.status.value == ("scope_or_policy_mismatch" if fault_stage=="activated_between_claim_ticket" else
            "selection_entry_vacuum" if fault_stage=="switch_between_claim_ticket" else "strategy_paused"), refused
        if fault_stage=="switch_between_claim_ticket":
            async with PostgresKernelUnitOfWork(database) as uow:
                decision = await uow.admission_decisions.get_for_signal(signal_event_id)
            assert decision.decision_status.value=="rejected"
            assert decision.first_blocker=="selection_entry_vacuum"
            assert decision.selection_authority_id==selection_authority_id
            assert decision.capacity_claim_id is None and decision.ticket_id is None
        await assert_no_ticket_for_signal()
        if fault_stage=="activated_between_claim_ticket":
            async with PostgresKernelUnitOfWork(database) as uow:
                assert await uow.capacity_claims.get_for_signal(signal_event_id) is None
        return
    async def issue_natural_signal():
        async with PostgresKernelUnitOfWork(database) as uow:
            return await issue_ready_signal(uow,IssueReadySignalRequest(
                signal_event_id=signal_event_id,admission_snapshot=admission,
                claim_owner=f"hourly-{group}-entry",runtime_commit="a"*40,
                schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now_ms))

    if fault_stage == "pending_static_between_claim_ticket":
        from src.trading_kernel.application.issue_ticket import (
            issue_ticket as actual_issue_ticket,
        )
        from src.trading_kernel.application.owner_control import (
            stage_generic_static_selection_mode,
        )

        async def schedule_after_claim(uow, issue_request):
            assert issue_request.capacity_claim.selection_authority_id == selection_authority_id
            async with PostgresKernelUnitOfWork(database) as owner_uow:
                control = await owner_uow.instrument_selection.get_selection_control(group)
                assert control is not None and control.rollback_baseline_id is not None
                cadence = inputs(group).spec.cadence_hours*HOUR
                await stage_generic_static_selection_mode(owner_uow,strategy_group_id=group,
                    rollback_baseline_id=control.rollback_baseline_id,
                    selection_epoch_id=control.selection_epoch_id,
                    effective_period_anchor_ms=((now_ms+1)//cadence+1)*cadence,
                    authentication_strength="totp_step_up",
                    request=ControlMutationRequest(expected_version=control.control_version,
                        reason="future_static_intent_during_claim",
                        idempotency_key=f"static:during-claim:{group}",owner_identity="owner",now_ms=now_ms+1))
            return await actual_issue_ticket(uow,issue_request)

        with patch("src.trading_kernel.application.issue_ready_signal.issue_ticket",new=schedule_after_claim):
            issued = await issue_natural_signal()
    else:
        issued = await issue_natural_signal()
    assert issued.status.value == "issued", issued
    async with PostgresKernelUnitOfWork(database) as uow:
        ticket = await uow.tickets.get(issued.ticket_id)
        claim = await uow.capacity_claims.get_for_signal(signal_event_id)
        assert ticket is not None and claim is not None
        assert ticket.selection_authority_id == selection_authority_id
        assert claim.selection_authority_id == selection_authority_id
        if fault_stage == "pending_static_between_claim_ticket":
            control = await uow.instrument_selection.get_selection_control(group)
            current = await uow.instrument_selection.get_current_generic_authority(inputs(group).spec.selection_spec_id)
            assert control.pending_selection_mode.value == "static_baseline"
            assert control.selection_mode.value == "dynamic_selection"
            assert current.authority.selection_authority_id == selection_authority_id
            assert current.authority.selection_control_version == control.control_version
            assert current.authority.event_binding.universe_version_id == universe_version_id

    if prepared_pause_fault is not None:
        await _assert_natural_prepared_entry_owner_pause(database,group=group,ticket=ticket,issued=issued,
            now_ms=now_ms,empty=prepared_pause_fault.endswith("empty") and not prepared_pause_fault.endswith("nonempty"),
            early_resume=prepared_pause_fault.startswith("early_"))
        return
    class ActionFacts:
        async def read_entry_admission_snapshot(self, request):
            if fault_stage=="switch_during_dispatch_facts":
                async with PostgresKernelUnitOfWork(database) as uow:
                    commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
                assert len(commands)==1 and commands[0].status is ExchangeCommandStatus.CLAIMED
                await authority_transition()
            if fault_stage=="stale_before_dispatch":
                stale_risk = AccountRiskSnapshot.create(**{**risk.model_dump(exclude={"snapshot_digest"}),
                    "observed_at_ms":request.observed_at_ms-60000,"valid_until_ms":request.observed_at_ms-1})
                return admission.model_copy(update={"account_risk_snapshot":stale_risk,
                    "observed_at_ms":request.observed_at_ms-60000,"valid_until_ms":request.observed_at_ms-1})
            fresh_risk = AccountRiskSnapshot.create(**{
                **risk.model_dump(exclude={"snapshot_digest"}),
                "observed_at_ms":request.observed_at_ms,
                "valid_until_ms":request.observed_at_ms+request.valid_for_ms})
            return admission.model_copy(update={"account_risk_snapshot":fresh_risk,
                "observed_at_ms":request.observed_at_ms,
                "valid_until_ms":request.observed_at_ms+request.valid_for_ms})

        async def read_instrument_rules(self, request):
            return InstrumentRulesFacts(exchange_instrument_id=request.exchange_instrument_id,
                quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),exchange_max_leverage=5,
                maintenance_margin_brackets=brackets,
                maintenance_margin_brackets_digest=canonical_digest(brackets),
                notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms+request.valid_for_ms)

    class Venue:
        def __init__(self):
            self.calls = []
            self.now_ms = now_ms+5

        async def execute(self, request):
            async with PostgresKernelUnitOfWork(database) as uow:
                command = await uow.exchange_commands.get(request.command_id)
                assert command.status is ExchangeCommandStatus.CLAIMED
            self.calls.append(request)
            return ExchangeCommandResult(status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=self.now_ms+1,
                exchange_order_id=f"hourly-{group}-{issued.ticket_id}-{request.kind.value}-{len(self.calls)}")

    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_runtime_capabilities_current SET enabled=true WHERE capability_key='exchange_commands'"))
    if fault_stage == "before_dispatch":
        await owner_pause(now_ms+1)
    if fault_stage in {"switch_before_dispatch","activated_before_dispatch"}:
        await authority_transition()
    venue = Venue()
    dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
        DispatchCommandRequest(worker_id=f"hourly-{group}-dispatch",ticket_id=issued.ticket_id,
            now_ms=now_ms+(30 if fault_stage=="activated_before_dispatch" else 5),lease_until_ms=now_ms+30_000,timeout_seconds=1,
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=60_000),entry_facts_source=ActionFacts())
    if fault_stage in {"before_dispatch","stale_before_dispatch","switch_before_dispatch","switch_during_dispatch_facts","activated_before_dispatch"}:
        assert dispatched.status.value == ("no_command" if fault_stage=="activated_before_dispatch" else "superseded"), dispatched
        assert venue.calls == []
        async with database.connect() as conn:
            assert await conn.scalar(sa.text(
                "SELECT status FROM brc_exchange_commands WHERE ticket_id=:ticket AND command_kind='entry'"
            ), {"ticket":issued.ticket_id}) == ("rejected" if fault_stage=="stale_before_dispatch" else "superseded")
        async with PostgresKernelUnitOfWork(database) as uow:
            reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
            assert reservation is not None and reservation.status=="released"
            assert not await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
            commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
            assert len(commands)==1 and commands[0].generation==1
            if fault_stage=="activated_before_dispatch":
                retained=await uow.tickets.get(issued.ticket_id)
                assert retained.model_dump(exclude={"status"})==ticket.model_dump(exclude={"status"})
                aggregate=await uow.aggregates.get(issued.ticket_id)
                assert aggregate.position_qty==0
        if fault_stage in {"switch_before_dispatch","switch_during_dispatch_facts"}:
            async with database.connect() as conn:
                payload = await conn.scalar(sa.text("SELECT payload FROM brc_trade_events "
                    "WHERE ticket_id=:ticket AND event_type='EntryVacuumSuperseded'"),{"ticket":issued.ticket_id})
            async with PostgresKernelUnitOfWork(database) as uow:
                vacuum = await uow.instrument_selection.get_current_entry_vacuum(
                    strategy_group_id=group,selection_spec_id=inputs(group).spec.selection_spec_id)
            assert payload["entry_vacuum_id"]==vacuum.entry_vacuum_id
            assert payload["command_id"]==commands[0].command_id
        return
    assert dispatched.status.value == "accepted", dispatched
    assert len(venue.calls) == 1
    if real_pause_fault is not None:
        async with PostgresKernelUnitOfWork(database) as uow:
            current=await uow.instrument_selection.get_current_generic_authority(inputs(group).spec.selection_spec_id)
            parent=await uow.instrument_selection.get_generic_snapshot(current.authority.selection_snapshot_id)
        source=inputs(group).model_copy(update={"selection_epoch_id":parent.selection_epoch_id})
        while source.feature_cutoff_at_ms<parent.feature_cutoff_at_ms:
            source=next_input(source)
        assert source.feature_cutoff_at_ms==parent.feature_cutoff_at_ms
        await _assert_natural_sent_entry_drained_by_selection(database,group=group,current=current,issued=issued,
            ticket=ticket,venue=venue,initial_source=source,entry_dispatched_at_ms=now_ms+5,
            supersede_with_nonempty=True,unknown_cancel=real_pause_fault.startswith("unknown"),partial_fill=real_pause_fault.startswith("partial"),
            pause_owner=True,corrupt_pause_completion=real_pause_fault if real_pause_fault in {"false","string"} else None,
            paused_nonempty_recovery=real_pause_fault.endswith("_recover"),early_resume="early_resume" in real_pause_fault)
        return
    from src.trading_kernel.application.maintain_ticket_lifecycle import (
        LifecycleMaintenanceRequest,
        TicketLifecycleFacts,
        maintain_ticket_lifecycle,
    )
    from src.trading_kernel.application.reconcile_ticket import (
        ReconcileTicketRequest,
        reconcile_ticket,
    )
    from src.trading_kernel.application.settle_ticket import (
        RecordTradeReviewRequest,
        SettleTicketRequest,
        record_trade_review,
        settle_ticket,
    )
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.events import PostFillStressAssessed
    from src.trading_kernel.domain.position import PositionSnapshot
    from src.trading_kernel.domain.reducer import reduce_event
    from tests.trading_kernel.support.capacity_claims import make_stress_evidence

    async with PostgresKernelUnitOfWork(database) as uow:
        filled = await reconcile_ticket(uow,ReconcileTicketRequest(ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=ticket.quantity,average_entry_price=ticket.entry_reference_price,
                venue_reported_liquidation_price=Decimal(0),open_orders=(),observed_at_ms=now_ms+100)))
    assert filled.status.value == "entry_fill_recorded"

    static_cutover_finished = False
    class SelectionReadsForbidden:
        def __getattr__(self,name):
            raise AssertionError(f"frozen Ticket lifecycle read Selection repository: {name}")

    @asynccontextmanager
    async def safety_uow():
        async with PostgresKernelUnitOfWork(database) as uow:
            if static_cutover_finished:
                uow.instrument_selection = SelectionReadsForbidden()
            yield uow

    async def dispatch_safety(step):
        async with PostgresKernelUnitOfWork(database) as uow:
            pending = await uow.aggregates.get(issued.ticket_id)
            if pending is not None and pending.status is AggregateStatus.POST_FILL_RISK_PENDING:
                event = PostFillStressAssessed(
                    event_id=f"event:{issued.ticket_id}:{pending.last_event_sequence+1}",
                    ticket_id=issued.ticket_id,sequence=pending.last_event_sequence+1,
                    occurred_at_ms=now_ms+step-1,status="passed",
                    evidence=make_stress_evidence(pending.ticket),
                    owner_policy_id=pending.ticket.owner_policy_id,
                    owner_policy_version=pending.ticket.owner_policy_version,
                    filled_qty=pending.position_qty,average_fill_price=pending.average_fill_price,
                    initial_stop_price=pending.ticket.initial_stop_price,
                    initial_stop_exchange_order_id=pending.initial_stop_exchange_order_id)
                await uow.commit_reduction(event=event,reduction=reduce_event(pending,event),
                    expected_version=pending.version)
        venue.now_ms = now_ms+step
        result = await dispatch_one_command(safety_uow,venue,
            DispatchCommandRequest(worker_id=f"hourly-{group}-lifecycle",ticket_id=issued.ticket_id,
                now_ms=venue.now_ms,lease_until_ms=venue.now_ms+30_000,timeout_seconds=1))
        assert result.status.value == "accepted", result

    await dispatch_safety(200)
    await dispatch_safety(300)
    async with PostgresKernelUnitOfWork(database) as uow:
        protected = await uow.aggregates.get(issued.ticket_id)
    assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
    assert protected.initial_stop_exchange_order_id is not None
    assert protected.tp1_exchange_order_id is not None
    exit_offset = 400
    if delayed_static or fault_stage in {"static_after_protection","static_timeout_after_protection","static_normal_after_protection","static_close_boundary_after_protection"}:
        static_at = await _cutover_static_with_protected_ticket(database,group=group,ticket=ticket,at_ms=now_ms+350,
            timeout=fault_stage=="static_timeout_after_protection",
            continuous=group in {"MPG-001","MI-001"} and (delayed_static or fault_stage in {"static_normal_after_protection","static_close_boundary_after_protection"}),
            close_failure=fault_stage=="static_close_boundary_after_protection",normal_delay_ms=int(fault_stage.rsplit(":",1)[1]) if delayed_static else 0)
        static_cutover_finished = True
        exit_offset = static_at-now_ms+400
    if fault_stage == "valid_empty_after_protection":
        async with PostgresKernelUnitOfWork(database) as uow:
            current_authority = await uow.instrument_selection.get_current_generic_authority(
                inputs(group).spec.selection_spec_id)
            assert current_authority is not None
            previous_snapshot = await uow.instrument_selection.get_generic_snapshot(
                current_authority.authority.selection_snapshot_id)
        empty_input = inputs(group).model_copy(update={
            "selection_epoch_id":previous_snapshot.selection_epoch_id})
        while empty_input.feature_cutoff_at_ms < previous_snapshot.feature_cutoff_at_ms:
            empty_input = next_input(empty_input)
        empty_input = next_input(empty_input).model_copy(update={
            "predecessor_snapshot":previous_snapshot})
        empty_input = empty_input.model_copy(update={"member_windows":tuple(
            qualify_window(window,False) for window in empty_input.member_windows)})
        class EmptyMarket:
            async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
                return tuple(window.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                    for window in empty_input.member_windows)

            async def fetch_generic_selection_klines(self, request):
                return next(window.candles for window in empty_input.member_windows
                    if window.exchange_instrument_id==request.exchange_instrument_id)
        selection_tick = empty_input.feature_cutoff_at_ms
        def empty_clock():
            nonlocal selection_tick
            selection_tick += 1
            return selection_tick
        selected = await run_instrument_selection_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=EmptyMarket(),
            request=RunInstrumentSelectionRequest(selection_spec_id=empty_input.spec.selection_spec_id,
                selection_epoch_id=empty_input.selection_epoch_id,
                period_anchor_ms=empty_input.feature_cutoff_at_ms,
                worker_id=f"hourly-{group}-empty-selector"),clock_ms=empty_clock)
        assert selected.outcome == "SNAPSHOT_READY", selected
        async with PostgresKernelUnitOfWork(database) as uow:
            empty_snapshot = await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
        assert not empty_snapshot.selected_members
        empty_at = empty_snapshot.effective_from_ms+1
        empty_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty_snapshot.selection_snapshot_id,
            worker_id=f"hourly-{group}-empty-coordinator")
        negative = None
        for offset in range(5):
            tick = empty_at+offset
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",
                new=AsyncMock(return_value=tick)):
                outcome = await coordinate_selection_materialization_once(
                    uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,
                    clock_ms=lambda tick=tick:tick)
            if outcome.disposition is MaterializationDisposition.VALID_EMPTY:
                negative = outcome
                break
        assert negative is not None
        async with PostgresKernelUnitOfWork(database) as uow:
            current_empty = await uow.instrument_selection.get_current_generic_authority(inputs(group).spec.selection_spec_id)
            frozen = await uow.tickets.get(issued.ticket_id)
            ongoing = await uow.aggregates.get(issued.ticket_id)
            scope = await uow.signals.get_runtime_scope(ticket.runtime_scope_id)
            assert scope is not None
            denied = await resolve_selection_entry_authority(uow,runtime_scope=scope,
                birth_selection_authority_id=selection_authority_id,
                observed_close_time_ms=empty_snapshot.effective_from_ms,now_ms=empty_at+4,
                allow_current_as_birth=False,lock_current=True)
        assert current_empty is not None and current_empty.authority.authority_outcome == "VALID_EMPTY"
        assert frozen is not None and frozen.selection_authority_id == selection_authority_id
        assert ongoing is not None and ongoing.status is AggregateStatus.POSITION_PROTECTED
        assert not denied.allowed and denied.reason_code == "selection_valid_empty"
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 1
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands "
                "WHERE command_kind='entry'")) == 1
        exit_offset = empty_at-now_ms+400
    async with safety_uow() as uow:
        runner = await maintain_ticket_lifecycle(uow,LifecycleMaintenanceRequest(
            ticket_id=issued.ticket_id,
            facts=TicketLifecycleFacts(position_quantity=ticket.quantity-ticket.take_profit_quantities[0],
                tp1_filled_quantity=ticket.take_profit_quantities[0],
                tp1_average_fill_price=ticket.take_profit_prices[0],
                allocated_entry_fee_quote=Decimal("0.01"),exit_taker_fee_rate=Decimal("0.001"),
                price_tick=Decimal("0.01"),market_facts=None,observed_at_ms=now_ms+exit_offset),
            now_ms=now_ms+exit_offset))
    assert runner.status.value == "break_even_requested"
    await dispatch_safety(exit_offset+100)
    await dispatch_safety(exit_offset+200)
    async with safety_uow() as uow:
        external_flat = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=Decimal(0),average_entry_price=None,open_orders=(),
                observed_at_ms=now_ms+exit_offset+300)))
    assert external_flat.status.value == "external_flat_incident"
    await dispatch_safety(exit_offset+400)
    async with safety_uow() as uow:
        matched = await reconcile_ticket(uow,ReconcileTicketRequest(
            ticket_id=issued.ticket_id,
            snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                quantity=Decimal(0),average_entry_price=None,open_orders=(),
                observed_at_ms=now_ms+exit_offset+500)))
        settled = await settle_ticket(uow,SettleTicketRequest(
            ticket_id=issued.ticket_id,settled_at_ms=now_ms+exit_offset+600))
        reviewed = await record_trade_review(uow,RecordTradeReviewRequest(
            ticket_id=issued.ticket_id,review_id=f"review:hourly-{group}" if selection_authority_id is not None else f"review:static:{issued.ticket_id}",
            outcome="closed",metrics={"realized_pnl":"1.25"},
            decision_impact={"strategy_action":"keep"},recorded_at_ms=now_ms+exit_offset+700))
        terminal = await uow.aggregates.get(issued.ticket_id)
        frozen = await uow.tickets.get(issued.ticket_id)
        reservation = await uow.budgets.get_for_ticket(issued.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(issued.ticket_id)
        active_domain = await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
        commands = await uow.exchange_commands.list_for_ticket(issued.ticket_id)
    assert matched.status.value == "matched"
    assert settled.status.value == "budget_settled" and reviewed.status.value == "review_recorded"
    assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
    assert frozen is not None and frozen.selection_authority_id == selection_authority_id
    assert frozen.universe_version_id==ticket.universe_version_id
    assert frozen.model_dump(exclude={"status"})==ticket.model_dump(exclude={"status"})
    assert frozen.status.value=="terminal"
    assert frozen.exit_binding_id==ticket.exit_binding_id and frozen.exit_binding_semantic_hash==ticket.exit_binding_semantic_hash
    assert all(command.ticket_identity==ticket.identity for command in commands)
    assert sum(command.kind.value=="entry" for command in commands)==1
    assert reservation is not None and reservation.status == "released"
    assert incident is None and not active_domain
    assert len(commands) == len(venue.calls)
    if selection_authority_id is None:
        async with PostgresKernelUnitOfWork(database) as uow:
            signal = await uow.signals.get(signal_event_id)
            decision = await uow.admission_decisions.get_for_signal(signal_event_id)
            proof = await uow.instrument_selection.get_generic_static_activation_proof_for_universe(ticket.universe_version_id)
        assert signal.selection_authority_id is None and decision.selection_authority_id is None
        assert signal.universe_version_id==ticket.universe_version_id and decision.ticket_id==issued.ticket_id
        assert proof is not None and proof.target_event.universe_version_id==ticket.universe_version_id
        assert ticket.exit_binding_id is not None and ticket.initial_stop_price>0
        return
    async with database.connect() as conn:
        path = (await conn.execute(sa.text("SELECT a.selection_spec_id,a.selection_epoch_id,"
            "a.selection_snapshot_id,s.occurred_at_ms,s.fact_digest,t.fact_digest AS ticket_fact_digest,"
            "t.exit_binding_id,t.exit_binding_semantic_hash,t.exit_binding_authority_version,"
            "t.initial_stop_price,t.exchange_instrument_id,agg.review_id,t.terminal_at_ms,t.capacity_claim_id,"
            "a.comparison_universe_id,a.comparison_transition_revision,spec.algorithm_semantic_digest,"
            "claim.selection_authority_id AS claim_authority,claim.universe_version_id AS claim_universe,"
            "claim.fact_digest AS claim_fact_digest "
            "FROM brc_trade_tickets t "
            "JOIN brc_selection_session_authorities a ON a.selection_authority_id=t.selection_authority_id "
            "JOIN brc_signal_events s ON s.signal_event_id=t.signal_event_id "
            "JOIN brc_trade_aggregates agg ON agg.ticket_id=t.ticket_id "
            "JOIN brc_capacity_claims claim ON claim.capacity_claim_id=t.capacity_claim_id "
            "JOIN brc_instrument_selection_specs spec ON spec.selection_spec_id=a.selection_spec_id "
            "WHERE t.ticket_id=:ticket"),{"ticket":issued.ticket_id})).mappings().one()
        member = (await conn.execute(sa.text("SELECT selected,stable_rank,input_window_digest,"
            "qualification_semantic_digest,feature_value FROM brc_instrument_selection_member_decisions "
            "WHERE selection_snapshot_id=:snapshot AND exchange_instrument_id=:member"),
            {"snapshot":path["selection_snapshot_id"],"member":path["exchange_instrument_id"]})).mappings().one()
        event_types = set((await conn.execute(sa.text("SELECT event_type FROM brc_trade_events "
            "WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})).scalars())
    assert path["selection_spec_id"] == inputs(group).spec.selection_spec_id
    assert path["algorithm_semantic_digest"]==inputs(group).spec.algorithm_semantic_digest
    assert path["capacity_claim_id"]==ticket.capacity_claim_id
    assert path["claim_authority"]==selection_authority_id and path["claim_universe"]==ticket.universe_version_id
    assert path["claim_fact_digest"]==ticket.fact_digest
    if group in {"MPG-001","MI-001"}:
        assert path["comparison_universe_id"] is not None and path["comparison_transition_revision"]>0
    else:
        assert path["comparison_universe_id"] is None and path["comparison_transition_revision"] is None
    assert path["selection_epoch_id"] is not None
    assert path["occurred_at_ms"] == closed_at_ms
    assert path["fact_digest"] == path["ticket_fact_digest"]
    assert path["exit_binding_id"] is not None
    assert path["exit_binding_semantic_hash"] is not None
    assert path["exit_binding_authority_version"] is not None
    assert path["initial_stop_price"] == ticket.initial_stop_price
    assert path["review_id"] == f"review:hourly-{group}"
    assert member["selected"] and member["stable_rank"] > 0 and member["feature_value"] is not None
    assert member["input_window_digest"].startswith("sha256:")
    assert member["qualification_semantic_digest"].startswith("sha256:")
    assert {"EntryFilled","TakeProfitFilled","ProtectionReplacementConfirmed",
        "BudgetSettled","ReviewRecorded"} <= event_types
    async with PostgresKernelUnitOfWork(database) as uow:
        events=await uow.events.list_for_ticket(issued.ticket_id)
        review=await uow.reviews.get_for_ticket(issued.ticket_id)
    lifecycle_times={type(event).__name__:event.occurred_at_ms for event in events}
    assert ticket.created_at_ms<lifecycle_times["EntryFilled"]<=lifecycle_times["TakeProfitFilled"]<=lifecycle_times["BudgetSettled"]<=path["terminal_at_ms"]
    from src.trading_kernel.domain.live_trade_evidence import (
        build_review_execution_evidence,
    )
    # This historical local fixture has a manual PnL Review, not venue fills.
    # The immutable chain is traceable but exact execution timing is incomplete.
    execution=build_review_execution_evidence(ticket=ticket,review_id=review.review_id,review_ticket_id=review.ticket_id,metrics=review.metrics,commands=commands)
    assert execution.status=="EVIDENCE_INCOMPLETE" and "ATTRIBUTED_FILLS_MISSING" in execution.missing
    assert execution.first_entry_fill_at_ms is None
    if fault_stage=="static_after_protection":
        await _issue_new_static_natural_trade(database,group=group,fault_stage=static_entry_fault)


async def _issue_second_dynamic_comparative_trade(database, *, group,selection_input=None):
    spec = inputs(group).spec
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        previous = await uow.instrument_selection.get_generic_snapshot(current.authority.selection_snapshot_id)
        epoch=current.authority.selection_epoch_id
        assert previous.predecessor_snapshot_id is None and len(previous.members)==24
        uid = current.authority.event_binding.universe_version_id
        assert uow._connection is not None
        scope_id,member = (await uow._connection.execute(sa.text("SELECT runtime_scope_id,exchange_instrument_id "
            "FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})).one()
    source = (inputs(group) if selection_input is None else selection_input).model_copy(update={"selection_epoch_id":current.authority.selection_epoch_id})
    while source.feature_cutoff_at_ms<previous.feature_cutoff_at_ms:
        source=next_input(source)
    trigger = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
    flat = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
    class Market:
        def __init__(self,template,close):
            self.template,self.delta=template,close-template.trigger_candle_close_time_ms
        async def fetch_closed_candles(self,request):
            candles=self.template.candles_1h if request.timeframe=="1h" else self.template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.delta,"close_time_ms":c.close_time_ms+self.delta}) for c in candles)
    for index,template in enumerate((trigger,flat,trigger)):
        if index:
            source=next_input(source).model_copy(update={"predecessor_snapshot":previous})
            class SelectorMarket:
                def __init__(self,selection_input):
                    self.selection_input=selection_input
                async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
                    return tuple(window.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for window in self.selection_input.member_windows)
                async def fetch_generic_selection_klines(self,request):
                    return next(window.candles for window in self.selection_input.member_windows if window.exchange_instrument_id==request.exchange_instrument_id)
            tick=source.feature_cutoff_at_ms
            def selector_clock():
                nonlocal tick
                tick+=1
                return tick
            selected=await run_instrument_selection_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=SelectorMarket(source),
                request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,selection_epoch_id=current.authority.selection_epoch_id,
                    period_anchor_ms=source.feature_cutoff_at_ms,worker_id="second-epoch-hourly-selector"),clock_ms=selector_clock)
            assert selected.outcome=="SNAPSHOT_READY",selected
            async with PostgresKernelUnitOfWork(database) as uow:
                successor=await uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
                assert successor.selection_epoch_id==epoch and len(successor.members)==24
                assert successor.predecessor_snapshot_id==previous.selection_snapshot_id
                previous=successor
        close=previous.effective_from_ms
        await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
        windows=[]
        for candidate in spec.candidate_ids:
            path=template if candidate==member else flat
            delta=close-path.trigger_candle_close_time_ms
            candles=tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in path.candles_1h)
            windows.append(ComparativeMemberWindow(exchange_instrument_id=candidate,candles_1h=candles))
        projection=build_comparative_universe_projection(event_spec_id=spec.event_spec_id,universe_version_id=uid,
            strategy_group_id=group,exchange_instrument_ids=spec.candidate_ids,closed_bar_time_ms=close,
            lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,member_windows=tuple(windows)).model_copy(update={
                "comparison_transition_revision":current.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
        attempted=max(close+5,current.authority.created_at_ms+1)
        if index:
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+4)):
                unchanged=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                    request=CoordinateGenericSnapshotRequest(selection_snapshot_id=previous.selection_snapshot_id,worker_id="second-epoch-hourly-authority"),clock_ms=lambda close=close:close+4)
            assert unchanged.disposition is MaterializationDisposition.NO_CHANGE,unchanged
            async with PostgresKernelUnitOfWork(database) as uow:
                current=await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=attempted)):
            observed=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),Market(template,close),
                ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                    trigger_candle_close_time_ms=close,attempted_at_ms=attempted))
        assert observed.status is (ObservationStatus.SIGNAL_CREATED if index==2 else ObservationStatus.NO_SIGNAL),observed
        if index==0:
            assert observed.detector_reason=="COMPARISON_REBASE_REQUIRED",observed
    await _issue_and_dispatch_hourly_natural_entry(database,group=group,signal_event_id=observed.signal_event_id,
        selection_authority_id=current.authority.selection_authority_id,member=member,universe_version_id=uid,
        closed_at_ms=close,now_ms=attempted+1,fault_stage=None)
    return attempted+800


async def _issue_second_dynamic_noncomparative_trade(database, *, group):
    spec = inputs(group).spec
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        assert current.authority.authority_outcome in {"ACTIVE_NEW","NO_CHANGE"}
        uid = current.authority.event_binding.universe_version_id
        close = current.authority.first_eligible_close_time_ms
        assert uow._connection is not None
        scope_id,member = (await uow._connection.execute(sa.text("SELECT runtime_scope_id,exchange_instrument_id "
            "FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})).one()
    class Market:
        def __init__(self,template,at):
            self.template,self.delta=template,at-template.trigger_candle_close_time_ms
        async def fetch_closed_candles(self,request):
            candles=self.template.candles_1h if request.timeframe=="1h" else self.template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.delta,"close_time_ms":c.close_time_ms+self.delta}) for c in candles)
    for at,template in ((close,cpm_flat_snapshot()),(close+HOUR,cpm_long_snapshot() if group=="CPM-RO-001" else brf2_short_snapshot())):
        attempted = max(at+1,current.authority.created_at_ms+1)
        await make_warming_ready(database,universe_version_id=uid,warm_closed_bar_time_ms=at,valid_until_ms=at+HOUR)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=attempted)):
            observed=await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),Market(template,at),
                ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                    trigger_candle_close_time_ms=at,attempted_at_ms=attempted))
        assert observed.status is (ObservationStatus.NO_SIGNAL if at==close else ObservationStatus.SIGNAL_CREATED),observed
    await _issue_and_dispatch_hourly_natural_entry(database,group=group,signal_event_id=observed.signal_event_id,
        selection_authority_id=current.authority.selection_authority_id,member=member,universe_version_id=uid,
        closed_at_ms=close+HOUR,now_ms=close+HOUR+2,fault_stage=None)
    return close+HOUR+800


async def _issue_new_static_natural_trade(database, *, group,fault_stage=None):
    spec = inputs(group).spec
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.strategy_universes.get_current(spec.event_spec_id)
        proof = await uow.instrument_selection.get_generic_static_activation_proof_for_universe(current.universe_version_id)
        assert uow._connection is not None
        scope_id,member = (await uow._connection.execute(sa.text("SELECT runtime_scope_id,exchange_instrument_id "
            "FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":current.universe_version_id})).one()
    first_close = proof.first_eligible_close_time_ms
    class Market:
        def __init__(self,template,close):
            self.template,self.delta = template,close-template.trigger_candle_close_time_ms
        async def fetch_closed_candles(self,request):
            candles = self.template.candles_1h if request.timeframe=="1h" else self.template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+self.delta,"close_time_ms":c.close_time_ms+self.delta}) for c in candles)
    comparative = group in {"MPG-001","MI-001"}
    if comparative:
        trigger = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        flat = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        sequence = ((first_close,trigger),(first_close+HOUR,flat),(first_close+2*HOUR,trigger))
    else:
        sequence = ((first_close,cpm_flat_snapshot()),(first_close+HOUR,cpm_long_snapshot() if group=="CPM-RO-001" else brf2_short_snapshot()))
    for close,template in sequence:
        await make_warming_ready(database,universe_version_id=current.universe_version_id,warm_closed_bar_time_ms=close,valid_until_ms=close+HOUR)
        if comparative:
            async with PostgresKernelUnitOfWork(database) as uow:
                members = await uow.strategy_universes.get_members(current.universe_version_id)
            shift = close-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+shift,"close_time_ms":c.close_time_ms+shift}) for c in template.candles_1h)
            projection = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,universe_version_id=current.universe_version_id,
                strategy_group_id=group,exchange_instrument_ids=members,closed_bar_time_ms=close,
                lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in members)).model_copy(update={
                    "comparison_transition_revision":proof.comparison_transition_revision})
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(projection)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close+1)):
            observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),Market(template,close),
                ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                    trigger_candle_close_time_ms=close,attempted_at_ms=close+1))
        assert observed.status is (ObservationStatus.SIGNAL_CREATED if close==sequence[-1][0] else ObservationStatus.NO_SIGNAL),observed
        if comparative and close==first_close:
            assert observed.detector_reason=="RECOVERY_REBASE_REQUIRED",observed
    await _issue_and_dispatch_hourly_natural_entry(database,group=group,signal_event_id=observed.signal_event_id,
        selection_authority_id=None,member=member,universe_version_id=current.universe_version_id,
        closed_at_ms=sequence[-1][0],now_ms=sequence[-1][0]+2,fault_stage=fault_stage)
    async with database.connect() as conn:
        ticket_count = 1 if fault_stage in {"before_issue","between_claim_ticket"} else 2
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==ticket_count
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets WHERE status NOT IN ('terminal','entry_rejected')"))==0
        assert await conn.scalar(sa.text("SELECT count(DISTINCT exposure_episode_id) FROM brc_trade_tickets"))==ticket_count
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands WHERE command_kind='entry'"))==ticket_count
        assert await conn.scalar(sa.text("SELECT count(DISTINCT entry_exchange_order_id) FROM brc_trade_aggregates"))==(2 if fault_stage is None else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["MPG-001", "MI-001"])
async def test_first_activation_same_members_still_materializes_changed_comparison(database: AsyncEngine, group: str) -> None:
    await _exercise_generic_generation(database, group, True, durable=True, first_activation=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("group,failure_case,first_activation", [
    (group,case,False) for group in ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001") for case in ("timeout", "permanent", "expired")
] + [("CPM-RO-001","timeout",True),("MI-001","expired",True)])
async def test_generic_failure_releases_target_but_keeps_recovery_vacuum(database, group, failure_case, first_activation):
    await _exercise_generic_generation(database,group,False,failure_case=failure_case,first_activation=first_activation)


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("failed_first", [False,True])
async def test_new_empty_selection_supersedes_failed_generation_on_same_vacuum(database, group, failed_first):
    await _exercise_generic_generation(database,group,False,failure_case="timeout_then_empty" if failed_first else "staged_then_empty")


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_static_recovery_proposal_is_built_from_database_without_grant(database, group):
    await _exercise_generic_generation(database,group,False,failure_case="timeout_then_prepare",first_activation=True)


@pytest.mark.asyncio
async def test_recovered_entry_dispatch_rejects_changed_rebase_before_venue_call(database):
    await _exercise_generic_generation(database,"CPM-RO-001",False,failure_case="timeout_then_prepare_dispatch_refusal",first_activation=True)


async def _cutover_static_with_protected_ticket(database, *, group, ticket, at_ms, timeout=False, continuous=False,close_failure=False,normal_delay_ms=0):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericStaticRequest,
    )
    from src.trading_kernel.application.owner_control import (
        stage_generic_static_selection_mode,
    )
    from src.trading_kernel.domain.aggregate import AggregateStatus

    spec = inputs(group).spec
    ticket_id = ticket.identity.ticket_id
    async with PostgresKernelUnitOfWork(database) as uow:
        control = await uow.instrument_selection.get_selection_control(group)
        before = await uow.aggregates.get(ticket_id)
        frozen = await uow.tickets.get(ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket_id)
        baseline = await uow.instrument_selection.get_generic_static_rollback_baseline(control.rollback_baseline_id)
        cadence = spec.cadence_hours*HOUR
        anchor = (at_ms//cadence+1)*cadence
        await stage_generic_static_selection_mode(uow,strategy_group_id=group,
            rollback_baseline_id=baseline.rollback_baseline_id,selection_epoch_id=control.selection_epoch_id,
            effective_period_anchor_ms=anchor,authentication_strength="totp_step_up",
            request=ControlMutationRequest(expected_version=control.control_version,reason="static_cutover_with_protected_ticket",
                idempotency_key=f"static:protected:{group}",owner_identity="owner",now_ms=at_ms))
    assert before.status is AggregateStatus.POSITION_PROTECTED
    if continuous:
        async with PostgresKernelUnitOfWork(database) as uow:
            original = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
        assert group in {"MPG-001","MI-001"} and original.authority.expires_at_ms==anchor
        await make_warming_ready(database,universe_version_id=ticket.universe_version_id,
            warm_closed_bar_time_ms=anchor,valid_until_ms=anchor+2*HOUR)
        template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
        delta = anchor-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,
            universe_version_id=ticket.universe_version_id,strategy_group_id=group,exchange_instrument_ids=spec.candidate_ids,
            closed_bar_time_ms=anchor,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in spec.candidate_ids)).model_copy(update={
                "comparison_transition_revision":original.authority.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=anchor+1)):
            continued = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=CoordinateGenericPeriodRequest(strategy_group_id=group,selection_spec_id=spec.selection_spec_id,
                    period_anchor_ms=anchor-HOUR,worker_id="continuous-before-static"),clock_ms=lambda:anchor+1)
        assert continued.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY, continued
    request = CoordinateGenericStaticRequest(strategy_group_id=group,worker_id="protected-static-materializer")
    due = anchor+2*HOUR-10 if close_failure else anchor+HOUR+1
    staged_for_delay = False
    staged_fence = None
    for offset in range(12):
        tick = due+offset+(normal_delay_ms if staged_for_delay else 0)
        if close_failure:
            async with PostgresKernelUnitOfWork(database) as uow:
                pending = await uow.instrument_selection.get_generic_static_materialization_generation(
                    GenericStaticMaterializationGeneration.id_for_authorization((await uow.instrument_selection.get_selection_control(group)).pending_authorization_id))
                pre_current = await uow.strategy_universes.get_current(spec.event_spec_id)
                pre_authority = await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)
                pre_control = await uow.instrument_selection.get_selection_control(group)
                pre_vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=spec.selection_spec_id)
            if pending is not None and pending.lifecycle_state.value=="STAGED":
                crossed = anchor+2*HOUR
                assert crossed<tick+30000 and crossed<pending.fenced_at_ms+spec.materialization_timeout_ms
                reached = []
                async def commit_clock(repository,*,reached=reached,crossed=crossed,tick=tick):
                    current_control = await repository.get_selection_control(group)
                    if current_control.selection_mode.value=="static_baseline":
                        reached.append(current_control.control_version)
                        return crossed
                    return tick
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=commit_clock), pytest.raises(
                    UniverseInstallConflict,match="STATIC_ACTIVATION_COMMIT_CROSSED_CLOSE"):
                    await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda tick=tick:tick)
                assert reached==[pre_control.control_version+1]
                async with PostgresKernelUnitOfWork(database) as uow:
                    assert await uow.strategy_universes.get_current(spec.event_spec_id)==pre_current
                    assert await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id)==pre_authority
                    assert await uow.instrument_selection.get_selection_control(group)==pre_control
                    assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=spec.selection_spec_id)==pre_vacuum
                    assert await uow.instrument_selection.get_generic_static_materialization_generation(pending.materialization_generation_id)==pending
                    assert await uow.tickets.get(ticket_id)==frozen and await uow.aggregates.get(ticket_id)==before
                    assert await uow.budgets.get_for_ticket(ticket_id)==reservation
                    assert await uow.exchange_commands.list_for_ticket(ticket_id)==commands
                return crossed
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=tick)):
            outcome = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda tick=tick:tick)
        if normal_delay_ms and outcome.disposition is MaterializationDisposition.GENERATION_STAGED:
            staged_for_delay = True
            async with PostgresKernelUnitOfWork(database) as uow:
                staged_fence = (await uow.instrument_selection.get_generic_static_materialization_generation(outcome.materialization_generation_id)).fenced_at_ms
        async with PostgresKernelUnitOfWork(database) as uow:
            assert await uow.tickets.get(ticket_id)==frozen
            assert await uow.aggregates.get(ticket_id)==before
            assert await uow.budgets.get_for_ticket(ticket_id)==reservation
            assert await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
            assert await uow.exchange_commands.list_for_ticket(ticket_id)==commands
        if outcome.disposition is MaterializationDisposition.ACTIVE_NEW:
            break
        if outcome.materialization_generation_id is None:
            continue
        async with PostgresKernelUnitOfWork(database) as uow:
            targets = await uow.strategy_universes.get_generation_universe_targets(outcome.materialization_generation_id)
        if targets:
            target = targets[0]
            if timeout:
                async with PostgresKernelUnitOfWork(database) as uow:
                    generation = await uow.instrument_selection.get_generic_static_materialization_generation(outcome.materialization_generation_id)
                failed_at = generation.fenced_at_ms+spec.materialization_timeout_ms
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=failed_at)):
                    failed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda failed_at=failed_at:failed_at)
                assert failed.disposition is MaterializationDisposition.BLOCKED and failed.reason_code=="MATERIALIZATION_TIMEOUT"
                async with PostgresKernelUnitOfWork(database) as uow:
                    assert await uow.tickets.get(ticket_id)==frozen and await uow.aggregates.get(ticket_id)==before
                    assert await uow.budgets.get_for_ticket(ticket_id)==reservation
                    assert await uow.exchange_commands.list_for_ticket(ticket_id)==commands
                    assert await uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
                    vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=group,selection_spec_id=spec.selection_spec_id)
                    assert vacuum.blocks_new_entry and vacuum.resolved_at_ms is None
                    assert (await uow.strategy_universes.get_current(spec.event_spec_id)).universe_version_id==ticket.universe_version_id
                    assert (await uow.instrument_selection.get_selection_control(group)).selection_mode.value=="dynamic_selection"
                    assert (await uow.strategy_universes.get_generation_universe_targets(generation.materialization_generation_id))[0].lifecycle_state.value=="abandoned"
                return failed_at
            await make_warming_ready(database,universe_version_id=target.universe_version_id,
                warm_closed_bar_time_ms=anchor+HOUR,valid_until_ms=due+HOUR)
            if group in {"MPG-001","MI-001"}:
                async with PostgresKernelUnitOfWork(database) as uow:
                    members = await uow.strategy_universes.get_members(target.universe_version_id)
                template = mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
                delta = anchor+HOUR-template.trigger_candle_close_time_ms
                candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
                projection = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,
                    universe_version_id=target.universe_version_id,strategy_group_id=group,exchange_instrument_ids=members,
                    closed_bar_time_ms=anchor+HOUR,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
                    member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in members))
                async with PostgresKernelUnitOfWork(database) as uow:
                    await uow.strategy_universes.save_comparative_projection(projection)
    assert outcome.disposition is MaterializationDisposition.ACTIVE_NEW, outcome
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.strategy_universes.get_current(spec.event_spec_id)
        changed = await uow.instrument_selection.get_selection_control(group)
        assert current.universe_version_id!=ticket.universe_version_id
        assert changed.selection_mode.value=="static_baseline"
        assert await uow.instrument_selection.get_current_generic_authority(spec.selection_spec_id) is None
        proof = await uow.instrument_selection.get_generic_static_activation_proof(outcome.materialization_generation_id)
        if continuous:
            assert proof.transition_rule=="NORMAL_TRANSITION" and proof.recovery_reason is None
            assert proof.first_eligible_close_time_ms==anchor+HOUR and proof.first_eligible_close_time_ms<proof.prepared_at_ms
            assert proof.comparison_rebase_required and not proof.episode_rebase_required
            assert proof.source_selection_authority_id==continued.selection_authority_id
            if normal_delay_ms:
                assert proof.prepared_at_ms-proof.first_eligible_close_time_ms>=normal_delay_ms
                assert proof.materialization_started_at_ms==staged_fence==proof.fenced_at_ms
                assert proof.prepared_at_ms<staged_fence+spec.materialization_timeout_ms
    if continuous:
        close = proof.first_eligible_close_time_ms
        template = mpg_long_snapshot() if group=="MPG-001" else mi_long_snapshot()
        delta = close-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        async with PostgresKernelUnitOfWork(database) as uow:
            members = await uow.strategy_universes.get_members(current.universe_version_id)
            assert uow._connection is not None
            scope_id = await uow._connection.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current "
                "WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":current.universe_version_id})
        projection = build_comparative_universe_projection(event_spec_id=spec.event_spec_id,
            universe_version_id=current.universe_version_id,strategy_group_id=group,exchange_instrument_ids=members,
            closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,freshness_window_ms=HOUR,
            member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=member,candles_1h=candles) for member in members)).model_copy(update={
                "comparison_transition_revision":proof.comparison_transition_revision})
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
        class NormalStaticMarket:
            async def fetch_closed_candles(self,request):
                if request.timeframe=="1h":
                    return candles
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta})
                    for c in template.candles_4h)
        observed = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),NormalStaticMarket(),
            ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=close,attempted_at_ms=tick+1))
        assert observed.status is ObservationStatus.NO_SIGNAL, observed
        assert observed.detector_reason=="COMPARISON_REBASE_REQUIRED", observed
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT comparison_last_observed_at_ms FROM brc_exposure_episode_current "
                "WHERE event_spec_id=:event AND exchange_instrument_id=:member AND position_side='long'"),
                {"event":spec.event_spec_id,"member":members[0]})==close
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==1
            checkpoint_before = (await conn.execute(sa.text("SELECT comparison_checkpoint_version,comparison_last_observed_at_ms "
                "FROM brc_exposure_episode_current WHERE event_spec_id=:event AND exchange_instrument_id=:member AND position_side='long'"),
                {"event":spec.event_spec_id,"member":members[0]})).one()
        repeated = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),NormalStaticMarket(),
            ObservationRequest(runtime_scope_id=scope_id,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                trigger_candle_close_time_ms=close,attempted_at_ms=tick+2))
        assert repeated.status is not ObservationStatus.SIGNAL_CREATED
        async with database.connect() as conn:
            assert (await conn.execute(sa.text("SELECT comparison_checkpoint_version,comparison_last_observed_at_ms "
                "FROM brc_exposure_episode_current WHERE event_spec_id=:event AND exchange_instrument_id=:member AND position_side='long'"),
                {"event":spec.event_spec_id,"member":members[0]})).one()==checkpoint_before
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events"))==1
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),
            {"uid":ticket.universe_version_id})=="retired"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets"))==1
    return tick


async def _exercise_generic_generation(database, group, comparison_only, *, durable=False, first_activation=False, failure_case=None, natural_selection=False):
    source = inputs(group)
    if comparison_only:
        source = source.model_copy(update={"member_windows":tuple(qualify_window(
            w.model_copy(update={"candles":source.member_windows[0].candles}),w.exchange_instrument_id==source.spec.candidate_ids[0])
            for w in source.member_windows)})
    uid,comparison_id = await _install_static_selection_source(database,group)
    if first_activation and not natural_selection:
        async with PostgresKernelUnitOfWork(database) as uow:
            first_control = await stage_generic_dynamic_selection_mode(
                uow,strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
                request=ControlMutationRequest(expected_version=1,
                    reason="first_activation_fixture",idempotency_key=f"owner:fixture:first:{group}",
                    owner_identity="owner",now_ms=CUTOFF-1),
                authentication_strength="totp_step_up",
            )
        source = source.model_copy(update={"selection_epoch_id":first_control.selection_epoch_id})
    if natural_selection:
        assert first_activation and failure_case is None
        async with PostgresKernelUnitOfWork(database) as owner_uow:
            staged = await stage_generic_dynamic_selection_mode(owner_uow,
                strategy_group_id=group,effective_period_anchor_ms=CUTOFF,
                request=ControlMutationRequest(expected_version=1,
                    reason="natural_first_selection",idempotency_key=f"owner:natural:first:{group}",
                    owner_identity="owner",now_ms=CUTOFF-1),
                authentication_strength="totp_step_up")
        source = source.model_copy(update={"selection_epoch_id":staged.selection_epoch_id})

        class SelectionMarket:
            async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
                assert event_spec_id == source.spec.event_spec_id and len(product_profiles) == 24
                return tuple(member.qualification.model_copy(update={"observed_at_ms":observed_at_ms})
                    for member in source.member_windows)

            async def fetch_generic_selection_klines(self, request):
                return next(member.candles for member in source.member_windows
                    if member.exchange_instrument_id == request.exchange_instrument_id)

        tick = CUTOFF

        def selection_clock():
            nonlocal tick
            tick += 1
            return tick

        selected = await run_instrument_selection_once(
            uow_factory=lambda:PostgresKernelUnitOfWork(database),market_source=SelectionMarket(),
            request=RunInstrumentSelectionRequest(selection_spec_id=source.spec.selection_spec_id,
                selection_epoch_id=staged.selection_epoch_id,period_anchor_ms=CUTOFF,
                worker_id=f"natural-{group}-selector"),clock_ms=selection_clock)
        assert selected.outcome == "SNAPSHOT_READY"
        async with PostgresKernelUnitOfWork(database) as selection_uow:
            snapshot = await selection_uow.instrument_selection.get_generic_snapshot(selected.selection_snapshot_id)
            assert snapshot.selection_epoch_id == staged.selection_epoch_id
            assert len(snapshot.members) == 24
    else:
        snapshot = compute_generic_selection(source)
    if comparison_only:
        assert snapshot.selected_members == source.spec.candidate_ids[:1]
    async with PostgresKernelUnitOfWork(database) as uow:
        if not natural_selection:
            await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
    if not natural_selection and not first_activation:
        await enable_epoch(database, group, pending=first_activation)
    generation = GenericMaterializationGeneration.build(snapshot=snapshot, selection_control_version=2, created_at_ms=CUTOFF+HOUR+1,
        previous_events=(MaterializationEventBaseline(event_spec_id=source.spec.event_spec_id,position_side=source.spec.position_side,
            grant_state="ACTIVE",universe_version_id=uid,member_set_digest=selected_member_set_digest(source.spec.candidate_ids[:1]),
            comparison_universe_id=comparison_id,comparison_transition_revision=0 if comparison_id else None),))
    snapshot_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="snapshot-coordinator")
    early = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=snapshot_request,clock_ms=lambda:snapshot.effective_from_ms-1)
    assert early.disposition == MaterializationDisposition.NOT_DUE
    handed_off = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=snapshot_request,
        clock_ms=lambda:generation.created_at_ms)
    assert handed_off.disposition == MaterializationDisposition.GENERATION_PENDING
    assert handed_off.materialization_generation_id == generation.materialization_generation_id
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id) == generation
        assert await uow.instrument_selection.add_generic_pending_materialization_generation(generation) == generation
    async with database.connect() as conn:
        rows = (await conn.execute(sa.text("SELECT * FROM brc_materialization_generation_event_baselines"))).mappings().all()
        assert len(rows)==1 and rows[0]["event_spec_id"]==source.spec.event_spec_id
        assert rows[0]["universe_version_id"]==uid and rows[0]["comparison_universe_id"]==comparison_id
    with pytest.raises(sa.exc.DBAPIError, match="immutable"):
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_materialization_generation_event_baselines SET universe_version_id=:uid"), {"uid":uid})
    if group == "CPM-RO-001" and not first_activation:
        with pytest.raises(sa.exc.DBAPIError, match="Generation source identity is immutable"):
            async with database.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_strategy_universe_materialization_generations SET semantic_digest=:digest"), {"digest":"sha256:"+"b"*64})
        async with PostgresKernelUnitOfWork(database) as uow:
            first = await uow.instrument_selection.claim_generic_materialization_generation(generation.materialization_generation_id,
                worker_id="generic-worker",now_ms=generation.created_at_ms+1,lease_duration_ms=1000)
        assert first.status.value=="CLAIMED" and first.generation.lease_epoch==1
        async with PostgresKernelUnitOfWork(database) as uow:
            held = await uow.instrument_selection.claim_generic_materialization_generation(generation.materialization_generation_id,
                worker_id="generic-worker",now_ms=generation.created_at_ms+2,lease_duration_ms=1000)
        assert held.status.value=="LEASE_HELD"
        async with PostgresKernelUnitOfWork(database) as uow:
            reclaimed = await uow.instrument_selection.claim_generic_materialization_generation(generation.materialization_generation_id,
                worker_id="generic-worker",now_ms=generation.created_at_ms+1001,lease_duration_ms=1000)
        assert reclaimed.status.value=="CLAIMED" and reclaimed.generation.lease_epoch==2
        async with PostgresKernelUnitOfWork(database) as uow:
            assert not await uow.instrument_selection.release_generic_materialization_generation_lease(
                generation.materialization_generation_id,worker_id="generic-worker",lease_epoch=1)
            assert await uow.instrument_selection.release_generic_materialization_generation_lease(
                generation.materialization_generation_id,worker_id="generic-worker",lease_epoch=2)
        later_source = next_input(source)
        later_snapshot = compute_generic_selection(later_source)
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.save_generic_snapshot(later_snapshot,decision_at_ms=later_source.decision_at_ms,source_observed_at_ms=later_source.source_observed_at_ms)
        later = GenericMaterializationGeneration.build(snapshot=later_snapshot,previous_events=generation.previous_events,
            selection_control_version=2,created_at_ms=later_snapshot.effective_from_ms+1)
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict, match="outside eligible source period"):
                await uow.instrument_selection.claim_generic_materialization_generation(generation.materialization_generation_id,
                    worker_id="late-worker", now_ms=later.created_at_ms, lease_duration_ms=1000)
        invalid = later.model_copy(update={"previous_events":(later.previous_events[0].model_copy(update={"universe_version_id":"universe:not-current"}),)})
        async with PostgresKernelUnitOfWork(database) as uow:
            with pytest.raises(SelectionJobConflict, match="previous current Universe"):
                await uow.instrument_selection.add_generic_pending_materialization_generation(invalid)
        async with PostgresKernelUnitOfWork(database) as uow:
            untouched = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
            assert untouched.lifecycle_state.value=="PENDING"
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.add_generic_pending_materialization_generation(later)
        async with PostgresKernelUnitOfWork(database) as uow:
            retired = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
            assert retired.lifecycle_state.value=="SUPERSEDED"
            assert retired.previous_events==generation.previous_events
            assert retired.semantic_digest==generation.semantic_digest
        generation, snapshot = later, later_snapshot
    coordinator_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,
        worker_id="generic-coordinator")
    @asynccontextmanager
    async def transient_pause_probe():
        async with PostgresKernelUnitOfWork(database) as uow:
            assert uow._connection is not None
            probe = await uow._connection.begin_nested()
            await uow._connection.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id=:group"), {"group":group})
            yield uow
            await probe.rollback()
    paused = await coordinate_selection_materialization_once(uow_factory=transient_pause_probe,
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+1)
    assert paused.disposition == MaterializationDisposition.OWNER_PAUSED
    async with database.begin() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current")) == 0
    prepared = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+1)
    assert prepared.disposition == MaterializationDisposition.GENERATION_DESIRED
    async with PostgresKernelUnitOfWork(database) as uow:
        preparation = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="prepare-worker",
            now_ms=generation.created_at_ms+2,lease_duration_ms=HOUR//2)
    assert preparation.generation is not None
    held = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+2)
    assert held.disposition == MaterializationDisposition.GENERATION_LEASE_HELD
    assert held.reason_code == "GENERIC_GENERATION_LEASE_UNAVAILABLE"
    with pytest.raises(SelectionJobConflict, match="lease changed"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.mark_generic_materialization_generation_desired(
                generation.materialization_generation_id,worker_id="prepare-worker",
                lease_epoch=preparation.generation.lease_epoch+1,
                expected_projection_version=preparation.generation.projection_version,
                desired_at_ms=generation.created_at_ms+2)
    async with PostgresKernelUnitOfWork(database) as uow:
        desired = await uow.instrument_selection.mark_generic_materialization_generation_desired(
            generation.materialization_generation_id,worker_id="prepare-worker",
            lease_epoch=preparation.generation.lease_epoch,
            expected_projection_version=preparation.generation.projection_version,
            desired_at_ms=generation.created_at_ms+2)
    assert desired.lifecycle_state.value == "DESIRED"
    assert desired.desired_at_ms == generation.created_at_ms+1
    async with PostgresKernelUnitOfWork(database) as uow:
        repeated = await uow.instrument_selection.mark_generic_materialization_generation_desired(
            generation.materialization_generation_id,worker_id="prepare-worker",
            lease_epoch=preparation.generation.lease_epoch,
            expected_projection_version=preparation.generation.projection_version,
            desired_at_ms=generation.created_at_ms+3)
        assert repeated == desired
        fence = StrategyEntryVacuum(entry_vacuum_id="vacuum:"+generation.materialization_generation_id,
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,
            period_anchor_ms=generation.period_anchor_ms,source_generation_id=generation.materialization_generation_id,
            state="DRAINING_ENTRY",fenced_at_ms=generation.created_at_ms+3,drained_at_ms=None,resolved_at_ms=None,
            first_blocker="ENTRY_DRAIN_REQUIRED",projection_version=2)
        with pytest.raises(SelectionJobConflict, match="lease changed"):
            await uow.instrument_selection.open_generation_entry_vacuum(fence,
                expected_generation_version=desired.projection_version,
                worker_id="prepare-worker",lease_epoch=preparation.generation.lease_epoch+1)
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) is None
        assert await uow.instrument_selection.release_generic_materialization_generation_lease(
            generation.materialization_generation_id,worker_id="prepare-worker",lease_epoch=preparation.generation.lease_epoch)
    fenced = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+3)
    assert fenced.disposition == MaterializationDisposition.WAITING_VACUUM
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(
            strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id) == fence
        draining = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
        assert draining is not None and draining.lifecycle_state.value == "DRAINING_ENTRY"
        assert draining.fenced_at_ms == fence.fenced_at_ms
    # No ENTRY exists in this fixture; use the shared drain completion gate.
    async with PostgresKernelUnitOfWork(database) as uow:
        with pytest.raises(SelectionJobConflict, match="Vacuum.*changed"):
            await uow.instrument_selection.mark_entry_vacuum_drained(
                fence.model_copy(update={"first_blocker":"forged"}),
                target_state="RECONFIGURING",drained_at_ms=generation.created_at_ms+4)
    drained = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+4)
    assert drained.disposition == MaterializationDisposition.GENERATION_MATERIALIZING
    other_spec = inputs("MI-001" if group == "CPM-RO-001" else "CPM-RO-001").spec
    async with PostgresKernelUnitOfWork(database) as uow:
        occupying = await install_strategy_universe(uow,UniverseInstallRequest(
            event_spec_id=other_spec.event_spec_id,runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",
            exchange_instrument_ids=other_spec.candidate_ids[:1],installed_at_ms=generation.created_at_ms+4))
    assert occupying.universe is not None
    busy = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+5)
    assert busy.disposition == MaterializationDisposition.TARGET_WARMING
    assert busy.reason_code == "GLOBAL_WARMING_SLOT_BUSY"
    async with PostgresKernelUnitOfWork(database) as uow:
        await abandon_strategy_universe(uow,AbandonStrategyUniverseRequest(
            universe_version_id=occupying.universe.universe_version_id,reason_code="test_release_warming_slot",
            attempted_at_ms=generation.created_at_ms+5))
    if comparison_only:
        async with database.begin() as conn:
            await conn.execute(sa.text("CREATE FUNCTION reject_target_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected target failure'; END; $$"))
            await conn.execute(sa.text("CREATE TRIGGER reject_target_test BEFORE INSERT ON brc_strategy_universe_versions FOR EACH ROW WHEN (NEW.source_kind='dynamic_selection') EXECUTE FUNCTION reject_target_test()"))
        with pytest.raises(sa.exc.DBAPIError,match="injected target failure"):
            await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=coordinator_request,clock_ms=lambda:generation.created_at_ms+5)
        async with database.begin() as conn:
            assert await conn.scalar(sa.text("SELECT lease_owner FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=:gid"),{"gid":generation.materialization_generation_id}) is None
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_versions WHERE source_kind='dynamic_selection'")) == 0
            await conn.execute(sa.text("DROP TRIGGER reject_target_test ON brc_strategy_universe_versions"))
            await conn.execute(sa.text("DROP FUNCTION reject_target_test()"))
    warming = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+5)
    assert warming.disposition.value == "TARGET_WARMING"
    async with PostgresKernelUnitOfWork(database) as uow:
        target = await install_strategy_universe(uow, UniverseInstallRequest(
            event_spec_id=source.spec.event_spec_id,runtime_profile_id="tiny-live-v1",owner_policy_id="policy-main",
            exchange_instrument_ids=snapshot.selected_members,source_kind="dynamic_selection",
            materialization_generation_id=generation.materialization_generation_id,expected_member_set_digest=snapshot.member_set_digest,
            installed_at_ms=generation.created_at_ms+5))
        assert target.universe is not None and target.universe.exchange_instrument_ids==snapshot.selected_members
        assert target.lifecycle_state=="warming"
    if group in {"MPG-001","MI-001"}:
        # Real Observation must fetch all Candidate24, not the tradable target.
        template = mpg_long_snapshot() if group == "MPG-001" else mi_long_snapshot()
        close_at = snapshot.effective_from_ms
        offset = close_at - template.trigger_candle_close_time_ms

        class ComparisonMarket:
            def __init__(self, missing_member=None):
                self.hourly_members = []
                self.missing_member = missing_member

            async def fetch_closed_candles(self, request):
                if request.timeframe == "1h":
                    self.hourly_members.append(request.exchange_instrument_id)
                    if request.exchange_instrument_id == self.missing_member:
                        return ()
                candles = template.candles_1h if request.timeframe == "1h" else template.candles_4h
                return tuple(c.model_copy(update={
                    "open_time_ms": c.open_time_ms + offset,
                    "close_time_ms": c.close_time_ms + offset,
                }) for c in candles)[-request.limit:]

        async with database.connect() as conn:
            scope_ids = tuple((await conn.scalars(sa.text(
                "SELECT runtime_scope_id FROM brc_runtime_scopes_current "
                "WHERE universe_version_id=:uid ORDER BY runtime_scope_id"
            ), {"uid": target.universe.universe_version_id})).all())
        assert len(scope_ids) == len(snapshot.selected_members)
        scope_id = scope_ids[0]
        excluded = next(m for m in source.spec.candidate_ids if m not in snapshot.selected_members)
        request = ObservationRequest(runtime_scope_id=scope_id, runtime_commit="a"*40,
            schema_revision=CURRENT_SCHEMA_REVISION, trigger_candle_close_time_ms=close_at,
            attempted_at_ms=generation.created_at_ms+6)
        missing = await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(database), ComparisonMarket(excluded), request,
        )
        assert missing.status == ObservationStatus.INVALID
        async with database.connect() as conn:
            assert await conn.scalar(sa.text(
                "SELECT warm_closed_bar_time_ms FROM brc_runtime_scopes_current WHERE runtime_scope_id=:sid"
            ), {"sid": scope_id}) is None
        market = ComparisonMarket()
        observed = await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(database), market,
            request.model_copy(update={"attempted_at_ms": generation.created_at_ms+30_007}),
        )
        assert observed.status == ObservationStatus.WARMED, observed
        for other_scope_id in scope_ids[1:]:
            other = await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(database), market,
                request.model_copy(update={"runtime_scope_id": other_scope_id,
                    "attempted_at_ms": generation.created_at_ms+30_007}),
            )
            assert other.status == ObservationStatus.WARMED, other
        # All tradable scopes share one complete comparison fetch per close.
        assert tuple(sorted(market.hourly_members)) == source.spec.candidate_ids
        async with database.connect() as conn:
            for table in ("brc_signal_events", "brc_exposure_episode_current", "brc_trade_tickets", "brc_exchange_commands"):
                assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
            assert await conn.scalar(sa.text(
                "SELECT comparison_transition_revision FROM brc_comparison_binding_current WHERE event_spec_id=:event"
            ), {"event": source.spec.event_spec_id}) == 0
            assert await conn.scalar(sa.text(
                "SELECT source_static_universe_version_id FROM brc_comparison_binding_current WHERE event_spec_id=:event"
            ), {"event": source.spec.event_spec_id}) == uid
        # The synthetic cache-row checks below use another fixture timestamp.
        async with database.begin() as conn:
            await conn.execute(sa.text("DELETE FROM brc_comparative_projection_current"))
        await _assert_generic_target_stages(database, source, generation, target.universe.universe_version_id, durable=durable, failure_case=failure_case)
        if durable or failure_case:
            return (source, snapshot, generation, target.universe.universe_version_id) if durable and not failure_case else None
        candles = mpg_long_snapshot().candles_1h if group=="MPG-001" else mi_long_snapshot().candles_1h
        close = candles[-1].close_time_ms
        for members in (source.spec.candidate_ids,snapshot.selected_members):
            projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
                universe_version_id=target.universe.universe_version_id,strategy_group_id=group,
                exchange_instrument_ids=members,closed_bar_time_ms=close,lookback_bars=8 if group=="MPG-001" else 12,
                freshness_window_ms=3600000,member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in members))
            if len(members)==24:
                async with PostgresKernelUnitOfWork(database) as uow:
                    saved = await uow.strategy_universes.save_comparative_projection(projection)
                    assert len(saved.member_windows)==24
            else:
                with pytest.raises(ComparativeProjectionAuthorityChanged, match="member"):
                    async with PostgresKernelUnitOfWork(database) as uow:
                        await uow.strategy_universes.save_comparative_projection(projection)
        # Same membership after an authority transition must not revive an old fetch.
        static_projection = build_comparative_universe_projection(
            event_spec_id=source.spec.event_spec_id, universe_version_id=uid,
            strategy_group_id=group, exchange_instrument_ids=source.spec.candidate_ids[:1],
            closed_bar_time_ms=close, lookback_bars=8 if group=="MPG-001" else 12,
            freshness_window_ms=3600000, member_windows=(ComparativeMemberWindow(
                exchange_instrument_id=source.spec.candidate_ids[0], candles_1h=candles),),
        )
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(static_projection)
        async with database.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE brc_comparison_binding_current SET comparison_transition_revision=1 WHERE event_spec_id=:event"
            ), {"event": source.spec.event_spec_id})
        with pytest.raises(ComparativeProjectionAuthorityChanged, match="revision"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(static_projection)
        with pytest.raises(ComparativeProjectionAuthorityChanged, match="revision"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.get_comparative_projection(
                    event_spec_id=source.spec.event_spec_id, universe_version_id=uid,
                    member_set_digest=static_projection.member_set_digest,
                    closed_bar_time_ms=close,
                )
        stale_failure = build_comparative_projection_failure(
            event_spec_id=source.spec.event_spec_id, universe_version_id=uid,
            member_set_digest=static_projection.member_set_digest, closed_bar_time_ms=close,
            observed_at_ms=close, reason_code="comparative_market_temporarily_unavailable",
        )
        with pytest.raises(ComparativeProjectionAuthorityChanged, match="revision"):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection_failure(stale_failure)
        refreshed = static_projection.model_copy(update={"comparison_transition_revision": 1})
        async with PostgresKernelUnitOfWork(database) as uow:
            current_source = await uow.strategy_universes.get_comparative_source(
                event_spec_id=source.spec.event_spec_id, universe_version_id=uid,
            )
            assert current_source.comparison_transition_revision == 1
            saved = await uow.strategy_universes.save_comparative_projection(refreshed)
            assert saved.comparison_transition_revision == 1
            assert saved.projection_version == 2
    else:
        await _assert_generic_target_stages(database, source, generation, target.universe.universe_version_id, durable=durable, failure_case=failure_case)
        if durable or failure_case:
            return (source, snapshot, generation, target.universe.universe_version_id) if durable and not failure_case else None
    if comparison_only:
        with pytest.raises(sa.exc.DBAPIError,match="uq_brc_strategy_universe_versions_current_digest"):
            async with database.begin() as conn:
                original = (await conn.execute(sa.select(strategy_universe_versions).where(
                    strategy_universe_versions.c.universe_version_id == target.universe.universe_version_id))).mappings().one()
                await conn.execute(sa.insert(strategy_universe_versions).values(**{
                    **dict(original),"universe_version_id":"universe:duplicate-staged","universe_version":999,
                    "source_kind":"manual","materialization_generation_id":None}))
    with pytest.raises(sa.exc.DBAPIError, match="Universe trusted member limit"):
        async with database.begin() as conn:
            await conn.execute(sa.text("INSERT INTO brc_strategy_universe_members(universe_version_id,exchange_instrument_id) VALUES(:uid,:member)"),
                [{"uid":uid,"member":member} for member in source.spec.candidate_ids[1:11]])


async def _assert_generic_target_stages(database, source, generation, uid, *, durable=False, failure_case=None):
    # Certification/warm facts are explicit prerequisites. The caller already
    # drove Coordinator fence/drain; activation is checked by the helpers below.
    close = generation.created_at_ms - 1
    await make_warming_ready(database, universe_version_id=uid,
        warm_closed_bar_time_ms=close, valid_until_ms=close+HOUR)
    async with PostgresKernelUnitOfWork(database) as uow:
        lease = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="stage-worker",now_ms=close+10,lease_duration_ms=HOUR//4)
    assert lease.generation is not None
    request = UniverseActivationRequest(universe_version_id=uid, attempted_at_ms=close+30_004,
        operation=UniverseActivationOperation.STAGE_DYNAMIC,
        materialization_lease_owner="stage-worker", materialization_lease_epoch=lease.generation.lease_epoch,
        materialization_generation_id=generation.materialization_generation_id)
    async with PostgresKernelUnitOfWork(database) as uow:
        not_staged = await advance_strategy_universe(uow,request.model_copy(update={"operation":UniverseActivationOperation.CERTIFY_STAGED}))
        assert not_staged.reason_code == "STAGED_UNIVERSE_REQUIRED"
    async with PostgresKernelUnitOfWork(database) as uow:
        stale_lease = await advance_strategy_universe(uow, request.model_copy(update={"materialization_lease_epoch":lease.generation.lease_epoch+1}))
    assert stale_lease.reason_code == "DYNAMIC_GENERATION_LEASE_CHANGED"
    if source.spec.strategy_group_id in {"MPG-001", "MI-001"}:
        async with PostgresKernelUnitOfWork(database) as uow:
            missing = await advance_strategy_universe(uow, request)
        assert missing.status == UniverseActivationStatus.NOT_READY
        assert missing.reason_code == "COMPARATIVE_PROJECTION_INCOMPLETE"
        template = mpg_long_snapshot() if source.spec.strategy_group_id == "MPG-001" else mi_long_snapshot()
        delta = close-template.trigger_candle_close_time_ms
        candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
        projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,
            universe_version_id=uid, strategy_group_id=source.spec.strategy_group_id,
            exchange_instrument_ids=source.spec.candidate_ids, closed_bar_time_ms=close,
            lookback_bars=8 if source.spec.strategy_group_id=="MPG-001" else 12,
            freshness_window_ms=HOUR, member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in source.spec.candidate_ids))
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
    async with database.connect() as conn:
        previous = await conn.scalar(sa.text("SELECT universe_version_id FROM brc_strategy_universe_current WHERE event_spec_id=:event"), {"event":source.spec.event_spec_id})
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='temporarily_unavailable',blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"), {"uid":uid})
    async with PostgresKernelUnitOfWork(database) as uow:
        waiting = await advance_strategy_universe(uow, request)
    assert waiting.reason_code == "CERTIFICATION_TEMPORARILY_UNAVAILABLE"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=:gid"), {"gid":generation.materialization_generation_id}) == "MATERIALIZING"
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='eligible',blocker_code=NULL WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"), {"uid":uid})
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.release_generic_materialization_generation_lease(
            generation.materialization_generation_id,worker_id="stage-worker",lease_epoch=lease.generation.lease_epoch)
    coordinated = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=CoordinateGenericGenerationRequest(materialization_generation_id=generation.materialization_generation_id,
            worker_id="stage-coordinator"),clock_ms=lambda:close+30_004)
    assert coordinated.disposition == MaterializationDisposition.GENERATION_STAGED
    if failure_case == "staged_then_empty":
        async with PostgresKernelUnitOfWork(database) as uow:
            original = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
            vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id)
        await _assert_generic_empty_handoff(database,source,original,vacuum)
        return
    if failure_case:
        await _assert_generic_failed_target(database,source,generation,uid,failure_case)
        return
    if durable:
        await _assert_generic_durable_activation(database, source, generation, uid, close+30_004)
        return
    async with PostgresKernelUnitOfWork(database) as uow:
        lease = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="stage-worker",now_ms=close+30_004,
            lease_duration_ms=HOUR//4-29_994)
    assert lease.generation is not None
    request = request.model_copy(update={"materialization_lease_epoch":lease.generation.lease_epoch})
    async with PostgresKernelUnitOfWork(database) as uow:
        staged = await advance_strategy_universe(uow, request)
    assert staged.status == UniverseActivationStatus.STAGED
    certification = request.model_copy(update={"operation":UniverseActivationOperation.CERTIFY_STAGED})
    async with PostgresKernelUnitOfWork(database) as uow:
        assert (await advance_strategy_universe(uow,certification)).status == UniverseActivationStatus.STAGED
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='temporarily_unavailable',blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":uid})
    async with PostgresKernelUnitOfWork(database) as uow:
        failed = await advance_strategy_universe(uow,certification)
        assert failed.reason_code == "CERTIFICATION_TEMPORARILY_UNAVAILABLE"
    async with database.begin() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid}) == "staged"
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='eligible',blocker_code=NULL WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":uid})
    await _assert_generic_active_new_storage(database,source,generation,uid,close+30_004)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await advance_strategy_universe(uow, request) == staged
        lease_expired = await advance_strategy_universe(uow, request.model_copy(update={"attempted_at_ms":close+HOUR//4+11}))
        assert lease_expired.reason_code == "DYNAMIC_GENERATION_LEASE_CHANGED"
        expired = await advance_strategy_universe(uow, request.model_copy(update={"attempted_at_ms":close+source.spec.cadence_hours*HOUR}))
        assert expired.reason_code == "GENERATION_SOURCE_PERIOD_EXPIRED"
    async with PostgresKernelUnitOfWork(database) as uow:
        reclaimed = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id, worker_id="stage-worker",
            now_ms=close+HOUR//4+12, lease_duration_ms=60_000)
    assert reclaimed.generation is not None
    assert reclaimed.generation.lease_epoch == lease.generation.lease_epoch + 1
    callback = request.model_copy(update={"attempted_at_ms":close+HOUR//4+13})
    async with PostgresKernelUnitOfWork(database) as uow:
        assert (await advance_strategy_universe(uow, callback)).reason_code == "DYNAMIC_GENERATION_LEASE_CHANGED"
        assert await advance_strategy_universe(uow, callback.model_copy(update={"materialization_lease_epoch":reclaimed.generation.lease_epoch})) == staged
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=:gid"), {"gid":generation.materialization_generation_id}) == "STAGED"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND (entry_enabled OR observation_enabled)"), {"uid":uid}) == 0
        assert await conn.scalar(sa.text("SELECT universe_version_id FROM brc_strategy_universe_current WHERE event_spec_id=:event"), {"event":source.spec.event_spec_id}) == previous
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid AND event_type='STAGED'"), {"gid":generation.materialization_generation_id}) == 1
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_selection_control_current SET control_version=control_version+1 WHERE selection_spec_id=:spec"), {"spec":source.spec.selection_spec_id})
    async with PostgresKernelUnitOfWork(database) as uow:
        stale = await advance_strategy_universe(uow, request)
    assert stale.reason_code == "DYNAMIC_GENERATION_CONTROL_CHANGED"


async def _assert_generic_failed_target(database, source, generation, uid, failure_case):
    async with PostgresKernelUnitOfWork(database) as uow:
        staged = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
        control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
    assert staged is not None and staged.fenced_at_ms is not None
    deadline = staged.fenced_at_ms+source.spec.materialization_timeout_ms
    request = CoordinateGenericGenerationRequest(materialization_generation_id=staged.materialization_generation_id,worker_id="failure-coordinator")
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='temporarily_unavailable',blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":uid})
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=deadline-1)):
        waiting = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:deadline-1)
    assert waiting.disposition == MaterializationDisposition.TARGET_WARMING
    async with PostgresKernelUnitOfWork(database) as uow:
        retried = await uow.instrument_selection.get_generic_materialization_generation(staged.materialization_generation_id)
        assert retried.fenced_at_ms == staged.fenced_at_ms and retried.created_at_ms == staged.created_at_ms
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=deadline-1)):
        async with PostgresKernelUnitOfWork(database) as uow:
            premature = await uow.instrument_selection.claim_generic_materialization_generation(staged.materialization_generation_id,
                worker_id="premature-timeout",now_ms=deadline-1,lease_duration_ms=30_000)
            assert premature.generation is not None
            with pytest.raises(SelectionJobConflict,match="deadline has not elapsed"):
                await uow.instrument_selection.fail_generic_materialization_generation(staged.materialization_generation_id,
                    expected_projection_version=premature.generation.projection_version,worker_id="premature-timeout",
                    lease_epoch=premature.generation.lease_epoch,reason_code="MATERIALIZATION_TIMEOUT")
            await uow.instrument_selection.release_generic_materialization_generation_lease(staged.materialization_generation_id,
                worker_id="premature-timeout",lease_epoch=premature.generation.lease_epoch)
    at = deadline
    reason = "MATERIALIZATION_TIMEOUT"
    if failure_case == "permanent":
        at = deadline-1
        reason = "CERTIFICATION_OWNER_ACTION_REQUIRED"
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status='owner_action_required',blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"),{"uid":uid})
    elif failure_case == "expired":
        at = staged.period_anchor_ms+(source.spec.cadence_hours+1)*HOUR
        reason = "MATERIALIZATION_PERIOD_EXPIRED"
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)), pytest.raises(SelectionJobConflict,match="lease/state changed"):
        async with PostgresKernelUnitOfWork(database) as uow:
            await uow.instrument_selection.fail_generic_materialization_generation(staged.materialization_generation_id,
                expected_projection_version=staged.projection_version,worker_id="wrong-worker",lease_epoch=staged.lease_epoch,
                reason_code=reason)

    @asynccontextmanager
    async def interrupted_failure():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            failed_state = await uow.instrument_selection.get_generic_materialization_generation(staged.materialization_generation_id)
            assert failed_state.lifecycle_state.value == "FAILED_CLOSED"
            raise RuntimeError("failure handoff interrupted")

    with pytest.raises(RuntimeError,match="failure handoff interrupted"), patch.object(
        PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
        await coordinate_selection_materialization_once(uow_factory=interrupted_failure,request=request,clock_ms=lambda:at)
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid}) == "staged"
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=:gid"),{"gid":staged.materialization_generation_id}) == "STAGED"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid AND event_type='FAILED_CLOSED'"),{"gid":staged.materialization_generation_id}) == 0
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=at)):
        failed = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at)
    assert failed.disposition == MaterializationDisposition.BLOCKED and failed.reason_code == reason
    await database.dispose()
    async with PostgresKernelUnitOfWork(database) as uow:
        persisted = await uow.instrument_selection.get_generic_materialization_generation(staged.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id)
        assert persisted.lifecycle_state.value == "FAILED_CLOSED" and persisted.terminal_at_ms == at and persisted.lease_owner is None
        assert vacuum.state.value == "RECONFIGURING" and vacuum.first_blocker == reason
        assert vacuum.fenced_at_ms == staged.fenced_at_ms and vacuum.resolved_at_ms is None
        assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == control
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
        current = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        assert current.universe_version_id == staged.previous_events[0].universe_version_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid}) == "abandoned"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_versions WHERE lifecycle_state IN ('warming','staged')")) == 0
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    repeated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:at+1)
    assert repeated.disposition == MaterializationDisposition.BLOCKED and repeated.reason_code == reason
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid AND event_type='FAILED_CLOSED'"),{"gid":staged.materialization_generation_id}) == 1
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_runtime_scopes_current WHERE universe_version_id=:uid AND (entry_enabled OR observation_enabled)"),{"uid":uid}) == 0
    if failure_case == "timeout_then_empty":
        await _assert_generic_empty_handoff(database,source,persisted,vacuum)
    if failure_case.startswith("timeout_then_prepare"):
        previous_uid = persisted.previous_events[0].universe_version_id
        now = at+1
        close = now//HOUR*HOUR
        await make_warming_ready(database,universe_version_id=previous_uid,warm_closed_bar_time_ms=close,valid_until_ms=now+HOUR)
        async with database.begin() as conn:
            await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true WHERE owner_policy_id='policy-main'"))
        if source.spec.strategy_group_id in {"MPG-001","MI-001"}:
            template = mpg_long_snapshot() if source.spec.strategy_group_id=="MPG-001" else mi_long_snapshot()
            delta = close-template.trigger_candle_close_time_ms
            candles = tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in template.candles_1h)
            members = source.spec.candidate_ids[:1]
            projection = build_comparative_universe_projection(event_spec_id=source.spec.event_spec_id,universe_version_id=previous_uid,
                strategy_group_id=source.spec.strategy_group_id,exchange_instrument_ids=members,closed_bar_time_ms=close,
                lookback_bars=8 if source.spec.strategy_group_id=="MPG-001" else 12,freshness_window_ms=HOUR,
                member_windows=tuple(ComparativeMemberWindow(exchange_instrument_id=m,candles_1h=candles) for m in members))
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.strategy_universes.save_comparative_projection(projection)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
            async with PostgresKernelUnitOfWork(database) as uow:
                proposal = await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)
                assert proposal.selection_mode == "static_baseline"
                assert proposal.first_eligible_close_time_ms > now
                assert proposal.event_binding.universe_version_id == previous_uid
                assert proposal.failed_activation_authorization_id == control.pending_authorization_id
                assert proposal.selection_control_version == control.control_version+1
                assert uow._connection is not None
                recovery_savepoint = await uow._connection.begin_nested()
                recovered = await uow.instrument_selection.commit_generic_recovery(proposal)
                await uow._connection.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                committed = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
                assert committed is not None and committed.authority == recovered
                recovered_control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
                assert recovered_control.selection_mode.value == "static_baseline"
                assert recovered_control.pending_selection_mode is None and recovered_control.selection_epoch_id is None
                assert recovered_control.control_version == proposal.selection_control_version
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,
                    selection_spec_id=source.spec.selection_spec_id) is None
                for cursor in proposal.observation_cursors:
                    checkpoint = await uow.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
                    assert checkpoint is not None and checkpoint.state == "REBASE_REQUIRED"
                await recovery_savepoint.rollback()
                for broken in (
                    "DELETE FROM brc_selection_authority_current WHERE selection_spec_id=:spec",
                    "UPDATE brc_strategy_selection_control_current SET control_version=control_version+1 WHERE selection_spec_id=:spec",
                    "UPDATE brc_strategy_entry_vacuums_current SET state='RECONFIGURING',resolved_at_ms=NULL WHERE selection_spec_id=:spec",
                    "DELETE FROM brc_exposure_episode_current WHERE episode_domain_key=:key",
                ):
                    with pytest.raises(sa.exc.DBAPIError,match="Static recovery requires"):
                        async with uow._connection.begin_nested():
                            await uow._connection.execute(sa.text("SET CONSTRAINTS ALL DEFERRED"))
                            await uow.instrument_selection.commit_generic_recovery(proposal)
                            await uow._connection.execute(sa.text(broken),{"spec":source.spec.selection_spec_id,"key":proposal.observation_cursors[0].episode_domain_key})
                            await uow._connection.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
                assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == control
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,
                    selection_spec_id=source.spec.selection_spec_id) == vacuum
                if source.spec.strategy_group_id in {"MPG-001","MI-001"}:
                    with pytest.raises(sa.exc.DBAPIError,match="unchanged comparison"):
                        async with uow._connection.begin_nested():
                            await uow._connection.execute(sa.text("SET CONSTRAINTS ALL DEFERRED"))
                            await uow.instrument_selection.commit_generic_recovery(proposal)
                            await uow._connection.execute(sa.text("UPDATE brc_comparison_binding_current SET comparison_transition_revision=comparison_transition_revision+1 WHERE event_spec_id=:event"),{"event":source.spec.event_spec_id})
                            await uow._connection.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                assert uow._connection is not None
                sql_check = sa.text("SELECT brc_generic_static_recovery_proof_matches(CAST(:proof AS jsonb),:at)")
                assert await uow._connection.scalar(sql_check,{"proof":proposal.model_dump_json(),"at":now}) is True
                for mutation in ({"observation_cursors":[]},{"selection_control_version":999},
                                 {"vacuum_fenced_at_ms":proposal.vacuum_fenced_at_ms-1},
                                 {"source_entry_vacuum_id":"wrong"},{"unexpected_field":True},{"committed_at_ms":"not-ms"},
                                 {"recovery_close_plan":{**proposal.recovery_close_plan.model_dump(mode="json"),"reason":"UNPROVEN_CRASH_CONTINUITY"}}):
                    assert await uow._connection.scalar(sql_check,{"proof":json.dumps({**proposal.model_dump(mode="json"),**mutation}),"at":now}) is False
                assert await uow._connection.scalar(sql_check,{"proof":proposal.model_dump_json(),"at":proposal.first_eligible_close_time_ms}) is False
                assert await uow.instrument_selection.require_generic_recovery_grant_proof(proposal) == now
                for mutation in ({"owner_control_version":proposal.owner_control_version+1},
                                 {"selection_control_version":proposal.selection_control_version+1},
                                 {"source_entry_vacuum_id":"vacuum:forged"},
                                 {"vacuum_fenced_at_ms":proposal.vacuum_fenced_at_ms-1}):
                    with pytest.raises(SelectionJobConflict,match="recovery proof changed"):
                        await uow.instrument_selection.require_generic_recovery_grant_proof(proposal.model_copy(update=mutation))
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=now+1)):
                    assert await uow.instrument_selection.require_generic_recovery_grant_proof(proposal) == now+1
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=now-1)), pytest.raises(ValueError,match="backwards"):
                    await uow.instrument_selection.require_generic_recovery_grant_proof(proposal)
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=persisted.terminal_at_ms-1)), pytest.raises(SelectionJobConflict,match="failure time"):
                    await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=proposal.first_eligible_close_time_ms)), pytest.raises(ValueError,match="boundary"):
                    await uow.instrument_selection.require_generic_recovery_grant_proof(proposal)
                assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == control
                assert await uow.instrument_selection.get_generic_materialization_generation(persisted.materialization_generation_id) == persisted
                assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id) == vacuum
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
                assert uow._connection is not None
                for sql, params, reason in (
                    ("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id=:group",{"group":source.spec.strategy_group_id},"Owner Control"),
                    ("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=false WHERE owner_policy_id='policy-main'",{},"Policy"),
                    ("UPDATE brc_strategy_selection_control_current SET control_version=control_version+1 WHERE strategy_group_id=:group",{"group":source.spec.strategy_group_id},"Control"),
                    ("UPDATE brc_strategy_entry_controls_current SET updated_at_ms=:future WHERE strategy_group_id=:group",{"group":source.spec.strategy_group_id,"future":now+1},"control time"),
                    ("UPDATE brc_instrument_certification_current SET status='temporarily_unavailable',blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id=:member",{"member":source.spec.candidate_ids[0]},"not ready"),
                ):
                    savepoint = await uow._connection.begin_nested()
                    await uow._connection.execute(sa.text(sql),params)
                    if reason != "not ready":
                        assert await uow._connection.scalar(sql_check,{"proof":proposal.model_dump_json(),"at":now}) is False
                    with pytest.raises(SelectionJobConflict,match=reason):
                        await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)
                    with pytest.raises(SelectionJobConflict,match=reason):
                        await uow.instrument_selection.require_generic_recovery_grant_proof(proposal)
                    await savepoint.rollback()
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(side_effect=[now,proposal.first_eligible_close_time_ms])), pytest.raises(ValueError,match="boundary"):
                    await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)
                savepoint = await uow._connection.begin_nested()
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(side_effect=[now,now,now,proposal.first_eligible_close_time_ms])), pytest.raises(ValueError,match="boundary"):
                    await uow.instrument_selection.initialize_generic_recovery_checkpoints(proposal)
                for cursor in proposal.observation_cursors:
                    assert await uow.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key) is None

                newer_source = next_input(source)
                newer_source = newer_source.model_copy(update={"member_windows":tuple(qualify_window(w,False) for w in newer_source.member_windows)})
                newer = compute_generic_selection(newer_source)
                await uow.instrument_selection.save_generic_snapshot(newer,decision_at_ms=newer_source.decision_at_ms,
                    source_observed_at_ms=newer_source.source_observed_at_ms)
                # A committed future Desired cannot displace the current
                # recovery early; once due, newest Selection takes priority.
                assert await uow.instrument_selection.require_generic_recovery_grant_proof(proposal) == now
                with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(return_value=newer.effective_from_ms+1)), pytest.raises(SelectionJobConflict,match="newer effective Selection"):
                    await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)

                for detector_status in (DetectorStatus.NOT_TRIGGERED,DetectorStatus.TRIGGERED):
                    existing_savepoint = await uow._connection.begin_nested()
                    member = proposal.observation_cursors[0].exchange_instrument_id
                    observed = (proposal.vacuum_fenced_at_ms//HOUR)*HOUR
                    existing_episode = advance_exposure_episode(contract=strategy_contract_for(source.spec.event_spec_id),current=None,
                        detector_status=detector_status,occurred_at_ms=observed if detector_status is DetectorStatus.TRIGGERED else None,
                        observed_at_ms=observed,exchange_instrument_id=member).current
                    await uow.signals.save_exposure_episode(existing_episode,expected_version=0)
                    refreshed = await uow.instrument_selection.prepare_generic_recovery_grant_proof(persisted.materialization_generation_id)
                    with pytest.raises(SelectionJobConflict,match="recovery proof changed"):
                        await uow.instrument_selection.initialize_generic_recovery_checkpoints(proposal)
                    checkpoints = await uow.instrument_selection.initialize_generic_recovery_checkpoints(refreshed)
                    assert await uow.signals.lock_exposure_episode(existing_episode.episode_domain_key) == existing_episode
                    assert checkpoints[0].state == "REBASE_REQUIRED" and checkpoints[0].armed_at_close_time_ms is None
                    assert checkpoints[0].last_detector_status is None
                    assert checkpoints[0].last_observed_close_time_ms == observed
                    assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
                    await existing_savepoint.rollback()
                initialized = await uow.instrument_selection.initialize_generic_recovery_checkpoints(proposal)
                assert len(initialized) == len(proposal.observation_cursors)
                for checkpoint in initialized:
                    assert checkpoint.state == "REBASE_REQUIRED"
                    assert checkpoint.last_detector_status is None and checkpoint.last_observed_close_time_ms is None
                    assert await uow.signals.get_authority_recovery_checkpoint(checkpoint.episode_domain_key) == checkpoint
                    episode = await uow.signals.lock_exposure_episode(checkpoint.episode_domain_key)
                    assert episode.state == "authority_rebase_required" and episode.last_observed_at_ms is None
                    assert episode.exposure_episode_id is None
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
                assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == control
                await savepoint.rollback()
                for cursor in proposal.observation_cursors:
                    assert await uow.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key) is None
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
            coordinated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),
                request=request,clock_ms=lambda:now)
        assert coordinated.disposition == MaterializationDisposition.FALLBACK_PREVIOUS
        async with PostgresKernelUnitOfWork(database) as recovery_uow:
            committed_current = await recovery_uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            assert committed_current is not None
            committed_recovery = committed_current.authority
            assert coordinated.selection_authority_id == committed_recovery.selection_authority_id
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now+1)):
            retried_coordinator = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=request,clock_ms=lambda:now+1)
        assert retried_coordinator.selection_authority_id == coordinated.selection_authority_id
        await database.dispose()
        async with PostgresKernelUnitOfWork(database) as restarted:
            current = await restarted.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            assert current is not None and current.authority == committed_recovery
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now+1)):
                repeated_recovery = await restarted.instrument_selection.commit_generic_recovery(committed_recovery.recovery_proof)
            assert repeated_recovery == committed_recovery
            if source.spec.strategy_group_id in {"MPG-001","MI-001"}:
                assert restarted._connection is not None
                checkpoint = await restarted._connection.begin_nested()
                await restarted._connection.execute(sa.text("UPDATE brc_comparison_binding_current SET comparison_transition_revision=comparison_transition_revision+1 WHERE event_spec_id=:event"),{"event":source.spec.event_spec_id})
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now+1)), pytest.raises(SelectionJobConflict,match="comparison changed"):
                    await restarted.instrument_selection.commit_generic_recovery(committed_recovery.recovery_proof)
                await checkpoint.rollback()
            with pytest.raises(SelectionJobConflict,match="idempotency"):
                await restarted.instrument_selection.commit_generic_recovery(committed_recovery.recovery_proof.model_copy(update={"owner_control_version":999}))
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=committed_recovery.expires_at_ms)), pytest.raises(SelectionJobConflict,match="idempotency"):
                await restarted.instrument_selection.commit_generic_recovery(committed_recovery.recovery_proof)
            for cursor in proposal.observation_cursors:
                checkpoint = await restarted.signals.get_authority_recovery_checkpoint(cursor.episode_domain_key)
                assert checkpoint is not None and checkpoint.state == "REBASE_REQUIRED"
            assert await restarted.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,
                selection_spec_id=source.spec.selection_spec_id) is None
        async with database.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid AND event_type='STATIC_RECOVERY_COMMITTED'"),{"gid":persisted.materialization_generation_id}) == 1
            recovery_scope = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":previous_uid})
        first_close = committed_recovery.first_eligible_close_time_ms
        if source.spec.strategy_group_id == "CPM-RO-001":
            for offset, template, expected_status in ((0,cpm_long_snapshot(),ObservationStatus.NO_SIGNAL),
                (1,cpm_flat_snapshot(),ObservationStatus.NO_SIGNAL),(2,cpm_long_snapshot(),ObservationStatus.SIGNAL_CREATED)):
                observation_close = first_close+offset*HOUR
                delta = observation_close-template.trigger_candle_close_time_ms
                class RecoveryMarket:
                    async def fetch_closed_candles(self, request, template=template, delta=delta):
                        candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                        return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=observation_close+1)):
                    result = await observe_strategy_scope(lambda:PostgresKernelUnitOfWork(database),RecoveryMarket(),
                        ObservationRequest(runtime_scope_id=recovery_scope,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                            trigger_candle_close_time_ms=observation_close,attempted_at_ms=observation_close+1))
                assert result.status == expected_status, result
                if offset == 0:
                    assert result.detector_reason == "RECOVERY_REBASE_REQUIRED"
            async with database.connect() as conn:
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 1
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
            from src.trading_kernel.application.issue_ready_signal import (
                IssueReadySignalRequest,
                issue_ready_signal,
            )
            from src.trading_kernel.domain.cross_margin_stress import (
                AccountRiskSnapshot,
                MaintenanceMarginBracket,
            )
            from src.trading_kernel.domain.entry_admission_snapshot import (
                EntryAdmissionSnapshot,
            )
            issued_at = first_close+2*HOUR+2
            # Refresh explicit readonly certification prerequisites at action
            # time; an expired setup certification is not Entry authority.
            await make_warming_ready(database,universe_version_id=previous_uid,
                warm_closed_bar_time_ms=first_close+2*HOUR,valid_until_ms=issued_at+60_000)
            admission = EntryAdmissionSnapshot(account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id="binance-usdm",account_id="generic-snapshot",account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",position_mode="independent_sides",margin_mode="cross",
                exchange_instrument_id=proposal.observation_cursors[0].exchange_instrument_id,mark_price=Decimal(105),configured_leverage=5,
                total_wallet_balance=Decimal(1000),total_margin_balance=Decimal(1000),total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),available_margin=Decimal(1000),account_positions=(),observed_at_ms=issued_at,valid_until_ms=issued_at+60_000),
                best_bid_price=Decimal("104.99"),best_ask_price=Decimal(105),open_orders=(),observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
            async with PostgresKernelUnitOfWork(database) as admission_uow:
                brackets = (MaintenanceMarginBracket(bracket_id="recovery-test:1",notional_floor=Decimal(0),notional_cap=Decimal(20_000),
                    maintenance_margin_rate=Decimal("0.005"),maintenance_amount=Decimal(0)),)
                await admission_uow.signals.upsert_instrument_rules(venue_id="binance-usdm",exchange_instrument_id=proposal.observation_cursors[0].exchange_instrument_id,
                    quantity_step=Decimal("0.001"),price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),min_notional=Decimal(5),exchange_max_leverage=5,
                    maintenance_margin_brackets=brackets,maintenance_margin_brackets_digest=canonical_digest(brackets),
                    notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                    observed_at_ms=issued_at,valid_until_ms=issued_at+60_000)
                issue_request = IssueReadySignalRequest(signal_event_id=result.signal_event_id,
                    admission_snapshot=admission,claim_owner="recovery-entry",runtime_commit="a"*40,
                    schema_revision=CURRENT_SCHEMA_REVISION,now_ms=issued_at)
                assert admission_uow._connection is not None
                fault = await admission_uow._connection.begin_nested()
                await admission_uow._connection.execute(sa.text("UPDATE brc_exposure_episode_current SET authority_recovery_revision=authority_recovery_revision+1 WHERE episode_domain_key=:key"),{"key":proposal.observation_cursors[0].episode_domain_key})
                refused = await issue_ready_signal(admission_uow,issue_request)
                assert refused.status.value == "selection_authority_invalid", refused
                assert await admission_uow._connection.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
                assert await admission_uow._connection.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
                await fault.rollback()
                issued = await issue_ready_signal(admission_uow,issue_request)
            assert issued.status.value == "issued", issued
            async with PostgresKernelUnitOfWork(database) as lineage_uow:
                ticket = await lineage_uow.tickets.get(issued.ticket_id)
                claim = await lineage_uow.capacity_claims.get_for_signal(result.signal_event_id)
                decision = await lineage_uow.admission_decisions.get_for_signal(result.signal_event_id)
                assert ticket.selection_authority_id == committed_recovery.selection_authority_id
                assert claim.selection_authority_id == ticket.selection_authority_id
                assert decision.selection_authority_id == ticket.selection_authority_id
                assert ticket.identity.signal_event_id == result.signal_event_id
                assert decision.ticket_id == issued.ticket_id and decision.decision_status.value == "admitted"
            async with database.connect() as conn:
                commands = (await conn.execute(sa.text("SELECT * FROM brc_exchange_commands WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})).mappings().all()
                assert len(commands) == 1 and commands[0]["command_kind"] == "entry"
                assert commands[0]["status"] == "prepared"
            from src.trading_kernel.application.dispatch_exchange_command import (
                DispatchCommandRequest,
                dispatch_one_command,
            )
            from src.trading_kernel.application.runtime_facts import (
                InstrumentRulesFacts,
            )
            from src.trading_kernel.domain.commands import (
                ExchangeCommandResult,
                ExchangeCommandStatus,
            )
            class RecoveryEntryFacts:
                async def read_entry_admission_snapshot(self, request):
                    risk = AccountRiskSnapshot.create(**{**admission.account_risk_snapshot.model_dump(exclude={"snapshot_digest"}),
                        "observed_at_ms":request.observed_at_ms,"valid_until_ms":request.observed_at_ms+request.valid_for_ms})
                    return admission.model_copy(update={"account_risk_snapshot":risk,"observed_at_ms":request.observed_at_ms,
                        "valid_until_ms":request.observed_at_ms+request.valid_for_ms})

                async def read_instrument_rules(self, request):
                    return InstrumentRulesFacts(exchange_instrument_id=request.exchange_instrument_id,quantity_step=Decimal("0.001"),
                        price_tick=Decimal("0.01"),min_quantity=Decimal("0.001"),min_notional=Decimal(5),exchange_max_leverage=5,
                        maintenance_margin_brackets=brackets,maintenance_margin_brackets_digest=canonical_digest(brackets),
                        notional_coefficient=Decimal(1),notional_coefficient_certified=True,
                        observed_at_ms=request.observed_at_ms,valid_until_ms=request.observed_at_ms+request.valid_for_ms)
            class RecoveryVenue:
                def __init__(self):
                    self.calls = []
                    self.observed_at_ms = issued_at + 6

                async def execute(self, request):
                    async with PostgresKernelUnitOfWork(database) as durable_uow:
                        durable = await durable_uow.exchange_commands.get(request.command_id)
                        assert durable.status is ExchangeCommandStatus.CLAIMED
                    self.calls.append(request)
                    return ExchangeCommandResult(status=ExchangeCommandStatus.ACCEPTED,observed_at_ms=self.observed_at_ms,exchange_order_id=f"recovery-{request.kind.value}-{len(self.calls)}")
            async with database.begin() as conn:
                # Local capability prerequisite only; no production promotion.
                await conn.execute(sa.text("UPDATE brc_runtime_capabilities_current SET enabled=true WHERE capability_key='exchange_commands'"))
            venue = RecoveryVenue()
            if failure_case.endswith("dispatch_refusal"):
                async with database.begin() as conn:
                    await conn.execute(sa.text("UPDATE brc_exposure_episode_current SET authority_recovery_revision=authority_recovery_revision+1 WHERE episode_domain_key=:key"),{"key":proposal.observation_cursors[0].episode_domain_key})
            dispatched = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                DispatchCommandRequest(worker_id="recovery-dispatch",ticket_id=issued.ticket_id,now_ms=issued_at+5,
                    lease_until_ms=issued_at+30_000,timeout_seconds=1,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                    admission_snapshot_validity_ms=60_000),entry_facts_source=RecoveryEntryFacts())
            if failure_case.endswith("dispatch_refusal"):
                assert dispatched.status.value == "superseded", dispatched
                assert venue.calls == []
                async with database.connect() as conn:
                    row = (await conn.execute(sa.text("SELECT status,result_payload FROM brc_exchange_commands WHERE ticket_id=:ticket"),{"ticket":issued.ticket_id})).mappings().one()
                    assert row["status"] == "rejected"
                    assert "selection" in str(row["result_payload"])
            else:
                assert dispatched.status.value == "accepted", dispatched
                assert len(venue.calls) == 1
                from src.trading_kernel.application.maintain_ticket_lifecycle import (
                    LifecycleMaintenanceRequest,
                    TicketLifecycleFacts,
                    maintain_ticket_lifecycle,
                )
                from src.trading_kernel.application.reconcile_ticket import (
                    ReconcileTicketRequest,
                    reconcile_ticket,
                )
                from src.trading_kernel.application.settle_ticket import (
                    RecordTradeReviewRequest,
                    SettleTicketRequest,
                    record_trade_review,
                    settle_ticket,
                )
                from src.trading_kernel.domain.aggregate import AggregateStatus
                from src.trading_kernel.domain.commands import ExchangeCommandKind
                from src.trading_kernel.domain.events import PostFillStressAssessed
                from src.trading_kernel.domain.position import PositionSnapshot
                from src.trading_kernel.domain.reducer import reduce_event
                from tests.trading_kernel.support.capacity_claims import (
                    make_stress_evidence,
                )

                async with PostgresKernelUnitOfWork(database) as lifecycle_uow:
                    filled = await reconcile_ticket(lifecycle_uow, ReconcileTicketRequest(
                        ticket_id=issued.ticket_id,
                        snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                            quantity=ticket.quantity,average_entry_price=ticket.entry_reference_price,
                            venue_reported_liquidation_price=Decimal(0),open_orders=(),
                            observed_at_ms=issued_at+100),
                    ))
                assert filled.status.value == "entry_fill_recorded"
                async def dispatch_safety(step):
                    async with PostgresKernelUnitOfWork(database) as stress_uow:
                        pending = await stress_uow.aggregates.get(issued.ticket_id)
                        if pending is not None and pending.status is AggregateStatus.POST_FILL_RISK_PENDING:
                            event = PostFillStressAssessed(
                                event_id=f"event:{issued.ticket_id}:{pending.last_event_sequence+1}",
                                ticket_id=issued.ticket_id,sequence=pending.last_event_sequence+1,
                                occurred_at_ms=issued_at+step-1,status="passed",
                                evidence=make_stress_evidence(pending.ticket),
                                owner_policy_id=pending.ticket.owner_policy_id,
                                owner_policy_version=pending.ticket.owner_policy_version,
                                filled_qty=pending.position_qty,average_fill_price=pending.average_fill_price,
                                initial_stop_price=pending.ticket.initial_stop_price,
                                initial_stop_exchange_order_id=pending.initial_stop_exchange_order_id)
                            await stress_uow.commit_reduction(event=event,
                                reduction=reduce_event(pending,event),expected_version=pending.version)
                    venue.observed_at_ms = issued_at + step + 1
                    outcome = await dispatch_one_command(lambda:PostgresKernelUnitOfWork(database),venue,
                        DispatchCommandRequest(worker_id="recovery-lifecycle",ticket_id=issued.ticket_id,
                            now_ms=issued_at+step,lease_until_ms=issued_at+step+30_000,
                            timeout_seconds=1))
                    assert outcome.status.value == "accepted", outcome
                    return outcome

                await dispatch_safety(200)
                await dispatch_safety(300)
                async with PostgresKernelUnitOfWork(database) as lifecycle_uow:
                    protected = await lifecycle_uow.aggregates.get(issued.ticket_id)
                assert protected is not None and protected.status is AggregateStatus.POSITION_PROTECTED
                assert protected.initial_stop_exchange_order_id is not None
                assert protected.tp1_exchange_order_id is not None
                async with PostgresKernelUnitOfWork(database) as lifecycle_uow:
                    runner = await maintain_ticket_lifecycle(lifecycle_uow, LifecycleMaintenanceRequest(
                        ticket_id=issued.ticket_id,
                        facts=TicketLifecycleFacts(position_quantity=ticket.quantity-ticket.take_profit_quantities[0],
                            tp1_filled_quantity=ticket.take_profit_quantities[0],
                            tp1_average_fill_price=ticket.take_profit_prices[0],
                            allocated_entry_fee_quote=Decimal("0.01"),exit_taker_fee_rate=Decimal("0.001"),
                            price_tick=Decimal("0.01"),market_facts=None,observed_at_ms=issued_at+400),
                        now_ms=issued_at+400))
                assert runner.status.value == "break_even_requested"
                await dispatch_safety(500)
                await dispatch_safety(600)
                async with PostgresKernelUnitOfWork(database) as lifecycle_uow:
                    flat = await reconcile_ticket(lifecycle_uow, ReconcileTicketRequest(
                        ticket_id=issued.ticket_id,
                        snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                            quantity=Decimal(0),average_entry_price=None,open_orders=(),
                            observed_at_ms=issued_at+700),
                    ))
                assert flat.status.value == "external_flat_incident"
                await dispatch_safety(800)
                async with PostgresKernelUnitOfWork(database) as lifecycle_uow:
                    matched = await reconcile_ticket(lifecycle_uow, ReconcileTicketRequest(
                        ticket_id=issued.ticket_id,
                        snapshot=PositionSnapshot(netting_domain=ticket.identity.netting_domain,
                            quantity=Decimal(0),average_entry_price=None,open_orders=(),
                            observed_at_ms=issued_at+900),
                    ))
                    settled = await settle_ticket(lifecycle_uow, SettleTicketRequest(
                        ticket_id=issued.ticket_id,settled_at_ms=issued_at+1000))
                    reviewed = await record_trade_review(lifecycle_uow, RecordTradeReviewRequest(
                        ticket_id=issued.ticket_id,review_id="review:recovered-cpm",
                        outcome="closed",metrics={"realized_pnl":"1.25"},
                        decision_impact={"strategy_action":"keep"},recorded_at_ms=issued_at+1100))
                    terminal = await lifecycle_uow.aggregates.get(issued.ticket_id)
                    frozen = await lifecycle_uow.tickets.get(issued.ticket_id)
                    review = await lifecycle_uow.reviews.get_for_ticket(issued.ticket_id)
                    reservation = await lifecycle_uow.budgets.get_for_ticket(issued.ticket_id)
                    active_in_domain = await lifecycle_uow.entry_admission.has_active_ticket_in_domain(ticket.identity.netting_domain.key())
                    incident = await lifecycle_uow.incidents.get_open_for_ticket(issued.ticket_id)
                    commands = await lifecycle_uow.exchange_commands.list_for_ticket(issued.ticket_id)
                assert matched.status.value == "matched"
                assert settled.status.value == "budget_settled"
                assert reviewed.status.value == "review_recorded"
                assert terminal is not None and terminal.status is AggregateStatus.TERMINAL
                assert frozen is not None and frozen.selection_authority_id == committed_recovery.selection_authority_id
                assert review is not None and review.review_id == "review:recovered-cpm"
                assert reservation is not None and reservation.status == "released"
                assert not active_in_domain and incident is None
                assert [command.kind for command in commands] == [
                    ExchangeCommandKind.ENTRY,ExchangeCommandKind.INITIAL_STOP,
                    ExchangeCommandKind.TAKE_PROFIT,ExchangeCommandKind.REPLACE_PROTECTION,
                    ExchangeCommandKind.CANCEL_ORDER,ExchangeCommandKind.CANCEL_ORDER,
                ], [command.kind.value for command in commands]
                assert len(venue.calls) == len(commands)
            return
        from src.trading_kernel.application.ingest_signal import (
            resolve_selection_observation_authority,
        )
        template = {"MPG-001":mpg_long_snapshot,"MI-001":mi_long_snapshot,"BRF2-001":brf2_short_snapshot}[source.spec.strategy_group_id]()
        delta = first_close-template.trigger_candle_close_time_ms
        class FirstRecoveryMarket:
            def __init__(self):
                self.calls = []

            async def fetch_closed_candles(self, request):
                self.calls.append(request)
                candles = template.candles_1h if request.timeframe=="1h" else template.candles_4h
                return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)

        async with PostgresKernelUnitOfWork(database) as producer_uow:
            assert producer_uow._connection is not None
            probe = await producer_uow._connection.begin_nested()
            @asynccontextmanager
            async def borrowed_producer_transaction():
                yield producer_uow
            class MissingRecoveryMarket:
                async def fetch_closed_candles(self, request):
                    return ()
            invalid_probe = await producer_uow._connection.begin_nested()
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+1)):
                invalid = await observe_strategy_scope(borrowed_producer_transaction,MissingRecoveryMarket(),
                    ObservationRequest(runtime_scope_id=recovery_scope,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                        trigger_candle_close_time_ms=first_close,attempted_at_ms=first_close+1))
            assert invalid.status == ObservationStatus.INVALID
            pending_checkpoint = await producer_uow.signals.get_authority_recovery_checkpoint(proposal.observation_cursors[0].episode_domain_key)
            assert pending_checkpoint.last_observed_close_time_ms is None and pending_checkpoint.armed_at_close_time_ms is None
            await invalid_probe.rollback()
            market = FirstRecoveryMarket()
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+1)):
                observed = await observe_strategy_scope(borrowed_producer_transaction,market,
                    ObservationRequest(runtime_scope_id=recovery_scope,runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,
                        trigger_candle_close_time_ms=first_close,attempted_at_ms=first_close+1))
            assert observed.status == ObservationStatus.NO_SIGNAL, observed
            assert observed.detector_reason == "RECOVERY_REBASE_REQUIRED", observed
            assert market.calls
            assert await producer_uow._connection.scalar(sa.text("SELECT count(*) FROM brc_signal_events")) == 0
            checkpoint = await producer_uow.signals.get_authority_recovery_checkpoint(proposal.observation_cursors[0].episode_domain_key)
            assert checkpoint.last_detector_status is DetectorStatus.TRIGGERED
            assert checkpoint.armed_at_close_time_ms is None
            await probe.rollback()
        async with PostgresKernelUnitOfWork(database) as authorized_uow:
            recovered_scope = await authorized_uow.signals.get_runtime_scope(recovery_scope)
            args = {"runtime_scope":recovered_scope,"birth_selection_authority_id":None,
                "observed_close_time_ms":first_close,"now_ms":first_close+1,"allow_current_as_birth":True,"lock_current":True}
            observation_permission = await resolve_selection_observation_authority(authorized_uow,**args)
            assert observation_permission.allowed
            entry_permission = await resolve_selection_entry_authority(authorized_uow,**args)
            assert not entry_permission.allowed and entry_permission.reason_code == "RECOVERY_REBASE_REQUIRED"
        if first_close+HOUR+1<committed_recovery.expires_at_ms:
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+HOUR+1)), pytest.raises(RuntimeError,match="latest close"):
                async with PostgresKernelUnitOfWork(database) as observed_uow:
                    await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                        selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=first_close,
                        detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None)
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+1)):
            async with PostgresKernelUnitOfWork(database) as observed_uow:
                with pytest.raises(RuntimeError,match="current authority"):
                    await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                        selection_authority_id="authority:wrong",observed_at_ms=first_close,detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=first_close)
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(side_effect=[first_close+1,committed_recovery.expires_at_ms])), pytest.raises(RuntimeError,match="expired"):
                    await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                        selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=first_close,detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=first_close)
                old_checkpoint = await observed_uow.signals.get_authority_recovery_checkpoint(proposal.observation_cursors[0].episode_domain_key)
                assert old_checkpoint.last_observed_close_time_ms is None
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(side_effect=[first_close+1,first_close])), pytest.raises(RuntimeError,match="latest close changed"):
                    await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                        selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=first_close,
                        detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=first_close)
                unchanged = await observed_uow.signals.get_authority_recovery_checkpoint(proposal.observation_cursors[0].episode_domain_key)
                assert unchanged == old_checkpoint
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+1)):
            async with PostgresKernelUnitOfWork(database) as observed_uow:
                transition = await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                    selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=first_close,
                    detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=first_close)
                assert not transition.signal_eligible and transition.episode_transition is None
                assert transition.recovery_checkpoint.last_observed_close_time_ms == first_close
        await database.dispose()
        async with PostgresKernelUnitOfWork(database) as observed_uow:
            checkpoint = await observed_uow.signals.get_authority_recovery_checkpoint(proposal.observation_cursors[0].episode_domain_key)
            assert checkpoint.last_detector_status == DetectorStatus.TRIGGERED
            assert checkpoint.state == "REBASE_REQUIRED"
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=first_close+2)):
                repeated = await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                    selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=first_close,
                    detector_status=DetectorStatus.TRIGGERED,occurred_at_ms=first_close)
            assert repeated.recovery_checkpoint == checkpoint and not repeated.signal_eligible
        for close_time, status in ((first_close+HOUR,DetectorStatus.NOT_TRIGGERED),(first_close+2*HOUR,DetectorStatus.TRIGGERED)):
            if close_time>=committed_recovery.expires_at_ms:
                break  # hourly periods cannot fabricate an additional close.
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=close_time+1)):
                async with PostgresKernelUnitOfWork(database) as observed_uow:
                    progressed = await observed_uow.signals.advance_recovery_observation(runtime_scope_id=recovery_scope,
                        selection_authority_id=committed_recovery.selection_authority_id,observed_at_ms=close_time,
                        detector_status=status,occurred_at_ms=close_time if status is DetectorStatus.TRIGGERED else None)
                    assert progressed.recovery_checkpoint.state == "ARMED"
                    assert progressed.signal_eligible == (status is DetectorStatus.TRIGGERED)
                    current_scope = await observed_uow.signals.get_runtime_scope(recovery_scope)
                    admitted = await resolve_selection_entry_authority(observed_uow,runtime_scope=current_scope,
                        birth_selection_authority_id=committed_recovery.selection_authority_id,observed_close_time_ms=close_time,
                        now_ms=close_time+1,allow_current_as_birth=False,lock_current=True)
                    assert admitted.allowed == (status is DetectorStatus.TRIGGERED)


async def _assert_generic_empty_handoff(database, source, original, vacuum):
    next_source = next_input(source)
    while next_source.feature_cutoff_at_ms <= original.period_anchor_ms:
        next_source = next_input(next_source)
    next_source = next_source.model_copy(update={"member_windows":tuple(qualify_window(w,False) for w in next_source.member_windows)})
    empty = compute_generic_selection(next_source)
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(empty,decision_at_ms=next_source.decision_at_ms,source_observed_at_ms=next_source.source_observed_at_ms)
    empty_request = CoordinateGenericSnapshotRequest(selection_snapshot_id=empty.selection_snapshot_id,worker_id="empty-successor")
    now = empty.effective_from_ms+8000
    async with PostgresKernelUnitOfWork(database) as uow:
        owner = await uow.owner_controls.get_strategy_control(source.spec.strategy_group_id)
        control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
    for old_vacuum, owner_version, control_version, checked_at, error in (
        (vacuum,owner.control_version+1,control.control_version,now,"Owner or Control"),
        (vacuum,owner.control_version,control.control_version+1,now,"Owner or Control"),
        (vacuum.model_copy(update={"projection_version":vacuum.projection_version+1}),owner.control_version,control.control_version,now,"Vacuum changed"),
        (vacuum,owner.control_version,control.control_version,empty.effective_from_ms-1,"latest effective"),
    ):
        with pytest.raises(SelectionJobConflict,match=error), patch.object(
            PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=checked_at)):
            async with PostgresKernelUnitOfWork(database) as uow:
                await uow.instrument_selection.retarget_generic_empty_vacuum(old_vacuum,selection_snapshot_id=empty.selection_snapshot_id,
                    expected_owner_version=owner_version,expected_control_version=control_version)
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id=:group"),{"group":source.spec.strategy_group_id})
    paused = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:now)
    assert paused.disposition == MaterializationDisposition.OWNER_PAUSED
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='enabled' WHERE strategy_group_id=:group"),{"group":source.spec.strategy_group_id})

    @asynccontextmanager
    async def interrupted_handoff():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
            assert current is not None and current.authority.blocks_new_entry
            raise RuntimeError("empty handoff interrupted")

    with pytest.raises(RuntimeError,match="empty handoff interrupted"), patch.object(
        PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
        await coordinate_selection_materialization_once(uow_factory=interrupted_handoff,request=empty_request,clock_ms=lambda:now)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id,selection_spec_id=source.spec.selection_spec_id) == vacuum
        assert await uow.instrument_selection.get_generic_materialization_generation(original.materialization_generation_id) == original
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
        result = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:now)
    assert result.disposition == MaterializationDisposition.VALID_EMPTY, result
    async with PostgresKernelUnitOfWork(database) as uow:
        current = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        assert current is not None and current.authority.blocks_new_entry
        assert current.authority.selection_snapshot_id == empty.selection_snapshot_id
        old = await uow.instrument_selection.get_generic_materialization_generation(original.materialization_generation_id)
        if original.lifecycle_state.value == "FAILED_CLOSED":
            assert old == original
        else:
            assert old.lifecycle_state.value == "SUPERSEDED" and old.terminal_at_ms == now
    async with database.connect() as conn:
        row = (await conn.execute(sa.text("SELECT * FROM brc_strategy_entry_vacuums_current"))).mappings().one()
        assert row["entry_vacuum_id"] == vacuum.entry_vacuum_id
        assert row["state"] == "VALID_EMPTY" and row["source_generation_id"] is None
        assert row["fenced_at_ms"] == vacuum.fenced_at_ms and row["drained_at_ms"] == vacuum.drained_at_ms
        assert row["period_anchor_ms"] == empty.feature_cutoff_at_ms
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    repeated = await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(database),request=empty_request,clock_ms=lambda:now+1)
    assert repeated.selection_authority_id == result.selection_authority_id
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuum_events WHERE entry_vacuum_id=:id AND event_type='VALID_EMPTY_INTENT'"),{"id":vacuum.entry_vacuum_id}) == 1


async def _assert_generic_durable_activation(database, source, generation, uid, now):
    # Existing Active baseline/certification are explicit prerequisites. Unlike
    # the storage probe below, every coordinator call owns and commits its UoW.
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true WHERE owner_policy_id='policy-main'"))
    request = CoordinateGenericGenerationRequest(materialization_generation_id=generation.materialization_generation_id, worker_id="durable-activation")
    def factory():
        return PostgresKernelUnitOfWork(database)

    async with factory() as uow:
        original_control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
    assert original_control is not None

    if original_control.pending_authorization_id is not None:
        # A wrong-purpose proof cannot even replace the pending pointer now;
        # the DB boundary rejects it before Coordinator can see it.
        with pytest.raises(sa.exc.DBAPIError, match="Generic pending Owner epoch"):
            async with database.begin() as conn:
                await conn.execute(sa.text("INSERT INTO brc_owner_authorizations SELECT authorization_id||:suffix, 'universe_configure', owner_identity, authentication_strength, request_digest, target_scope, idempotency_key||:suffix, authorized_at_ms FROM brc_owner_authorizations WHERE authorization_id=:id"), {"id":original_control.pending_authorization_id,"suffix":":wrong"})
                await conn.execute(sa.text("UPDATE brc_strategy_selection_control_current SET pending_authorization_id=:id WHERE strategy_group_id=:group"), {"id":original_control.pending_authorization_id+":wrong", "group":source.spec.strategy_group_id})
        async with factory() as uow:
            assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == original_control
        # Omitting the mode write must fail at actual transaction commit, not
        # merely rely on application validation before the authority insert.
        with pytest.raises(sa.exc.DBAPIError, match="atomic authorized mode transition"), patch.object(
            PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=AsyncMock(return_value=now)
        ), patch.object(PostgresInstrumentSelectionRepository, "activate_pending_selection_mode", new=AsyncMock(return_value=original_control)):
            await coordinate_selection_materialization_once(uow_factory=factory, request=request, clock_ms=lambda:now)

    @asynccontextmanager
    async def interrupted_before_commit():
        async with PostgresKernelUnitOfWork(database) as uow:
            yield uow
            assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is not None
            raise RuntimeError("injected interruption before commit")

    with pytest.raises(RuntimeError, match="injected interruption"), patch.object(
        PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=AsyncMock(return_value=now)
    ):
        await coordinate_selection_materialization_once(uow_factory=interrupted_before_commit, request=request, clock_ms=lambda:now)
    await database.dispose()
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id) == original_control
        assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
        interrupted = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
        old_current = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        unresolved = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id, selection_spec_id=source.spec.selection_spec_id)
        assert interrupted is not None and interrupted.lifecycle_state.value == "STAGED" and interrupted.lease_owner is None
        assert old_current is not None and old_current.universe_version_id == generation.previous_events[0].universe_version_id
        assert unresolved is not None and unresolved.state.value == "RECONFIGURING"
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"), {"uid":uid}) == "staged"
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid AND event_type='ACTIVE'"), {"gid":generation.materialization_generation_id}) == 0
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=AsyncMock(return_value=now)):
        activated = await coordinate_selection_materialization_once(uow_factory=factory, request=request, clock_ms=lambda:now)
    assert activated.disposition == MaterializationDisposition.ACTIVE_NEW, activated
    # Drop pooled connections, then create fresh repositories: recovery must
    # use committed facts, not objects retained by the activating transaction.
    await database.dispose()
    async with PostgresKernelUnitOfWork(database) as uow:
        authority = await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id)
        current = await uow.strategy_universes.get_current(source.spec.event_spec_id)
        persisted = await uow.instrument_selection.get_generic_materialization_generation(generation.materialization_generation_id)
        vacuum = await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=source.spec.strategy_group_id, selection_spec_id=source.spec.selection_spec_id)
        assert authority is not None and authority.authority.selection_authority_id == activated.selection_authority_id
        control = await uow.instrument_selection.get_selection_control(source.spec.strategy_group_id)
        assert control is not None and control.selection_mode.value == "dynamic_selection"
        assert control.pending_authorization_id is None and control.pending_selection_mode is None
        assert control.control_version == original_control.control_version + int(original_control.pending_authorization_id is not None)
        assert authority.authority.selection_control_version == control.control_version
        assert authority.authority.activation_authorization_id == original_control.pending_authorization_id
        assert persisted is not None and persisted.selection_control_version == original_control.control_version
        assert current is not None and current.universe_version_id == uid
        assert persisted is not None and persisted.lifecycle_state.value == "ACTIVE" and persisted.lease_owner is None
        assert vacuum is None
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT state FROM brc_strategy_entry_vacuums_current WHERE source_generation_id=:gid"), {"gid":generation.materialization_generation_id}) == "RESOLVED_ACTIVE"
        scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
        before = await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid"), {"gid":generation.materialization_generation_id})
    async with PostgresKernelUnitOfWork(database) as uow:
        scope = await uow.signals.get_runtime_scope(scope_id)
        assert scope is not None
        decision = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=None,observed_close_time_ms=now//HOUR*HOUR,
            now_ms=now,allow_current_as_birth=True,lock_current=True)
        assert decision.allowed, decision
        assert decision.selection_authority_id == activated.selection_authority_id
        born = await resolve_selection_entry_authority(uow,runtime_scope=scope,
            birth_selection_authority_id=decision.selection_authority_id,observed_close_time_ms=now//HOUR*HOUR,
            now_ms=now+1,allow_current_as_birth=False,lock_current=True)
        assert born.allowed and born.selection_authority_id == decision.selection_authority_id
        for wrong_version in (persisted.selection_control_version-1,persisted.selection_control_version+1):
            with patch.object(uow.instrument_selection,"get_generic_materialization_generation",new=AsyncMock(
                return_value=persisted.model_copy(update={"selection_control_version":wrong_version}))):
                denied = await resolve_selection_entry_authority(uow,runtime_scope=scope,
                    birth_selection_authority_id=decision.selection_authority_id,observed_close_time_ms=now//HOUR*HOUR,
                    now_ms=now+1,allow_current_as_birth=False,lock_current=True)
            assert not denied.allowed and denied.reason_code == "selection_generation_not_active"
    with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=AsyncMock(return_value=now+1)):
        repeated = await coordinate_selection_materialization_once(uow_factory=factory, request=request.model_copy(update={"worker_id":"restarted-worker"}), clock_ms=lambda:now+1)
    assert repeated.selection_authority_id == activated.selection_authority_id
    assert repeated.disposition == MaterializationDisposition.ACTIVE_NEW
    async with database.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_universe_materialization_events WHERE materialization_generation_id=:gid"), {"gid":generation.materialization_generation_id}) == before
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0


async def _assert_generic_active_new_storage(database, source, generation, uid, now):
    from types import SimpleNamespace

    from src.trading_kernel.infrastructure.pg_repositories import (
        PostgresEntryAdmissionRepository,
        PostgresOwnerControlRepository,
    )
    from src.trading_kernel.infrastructure.pg_signal_repository import (
        PostgresSignalRepository,
    )
    # Official activation entrypoint in a rollback probe, so subsequent staging
    # fault cases continue on the same fixture. Database wall-clock is injected.
    async with database.connect() as conn:
        transaction = await conn.begin()
        try:
            repository = PostgresInstrumentSelectionRepository(conn)
            snapshot = await repository.get_generic_snapshot(generation.selection_snapshot_id)
            period = build_generic_selection_period(feature_cutoff_at_ms=snapshot.feature_cutoff_at_ms,cadence_hours=source.spec.cadence_hours)
            cursors = await PostgresSignalRepository(conn).lock_generic_close_coverage(event_spec_id=source.spec.event_spec_id,
                exchange_instrument_ids=snapshot.selected_members,closed_at_ms=now//HOUR*HOUR)
            proof = CurrentFinalCloseGrantProof(selection_snapshot_id=snapshot.selection_snapshot_id,selection_committed_at_ms=snapshot.committed_at_ms,
                source_snapshot_cutoff_at_ms=snapshot.feature_cutoff_at_ms,period=period,current_final_close_time_ms=now//HOUR*HOUR,
                authority_granted_at_ms=now,observation_cursors=cursors)
            await conn.execute(sa.text("UPDATE brc_owner_policy_current SET new_entry_submit_enabled=true WHERE owner_policy_id='policy-main'"))
            cid = None
            revision = None
            if source.spec.strategy_group_id in {"MPG-001","MI-001"}:
                cid = "comparison:"+canonical_digest({"exchange_instrument_ids":source.spec.candidate_ids})[7:]
                revision = generation.previous_events[0].comparison_transition_revision + 1
            authority = GenericSelectionAuthority(selection_authority_id="authority:active:"+source.spec.strategy_group_id,
                selection_spec_id=source.spec.selection_spec_id,strategy_group_id=source.spec.strategy_group_id,selection_epoch_id=snapshot.selection_epoch_id,
                selection_snapshot_id=snapshot.selection_snapshot_id,materialization_generation_id=generation.materialization_generation_id,
                authority_sequence=1,owner_control_version=1,selection_control_version=generation.selection_control_version,period=period,
                authority_outcome="ACTIVE_NEW",event_binding=AuthorityEventBinding(event_spec_id=source.spec.event_spec_id,position_side=source.spec.position_side,
                    grant_state="ACTIVE",universe_version_id=uid,member_set_digest=snapshot.member_set_digest),current_close_proof=proof,
                membership_freshness=build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,source_member_set_digest=snapshot.member_set_digest,period=period),
                comparison_universe_id=cid,comparison_transition_revision=revision,effective_from_ms=now,created_at_ms=now)
            leased = await repository.get_generic_materialization_generation(generation.materialization_generation_id)
            request = UniverseActivationRequest(universe_version_id=uid,attempted_at_ms=now,operation=UniverseActivationOperation.ACTIVATE_GENERIC,
                materialization_generation_id=generation.materialization_generation_id,materialization_lease_owner=leased.lease_owner,
                materialization_lease_epoch=leased.lease_epoch,generic_authority=authority)
            for bad_request, reason in (
                (request.model_copy(update={"materialization_lease_epoch":leased.lease_epoch+1}),"LEASE_CHANGED"),
                (request.model_copy(update={"generic_authority":authority.model_copy(update={"owner_control_version":99})}),"OWNER_CONTROL_CHANGED"),
            ):
                with pytest.raises(UniverseInstallConflict,match=reason), patch.object(
                    PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                    await PostgresStrategyUniverseRepository(conn).try_activate(bad_request)
            with pytest.raises(ValueError,match="boundary"):
                async with conn.begin_nested():
                    with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(side_effect=[now,(now//HOUR+1)*HOUR])):
                        await PostgresStrategyUniverseRepository(conn).try_activate(request)
            for final_clock, reason in (
                (leased.fenced_at_ms+source.spec.materialization_timeout_ms,"MATERIALIZATION_TIMEOUT"),
                (leased.lease_expires_at_ms,"DYNAMIC_GENERATION_LEASE_CHANGED"),
            ):
                with pytest.raises(UniverseInstallConflict,match=reason):
                    async with conn.begin_nested():
                        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(side_effect=[now,final_clock])):
                            await PostgresStrategyUniverseRepository(conn).try_activate(request)
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 0
            assert await conn.scalar(sa.text("SELECT lifecycle_state FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid}) == "staged"
            assert await conn.scalar(sa.text("SELECT state FROM brc_strategy_entry_vacuums_current WHERE source_generation_id=:gid"),{"gid":generation.materialization_generation_id}) == "RECONFIGURING"
            await repository.release_generic_materialization_generation_lease(generation.materialization_generation_id,
                worker_id=leased.lease_owner,lease_epoch=leased.lease_epoch)
            @asynccontextmanager
            async def borrowed_transaction():
                yield SimpleNamespace(instrument_selection=repository,signals=PostgresSignalRepository(conn),
                    strategy_universes=PostgresStrategyUniverseRepository(conn),owner_controls=PostgresOwnerControlRepository(conn),
                    entry_admission=PostgresEntryAdmissionRepository(conn))
            coordinator_request = CoordinateGenericGenerationRequest(materialization_generation_id=generation.materialization_generation_id,worker_id="activate-coordinator")
            for certification_status, expected_disposition, expected_reason in (
                ("temporarily_unavailable", MaterializationDisposition.TARGET_WARMING, "CERTIFICATION_TEMPORARILY_UNAVAILABLE"),
                ("owner_action_required", MaterializationDisposition.BLOCKED, "CERTIFICATION_OWNER_ACTION_REQUIRED"),
            ):
                checkpoint = await conn.begin_nested()
                await conn.execute(sa.text("UPDATE brc_instrument_certification_current SET status=:status,blocker_code='readonly_facts_unavailable' WHERE exchange_instrument_id IN (SELECT exchange_instrument_id FROM brc_strategy_universe_members WHERE universe_version_id=:uid)"), {"status":certification_status,"uid":uid})
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                    waiting = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,request=coordinator_request,clock_ms=lambda:now)
                assert waiting.disposition == expected_disposition
                assert waiting.reason_code == expected_reason
                pending = await repository.get_generic_materialization_generation(generation.materialization_generation_id)
                assert pending is not None and pending.lifecycle_state.value == ("FAILED_CLOSED" if certification_status=="owner_action_required" else "STAGED")
                assert pending.created_at_ms == generation.created_at_ms
                assert pending.lease_owner is None
                assert await repository.get_current_generic_authority(source.spec.selection_spec_id) is None
                await checkpoint.rollback()
            if source.spec.strategy_group_id in {"MPG-001", "MI-001"}:
                # Lose the persisted comparison input after staging. The real
                # readiness path must wait without granting or resetting time.
                checkpoint = await conn.begin_nested()
                before = await repository.get_generic_materialization_generation(generation.materialization_generation_id)
                await conn.execute(sa.text("DELETE FROM brc_comparative_projection_current WHERE universe_version_id=:uid"), {"uid":uid})
                with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                    waiting = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,request=coordinator_request,clock_ms=lambda:now)
                assert waiting.disposition == MaterializationDisposition.TARGET_WARMING
                assert waiting.reason_code == "COMPARATIVE_PROJECTION_INCOMPLETE"
                after = await repository.get_generic_materialization_generation(generation.materialization_generation_id)
                assert before is not None and after is not None
                assert after.lifecycle_state == before.lifecycle_state
                assert after.created_at_ms == before.created_at_ms
                assert after.lease_owner is None
                assert await repository.get_current_generic_authority(source.spec.selection_spec_id) is None
                await checkpoint.rollback()
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                result = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,request=coordinator_request,clock_ms=lambda:now)
            assert result.disposition == MaterializationDisposition.ACTIVE_NEW
            committed = await repository.get_current_generic_authority(source.spec.selection_spec_id)
            assert committed is not None
            authority = committed.authority
            request = request.model_copy(update={"generic_authority":authority})
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                repeated = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,request=coordinator_request,clock_ms=lambda:now)
            assert repeated.selection_authority_id == authority.selection_authority_id
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=authority.expires_at_ms)):
                stale = await coordinate_selection_materialization_once(uow_factory=borrowed_transaction,request=coordinator_request,
                    clock_ms=lambda:now)
            assert stale.disposition == MaterializationDisposition.BLOCKED
            scope_id = await conn.scalar(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid ORDER BY runtime_scope_id LIMIT 1"),{"uid":uid})
            async with borrowed_transaction() as active_uow:
                scope = await active_uow.signals.get_runtime_scope(scope_id)
                allowed = await resolve_selection_entry_authority(active_uow,runtime_scope=scope,birth_selection_authority_id=None,
                    observed_close_time_ms=proof.current_final_close_time_ms,now_ms=now,allow_current_as_birth=True,lock_current=True)
                assert allowed.allowed and allowed.selection_authority_id == authority.selection_authority_id
            assert await conn.scalar(sa.text("SELECT lease_owner FROM brc_strategy_universe_materialization_generations WHERE materialization_generation_id=:gid"),{"gid":generation.materialization_generation_id}) is None
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
            with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now)):
                assert (await PostgresStrategyUniverseRepository(conn).try_activate(request)).status == UniverseActivationStatus.ALREADY_ACTIVE
            for broken in (
                "UPDATE brc_strategy_entry_vacuums_current SET state='RECONFIGURING',resolved_at_ms=NULL WHERE source_generation_id=:gid",
                "UPDATE brc_strategy_universe_materialization_generations SET activated_at_ms=activated_at_ms+1 WHERE materialization_generation_id=:gid",
                "UPDATE brc_strategy_universe_materialization_generations SET fenced_at_ms=fenced_at_ms+1 WHERE materialization_generation_id=:gid",
                "DELETE FROM brc_selection_authority_current WHERE selection_spec_id=:spec",
            ):
                with pytest.raises(sa.exc.DBAPIError,match="Generic ACTIVE_NEW requires atomic"):
                    async with conn.begin_nested():
                        await conn.execute(sa.text(broken),{"gid":generation.materialization_generation_id,"spec":source.spec.selection_spec_id})
                        await conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
            await conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_expired_generic_runner_records_job_without_market_read(database: AsyncEngine) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    expiry = build_generic_selection_period(
        feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours,
    ).period_expires_at_ms

    class NoMarket:
        async def fetch_generic_selection_qualifications(self, **kwargs):
            raise AssertionError("Expired Selection must not read qualifications")

        async def fetch_generic_selection_klines(self, request):
            raise AssertionError("Expired Selection must not read market path")

    result = await run_instrument_selection_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(database),
        market_source=NoMarket(),
        request=RunInstrumentSelectionRequest(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
            worker_id="selection:expired-runner",
        ),
        clock_ms=lambda: expiry,
    )
    assert result.outcome == "EXPIRED"
    assert result.reason_code == "SELECTION_PERIOD_EXPIRED"
    async with PostgresKernelUnitOfWork(database) as uow:
        job = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
        )
    assert job is not None and job.state == "EXPIRED" and job.attempt_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("source_failure", [False, True])
async def test_generic_runner_discards_source_when_period_expires_during_market_read(
    database: AsyncEngine, source_failure: bool,
) -> None:
    source = inputs("MI-001")
    await enable_epoch(database, "MI-001")
    expiry = build_generic_selection_period(
        feature_cutoff_at_ms=CUTOFF,
        cadence_hours=source.spec.cadence_hours,
    ).period_expires_at_ms
    now = CUTOFF
    calls = 0

    def clock() -> int:
        nonlocal now
        now += 1
        return now

    class LateMarket:
        async def fetch_generic_selection_qualifications(self, **kwargs):
            nonlocal now
            now = expiry
            return tuple(
                member.qualification.model_copy(update={"observed_at_ms": CUTOFF + 2})
                for member in source.member_windows
            )

        async def fetch_generic_selection_klines(self, request):
            nonlocal calls
            calls += 1
            candles = next(member.candles for member in source.member_windows
                           if member.exchange_instrument_id == request.exchange_instrument_id)
            return candles[:-1] if source_failure and request.exchange_instrument_id == source.spec.candidate_ids[0] else candles

    result = await run_instrument_selection_once(
        uow_factory=lambda: PostgresKernelUnitOfWork(database),
        market_source=LateMarket(),
        request=RunInstrumentSelectionRequest(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
            worker_id="selection:late-market",
        ),
        clock_ms=clock,
    )
    assert result.outcome == "EXPIRED" and calls == 24
    async with PostgresKernelUnitOfWork(database) as uow:
        job = await uow.instrument_selection.get_selection_job(
            selection_spec_id=source.spec.selection_spec_id,
            selection_epoch_id=source.selection_epoch_id,
            period_anchor_ms=CUTOFF,
        )
    assert job is not None and job.state == "EXPIRED"
    async with database.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_attempts)) == 0
        assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("group,defect", [("CPM-RO-001", None), ("MPG-001", None), ("MI-001", None), ("BRF2-001", None),
    ("CPM-RO-001", "missing"), ("CPM-RO-001", "empty"), ("CPM-RO-001", "flat"), ("CPM-RO-001", "unknown"), ("CPM-RO-001", "control_changed")])
async def test_generic_runner_uses_full_source_outside_transaction_and_ends_at_snapshot(database: AsyncEngine, group: str, defect: str | None) -> None:
    source_input = inputs(group)
    if defect == "empty":
        source_input = source_input.model_copy(update={"member_windows": tuple(qualify_window(w, False) for w in source_input.member_windows)})
    elif defect == "flat":
        source_input = source_input.model_copy(update={"member_windows": tuple(w.model_copy(update={"candles": tuple(
            c.model_copy(update={"close": Decimal(100)}) for c in w.candles)}) for w in source_input.member_windows)})
    calls: list[str] = []
    active_transactions = 0

    class ObservedUow(PostgresKernelUnitOfWork):
        async def __aenter__(self):
            nonlocal active_transactions
            entered = await super().__aenter__()
            active_transactions += 1
            return entered

        async def __aexit__(self, *args):
            nonlocal active_transactions
            try:
                return await super().__aexit__(*args)
            finally:
                active_transactions -= 1

    class Market:
        async def fetch_selection_klines(self, request):
            raise AssertionError("Generic cannot read SOR's 15m input")

        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            assert active_transactions == 0
            assert event_spec_id == source_input.spec.event_spec_id and len(product_profiles) == 24
            calls.append("qualification")
            if defect == "unknown":
                raise ValueError("qualification unavailable")
            return tuple(w.qualification.model_copy(update={"observed_at_ms": observed_at_ms}) for w in source_input.member_windows)

        async def fetch_generic_selection_klines(self, request):
            assert active_transactions == 0
            assert request.feature_cutoff_at_ms == CUTOFF and request.expected_bars == source_input.spec.window_bars
            calls.append(request.exchange_instrument_id)
            candles = next(w.candles for w in source_input.member_windows if w.exchange_instrument_id == request.exchange_instrument_id)
            if request.exchange_instrument_id == source_input.spec.candidate_ids[0]:
                if defect == "missing":
                    return candles[:-1]
                if defect == "control_changed":
                    async with database.begin() as conn:
                        await conn.execute(sa.update(strategy_selection_control_current).where(
                            strategy_selection_control_current.c.strategy_group_id == group).values(control_version=3))
            return candles

    timestamp = CUTOFF

    def clock() -> int:
        nonlocal timestamp
        timestamp += 1
        return timestamp

    request = RunInstrumentSelectionRequest(selection_spec_id=source_input.spec.selection_spec_id,
        selection_epoch_id="epoch:1", period_anchor_ms=CUTOFF, worker_id="runner:generic")
    market = Market()
    factory = lambda: ObservedUow(database)
    skipped = await run_instrument_selection_once(uow_factory=factory, market_source=market, request=request, clock_ms=clock)
    assert skipped.outcome == "NOT_DUE" and calls == []
    await enable_epoch(database, group)
    if defect == "control_changed":
        with pytest.raises(SelectionJobConflict, match="control"):
            await run_instrument_selection_once(uow_factory=factory, market_source=market, request=request, clock_ms=clock)
        async with database.connect() as conn:
            assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 0
        return
    result = await run_instrument_selection_once(uow_factory=factory, market_source=market, request=request, clock_ms=clock)
    if defect in {"missing", "unknown", "flat"}:
        assert result.outcome == ("COMPUTE_FAILED" if defect == "flat" else "SOURCE_FAILED")
        call_count = len(calls)
        replay = await run_instrument_selection_once(uow_factory=factory, market_source=market, request=request, clock_ms=clock)
        assert replay.outcome == result.outcome and len(calls) == call_count
        async with database.connect() as conn:
            assert await conn.scalar(sa.select(sa.func.count()).select_from(instrument_selection_snapshots)) == 0
            attempt = (await conn.execute(sa.select(instrument_selection_attempts))).mappings().one()
            assert attempt["source_member_count"] == (0 if defect == "unknown" else 23 if defect == "missing" else 24)
            if defect == "flat":
                assert attempt["source_digest"].startswith("sha256:")
                assert source_input.spec.candidate_ids[0] in attempt["reason_code"]
        return
    assert result.outcome == "SNAPSHOT_READY"
    assert len(calls) == 25
    replay = await run_instrument_selection_once(uow_factory=factory, market_source=market, request=request, clock_ms=clock)
    assert replay.outcome == "ALREADY_READY" and len(calls) == 25
    async with PostgresKernelUnitOfWork(database) as uow:
        snapshot = await uow.instrument_selection.get_generic_snapshot(result.selection_snapshot_id)
        assert snapshot.selected_members == compute_generic_selection(source_input).selected_members
        if defect == "empty":
            assert snapshot.selected_members == () and snapshot.ready_count == 0
        assert all(member.qualification_semantic_digest.startswith("sha256:") for member in snapshot.members)
    async with database.connect() as conn:
        for table in ("brc_strategy_universe_materialization_generations", "brc_selection_session_authorities", "brc_trade_tickets", "brc_exchange_commands"):
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
