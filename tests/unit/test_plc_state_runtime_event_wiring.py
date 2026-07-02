from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.campaign_state_service import CampaignRuntimeEvent
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.domain.execution_intent import ExecutionIntent
from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType, SignalResult


SYMBOL = "ETH/USDT:USDT"


class _Lifecycle:
    def set_entry_partially_filled_callback(self, callback):
        self.entry_partial_callback = callback

    def set_entry_filled_callback(self, callback):
        self.entry_filled_callback = callback

    def set_exit_progressed_callback(self, callback):
        self.exit_progressed_callback = callback

    async def get_orders_by_signal(self, signal_id: str):
        return []


class _CampaignRecorder:
    def __init__(self) -> None:
        self.events = []

    async def apply_runtime_event(self, **kwargs):
        self.events.append(kwargs)


class _CapitalProtection:
    def __init__(self) -> None:
        self.exit_projections = []

    async def record_exit_projection(self, **kwargs):
        self.exit_projections.append(kwargs)


class _ProjectionService:
    def __init__(self, result) -> None:
        self.result = result

    async def project_exit_fill(self, order):
        return self.result

    async def project_entry_fill(self, order):
        return None


def _signal() -> SignalResult:
    return SignalResult(
        symbol=SYMBOL,
        timeframe="1m",
        direction=Direction.LONG,
        entry_price=Decimal("2000"),
        suggested_stop_loss=Decimal("1900"),
        suggested_position_size=Decimal("0.01"),
        current_leverage=1,
        risk_reward_info="test",
        confidence=0.9,
        trigger_reason="test",
    )


def _order(*, order_id: str, role: OrderRole) -> Order:
    return Order(
        id=order_id,
        signal_id="sig-1",
        symbol=SYMBOL,
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=role,
        requested_qty=Decimal("0.01"),
        filled_qty=Decimal("0.01"),
        average_exec_price=Decimal("2100"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=2,
    )


def _orchestrator(*, campaign, projection_result=None, capital=None):
    return ExecutionOrchestrator(
        capital_protection=capital or _CapitalProtection(),
        order_lifecycle=_Lifecycle(),
        gateway=object(),
        position_projection_service=_ProjectionService(projection_result),
        campaign_state_service=campaign,
    )


@pytest.mark.asyncio
async def test_entry_fill_wires_campaign_runtime_event_before_protection():
    campaign = _CampaignRecorder()
    orchestrator = _orchestrator(campaign=campaign)
    entry_order = _order(order_id="entry-1", role=OrderRole.ENTRY)
    intent = ExecutionIntent(
        id="intent-1",
        signal_id="sig-1",
        signal=_signal(),
        order_id=entry_order.id,
    )
    orchestrator._intents[intent.id] = intent

    await orchestrator._handle_entry_filled(entry_order)

    assert [event["event"] for event in campaign.events] == [
        CampaignRuntimeEvent.ENTRY_FILLED
    ]
    assert campaign.events[0]["symbol"] == SYMBOL
    assert campaign.events[0]["signal_id"] == "sig-1"
    assert campaign.events[0]["order_id"] == "entry-1"


@pytest.mark.asyncio
async def test_tp_exit_progress_wires_profit_protect_and_close_events():
    campaign = _CampaignRecorder()
    capital = _CapitalProtection()
    projection_result = SimpleNamespace(
        position=object(),
        position_id="pos-1",
        signal_id="sig-1",
        exit_order_id="tp-1",
        delta_exit_qty=Decimal("0.01"),
        projected_exit_qty_after=Decimal("0.01"),
        delta_realized_pnl=Decimal("1.23"),
        just_closed=True,
        was_already_processed=False,
    )
    orchestrator = _orchestrator(
        campaign=campaign,
        projection_result=projection_result,
        capital=capital,
    )

    await orchestrator._handle_exit_filled(_order(order_id="tp-1", role=OrderRole.TP1))

    assert [event["event"] for event in campaign.events] == [
        CampaignRuntimeEvent.PROFIT_PROTECT_TRIGGERED,
        CampaignRuntimeEvent.POSITION_CLOSED,
    ]
    assert campaign.events[0]["position_id"] == "pos-1"
    assert capital.exit_projections[0]["just_closed"] is True


@pytest.mark.asyncio
async def test_sl_exit_progress_wires_stop_loss_before_close_event():
    campaign = _CampaignRecorder()
    projection_result = SimpleNamespace(
        position=object(),
        position_id="pos-1",
        signal_id="sig-1",
        exit_order_id="sl-1",
        delta_exit_qty=Decimal("0.01"),
        projected_exit_qty_after=Decimal("0.01"),
        delta_realized_pnl=Decimal("-1.23"),
        just_closed=True,
        was_already_processed=False,
    )
    orchestrator = _orchestrator(campaign=campaign, projection_result=projection_result)

    await orchestrator._handle_exit_filled(_order(order_id="sl-1", role=OrderRole.SL))

    assert [event["event"] for event in campaign.events] == [
        CampaignRuntimeEvent.STOP_LOSS_FILLED,
        CampaignRuntimeEvent.POSITION_CLOSED,
    ]
