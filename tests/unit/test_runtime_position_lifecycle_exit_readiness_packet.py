from __future__ import annotations

import json

from scripts import runtime_position_lifecycle_exit_readiness_packet as script


def _gate_classification(**overrides):
    values = {
        "scope": "runtime_next_attempt_gate_blocker_classification",
        "status": "gate_blocked_by_active_position_slot",
        "runtime_instance_id": "runtime-bnb",
        "blockers": ["next_attempt_gate_blocked", "runtime_max_active_positions_in_use"],
        "warnings": ["current_position_or_protection_open_no_next_attempt"],
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
    values.update(overrides)
    return values


def _monitor_packet(**overrides):
    packet = {
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
        "hard_stop_boundary_present": True,
        "protection_status": "hard_stop_only",
        "sl_protection_present": True,
        "tp_protection_present": False,
        "can_continue_holding": True,
        "attempts_used": 1,
        "attempts_remaining": 2,
        "budget_reserved": "0.23841734",
        "budget_remaining": "8.76158266",
        "reconciliation_mismatch_types": ["missing_tp_protection"],
        "reconciliation_warning_count": 1,
        "reconciliation_severe_count": 0,
        "blockers": ["runtime_max_active_positions_in_use"],
        "warnings": [
            "missing_tp_protection_right_tail_exit_not_mounted",
            "reconciliation_warning_present",
        ],
    }
    packet.update(overrides)
    return {
        "scope": "runtime_live_position_monitor",
        "status": packet["status"],
        "packet": packet,
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _exit_plan(**overrides):
    plan = {
        "status": "ready_for_owner_review",
        "runtime_instance_id": "runtime-bnb",
        "symbol": "BNB/USDT:USDT",
        "side": "long",
        "recommended_owner_decision": (
            "keep_hard_stop_only_or_prepare_official_reduce_only_recovery"
        ),
        "tp1_quantity_feasible": False,
        "tp1_price_reference": "616.09",
        "tp1_quantity_requested": "0.005",
        "tp1_quantity_step_aligned": "0",
        "runner_quantity_reference": "0.01",
        "runner_preserved": True,
        "full_reduce_only_close_feasible": True,
        "full_reduce_only_close_quantity": "0.01",
        "full_reduce_only_close_notional_reference": "6.0503",
        "full_reduce_only_close_requires_owner_authorization": False,
        "blockers": [],
        "warnings": ["tp1_partial_quantity_below_min_qty_or_step"],
    }
    plan.update(overrides)
    return {
        "scope": "runtime_position_exit_plan",
        "status": plan["status"],
        "plan": plan,
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _followup(**overrides):
    packet = {
        "status": "ready_for_standing_reduce_only_recovery",
        "runtime_instance_id": "runtime-bnb",
        "symbol": "BNB/USDT:USDT",
        "active_position_present": True,
        "owner_close_approval_env": None,
        "owner_close_approval_value": None,
        "standing_recovery_authorization_scope": (
            "standing-authorization:strategygroup-runtime-pilot:reduce-only-recovery"
        ),
        "required_steps": [
            "prepare_official_operation_layer_reduce_only_recovery",
            "run_action_time_finalgate_for_reduce_only_recovery",
            "execute_reduce_only_recovery_through_operation_layer",
            "verify_runtime_live_position_monitor_flat",
            "record_runtime_closed_trade_review",
            "verify_next_attempt_gate",
        ],
        "completed_steps": ["fresh_monitor_read", "owner_close_packet_built"],
        "recommended_next_action": "prepare_official_reduce_only_recovery_or_continue_holding",
        "blockers": [],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
    }
    packet.update(overrides)
    return {
        "scope": "runtime_post_close_followup_packet",
        "status": packet["status"],
        "packet": packet,
        "safety_invariants": {
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def test_lifecycle_classifies_hold_or_standing_recovery_ready():
    packet = script.build_lifecycle_packet(
        gate_classification=_gate_classification(),
        live_position_monitor=_monitor_packet(),
        position_exit_plan=_exit_plan(),
        post_close_followup=_followup(),
    )

    assert packet["status"] == "position_lifecycle_hold_or_standing_recovery_ready"
    assert packet["position_facts"]["active_position_present"] is True
    assert packet["position_facts"]["hard_stop_boundary_present"] is True
    assert packet["exit_path"]["full_reduce_only_close_feasible"] is True
    assert packet["exit_path"]["tp1_quantity_feasible"] is False
    assert packet["operator_command_plan"][
        "reduce_only_close_ready_for_owner_authorization"
    ] is False
    assert packet["operator_command_plan"][
        "reduce_only_recovery_ready_for_standing_authorization"
    ] is True
    assert packet["operator_command_plan"]["requires_official_operation_layer"] is True
    assert packet["operator_command_plan"]["execute_reduce_only_close_now"] is False
    assert packet["operator_command_plan"]["allows_new_attempt_now"] is False
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is True
    assert packet["right_tail_objective_context"][
        "protected_position_may_be_held_for_right_tail"
    ] is True


def test_lifecycle_classifies_hard_stop_hold_when_close_packet_absent():
    packet = script.build_lifecycle_packet(
        gate_classification=_gate_classification(),
        live_position_monitor=_monitor_packet(),
        position_exit_plan=_exit_plan(full_reduce_only_close_feasible=False),
        post_close_followup=None,
    )

    assert packet["status"] == "position_lifecycle_hold_with_hard_stop"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_read_only_position_monitoring_until_flat_or_exit_signal"
    )


def test_lifecycle_routes_flat_runtime_to_closed_review():
    packet = script.build_lifecycle_packet(
        gate_classification=_gate_classification(
            status="gate_blocker_classification_no_next_attempt_gate_blocker",
            blockers=[],
        ),
        live_position_monitor=_monitor_packet(
            status="flat_review_required",
            active_position_present=False,
            local_active_position_count=0,
            exchange_active_position_count=0,
            hard_stop_boundary_present=False,
            sl_protection_present=False,
            can_continue_holding=False,
            blockers=[],
            warnings=[],
        ),
        position_exit_plan=None,
        post_close_followup=_followup(
            status="ready_for_closed_review",
            active_position_present=False,
            owner_close_approval_env=None,
            owner_close_approval_value=None,
            required_steps=["record_runtime_closed_trade_review", "verify_next_attempt_gate"],
            completed_steps=["runtime_flat_observed"],
        ),
    )

    assert packet["status"] == "position_lifecycle_ready_for_closed_review"
    assert packet["operator_command_plan"]["allows_new_attempt_now"] is False


def test_lifecycle_blocks_forbidden_effect():
    packet = script.build_lifecycle_packet(
        gate_classification=_gate_classification(),
        live_position_monitor=_monitor_packet(),
        position_exit_plan=_exit_plan(),
        post_close_followup=_followup(),
    )
    assert packet["status"] == "position_lifecycle_hold_or_standing_recovery_ready"

    blocked = script.build_lifecycle_packet(
        gate_classification=_gate_classification(
            safety_invariants={
                "forbidden_effects": {
                    "exchange_write_called": True,
                }
            }
        ),
        live_position_monitor=_monitor_packet(),
        position_exit_plan=_exit_plan(),
        post_close_followup=_followup(),
    )

    assert blocked["status"] == "position_lifecycle_blocked_forbidden_effect"
    assert blocked["operator_command_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )


def test_lifecycle_cli_tolerates_log_prefixed_json(tmp_path, capsys):
    gate_path = tmp_path / "gate.json"
    monitor_path = tmp_path / "monitor.json"
    exit_path = tmp_path / "exit.json"
    followup_path = tmp_path / "followup.json"
    output_path = tmp_path / "lifecycle.json"
    gate_path.write_text(json.dumps(_gate_classification()), encoding="utf-8")
    monitor_path.write_text(json.dumps(_monitor_packet()), encoding="utf-8")
    exit_path.write_text(
        "[2026-06-13 09:19:18] [INFO] Exchange connections closed\n"
        + json.dumps(_exit_plan()),
        encoding="utf-8",
    )
    followup_path.write_text(json.dumps(_followup()), encoding="utf-8")

    assert script.main(
        [
            "--gate-classification-json",
            str(gate_path),
            "--live-position-monitor-json",
            str(monitor_path),
            "--position-exit-plan-json",
            str(exit_path),
            "--post-close-followup-json",
            str(followup_path),
            "--output-json",
            str(output_path),
            "--deployed-head",
            "f8871634",
        ]
    ) == 0

    stdout_packet = json.loads(capsys.readouterr().out)
    file_packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_packet["status"] == "position_lifecycle_hold_or_standing_recovery_ready"
    assert file_packet["deployment_context"]["deployed_head"] == "f8871634"
