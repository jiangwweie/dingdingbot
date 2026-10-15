from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.shadow_outcome import ShadowOutcomeSpec
from src.trading_kernel.infrastructure.pg_models import shadow_outcomes_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork

HOUR=3_600_000


def spec(signal_id: str) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(shadow_outcome_id='shadow:path:'+signal_id,signal_event_id=signal_id,
        admission_decision_id=None,source_kind='signal_path',evaluation_kind='generic_signal_path_v1',
        exchange_instrument_id='binance-usdm:BTCUSDT:perpetual',position_side='long',timeframe='1h',
        entry_reference_price=Decimal(100),initial_stop_price=Decimal(95),
        horizon_start_ms=HOUR,horizon_end_ms=25*HOUR,created_at_ms=HOUR,
        reference_at_ms=HOUR,price_basis='signal_closed_bar',path_spec_digest='sha256:'+'a'*64,source_runtime_commit='a'*40)


@pytest.mark.asyncio
async def test_generic_collection_defaults_off_and_quota_is_atomic(head_template_engine: AsyncEngine):
    engine=head_template_engine
    async with engine.connect() as conn:
        row=(await conn.execute(sa.text("SELECT enabled,daily_limit,control_version FROM brc_research_collection_control WHERE control_id='generic_signal_path_v1'"))).one()
    assert row==(False,0,1)
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert not await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:a'),strategy_group_id='CPM-RO-001')
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=control_version+1 WHERE control_id='generic_signal_path_v1'"))
    async def insert(signal_id):
        async with PostgresKernelUnitOfWork(engine) as uow:
            return await uow.shadow_outcomes.add_signal_path_if_enabled(spec(signal_id),strategy_group_id='CPM-RO-001')
    results=await asyncio.gather(insert('signal:a'),insert('signal:b'))
    assert sorted(results)==[False,True]
    assert not await insert('signal:a') or not await insert('signal:b')
    async with engine.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(shadow_outcomes_current))==1
        count=await conn.scalar(sa.text("SELECT admitted_count FROM brc_research_collection_daily WHERE day_start_ms=0"))
        assert count==1
    from scripts.trading_kernel.configure_research_collection import _parser, configure
    shown=await configure(_parser().parse_args(['--database-url',engine.url.render_as_string(hide_password=False),
        '--show','--day-start-ms','0']))
    assert shown['control']['daily_limit']==1
    assert shown['coverage']['coverage_counts']['CPM-RO-001/01']['admitted']==1
    assert shown['coverage']['coverage_counts']['CPM-RO-001/01']['skipped']>=1
    assert shown['coverage']['skipped_budget']==shown['coverage']['skipped_count']
    assert shown['sample_population']=='quota_limited_prospective'


@pytest.mark.asyncio
async def test_signal_path_retry_backoff_skips_bad_oldest_and_terminates(head_template_engine: AsyncEngine):
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=2,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:a'),strategy_group_id='CPM-RO-001')
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:b'),strategy_group_id='CPM-RO-001')
    now=25*HOUR
    async with PostgresKernelUnitOfWork(engine) as uow:
        first=await uow.shadow_outcomes.claim_one_due(worker_id='w',now_ms=now,lease_until_ms=now+1000)
        assert first and first.spec.signal_event_id=='signal:a'
        assert await uow.shadow_outcomes.retry_signal_path(claim=first,now_ms=now,reason='ConnectionError')
    async with PostgresKernelUnitOfWork(engine) as uow:
        other=await uow.shadow_outcomes.claim_one_due(worker_id='w',now_ms=now,lease_until_ms=now+2*HOUR)
        assert other and other.spec.signal_event_id=='signal:b'
    for tick in (now+60_000,now+6*60_000,now+21*60_000):
        async with PostgresKernelUnitOfWork(engine) as uow:
            claim=await uow.shadow_outcomes.claim_one_due(worker_id='w',now_ms=tick,lease_until_ms=tick+1000)
            assert claim and claim.spec.signal_event_id=='signal:a'
            again=await uow.shadow_outcomes.retry_signal_path(claim=claim,now_ms=tick,reason='TimeoutError')
    assert not again
    async with engine.connect() as conn:
        row=(await conn.execute(sa.select(shadow_outcomes_current.c.status,shadow_outcomes_current.c.attempt_count,
            shadow_outcomes_current.c.completion_reason).where(shadow_outcomes_current.c.signal_event_id=='signal:a'))).one()
        assert row==('unavailable',4,'TimeoutError')


