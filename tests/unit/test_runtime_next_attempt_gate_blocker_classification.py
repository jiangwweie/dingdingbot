from __future__ import annotations

import json

from scripts import runtime_next_attempt_gate_blocker_classification as script


def _readiness_row(
    runtime_id: str,
    *,
    blockers: list[str] | None = None,
    status: str = "blocked",
) -> dict:
    effective_blockers = (
        ["next_attempt_gate_blocked"] if blockers is None else blockers
    )
    return {
        "runtime_instance_id": runtime_id,
        "status": status,
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "ready_for_prepare": False,
        "ready_for_final_gate_preflight": False,
        "blockers": effective_blockers,
        "warnings": ["current_position_or_protection_open_no_next_attempt"],
        "forbidden_effects": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _readiness_artifact(row: dict, *, exchange_write_called: bool = False) -> dict:
    return {
        "scope": "runtime_live_attempt_readiness_artifact",
        "status": "live_attempt_blocked_by_runtime_or_signal_gate",
        "runtime_readiness": [row],
        "safety_invariants": {
            "forbidden_effects": {
                "exchange_write_called": exchange_write_called,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "execute_real_submit": False,
                "exchange_submit_armed": False,
                "local_registration_armed": False,
                "executable_execution_intent_created": False,
                "position_opened": False,
                "position_closed": False,
            }
        },
    }


def _live_position_artifact(**overrides) -> dict:
    report = {
        "scope": "runtime_live_position_monitor",
        "status": "active_protection_warning",
        "artifact": {
            "status": "active_protection_warning",
            "runtime_instance_id": "runtime-bnb",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "active_position_present": True,
            "current_qty": "0.01",
            "entry_price": "603.86",
            "mark_price": "605.03",
            "unrealized_pnl": "0.0117",
            "local_active_position_count": 1,
            "exchange_active_position_count": 1,
            "max_active_positions": 1,
            "local_open_order_count": 1,
            "exchange_open_stop_order_count": 1,
            "protection_status": "hard_stop_only",
            "sl_protection_present": True,
            "tp_protection_present": False,
            "hard_stop_boundary_present": True,
            "can_continue_holding": True,
            "attempts_used": 1,
            "attempts_remaining": 2,
            "budget_reserved": "0.23841734",
            "budget_remaining": "8.76158266",
            "blockers": ["runtime_max_active_positions_in_use"],
            "warnings": [
                "missing_tp_protection_right_tail_exit_not_mounted",
                "reconciliation_warning_present",
            ],
            "reconciliation_mismatch_types": ["missing_tp_protection"],
            "reconciliation_warning_count": 1,
            "reconciliation_severe_count": 0,
        },
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }
    report["artifact"].update(overrides)
    return report


def test_classifies_real_active_position_slot_with_hard_stop_as_hold_monitoring():
    artifact = script.build_classification_artifact(
        readiness_artifact=_readiness_artifact(_readiness_row("runtime-bnb")),
        runtime_instance_id="runtime-bnb",
        live_position_monitor=_live_position_artifact(),
    )

    assert artifact["status"] == "gate_blocked_by_active_position_slot"
    assert artifact["has_next_attempt_gate_blocker"] is True
    assert artifact["position_facts"]["active_position_present"] is True
    assert artifact["position_facts"]["hard_stop_boundary_present"] is True
    assert artifact["position_facts"]["tp_protection_present"] is False
    assert artifact["right_tail_objective_context"][
        "hard_stop_only_is_warning_not_runaway_if_boundary_present"
    ] is True
    assert "operator_command_plan" not in artifact
    assert artifact["next_attempt_gate_blocker_plan"]["next_step"] == (
        "continue_read_only_position_monitoring_until_flat_or_signal_exit"
    )
    assert artifact["next_attempt_gate_blocker_plan"]["allows_new_attempt_now"] is False
    assert (
        artifact["safety_invariants"]["gate_blocker_classification_projection_only"]
        is True
    )
    assert "packet_only" not in artifact["safety_invariants"]
    assert artifact["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_classifies_flat_position_with_gate_blocker_as_stale_projection():
    artifact = script.build_classification_artifact(
        readiness_artifact=_readiness_artifact(_readiness_row("runtime-bnb")),
        runtime_instance_id="runtime-bnb",
        live_position_monitor=_live_position_artifact(
            active_position_present=False,
            local_active_position_count=0,
            exchange_active_position_count=0,
            blockers=[],
            warnings=[],
            hard_stop_boundary_present=False,
            sl_protection_present=False,
            tp_protection_present=False,
        ),
    )

    assert (
        artifact["status"]
        == "gate_blocked_by_stale_or_unresolved_next_attempt_projection"
    )
    assert artifact["next_attempt_gate_blocker_plan"]["next_step"] == (
        "refresh_reconciliation_or_finalize_closed_review_before_next_attempt"
    )


def test_classifies_missing_position_facts_before_live_attempt():
    artifact = script.build_classification_artifact(
        readiness_artifact=_readiness_artifact(_readiness_row("runtime-bnb")),
        runtime_instance_id="runtime-bnb",
        live_position_monitor=None,
    )

    assert artifact["status"] == "gate_blocker_classification_missing_position_facts"
    assert artifact["next_attempt_gate_blocker_plan"]["calls_exchange"] is False


def test_classifies_no_next_attempt_gate_blocker_as_return_to_readiness_flow():
    artifact = script.build_classification_artifact(
        readiness_artifact=_readiness_artifact(
            _readiness_row("runtime-bnb", blockers=[], status="waiting_for_signal")
        ),
        runtime_instance_id="runtime-bnb",
        live_position_monitor=_live_position_artifact(),
    )

    assert artifact["status"] == (
        "gate_blocker_classification_no_next_attempt_gate_blocker"
    )
    assert artifact["next_attempt_gate_blocker_plan"]["allows_new_attempt_now"] is True


def test_classifies_forbidden_effects_as_stop():
    artifact = script.build_classification_artifact(
        readiness_artifact=_readiness_artifact(
            _readiness_row("runtime-bnb"),
            exchange_write_called=True,
        ),
        runtime_instance_id="runtime-bnb",
        live_position_monitor=_live_position_artifact(),
    )

    assert artifact["status"] == "gate_blocker_classification_forbidden_effect"
    assert artifact["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert artifact["next_attempt_gate_blocker_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )


def test_classification_cli_outputs_json(tmp_path, capsys):
    readiness_path = tmp_path / "readiness.json"
    position_path = tmp_path / "position.json"
    output_path = tmp_path / "classification.json"
    readiness_path.write_text(
        json.dumps(_readiness_artifact(_readiness_row("runtime-bnb"))),
        encoding="utf-8",
    )
    position_path.write_text(json.dumps(_live_position_artifact()), encoding="utf-8")

    assert script.main(
        [
            "--readiness-json",
            str(readiness_path),
            "--runtime-instance-id",
            "runtime-bnb",
            "--live-position-monitor-json",
            str(position_path),
            "--output-json",
            str(output_path),
            "--deployed-head",
            "729f3ef8",
        ]
    ) == 0

    stdout_artifact = json.loads(capsys.readouterr().out)
    file_artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_artifact["status"] == "gate_blocked_by_active_position_slot"
    assert file_artifact["deployment_context"]["deployed_head"] == "729f3ef8"
