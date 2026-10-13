from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.orb_session_selection import OrbSessionSelectionSpec
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

D = 1_800_000_000_000 // 86_400_000 * 86_400_000


@pytest.mark.asyncio
async def test_hourly_spec_installs_as_independent_paused_pair_with_frozen_candidate_panel(
    head_template_engine: AsyncEngine,
) -> None:
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT to_regclass('public.brc_orb_session_selection_specs_v1')"
                )
            )
            is not None
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(
            OrbSessionSelectionSpec(), installed_at_ms=D + 1
        )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"
                )
            )
            == "paused"
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_spec_members WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 24
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_spec_events WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 2
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT selection_kind FROM brc_instrument_selection_specs WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == "orb_session_dynamic_v1"
        )
        assert (
            await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_selection_session_authorities WHERE selection_spec_id='SOR_1H_OR_ATR_DYNAMIC_V1'"
                )
            )
            == 0
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert (
            await uow.instrument_selection.get_orb_spec("SOR_1H_OR_ATR_DYNAMIC_V1")
            == OrbSessionSelectionSpec()
        )


@pytest.mark.asyncio
async def test_hourly_snapshot_member_results_are_immutable_independent_and_epoch_bound(
    head_template_engine: AsyncEngine,
) -> None:
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        build_orb_session_period,
        compute_orb_selection,
    )

    spec = OrbSessionSelectionSpec()
    h = 3_600_000
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(spec, installed_at_ms=D + 1)
    windows = tuple(
        SelectionSourceWindow(
            exchange_instrument_id=m,
            input_window_start_ms=D - 23 * h,
            feature_cutoff_at_ms=D + h,
            klines=tuple(
                SelectionKline(
                    open_time_ms=D - 23 * h + i * 900000,
                    close_time_ms=D - 23 * h + (i + 1) * 900000,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(101),
                    low=Decimal(99),
                    quote_volume=Decimal(1000000),
                )
                for i in range(96)
            ),
        )
        for m in spec.candidate_ids
    )
    result = compute_orb_selection(
        spec=spec,
        period=build_orb_session_period(D),
        selection_epoch_id="epoch:orb:pg",
        source_windows=windows,
        decision_at_ms=D + h,
        source_observed_at_ms=D + h + 1,
        created_at_ms=D + h + 2,
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow.instrument_selection.save_orb_snapshot(result)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        assert (
            await uow.instrument_selection.get_orb_snapshot(
                result.snapshot.selection_snapshot_id
            )
            == result
        )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_member_decisions WHERE selection_family='orb_session_dynamic_v1'"
                )
            )
            == 24
        )
    with pytest.raises(Exception, match="immutable"):
        async with head_template_engine.begin() as c:
            await c.execute(
                sa.text(
                    "UPDATE brc_instrument_selection_snapshots SET selected_count=6 WHERE selection_snapshot_id=:sid"
                ),
                {"sid": result.snapshot.selection_snapshot_id},
            )


async def install_static_pair(engine: AsyncEngine):
    from src.trading_kernel.application.advance_strategy_universe import (
        UniverseActivationRequest,
        UniverseActivationStatus,
        advance_strategy_universe,
    )
    from src.trading_kernel.application.install_strategy_universe import (
        UniverseInstallRequest,
        install_strategy_universe,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_EVENT_SPEC_IDS,
        ORB_STATIC_MEMBERS,
    )
    from tests.trading_kernel.integration.universe_activation_support import (
        make_warming_ready,
    )

    result = []
    for event in ORB_EVENT_SPEC_IDS:
        async with PostgresKernelUnitOfWork(engine) as uow:
            r = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=event,
                    runtime_profile_id="tiny-live-v1",
                    owner_policy_id="policy-main",
                    exchange_instrument_ids=ORB_STATIC_MEMBERS,
                    installed_at_ms=D + 10,
                ),
            )
        assert r.universe is not None
        await make_warming_ready(
            engine,
            universe_version_id=r.universe.universe_version_id,
            warm_closed_bar_time_ms=D + 3600000,
            valid_until_ms=D + 7200000,
        )
        async with PostgresKernelUnitOfWork(engine) as uow:
            a = await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=r.universe.universe_version_id,
                    attempted_at_ms=D + 3600001,
                ),
            )
        assert a.status in {
            UniverseActivationStatus.ACTIVATED,
            UniverseActivationStatus.ALREADY_ACTIVE,
        }
        result.append(r.universe.universe_version_id)
    return tuple(result)