@pytest.mark.asyncio
async def test_generic_signal_path_projects_exact_summary_with_no_execution_writes(head_template_engine: AsyncEngine):
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.observation_worker import (
        ObservationWorkerRequest,
        run_observation_worker_once,
    )
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:path'),strategy_group_id='CPM-RO-001')
    class Source:
        calls=0
        async def fetch_closed_candles(self, request):
            self.calls+=1
            assert request.limit==24 and request.since_ms==HOUR
            return tuple(ClosedCandle(open_time_ms=i*HOUR,close_time_ms=(i+1)*HOUR,
                open=Decimal(100),high=Decimal(106 if i==1 else 125 if i==2 else 101),
                low=Decimal(99 if i==1 else 94 if i==2 else 98),close=Decimal(100),volume=Decimal(1))
                for i in range(1,25))
    source=Source()
    now=25*HOUR
    result=await run_observation_worker_once(lambda:PostgresKernelUnitOfWork(engine),source,
        ObservationWorkerRequest(worker_id='research',runtime_commit='test',schema_revision='0012_generic_signal_path_v1',
            now_ms=now,lease_until_ms=now+30_000,timeout_seconds=1,retry_interval_ms=1000,prefer_shadow=True))
    assert result.status.value=='shadow_completed' and source.calls==1
    async with engine.connect() as conn:
        row=(await conn.execute(sa.select(shadow_outcomes_current).where(shadow_outcomes_current.c.signal_event_id=='signal:path'))).mappings().one()
        assert row['mfe_r']==Decimal(5) and row['mae_r']==Decimal('1.2')
        assert row['path_metrics']['levels']['3R']['order_vs_stop']=='same_bar_ambiguous'
        assert await conn.scalar(sa.text('SELECT count(*) FROM brc_trade_tickets'))==0
        assert await conn.scalar(sa.text('SELECT count(*) FROM brc_exchange_commands'))==0


@pytest.mark.asyncio
async def test_generic_signal_path_readonly_view_preserves_missing_ticket_and_review(head_template_engine: AsyncEngine):
    from src.trading_kernel.interfaces.read_signal_path import read_signal_path
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:research'),strategy_group_id='CPM-RO-001')
    before=await read_signal_path(engine,signal_event_id='signal:research')
    assert before and before.path_initial_risk_per_unit==Decimal(5)
    assert before.ticket_id is None and before.review_id is None and before.review_metrics is None
    assert before.ticket_frozen_stop_risk is None
    assert before.admission_status is None
    assert await read_signal_path(engine,signal_event_id='signal:absent') is None


@pytest.mark.asyncio
async def test_0011_to_0012_preserves_existing_shadow_and_starts_collection_off():
    """Upgrade a real source database, retaining every existing Shadow column."""
    from uuid import uuid4

    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    from tests.trading_kernel.support.postgres import (
        TEST_POSTGRES_ADMIN_DSN,
        async_database_url,
        drop_database,
        run_alembic,
    )
    name='brc_kernel_test_'+uuid4().hex[:12]
    admin=await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{name}"')
    url=async_database_url(name)
    engine=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0011_orb_session_1h_v1')
        async with engine.begin() as conn:
            await conn.execute(sa.text("""INSERT INTO brc_shadow_outcomes_current
                (shadow_outcome_id,signal_event_id,admission_decision_id,source_kind,status,evaluation_kind,
                 exchange_instrument_id,position_side,timeframe,entry_reference_price,initial_stop_price,
                 initial_risk_per_unit,horizon_start_ms,horizon_end_ms,projection_version,created_at_ms)
                VALUES ('shadow:old','signal:old','admission:old','portfolio_rejection','pending',
                'fixed_horizon_excursion_v1','binance-usdm:BTCUSDT:perpetual','long','1h',100,95,5,
                3600000,90000000,1,3600000)"""))
        from scripts.trading_kernel.verify_schema import (
            _signal_path_source_preservation_manifest,
            _source_0011_table_columns,
            _verify_exact_metadata_shape,
        )
        async with engine.connect() as conn:
            before=(await conn.execute(sa.text("SELECT * FROM brc_shadow_outcomes_current WHERE signal_event_id='signal:old'"))).mappings().one()
            frozen=dict(before)
            shape=await _verify_exact_metadata_shape(conn,expected_columns=_source_0011_table_columns())
            assert shape['status']=='pass'
            prior=await _signal_path_source_preservation_manifest(conn)
        await engine.dispose()
        run_alembic(url,'upgrade','0012_generic_signal_path_v1')
        engine=create_async_engine(url)
        async with engine.connect() as conn:
            after=(await conn.execute(sa.text("SELECT * FROM brc_shadow_outcomes_current WHERE signal_event_id='signal:old'"))).mappings().one()
            assert {key:after[key] for key in frozen}==frozen
            assert after['path_metrics'] is None and after['attempt_count']==0
            assert (await _signal_path_source_preservation_manifest(conn))['digest']==prior['digest']
            assert not await conn.scalar(sa.text("SELECT enabled FROM brc_research_collection_control"))
    finally:
        await engine.dispose()
        await drop_database(admin,name)
        await admin.close()


