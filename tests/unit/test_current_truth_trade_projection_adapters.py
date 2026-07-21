from __future__ import annotations

import pytest

from src.application.current_truth_projection_adapters import (
    adapt_daily_table,
    adapt_goal_status,
    adapt_monitor_status,
)
from src.application.current_truth_reducer import reduce_current_truth
from src.domain.runtime_semantic_kernel import RuntimeState
from tests.unit.test_current_truth_reducer import _typed_trade_control_state
from tests.unit.test_action_time_projection_truth import (
    _attach_certifications,
    _ready_control_state,
)


@pytest.mark.parametrize(
    ("case", "status", "owner_action_required"),
    (
        ("entry_unknown", "processing", False),
        ("sl_pending_within_sla", "processing", False),
        ("sl_hard_incident", "needs_intervention", True),
        ("tp1_degraded", "running", False),
        ("protected_matched", "running", False),
    ),
)
def test_goal_daily_and_monitor_are_thin_trade_decision_adapters(
    case,
    status,
    owner_action_required,
):
    bundle = reduce_current_truth(_typed_trade_control_state(case))
    goal = adapt_goal_status(
        {
            "status": "waiting_for_signal",
            "owner_action_required": False,
            "owner_state": {"status": "waiting_for_opportunity"},
            "evidence": {},
        },
        bundle=bundle,
    )
    daily = adapt_daily_table(
        {
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                    "first_blocker": "market_wait_validated",
                }
            ]
        },
        bundle=bundle,
    )
    monitor = adapt_monitor_status(
        {
            "status": "waiting_for_opportunity",
            "owner_action_required": False,
            "first_blocker": "no_signal",
        },
        bundle=bundle,
    )

    decision = bundle.trade_decisions[0]
    assert goal["status"] == status
    assert goal["owner_action_required"] is owner_action_required
    assert goal["owner_state"]["status"] == status
    assert daily["rows"][0]["owner_state"] == status
    assert daily["rows"][0]["first_blocker"] == decision.first_blocker
    assert monitor["status"] == status
    assert monitor["first_blocker"] == decision.first_blocker
    assert monitor["owner_action_required"] is owner_action_required
    assert "market_wait_validated" not in {
        goal.get("first_blocker"),
        daily["rows"][0]["first_blocker"],
        monitor["first_blocker"],
    }


def test_daily_trade_override_is_exact_scope_not_strategy_group_global():
    bundle = reduce_current_truth(
        _typed_trade_control_state("sl_hard_incident")
    )
    daily = adapt_daily_table(
        {
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                    "first_blocker": "market_wait_validated",
                },
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "first_blocker": "market_wait_validated",
                },
            ]
        },
        bundle=bundle,
    )

    assert daily["rows"][0]["owner_state"] == "needs_intervention"
    assert daily["rows"][1]["first_blocker"] == "market_wait_validated"
    assert "owner_state" not in daily["rows"][1]


def test_daily_maps_two_independent_trade_lanes_without_cross_contamination():
    first_bundle = reduce_current_truth(
        _typed_trade_control_state("sl_hard_incident")
    )
    first = first_bundle.trade_decisions[0]
    second = first.model_copy(
        update={
            "ticket_id": "ticket:mpg",
            "action_time_lane_input_id": "lane:mpg",
            "strategy_group_id": "MPG-001",
            "symbol": "BTCUSDT",
            "side": "short",
            "state": RuntimeState.RUNNING,
            "protection_state": "initial_stop_confirmed",
            "first_blocker": "",
            "next_system_action": "continue_protected_lifecycle_monitoring",
            "owner_state": "running",
            "owner_message": "持仓保护与交易所状态正常",
            "owner_action_required": False,
        }
    )
    bundle = first_bundle.model_copy(
        update={"trade_decisions": (first, second)}
    )

    daily = adapt_daily_table(
        {
            "rows": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                },
                {
                    "strategy_group_id": "MPG-001",
                    "symbol": "BTCUSDT",
                    "side": "short",
                },
            ]
        },
        bundle=bundle,
    )

    assert [row["owner_state"] for row in daily["rows"]] == [
        "needs_intervention",
        "running",
    ]


