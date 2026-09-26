from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch

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
    CoordinateGenericSnapshotRequest,
    MaterializationDisposition,
    coordinate_selection_materialization_once,
    prepare_generic_current_close_proof,
)
from src.trading_kernel.application.ingest_signal import (
    resolve_selection_entry_authority,
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
    advance_comparison_bound_exposure_episode,
    advance_exposure_episode,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_materialization import (
    GenericMaterializationGeneration,
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
    GenericSelectionAuthority,
    selected_member_set_digest,
)
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
    SelectionJobConflict,
    generic_authority_from_storage,
    generic_authority_storage_values,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    selection_authority_event_bindings,
    selection_session_authorities,
    strategy_selection_control_current,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_universe_repository import (
    PostgresStrategyUniverseRepository,
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
    mi_long_snapshot,
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
            await uow.instrument_selection.install_generic_spec(spec, installed_at_ms=CUTOFF, certification=SpecNumericInstallationEvidence(
                selection_spec_id=spec.selection_spec_id, algorithm_semantic_digest=spec.algorithm_semantic_digest,
                checked_cutoffs=463 if spec.cadence_hours == 4 else 1852, mismatch_count=0, source_archive_count=96,
                reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb", common_numeric_authority="PASS", sor_golden="PASS", spec_cert="PASS",
            ))
    yield head_template_engine


@pytest.mark.asyncio
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
@pytest.mark.parametrize("normal_parent", [False,True,"commit"])
async def test_prepare_generic_proof_uses_database_clock_and_complete_locked_coverage(database: AsyncEngine, group: str, normal_parent: bool | str) -> None:
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
                with pytest.raises(sa.exc.DBAPIError,match="Generic NO_CHANGE requires exact current active membership"):
                    async with conn.begin_nested():
                        await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
                        await conn.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,
                            **authority.event_binding.model_dump(mode="json")))
                        await conn.execute(sa.text("DELETE FROM brc_strategy_universe_current WHERE event_spec_id=:event"),{"event":source.spec.event_spec_id})
                        await conn.execute(sa.text("SET CONSTRAINTS ALL IMMEDIATE"))
                if normal_parent != "commit":
                    await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
                    await conn.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,
                        **authority.event_binding.model_dump(mode="json")))
            if normal_parent == "commit":
                await enable_epoch(database,group)
                authority = authority.model_copy(update={"selection_control_version":2})
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
                with pytest.raises(ValueError,match="boundary"):
                    async with uow._connection.begin_nested():
                        with patch.object(uow.instrument_selection,"read_authority_clock_ms",new=AsyncMock(side_effect=[
                            proof.authority_granted_at_ms,proof.period.period_expires_at_ms])):
                            await uow.instrument_selection.commit_generic_no_change(authority,expected_current_version=None)
                assert await uow.instrument_selection.get_current_generic_authority(source.spec.selection_spec_id) is None
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
                if normal_parent != "commit":
                    row = (await conn.execute(sa.select(selection_session_authorities))).mappings().one()
                    bindings = tuple((await conn.execute(sa.select(selection_authority_event_bindings))).mappings())
                    assert generic_authority_from_storage(dict(row),spec=source.spec,event_bindings=tuple(dict(b) for b in bindings)) == authority
                assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_authority_current")) == 0
            if cid and normal_parent != "commit":
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
                            {"unexpected_field":True}):
                assert await conn.scalar(sa.text("SELECT brc_generic_close_proof_matches(:sid,CAST(:proof AS jsonb),:at)"),
                    {"sid":snapshot.selection_snapshot_id,"proof":json.dumps({**payload,**changes}),"at":proof.authority_granted_at_ms}) is False
        state = advance_exposure_episode(contract=strategy_contract_for(source.spec.event_spec_id),current=None,
            detector_status=DetectorStatus.NOT_TRIGGERED,occurred_at_ms=None,observed_at_ms=proof.current_final_close_time_ms,
            exchange_instrument_id=snapshot.selected_members[0]).current
        await uow.signals.save_exposure_episode(state,expected_version=0)
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
async def test_generic_empty_snapshot_coordinator_commits_negative_authority(database: AsyncEngine, group: str) -> None:
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
    await enable_epoch(database,group)
    request = CoordinateGenericSnapshotRequest(selection_snapshot_id=snapshot.selection_snapshot_id,worker_id="empty-coordinator")
    results = []
    for tick in range(4):
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