@pytest.mark.asyncio
async def test_collection_pause_stops_due_research_claims(head_template_engine: AsyncEngine):
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:paused'),strategy_group_id='CPM-RO-001')
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=false,control_version=3"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.claim_one_due(worker_id='test',now_ms=25*HOUR,lease_until_ms=25*HOUR+1000) is None
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,control_version=4"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        claimed=await uow.shadow_outcomes.claim_one_due(worker_id='test',now_ms=25*HOUR,lease_until_ms=25*HOUR+1000)
        assert claimed and claimed.spec.signal_event_id=='signal:paused'
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=false,control_version=5"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.claim_one_due(worker_id='test',now_ms=25*HOUR+1001,lease_until_ms=25*HOUR+2000) is None


@pytest.mark.asyncio
async def test_research_collection_cli_requires_exact_revision_and_audits_enable(head_template_engine: AsyncEngine):
    from scripts.trading_kernel.configure_research_collection import _parser, configure
    engine=head_template_engine
    url=engine.url.render_as_string(hide_password=False)
    args=_parser().parse_args(['--database-url',url,'--expected-version','1','--daily-limit','2',
        '--enabled','--owner-identity','owner','--reason','approved prospective trial'])
    updated=await configure(args)
    assert updated['control_version']==2 and updated['enabled']
    with pytest.raises(ValueError,match='version changed'):
        await configure(args)
    async with engine.connect() as conn:
        row=(await conn.execute(sa.text('SELECT enabled,daily_limit,control_version FROM brc_research_collection_control'))).one()
        event=(await conn.execute(sa.text('SELECT enabled,daily_limit,owner_identity FROM brc_research_collection_events'))).one()
        assert row==(True,2,2) and event==(True,2,'owner')


@pytest.mark.asyncio
async def test_0011_source_to_0012_identity_rotation_preserves_registry_and_policy():
    from uuid import uuid4

    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.trading_kernel.infrastructure.runtime_authority_seed import (
        RuntimeAuthoritySeedRequest,
        deploy_compatible_upgrade_identity,
        seed_runtime_authority,
    )
    from tests.trading_kernel.support.postgres import (
        TEST_POSTGRES_ADMIN_DSN,
        async_database_url,
        drop_database,
        run_alembic,
    )
    name='brc_kernel_test_'+uuid4().hex[:12]
    admin=await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{name}"')
    url=async_database_url(name)
    engine=create_async_engine(url)
    try:
        run_alembic(url,'upgrade','0011_orb_session_1h_v1')
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(
                account_id='test-account',runtime_commit='a'*40,
                schema_revision='0011_orb_session_1h_v1',seeded_at_ms=10_000))
        from src.trading_kernel.application.owner_control import (
            ControlMutationRequest,
            set_global_entry_state,
        )
        from src.trading_kernel.infrastructure.runtime_authority_seed import (
            ArmAcceptancePolicyRequest,
            arm_acceptance_policy,
        )
        # Build production-shaped, paused version>=4 through official local
        # policy transitions; this disposable database has no exposure.
        for index in range(2):
            async with PostgresKernelUnitOfWork(engine) as uow:
                await arm_acceptance_policy(uow,ArmAcceptancePolicyRequest(armed_at_ms=10_001+index*2))
                current=await uow.entry_admission.get_owner_policy('policy-main')
                await set_global_entry_state(uow,owner_policy_id='policy-main',enabled=False,
                    request=ControlMutationRequest(expected_version=current.policy_version,
                        reason='source fixture paused',idempotency_key=f'source-fixture-pause:{index}',
                        owner_identity='test-owner',now_ms=10_002+index*2),authentication_strength='session')
        async with engine.connect() as conn:
            before=(await conn.execute(sa.text("SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='registry_semantic_hash'"))).scalar_one()
        from scripts.trading_kernel.verify_schema import (
            _verify_generic_selection_source,
            _verify_preservation,
        )
        source_gate=await _verify_generic_selection_source(url,'0011_orb_session_1h_v1')
        assert source_gate['status']=='pass',{key:value for key,value in source_gate.items() if isinstance(value,dict) and value.get('status')=='fail'}
        digest=source_gate['preservation_manifest']['digest']
        await engine.dispose()
        run_alembic(url,'upgrade','0012_generic_signal_path_v1')
        preserved=await _verify_preservation(url,source_revision='0011_orb_session_1h_v1',expected_digest=digest)
        assert preserved['status']=='pass',preserved
        engine=create_async_engine(url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await deploy_compatible_upgrade_identity(uow,RuntimeAuthoritySeedRequest(
                account_id='test-account',runtime_commit='b'*40,
                schema_revision='0012_generic_signal_path_v1',seeded_at_ms=20_000))
        async with engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='schema_revision'"))=='0012_generic_signal_path_v1'
            assert await conn.scalar(sa.text("SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='registry_semantic_hash'"))==before
            assert not await conn.scalar(sa.text("SELECT enabled FROM brc_research_collection_control"))
    finally:
        await engine.dispose()
        await drop_database(admin,name)
        await admin.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['network','timeout'])
