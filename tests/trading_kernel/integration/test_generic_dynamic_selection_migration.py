from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    ComparativeUniverseProjection,
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
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    RuntimeAuthorityTransitionRefused,
    arm_acceptance_policy,
    deploy_compatible_upgrade_identity,
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
@pytest.mark.parametrize("source_entry_enabled", [False, True])
async def test_0007_to_0008_identity_rotation_preserves_static_authority(
    source_entry_enabled: bool,
) -> None:
    name, url = await create_empty_database()
    engine = create_async_engine(url)
    source_commit = "a" * 40
    target_commit = "b" * 40
    try:
        await asyncio.to_thread(run_alembic, url, "upgrade", "0007_exit_profile_authority_v1")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(
                account_id="generic-upgrade", runtime_commit=source_commit,
                schema_revision="0007_exit_profile_authority_v1",
                seeded_at_ms=NOW_MS - 1000,
            ))
        if source_entry_enabled:
            async with PostgresKernelUnitOfWork(engine) as uow:
                await arm_acceptance_policy(
                    uow, ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS - 500)
                )
        async with engine.connect() as conn:
            source_policy = (await conn.execute(sa.text(
                "SELECT policy_version, new_entry_submit_enabled FROM brc_owner_policy_current"
            ))).mappings().one()
            source_static = (await conn.execute(sa.text(
                "SELECT strategy_group_id, entry_state FROM brc_strategy_entry_controls_current ORDER BY strategy_group_id"
            ))).mappings().all()
        with pytest.raises(RuntimeAuthorityTransitionRefused, match="exact 0008 schema"):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await deploy_compatible_upgrade_identity(uow,
                    RuntimeAuthoritySeedRequest(account_id="generic-upgrade",
                        runtime_commit=target_commit,schema_revision=TARGET_REVISION,
                        seeded_at_ms=NOW_MS+1000))
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()
        with pytest.raises(RuntimeAuthorityTransitionRefused, match="exact 0008 target"):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await deploy_compatible_upgrade_identity(uow,
                    RuntimeAuthoritySeedRequest(account_id="generic-upgrade",
                        runtime_commit=target_commit,schema_revision="0006_sor_dynamic_selection_v0",
                        seeded_at_ms=NOW_MS+1000))
        async with PostgresKernelUnitOfWork(engine) as uow:
            rotated = await deploy_compatible_upgrade_identity(uow,
                RuntimeAuthoritySeedRequest(account_id="generic-upgrade",
                    runtime_commit=target_commit,schema_revision=TARGET_REVISION,
                    seeded_at_ms=NOW_MS+1000))
        assert rotated.schema_revision == TARGET_REVISION
        assert rotated.runtime_commit == target_commit
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text(
                "SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='schema_revision'"
            )) == TARGET_REVISION
            policy = (await conn.execute(sa.text(
                "SELECT policy_version, new_entry_submit_enabled FROM brc_owner_policy_current"
            ))).mappings().one()
            assert policy["new_entry_submit_enabled"] is False
            assert policy["policy_version"] == source_policy["policy_version"] + int(source_entry_enabled)
            assert (await conn.execute(sa.text(
                "SELECT strategy_group_id, entry_state FROM brc_strategy_entry_controls_current ORDER BY strategy_group_id"
            ))).mappings().all() == source_static
            for table in ("brc_instrument_selection_jobs_current", "brc_instrument_selection_snapshots",
                          "brc_strategy_universe_materialization_generations", "brc_strategy_entry_vacuums_current",
                          "brc_selection_session_authorities", "brc_trade_tickets", "brc_exchange_commands"):
                assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_authority_clock_advances_inside_one_readonly_transaction(head_template_engine) -> None:
    from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
        PostgresInstrumentSelectionRepository,
    )
    async with head_template_engine.connect() as conn:
        await conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        repository = PostgresInstrumentSelectionRepository(conn)
        frozen = await conn.scalar(sa.text("SELECT transaction_timestamp()"))
        first = await repository.read_authority_clock_ms()
        await conn.execute(sa.text("SELECT pg_sleep(0.02)"))
        second = await repository.read_authority_clock_ms()
        assert second > first
        assert await conn.scalar(sa.text("SELECT transaction_timestamp()")) == frozen


