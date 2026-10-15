from __future__ import annotations

import asyncio
import json
from itertools import pairwise
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from src.trading_kernel.interfaces import observation_worker as observation
from src.trading_kernel.interfaces import worker_process as process
from tests.trading_kernel.support.efficiency_baseline import benchmark_variants


class Result(BaseModel):
    status: str
    identity: str = 'one'


@pytest.mark.asyncio
async def test_idle_logs_preserve_identity_change_and_recovery(monkeypatch):
    stop = asyncio.Event()
    monkeypatch.setattr(process, '_shutdown_event', lambda: stop)
    results = iter([
        Result(status='unchanged'), Result(status='unchanged'),
        Result(status='unchanged', identity='two'), Result(status='blocked'),
        Result(status='unchanged', identity='two'),
    ])
    output = []
    count = 0

    async def tick():
        nonlocal count
        count += 1
        if count == 5:
            stop.set()
        return next(results)

    await process.run_worker_process_group((process.WorkerProcessLoop(
        'materialization', tick, 1, frozenset({'unchanged'})),),
        run_forever=True, idle_log_interval_ms=300_000, emit=lambda s: output.append(json.loads(s)))
    assert [(r['status'], r['identity']) for r in output] == [
        ('unchanged', 'one'), ('unchanged', 'two'), ('blocked', 'one'), ('unchanged', 'two')]


@pytest.mark.asyncio
@pytest.mark.parametrize('slow', [False, True])
async def test_burst_is_bounded_and_failure_idle_retain_poll(monkeypatch, slow):
    stop = asyncio.Event()
    monkeypatch.setattr(process, '_shutdown_event', lambda: stop)
    clock = [0]
    monkeypatch.setattr(process.time, 'monotonic_ns', lambda: clock[0] * 1_000_000)
    delays = []
    actual_wait = asyncio.wait_for

    async def wait(awaitable, *, timeout):
        if timeout == 5:
            delays.append(count)
            awaitable.close()
            raise TimeoutError
        return await actual_wait(awaitable, timeout=timeout)

    monkeypatch.setattr(process.asyncio, 'wait_for', wait)
    count = 0

    async def tick():
        nonlocal count
        count += 1
        clock[0] += 20 if slow else 1
        if count == 5:
            raise RuntimeError('temporary source failure')
        if count == 7:
            stop.set()
        return Result(status='no_work' if count == 6 else 'observed')

    await process.run_worker_process_group((process.WorkerProcessLoop(
        'observation', tick, 5000, frozenset({'no_work'}),
        burst_statuses=frozenset({'observed'}), max_burst_ticks=3, max_burst_ms=10),),
        run_forever=True, idle_log_interval_ms=300_000, emit=lambda _: None)
    assert delays == ([1, 2, 3, 4, 5, 6] if slow else [3, 5, 6])