async def test_generic_path_worker_network_timeout_uses_durable_retry_without_trading_writes(head_template_engine: AsyncEngine,failure):
    from src.trading_kernel.interfaces.observation_worker import (
        ObservationWorkerRequest,
        run_observation_worker_once,
    )
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:timeout'),strategy_group_id='CPM-RO-001')
    class Unavailable:
        async def fetch_closed_candles(self,_):
            if failure=='network':
                raise ConnectionError('network unavailable')
            await asyncio.Event().wait()
    now=25*HOUR
    request=ObservationWorkerRequest(worker_id='research',runtime_commit='a'*40,
        schema_revision='0012_generic_signal_path_v1',now_ms=now,lease_until_ms=now+30_000,
        timeout_seconds=.01,retry_interval_ms=1000,prefer_shadow=True)
    failed=await run_observation_worker_once(lambda:PostgresKernelUnitOfWork(engine),Unavailable(),request)
    assert failed.status.value=='shadow_retry_scheduled' and failed.detail==('ConnectionError' if failure=='network' else 'TimeoutError')
    async with engine.connect() as conn:
        row=(await conn.execute(sa.select(shadow_outcomes_current).where(
            shadow_outcomes_current.c.signal_event_id=='signal:timeout'))).mappings().one()
        assert row['status']=='pending' and row['attempt_count']==1 and row['next_attempt_at_ms']==now+60_000
        assert await conn.scalar(sa.text('SELECT count(*) FROM brc_trade_tickets'))==0
        assert await conn.scalar(sa.text('SELECT count(*) FROM brc_exchange_commands'))==0


@pytest.mark.asyncio
@pytest.mark.parametrize('column,value', [('reference_at_ms',None),('path_spec_digest',None),('initial_stop_price',Decimal(101))])
async def test_generic_path_rejects_frozen_reference_mutation(head_template_engine: AsyncEngine,column,value):
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:frozen'),strategy_group_id='CPM-RO-001')
    with pytest.raises(sa.exc.DBAPIError):
        async with engine.begin() as conn:
            await conn.execute(sa.update(shadow_outcomes_current)
                .where(shadow_outcomes_current.c.signal_event_id=='signal:frozen').values({column:value}))


@pytest.mark.asyncio
async def test_failed_legacy_shadow_cannot_starve_new_signal_path(head_template_engine: AsyncEngine):
    engine=head_template_engine
    legacy=ShadowOutcomeSpec(shadow_outcome_id='shadow:legacy',signal_event_id='signal:legacy',
        admission_decision_id='admission:legacy',source_kind='portfolio_rejection',evaluation_kind='fixed_horizon_excursion_v1',
        exchange_instrument_id='binance-usdm:BTCUSDT:perpetual',position_side='long',timeframe='1h',
        entry_reference_price=Decimal(100),initial_stop_price=Decimal(95),horizon_start_ms=HOUR,
        horizon_end_ms=24*HOUR,created_at_ms=HOUR)
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.shadow_outcomes.add_pending(legacy)
        await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:new'),strategy_group_id='CPM-RO-001')
    async with PostgresKernelUnitOfWork(engine) as uow:
        first=await uow.shadow_outcomes.claim_one_due(worker_id='w',now_ms=25*HOUR,lease_until_ms=25*HOUR+1000)
        assert first and first.spec.signal_event_id=='signal:legacy'
        await uow.shadow_outcomes.release_expired_claim(claim=first)
    async with PostgresKernelUnitOfWork(engine) as uow:
        second=await uow.shadow_outcomes.claim_one_due(worker_id='w',now_ms=25*HOUR,lease_until_ms=25*HOUR+1000)
        assert second and second.spec.signal_event_id=='signal:new'