async def enable_epoch(database: AsyncEngine, group: str, epoch: str = "epoch:1") -> None:
    # Isolated repository prerequisite, not an Owner API/activation acceptance.
    async with database.begin() as conn:
        await conn.execute(sa.update(strategy_selection_control_current).where(
            strategy_selection_control_current.c.strategy_group_id == group,
        ).values(selection_mode="dynamic_selection", selection_epoch_id=epoch, control_version=2))


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
@pytest.mark.parametrize("defect", ["epoch_changed", "control_changed", "lease_expired", "lease_reclaimed", "predecessor_changed"])
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
    if defect in {"epoch_changed", "control_changed"}:
        async with database.begin() as conn:
            await conn.execute(sa.update(strategy_selection_control_current).where(
                strategy_selection_control_current.c.strategy_group_id == "MPG-001",
            ).values(control_version=3, selection_epoch_id="epoch:2" if defect == "epoch_changed" else "epoch:1"))
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
    with pytest.raises(SelectionJobConflict):
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
async def test_same_period_in_new_epoch_does_not_reuse_old_job_or_hysteresis(database: AsyncEngine) -> None:
    source = inputs("MPG-001")
    await enable_epoch(database, "MPG-001")
    async with PostgresKernelUnitOfWork(database) as uow:
        original = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:1",
            feature_cutoff_at_ms=CUTOFF, worker_id="epoch:old", now_ms=CUTOFF + 1, lease_duration_ms=1000,
        )
    # A new Owner transition is represented only as a repository prerequisite here.
    await enable_epoch(database, "MPG-001", "epoch:2")
    async with PostgresKernelUnitOfWork(database) as uow:
        fresh = await uow.instrument_selection.claim_generic_selection_job(
            selection_spec_id=source.spec.selection_spec_id, selection_epoch_id="epoch:2",
            feature_cutoff_at_ms=CUTOFF, worker_id="epoch:new", now_ms=CUTOFF + 2, lease_duration_ms=1000,
        )
        assert isinstance(original, GenericSelectionJobClaim) and isinstance(fresh, GenericSelectionJobClaim)
        assert fresh.selection_job_id != original.selection_job_id
        assert fresh.predecessor_snapshot_id is None
        assert await uow.instrument_selection.get_selection_job(selection_spec_id=source.spec.selection_spec_id, period_anchor_ms=CUTOFF, selection_epoch_id="epoch:2") is not None


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
async def test_control_cannot_point_at_another_strategys_selection_spec(database: AsyncEngine) -> None:
    with pytest.raises(sa.exc.DBAPIError, match="Control.*Spec"):
        async with database.begin() as conn:
            await conn.execute(sa.update(strategy_selection_control_current).where(
                strategy_selection_control_current.c.strategy_group_id == "MI-001",
            ).values(selection_spec_id=inputs("MPG-001").spec.selection_spec_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("group,comparison_only", [("CPM-RO-001",False), ("MPG-001",False), ("MI-001",False), ("BRF2-001",False), ("MPG-001",True), ("MI-001",True)])
async def test_generic_generation_schema_uses_one_exact_previous_event_without_fake_pair(database: AsyncEngine, group: str, comparison_only: bool) -> None:
    source = inputs(group)
    if comparison_only:
        source = source.model_copy(update={"member_windows":tuple(qualify_window(
            w.model_copy(update={"candles":source.member_windows[0].candles}),w.exchange_instrument_id==source.spec.candidate_ids[0])
            for w in source.member_windows)})
    snapshot = compute_generic_selection(source)
    if comparison_only:
        assert snapshot.selected_members == source.spec.candidate_ids[:1]
    async with PostgresKernelUnitOfWork(database) as uow:
        await uow.instrument_selection.save_generic_snapshot(snapshot, decision_at_ms=source.decision_at_ms, source_observed_at_ms=source.source_observed_at_ms)
        installed = await install_strategy_universe(uow, UniverseInstallRequest(
            event_spec_id=source.spec.event_spec_id, runtime_profile_id="tiny-live-v1", owner_policy_id="policy-main",
            exchange_instrument_ids=source.spec.candidate_ids[:1], installed_at_ms=CUTOFF-1,
        ))
    assert installed.universe is not None
    uid = installed.universe.universe_version_id
    comparison_id = None
    async with database.begin() as conn:
        # A schema prerequisite, not a Warming/Owner activation certification.
        await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:now WHERE universe_version_id=:uid"), {"now": CUTOFF, "uid": uid})
        await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,observation_enabled=true,warm_closed_bar_time_ms=:closed,"
            "warm_completed_at_ms=:now,warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"),
            {"uid":uid,"closed":CUTOFF-HOUR,"now":CUTOFF,"digest":"sha256:"+"1"*64,"valid":CUTOFF+2*HOUR})
        await conn.execute(sa.text("INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:now)"),
            {"event":source.spec.event_spec_id,"uid":uid,"digest":installed.universe.semantic_digest,"now":CUTOFF})
        if group in {"MPG-001", "MI-001"}:
            digest = canonical_digest({"exchange_instrument_ids": source.spec.candidate_ids[:1]})
            comparison_id = "comparison:" + digest[7:]
            await conn.execute(sa.text("INSERT INTO brc_comparison_universe_definitions VALUES(:cid,:digest,1)"), {"cid": comparison_id, "digest": digest})
            await conn.execute(sa.text("INSERT INTO brc_comparison_universe_members VALUES(:cid,:member)"), {"cid": comparison_id, "member": source.spec.candidate_ids[0]})
            await conn.execute(sa.text("INSERT INTO brc_comparison_binding_current VALUES(:event,:cid,0,:uid)"),
                {"event":source.spec.event_spec_id,"cid":comparison_id,"uid":uid})
    await enable_epoch(database, group)
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
    if group == "CPM-RO-001":
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
    async with database.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='paused' WHERE strategy_group_id=:group"), {"group":group})
    paused = await coordinate_selection_materialization_once(uow_factory=lambda: PostgresKernelUnitOfWork(database),
        request=coordinator_request,clock_ms=lambda:generation.created_at_ms+1)
    assert paused.disposition == MaterializationDisposition.OWNER_PAUSED
    async with database.begin() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_entry_vacuums_current")) == 0
        await conn.execute(sa.text("UPDATE brc_strategy_entry_controls_current SET entry_state='enabled' WHERE strategy_group_id=:group"), {"group":group})
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
        await _assert_generic_target_stages(database, source, generation, target.universe.universe_version_id)
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
        await _assert_generic_target_stages(database, source, generation, target.universe.universe_version_id)
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


