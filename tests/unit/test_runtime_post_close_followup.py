from __future__ import annotations

from decimal import Decimal

import pytest

from tests.unit.test_runtime_live_position_monitor import (
    _exchange_position,
    _exchange_sl_order,
    _order,
    _position,
    _runtime,
)

from src.domain.models import OrderRole, OrderStatus
from src.domain.runtime_closed_trade_review_facts import (
    RuntimeClosedTradeReviewFactsArtifact,
    RuntimeClosedTradeReviewFactsStatus,
    build_runtime_closed_trade_review_facts_artifact,
)
from src.domain.runtime_live_position_monitor import build_runtime_live_position_monitor_artifact
from src.domain.runtime_position_exit_plan import build_runtime_position_exit_plan
from src.domain.runtime_post_close_followup import (
    RuntimePostCloseFollowupArtifact,
    RuntimePostCloseFollowupStatus,
    build_runtime_post_close_followup_artifact,
)
from src.domain.runtime_reduce_only_close_authorization import (
    build_runtime_reduce_only_close_owner_evidence,
)


def _active_monitor():
    return build_runtime_live_position_monitor_artifact(
        runtime=_runtime(),
        local_positions=[_position()],
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_positions=[_exchange_position()],
        exchange_open_stop_orders=[_exchange_sl_order()],
        reconciliation_result=None,
        now_ms=1,
        exchange_facts_available=True,
    )


def test_post_close_followup_prepares_standing_recovery_when_position_active():
    monitor = _active_monitor()
    exit_plan = build_runtime_position_exit_plan(
        runtime=_runtime(),
        monitor=monitor,
        local_open_orders=[_order("ord-sl", OrderRole.SL)],
        exchange_open_stop_orders=[_exchange_sl_order()],
        market_rule={"min_quantity": Decimal("1"), "step_size": Decimal("1")},
        now_ms=1,
    )
    owner_close_artifact = build_runtime_reduce_only_close_owner_evidence(
        exit_plan=exit_plan,
        now_ms=2,
    )

    artifact = build_runtime_post_close_followup_artifact(
        monitor=monitor,
        owner_close_artifact=owner_close_artifact,
        now_ms=3,
    )

    assert (
        artifact.status
        == RuntimePostCloseFollowupStatus.READY_FOR_STANDING_REDUCE_ONLY_RECOVERY
    )
    assert artifact.owner_close_approval_value is None
    assert artifact.standing_recovery_authorization_scope == (
        owner_close_artifact.standing_authorization_scope
    )
    assert "prepare_official_operation_layer_reduce_only_recovery" in artifact.required_steps
    assert "run_action_time_finalgate_for_reduce_only_recovery" in artifact.required_steps
    assert "execute_reduce_only_recovery_through_operation_layer" in artifact.required_steps
    assert "execute_runtime_owner_reduce_only_close_flow" not in artifact.required_steps
    assert "record_runtime_closed_trade_review" in artifact.required_steps
    assert artifact.exchange_order_submitted is False
    assert artifact.position_closed is False
    payload = artifact.model_dump(mode="json")
    assert (
        payload["owner_close_evidence_status"]
        == "ready_for_standing_recovery_authorization"
    )
    assert "owner_close_packet_status" not in payload
    assert payload["post_close_followup_evidence_only"] is True
    assert "packet_only" not in payload


def test_post_close_followup_blocks_without_owner_close_artifact_for_active_position():
    artifact = build_runtime_post_close_followup_artifact(
        monitor=_active_monitor(),
        owner_close_artifact=None,
        now_ms=3,
    )

    assert artifact.status == RuntimePostCloseFollowupStatus.BLOCKED
    assert "owner_close_artifact_missing" in artifact.blockers


def test_post_close_followup_carries_resolved_closed_review_facts_when_flat():
    runtime = _runtime()
    monitor = build_runtime_live_position_monitor_artifact(
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
    review_facts = build_runtime_closed_trade_review_facts_artifact(
        runtime=runtime,
        orders=[entry_order, exit_order],
        active_positions=[],
        open_orders=[],
        now_ms=2,
    )

    artifact = build_runtime_post_close_followup_artifact(
        monitor=monitor,
        owner_close_artifact=None,
        closed_review_facts_artifact=review_facts,
        now_ms=3,
    )

    assert review_facts.status == RuntimeClosedTradeReviewFactsStatus.READY_FOR_CLOSED_REVIEW
    assert artifact.status == RuntimePostCloseFollowupStatus.READY_FOR_CLOSED_REVIEW
    assert artifact.closed_review_facts_status == "ready_for_closed_review"
    assert artifact.closed_review_entry_order_id == "entry-1"
    assert artifact.closed_review_exit_order_id == "exit-1"
    assert artifact.closed_review_command_args[:5] == [
        "scripts/create_runtime_closed_trade_review.py",
        "--runtime-instance-id",
        runtime.runtime_instance_id,
        "--entry-order-id",
        "entry-1",
    ]
    assert "closed_review_facts_resolved" in artifact.completed_steps
    assert "use_resolved_closed_review_order_ids" in artifact.required_steps
    review_payload = review_facts.model_dump(mode="json")
    assert review_payload["closed_trade_review_facts_evidence_only"] is True
    assert "packet_only" not in review_payload


def test_post_close_followup_completes_when_closed_review_already_recorded():
    runtime = _runtime()
    monitor = build_runtime_live_position_monitor_artifact(
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
    review_facts = build_runtime_closed_trade_review_facts_artifact(
        runtime=runtime,
        orders=[entry_order, exit_order],
        active_positions=[],
        open_orders=[],
        now_ms=2,
    )

    artifact = build_runtime_post_close_followup_artifact(
        monitor=monitor,
        owner_close_artifact=None,
        closed_review_facts_artifact=review_facts,
        closed_review_recorded=True,
        closed_review_id="live-review-1",
        now_ms=3,
    )

    assert artifact.status == RuntimePostCloseFollowupStatus.POST_CLOSE_COMPLETE
    assert artifact.closed_review_recorded is True
    assert artifact.closed_review_id == "live-review-1"
    assert artifact.required_steps == ["verify_next_attempt_gate"]
    assert "closed_review_recorded" in artifact.completed_steps
    assert "record_runtime_closed_trade_review" not in artifact.required_steps


def test_post_close_followup_rejects_legacy_packet_only_input():
    artifact = build_runtime_post_close_followup_artifact(
        monitor=_active_monitor(),
        owner_close_artifact=None,
        now_ms=3,
    )
    legacy_payload = artifact.model_dump(mode="json")
    legacy_payload["packet_only"] = legacy_payload.pop(
        "post_close_followup_evidence_only",
    )

    with pytest.raises(ValueError):
        RuntimePostCloseFollowupArtifact.model_validate(legacy_payload)


def test_closed_review_facts_rejects_legacy_packet_only_input():
    runtime = _runtime()
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
    artifact = build_runtime_closed_trade_review_facts_artifact(
        runtime=runtime,
        orders=[entry_order, exit_order],
        active_positions=[],
        open_orders=[],
        now_ms=2,
    )
    legacy_payload = artifact.model_dump(mode="json")
    legacy_payload["packet_only"] = legacy_payload.pop(
        "closed_trade_review_facts_evidence_only",
    )

    with pytest.raises(ValueError):
        RuntimeClosedTradeReviewFactsArtifact.model_validate(legacy_payload)
