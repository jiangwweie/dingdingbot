from __future__ import annotations

from pathlib import Path

from src.application.current_truth_reducer import (
    reduce_current_truth,
    semantic_state_for_aggregate,
)
from src.domain.runtime_semantic_kernel import RuntimeState
from tests.unit.test_action_time_projection_truth import (
    _attach_certifications,
    _ready_control_state,
)


def test_current_truth_conserves_release_certification_as_one_lane_blocker(
    tmp_path: Path,
) -> None:
    bundle = reduce_current_truth(_ready_control_state(tmp_path))

    assert len(bundle.lane_decisions) == 22
    assert {item.first_blocker for item in bundle.lane_decisions} == {
        "action_time_boundary_not_reproduced"
    }
    assert {item.blocker_owner for item in bundle.lane_decisions} == {"system"}
    assert bundle.system_summary["current_issue_count"] == 22


def test_current_truth_uses_one_stable_market_wait_after_certification(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)

    first = reduce_current_truth(state)
    second = reduce_current_truth(state)

    assert {item.first_blocker for item in first.lane_decisions} == {
        "market_wait_validated"
    }
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert not first.incident_decisions


def test_current_truth_promotes_a_fresh_fully_ready_lane_to_action_time(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    _attach_certifications(state)
    candidate = state["candidate_scope"][0]
    now_ms = state["read_now_ms"]
    state["live_signal_events"] = [
        {
            "signal_event_id": "signal:current-truth-ready",
            "strategy_group_id": candidate["strategy_group_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "status": "facts_validated",
            "freshness_state": "fresh",
            "observed_at_ms": now_ms,
            "created_at_ms": now_ms,
            "expires_at_ms": now_ms + 60_000,
        }
    ]

    bundle = reduce_current_truth(state)
    target = next(
        item
        for item in bundle.lane_decisions
        if item.lane_identity.key
        == (candidate["strategy_group_id"], candidate["symbol"], candidate["side"])
    )

    assert target.first_blocker == "action_time_preflight_ready"
    assert target.current_issue is False


def test_current_truth_keeps_two_tickets_as_independent_current_decisions(
    tmp_path: Path,
) -> None:
    state = _ready_control_state(tmp_path)
    state["action_time_tickets"] = [
        {
            "ticket_id": "ticket:btc",
            "status": "outcome_unknown",
            "exposure_episode_id": "exposure:btc",
            "netting_domain_key": "binance:BTCUSDT",
            "protection_state": "ready",
            "reconciliation_state": "pending",
            "created_at_ms": state["read_now_ms"],
        },
        {
            "ticket_id": "ticket:eth",
            "status": "submitted",
            "exposure_episode_id": "exposure:eth",
            "netting_domain_key": "binance:ETHUSDT",
            "protection_state": "missing",
            "reconciliation_state": "pending",
            "created_at_ms": state["read_now_ms"],
        },
    ]

    bundle = reduce_current_truth(state)
    by_ticket = {item.ticket_id: item for item in bundle.trade_decisions}

    assert set(by_ticket) == {"ticket:btc", "ticket:eth"}
    assert by_ticket["ticket:btc"].first_blocker == "outcome_unknown"
    assert by_ticket["ticket:eth"].first_blocker == "protection_missing"
    assert by_ticket["ticket:btc"].semantic_fingerprint != by_ticket["ticket:eth"].semantic_fingerprint


def test_unknown_aggregate_status_is_a_current_fail_closed_blocker() -> None:
    semantic = semantic_state_for_aggregate("ticket", "a_new_status")

    assert semantic.state is RuntimeState.BLOCKED
    assert semantic.is_current is True
    assert semantic.reason_code == "unsupported_runtime_status:ticket:a_new_status"