@pytest.mark.asyncio
async def test_authority_schema_binds_snapshot_epoch(head_template_engine) -> None:
    from src.trading_kernel.infrastructure.pg_models import (
        selection_session_authorities,
    )
    async with head_template_engine.begin() as conn:
        for column in ("current_close_proof", "membership_freshness", "recovery_grant_proof"):
            nullable_type = selection_session_authorities.c[column].type
            assert await conn.scalar(sa.select(sa.bindparam("proof", None, type_=nullable_type).is_(None))) is True
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id="authority-epoch",runtime_commit="a"*40,
            schema_revision=TARGET_REVISION,seeded_at_ms=NOW_MS))
    async with head_template_engine.connect() as conn:
        columns = await conn.run_sync(lambda c: {x["name"] for x in sa.inspect(c).get_columns("brc_selection_session_authorities")})
        assert {"selection_epoch_id", "selection_control_version"} <= columns
        assert {"current_close_proof", "membership_freshness", "comparison_universe_id", "comparison_transition_revision"} <= columns
        foreign_keys = await conn.run_sync(lambda c: sa.inspect(c).get_foreign_keys("brc_selection_session_authorities"))
        assert any(fk["constrained_columns"] == ["selection_snapshot_id", "selection_spec_id", "selection_epoch_id"]
            and fk["referred_table"] == "brc_instrument_selection_snapshots" for fk in foreign_keys)
    async with head_template_engine.begin() as conn:
        await conn.execute(sa.text("INSERT INTO brc_instrument_selection_specs "
            "(selection_spec_id,strategy_group_id,strategy_version_id,selection_version,selection_kind,algorithm_semantic_digest,status,installed_at_ms) "
            "VALUES('sor-dynamic-selection-v0','SOR-001','sgv:SOR-001:v4',1,'sor_dynamic_v0',:digest,'active',:now) ON CONFLICT DO NOTHING"),
            {"digest":"sha256:"+"a"*64,"now":NOW_MS})
    with pytest.raises(sa.exc.DBAPIError, match="SOR Authority cannot carry Generic epoch"):
        async with head_template_engine.begin() as conn:
            await conn.execute(sa.text("INSERT INTO brc_selection_session_authorities "
                "(selection_authority_id,selection_spec_id,selection_epoch_id,selection_control_version) "
                "VALUES('authority:wrong-epoch','sor-dynamic-selection-v0','generic:1',1)"))
    async with head_template_engine.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM brc_selection_session_authorities")) == 0
    with pytest.raises(sa.exc.DBAPIError, match="SOR Authority forbids Generic proof"):
        async with head_template_engine.begin() as conn:
            await conn.execute(sa.text("INSERT INTO brc_selection_session_authorities "
                "(selection_authority_id,selection_spec_id,current_close_proof) "
                "VALUES('authority:wrong-proof','sor-dynamic-selection-v0','{}'::jsonb)"))


