from __future__ import annotations

from src.application.action_time.process_outcome_relevance import (
    process_outcome_has_current_blocking_authority,
)
from src.application.readmodels import strategy_live_candidate_pool as candidate_pool
from src.domain.runtime_lane_identity import RuntimeLaneIdentity


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


def _typed_invocation_outcome(**overrides):
    identity = RuntimeLaneIdentity(
        candidate_scope_id="scope:SOR-001:ETHUSDT:long",
        candidate_scope_event_binding_id="binding:SOR-001:ETHUSDT:long:SOR-LONG",
        runtime_scope_binding_id="runtime_scope:SOR-001:ETHUSDT:long",
        runtime_instance_id="runtime-sor-eth-long",
        runtime_profile_id="runtime-profile:pilot",
        policy_current_id="policy:SOR-001:ETHUSDT:long",
        strategy_group_id="SOR-001",
        strategy_group_version_id="sgv:SOR-001:v2",
        symbol="ETHUSDT",
        asset_class="crypto_perpetual",
        side="long",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        event_spec_version="v2",
        event_id="SOR-LONG",
        timeframe="1h",
        time_authority="trigger_candle_close_time_ms",
    )
    row = _outcome(
        action_time_invocation_id="action_time_invocation:unit",
        scope_kind="runtime_lane",
        lane_identity_key=identity.identity_key,
        source_watermark="runtime-sor-eth-long:100",
        **identity.model_dump(mode="json"),
    )
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


def test_expired_event_scoped_outcome_keeps_current_blocking_authority():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:expired", fresh=False)
        ],
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(),
    ) is True


def test_invocation_backed_outcome_requires_full_typed_lane_identity():
    state = _control_state()

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(action_time_invocation_id="action_time_invocation:missing-identity"),
    ) is False
    assert process_outcome_has_current_blocking_authority(
        state,
        _typed_invocation_outcome(),
    ) is True
    assert process_outcome_has_current_blocking_authority(
        state,
        _typed_invocation_outcome(lane_identity_key="runtime_lane:wrong"),
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


def test_outer_action_time_refresh_failure_has_same_lane_blocking_authority():
    state = _control_state()

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(
            process_name="action_time_refresh_sequence",
            first_blocker="materialize_action_time_finalgate_preflight_timeout",
            source_watermark="ticket:exact",
        ),
    ) is True
    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(
            process_name="action_time_refresh_sequence",
            process_state="succeeded",
            first_blocker=None,
            source_watermark="ticket:exact",
        ),
    ) is False


def test_candidate_pool_projects_outer_refresh_failure_as_action_time_blocker():
    outcome = _outcome(
        process_name="action_time_refresh_sequence",
        first_blocker="materialize_action_time_finalgate_preflight_timeout",
        source_watermark="ticket:exact",
        updated_at_ms=NOW_MS,
    )

    unresolved = candidate_pool._unresolved_action_time_sequence_outcomes(
        _control_state(runtime_process_outcomes=[outcome])
    )

    assert unresolved[("SOR-001", "ETHUSDT", "long")]["first_blocker"] == (
        "materialize_action_time_finalgate_preflight_timeout"
    )


def test_other_lane_activity_does_not_erase_lane_blocker_authority():
    other_lane_signal = _signal(
        "signal:SOR-001:ETHUSDT:long:current",
        fresh=True,
    )
    other_lane_signal["symbol"] = "BTCUSDT"

    assert process_outcome_has_current_blocking_authority(
        _control_state(live_signal_events=[other_lane_signal]),
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:current"),
    ) is True


def test_monitor_filtering_expired_source_does_not_drop_event_blocker():
    assert process_outcome_has_current_blocking_authority(
        _control_state(),
        _outcome(
            source_watermark="signal:SOR-001:ETHUSDT:long:expired-and-filtered"
        ),
    ) is True


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


def test_lifecycle_closure_does_not_erase_separate_unresolved_process_outcome():
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
    ) is True


def test_orphan_runtime_safety_snapshot_does_not_change_persisted_outcome():
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
    ) is True


def test_new_signal_identity_does_not_erase_old_same_lane_outcome_before_rerun():
    state = _control_state(
        live_signal_events=[
            _signal("signal:SOR-001:ETHUSDT:long:new", fresh=True)
        ]
    )

    assert process_outcome_has_current_blocking_authority(
        state,
        _outcome(source_watermark="signal:SOR-001:ETHUSDT:long:old"),
    ) is True


def test_newer_success_for_same_process_and_lane_supersedes_old_failure():
    old_failure = _outcome(
        process_outcome_id="process_outcome:old-failure",
        updated_at_ms=NOW_MS - 100,
    )
    newer_success = _outcome(
        process_outcome_id="process_outcome:new-success",
        process_state="succeeded",
        first_blocker=None,
        updated_at_ms=NOW_MS,
    )
    state = _control_state(runtime_process_outcomes=[old_failure, newer_success])

    assert process_outcome_has_current_blocking_authority(
        state,
        old_failure,
    ) is False