async def _assert_generic_target_stages(database, source, generation, uid):
    # Stage-readiness prerequisites only: Coordinator fence/drain is not mocked
    # as completed by this test. No activation or positive grant is requested.
    close = generation.created_at_ms - 1
    await make_warming_ready(database, universe_version_id=uid,
        warm_closed_bar_time_ms=close, valid_until_ms=close+HOUR)
    async with PostgresKernelUnitOfWork(database) as uow:
        lease = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="stage-worker",now_ms=close+10,lease_duration_ms=HOUR//2)
    assert lease.generation is not None
    request = UniverseActivationRequest(universe_version_id=uid, attempted_at_ms=close+30_004,
        operation=UniverseActivationOperation.STAGE_DYNAMIC,
        materialization_lease_owner="stage-worker", materialization_lease_epoch=lease.generation.lease_epoch,
        materialization_generation_id=generation.materialization_generation_id)
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
    async with PostgresKernelUnitOfWork(database) as uow:
        lease = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="stage-worker",now_ms=close+30_004,
            lease_duration_ms=HOUR//2-29_994)
    assert lease.generation is not None
    request = request.model_copy(update={"materialization_lease_epoch":lease.generation.lease_epoch})
    async with PostgresKernelUnitOfWork(database) as uow:
        staged = await advance_strategy_universe(uow, request)
    assert staged.status == UniverseActivationStatus.STAGED
    await _assert_generic_active_new_storage(database,source,generation,uid,close+30_004)
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await advance_strategy_universe(uow, request) == staged
        lease_expired = await advance_strategy_universe(uow, request.model_copy(update={"attempted_at_ms":close+HOUR//2+11}))
        assert lease_expired.reason_code == "DYNAMIC_GENERATION_LEASE_CHANGED"
        expired = await advance_strategy_universe(uow, request.model_copy(update={"attempted_at_ms":close+source.spec.cadence_hours*HOUR}))
        assert expired.reason_code == "GENERATION_SOURCE_PERIOD_EXPIRED"
    async with PostgresKernelUnitOfWork(database) as uow:
        reclaimed = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id, worker_id="stage-worker",
            now_ms=close+HOUR//2+12, lease_duration_ms=60_000)
    assert reclaimed.generation is not None
    assert reclaimed.generation.lease_epoch == lease.generation.lease_epoch + 1
    callback = request.model_copy(update={"attempted_at_ms":close+HOUR//2+13})
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


async def _assert_generic_active_new_storage(database, source, generation, uid, now):
    from src.trading_kernel.infrastructure.pg_signal_repository import (
        PostgresSignalRepository,
    )
    # Schema transaction probe, rolled back intentionally so other staging
    # negative tests continue on the original state. Not runtime activation.
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
            previous = generation.previous_events[0].universe_version_id
            await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='retired',retired_at_ms=:now WHERE universe_version_id=:uid"),{"uid":previous,"now":now})
            await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='retired',entry_enabled=false,observation_enabled=false WHERE universe_version_id=:uid"),{"uid":previous})
            await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:now WHERE universe_version_id=:uid"),{"uid":uid,"now":now})
            await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,observation_enabled=true WHERE universe_version_id=:uid"),{"uid":uid})
            digest = await conn.scalar(sa.text("SELECT semantic_digest FROM brc_strategy_universe_versions WHERE universe_version_id=:uid"),{"uid":uid})
            await conn.execute(sa.text("UPDATE brc_strategy_universe_current SET universe_version_id=:uid,semantic_digest=:digest,activation_generation=activation_generation+1,activated_at_ms=:now WHERE event_spec_id=:event"),{"uid":uid,"digest":digest,"now":now,"event":source.spec.event_spec_id})
            await conn.execute(sa.text("UPDATE brc_strategy_universe_materialization_generations SET lifecycle_state='ACTIVE',activated_at_ms=:now,terminal_at_ms=:now WHERE materialization_generation_id=:gid"),{"gid":generation.materialization_generation_id,"now":now})
            await conn.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='RESOLVED_ACTIVE',resolved_at_ms=:now WHERE source_generation_id=:gid"),{"gid":generation.materialization_generation_id,"now":now})
            cid = None
            revision = None
            if source.spec.strategy_group_id in {"MPG-001","MI-001"}:
                cid = "comparison:"+canonical_digest({"exchange_instrument_ids":source.spec.candidate_ids})[7:]
                revision = await conn.scalar(sa.text("UPDATE brc_comparison_binding_current SET comparison_universe_id=:cid,comparison_transition_revision=comparison_transition_revision+1,source_static_universe_version_id=NULL WHERE event_spec_id=:event RETURNING comparison_transition_revision"),{"cid":cid,"event":source.spec.event_spec_id})
            authority = GenericSelectionAuthority(selection_authority_id="authority:active:"+source.spec.strategy_group_id,
                selection_spec_id=source.spec.selection_spec_id,strategy_group_id=source.spec.strategy_group_id,selection_epoch_id=snapshot.selection_epoch_id,
                selection_snapshot_id=snapshot.selection_snapshot_id,materialization_generation_id=generation.materialization_generation_id,
                authority_sequence=1,owner_control_version=1,selection_control_version=generation.selection_control_version,period=period,
                authority_outcome="ACTIVE_NEW",event_binding=AuthorityEventBinding(event_spec_id=source.spec.event_spec_id,position_side=source.spec.position_side,
                    grant_state="ACTIVE",universe_version_id=uid,member_set_digest=snapshot.member_set_digest),current_close_proof=proof,
                membership_freshness=build_dynamic_membership_freshness(source_snapshot_id=snapshot.selection_snapshot_id,source_member_set_digest=snapshot.member_set_digest,period=period),
                comparison_universe_id=cid,comparison_transition_revision=revision,effective_from_ms=now,created_at_ms=now)
            await conn.execute(sa.insert(selection_session_authorities).values(**generic_authority_storage_values(authority)))
            await conn.execute(sa.insert(selection_authority_event_bindings).values(selection_authority_id=authority.selection_authority_id,**authority.event_binding.model_dump(mode="json")))
            await conn.execute(sa.text("INSERT INTO brc_selection_authority_current VALUES(:spec,:aid,1,:now)"),{"spec":source.spec.selection_spec_id,"aid":authority.selection_authority_id,"now":now})
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
