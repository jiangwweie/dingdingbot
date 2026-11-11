import asyncio
from decimal import Decimal

import ccxt.pro as ccxt_pro
import pytest

from src.trading_kernel.application.ports import VenueCommandRequest, VenueSendBlocked
from src.trading_kernel.domain.commands import ExchangeCommandKind, OrderCommandPayload
from src.trading_kernel.infrastructure.binance_management_stream import (
    ManagementBinanceUsdm,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter


@pytest.mark.asyncio
async def test_transport_rechecks_management_after_loading_and_throttling(monkeypatch):
    exchange = ManagementBinanceUsdm({})
    manual = False
    writes = []

    async def actual_fetch(*args, **kwargs):
        writes.append(1)
        return {"id": "1"}

    monkeypatch.setattr(ccxt_pro.binanceusdm, "fetch", actual_fetch)

    async def create_order(*args):
        nonlocal manual
        await asyncio.sleep(0)
        manual = True
        return await exchange.fetch("https://example.invalid", "POST")

    exchange.create_order = create_order

    async def check():
        if manual:
            raise VenueSendBlocked("trade_management:MANUAL", superseded=True)

    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "manual"): exchange}, clock_ms=lambda: 1000
    )
    request = VenueCommandRequest(
        command_id="cmd",
        kind=ExchangeCommandKind.REPLACE_PROTECTION,
        venue_id="binance-usdm",
        account_id="manual",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        venue_client_order_id="c",
        payload=OrderCommandPayload(
            side="sell",
            quantity=Decimal(".006"),
            order_type="stop_market",
            reduce_only=True,
            stop_price=Decimal(60000),
        ),
        deadline_at_ms=3000,
        before_send=check,
    )
    with pytest.raises(VenueSendBlocked):
        await adapter.execute(request)
    assert writes == []
    await exchange.close()


@pytest.mark.asyncio
async def test_transport_never_retries_after_a_request_crossed_send_boundary(
    monkeypatch,
):
    from src.trading_kernel.application.ports import VenueMutationFailure
    from src.trading_kernel.infrastructure.mutation_send_guard import (
        MutationSendContext,
        current_mutation_guard,
    )

    exchange = ManagementBinanceUsdm({})
    calls = []

    async def actual_fetch(*args, **kwargs):
        calls.append(1)
        raise TimeoutError("sent then response lost")

    monkeypatch.setattr(ccxt_pro.binanceusdm, "fetch", actual_fetch)

    async def check():
        return None

    token = current_mutation_guard.set(MutationSendContext(check))
    try:
        with pytest.raises(TimeoutError):
            await exchange.fetch("https://example.invalid", "POST")
        with pytest.raises(VenueMutationFailure):
            await exchange.fetch("https://example.invalid", "POST")
        assert calls == [1]
    finally:
        current_mutation_guard.reset(token)
        await exchange.close()