@pytest.mark.asyncio
async def test_static_pair_and_owner_intent_drive_daily_job_on_later_session(
    head_template_engine: AsyncEngine,
):
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.domain.generic_selection_jobs import (
        GenericSelectionJobClaim,
    )

    spec = OrbSessionSelectionSpec()
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="orb-test",
                runtime_commit="orb-local-test",
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=D,
            ),
        )
        await uow.instrument_selection.install_orb_spec(spec, installed_at_ms=D + 1)
    await install_static_pair(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        c = await stage_orb_dynamic_selection_mode(
            uow,
            effective_session_start_ms=D + 86400000,
            request=ControlMutationRequest(
                expected_version=1,
                reason="hourly dynamic",
                idempotency_key="orb:first:dynamic",
                owner_identity="owner",
                now_ms=D + 3600100,
            ),
            authentication_strength="totp_step_up",
        )
    assert (
        c.pending_authorization_id and c.selection_epoch_id and c.rollback_baseline_id
    )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        claim = await uow.instrument_selection.claim_orb_selection_job(
            selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,
            session_start_ms=D + 2 * 86400000,
            worker_id="orb:test",
            now_ms=D + 2 * 86400000 + 3600000,
            lease_duration_ms=120000,
        )
    assert isinstance(claim, GenericSelectionJobClaim)
    assert (
        claim.selection_epoch_id == c.selection_epoch_id
        and claim.period_anchor_ms == D + 2 * 86400000
    )
    from src.trading_kernel.domain.instrument_selection import SelectionAttemptOutcome

    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await uow.instrument_selection.complete_selection_failure(
            claim=claim,
            outcome=SelectionAttemptOutcome.SOURCE_FAILED,
            reason_code="SOURCE_TIMEOUT",
            source_member_count=0,
            source_digest=None,
            completed_at_ms=D + 2 * 86400000 + 3600001,
        )
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        preserved = await uow.instrument_selection.get_selection_control(
            spec.strategy_group_id
        )
        assert preserved == c
        next_claim = await uow.instrument_selection.claim_orb_selection_job(
            selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=c.selection_epoch_id,
            session_start_ms=D + 3 * 86400000,
            worker_id="orb:test",
            now_ms=D + 3 * 86400000 + 3600000,
            lease_duration_ms=120000,
        )
        assert isinstance(next_claim, GenericSelectionJobClaim)
        assert next_claim.selection_epoch_id == c.selection_epoch_id
    async with head_template_engine.connect() as connection:
        assert (
            await connection.scalar(
                sa.text("SELECT count(*) FROM brc_exchange_commands")
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed,failed", [(False,False),(True,False),(True,True),(None,False)])
async def test_hourly_first_no_change_commits_exact_pair_epoch_and_owner_proof(head_template_engine, changed, failed):
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
        stage_orb_dynamic_selection_mode,
    )
    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_STATIC_MEMBERS,
        build_orb_session_period,
        compute_orb_selection,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    h=3600000;day=86400000;session=D+day;spec=OrbSessionSelectionSpec()
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        await seed_runtime_authority(uow,RuntimeAuthoritySeedRequest(account_id='orb-test',runtime_commit='orb-local-test',schema_revision=CURRENT_SCHEMA_REVISION,seeded_at_ms=D))
        await uow.instrument_selection.install_orb_spec(spec,installed_at_ms=D+1)
    await install_static_pair(head_template_engine)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        control=await stage_orb_dynamic_selection_mode(uow,effective_session_start_ms=session,
            request=ControlMutationRequest(expected_version=1,reason='dynamic',idempotency_key='orb:first:dynamic',owner_identity='owner',now_ms=D+h+100),authentication_strength='totp_step_up')
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=1,reason='test resume',idempotency_key='orb:first:resume',owner_identity='owner',now_ms=D+h+101),authentication_strength='totp_step_up')
    windows=tuple(SelectionSourceWindow(exchange_instrument_id=m,input_window_start_ms=session-23*h,feature_cutoff_at_ms=session+h,
        klines=tuple(SelectionKline(open_time_ms=session-23*h+i*900000,close_time_ms=session-23*h+(i+1)*900000,
            open=Decimal(100),close=Decimal(100),high=Decimal(101 if i<92 or m in (spec.candidate_ids[:7] if changed else ORB_STATIC_MEMBERS) else 103),
            low=Decimal(99),quote_volume=Decimal(1 if changed is None else 1000000)) for i in range(96))) for m in spec.candidate_ids)
    computation=compute_orb_selection(spec=spec,period=build_orb_session_period(session),selection_epoch_id=control.selection_epoch_id,
        source_windows=windows,decision_at_ms=session+h,source_observed_at_ms=session+h+1,created_at_ms=session+h+2)
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        claim=await uow.instrument_selection.claim_orb_selection_job(selection_spec_id=spec.selection_spec_id,
            selection_epoch_id=control.selection_epoch_id,session_start_ms=session,worker_id='orb:selector',now_ms=session+h,lease_duration_ms=120000)
        await uow.instrument_selection.complete_orb_selection_snapshot(claim=claim,computation=computation,completed_at_ms=session+h+2)
    if changed is False:
        stale=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),
            request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:stale'),clock_ms=lambda:session+h+3)
        assert stale.disposition=='BLOCKED' and stale.reason_code.startswith('ORB_CURRENT_PAIR_')
        from tests.trading_kernel.integration.universe_activation_support import (
            make_warming_ready,
        )
        async with head_template_engine.connect() as connection:
            current_ids=tuple((await connection.execute(sa.text("SELECT p.universe_version_id FROM brc_strategy_universe_current p JOIN brc_strategy_universe_versions u USING(universe_version_id) WHERE u.strategy_group_id='SOR-1H-001'"))).scalars())
        for uid in current_ids:
            await make_warming_ready(head_template_engine,universe_version_id=uid,warm_closed_bar_time_ms=session+h,valid_until_ms=session+2*h)
    result=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,
            session_start_ms=session,worker_id='orb:materializer'),clock_ms=lambda:session+h+3)
    if changed is None:
        assert result.disposition=='VALID_EMPTY_INTENT'
        from src.trading_kernel.application.drain_strategy_entry_vacuum import (
            DrainStrategyEntryVacuumRequest,
            drain_strategy_entry_vacuum_once,
        )
        for tick in range(4,7):
            async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                empty=await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+h+tick))
            if empty.status=='VALID_EMPTY_COMMITTED':break
        assert empty.status=='VALID_EMPTY_COMMITTED'
        async with PostgresKernelUnitOfWork(head_template_engine) as uow:
            final=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
            assert final.authority.authority_outcome=='VALID_EMPTY' and final.authority.authorized_pair is None
            assert final.authority.activation_authorization_id==control.pending_authorization_id
        return
    if changed:
        assert result.disposition=='GENERATION_PENDING'
        async with PostgresKernelUnitOfWork(head_template_engine) as uow:
            generation=await uow.instrument_selection.get_materialization_generation(result.materialization_generation_id)
            assert generation.selection_epoch_id==control.selection_epoch_id
            assert generation.selection_control_version==control.control_version
            assert generation.strategy_group_id==spec.strategy_group_id
        with pytest.raises(Exception,match='Generation source identity is immutable'):
            async with head_template_engine.begin() as connection:
                await connection.execute(sa.text('UPDATE brc_strategy_universe_materialization_generations SET selection_control_version=999 WHERE materialization_generation_id=:gid'),{'gid':generation.materialization_generation_id})
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:materializer')
        outcomes=[]
        for tick in range(4,9):
            progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),request=request,clock_ms=lambda tick=tick:session+h+tick)
            outcomes.append(progress.disposition.value)
            if progress.disposition=='WAITING_VACUUM':
                from src.trading_kernel.application.drain_strategy_entry_vacuum import (
                    DrainStrategyEntryVacuumRequest,
                    drain_strategy_entry_vacuum_once,
                )
                async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                    await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+h+tick))
        assert outcomes[:2]==['GENERATION_DESIRED','WAITING_VACUUM']
        assert outcomes[-1]=='LONG_WARMING'
        from tests.trading_kernel.integration.universe_activation_support import (
            make_warming_ready,
        )
        for tick in range(9,15):
            if failed:
                tick=1800100
            async with head_template_engine.connect() as connection:
                warming=tuple((await connection.execute(sa.text("SELECT universe_version_id FROM brc_strategy_universe_versions WHERE materialization_generation_id=:gid AND lifecycle_state='warming'"),{'gid':generation.materialization_generation_id})).scalars())
            for uid in warming:
                await make_warming_ready(head_template_engine,universe_version_id=uid,warm_closed_bar_time_ms=session+h,valid_until_ms=session+2*h)
            progress=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),request=request,clock_ms=lambda tick=tick:session+h+tick)
            if progress.disposition=='GAP_AUDIT_PENDING':break
        assert progress.disposition=='GAP_AUDIT_PENDING'
        from src.trading_kernel.application.coordinate_selection_materialization import (
            complete_pending_authority_gap_audit,
        )
        from src.trading_kernel.domain.market import ClosedCandle
        from src.trading_kernel.interfaces.authority_gap_audit_source import (
            PublicMarketAuthorityGapAuditSource,
        )
        class Market:
            async def fetch_closed_candles(self, request):
                assert request.timeframe=='1h' and request.limit==1
                return (ClosedCandle(open_time_ms=session,close_time_ms=session+h,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(1000)),)
        active=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(head_template_engine),authority_gap_audit_id=progress.authority_gap_audit_id,
            audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:session+h+(1800101 if failed else 15))
        assert active.disposition==('FALLBACK_PREVIOUS' if failed else 'ACTIVE_NEW')
        if failed:
            async with PostgresKernelUnitOfWork(head_template_engine) as uow:
                kept=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
                assert kept==control
                baseline=await uow.instrument_selection.get_orb_static_baseline(control.rollback_baseline_id)
                assert baseline.rollback_baseline_id==control.rollback_baseline_id
                restored=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
                assert restored.authority.selection_mode=='static_baseline'
                assert restored.authority.activation_authorization_id is None
            return
        await assert_pair_entry_authority(head_template_engine,spec,session,active.selection_authority_id)
        await assert_next_day_continuity(head_template_engine,spec,session)
        return
    assert result.disposition=='NO_CHANGE'
    async with PostgresKernelUnitOfWork(head_template_engine) as uow:
        authority=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        current_control=await uow.instrument_selection.get_selection_control(spec.strategy_group_id)
        assert authority.authority.selection_epoch_id==control.selection_epoch_id
        assert authority.authority.activation_authorization_id==control.pending_authorization_id
        assert authority.authority.selection_control_version==current_control.control_version==3
        assert authority.authority.first_eligible_close_time_ms==session+2*h
        assert current_control.pending_authorization_id is None

    await assert_pair_entry_authority(head_template_engine,spec,session,result.selection_authority_id)
    await assert_next_day_continuity(head_template_engine,spec,session)


