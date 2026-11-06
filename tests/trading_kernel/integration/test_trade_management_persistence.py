import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.events import ManualTakeoverConfirmed
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.trade_management import ManagementMode
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_manual_ownership_survives_repository_reload(head_template_engine):
    e=head_template_engine;t=registered_sor_long_ticket()
    await reach_position_protected(e,t)
    async with PostgresKernelUnitOfWork(e) as uow:
        a=await uow.aggregates.get_for_update(t.identity.ticket_id)
        event=ManualTakeoverConfirmed(event_id='manual-1',ticket_id=t.identity.ticket_id,
              sequence=a.last_event_sequence+1,occurred_at_ms=5000,evidence_id='external-evidence',reason='external_order_amendment')
        await uow.commit_reduction(event=event,reduction=reduce_event(a,event),expected_version=a.version)
    async with PostgresKernelUnitOfWork(e) as uow:
        a=await uow.aggregates.get(t.identity.ticket_id)
        assert a.management_mode is ManagementMode.MANUAL
        assert a.management_evidence_id=='external-evidence'
        assert a.manual_takeover_at_ms==5000
    with pytest.raises(sa.exc.DBAPIError,match='management'):
        async with e.begin() as c:
            await c.execute(sa.text("UPDATE brc_trade_aggregates SET management_mode='AUTO' WHERE ticket_id=:id"),{'id':t.identity.ticket_id})
