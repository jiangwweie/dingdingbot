from __future__ import annotations

from src.application.action_time.process_outcome_relevance import (
    process_outcome_has_current_blocking_authority,
)


NOW_MS = 10_000
SCOPE_KEY = "lane:SOR-001:ETHUSDT:long"


def _outcome(**overrides):
    row = {
        "process_name": "action_time_ticket_sequence",
        "scope_key": SCOPE_KEY,
        "process_state": "business_blocked",
        "first_blocker": "unit_action_time_failure",
        "source_watermark": "signal:SOR-001:ETHUSDT:long:expired",
    }
    row.update(overrides)
    return row


def _signal(signal_event_id: str, *, fresh: bool) -> dict[str, object]:
    return {
        "signal_event_id": signal_event_id,
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "status": "facts_validated",
        "freshness_state": "fresh" if fresh else "expired",
        "source_kind": "live_market",
        "invalidated_at_ms": None,
        "event_time_ms": NOW_MS - 100,
        "observed_at_ms": NOW_MS - 50,
        "created_at_ms": NOW_MS - 25,
        "expires_at_ms": NOW_MS + 1_000 if fresh else NOW_MS - 1,
    }


def _control_state(**overrides):
    state = {
        "read_now_ms": NOW_MS,
        "live_signal_events": [],
        "promotion_candidates": [],
        "action_time_lane_inputs": [],
        "action_time_tickets": [],
        "ticket_bound_order_lifecycle_runs": [],
        "runtime_safety_state": [],
    }
    state.update(overrides)
    return state


def test_expired_event_scoped_outcome_loses_current_blocking_authority():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:expired", fresh=False)
        ],
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(),
    ) is False


def test_fresh_matching_signal_keeps_current_blocking_authority():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:current", fresh=True)
        ],
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:current"),
    ) is True


def test_submitted_ticket_keeps_its_signal_outcome_current_after_signal_expiry():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:ticket", fresh=False)
        ],
        action_time_tickets=[
            {
                "ticket_id": "ticket-current",
                "signal_event_id": "signal:SOR-001:ETHUSDT:long:ticket",
                "promotion_candidate_id": "promotion-current",
                "action_time_lane_input_id": "lane-current",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "status": "submitted",
                "created_at_ms": NOW_MS - 10,
                "expires_at_ms": NOW_MS - 1,
            }
        ],
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:ticket"),
    ) is True


def test_opaque_failure_remains_current_until_scope_outcome_is_superseded():
    state = _control_state()

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark=""),
    ) is True
    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(
            source_watermark="",
            process_state="succeeded",
            first_blocker=None,
        ),
    ) is False


def test_current_object_from_another_lane_cannot_keep_blocker_authority():
    other_lane_signal = _signal(
        "signal:SOR-001:ETHUSDT:long:current",
        fresh=True,
    )
    other_lane_signal["symbol"] = "BTCUSDT"

    assert process_outcome_has_current_blocking_authority(
        _control_state(live_signal_events=[other_lane_signal]),
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:current"),
    ) is False


def test_monitor_bounded_state_without_expired_source_row_drops_event_blocker():
    assert process_outcome_has_current_blocking_authority(
        _control_state(),
        _outcome(
            source_watermark="signal:SOR-001:ETHUSDT:long:expired-and-filtered"
        ),
    ) is False


def test_open_promotion_lane_and_active_ticket_each_keep_direct_source_current():
    promotion = {
        "promotion_candidate_id": "promotion:SOR-001:ETHUSDT:long:current",
        "signal_event_id": "signal:SOR-001:ETHUSDT:long:expired",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "status": "eligible",
        "closed_at_ms": None,
        "created_at_ms": NOW_MS - 10,
        "expires_at_ms": NOW_MS + 1_000,
    }
    lane = {
        "action_time_lane_input_id": "lane:SOR-001:ETHUSDT:long:current",
        "promotion_candidate_id": promotion["promotion_candidate_id"],
        "signal_event_id": promotion["signal_event_id"],
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "lane_scope": "real_submit_candidate",
        "status": "opened",
        "closed_at_ms": None,
        "created_at_ms": NOW_MS - 10,
        "expires_at_ms": NOW_MS + 1_000,
    }
    ticket = {
        "ticket_id": "ticket:SOR-001:ETHUSDT:long:current",
        "action_time_lane_input_id": lane["action_time_lane_input_id"],
        "promotion_candidate_id": promotion["promotion_candidate_id"],
        "signal_event_id": promotion["signal_event_id"],
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "status": "finalgate_ready",
        "created_at_ms": NOW_MS - 10,
        "expires_at_ms": NOW_MS + 1_000,
    }
    state = _control_state(
        promotion_candidates=[promotion],
        action_time_lane_inputs=[lane],
        action_time_tickets=[ticket],
    )

    for watermark in (
        promotion["promotion_candidate_id"],
        lane["action_time_lane_input_id"],
        ticket["ticket_id"],
    ):
        assert process_outcome_has_current_blocking_authority(
            state,
            _outcome(source_watermark=watermark),
        ) is True


def test_nonclosed_lifecycle_keeps_lineage_but_closed_lifecycle_releases_it():
    signal_id = "signal:SOR-001:ETHUSDT:long:lifecycle"
    ticket = {
        "ticket_id": "ticket:SOR-001:ETHUSDT:long:lifecycle",
        "action_time_lane_input_id": "lane:SOR-001:ETHUSDT:long:lifecycle",
        "promotion_candidate_id": "promotion:SOR-001:ETHUSDT:long:lifecycle",
        "signal_event_id": signal_id,
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "status": "closed",
        "created_at_ms": NOW_MS - 1_000,
        "expires_at_ms": NOW_MS - 1,
    }
    lifecycle = {
        "lifecycle_run_id": "lifecycle:current",
        "ticket_id": ticket["ticket_id"],
        "status": "position_protected",
    }
    state = _control_state(
        action_time_tickets=[ticket],
        ticket_bound_order_lifecycle_runs=[lifecycle],
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark=signal_id),
    ) is True

    lifecycle["status"] = "lifecycle_closed"
    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark=signal_id),
    ) is False


def test_orphan_runtime_safety_snapshot_cannot_revive_expired_outcome():
    state = _control_state(
        runtime_safety_state=[
            {
                "runtime_safety_snapshot_id": "safety:orphan",
                "action_time_lane_input_id": "lane:orphan",
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
                "observed_at_ms": NOW_MS - 10,
                "valid_until_ms": NOW_MS + 1_000,
                "trusted_fact_refs": {
                    "signal_event_id": "signal:SOR-001:ETHUSDT:long:expired",
                    "ticket_id": "ticket:orphan",
                },
            }
        ]
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(
            source_watermark="signal:SOR-001:ETHUSDT:long:expired"
        ),
    ) is False


def test_new_signal_identity_does_not_inherit_old_same_lane_outcome():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:new", fresh=True)
        ]
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:old"),
    ) is False
