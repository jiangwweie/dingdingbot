from __future__ import annotations

import json

from scripts import runtime_live_continuation_selector_projection as script


def _runtime_row(
    runtime_id: str,
    *,
    status: str = "waiting_for_signal",
    blockers: list[str] | None = None,
    ready_for_prepare: bool = False,
    ready_for_final_gate_preflight: bool = False,
    symbol: str = "AVAX/USDT:USDT",
    side: str = "short",
    family: str = "BTPC-001",
) -> dict:
    return {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": symbol,
        "side": side,
        "strategy_family_id": family,
        "strategy_family_version_id": f"{family}-v0",
        "ready_for_prepare": ready_for_prepare,
        "ready_for_final_gate_preflight": ready_for_final_gate_preflight,
        "blockers": blockers or [],
        "warnings": [],
        "signal": {
            "evaluation_status": "observe_only",
            "signal_type": "no_action",
            "required_execution_mode": "observe_only",
            "confidence": "0.25",
            "reason_codes": ["no_ready_signal"],
            "human_summary": "No ready signal.",
        },
    }


def _readiness_artifact(*rows: dict, exchange_write_called: bool = False) -> dict:
    return {
        "scope": "runtime_live_attempt_readiness_artifact",
        "status": "live_attempt_blocked_by_runtime_or_signal_gate",
        "active_runtime_count": len(rows),
        "monitored_runtime_count": len(rows),
        "runtime_readiness": list(rows),
        "blockers": [
            f"{row['runtime_instance_id']}:{blocker}"
            for row in rows
            for blocker in row.get("blockers") or []
        ],
        "warnings": [],
        "safety_invariants": {
            "forbidden_effects": {
                "exchange_write_called": exchange_write_called,
                "order_created": False,
                "order_lifecycle_called": False,
                "runtime_state_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "position_closed": False,
                "execute_real_submit": False,
                "exchange_submit_armed": False,
                "local_registration_armed": False,
                "executable_execution_intent_created": False,
            }
        },
    }


def _lifecycle_artifact(**overrides) -> dict:
    artifact = {
        "scope": "runtime_position_lifecycle_exit_readiness_artifact",
        "status": "position_lifecycle_hold_or_standing_recovery_ready",
        "runtime_instance_id": "runtime-bnb",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "position_lifecycle_plan": {
            "next_step": "continue_monitoring_or_prepare_official_reduce_only_recovery",
            "allows_new_attempt_now": False,
            "reduce_only_close_ready_for_owner_authorization": False,
            "reduce_only_recovery_ready_for_standing_authorization": True,
            "standing_recovery_authorization_scope": (
                "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
            ),
        },
        "safety_invariants": {
            "forbidden_effects": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "runtime_state_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "position_closed": False,
            }
        },
    }
    artifact.update(overrides)
    return artifact


