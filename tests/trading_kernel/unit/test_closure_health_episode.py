from types import SimpleNamespace

import pytest

from src.trading_kernel.application.ports import MonitorOwnerStatus
from src.trading_kernel.application.reconciliation_health import (
    record_reconciliation_wait,
    resolve_reconciliation_wait,
)


class Monitors:
    def __init__(self):
        self.row = None
        self.changes = []

    async def get(self, key):
        return self.row

    async def save_if_changed(self, state):
        if self.row is None or (self.row.owner_status,self.row.summary,self.row.intervention) != (state.owner_status,state.summary,state.intervention):
            self.changes.append(state)
        self.row = state
        return state


@pytest.mark.asyncio
async def test_closure_uses_one_window_and_never_downgrades_or_backdates_alert():
    repo = Monitors()
    uow = SimpleNamespace(monitors=repo)
    for now, delay in [(1000, 300_000), (181_000, 180_000), (300_999, 300_000)]:
        await record_reconciliation_wait(uow, key='reconciliation-closure:ticket',
            reason='closure_wait:review_pending', now_ms=now, allowed_delay_ms=delay)
        assert repo.row.owner_status is MonitorOwnerStatus.PROCESSING
    for now, delay in [(301_000, 300_000), (301_001, 900_000)]:
        await record_reconciliation_wait(uow, key='reconciliation-closure:ticket',
            reason='closure_wait:review_pending', now_ms=now, allowed_delay_ms=delay)
        assert repo.row.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
    assert repo.row.first_wait_at_ms == 1000
    assert repo.row.escalated_at_ms == 301_000
    assert repo.row.updated_at_ms == 301_000
    assert len([s for s in repo.changes if s.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION]) == 1
    await resolve_reconciliation_wait(uow, key='reconciliation-closure:ticket', now_ms=400_000,
        economics_complete=False)
    assert repo.row.summary == 'trade_closed_economics_incomplete'
    assert repo.row.resolved_at_ms == 400_000


@pytest.mark.asyncio
async def test_duplicate_wait_updates_last_check_without_state_transition():
    repo = Monitors()
    uow = SimpleNamespace(monitors=repo)
    for now in (1000, 2000):
        await record_reconciliation_wait(uow, key='reconciliation-closure:ticket',
            reason='closure_wait:review_pending', now_ms=now, allowed_delay_ms=300_000)
    assert repo.row.first_wait_at_ms == 1000
    assert repo.row.last_checked_at_ms == 2000


@pytest.mark.asyncio
async def test_late_wait_cannot_rewind_health_clock_or_downgrade_alert():
    repo=Monitors();uow=SimpleNamespace(monitors=repo)
    for now in (1000,301000,2000):
        await record_reconciliation_wait(uow,key='reconciliation-closure:ticket',reason='closure_wait:review_pending',
            now_ms=now,allowed_delay_ms=300000)
    assert repo.row.last_checked_at_ms==301000
    assert repo.row.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
