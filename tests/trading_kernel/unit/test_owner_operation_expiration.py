from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.owner_operation_expiration import (
    expire_unstarted_owner_commands,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from tests.trading_kernel.support.owner_reduction import aggregate


@pytest.mark.asyncio
async def test_only_expired_prepared_owner_commands_may_be_superseded():
    a=aggregate()
    commands=tuple(SimpleNamespace(command_id=str(i),status=status,deadline_at_ms=1000,
        kind=K.OWNER_REDUCE,payload=SimpleNamespace(owner_operation_id='op')) for i,status in enumerate([S.PREPARED,S.CLAIMED,S.OUTCOME_UNKNOWN,S.ACCEPTED]))
    u=SimpleNamespace(exchange_commands=SimpleNamespace(mark_prepared_superseded=AsyncMock()),commit_reduction=AsyncMock())
    assert await expire_unstarted_owner_commands(u,aggregate=a,commands=commands,operation_id='op',now_ms=2000)
    u.exchange_commands.mark_prepared_superseded.assert_awaited_once_with(command_id='0',observed_at_ms=2000,reason='owner_unstarted_window_expired')


@pytest.mark.asyncio
async def test_expired_unstarted_full_close_returns_original_managed_stage():
    from src.trading_kernel.domain.aggregate import AggregateStatus as A
    a=aggregate().model_copy(update={'status':A.EXIT_PENDING,'protection_return_status':A.POSITION_PROTECTED,
        'protection_operation_id':'op'})
    c=SimpleNamespace(command_id='owner-exit',status=S.PREPARED,deadline_at_ms=1000,kind=K.EXIT,payload=SimpleNamespace(owner_operation_id='op'))
    u=SimpleNamespace(exchange_commands=SimpleNamespace(mark_prepared_superseded=AsyncMock()),commit_reduction=AsyncMock())
    await expire_unstarted_owner_commands(u,aggregate=a,commands=(c,),operation_id='op',now_ms=2000)
    result=u.commit_reduction.await_args.kwargs['reduction'].aggregate
    assert result.status is A.POSITION_PROTECTED