@pytest.mark.asyncio
async def test_generic_job_terminal_states_cannot_expand_sor_contract(head_template_engine) -> None:
    anchor = 86_400_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id="sor-job-terminal",runtime_commit="a"*40,
            schema_revision=TARGET_REVISION,seeded_at_ms=NOW_MS))
    async with head_template_engine.begin() as conn:
        await conn.execute(sa.text("INSERT INTO brc_instrument_selection_specs "
            "(selection_spec_id,strategy_group_id,strategy_version_id,selection_version,selection_kind,algorithm_semantic_digest,status,installed_at_ms) "
            "VALUES('sor-dynamic-selection-v0','SOR-001','sgv:SOR-001:v4',1,'sor_dynamic_v0',:digest,'active',:now) ON CONFLICT DO NOTHING"),
            {"digest":"sha256:"+"a"*64,"now":NOW_MS})
    with pytest.raises(sa.exc.DBAPIError, match="generic_terminal_state"):
        async with head_template_engine.begin() as conn:
            await conn.execute(sa.text("""
                INSERT INTO brc_instrument_selection_jobs_current
                (selection_job_id,selection_spec_id,selection_epoch_id,period_anchor_ms,
                 scheduled_at_ms,feature_cutoff_at_ms,state,first_blocker,
                 attempt_count,projection_version,updated_at_ms)
                VALUES(:job,'sor-dynamic-selection-v0','sor-v0',:anchor,
                       :cutoff,:cutoff,'EXPIRED','SELECTION_PERIOD_EXPIRED',0,1,:cutoff)
            """), {"job":f"selection-job:sor-dynamic-selection-v0:{anchor}",
                    "anchor":anchor,"cutoff":anchor+3_600_000})


async def _insert_0007_comparison_source(
    engine: AsyncEngine, projection: ComparativeUniverseProjection
) -> None:
    """Construct source evidence, never invoke target repositories on old schema."""
    async with engine.begin() as conn:
        assert await conn.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0007_exit_profile_authority_v1"
        )
        await conn.execute(
            sa.text("""
                INSERT INTO brc_comparative_projection_current
                (event_spec_id, universe_version_id, closed_bar_time_ms,
                 member_set_digest, projection_status, failure_reason, projection,
                 observed_at_ms, valid_until_ms, projection_version)
                VALUES (:event, :universe, :closed, :digest, 'ready', NULL,
                        CAST(:payload AS jsonb), :observed, :valid, 1)
            """),
            {
                "event": projection.event_spec_id,
                "universe": projection.universe_version_id,
                "closed": projection.closed_bar_time_ms,
                "digest": projection.member_set_digest,
                "payload": json.dumps(projection.model_dump(mode="json")),
                "observed": projection.observed_at_ms,
                "valid": projection.valid_until_ms,
            },
        )


