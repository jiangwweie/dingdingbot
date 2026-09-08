from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
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
from tests.trading_kernel.support.generic_selection import (
    CUTOFF,
    HOUR,
    inputs,
    qualify_window,
    shift_window,
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
        if group in {"MPG-001", "MI-001"}:
            digest = canonical_digest({"exchange_instrument_ids": source.spec.candidate_ids[:1]})
            comparison_id = "comparison:" + digest[7:]
            await conn.execute(sa.text("INSERT INTO brc_comparison_universe_definitions VALUES(:cid,:digest,1)"), {"cid": comparison_id, "digest": digest})
            await conn.execute(sa.text("INSERT INTO brc_comparison_universe_members VALUES(:cid,:member)"), {"cid": comparison_id, "member": source.spec.candidate_ids[0]})
        await conn.execute(sa.text("""
            INSERT INTO brc_strategy_universe_materialization_generations
            (materialization_generation_id,selection_spec_id,strategy_group_id,strategy_version_id,selection_mode,selection_snapshot_id,
             rollback_baseline_id,period_anchor_ms,desired_member_count,semantic_digest,lifecycle_state,projection_version,created_at_ms)
            VALUES('generation:single',:spec,:sg,:version,'dynamic_selection',:snapshot,NULL,:cutoff,:count,:digest,'PENDING',1,:now)
        """), {"spec":source.spec.selection_spec_id,"sg":group,"version":source.spec.strategy_version_id,
            "snapshot":snapshot.selection_snapshot_id,"cutoff":CUTOFF,"count":len(snapshot.selected_members),"digest":"sha256:"+"a"*64,"now":CUTOFF+HOUR+1})
        await conn.execute(sa.text("""
            INSERT INTO brc_strategy_universe_materialization_targets VALUES('generation:single',:event,:side,:digest,:ordinal)
        """), {"event":source.spec.event_spec_id,"side":source.spec.position_side,"digest":snapshot.member_set_digest,"ordinal":1 if source.spec.position_side=="long" else 2})
        await conn.execute(sa.text("""
            INSERT INTO brc_materialization_generation_event_baselines VALUES('generation:single',:event,:side,'ACTIVE',:uid,:digest,:comparison)
        """), {"event":source.spec.event_spec_id,"side":source.spec.position_side,"uid":uid,
            "digest":selected_member_set_digest(source.spec.candidate_ids[:1]),"comparison":comparison_id})
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
