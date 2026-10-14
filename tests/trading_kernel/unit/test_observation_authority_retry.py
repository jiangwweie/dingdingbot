from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.trading_kernel.application.observe_strategy_scope import (
    ObservationResult,
    ObservationStatus,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    run_observation_worker_once,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("group",["CPM-RO-001","MPG-001","MI-001","BRF2-001","SOR-001"])
@pytest.mark.parametrize("reason",["selection_authority_missing_or_expired","selection_entry_vacuum","selection_activation_pending_current_close","selection_valid_empty","OWNER_PAUSED","RECOVERY_REBASE_REQUIRED"])
@pytest.mark.parametrize("offset",[8,3_600_000-8])
@pytest.mark.parametrize("lease_changed",[False,True])
async def test_only_generic_transient_authority_wait_retries_unconsumed_close(monkeypatch,group,reason,offset,lease_changed):
    close=102*3_600_000
    scheduled=[]
    class Signals:
        async def claim_next_observation_scope(self,**_):
            return SimpleNamespace(runtime_scope_id="scope",trigger_candle_close_time_ms=close,observation_generation=1,timeframe="1h")
        async def get_runtime_scope(self,*_): return SimpleNamespace(strategy_group_id=group)
        async def schedule_observation_scope(self,**kwargs):
            if lease_changed:
                from src.trading_kernel.application.ports import ObservationLeaseChanged
                raise ObservationLeaseChanged("lease changed")
            scheduled.append(kwargs["due_at_ms"])
    class Uow:
        signals=Signals()
        async def __aenter__(self): return self
        async def __aexit__(self,*_): return None
    async def observe(*_):
        return ObservationResult(status=ObservationStatus.INVALID,runtime_scope_id="scope",event_spec_id="event",
            detector_reason=reason,signal_event_id=None,current_fact_count=0)
    monkeypatch.setattr("src.trading_kernel.interfaces.observation_worker.observe_strategy_scope",observe)
    result=await run_observation_worker_once(Uow,SimpleNamespace(),ObservationWorkerRequest(worker_id="observation",runtime_commit="test",
        schema_revision="test",now_ms=close+offset,lease_until_ms=close+offset+30_000,timeout_seconds=1,retry_interval_ms=1_000))
    retry=group!="SOR-001" and reason in {"selection_authority_missing_or_expired","selection_entry_vacuum","selection_activation_pending_current_close"}
    if lease_changed:
        assert result.status.value=="superseded"
        assert scheduled==[]
        return
    assert result.status.value==("retry_scheduled" if retry else "observed")
    assert scheduled==[min(close+offset+1_000,close+3_600_000) if retry else close+3_600_000]