async def assert_pair_entry_authority(engine,spec,session,authority_id):
    from src.trading_kernel.application.ingest_signal import (
        resolve_selection_entry_authority,
    )
    async with engine.connect() as connection:
        scopes=tuple((await connection.execute(sa.text("SELECT runtime_scope_id FROM brc_runtime_scopes_current WHERE strategy_group_id='SOR-1H-001' AND lifecycle_state='active' ORDER BY event_spec_id LIMIT 14"))).scalars())
    assert len(scopes)==14
    async with PostgresKernelUnitOfWork(engine) as uow:
        sides=set()
        for scope_id in scopes:
            scope=await uow.signals.get_runtime_scope(scope_id)
            sides.add(scope.position_side)
            decision=await resolve_selection_entry_authority(uow,runtime_scope=scope,birth_selection_authority_id=authority_id,
                observed_close_time_ms=session+7200000,now_ms=session+7200001,allow_current_as_birth=False)
            assert decision.reason_code=="selection_owner_or_policy_blocked"
            assert decision.current_selection_authority_id==authority_id
        assert sides=={'long','short'}


async def assert_next_day_continuity(engine,spec,session):
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        complete_pending_authority_gap_audit,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    day=session+86400000;h=3600000
    planned=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),
        request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=day,worker_id='orb:continuity'),clock_ms=lambda:day+h+1)
    assert planned.disposition=='GAP_AUDIT_PENDING'
    class Market:
        async def fetch_closed_candles(self,request):
            assert request.limit==1 and request.timeframe=='1h'
            return (ClosedCandle(open_time_ms=day,close_time_ms=day+h,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    continued=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=planned.authority_gap_audit_id,audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:day+h+2)
    assert continued.disposition=='PRE_FENCE_CONTINUITY'
    await assert_owner_pause(engine,spec,day)


async def assert_owner_pause(engine,spec,session):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateSelectionMaterializationRequest,
        coordinate_selection_materialization_once,
    )
    from src.trading_kernel.application.owner_control import (
        ControlMutationRequest,
        set_strategy_entry_state,
    )
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    async with PostgresKernelUnitOfWork(engine) as uow:
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.PAUSED,
            request=ControlMutationRequest(expected_version=2,reason='test pause',idempotency_key='orb:pause',owner_identity='owner',now_ms=session+3600100),authentication_strength='session')
    paused=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:pause'),clock_ms=lambda:session+3600101)
    assert paused.disposition=='OWNER_PAUSED'
    async with PostgresKernelUnitOfWork(engine) as uow:
        current=await uow.instrument_selection.get_current_authority_projection(spec.selection_spec_id)
        assert current.authority.blocks_new_entry
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        assert vacuum.blocks_new_entry
    from src.trading_kernel.application.drain_strategy_entry_vacuum import (
        DrainStrategyEntryVacuumRequest,
        drain_strategy_entry_vacuum_once,
    )
    for tick in (102,103):
        async with PostgresKernelUnitOfWork(engine) as uow:
            await drain_strategy_entry_vacuum_once(uow,DrainStrategyEntryVacuumRequest(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,now_ms=session+3600000+tick))
    async with PostgresKernelUnitOfWork(engine) as uow:
        await set_strategy_entry_state(uow,strategy_group_id=spec.strategy_group_id,target_state=StrategyEntryState.ENABLED,
            request=ControlMutationRequest(expected_version=3,reason='test resume',idempotency_key='orb:resumed',owner_identity='owner',now_ms=session+3600200),authentication_strength='totp_step_up')
    resumed=await coordinate_selection_materialization_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),request=CoordinateSelectionMaterializationRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,session_start_ms=session,worker_id='orb:resume'),clock_ms=lambda:session+3600201)
    assert resumed.disposition=='GAP_AUDIT_PENDING'
    with pytest.raises(Exception,match='ORB.*audit'):
        async with engine.begin() as connection:
            await connection.execute(sa.text("UPDATE brc_selection_authority_gap_audits_current SET state='COMPLETE',audited_through_close_time_ms=:through,first_eligible_close_time_ms=:first,audit_scope_digest=:digest,audit_result_digest=:digest,projection_version=projection_version+1 WHERE authority_gap_audit_id=:aid"),{'through':session+3600000,'first':session+7200000,'digest':'sha256:'+'a'*64,'aid':resumed.authority_gap_audit_id})
    from decimal import Decimal

    from src.trading_kernel.application.coordinate_selection_materialization import (
        complete_pending_authority_gap_audit,
    )
    from src.trading_kernel.domain.market import ClosedCandle
    from src.trading_kernel.interfaces.authority_gap_audit_source import (
        PublicMarketAuthorityGapAuditSource,
    )
    with pytest.raises(Exception,match='ORB.*audit'):
        async with engine.begin() as connection:
            await connection.execute(sa.text("UPDATE brc_strategy_entry_vacuums_current SET state='RESOLVED_CONTINUITY',resolved_at_ms=:at,projection_version=projection_version+1 WHERE strategy_group_id='SOR-1H-001' AND state='OWNER_PAUSED'"),{'at':session+3600202})
    class Market:
        async def fetch_closed_candles(self,request):
            return (ClosedCandle(open_time_ms=session,close_time_ms=session+3600000,open=Decimal(100),high=Decimal(101),low=Decimal(99),close=Decimal(100),volume=Decimal(100)),)
    recovered=await complete_pending_authority_gap_audit(uow_factory=lambda:PostgresKernelUnitOfWork(engine),authority_gap_audit_id=resumed.authority_gap_audit_id,audit_source=PublicMarketAuthorityGapAuditSource(Market()),clock_ms=lambda:session+3600202)
    assert recovered.disposition=='PRE_FENCE_CONTINUITY'
    async with PostgresKernelUnitOfWork(engine) as uow:
        vacuum=await uow.instrument_selection.get_current_entry_vacuum(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id)
        assert vacuum is None or not vacuum.blocks_new_entry
