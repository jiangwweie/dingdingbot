from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationOperation,
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    DrainStrategyEntryVacuumRequest,
    VacuumDrainStatus,
    drain_strategy_entry_vacuum_once,
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
from src.trading_kernel.domain.selection_authority import selected_member_set_digest
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    SelectionJobConflict,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_selection_attempts,
    instrument_selection_jobs_current,
    instrument_selection_member_decisions,
    instrument_selection_snapshots,
    strategy_selection_control_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
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
            close = ((revision-1)*3 + step+1)*1000
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
@pytest.mark.parametrize("group", ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"])
async def test_generic_generation_schema_uses_one_exact_previous_event_without_fake_pair(database: AsyncEngine, group: str) -> None:
    source = inputs(group)
    snapshot = compute_generic_selection(source)
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
    async with PostgresKernelUnitOfWork(database) as uow:
        assert await uow.instrument_selection.add_generic_pending_materialization_generation(generation) == generation
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
    async with PostgresKernelUnitOfWork(database) as uow:
        preparation = await uow.instrument_selection.claim_generic_materialization_generation(
            generation.materialization_generation_id,worker_id="prepare-worker",
            now_ms=generation.created_at_ms+1,lease_duration_ms=HOUR//2)
    assert preparation.generation is not None
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
    assert desired.desired_at_ms == generation.created_at_ms+2
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
        await uow.instrument_selection.open_generation_entry_vacuum(fence,
            expected_generation_version=desired.projection_version,
            worker_id="prepare-worker",lease_epoch=preparation.generation.lease_epoch)
        assert await uow.instrument_selection.release_generic_materialization_generation_lease(
            generation.materialization_generation_id,worker_id="prepare-worker",lease_epoch=preparation.generation.lease_epoch)
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
        drained = await drain_strategy_entry_vacuum_once(uow,
            DrainStrategyEntryVacuumRequest(strategy_group_id=group,
                selection_spec_id=source.spec.selection_spec_id,now_ms=generation.created_at_ms+4))
        assert drained.status == VacuumDrainStatus.ENTRY_DRAINED
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
        staged = await advance_strategy_universe(uow, request)
    assert staged.status == UniverseActivationStatus.STAGED
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