def test_global_adapters_use_stable_trade_safety_priority_over_market_wait(
    tmp_path,
):
    lane_state = _ready_control_state(tmp_path)
    _attach_certifications(lane_state)
    lane_bundle = reduce_current_truth(lane_state)
    hard_bundle = reduce_current_truth(
        _typed_trade_control_state("sl_hard_incident")
    )
    unknown_bundle = reduce_current_truth(
        _typed_trade_control_state("entry_unknown")
    )
    bundle = hard_bundle.model_copy(
        update={
            "lane_decisions": lane_bundle.lane_decisions,
            "trade_decisions": (
                unknown_bundle.trade_decisions[0].model_copy(
                    update={"ticket_id": "ticket:aaa-unknown"}
                ),
                hard_bundle.trade_decisions[0].model_copy(
                    update={"ticket_id": "ticket:zzz-hard"}
                ),
            ),
        }
    )

    goal = adapt_goal_status({"owner_state": {}}, bundle=bundle)
    monitor = adapt_monitor_status({}, bundle=bundle)

    assert goal["status"] == "needs_intervention"
    assert goal["first_blocker"] == "initial_stop_deadline_exhausted"
    assert monitor["status"] == "needs_intervention"
    assert monitor["first_blocker"] == "initial_stop_deadline_exhausted"


def test_global_adapters_project_completed_when_only_trade_is_closed():
    bundle = reduce_current_truth(_typed_trade_control_state("closed"))

    goal = adapt_goal_status({"owner_state": {}}, bundle=bundle)
    monitor = adapt_monitor_status({}, bundle=bundle)

    assert goal["status"] == "completed"
    assert monitor["status"] == "completed"
    assert goal["owner_action_required"] is False


def test_completed_trade_does_not_override_current_market_wait_lane(tmp_path):
    lane_state = _ready_control_state(tmp_path)
    _attach_certifications(lane_state)
    lane_bundle = reduce_current_truth(lane_state)
    closed_bundle = reduce_current_truth(_typed_trade_control_state("closed"))
    bundle = closed_bundle.model_copy(
        update={"lane_decisions": lane_bundle.lane_decisions}
    )

    goal = adapt_goal_status({"owner_state": {}}, bundle=bundle)
    monitor = adapt_monitor_status({}, bundle=bundle)

    assert goal["status"] == "waiting_for_signal"
    assert monitor["status"] == "waiting_for_opportunity"
    assert goal["status"] != "completed"
    assert monitor["status"] != "completed"


def test_global_adapters_keep_market_wait_when_there_is_no_trade(tmp_path):
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)
    bundle = reduce_current_truth(state)

    goal = adapt_goal_status({"owner_state": {}}, bundle=bundle)
    monitor = adapt_monitor_status({}, bundle=bundle)

    assert goal["status"] == "waiting_for_signal"
    assert monitor["status"] == "waiting_for_opportunity"
    assert monitor["first_blocker"] == "market_wait_validated"


def test_global_adapters_do_not_hide_mixed_lane_blocker_behind_market_wait(
    tmp_path,
):
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)
    bundle = reduce_current_truth(state)
    blocked = bundle.lane_decisions[0].model_copy(
        update={
            "first_blocker": "action_time_boundary_not_reproduced",
            "next_system_action": "certify_current_release_action_time_capability",
            "current_issue": True,
        }
    )
    bundle = bundle.model_copy(
        update={
            "lane_decisions": (blocked, *bundle.lane_decisions[1:]),
        }
    )

    goal = adapt_goal_status({"owner_state": {}}, bundle=bundle)
    monitor = adapt_monitor_status({}, bundle=bundle)

    assert goal["first_blocker"] == "action_time_boundary_not_reproduced"
    assert monitor["first_blocker"] == "action_time_boundary_not_reproduced"
