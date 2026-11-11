from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

"""Production-shaped decoding and durable coverage before normal AUTO management."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock

import ccxt
import pytest
import sqlalchemy as sa

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    dispatch_one_command,
)
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    LifecycleMaintenanceRequest,
    TicketLifecycleFacts,
    maintain_ticket_lifecycle,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.management_collector import (
    collect_management_scan,
)
from src.trading_kernel.infrastructure.pg_models import runtime_capabilities_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.management_observation_worker import (
    observe_management_once,
)
from tests.trading_kernel.support.dispatch_venues import KindAwareAcceptingVenue
from tests.trading_kernel.support.lifecycle import (
    reach_position_protected,
    registered_sor_long_ticket,
)


@pytest.mark.asyncio
async def test_decoded_own_creation_baselines_allow_auto_tp1_runner_then_app_handover(
    head_template_engine, monkeypatch
):
    original = KindAwareAcceptingVenue.execute

    async def numeric_order_ids(self, request):
        result = await original(self, request)
        identities = {
            "entry": "11",
            "initial_stop": "12",
            "take_profit": "13",
            "replace_protection": "14",
        }
        return result.model_copy(
            update={
                "exchange_order_id": identities.get(
                    request.kind.value, result.exchange_order_id
                )
            }
        )

    monkeypatch.setattr(KindAwareAcceptingVenue, "execute", numeric_order_ids)
    e = head_template_engine
    t = registered_sor_long_ticket()
    await reach_position_protected(e, t)
    d = t.identity.netting_domain
    scope = f"brc-app-manual-v1:{d.venue_id}:{d.account_id}"
    async with PostgresKernelUnitOfWork(e) as u:
        commands = await u.management.command_rows(t.identity.ticket_id)
        await u.management.start_feed(
            scope_key=scope,
            epoch_id="lifecycle-epoch",
            worker_id="receiver",
            runtime_commit="kernel-test-head",
            now_ms=900,
        )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id="lifecycle-epoch",
            events=[],
            connected_at_ms=900,
            now_ms=6000,
        )
    x = AsyncMock()
    x.management_started_ms = None
    regular = []
    conditional = []
    for command in commands:
        p = command["request_payload"]
        conditional_order = p["order_type"] == "stop_market"
        created = max(command["created_at_ms"], command["completed_at_ms"] - 1)
        raw = {
            "symbol": "BTCUSDT",
            "side": p["side"].upper(),
            "positionSide": "LONG",
            "price": p.get("limit_price") or "0",
            "reduceOnly": conditional_order,
            "closePosition": False,
            "timeInForce": p.get("time_in_force") or "GTC",
            "workingType": "CONTRACT_PRICE",
            "priceProtect": False,
            "priceMatch": "NONE",
            "selfTradePreventionMode": "EXPIRE_MAKER",
            "goodTillDate": 0,
            "updateTime": created,
        }
        if conditional_order:
            raw.update(
                algoId=command["result_payload"]["exchange_order_id"],
                clientAlgoId=command["venue_client_order_id"],
                orderType="STOP_MARKET",
                quantity=p["quantity"],
                triggerPrice=p["stop_price"],
                algoStatus="NEW",
                createTime=created,
            )
        else:
            raw.update(
                orderId=command["result_payload"]["exchange_order_id"],
                clientOrderId=command["venue_client_order_id"],
                type=p["order_type"].upper(),
                origQty=p["quantity"],
                stopPrice="0",
                status="FILLED" if command["command_kind"] == "entry" else "NEW",
                executedQty=p["quantity"]
                if command["command_kind"] == "entry"
                else "0",
                time=created,
            )
        (conditional if conditional_order else regular).append(
            ccxt.binanceusdm().on_json_response(json.dumps(raw))
        )
    x.fapiPrivateGetAllOrders.return_value = regular
    x.fapiPrivateGetAllAlgoOrders.return_value = conditional
    x.fapiPrivateGetOrderAmendment.return_value = []

    class Source:
        async def read_management_scan(self, request):
            async with PostgresKernelUnitOfWork(e) as u:
                covered = await u.management.continuity_covers(
                    scope, request.since_ms, request.now_ms
                )
            request = request.model_copy(
                update={"durable_context_required": True, "durable_coverage": covered}
            )
            return await collect_management_scan(
                x,
                request,
                PositionSnapshot(
                    netting_domain=d,
                    quantity=t.quantity,
                    average_entry_price=Decimal(60000),
                    observed_at_ms=request.now_ms,
                ),
            )

    assert (
        await observe_management_once(
            lambda: PostgresKernelUnitOfWork(e),
            Source(),
            ticket_id=t.identity.ticket_id,
            now_ms=6000,
        )
        == "AUTO"
    )
    async with e.begin() as c:
        await c.execute(
            sa.update(runtime_capabilities_current).values(
                certification={
                    "product_id": "brc-app-manual-v1",
                    "management_feed_required": True,
                }
            )
        )
    async with PostgresKernelUnitOfWork(e) as u:
        assert await u.management.accepted_orders_confirmed(t.identity.ticket_id)
        await maintain_ticket_lifecycle(
            u,
            LifecycleMaintenanceRequest(
                ticket_id=t.identity.ticket_id,
                now_ms=6500,
                facts=TicketLifecycleFacts(
                    position_quantity=t.quantity - t.take_profit_quantities[0],
                    tp1_filled_quantity=t.take_profit_quantities[0],
                    tp1_average_fill_price=t.take_profit_prices[0],
                    allocated_entry_fee_quote=Decimal(".01"),
                    exit_taker_fee_rate=Decimal(".001"),
                    price_tick=Decimal(".1"),
                    market_facts=None,
                    observed_at_ms=6500,
                ),
            ),
        )
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(e),
        KindAwareAcceptingVenue(observed_at_ms=7001),
        DispatchCommandRequest(
            worker_id="lifecycle",
            ticket_id=t.identity.ticket_id,
            now_ms=7000,
            lease_until_ms=8000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
        ),
        clock_ms=lambda: 7000,
    )
    assert result.status.value == "accepted"
    from src.trading_kernel.application.observe_trade_management import (
        observe_trade_management,
    )
    from tests.trading_kernel.support.manual_management import app_evidence

    async with PostgresKernelUnitOfWork(e) as u:
        await observe_trade_management(
            u,
            ticket_id=t.identity.ticket_id,
            evidence=app_evidence(t).model_copy(update={"received_at_ms": 7100}),
            now_ms=7100,
        )
    venue = KindAwareAcceptingVenue()
    venue.execute = AsyncMock(wraps=venue.execute)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(e),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle",
            ticket_id=t.identity.ticket_id,
            now_ms=7200,
            lease_until_ms=8000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
        ),
        clock_ms=lambda: 7200,
    )
    assert result.status.value in {"no_command", "superseded"}
    venue.execute.assert_not_awaited()
    async with PostgresKernelUnitOfWork(e) as u:
        assert (
            await u.aggregates.get(t.identity.ticket_id)
        ).management_mode.value == "MANUAL"