def test_selector_prioritizes_position_lifecycle_over_waiting_signals():
    readiness = _readiness_artifact(
        _runtime_row(
            "runtime-ada",
            blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
            symbol="ADA/USDT:USDT",
            family="RBR-001",
        ),
        _runtime_row(
            "runtime-bnb",
            status="blocked",
            blockers=["next_attempt_gate_blocked"],
            symbol="BNB/USDT:USDT",
            side="long",
            family="CPM-001",
        ),
        _runtime_row(
            "runtime-avax",
            blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        ),
    )

    projection = script.build_selector_projection(
        readiness_artifact=readiness,
        lifecycle_artifacts=[_lifecycle_artifact()],
    )

    assert projection["status"] == "continuation_monitor_position_or_standing_recovery"
    selected = projection["selected_continuation"]
    assert selected["runtime_instance_id"] == "runtime-bnb"
    assert selected["selected_action"] == (
        "monitor_position_or_prepare_official_reduce_only_recovery"
    )
    assert selected["reduce_only_close_ready_for_owner_authorization"] is False
    assert selected["reduce_only_recovery_ready_for_standing_authorization"] is True
    assert "operator_command_plan" not in projection
    assert projection["selector_plan"]["not_execution_authority"] is True
    assert projection["selector_plan"]["execute_reduce_only_close_now"] is False
    assert projection["selector_plan"]["execute_tiny_live_attempt_now"] is False
    assert projection["safety_invariants"]["selector_projection_only"] is True
    assert "packet_only" not in projection["safety_invariants"]
    assert projection["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_selector_prioritizes_ready_final_gate_over_position_monitoring():
    readiness = _readiness_artifact(
        _runtime_row(
            "runtime-ready",
            status="ready_for_final_gate_preflight",
            ready_for_final_gate_preflight=True,
            symbol="AVAX/USDT:USDT",
        ),
        _runtime_row(
            "runtime-bnb",
            status="blocked",
            blockers=["next_attempt_gate_blocked"],
            symbol="BNB/USDT:USDT",
            side="long",
            family="CPM-001",
        ),
    )

    projection = script.build_selector_projection(
        readiness_artifact=readiness,
        lifecycle_artifacts=[_lifecycle_artifact()],
    )

    assert projection["status"] == "continuation_ready_for_final_gate_review"
    assert projection["selected_continuation"]["runtime_instance_id"] == "runtime-ready"
    assert projection["selected_continuation"]["selected_action"] == (
        "review_final_gate_preflight"
    )


def test_selector_waits_when_all_runtimes_wait_for_signal():
    readiness = _readiness_artifact(
        _runtime_row(
            "runtime-ada",
            blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        ),
        _runtime_row(
            "runtime-avax",
            blockers=["strategy_signal_not_ready_for_shadow_candidate_prepare"],
        ),
    )

    projection = script.build_selector_projection(readiness_artifact=readiness)

    assert projection["status"] == "continuation_waiting_for_strategy_signal"
    assert projection["selector_plan"]["next_step"] == (
        "continue_live_read_only_strategy_observation"
    )


def test_selector_requests_gate_classification_when_lifecycle_missing():
    readiness = _readiness_artifact(
        _runtime_row(
            "runtime-bnb",
            status="blocked",
            blockers=["next_attempt_gate_blocked"],
            symbol="BNB/USDT:USDT",
            side="long",
            family="CPM-001",
        )
    )

    projection = script.build_selector_projection(readiness_artifact=readiness)

    assert projection["status"] == "continuation_needs_gate_blocker_classification"
    assert projection["selected_continuation"]["selected_action"] == (
        "classify_or_refresh_next_attempt_gate_blocker"
    )


def test_selector_blocks_forbidden_effects():
    readiness = _readiness_artifact(
        _runtime_row("runtime-avax"),
        exchange_write_called=True,
    )

    projection = script.build_selector_projection(readiness_artifact=readiness)

    assert projection["status"] == "continuation_blocked_forbidden_effect"
    assert projection["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert projection["selector_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )


def test_selector_cli_outputs_json(tmp_path, capsys):
    readiness_path = tmp_path / "readiness.json"
    lifecycle_path = tmp_path / "lifecycle.json"
    output_path = tmp_path / "selector.json"
    readiness_path.write_text(
        json.dumps(
            _readiness_artifact(
                _runtime_row(
                    "runtime-bnb",
                    status="blocked",
                    blockers=["next_attempt_gate_blocked"],
                    symbol="BNB/USDT:USDT",
                    side="long",
                    family="CPM-001",
                )
            )
        ),
        encoding="utf-8",
    )
    lifecycle_path.write_text(json.dumps(_lifecycle_artifact()), encoding="utf-8")

    assert script.main(
        [
            "--readiness-json",
            str(readiness_path),
            "--lifecycle-json",
            str(lifecycle_path),
            "--output-json",
            str(output_path),
            "--deployed-head",
            "182c4b71",
        ]
    ) == 0

    stdout_artifact = json.loads(capsys.readouterr().out)
    file_projection = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_artifact["status"] == "continuation_monitor_position_or_standing_recovery"
    assert file_projection["deployment_context"]["deployed_head"] == "182c4b71"
    assert "operator_command_plan" not in file_projection
