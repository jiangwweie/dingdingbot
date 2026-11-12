import pytest

from src.trading_kernel.application.notice_policy import build_notices
from src.trading_kernel.application.verified_exit_closure import settle_verified_exit
from src.trading_kernel.domain.notices import NoticeKind
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.support.verified_exit import protected_proof


@pytest.mark.asyncio
async def test_review_terminal_exact_closure_notifies_closed_without_residual(head_template_engine):
    e=head_template_engine;t,p=await protected_proof(e)
    async with PostgresKernelUnitOfWork(e) as u:
        before=await u.aggregates.get(t.identity.ticket_id)
        await settle_verified_exit(u,proof=p,now_ms=7001)
        after=await u.aggregates.get(t.identity.ticket_id)
        events=tuple(e for e in await u.events.list_for_ticket(t.identity.ticket_id) if e.sequence>before.last_event_sequence)
    notices=build_notices(before,after,events,p.snapshot)
    assert [n.kind for n in notices]==[NoticeKind.CLOSED]
    assert notices[0].residual_order_count==0
