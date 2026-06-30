from __future__ import annotations

from scripts.build_runtime_fresh_attempt_readiness_projection import (
    build_fresh_attempt_readiness_projection,
)


def _operator_evidence(status: str = "ready_for_strategy_signal") -> dict:
    return {
        "scope": "runtime_operator_live_fact_evidence",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "blockers": ["next_attempt_gate_blocked"]
        if status != "ready_for_strategy_signal"
        else [],
        "next_attempt_gate_state": {
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_evidence": False,
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
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
        },
    }


def _readiness_projection(status: str = "ready_for_official_submit_call") -> dict:
    return {
        "scope": "runtime_fresh_signal_readiness_evidence",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "blockers": [],
        "warnings": [],
    }


def test_fresh_attempt_readiness_blocks_when_live_fact_gate_not_ready() -> None:
    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence("waiting_for_position_resolution"),
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert projection["status"] == "blocked_by_live_fact_gate"
    assert "live_fact_gate_not_ready_for_fresh_attempt" in projection["blockers"]
    assert projection["fresh_attempt_policy"]["legacy_authorization_replay_allowed"] is False
    assert projection["fresh_attempt_policy"]["executable_submit_allowed_by_evidence"] is False
    assert "operator_command_plan" not in projection
    assert projection["readiness_plan"]["places_order"] is False


def test_fresh_attempt_readiness_waits_for_fresh_signal_after_live_gate() -> None:
    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence(),
        generated_at_ms=1,
    )

    assert projection["status"] == "waiting_for_fresh_strategy_signal"
    assert projection["readiness_plan"]["next_step"] == (
        "continue_fresh_strategy_signal_observation"
    )
    assert projection["chain_coverage"]["fresh_strategy_signal"]["status"] == "missing"
    assert "packet_status" not in projection["chain_coverage"]["live_fact_gate"]
    assert "packet_status" not in projection["chain_coverage"]["fresh_strategy_signal"]
    assert (
        projection["chain_coverage"]["live_fact_gate"]["source_status"]
        == "ready_for_strategy_signal"
    )


def test_fresh_attempt_readiness_requires_evidence_after_fresh_signal_loop() -> None:
    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence(),
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert projection["status"] == "ready_for_readiness_evidence"
    assert projection["chain_coverage"]["fresh_strategy_signal"]["status"] == "present"
    assert projection["fresh_attempt_policy"]["requires_fresh_readiness_evidence"] is True


def test_fresh_attempt_readiness_carries_artifact_paths_for_dispatcher() -> None:
    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence(),
        fresh_signal_loop=_fresh_loop(),
        readiness_projection=_readiness_projection(
            "ready_for_fresh_submit_authorization"
        ),
        artifact_paths={"readiness_handoff_evidence": "/tmp/handoff.json"},
        generated_at_ms=1,
    )

    assert projection["status"] == "waiting_for_fresh_authorization"
    assert projection["readiness_plan"]["next_step"] == (
        "bind_or_resolve_fresh_authorization"
    )
    assert projection["artifact_paths"]["readiness_handoff_evidence"] == (
        "/tmp/handoff.json"
    )


def test_fresh_attempt_readiness_action_time_gate_uses_standing_authorization() -> None:
    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence(),
        fresh_signal_loop=_fresh_loop(),
        readiness_projection=_readiness_projection(),
        generated_at_ms=1,
    )

    readiness_plan = projection["readiness_plan"]
    assert projection["status"] == "ready_for_action_time_gate"
    assert projection["safety_invariants"]["fresh_attempt_readiness_projection_only"] is True
    assert "packet_only" not in projection["safety_invariants"]
    assert readiness_plan["next_step"] == (
        "run_action_time_final_gate_before_any_official_submit"
    )
    assert readiness_plan["requires_owner_chat_confirmation"] is False
    assert readiness_plan["uses_standing_runtime_authorization"] is True
    assert readiness_plan["requires_action_time_final_gate"] is True
    assert readiness_plan["requires_official_operation_layer"] is True
    assert readiness_plan["can_continue_without_owner_chat"] is True
    assert readiness_plan["requires_action_time_confirmation"] is False


def test_fresh_attempt_readiness_blocks_legacy_authorization_replay() -> None:
    operator = _operator_evidence()
    operator["next_attempt_gate_state"]["legacy_authorization_replay_allowed"] = True

    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=operator,
        fresh_signal_loop=_fresh_loop(),
        generated_at_ms=1,
    )

    assert projection["status"] == "blocked_legacy_authorization_replay"
    assert projection["safety_invariants"]["legacy_authority_attempts"] == [
        "operator_live_fact_evidence.next_attempt_gate_state.legacy_authorization_replay_allowed"
    ]
    assert "legacy_authorization_replay_attempted_as_current_authority" in projection[
        "blockers"
    ]


def test_fresh_attempt_readiness_blocks_forbidden_side_effects() -> None:
    loop = _fresh_loop()
    loop["safety_invariants"]["exchange_write_called"] = True

    projection = build_fresh_attempt_readiness_projection(
        operator_live_fact_evidence=_operator_evidence(),
        fresh_signal_loop=loop,
        generated_at_ms=1,
    )

    assert projection["status"] == "blocked_forbidden_effect"
    assert projection["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert "fresh_signal_loop.safety_invariants.exchange_write_called" in projection[
        "safety_invariants"
    ]["forbidden_effects"]
