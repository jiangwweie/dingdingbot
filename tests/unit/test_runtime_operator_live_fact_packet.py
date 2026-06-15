from __future__ import annotations

from scripts.build_runtime_operator_live_fact_packet import (
    build_operator_live_fact_packet,
)


def _complete_account() -> dict:
    return {
        "scope": "read_only_account_facts",
        "source": "tokyo_readonly",
        "timestamp_ms": 1,
    }


def _monitor_packet(**overrides) -> dict:
    packet = {
        "active_position_present": True,
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "local_active_position_count": 1,
        "exchange_active_position_count": 1,
        "local_open_order_count": 2,
        "exchange_open_stop_order_count": 1,
        "protection_status": "hard_stop_present",
        "sl_protection_present": True,
        "tp_protection_present": False,
        "hard_stop_boundary_present": True,
        "can_continue_holding": True,
        "budget_reserved": "0.10",
    }
    packet.update(overrides)
    return {
        "scope": "runtime_live_position_monitor",
        "status": "holding_with_hard_stop",
        "packet": packet,
        "safety_invariants": {
            "exchange_read_only": True,
            "exchange_write_called": False,
            "order_created": False,
            "runtime_state_mutated": False,
        },
    }


def _finalize_packet(**gate_overrides) -> dict:
    next_gate = {
        "status": "blocked",
        "attempts_remaining": 1,
        "budget_remaining": "0.90",
        "blockers": ["runtime_max_active_positions_in_use"],
    }
    next_gate.update(gate_overrides)
    return {
        "scope": "runtime_post_submit_finalize_probe",
        "status": "finalized_next_attempt_blocked",
        "post_submit_finalize_packet": {
            "status": "finalized_next_attempt_blocked",
            "next_attempt_gate": next_gate,
        },
        "safety_invariants": {"exchange_write_called": False},
    }


def test_operator_live_fact_packet_waits_on_active_position_slot() -> None:
    packet = build_operator_live_fact_packet(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=_monitor_packet(),
        post_submit_finalize=_finalize_packet(),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "waiting_for_position_resolution",
            "packet": {"status": "waiting_for_position_resolution"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocked_by_active_position_slot",
            "blockers": ["next_attempt_gate_blocked"],
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_position_resolution"
    assert packet["fact_coverage"]["account"]["status"] == "present"
    assert packet["fact_coverage"]["position"]["active_position_present"] is True
    assert packet["next_attempt_gate_state"]["legacy_authorization_replay_allowed"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_operator_live_fact_packet_waits_on_lifecycle_active_slot_blocker() -> None:
    packet = build_operator_live_fact_packet(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=_monitor_packet(
            attempts_remaining=2,
            budget_remaining="8.76",
        ),
        active_position_resolution={
            "scope": "runtime_position_lifecycle_exit_readiness_packet",
            "status": "position_lifecycle_hold_or_owner_close_ready",
            "runtime_instance_id": "runtime-1",
            "blockers": [
                "next_attempt_gate_blocked",
                "runtime_max_active_positions_in_use",
            ],
            "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
            "safety_invariants": {"no_forbidden_live_side_effects": True},
        },
        next_attempt_release={
            "scope": "runtime_live_continuation_refresh_flow",
            "status": "continuation_refresh_monitor_position_or_owner_close",
            "blockers": ["runtime-1:next_attempt_gate_blocked"],
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_position_resolution"
    assert packet["fact_coverage"]["budget"]["attempts_remaining"] == 2
    assert packet["fact_coverage"]["budget"]["budget_remaining"] == "8.76"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_read_only_position_monitoring_until_flat_or_reviewed"
    )


def test_operator_live_fact_packet_ready_requires_fresh_signal_and_authorization() -> None:
    monitor = _monitor_packet(
        active_position_present=False,
        local_active_position_count=0,
        exchange_active_position_count=0,
        local_open_order_count=0,
        exchange_open_stop_order_count=0,
        protection_status="flat_no_open_protection_required",
        sl_protection_present=False,
        tp_protection_present=False,
        hard_stop_boundary_present=False,
        can_continue_holding=False,
    )
    packet = build_operator_live_fact_packet(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=monitor,
        post_submit_finalize=_finalize_packet(
            status="ready_for_fresh_signal",
            blockers=[],
        ),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "ready_for_strategy_signal",
            "packet": {"status": "ready_for_strategy_signal"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocker_classification_no_next_attempt_gate_blocker",
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "ready_for_strategy_signal"
    assert packet["next_attempt_gate_state"]["requires_fresh_strategy_signal"] is True
    assert packet["next_attempt_gate_state"]["requires_fresh_authorization_before_submit"] is True
    assert packet["next_attempt_gate_state"]["executable_submit_allowed_by_packet"] is False
    assert packet["operator_command_plan"]["next_step"] == "start_fresh_strategy_signal_observation"


def test_operator_live_fact_packet_blocks_forbidden_effects() -> None:
    monitor = _monitor_packet()
    monitor["safety_invariants"]["order_created"] = True

    packet = build_operator_live_fact_packet(
        runtime_instance_id="runtime-1",
        account_facts=_complete_account(),
        live_position_monitor=monitor,
        post_submit_finalize=_finalize_packet(),
        next_attempt_release={
            "scope": "runtime_next_attempt_release_from_reports",
            "status": "waiting_for_position_resolution",
            "packet": {"status": "waiting_for_position_resolution"},
        },
        next_attempt_gate_classification={
            "scope": "runtime_next_attempt_gate_blocker_classification",
            "status": "gate_blocked_by_active_position_slot",
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert "live_position_monitor.safety_invariants.order_created" in packet[
        "safety_invariants"
    ]["forbidden_effects"]