@pytest.mark.asyncio
async def test_generic_terminal_cannot_omit_threshold_evidence(head_template_engine: AsyncEngine):
    engine=head_template_engine
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.shadow_outcomes.add_signal_path_if_enabled(spec('signal:pseudo'),strategy_group_id='CPM-RO-001')
    with pytest.raises(sa.exc.DBAPIError):
        async with engine.begin() as conn:
            await conn.execute(sa.update(shadow_outcomes_current)
                .where(shadow_outcomes_current.c.signal_event_id=='signal:pseudo')
                .values(status='completed',max_favorable_price=Decimal(125),max_adverse_price=Decimal(94),
                    mfe_r=Decimal(5),mae_r=Decimal('1.2'),observed_through_ms=25*HOUR,
                    observed_bar_count=24,completion_reason='signal_path_observed',completed_at_ms=25*HOUR))


@pytest.mark.asyncio
async def test_generic_sampling_rejects_legacy_insert_bypass_and_digest_drift(head_template_engine: AsyncEngine):
    engine=head_template_engine
    frozen=spec('signal:identity')
    async with PostgresKernelUnitOfWork(engine) as uow:
        with pytest.raises(ValueError,match='quota-controlled'):
            await uow.shadow_outcomes.add_pending(frozen)
    async with engine.begin() as conn:
        await conn.execute(sa.text("UPDATE brc_research_collection_control SET enabled=true,daily_limit=1,control_version=2"))
    async with PostgresKernelUnitOfWork(engine) as uow:
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(frozen,strategy_group_id='CPM-RO-001')
        assert await uow.shadow_outcomes.add_signal_path_if_enabled(frozen,strategy_group_id='CPM-RO-001')
    async with PostgresKernelUnitOfWork(engine) as uow:
        with pytest.raises(ValueError,match='identity conflict'):
            await uow.shadow_outcomes.add_signal_path_if_enabled(
                frozen.model_copy(update={'path_spec_digest':'sha256:'+'b'*64}),strategy_group_id='CPM-RO-001')
    async with engine.connect() as conn:
        assert await conn.scalar(sa.select(sa.func.count()).select_from(shadow_outcomes_current))==1
        assert await conn.scalar(sa.text('SELECT admitted_count FROM brc_research_collection_daily'))==1


@pytest.mark.asyncio
async def test_research_savepoint_restores_settings_and_does_not_swallow_connection_loss(head_template_engine: AsyncEngine):
    from src.trading_kernel.infrastructure.pg_repositories import (
        PostgresShadowOutcomeRepository,
    )
    engine=head_template_engine
    async with engine.begin() as connection:
        repo=PostgresShadowOutcomeRepository(connection)
        await connection.execute(sa.text("SET LOCAL lock_timeout='3s'"))
        await connection.execute(sa.text("SET LOCAL statement_timeout='4s'"))
        for fail in (False, True):
            async with repo.isolate_collection(signal_event_id='signal:settings',stage='test'):
                assert await connection.scalar(sa.text("SHOW lock_timeout"))=='100ms'
                assert await connection.scalar(sa.text("SHOW statement_timeout"))=='500ms'
                if fail:
                    await connection.execute(sa.text('SELECT 1/0'))
            assert await connection.scalar(sa.text("SHOW lock_timeout"))=='3s'
            assert await connection.scalar(sa.text("SHOW statement_timeout"))=='4s'
            assert await connection.scalar(sa.text('SELECT 1'))==1
    with pytest.raises(sa.exc.DBAPIError):
        async with engine.begin() as connection:
            repo=PostgresShadowOutcomeRepository(connection)
            async with repo.isolate_collection(signal_event_id='signal:connection-loss',stage='test'):
                pid=await connection.scalar(sa.text('SELECT pg_backend_pid()'))
                async with engine.begin() as killer:
                    assert await killer.scalar(sa.text('SELECT pg_terminate_backend(:pid)'),{'pid':pid})
                await connection.execute(sa.text('SELECT 1'))
