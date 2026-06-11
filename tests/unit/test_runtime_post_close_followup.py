from __future__ import annotations

from decimal import Decimal

from tests.unit.test_runtime_live_position_monitor import _order, _position, _runtime

from src.domain.runtime_live_position_monitor import build_runtime_live_position_monitor_packet
from src.domain.runtime_position_exit_plan import build_runtime_position_exit_plan
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupStatus,
    build_runtime_post_close_followup_packet,
)
from src.domain.runtime_reduce_only_close_authorization import (
    build_runtime_reduce_only_close_owner_packet,
)
from src.domain.models import OrderRole


def _active_monitor():
    return build_runtime_live_position_monitor_packet(
        runtime=_runtime(),
        local_positions=[_position()],
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_positions=[],
        exchange_open_stop_orders=[],
        reconciliation_result=None,
        now_ms=1,
        exchange_facts_available=True,
    )


def test_post_close_followup_waits_for_owner_close_when_position_active():
    monitor = _active_monitor()
    exit_plan = build_runtime_position_exit_plan(
        runtime=_runtime(),
        monitor=monitor,
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_open_stop_orders=[],
        market_rule={"min_quantity": Decimal("1"), "step_size": Decimal("1")},
        now_ms=1,
    )
    owner_packet = build_runtime_reduce_only_close_owner_packet(
        exit_plan=exit_plan,
        now_ms=2,
    )

    packet = build_runtime_post_close_followup_packet(
        monitor=monitor,
        owner_close_packet=owner_packet,
        now_ms=3,
    )

    assert packet.status == RuntimePostCloseFollowupStatus.WAITING_FOR_OWNER_CLOSE_AUTHORIZATION
    assert packet.owner_close_approval_value == owner_packet.owner_approval_value
    assert "execute_runtime_owner_reduce_only_close_flow" in packet.required_steps
    assert "record_runtime_closed_trade_review" in packet.required_steps
    assert packet.exchange_order_submitted is False
    assert packet.position_closed is False


def test_post_close_followup_blocks_without_owner_packet_for_active_position():
    packet = build_runtime_post_close_followup_packet(
        monitor=_active_monitor(),
        owner_close_packet=None,
        now_ms=3,
    )

    assert packet.status == RuntimePostCloseFollowupStatus.BLOCKED
    assert "owner_close_packet_missing" in packet.blockers
