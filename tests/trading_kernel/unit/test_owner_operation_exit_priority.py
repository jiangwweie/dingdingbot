from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.owner_operation_exit import (
    read_original_operation_exit,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.exit_policy import (
    LifecycleMarketFacts,
    registered_exit_profiles,
)
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from tests.trading_kernel.support.owner_reduction import aggregate


@pytest.mark.asyncio
async def test_original_session_expiry_survives_an_owner_adjustment():
    a=aggregate().model_copy(update={'ticket':aggregate().ticket.model_copy(update={'exposure_session_end_ms':3500})})
    profile=next(p for p in registered_exit_profiles() if p.exit_profile_id==a.ticket.exit_policy_id)
    ref=TicketOrderReference(command_id='entry',command_kind=K.ENTRY,role=OrderRole.ENTRY,namespace=OrderNamespace.REGULAR,
        venue_client_order_id='entry',submitted_exchange_order_id="entry-order",command_created_at_ms=1000)
    facts=SimpleNamespace(position_quantity=a.position_qty,observed_at_ms=4000,market_facts=LifecycleMarketFacts(
        watermark_ms=3999,is_final_closed_candle=True,latest_close=D(60000),structure_reference=D(59000),atr=D(100),holding_bars=1))
    source=SimpleNamespace(read_lifecycle_facts=AsyncMock(return_value=facts))
    reason=await read_original_operation_exit(source,aggregate=a,profile=profile,rules=SimpleNamespace(price_tick=D('.1')),
        references=(ref,),now_ms=4000)
    assert reason=='session_expired'
