from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.domain.generic_selection_jobs import (
    GenericSelectionJobClaim,
    selection_job_identity,
)
from src.trading_kernel.domain.instrument_selection import (
    SelectionKline,
)
from src.trading_kernel.domain.orb_session_selection import OrbSessionSelectionSpec

D=1704067200000
H=3600000


@pytest.mark.asyncio
async def test_hourly_selector_claims_exact_day_epoch_then_reads_outside_transaction_and_commits_once():
    spec=OrbSessionSelectionSpec();epoch='epoch:orb:runner'
    claim=GenericSelectionJobClaim(selection_job_id=selection_job_identity(spec.selection_spec_id,D,epoch),
        selection_spec_id=spec.selection_spec_id,selection_epoch_id=epoch,selection_control_version=2,period_anchor_ms=D,
        worker_id='orb-runner',attempt_number=1,projection_version=2,started_at_ms=D+H,lease_expires_at_ms=D+H+120000)
    repo=SimpleNamespace(get_orb_spec=AsyncMock(return_value=spec),claim_orb_selection_job=AsyncMock(return_value=claim),
        complete_orb_selection_snapshot=AsyncMock())
    active=0;calls=[]
    @asynccontextmanager
    async def factory():
        nonlocal active
        active+=1
        try:yield SimpleNamespace(instrument_selection=repo)
        finally:active-=1
    class Market:
        async def fetch_selection_klines(self,request):
            assert active==0
            calls.append(request)
            return tuple(SelectionKline(open_time_ms=D-23*H+i*900000,close_time_ms=D-23*H+(i+1)*900000,
                    open=Decimal(100),close=Decimal(100),high=Decimal(101),low=Decimal(99),quote_volume=Decimal(1000000)) for i in range(96))
    result=await run_instrument_selection_once(uow_factory=factory,market_source=Market(),
        request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,selection_epoch_id=epoch,
            period_anchor_ms=D,worker_id='orb-runner'),clock_ms=lambda:D+H+1)
    assert result.outcome=='SNAPSHOT_READY' and result.ready_count==24 and result.selected_count==7
    assert len(calls)==24
    repo.complete_orb_selection_snapshot.assert_awaited_once()
    assert repo.claim_orb_selection_job.call_args.kwargs["lease_duration_ms"]>=120000
    c=repo.complete_orb_selection_snapshot.call_args.kwargs['computation']
    assert c.snapshot.selection_epoch_id==epoch and c.snapshot.eligibility_not_before_ms==D+2*H


@pytest.mark.asyncio
async def test_hourly_runtime_dispatch_preserves_owner_epoch_on_later_day(monkeypatch):
    from src.trading_kernel.application.run_instrument_selection import (
        RunInstrumentSelectionResult,
    )
    from src.trading_kernel.domain.selection_authority import (
        SelectionControl,
        SelectionMode,
    )
    from src.trading_kernel.interfaces.selection_runtime_worker import (
        SelectionRuntimeRequest,
        run_selection_runtime_once,
    )
    spec=OrbSessionSelectionSpec();session=D+2*24*H
    control=SelectionControl(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,
        selection_mode=SelectionMode.STATIC_BASELINE,pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
        pending_effective_period_anchor_ms=D,pending_authorization_id='owner:orb:first',control_version=2,
        rollback_baseline_id='baseline:orb:first',selection_epoch_id='epoch:orb:first',updated_at_ms=D)
    repo=SimpleNamespace(get_selection_control=AsyncMock(return_value=control),get_orb_spec=AsyncMock(return_value=spec))
    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(instrument_selection=repo,owner_controls=SimpleNamespace(get_strategy_control=AsyncMock(return_value=SimpleNamespace(entry_state='enabled'))))
    run=AsyncMock(return_value=RunInstrumentSelectionResult(outcome='SNAPSHOT_READY',selection_job_id='job:orb',selection_snapshot_id='snapshot:orb'))
    monkeypatch.setattr('src.trading_kernel.interfaces.selection_runtime_worker.run_instrument_selection_once',run)
    result=await run_selection_runtime_once(uow_factory=factory,market_source=object(),
        request=SelectionRuntimeRequest(selection_spec_id=spec.selection_spec_id,strategy_group_id=spec.strategy_group_id,worker_id='orb',now_ms=session+H),clock_ms=lambda:session+H)
    assert result.status=='snapshot_ready'
    sent=run.call_args.kwargs['request']
    assert sent.selection_epoch_id==control.selection_epoch_id and sent.period_anchor_ms==session
    assert sent.lease_duration_ms>=120000


