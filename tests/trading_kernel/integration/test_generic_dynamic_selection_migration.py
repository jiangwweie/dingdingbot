from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import advance_exposure_episode
from src.trading_kernel.domain.generic_selection_spec import (
    SpecNumericInstallationEvidence,
    generic_selection_spec,
)
from src.trading_kernel.domain.market import MarketSnapshot
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    SourceProvenanceInsufficient,
    certify_0007_static_comparison_sources,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    ETH,
    NOW_MS,
    mi_flat_snapshot,
    mi_long_snapshot,
    mpg_flat_snapshot,
    mpg_long_snapshot,
)

TARGET_REVISION = "0008_generic_dynamic_selection_v1"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_source", [False, True])
async def test_static_sor_baseline_has_exact_pair_and_hash_reconstruction_after_migration(invalid_source: bool) -> None:
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(run_alembic, url, "upgrade", "0007_exit_profile_authority_v1")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(account_id="baseline-source",runtime_commit="a"*40,
                schema_revision="0007_exit_profile_authority_v1",seeded_at_ms=NOW_MS-1000))
        for side in ("LONG", "SHORT"):
            event = f"event_spec:SOR-001:SOR-{side}:v4"
            async with PostgresKernelUnitOfWork(engine) as uow:
                installed = await install_strategy_universe(uow, UniverseInstallRequest(event_spec_id=event,
                    runtime_profile_id=RUNTIME_PROFILE_ID,owner_policy_id=OWNER_POLICY_ID,exchange_instrument_ids=(ETH,),installed_at_ms=NOW_MS-500))
            assert installed.universe is not None
            universe = installed.universe
            async with engine.begin() as conn:
                await conn.execute(sa.text("UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:now WHERE universe_version_id=:uid"),
                    {"now":NOW_MS,"uid":universe.universe_version_id})
                await conn.execute(sa.text("UPDATE brc_runtime_scopes_current SET lifecycle_state='active',entry_enabled=true,observation_enabled=true,warm_closed_bar_time_ms=:closed,"
                    "warm_completed_at_ms=:now,warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"),
                    {"uid":universe.universe_version_id,"closed":NOW_MS-3600000,"now":NOW_MS,"digest":"sha256:"+"1"*64,"valid":NOW_MS+3600000})
                await conn.execute(sa.text("INSERT INTO brc_strategy_universe_current VALUES(:event,:uid,:digest,'active',1,:now)"),
                    {"event":event,"uid":universe.universe_version_id,"digest":universe.semantic_digest,"now":NOW_MS})
        # This frozen migration helper is test-only source construction, never a runtime old-schema reader.
        source_migration = importlib.import_module("migrations.trading_kernel.versions.0006_sor_dynamic_selection_v0")
        async with engine.begin() as conn:
            savepoint = await conn.begin_nested()
            baseline_id = await conn.run_sync(lambda sync: source_migration._capture_rollback_baseline(sync, now_ms=NOW_MS))
            before = dict((await conn.execute(sa.text("SELECT * FROM brc_strategy_selection_rollback_baselines WHERE rollback_baseline_id=:id"), {"id":baseline_id})).mappings().one())
            if invalid_source:
                await savepoint.rollback()
                before["source_long_universe_version_id"],before["source_short_universe_version_id"] = before["source_short_universe_version_id"],before["source_long_universe_version_id"]
                await conn.execute(sa.text("INSERT INTO brc_strategy_selection_rollback_baselines VALUES(:rollback_baseline_id,:strategy_group_id,:strategy_version_id,"
                    ":source_long_universe_version_id,:source_short_universe_version_id,:semantic_digest,:captured_at_ms)"), before)
            else:
                await savepoint.commit()
        if invalid_source:
            with pytest.raises(AssertionError, match="BASELINE_SOURCE_MISMATCH"):
                await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
            async with engine.connect() as conn:
                assert await conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0007_exit_profile_authority_v1"
                assert await conn.scalar(sa.text("SELECT to_regclass('brc_materialization_generation_event_baselines')")) is None
            return
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()
        async with engine.connect() as conn:
            after = dict((await conn.execute(sa.text("SELECT * FROM brc_strategy_selection_rollback_baselines WHERE rollback_baseline_id=:id"), {"id":baseline_id})).mappings().one())
            rows = (await conn.execute(sa.text("SELECT * FROM brc_selection_rollback_baseline_events WHERE rollback_baseline_id=:id ORDER BY position_side"), {"id":baseline_id})).mappings().all()
            assert len(rows) == 2
            reconstructed = {**after, **{f"source_{row['position_side']}_universe_version_id":row["universe_version_id"] for row in rows}}
            assert reconstructed == before
            assert all(row["comparison_universe_id"] is None for row in rows)
            for table in ("brc_strategy_universe_materialization_generations", "brc_instrument_selection_snapshots", "brc_selection_session_authorities"):
                assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