@pytest.mark.asyncio
async def test_shadow_priority_claim_is_bounded_and_falls_back_to_observation(monkeypatch):
    calls = []

    class Signals:
        async def claim_next_observation_scope(self, **kwargs):
            calls.append('observation')

    class Uow:
        signals = Signals()
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return None

    async def shadow(*_):
        calls.append('shadow')
        return observation.ObservationWorkerResult(status=observation.ObservationWorkerStatus.NO_WORK)

    monkeypatch.setattr(observation, '_run_one_due_shadow', shadow)
    request = observation.ObservationWorkerRequest(worker_id='test', runtime_commit='test', schema_revision='test',
        now_ms=100, lease_until_ms=1000, timeout_seconds=1, retry_interval_ms=100, prefer_shadow=True)
    result = await observation.run_observation_worker_once(Uow, SimpleNamespace(), request)
    assert result.status is observation.ObservationWorkerStatus.NO_WORK
    assert calls == ['shadow', 'observation']
    calls.clear()
    monkeypatch.setattr(observation, '_run_one_due_shadow', AsyncMock(return_value=observation.ObservationWorkerResult(
        status=observation.ObservationWorkerStatus.SHADOW_COMPLETED, shadow_outcome_id='shadow')))
    result = await observation.run_observation_worker_once(Uow, SimpleNamespace(), request)
    assert result.status is observation.ObservationWorkerStatus.SHADOW_COMPLETED
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('disposition,reason,expected_status', [
    ('ACTIVE_NEW', None, 'advanced'),
    ('GENERATION_DESIRED', 'GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED', 'waiting'),
    ('BLOCKED', 'GENERIC_CURRENT_CLOSE_ALREADY_CONSUMED', 'blocked'),
])
async def test_active_generation_routes_directly_but_first_activation_keeps_continuity(
    monkeypatch, active, disposition, reason, expected_status,
):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        CoordinateGenericGenerationRequest,
        CoordinateGenericPeriodRequest,
        CoordinateGenericSnapshotRequest,
        CoordinateSelectionMaterializationResult,
        MaterializationDisposition,
    )
    from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
    from src.trading_kernel.domain.selection_authority import (
        MaterializationGenerationState,
        SelectionControl,
    )
    from src.trading_kernel.interfaces import selection_runtime_worker as worker

    spec = generic_selection_spec('CPM-RO-001')
    control = SelectionControl(strategy_group_id=spec.strategy_group_id, selection_spec_id=spec.selection_spec_id,
        selection_mode='dynamic_selection', pending_selection_mode=None, pending_effective_period_anchor_ms=None,
        pending_authorization_id=None, control_version=2, rollback_baseline_id=None, selection_epoch_id='epoch', updated_at_ms=1)
    class Repo:
        async def get_generic_spec(self, *_): return spec
        async def get_selection_control(self, *_): return control
        async def get_latest_unfinished_generic_generation(self, **_): return None
        async def get_current_entry_vacuum(self, **_): return None
        async def get_selection_job(self, **_): return SimpleNamespace(state='SNAPSHOT_READY', selection_snapshot_id='snapshot')
        async def get_generic_materialization_generation(self, gid):
            return SimpleNamespace(materialization_generation_id=gid, lifecycle_state=MaterializationGenerationState.ACTIVE) if active else None
    class Uow:
        instrument_selection = Repo()
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return None
    calls = []
    async def coordinate(**kwargs):
        calls.append(kwargs['request'])
        return CoordinateSelectionMaterializationResult(disposition=MaterializationDisposition(disposition),
            reason_code=('TERMINAL_AUTHORITY_ALREADY_COMMITTED' if active and reason is None else reason))
    monkeypatch.setattr(worker, 'coordinate_selection_materialization_once', coordinate)
    result = await worker.run_materialization_runtime_once(uow_factory=Uow, audit_source=None,
        request=worker.SelectionRuntimeRequest(strategy_group_id=spec.strategy_group_id, selection_spec_id=spec.selection_spec_id,
            worker_id='test', now_ms=101*3_600_000+1), clock_ms=lambda:101*3_600_000+1)
    assert [type(call) for call in calls] == ([CoordinateGenericGenerationRequest] if active else
        [CoordinateGenericPeriodRequest, CoordinateGenericSnapshotRequest])
    assert result.status.value == ('unchanged' if active and reason is None else expected_status)
    # The same consumed-close reason must not hide a Coordinator BLOCKED result.
    stop = asyncio.Event()
    monkeypatch.setattr(process, '_shutdown_event', lambda: stop)
    ticks = 0
    logs = []
    async def tick():
        nonlocal ticks
        ticks += 1
        if ticks == 3:
            stop.set()
        return result
    await process.run_worker_process_group((process.WorkerProcessLoop('materialization', tick, 1,
        frozenset({'not_due', 'waiting', 'unchanged'})),), run_forever=True,
        idle_log_interval_ms=300_000, emit=logs.append)
    assert len(logs) == (3 if result.status.value in {'advanced', 'blocked'} else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('baseline', benchmark_variants())
@pytest.mark.parametrize('service_ms', [100, 1500])
async def test_reproducible_106_scope_queue_benchmark(monkeypatch, baseline, service_ms):
    import scripts.trading_kernel.run_observation_worker_once as current_script
    from tests.trading_kernel.support.efficiency_baseline import load_baseline

    runner = load_baseline('src/trading_kernel/interfaces/worker_process.py', 'baseline_process') if baseline else process
    script = load_baseline('scripts/trading_kernel/run_observation_worker_once.py', 'baseline_script') if baseline else current_script
    stop = asyncio.Event()
    monkeypatch.setattr(runner, '_shutdown_event', lambda: stop)
    clock = [0]
    monkeypatch.setattr(runner.time, 'monotonic_ns', lambda: clock[0]*1_000_000)
    completed = []
    shadows = []
    requests = []
    idle_polls = []

    async def wait(awaitable, *, timeout):
        awaitable.close()
        clock[0] += round(timeout*1000)
        raise TimeoutError

    monkeypatch.setattr(runner.asyncio, 'wait_for', wait)
    class Source:
        async def fetch_closed_candles(self, _): raise AssertionError('no external I/O')
    class Engine:
        async def dispose(self): pass
    monkeypatch.setattr(script, '_load_factory', lambda _: Source)
    monkeypatch.setattr(script, 'create_async_engine', lambda _: Engine())

    async def tick(_uow, _source, request):
        requests.append(request)
        clock[0] += service_ms
        if len(shadows) < 12 and (request.prefer_shadow or len(completed) == 106):
            shadows.append(clock[0])
            return observation.ObservationWorkerResult(status='shadow_completed', shadow_outcome_id=str(len(shadows)))
        if len(completed) < 106:
            completed.append(clock[0])
            return observation.ObservationWorkerResult(status='observed', runtime_scope_id=str(len(completed)))
        idle_polls.append(clock[0])
        if len(idle_polls) == 3:
            stop.set()
        return observation.ObservationWorkerResult(status='no_work')

    monkeypatch.setattr(script, 'run_observation_worker_once', tick)
    output = []
    async def group(loops, **kwargs):
        selected = tuple(loop for loop in loops if loop.component_id == 'benchmark')
        return await runner.run_worker_process_group(selected, run_forever=True,
            idle_log_interval_ms=300_000, emit=lambda row: (output.append(row), stop.set() if 'tick_failed' in row else None))
    monkeypatch.setattr(script, 'run_worker_process_group', group)
    args = script._parser().parse_args(['--database-url', 'postgresql+asyncpg://unused/test',
        '--market-source-factory', 'unused:source', '--worker-id', 'benchmark',
        '--runtime-commit', 'test', '--schema-revision', 'test', '--run-forever'])
    assert await script._run(args) == 0
    assert not any('tick_failed' in row for row in output), output
    assert len(completed) == 106 and len(shadows) == 12
    assert all(b-a == 5000+service_ms for a,b in pairwise(idle_polls))
    if not baseline:
        assert sum(r.prefer_shadow for r in requests[:9]) == 1
        assert shadows[0] < completed[-1]
        # Release regression budgets are independent of a historical checkout.
        assert completed[100] <= (81_300 if service_ms == 100 else 449_500)
        assert shadows[0] <= (5_900 if service_ms == 100 else 33_500)
        assert len(requests) == 121
    metrics = {'baseline': baseline, 'service_ms': service_ms,
        'scope_p50_ms': completed[52], 'scope_p95_ms': completed[100], 'scope_max_ms': completed[-1],
        'shadow_first_ms': shadows[0], 'shadow_p95_ms': shadows[-1], 'task_calls': len(requests),
        'idle_poll_ms': idle_polls[1]-idle_polls[0]}
    print('EFFICIENCY_QUEUE ' + json.dumps(metrics, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.parametrize('baseline', benchmark_variants())
async def test_repeated_materialization_log_volume(monkeypatch, baseline):
    from tests.trading_kernel.support.efficiency_baseline import load_baseline
    runner = load_baseline('src/trading_kernel/interfaces/worker_process.py', 'baseline_log_process') if baseline else process
    stop = asyncio.Event()
    monkeypatch.setattr(runner, '_shutdown_event', lambda: stop)
    clock = [0]
    monkeypatch.setattr(runner.time, 'monotonic_ns', lambda: clock[0]*1_000_000)
    calls = 0
    async def tick():
        nonlocal calls
        calls += 1
        if calls == 150:
            stop.set()
        return Result(status='advanced' if baseline or calls == 1 else 'unchanged')
    async def wait(awaitable, *, timeout):
        awaitable.close()
        clock[0] += int(timeout*1000)
        raise TimeoutError
    monkeypatch.setattr(runner.asyncio, 'wait_for', wait)
    logs = []
    await runner.run_worker_process_group((runner.WorkerProcessLoop('materialization', tick, 2000,
        frozenset({'unchanged'})),), run_forever=True, idle_log_interval_ms=300_000, emit=logs.append)
    assert len(logs) == (150 if baseline else 2)
    print('EFFICIENCY_LOG ' + json.dumps({'baseline': baseline, 'ticks': calls, 'logs': len(logs)}))


def test_release_benchmark_does_not_load_historical_git(monkeypatch):
    from tests.trading_kernel.support import efficiency_baseline

    monkeypatch.delenv('BRC_OBS_HISTORICAL_BENCHMARK', raising=False)
    def forbidden(*_, **__):
        raise AssertionError('release regression must not query historical Git')
    monkeypatch.setattr(efficiency_baseline.subprocess, 'run', forbidden)
    assert efficiency_baseline.benchmark_variants() == (False,)
    with pytest.raises(RuntimeError, match='requires BRC_OBS_HISTORICAL_BENCHMARK=1'):
        efficiency_baseline.load_baseline('unused', 'unused')


def test_explicit_historical_experiment_fails_clearly_when_baseline_missing(monkeypatch):
    from tests.trading_kernel.support import efficiency_baseline

    monkeypatch.setenv('BRC_OBS_HISTORICAL_BENCHMARK', '1')
    monkeypatch.setattr(efficiency_baseline.subprocess, 'run', lambda *_, **__: SimpleNamespace(returncode=128))
    assert efficiency_baseline.benchmark_variants() == (True, False)
    with pytest.raises(RuntimeError, match='requires Git baseline de73f279'):
        efficiency_baseline.load_baseline('unused', 'unused')


@pytest.mark.asyncio
async def test_alpha_research_backlog_keeps_106_live_scopes_moving(monkeypatch):
    """A+B host 106 due scopes and 200 research attempts with bounded failures."""
    import scripts.trading_kernel.run_observation_worker_once as script

    stop=asyncio.Event()
    monkeypatch.setattr(process,'_shutdown_event',lambda:stop)
    elapsed=[0]
    monkeypatch.setattr(process.time,'monotonic_ns',lambda:elapsed[0]*1_000_000)
    scopes=[]
    research=[]
    failures=[]
    class Source:
        async def fetch_closed_candles(self,_): raise AssertionError('fake tick owns no exchange I/O')
    class Engine:
        async def dispose(self): pass
    monkeypatch.setattr(script,'_load_factory',lambda _:Source)
    monkeypatch.setattr(script,'create_async_engine',lambda _:Engine())
    async def fake_tick(_uow,_source,request):
        elapsed[0]+=10
        if request.prefer_shadow and len(research)<200:
            if len(scopes)<106 and len(research)%2==1 and len(failures)<6:
                failures.append(elapsed[0])
                return observation.ObservationWorkerResult(status='shadow_retry_scheduled',
                    shadow_outcome_id='slow:research',detail='TimeoutError')
            research.append(elapsed[0])
            return observation.ObservationWorkerResult(status='shadow_completed',shadow_outcome_id=str(len(research)))
        if len(scopes)<106:
            scopes.append(elapsed[0])
            return observation.ObservationWorkerResult(status='observed',runtime_scope_id=str(len(scopes)))
        if len(research)<200:
            research.append(elapsed[0])
            return observation.ObservationWorkerResult(status='shadow_completed',shadow_outcome_id=str(len(research)))
        stop.set()
        return observation.ObservationWorkerResult(status='no_work')
    monkeypatch.setattr(script,'run_observation_worker_once',fake_tick)
    real_wait=asyncio.wait_for
    async def virtual_wait(awaitable,*,timeout):
        if timeout==5:
            elapsed[0]+=5000
            awaitable.close()
            raise TimeoutError
        return await real_wait(awaitable,timeout=timeout)
    monkeypatch.setattr(process.asyncio,'wait_for',virtual_wait)
    async def group(loops,**_):
        selected=tuple(loop for loop in loops if loop.component_id=='alpha-benchmark')
        return await process.run_worker_process_group(selected,run_forever=True,idle_log_interval_ms=300_000,
            emit=lambda _:None)
    monkeypatch.setattr(script,'run_worker_process_group',group)
    args=script._parser().parse_args(['--database-url','postgresql+asyncpg://unused/test',
        '--market-source-factory','unused:source','--worker-id','alpha-benchmark',
        '--runtime-commit','test','--schema-revision','test','--run-forever'])
    assert await script._run(args)==0
    assert len(scopes)==106 and len(research)==200 and len(failures)==6
    assert research[0]<scopes[8]
    assert scopes[-1]<research[-1]
    assert scopes[100]<120_000
