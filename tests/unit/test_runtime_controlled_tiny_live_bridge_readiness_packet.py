from __future__ import annotations

import json

from scripts import runtime_controlled_tiny_live_bridge_readiness_packet as script


def _selected(
    *,
    ready_for_prepare: bool = False,
    ready_for_final_gate_preflight: bool = False,
    runtime_id: str = "runtime-avax",
) -> dict:
    return {
        "runtime_instance_id": runtime_id,
        "selected_action": "prepare_shadow_candidate",
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "strategy_family_id": "BTPC-001",
        "strategy_family_version_id": "BTPC-001-v0",
        "ready_for_prepare": ready_for_prepare,
        "ready_for_final_gate_preflight": ready_for_final_gate_preflight,
        "blockers": [],
        "warnings": [],
    }


def _refresh(
    *,
    status: str = "continuation_refresh_monitor_position_or_owner_close",
    selected: dict | None = None,
    forbidden: bool = False,
) -> dict:
    return {
        "scope": "runtime_live_continuation_refresh_flow",
        "status": status,
        "readiness_status": "live_attempt_blocked_by_runtime_or_signal_gate",
        "selector_status": "continuation_monitor_position_or_owner_close",
        "active_runtime_count": 3,
        "selected_continuation": selected
        or {
            "runtime_instance_id": "runtime-bnb",
            "selected_action": "monitor_position_or_owner_authorize_reduce_only_close",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "strategy_family_id": "CPM-001",
            "strategy_family_version_id": "CPM-001-v0",
            "ready_for_prepare": False,
            "ready_for_final_gate_preflight": False,
        },
        "blockers": ["runtime-bnb:next_attempt_gate_blocked"],
        "warnings": ["missing_tp_protection_right_tail_exit_not_mounted"],
        "safety_invariants": {
            "packet_only": True,
            "forbidden_effects": {
                "exchange_write_called": forbidden,
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
            },
        },
        "operator_command_plan": {
            "ready_for_controlled_tiny_live_path": status
            in {
                "continuation_refresh_ready_for_prepare",
                "continuation_refresh_ready_for_final_gate_review",
            },
            "execute_tiny_live_attempt_now": False,
            "execute_reduce_only_close_now": False,
        },
    }


def test_bridge_waits_for_ready_selector_without_execution_authority():
    packet = script.build_bridge_readiness_packet(
        refresh_packet=_refresh(),
        deployed_head="b1009096",
        release_name="brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow",
    )

    assert packet["status"] == "controlled_tiny_live_bridge_waiting_for_ready_selector"
    assert packet["blockers"] == ["continuation_refresh_monitor_position_or_owner_close"]
    assert packet["bridge_inputs"]["ready_for_prepare"] is False
    assert packet["bridge_inputs"]["ready_for_final_gate_preflight"] is False
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_selector_refresh_until_ready"
    )
    assert packet["operator_command_plan"]["execute_tiny_live_attempt_now"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["operator_command_plan"]["calls_exchange"] is False
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is True


def test_bridge_marks_official_prepare_ready_only_from_prepare_refresh_status():
    packet = script.build_bridge_readiness_packet(
        refresh_packet=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(ready_for_prepare=True),
        )
    )

    assert packet["status"] == "controlled_tiny_live_bridge_ready_for_official_prepare"
    assert packet["blockers"] == []
    assert packet["operator_command_plan"]["next_step"] == (
        "run_official_prepare_then_final_gate_preflight"
    )
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False
    assert packet["right_tail_objective_context"]["new_attempt_not_started_by_bridge"]


def test_bridge_marks_final_gate_ready_only_from_final_gate_refresh_status():
    selected = _selected(ready_for_final_gate_preflight=True)
    selected["selected_action"] = "review_final_gate_preflight"
    packet = script.build_bridge_readiness_packet(
        refresh_packet=_refresh(
            status="continuation_refresh_ready_for_final_gate_review",
            selected=selected,
        )
    )

    assert packet["status"] == "controlled_tiny_live_bridge_ready_for_final_gate_review"
    assert packet["operator_command_plan"]["next_step"] == (
        "run_official_final_gate_preflight_before_controlled_tiny_live_submit"
    )
    assert packet["operator_command_plan"]["requires_fresh_final_gate_before_submit"]
    assert packet["operator_command_plan"]["calls_order_lifecycle"] is False


def test_bridge_blocks_forbidden_effects_in_source_refresh():
    packet = script.build_bridge_readiness_packet(refresh_packet=_refresh(forbidden=True))

    assert packet["status"] == "controlled_tiny_live_bridge_blocked_forbidden_effect"
    assert packet["blockers"] == ["forbidden_live_side_effect_detected"]
    assert packet["operator_command_plan"]["next_step"] == (
        "stop_and_review_forbidden_side_effects"
    )
    assert packet["safety_invariants"]["no_forbidden_live_side_effects"] is False


def test_bridge_blocks_inconsistent_ready_status_and_selected_flags():
    packet = script.build_bridge_readiness_packet(
        refresh_packet=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(ready_for_prepare=False),
        )
    )

    assert packet["status"] == "controlled_tiny_live_bridge_blocked_inconsistent_selector"
    assert packet["blockers"] == ["selector_ready_status_without_matching_selected_flags"]
    assert packet["operator_command_plan"]["next_step"] == "refresh_selector_before_bridge"


def test_bridge_blocks_mismatched_prepare_and_final_gate_flags():
    packet = script.build_bridge_readiness_packet(
        refresh_packet=_refresh(
            status="continuation_refresh_ready_for_prepare",
            selected=_selected(ready_for_prepare=False, ready_for_final_gate_preflight=True),
        )
    )

    assert packet["status"] == "controlled_tiny_live_bridge_blocked_inconsistent_selector"


def test_bridge_cli_writes_json_and_returns_zero_for_waiting(tmp_path, capsys):
    refresh_path = tmp_path / "refresh.json"
    output_path = tmp_path / "bridge.json"
    refresh_path.write_text(json.dumps(_refresh()), encoding="utf-8")

    assert script.main(
        [
            "--refresh-json",
            str(refresh_path),
            "--deployed-head",
            "b1009096",
            "--release-name",
            "brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow",
            "--remote-report-path",
            "/home/ubuntu/brc-deploy/reports/rtf099",
            "--output-json",
            str(output_path),
        ]
    ) == 0

    stdout_packet = json.loads(capsys.readouterr().out)
    file_packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_packet["status"] == "controlled_tiny_live_bridge_waiting_for_ready_selector"
    assert file_packet["deployment_context"]["deployed_head"] == "b1009096"
    assert file_packet["operator_command_plan"]["execute_tiny_live_attempt_now"] is False
