from __future__ import annotations

from scripts.build_runtime_fresh_attempt_readiness_packet import (
    build_fresh_attempt_readiness_packet,
)


def _operator_packet(status: str = "ready_for_strategy_signal") -> dict:
    return {
        "scope": "runtime_operator_live_fact_packet",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "blockers": ["next_attempt_gate_blocked"]
        if status != "ready_for_strategy_signal"
        else [],
        "next_attempt_gate_state": {
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_packet": False,
        },
        "safety_invariants": {
            "packet_only": True,
            "exchange_write_called_by_builder": False,
            "order_lifecycle_called_by_builder": False,
        },
    }


def _fresh_loop(status: str = "ready_for_prepare") -> dict:
    return {
        "scope": "runtime_fresh_signal_prepare_loop",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "signal_input_json": "/tmp/runtime-1-signal-input.json",
        "prepared_authorization_id": "prepared-auth-1",
        "operator_command_plan": {
            "requires_fresh_authorization_before_submit": True,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def test_fresh_attempt_readiness_blocks_when_live_fact_gate_not_ready() -> None:
    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=_operator_packet("waiting_for_position_resolution"),
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_by_live_fact_gate"
    assert "live_fact_gate_not_ready_for_fresh_attempt" in packet["blockers"]
    assert packet["fresh_attempt_policy"]["legacy_authorization_replay_allowed"] is False
    assert packet["fresh_attempt_policy"]["executable_submit_allowed_by_packet"] is False
    assert packet["operator_command_plan"]["places_order"] is False


def test_fresh_attempt_readiness_waits_for_fresh_signal_after_live_gate() -> None:
    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=_operator_packet(),
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_fresh_strategy_signal"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_fresh_strategy_signal_observation"
    )
    assert packet["chain_coverage"]["fresh_strategy_signal"]["status"] == "missing"


def test_fresh_attempt_readiness_requires_evidence_after_fresh_signal_loop() -> None:
    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=_operator_packet(),
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert packet["status"] == "ready_for_readiness_evidence"
    assert packet["chain_coverage"]["fresh_strategy_signal"]["status"] == "present"
    assert packet["fresh_attempt_policy"]["requires_fresh_readiness_evidence"] is True


def test_fresh_attempt_readiness_blocks_legacy_authorization_replay() -> None:
    operator = _operator_packet()
    operator["next_attempt_gate_state"]["legacy_authorization_replay_allowed"] = True

    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=operator,
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_legacy_authorization_replay"
    assert packet["safety_invariants"]["legacy_authority_attempts"] == [
        "operator_live_fact_packet.next_attempt_gate_state.legacy_authorization_replay_allowed"
    ]
    assert "legacy_authorization_replay_attempted_as_current_authority" in packet[
        "blockers"
    ]


def test_fresh_attempt_readiness_blocks_forbidden_side_effects() -> None:
    loop = _fresh_loop()
    loop["safety_invariants"]["exchange_write_called"] = True

    packet = build_fresh_attempt_readiness_packet(
        operator_live_fact_packet=_operator_packet(),
        fresh_signal_loop=loop,
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_forbidden_effect"
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert "fresh_signal_loop.safety_invariants.exchange_write_called" in packet[
        "safety_invariants"
    ]["forbidden_effects"]