@pytest.mark.asyncio
async def test_period_column_rename_preserves_existing_sor_job_and_attempt_facts() -> None:
    from scripts.trading_kernel.verify_schema import (
        _generic_source_preservation_manifest,
    )

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    anchor = 1_704_067_200_000
    jid = f"selection-job:sor-dynamic-selection-v0:{anchor}"
    try:
        await asyncio.to_thread(run_alembic, url, "upgrade", "0005_tradfi_instrument_center")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(account_id="period-source", runtime_commit="a"*40,
                schema_revision="0005_tradfi_instrument_center", seeded_at_ms=anchor))
        await asyncio.to_thread(run_alembic, url, "upgrade", "0007_exit_profile_authority_v1")
        async with engine.begin() as conn:
            await conn.execute(sa.text("""
                INSERT INTO brc_instrument_selection_jobs_current
                (selection_job_id,selection_spec_id,session_start_ms,scheduled_at_ms,feature_cutoff_at_ms,state,
                 selection_snapshot_id,first_blocker,attempt_count,next_retry_at_ms,lease_owner,lease_expires_at_ms,projection_version,updated_at_ms)
                VALUES(:jid,'sor-dynamic-selection-v0',:anchor,:cutoff,:cutoff,'SOURCE_FAILED',NULL,'SOURCE_INCOMPLETE',1,NULL,NULL,NULL,3,:done)
            """), {"jid":jid,"anchor":anchor,"cutoff":anchor+3600000,"done":anchor+3600010})
            await conn.execute(sa.text("""
                INSERT INTO brc_instrument_selection_attempts
                (selection_attempt_id,selection_job_id,selection_spec_id,session_start_ms,worker_id,attempt_number,
                 started_at_ms,completed_at_ms,outcome,reason_code,source_member_count,source_digest)
                VALUES('attempt:source',:jid,'sor-dynamic-selection-v0',:anchor,'source-worker',1,:start,:done,'SOURCE_FAILED','SOURCE_INCOMPLETE',23,NULL)
            """), {"jid":jid,"anchor":anchor,"start":anchor+3600000,"done":anchor+3600010})
            before = {table: dict((await conn.execute(sa.text(f"SELECT * FROM {table}"))).mappings().one()) for table in (
                "brc_instrument_selection_jobs_current", "brc_instrument_selection_attempts")}
            source_manifest = await _generic_source_preservation_manifest(conn)
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()
        async with engine.connect() as conn:
            for table, original in before.items():
                row = (await conn.execute(sa.text(f"SELECT * FROM {table}"))).mappings().one()
                assert {key: row["period_anchor_ms" if key=="session_start_ms" else key] for key in original} == original
                assert row["selection_epoch_id"] == "sor-v0"
                assert "session_start_ms" not in row
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_instrument_selection_snapshots")) == 0
            target_manifest = await _generic_source_preservation_manifest(conn)
            assert target_manifest["digest"] == source_manifest["digest"]
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_generic_source_manifest_detects_target_job_corruption() -> None:
    from scripts.trading_kernel.verify_schema import (
        _generic_source_preservation_manifest,
        _verify_preservation,
    )

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    anchor = 1_704_067_200_000
    try:
        await asyncio.to_thread(run_alembic, url, "upgrade", "0005_tradfi_instrument_center")
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(
                account_id="manifest-source", runtime_commit="a" * 40,
                schema_revision="0005_tradfi_instrument_center", seeded_at_ms=anchor,
            ))
        await asyncio.to_thread(run_alembic, url, "upgrade", "0007_exit_profile_authority_v1")
        async with engine.begin() as conn:
            await conn.execute(sa.text("""
                INSERT INTO brc_instrument_selection_jobs_current
                (selection_job_id, selection_spec_id, session_start_ms, scheduled_at_ms,
                 feature_cutoff_at_ms, state, first_blocker, attempt_count,
                 projection_version, updated_at_ms)
                VALUES (:job, 'sor-dynamic-selection-v0', :anchor, :cutoff,
                        :cutoff, 'SOURCE_FAILED', 'SOURCE_INCOMPLETE', 1, 2, :done)
            """), {"job":f"selection-job:sor-dynamic-selection-v0:{anchor}",
                    "anchor":anchor, "cutoff":anchor+3_600_000, "done":anchor+3_600_010})
            source = await _generic_source_preservation_manifest(conn)
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()
        verified = await _verify_preservation(url,
            source_revision="0007_exit_profile_authority_v1",
            expected_digest=source["digest"])
        assert verified["status"] == "pass"
        async with engine.begin() as conn:
            await conn.execute(sa.text("""
                UPDATE brc_instrument_selection_jobs_current
                SET first_blocker='SOURCE_CHANGED'
                WHERE period_anchor_ms=:anchor
            """), {"anchor":anchor})
        corrupted = await _verify_preservation(url,
            source_revision="0007_exit_profile_authority_v1",
            expected_digest=source["digest"])
        assert corrupted["status"] == "fail"
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_source", [False, True])
async def test_static_sor_baseline_has_exact_pair_and_hash_reconstruction_after_migration(invalid_source: bool) -> None:
    from scripts.trading_kernel.verify_schema import (
        _generic_source_preservation_manifest,
    )

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
        async with engine.connect() as conn:
            source_manifest = await _generic_source_preservation_manifest(conn)
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()
        async with engine.connect() as conn:
            after = dict((await conn.execute(sa.text("SELECT * FROM brc_strategy_selection_rollback_baselines WHERE rollback_baseline_id=:id"), {"id":baseline_id})).mappings().one())
            rows = (await conn.execute(sa.text("SELECT * FROM brc_selection_rollback_baseline_events WHERE rollback_baseline_id=:id ORDER BY position_side"), {"id":baseline_id})).mappings().all()
            assert len(rows) == 2
            reconstructed = {**after, **{f"source_{row['position_side']}_universe_version_id":row["universe_version_id"] for row in rows}}
            assert reconstructed == before
            assert all(row["comparison_universe_id"] is None for row in rows)
            target_manifest = await _generic_source_preservation_manifest(conn)
            assert target_manifest["digest"] == source_manifest["digest"]
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
    from scripts.trading_kernel.verify_schema import (
        _generic_source_preservation_manifest,
        _verify_compatible_source,
    )

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
        async with PostgresKernelUnitOfWork(engine) as uow:
            await arm_acceptance_policy(
                uow, ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS - 9000)
            )
        async with engine.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE brc_owner_policy_current SET policy_version=4 "
                "WHERE owner_policy_id='policy-main'"
            ))
        async with PostgresKernelUnitOfWork(engine) as uow:
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
        await _insert_0007_comparison_source(engine, projection)
        source_gate = await _verify_compatible_source(
            url, "0007_exit_profile_authority_v1"
        )
        assert source_gate["status"] == "pass", (
            source_gate["source_shape"]["status"],
            source_gate["migration_gate"],
            source_gate["registry_identity"]["status"],
            source_gate["owner_policy"],
            source_gate["runtime_profile"]["status"],
            source_gate["strategy_controls"]["status"],
            source_gate["capabilities"]["status"],
            source_gate["provenance"]["status"],
        )
        assert source_gate["provenance"]["status"] == "pass"
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
        missing_gate = await _verify_compatible_source(
            url, "0007_exit_profile_authority_v1"
        )
        assert missing_gate["status"] == "fail"
        assert missing_gate["provenance"]["status"] == "fail"
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
        await _insert_0007_comparison_source(engine, projection)
        async with engine.connect() as conn:
            source_manifest = await _generic_source_preservation_manifest(conn)
        await asyncio.to_thread(run_alembic, url, "upgrade", TARGET_REVISION)
        await engine.dispose()  # Stopped cutover discards source prepared statements.
        async with engine.connect() as conn:
            preserved_cache = (await conn.execute(sa.text(
                "SELECT * FROM brc_comparative_projection_current"
            ))).mappings().one()
            assert preserved_cache["universe_version_id"] == universe.universe_version_id
            assert preserved_cache["member_set_digest"] == projection.member_set_digest
            assert preserved_cache["projection"] == projection.model_dump(mode="json")
            assert preserved_cache["comparison_transition_revision"] == 0
            assert preserved_cache["projection_version"] == 1
            target_manifest = await _generic_source_preservation_manifest(conn)
            assert target_manifest["digest"] == source_manifest["digest"]
            target_row = (await conn.execute(sa.text("SELECT * FROM brc_exposure_episode_current"))).mappings().one()
            recovery_fields = {key:value for key,value in target_row.items() if key.startswith("authority_recovery_")}
            assert len(recovery_fields) == 8 and all(value is None for value in recovery_fields.values())
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
            for table in ("brc_instrument_selection_jobs_current", "brc_instrument_selection_attempts",
                "brc_instrument_selection_snapshots", "brc_instrument_selection_member_decisions",
                "brc_strategy_universe_materialization_generations", "brc_strategy_entry_vacuums_current",
                "brc_selection_authority_gap_audits_current", "brc_selection_session_authorities"):
                period_columns = await conn.run_sync(lambda sync, name=table: {
                    c["name"] for c in sa.inspect(sync).get_columns(name)
                })
                assert "period_anchor_ms" in period_columns and "session_start_ms" not in period_columns
            assert await conn.scalar(sa.text("SELECT count(*) FROM brc_strategy_selection_control_current WHERE selection_mode<>'static_baseline' OR pending_selection_mode IS NOT NULL")) == 0
            for table in ("brc_instrument_selection_jobs_current","brc_instrument_selection_snapshots","brc_strategy_universe_materialization_generations","brc_selection_session_authorities","brc_trade_tickets","brc_exchange_commands"):
                assert await conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
    finally:
        await engine.dispose()
        await drop_disposable_database(name)
