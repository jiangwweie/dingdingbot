from __future__ import annotations

from decimal import Decimal

from tests.unit.test_runtime_live_position_monitor import _order, _position, _runtime

from src.domain.models import OrderRole, OrderStatus
from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsStatus,
    build_runtime_closed_trade_review_facts_packet,
)
from src.domain.runtime_live_position_monitor import build_runtime_live_position_monitor_packet
from src.domain.runtime_position_exit_plan import build_runtime_position_exit_plan
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupStatus,
    build_runtime_post_close_followup_packet,
)
from src.domain.runtime_reduce_only_close_authorization import (
    build_runtime_reduce_only_close_owner_packet,
)


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


def test_post_close_followup_carries_resolved_closed_review_facts_when_flat():
    runtime = _runtime()
    monitor = build_runtime_live_position_monitor_packet(
        runtime=runtime,
        local_positions=[],
        local_open_orders=[],
        exchange_positions=[],
        exchange_open_stop_orders=[],
        reconciliation_result=None,
        now_ms=1,
        exchange_facts_available=True,
    )
    entry_order = _order(
        "entry-1",
        OrderRole.ENTRY,
        status=OrderStatus.FILLED,
        filled_qty=Decimal("1"),
        average_exec_price=Decimal("6.595"),
        filled_at=1,
    )
    exit_order = _order(
        "exit-1",
        OrderRole.EXIT,
        status=OrderStatus.FILLED,
        filled_qty=Decimal("1"),
        average_exec_price=Decimal("6.555"),
        filled_at=2,
        parent_order_id="entry-1",
    )
    review_facts = build_runtime_closed_trade_review_facts_packet(
        runtime=runtime,
        orders=[entry_order, exit_order],
        active_positions=[],
        open_orders=[],
        now_ms=2,
    )

    packet = build_runtime_post_close_followup_packet(
        monitor=monitor,
        owner_close_packet=None,
        closed_review_facts_packet=review_facts,
        now_ms=3,
    )

    assert review_facts.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
    assert packet.status == RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
    assert packet.closed_review_facts_status == "ready_for_closed_review"
    assert packet.closed_review_entry_order_id == "entry-1"
    assert packet.closed_review_exit_order_id == "exit-1"
    assert packet.closed_review_command_args[:5] == [
        "scripts/create_runtime_closed_trade_review.py",
        "--runtime-instance-id",
        runtime.runtime_instance_id,
        "--entry-order-id",
        "entry-1",
    ]
    assert "closed_review_facts_resolved" in packet.completed_steps
    assert "use_resolved_closed_review_order_ids" in packet.required_steps