@pytest.mark.asyncio
async def test_hourly_readiness_host_refreshes_staged_pair_without_generic_identity(monkeypatch):
    from src.trading_kernel.application.ports import RuntimeScopeSnapshot
    from src.trading_kernel.domain.selection_authority import (
        SelectionControl,
        SelectionMode,
    )
    from src.trading_kernel.interfaces.selection_runtime_worker import (
        CurrentFactRefreshRuntimeRequest,
        run_current_fact_refresh_runtime_once,
    )
    spec=OrbSessionSelectionSpec()
    control=SelectionControl(strategy_group_id=spec.strategy_group_id,selection_spec_id=spec.selection_spec_id,selection_mode=SelectionMode.DYNAMIC_SELECTION,
        pending_selection_mode=None,pending_effective_period_anchor_ms=None,pending_authorization_id=None,control_version=3,rollback_baseline_id='baseline:orb',selection_epoch_id='epoch:orb',updated_at_ms=D)
    scope=RuntimeScopeSnapshot(runtime_scope_id='scope:orb:staged',strategy_group_id=spec.strategy_group_id,strategy_version_id=spec.strategy_version_id,event_spec_id=spec.event_spec_ids[0],
        runtime_profile_id='tiny-live-v1',owner_policy_id='policy-main',exchange_instrument_id=spec.candidate_ids[0],position_side='long',universe_version_id='orb:staged',
        universe_semantic_digest='sha256:'+'a'*64,lifecycle_state='staged',observation_enabled=False,entry_enabled=False,scope_version=2,observation_generation=3)
    repo=SimpleNamespace(get_selection_control=AsyncMock(return_value=control),get_current_entry_vacuum=AsyncMock(return_value=SimpleNamespace(source_generation_id='generation:orb',state='RECONFIGURING',drained_at_ms=D+H)))
    universes=SimpleNamespace(get_current=AsyncMock(return_value=None),get_generation_universe_targets=AsyncMock(return_value=(SimpleNamespace(universe_version_id=scope.universe_version_id,event_spec_id=scope.event_spec_id,lifecycle_state=SimpleNamespace(value='staged')),)))
    @asynccontextmanager
    async def factory():
        yield SimpleNamespace(instrument_selection=repo,strategy_universes=universes,signals=SimpleNamespace(list_current_fact_refresh_scopes=AsyncMock(return_value=(scope,))),owner_controls=SimpleNamespace(get_strategy_control=AsyncMock(return_value=SimpleNamespace(entry_state='enabled'))))
    observe=AsyncMock(return_value=SimpleNamespace(status=SimpleNamespace(value='facts_refreshed'),detector_reason='orb'))
    monkeypatch.setattr('src.trading_kernel.interfaces.selection_runtime_worker.observe_strategy_scope',observe)
    result=await run_current_fact_refresh_runtime_once(uow_factory=factory,market_source=object(),request=CurrentFactRefreshRuntimeRequest(strategy_group_id=spec.strategy_group_id,
        selection_spec_id=spec.selection_spec_id,worker_id='orb',now_ms=D+2*H+1,runtime_commit='orb',schema_revision='schema'))
    assert result.status=='facts_refreshed'
    assert observe.call_args.args[2].operation=='refresh_staged_facts'


@pytest.mark.asyncio
async def test_hourly_runner_expired_session_does_not_read_source_or_compute():
    spec=OrbSessionSelectionSpec()
    @asynccontextmanager
    async def factory():
        raise AssertionError('expired runner cannot start source transaction')
        yield
    class Market:
        async def fetch_selection_klines(self,request):raise AssertionError('expired source read')
    result=await run_instrument_selection_once(uow_factory=factory,market_source=Market(),request=RunInstrumentSelectionRequest(selection_spec_id=spec.selection_spec_id,
        selection_epoch_id='epoch:orb',period_anchor_ms=D,worker_id='orb'),clock_ms=lambda:D+24*H)
    assert result.outcome=='EXPIRED'