def test_alembic_import_root_is_the_selected_worktree_not_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "migrations/trading_kernel/alembic.ini"))
    monkeypatch.chdir(tmp_path)
    assert Path(config.get_main_option("prepend_sys_path")).resolve() == root


def test_generic_dynamic_selection_is_the_single_current_schema_head() -> None:
    config = Config("migrations/trading_kernel/alembic.ini")

    assert CURRENT_SCHEMA_REVISION == TARGET_REVISION
    assert ScriptDirectory.from_config(config).get_heads() == [TARGET_REVISION]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group,event", [("MPG-001", "MPG-LONG"), ("MI-001", "MI-LONG")]
)
@pytest.mark.parametrize("triggered", [True, False])
async def test_0007_static_comparison_source_requires_exact_contemporaneous_evidence(
    group: str, event: str, triggered: bool
) -> None:
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(
            run_alembic, url, "upgrade", "0007_exit_profile_authority_v1"
        )
        contract = strategy_contract_for(f"event_spec:{group}:{event}:v3")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="source-neutrality",
                    runtime_commit="a" * 40,
                    schema_revision="0007_exit_profile_authority_v1",
                    seeded_at_ms=NOW_MS - 10000,
                ),
            )
            installed = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=contract.event_spec_id,
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    owner_policy_id=OWNER_POLICY_ID,
                    exchange_instrument_ids=(ETH,),
                    installed_at_ms=NOW_MS - 1000,
                ),
            )
        assert installed.universe is not None
        universe = installed.universe
        template = (
            (mpg_long_snapshot if triggered else mpg_flat_snapshot)()
            if group == "MPG-001"
            else (mi_long_snapshot if triggered else mi_flat_snapshot)()
        )
        projection = build_comparative_universe_projection(
            event_spec_id=contract.event_spec_id,
            universe_version_id=universe.universe_version_id,
            strategy_group_id=group,
            exchange_instrument_ids=(ETH,),
            closed_bar_time_ms=NOW_MS,
            lookback_bars=8 if group == "MPG-001" else 12,
            freshness_window_ms=contract.freshness_window_ms,
            member_windows=(
                ComparativeMemberWindow(
                    exchange_instrument_id=ETH, candles_1h=template.candles_1h
                ),
            ),
        )
        snapshot = MarketSnapshot(
            exchange_instrument_id=ETH,
            trigger_candle_close_time_ms=NOW_MS,
            candles_1h=template.candles_1h,
            candles_4h=template.candles_4h,
            comparative_strength=projection.comparative_strength,
        )
        detector = evaluate_strategy_snapshot(contract, snapshot)
        assert detector.status is (
            DetectorStatus.TRIGGERED if triggered else DetectorStatus.NOT_TRIGGERED
        )
        episode = advance_exposure_episode(
            contract=contract,
            current=None,
            detector_status=detector.status,
            occurred_at_ms=detector.occurred_at_ms,
            observed_at_ms=NOW_MS,
            exchange_instrument_id=ETH,
        ).current
        async with engine.begin() as conn:
            await conn.execute(
                sa.text(
                    "UPDATE brc_strategy_universe_versions SET lifecycle_state='active',activated_at_ms=:time WHERE universe_version_id=:uid"
                ),
                {"time": NOW_MS - 500, "uid": universe.universe_version_id},
            )
            await conn.execute(
                sa.text(
                    "UPDATE brc_runtime_scopes_current SET lifecycle_state='active',observation_enabled=true,entry_enabled=true, warm_closed_bar_time_ms=:closed,warm_completed_at_ms=:completed,warm_readiness_digest=:digest,warm_valid_until_ms=:valid WHERE universe_version_id=:uid"
                ),
                {
                    "uid": universe.universe_version_id,
                    "closed": NOW_MS - 3600000,
                    "completed": NOW_MS - 500,
                    "valid": NOW_MS + 3600000,
                    "digest": "sha256:" + "a" * 64,
                },
            )
            await conn.execute(
                sa.text(
                    "INSERT INTO brc_strategy_universe_current(event_spec_id,universe_version_id,semantic_digest,lifecycle_state,activation_generation,activated_at_ms) VALUES(:event,:uid,:digest,'active',1,:time)"
                ),
                {
                    "event": contract.event_spec_id,
                    "uid": universe.universe_version_id,
                    "digest": universe.semantic_digest,
                    "time": NOW_MS - 500,
                },
            )
        async with engine.connect() as conn:
            scope_id = await conn.scalar(
                sa.text(
                    "SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE universe_version_id=:uid"
                ),
                {"uid": universe.universe_version_id},
            )
        async with PostgresKernelUnitOfWork(engine) as uow:
            await uow.signals.upsert_current_facts(
                runtime_scope_id=scope_id, facts=detector.facts
            )
            await uow.signals.save_exposure_episode(episode, expected_version=0)
            await uow.signals.save_readiness(
                runtime_scope_id=scope_id,
                readiness_state="signal_absent",
                first_blocker="signal_absent",
                signal_event_id=None,
                fact_summary={},
                updated_at_ms=NOW_MS,
            )
            await uow.strategy_universes.save_comparative_projection(projection)
        async with engine.connect() as conn:
            await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            proofs = await certify_0007_static_comparison_sources(conn)
            assert len(proofs) == 1
            assert proofs[0].episode_domain_key == episode.episode_domain_key
            assert proofs[0].observed_close_ms == NOW_MS
            # A restart after the last observed close does not invent a transition.
            assert await certify_0007_static_comparison_sources(conn) == proofs
            stored = (
                (
                    await conn.execute(
                        sa.text("SELECT * FROM brc_exposure_episode_current")
                    )
                )
                .mappings()
                .one()
            )
            assert dict(stored) == episode.model_dump()
        async with engine.begin() as conn:
            await conn.execute(
                sa.text("DELETE FROM brc_comparative_projection_current")
            )
        async with engine.connect() as conn:
            await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            with pytest.raises(
                SourceProvenanceInsufficient, match="SOURCE_PROVENANCE_INSUFFICIENT"
            ):
                await certify_0007_static_comparison_sources(conn)
            assert (
                await conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "0007_exit_profile_authority_v1"
            )
        with pytest.raises(AssertionError, match="SOURCE_PROVENANCE_INSUFFICIENT"):
            await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT to_regclass('brc_comparison_universe_definitions')")) is None
        async with PostgresKernelUnitOfWork(engine) as uow:
            await uow.strategy_universes.save_comparative_projection(projection)
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()  # Stopped cutover discards source prepared statements.
        async with engine.connect() as conn:
            target_row = (await conn.execute(sa.text("SELECT * FROM brc_exposure_episode_current"))).mappings().one()
            assert {key: target_row[key] for key in type(episode).model_fields} == episode.model_dump()
            assert target_row["comparison_transition_revision"] == 0
            assert target_row["comparison_armed_at_ms"] is None
            assert target_row["comparison_source_evidence_digest"] == proofs[0].source_evidence_digest
            assert await conn.scalar(sa.text("SELECT comparison_transition_revision FROM brc_comparison_binding_current WHERE event_spec_id=:event"), {"event":contract.event_spec_id}) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 0
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_certified_spec_installation_is_static_and_does_not_create_runtime_work() -> None:
    name,url = await create_empty_database()
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(run_alembic,url,"upgrade",TARGET_REVISION)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(account_id="spec-installation",runtime_commit="b"*40,
                schema_revision=TARGET_REVISION,seeded_at_ms=NOW_MS))
        for group in ("CPM-RO-001","MPG-001","MI-001","BRF2-001"):
            spec=generic_selection_spec(group)
            certificate=SpecNumericInstallationEvidence(selection_spec_id=spec.selection_spec_id,
                algorithm_semantic_digest=spec.algorithm_semantic_digest,
                checked_cutoffs=463 if spec.cadence_hours==4 else 1852,mismatch_count=0,source_archive_count=96,
                reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",common_numeric_authority="PASS",sor_golden="PASS",spec_cert="PASS")
            async with PostgresKernelUnitOfWork(engine) as uow:
                await uow.instrument_selection.install_generic_spec(spec,installed_at_ms=NOW_MS+1,certification=certificate)
                assert await uow.instrument_selection.get_generic_spec(spec.selection_spec_id)==spec
            async with PostgresKernelUnitOfWork(engine) as uow:
                await uow.instrument_selection.install_generic_spec(spec,installed_at_ms=NOW_MS+2,certification=certificate)
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_generic_dynamic_selection_specs_v1")) == 4
            columns = await conn.run_sync(lambda sync: {
                column["name"] for column in sa.inspect(sync).get_columns("brc_instrument_selection_snapshots")
            })
            assert {"selection_epoch_id", "predecessor_snapshot_id", "predecessor_member_digest"} <= columns
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_control_current WHERE selection_mode<>'static_baseline' OR pending_selection_mode IS NOT NULL")) == 0
            for table in ("brc_instrument_selection_jobs_current","brc_instrument_selection_snapshots","brc_strategy_universe_materialization_generations","brc_selection_session_authorities","brc_trade_tickets","brc_exchange_commands"):
                assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
